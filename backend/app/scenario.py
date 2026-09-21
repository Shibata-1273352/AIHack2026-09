"""デモ運転席（/ops）用の管理操作。

障害注入・リセットはシミュレータの /admin/* を呼ぶ。診断エージェント
（ToolBelt）からは到達できない経路であり、正解情報はエージェントに渡さない。
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import settings


def _client() -> httpx.Client:
    return httpx.Client(base_url=settings.sim_url, timeout=90)


def inject(fault: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    with _client() as c:
        if fault in ("a", "both"):
            out["fault_a"] = c.post("/admin/inject/fault_a").json()
        if fault in ("b", "both"):
            out["fault_b"] = c.post("/admin/inject/fault_b").json()
    return out


def reset() -> dict[str, Any]:
    with _client() as c:
        response = c.post("/admin/reset")
        response.raise_for_status()
        result = response.json()
        if result.get("ok") is False:
            raise RuntimeError("シミュレータのリセットに失敗しました")
        return result


def ground_truth() -> dict[str, Any]:
    with _client() as c:
        return c.get("/admin/ground_truth").json()


def pulse() -> dict[str, Any]:
    """ライブテレメトリ（業務疎通・使用経路）。UI 演出専用でエージェント不可視。"""
    with _client() as c:
        return c.get("/admin/pulse", timeout=3).json()


def sim_health() -> dict[str, Any]:
    try:
        with _client() as c:
            return c.get("/healthz", timeout=3).json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
