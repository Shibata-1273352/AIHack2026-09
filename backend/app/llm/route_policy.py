"""Route policy（モデル名をコードへ直書きしない、M-17）。

route_policy.yaml がプロファイル（decide/vlm/summarize）×候補列×単価表を宣言する。
OrcaRouter は応答に原価を返さない（usage はトークン数のみ）ため、
原価は単価表から算出する。単価不明のモデルは None のままにし、0 と偽らない。
"""

from __future__ import annotations

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

    def estimate_cost_usd(self, resolved_model: str | None,
                          input_tokens: int | None,
                          output_tokens: int | None,
                          route: str | None = None) -> float | None:
        key = None
        for cand in (resolved_model, route):
            if cand and cand in self.pricing:
                key = cand
                break
        if key is None or input_tokens is None or output_tokens is None:
            return None
        p = self.pricing[key]
        return (input_tokens * p["prompt_per_million"]
                + output_tokens * p["completion_per_million"]) / 1_000_000


class RoutePolicy:
    def __init__(self, path: Path = POLICY_PATH) -> None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.version = raw.get("version", "unknown")
        self._profiles = raw["profiles"]
        self._pricing = raw.get("pricing", {})
        self.budget_per_incident_usd = raw.get("budget", {}).get(
            "per_incident_usd", 0.50)

    def resolve(self, name: str) -> ResolvedProfile:
        p = self._profiles[name]
        return ResolvedProfile(
            profile=name,
            routes=list(p["routes"]),
            temperature=float(p.get("temperature", 0)),
            timeout_seconds=int(p.get("timeout_seconds", 30)),
            uses_json_schema=p.get("response_format") == "json_schema",
            strict=bool(p.get("strict", False)),
            max_cost_usd=float(p.get("max_cost_usd", 0.05)),
            pricing=self._pricing,
        )


policy = RoutePolicy()
