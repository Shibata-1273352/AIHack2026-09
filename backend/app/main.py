"""NetWalker バックエンド (:8000)。

- 案件・承認・イベントの一元管理（状態の正本はサーバ側、§9）
- SSE によるイベント配信（Mac コンソール / iPad 承認画面）
- フロントエンド（vite build 成果物）の静的配信
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import agent, approval, db, events, incident, scenario
from .config import settings

app = FastAPI(title="netwalker-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


def _pulse_loop() -> None:
    """シミュレータの軽量テレメトリを2秒周期で SSE 配信（構成図のライブ演出用）。"""
    while True:
        try:
            events.publish("sim_pulse", {"pulse": scenario.pulse()})
        except Exception:  # noqa: BLE001  sim 停止中は配信を止めるだけ（UI側は「同期待ち」表示）
            pass
        time.sleep(2)


@app.on_event("startup")
async def _startup() -> None:
    events.set_loop(asyncio.get_running_loop())
    db.conn()  # スキーマ初期化
    threading.Thread(target=_pulse_loop, daemon=True).start()


# ================================================================ 案件

class CreateIncidentReq(BaseModel):
    symptom: str = "受注画面が開かない。機器は動いているように見える"
    site: str = "拠点A"
    business: str = "受注業務（order.example.com）"
    reporter: str = "拠点担当者"


@app.post("/api/incidents")
def create_incident(req: CreateIncidentReq) -> dict[str, Any]:
    inc = incident.create(req.symptom, req.site, req.business, req.reporter,
                          mode=settings.agent_mode)
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


@app.post("/api/incidents/{incident_id}/approval")
def decide_approval(incident_id: str, req: ApprovalReq) -> dict[str, Any]:
    try:
        ap = approval.decide(incident_id, req.plan_id, req.plan_hash,
                             req.decision, req.approver)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    agent.on_approval_decided(incident_id, ap)
    return ap


class BusinessCheckReq(BaseModel):
    pass


@app.post("/api/business_check")
def business_check() -> dict[str, Any]:
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
def demo_inject(req: InjectReq) -> dict[str, Any]:
    if req.fault not in ("a", "b", "both"):
        raise HTTPException(422, "fault must be a|b|both")
    out = scenario.inject(req.fault)
    events.publish("demo", {"injected": req.fault})
    return out


@app.post("/api/demo/reset")
def demo_reset() -> dict[str, Any]:
    out = scenario.reset()
    events.publish("demo", {"reset": True})
    return out


@app.get("/api/demo/ground_truth")
def demo_ground_truth() -> dict[str, Any]:
    return scenario.ground_truth()


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return {
        "agent_mode": settings.agent_mode,
        "route_mode": settings.nw_route_mode,
        "has_api_key": settings.has_api_key,  # キーの値は返さない
        "sim": scenario.sim_health(),
        "approval_ttl_seconds": settings.approval_ttl_seconds,
    }


@app.get("/api/assets/topology-diagram.png")
def topology_png() -> FileResponse:
    p = settings.assets_dir / "topology-diagram.png"
    if not p.exists():
        raise HTTPException(404, "構成図がまだ生成されていません")
    return FileResponse(p)


# ================================================================ 静的配信（SPA）

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/{path:path}")
async def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    target = STATIC_DIR / path
    if path and target.is_file():
        return FileResponse(target)
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(404, "frontend がまだビルドされていません (frontend/ で npm run build)")
