"""mock | record | live の3モード（デモ安全弁。tsumugi recorder.py の移植）。

- mock:   golden（録画済み応答）を再生。キー不要。
- record: live 実行し、応答を golden として保存（開発時に使用）。
- live:   実行。失敗・キー未設定時は golden へ自動フォールバックし、
          その事実を outcome と画面のルート表示に残す。黙って隠さない。

呼出ごとに model_run を記録し、費用は route_policy の単価表から算出する
（OrcaRouter は原価を返さない）。案件の費用上限（N-04）もここで守る。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import db, events
from ..config import settings
from .orcarouter import GuardrailBlocked, ModelResponse, OrcaRouterClient
from .route_policy import ResolvedProfile, policy


class BudgetExceeded(Exception):
    pass


class SendPolicyViolation(Exception):
    """外部送信不可データの送信をプロバイダ呼出前に遮断する（T-13/T-19）。"""


class ModelGateway:
    def __init__(self) -> None:
        self.mode = settings.nw_route_mode

    # ------------------------------------------------------------- golden

    def _recorded_path(self, key: str) -> Path:
        return settings.golden_dir / f"{key}.json"

    def load_recorded(self, key: str) -> ModelResponse | None:
        path = self._recorded_path(key)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ModelResponse(
            text=raw.get("text", ""),
            parsed=raw.get("parsed"),
            route=raw.get("route", "mock"),
            resolved_model=raw.get("resolved_model"),
            input_tokens=raw.get("input_tokens"),
            output_tokens=raw.get("output_tokens"),
            # 再生に原価は発生していない。記録時の値は extra に残し実支出は 0。
            cost_usd=0.0,
            latency_ms=int(raw.get("latency_ms", 0)),
            schema_ok=bool(raw.get("schema_ok", True)),
            outcome="mock",
            extra={"recorded_cost_usd": raw.get("cost_usd"),
                   "recorded_model": raw.get("resolved_model")},
        )

    def save_recorded(self, key: str, r: ModelResponse) -> None:
        path = self._recorded_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "text": r.text, "parsed": r.parsed, "route": r.route,
            "resolved_model": r.resolved_model,
            "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
            "cost_usd": r.cost_usd, "latency_ms": r.latency_ms,
            "schema_ok": r.schema_ok,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------- budget

    def spent_usd(self, incident_id: str) -> float:
        """費用上限の判定に使う累計。

        単価不明のモデル（Named Router・無料枠）は cost_usd が None になる。
        None を 0 として足すと**費用上限が無限**になってしまうので、
        記録時に算出した保守的な budget_cost_usd を優先して積む。
        """
        total = 0.0
        for run in db.list_records(incident_id, "model_run"):
            total += run.get("budget_cost_usd") or run.get("cost_usd") or 0.0
        return total

    def actual_usd(self, incident_id: str) -> tuple[float, bool]:
        """確定請求額の合計と、全件が確定済みかどうか。"""
        total = 0.0
        complete = True
        for run in db.list_records(incident_id, "model_run"):
            if run.get("outcome") in ("mock", "fallback_to_mock", "send_policy_violation"):
                continue
            if run.get("actual_cost_usd") is None:
                complete = False
            else:
                total += run["actual_cost_usd"]
        return total, complete

    # ------------------------------------------------------------- call

    def call(self, incident_id: str, key: str, profile_name: str, *,
             system: str, user: str | list[dict[str, Any]],
             json_schema: dict[str, Any] | None = None,
             data_class: str = "external_allowed",
             budget_usd: float | None = None) -> ModelResponse:
        # 送信ゲート（T-13/T-19）: external_allowed 以外はモード・キー有無に関わらず
        # プロバイダ呼出前に遮断し、違反を model_run として監査記録する。
        if data_class != "external_allowed":
            self._record_run(incident_id, key, profile_name, None,
                             outcome="send_policy_violation",
                             error=f"data_class={data_class} は外部送信不可")
            raise SendPolicyViolation(
                f"data_class={data_class} のデータは外部LLMへ送信できません（送信ゲート）")

        profile = policy.resolve(profile_name)

        # 費用上限: 直前の利用額 + 次呼出の予約額（上限額で保守的に見積る）。
        # 構成図PDF は案件成立前に発生するため per_document_usd の別枠で管理する
        # （budget_usd 未指定時は案件予算）。
        limit = budget_usd if budget_usd is not None else policy.budget_per_incident_usd
        if self.mode in ("live", "record") and settings.has_api_key:
            if self.spent_usd(incident_id) + profile.max_cost_usd > limit:
                raise BudgetExceeded(
                    f"費用上限 {limit} USD に到達するため新規呼出を停止しました")

        if self.mode == "mock":
            response = self.load_recorded(key) or self._empty_mock(key, profile)
        elif not settings.has_api_key:
            response = self.load_recorded(key) or self._empty_mock(key, profile)
            response.outcome = "fallback_to_mock"
            response.error = "ORCAROUTER_API_KEY が未設定のため golden を使用"
        else:
            client = OrcaRouterClient(
                base_url=settings.orcarouter_base_url,
                api_key=settings.orcarouter_api_key.get_secret_value(),
                timeout=float(profile.timeout_seconds))
            try:
                response = client.complete(
                    profile, system=system, user=user, json_schema=json_schema)
                if response.cost_usd is None:
                    response.cost_usd = profile.estimate_cost_usd(
                        response.resolved_model, response.input_tokens,
                        response.output_tokens, route=response.route)
                response.extra["budget_cost_usd"] = profile.budget_cost_usd(
                    response.resolved_model, response.input_tokens,
                    response.output_tokens, route=response.route)
                if self.mode == "record":
                    self.save_recorded(key, response)
            except GuardrailBlocked as exc:
                # ゲートウェイの防御が発動した＝設計どおりの動作。
                # 例外で調査を落とさず、案件を安全停止させるために記録して持ち上げる。
                self._record_run(incident_id, key, profile_name, None,
                                 outcome="guardrail_blocked", error=str(exc))
                raise
            except Exception as exc:  # noqa: BLE001
                fallback = self.load_recorded(key)
                if fallback is None:
                    self._record_run(incident_id, key, profile_name, None,
                                     outcome="error", error=type(exc).__name__)
                    raise
                fallback.outcome = "fallback_to_mock"
                fallback.error = type(exc).__name__
                response = fallback

        self._record_run(incident_id, key, profile_name, response)
        return response

    # ------------------------------------------------------------- misc

    def _record_run(self, incident_id: str, key: str, profile_name: str,
                    r: ModelResponse | None, outcome: str | None = None,
                    error: str | None = None) -> None:
        run = db.add_record(incident_id, "model_run", {
            "key": key, "profile": profile_name,
            "route": r.route if r else None,
            "resolved_model": r.resolved_model if r else None,
            "input_tokens": r.input_tokens if r else None,
            "output_tokens": r.output_tokens if r else None,
            "cost_usd": r.cost_usd if r else None,            # 単価表からの推定
            "budget_cost_usd": (r.extra.get("budget_cost_usd") if r else None),
            "actual_cost_usd": r.actual_cost_usd if r else None,  # 確定請求額（事後）
            "latency_ms": r.latency_ms if r else None,
            "outcome": outcome or (r.outcome if r else "error"),
            "error": error or (r.error if r else None),
            "attempts": (r.extra.get("attempts") if r else None),
            # OrcaRouter のルーティング判断（画面に「なぜこのモデルか」を出す）
            "router": r.router if r else None,
            "strategy": r.strategy if r else None,
            "fallback_level": r.fallback_level if r else None,
            "request_id": r.request_id if r else None,
        })
        events.publish("model_run", {"incident_id": incident_id, "model_run": run})

    # ------------------------------------------------------------- 実費の確定

    def finalize_actual_costs(self, incident_id: str) -> int:
        """案件の model_run に確定請求額（GET /v1/generation）を埋める。

        呼出前には取れないため案件終了時にまとめて引く。取れなかったものは
        None のまま（「未確定」として正直に出し、推定値と混ぜない）。
        """
        if self.mode == "mock" or not settings.has_api_key:
            return 0
        pending = [r for r in db.list_records(incident_id, "model_run")
                   if r.get("request_id") and r.get("actual_cost_usd") is None]
        if not pending:
            return 0
        client = OrcaRouterClient(
            base_url=settings.orcarouter_base_url,
            api_key=settings.orcarouter_api_key.get_secret_value(), timeout=15)
        filled = 0
        for run in pending:
            data = client.fetch_actual_cost(run["request_id"])
            if not data:
                continue
            run["actual_cost_usd"] = data.get("total_cost")
            run["actual_latency_ms"] = data.get("latency_ms")
            run["ttft_ms"] = data.get("ttft_ms")
            run["cost_source"] = "orcarouter_generation"
            db.update_record(run["id"], run)
            events.publish("model_run", {"incident_id": incident_id, "model_run": run})
            filled += 1
        return filled

    @staticmethod
    def _empty_mock(key: str, profile: ResolvedProfile) -> ModelResponse:
        return ModelResponse(
            text="", parsed=None, route="mock", resolved_model=None,
            input_tokens=0, output_tokens=0, cost_usd=0.0, latency_ms=0,
            schema_ok=True, outcome="mock",
            extra={"key": key, "profile": profile.profile, "empty": True})


gateway = ModelGateway()
