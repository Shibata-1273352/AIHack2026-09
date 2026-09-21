"""Route policy（モデル名をコードへ直書きしない、M-17）。

route_policy.yaml がプロファイル（decide/vlm/summarize）×候補列×単価表×
選択可能モデル（capabilities）を宣言する。

費用の扱い（誠実性のため二本立てにする）:
- **呼出前の予算判定** … 単価表からの推定。実費は事後にしか出ないため。
  単価不明のモデル（Named Router・無料枠）は `unknown_model_pricing` で
  保守的に上振れ見積りする。0 円扱いにすると費用上限が無限になるため。
- **表示・評価** … OrcaRouter の GET /v1/generation が返す確定請求額。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

POLICY_PATH = Path(__file__).parent / "route_policy.yaml"


@dataclass(slots=True)
class ResolvedProfile:
    profile: str
    routes: list[str]
    temperature: float
    timeout_seconds: int
    uses_json_schema: bool
    strict: bool
    max_cost_usd: float
    pricing: dict[str, dict[str, float]] = field(default_factory=dict)
    unknown_pricing: dict[str, float] | None = None
    #: 候補列の出所（policy = 設定どおり / override = 画面からの選択）
    source: str = "policy"
    variant: str = "b"

    def _price_of(self, resolved_model: str | None,
                  route: str | None) -> dict[str, float] | None:
        for cand in (resolved_model, route):
            if cand and cand in self.pricing:
                return self.pricing[cand]
        return None

    def estimate_cost_usd(self, resolved_model: str | None,
                          input_tokens: int | None,
                          output_tokens: int | None,
                          route: str | None = None) -> float | None:
        """単価表からの推定。単価不明なら None（0 と偽らない）。"""
        p = self._price_of(resolved_model, route)
        if p is None or input_tokens is None or output_tokens is None:
            return None
        return (input_tokens * p["prompt_per_million"]
                + output_tokens * p["completion_per_million"]) / 1_000_000

    def budget_cost_usd(self, resolved_model: str | None,
                        input_tokens: int | None,
                        output_tokens: int | None,
                        route: str | None = None) -> float:
        """費用上限の判定に使う保守的な額。単価不明でも 0 にしない。"""
        est = self.estimate_cost_usd(resolved_model, input_tokens, output_tokens, route)
        if est is not None:
            return est
        p = self.unknown_pricing
        if p and input_tokens is not None and output_tokens is not None:
            return (input_tokens * p["prompt_per_million"]
                    + output_tokens * p["completion_per_million"]) / 1_000_000
        # トークン数すら分からない場合はプロファイルの上限額で見積る
        return self.max_cost_usd


class RoutePolicy:
    def __init__(self, path: Path = POLICY_PATH) -> None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.version = raw.get("version", "unknown")
        self._profiles = raw["profiles"]
        self._pricing = raw.get("pricing", {})
        self._unknown_pricing = raw.get("unknown_model_pricing")
        self._variants = raw.get("variants", {})
        self._capabilities = raw.get("capabilities", {})
        budget = raw.get("budget", {})
        self.budget_per_incident_usd = budget.get("per_incident_usd", 0.50)
        self.budget_per_document_usd = budget.get("per_document_usd", 0.20)
        # 画面からのモデル選択（メモリ上書き。**永続化しない**）
        self._lock = threading.Lock()
        self._override: str | None = None

    # ------------------------------------------------------------ 選択肢

    @property
    def capabilities(self) -> dict[str, dict[str, Any]]:
        return self._capabilities

    def pricing_of(self, model: str) -> dict[str, float] | None:
        return self._pricing.get(model)

    def selectable_models(self) -> list[dict[str, Any]]:
        """UI に出す選択肢。構造化出力に対応と検証済みのものだけを載せる。"""
        out: list[dict[str, Any]] = []
        for model, cap in self._capabilities.items():
            if not cap.get("json_schema"):
                continue
            out.append({
                "model": model,
                "display": cap.get("display", model),
                "note": cap.get("note", ""),
                "vision": bool(cap.get("vision")),
                "verified_at": cap.get("verified_at"),
                # 単価はサーバの値を返す。フロントにハードコードしない
                "pricing": self._pricing.get(model),
                "named_router": model.startswith("orcarouter/"),
            })
        return out

    def is_selectable(self, model: str) -> bool:
        cap = self._capabilities.get(model)
        return bool(cap and cap.get("json_schema"))

    def supports_json_schema(self, model: str) -> bool:
        cap = self._capabilities.get(model)
        return bool(cap and cap.get("json_schema"))

    # ------------------------------------------------------------ 上書き

    def set_override(self, model: str | None) -> None:
        """decide プロファイルの候補列をメモリ上で差し替える。

        **永続化しない**（プロセス再起動で消える）。A/B/R 比較は別プロセスで
        起動するため、この上書きが実測値へ混入することはない（§12.2 の誠実性）。
        """
        with self._lock:
            self._override = model

    def current_override(self) -> str | None:
        with self._lock:
            return self._override

    # ------------------------------------------------------------ 解決

    @property
    def variant(self) -> str:
        """比較評価の方式（a|b|bs）。既定は b（製品のルーティング）。"""
        from ..config import settings
        return settings.nw_route_variant

    def resolve(self, name: str) -> ResolvedProfile:
        p = self._profiles[name]
        variant = self.variant
        # 方式ごとの上書き（候補列のみ差し替え、単価表・上限は共通）
        override = (self._variants.get(variant, {}).get("profiles") or {}).get(name)
        if override:
            p = {**p, **override}
        # 画面からの選択は variant マージの「後」に適用する（decide のみ）
        source = "policy"
        chosen = self.current_override()
        if name == "decide" and chosen:
            p = {**p, "routes": [chosen]}
            source = "override"
        return ResolvedProfile(
            profile=name,
            routes=list(p["routes"]),
            temperature=float(p.get("temperature", 0)),
            timeout_seconds=int(p.get("timeout_seconds", 30)),
            uses_json_schema=p.get("response_format") == "json_schema",
            strict=bool(p.get("strict", False)),
            max_cost_usd=float(p.get("max_cost_usd", 0.05)),
            pricing=self._pricing,
            unknown_pricing=self._unknown_pricing,
            source=source,
            variant=variant,
        )


policy = RoutePolicy()
