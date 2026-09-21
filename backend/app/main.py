"""NetWalker バックエンド (:8000)。

- 案件・承認・イベントの一元管理（状態の正本はサーバ側、§9）
- SSE によるイベント配信（Mac コンソール / iPad 承認画面）
- フロントエンド（vite build 成果物）の静的配信
"""

from __future__ import annotations

import asyncio
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import agent, approval, db, events, incident, scenario, runtime, topology_documents
from .config import settings

app = FastAPI(title="netwalker-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


def require_token(request: Request) -> None:
    """変更系API（承認・注入・リセット）の共有トークン検査（M-09/N-02）。

    APPROVAL_TOKEN 設定時のみ有効。ヘッダ X-Netwalker-Token を定数時間比較し、
    不一致・欠落は 403。未設定時は開発モードとして従来どおり通す。
    """
    if settings.approval_token is None:
        return
    expected = settings.approval_token.get_secret_value()
    supplied = request.headers.get("X-Netwalker-Token", "")
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(403, "操作トークンが一致しません。案内されたURL（?token=付き）から開き直してください")


def _pulse_loop() -> None:
    """シミュレータの軽量テレメトリを2秒周期で SSE 配信（構成図のライブ演出用）。"""
    while True:
        try:
            events.publish("sim_pulse", {"pulse": scenario.pulse()})
        except Exception:  # noqa: BLE001  sim 停止中は配信を止めるだけ（UI側は「同期待ち」表示）
            pass
        try:
            # 冗長化制御の検知・切替履歴（自力復旧タイムライン）。正解フラグは含まない
            events.publish("sim_failover", {"failover": scenario.failover()})
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)


@app.on_event("startup")
async def _startup() -> None:
    events.set_loop(asyncio.get_running_loop())
    db.conn()  # スキーマ初期化
    threading.Thread(target=_pulse_loop, daemon=True).start()


# ================================================================ 案件

class CreateIncidentReq(BaseModel):
    topology_document_id: str | None = None
    symptom: str = "受注画面が開かない。機器は動いているように見える"
    site: str = "拠点A"
    business: str = "受注業務（order.example.com）"
    reporter: str = "拠点担当者"


@app.post("/api/incidents")
def create_incident(req: CreateIncidentReq) -> dict[str, Any]:
    with runtime.lock:
        if runtime.workers or db.latest_incident():
            raise HTTPException(409, "次のデモを開始する前にリセットしてください")
        if req.topology_document_id:
            try:
                doc = topology_documents.get_document(req.topology_document_id)
            except KeyError:
                raise HTTPException(404, "構成図が見つかりません")
            if doc["status"] != "ready" or not doc["result"]["comparison"]["ok"]:
                raise HTTPException(422, "構成図の解析と登録構成との一致確認が必要です")
        inc = incident.create(req.symptom, req.site, req.business, req.reporter,
                              mode=settings.agent_mode)
        if req.topology_document_id:
            inc = incident.set_fields(inc["id"], topology_document_id=req.topology_document_id)
        agent.start_investigation(inc["id"])
        return inc


def _bundle(inc: dict[str, Any]) -> dict[str, Any]:
    iid = inc["id"]
    return {
        "incident": inc,
        "evidence": db.list_records(iid, "evidence"),
        "hypotheses": db.list_records(iid, "hypothesis"),
        "plans": db.list_records(iid, "plan"),
        "approvals": db.list_records(iid, "approval"),
        "executions": db.list_records(iid, "execution"),
        "spans": db.list_records(iid, "span"),
        "model_runs": db.list_records(iid, "model_run"),
        "steps": db.list_records(iid, "step"),
        "handoffs": db.list_records(iid, "handoff"),
    }


@app.get("/api/incidents/latest")
def get_latest() -> dict[str, Any]:
    inc = db.latest_incident()
    if inc is None:
        return {"incident": None}
    return _bundle(inc)


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict[str, Any]:
    try:
        return _bundle(incident.get(incident_id))
    except KeyError:
        raise HTTPException(404, "incident not found")


# ================================================================ 承認（iPad）

class ApprovalReq(BaseModel):
    plan_id: str
    plan_hash: str
    decision: str  # approve | reject
    approver: str
    reason: str = ""   # 却下理由（任意）。人間向けの記録・表示のみに使う


@app.post("/api/incidents/{incident_id}/approval")
def decide_approval(incident_id: str, req: ApprovalReq, request: Request) -> dict[str, Any]:
    require_token(request)
    with runtime.lock:
        current = db.latest_incident()
        if not current or current["id"] != incident_id or runtime.workers:
            raise HTTPException(409, "この案件は終了済み、または処理中です。最新の画面を確認してください")
        return _decide_approval(incident_id, req)


def _decide_approval(incident_id: str, req: ApprovalReq) -> dict[str, Any]:
    try:
        ap = approval.decide(incident_id, req.plan_id, req.plan_hash,
                             req.decision, req.approver, req.reason)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    agent.on_approval_decided(incident_id, ap)
    return ap


# ---------------------------------------------------------------- 却下後の出口（M-12 / §14.3）

class HandoffReq(BaseModel):
    action: str            # accept | hold
    assignee: str = ""
    note: str = ""


@app.post("/api/incidents/{incident_id}/handoff")
def record_handoff(incident_id: str, req: HandoffReq, request: Request) -> dict[str, Any]:
    """引き継ぎの受領／保留を記録する（§14.3「受領・保留・残存課題が記録される」）。

    担当交代後も再入力は不要。引き継ぎレコードが証拠・仮説・計画への参照を持つ。
    """
    require_token(request)
    if req.action not in ("accept", "hold"):
        raise HTTPException(422, "action must be accept|hold")
    with runtime.lock:
        try:
            incident.get(incident_id)
        except KeyError:
            raise HTTPException(404, "案件が見つかりません")
        records = db.list_records(incident_id, "handoff")
        if not records:
            raise HTTPException(404, "この案件には引き継ぎレコードがありません")
        rec = records[-1]
        rec["status"] = "accepted" if req.action == "accept" else "held"
        rec["notes"] = [*rec.get("notes", []), {
            "at": db.now_iso(), "action": req.action,
            "assignee": req.assignee.strip()[:120],
            "note": req.note.strip()[:500],
        }]
        db.update_record(rec["id"], rec)
        events.publish("handoff", {"incident_id": incident_id, "handoff": rec})
        incident.set_activity(
            incident_id,
            "引き継ぎを受領しました（対象環境は変更していません）" if req.action == "accept"
            else "引き継ぎを保留として記録しました（対象環境は変更していません）",
            f"handoff {rec['id']} → {rec['status']}")
        return rec


@app.post("/api/incidents/{incident_id}/reinvestigate")
def reinvestigate(incident_id: str, request: Request) -> dict[str, Any]:
    """却下された案件を退避し、**障害状態はそのままに**新しい案件で調べ直す。

    sim をリセットしないので、デモは障害を注入し直さずに続行できる。
    却下した計画・証拠・引き継ぎレコードは退避された案件に残る（履歴は消えない）。
    """
    require_token(request)
    with runtime.lock:
        if runtime.workers:
            raise HTTPException(409, "調査・適用処理中です。完了してからお試しください")
        current = db.latest_incident()
        if not current or current["id"] != incident_id:
            raise HTTPException(409, "この案件は最新ではありません。画面を再読み込みしてください")
        if current["status"] not in ("NEEDS_HUMAN", "CANCELLED"):
            raise HTTPException(409, "担当者対応待ちの案件のみ調べ直せます")
        db.archive_incident(incident_id)
        inc = incident.create(current["symptom"], current["site"],
                              current["business"], current["reporter"],
                              mode=settings.agent_mode)
        carry = {"reinvestigation_of": incident_id}
        if current.get("topology_document_id"):
            carry["topology_document_id"] = current["topology_document_id"]
        inc = incident.set_fields(inc["id"], **carry)
        agent.start_investigation(inc["id"])
        return inc


class BusinessCheckReq(BaseModel):
    pass


@app.post("/api/business_check")
def business_check() -> dict[str, Any]:
    with runtime.lock:
        if runtime.workers:
            raise HTTPException(409, "調査・復旧処理の完了を待ってください")
        return _business_check()


def _business_check() -> dict[str, Any]:
    """iPad の業務確認（再読込）。拠点側検証クライアント経由の実測（§7.3）。"""
    inc = db.latest_incident()
    if inc is None:
        raise HTTPException(404, "案件がありません")
    from .tools import ToolBelt
    tools = ToolBelt(inc["id"])
    try:
        res = tools.test_business()
        return {"at": db.now_iso(), "pass": res["result"]["pass"],
                "attempts": res["result"]["attempts"],
                "body_excerpt": res["result"]["attempts"][0].get("body_excerpt", "")
                if res["result"]["attempts"] else ""}
    finally:
        tools.close()


# ================================================================ SSE

@app.get("/api/events")
async def sse(request: Request) -> StreamingResponse:
    q = events.subscribe()

    async def stream():
        try:
            yield events.sse_format({"type": "hello"})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15)
                    yield events.sse_format(payload)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            events.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ================================================================ デモ運転席（/ops）

class InjectReq(BaseModel):
    fault: str  # a | b | both


@app.post("/api/demo/inject")
def demo_inject(req: InjectReq, request: Request) -> dict[str, Any]:
    require_token(request)
    if req.fault not in ("a", "b", "both"):
        raise HTTPException(422, "fault must be a|b|both")
    with runtime.lock:
        if runtime.workers or db.latest_incident():
            raise HTTPException(409, "障害を再現する前にデモをリセットしてください")
        out = scenario.inject(req.fault)
        events.publish("demo", {"injected": req.fault})
        return out


@app.post("/api/demo/reset")
def demo_reset(request: Request) -> dict[str, Any]:
    require_token(request)
    with runtime.lock:
        if runtime.workers:
            raise HTTPException(409, "調査・適用処理中です。処理完了または承認待ちになってからリセットしてください")
        out = scenario.reset()
        db.archive_demo()
        events.publish("demo", {"reset": True})
        return out


@app.get("/api/demo/ground_truth")
def demo_ground_truth() -> dict[str, Any]:
    return scenario.ground_truth()


@app.get("/api/demo/failover")
def demo_failover() -> dict[str, Any]:
    """冗長化制御の検知・切替履歴。**正解フラグは含まない**（審査画面へ映すため）。"""
    try:
        return scenario.failover()
    except Exception as exc:  # noqa: BLE001  sim 停止中は空で返し、UI は非表示にする
        return {"history": [], "error": str(exc)}


# ---------------------------------------------------------------- モデル選択（S8-5）

@app.get("/api/models")
def list_models() -> dict[str, Any]:
    """画面から選べるモデル（構造化出力に対応と検証済みのものだけ）。

    単価はサーバ側の値を返す。フロントにモデル名も単価もハードコードしない（M-17）。
    """
    from .llm.route_policy import policy
    replay = settings.nw_route_mode == "mock" or not settings.has_api_key
    return {
        "options": policy.selectable_models(),
        "current": policy.current_override(),
        "default": policy.resolve("decide").routes[0],
        "variant": policy.variant,
        "policy_version": policy.version,
        # 処理中は切り替えられない（走っている推論の方式を途中で変えない）
        "locked": bool(runtime.workers),
        # 録画再生中は選択しても実際には呼ばれない。詐称しないため明示する
        "replay": replay,
        "budget_per_incident_usd": policy.budget_per_incident_usd,
    }


class SelectModelReq(BaseModel):
    model: str | None = None   # null で「設定どおり（自動）」へ戻す


@app.post("/api/models/select")
def select_model(req: SelectModelReq, request: Request) -> dict[str, Any]:
    """decide プロファイルの候補列をメモリ上で差し替える（永続化しない）。

    安全策:
    - 処理中は 409（走っている調査の方式を途中で変えない）
    - 料金表／検証済みリストに無いモデルは 422（400 は再試行不可で即死するため、
      構造化出力に非対応のモデルは**選ばせない**）
    - A/B/R 比較は別プロセスで起動するので、この上書きは実測値に混入しない（§12.2）
    """
    require_token(request)
    from .llm.route_policy import policy
    with runtime.lock:
        if runtime.workers:
            raise HTTPException(409, "調査・適用の処理中です。完了してから切り替えてください")
        if req.model is not None:
            if not policy.is_selectable(req.model):
                raise HTTPException(
                    422, "そのモデルは選べません（構造化出力の検証が済んだモデルのみ選択できます）")
        policy.set_override(req.model)
        replay = settings.nw_route_mode == "mock" or not settings.has_api_key
        return {
            "current": policy.current_override(),
            "applies_to": "次に開始する案件から適用されます",
            "replay": replay,
            "note": ("録画再生モードのため、選択したモデルは実際には呼ばれません"
                     if replay else ""),
        }


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    sim = scenario.sim_health()
    return {
        "agent_mode": settings.agent_mode,
        "route_mode": settings.nw_route_mode,
        "has_api_key": settings.has_api_key,  # キーの値は返さない
        "token_required": settings.approval_token is not None,  # トークン値は返さない
        "sim": sim,
        "approval_ttl_seconds": settings.approval_ttl_seconds,
    }


@app.get("/api/assets/topology-diagram.png")
def topology_png() -> FileResponse:
    p = settings.assets_dir / "topology-diagram.png"
    if not p.exists():
        raise HTTPException(404, "構成図がまだ生成されていません")
    return FileResponse(p)


@app.get("/api/assets/demo-topology.pdf")
def demo_pdf() -> FileResponse:
    return FileResponse(settings.assets_dir / "netwalker-demo-topology.pdf",
                        media_type="application/pdf", filename="netwalker-demo-topology.pdf")


@app.post("/api/topology-documents", status_code=202)
async def upload_topology(request: Request, filename: str = "diagram.pdf") -> dict:
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > topology_documents.MAX_BYTES:
            raise HTTPException(413, "PDFは10MB以下にしてください")
    with runtime.lock:
        if runtime.workers or db.latest_incident():
            raise HTTPException(409, "案件開始前にアップロードしてください。解析・調査中は完了を待ってください")
        try:
            doc = topology_documents.create_document(bytes(content), filename)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        runtime.workers.add(doc["id"])
        threading.Thread(target=runtime.run_worker,
            args=(doc["id"], topology_documents.analyze_document, doc["id"]), daemon=True).start()
        return doc


@app.get("/api/topology-documents/{doc_id}")
def topology_document(doc_id: str) -> dict:
    try:
        return topology_documents.get_document(doc_id)
    except KeyError:
        raise HTTPException(404, "構成図が見つかりません")


@app.get("/api/topology-documents/{doc_id}/preview")
def topology_preview(doc_id: str) -> FileResponse:
    try:
        path = topology_documents.document_dir(doc_id) / "page-1.png"
        if not path.exists():
            raise KeyError(doc_id)
        return FileResponse(path, media_type="image/png")
    except KeyError:
        raise HTTPException(404, "プレビューを準備中です")


# ================================================================ 静的配信（SPA）

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/{path:path}")
async def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    target = (STATIC_DIR / path).resolve()
    if not target.is_relative_to(STATIC_DIR):  # パストラバーサル防止
        raise HTTPException(404)
    if path and target.is_file():
        return FileResponse(target)
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(404, "frontend がまだビルドされていません (frontend/ で npm run build)")
