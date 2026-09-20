"""OrcaRouter adapter（tsumugi-agreement-compiler から移植・実証済みパターン）。

実装上の重要な制約（実測に基づく）:

1. **ストリームしない。** OrcaRouter は 1 バイトでも送出した後は fallback が
   効かない。応答はサーバ内で完結させ、UI へは型付きイベントだけを流す。
2. **Anthropic は response_format 非対応。** 構造化出力プロファイルの候補列に
   入れない（route_policy.yaml 側で宣言）。
3. **fallback は自前で回す。** extra_body による宣言的 fallback はこの
   デプロイでは無効と実測済み。候補列を complete() が順に試し、
   どれが落ちてなぜ移ったかを attempts に残す。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Final


@dataclass(slots=True)
class ModelResponse:
    """typed result。生の応答をそのまま外へ出さない。"""

    text: str
    parsed: dict[str, Any] | None
    route: str
    resolved_model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int
    schema_ok: bool
    outcome: str  # ok | ok_after_fallback | schema_violation | error | fallback_to_mock | mock
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class OrcaRouterClient:
    """OpenAI 互換クライアントの薄いラッパ。"""

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self._base_url, api_key=self._api_key,
                timeout=self._timeout, max_retries=0)
        return self._client

    def complete(
        self,
        profile: Any,  # ResolvedProfile
        *,
        system: str,
        user: str | list[dict[str, Any]],
        json_schema: dict[str, Any] | None = None,
    ) -> ModelResponse:
        """候補列を順に試す。ストリームしない。user は vision 用に parts 形式も可。"""
        client = self._ensure_client()
        attempts: list[dict[str, Any]] = []
        last_error: Exception | None = None

        for candidate in profile.routes:
            kwargs: dict[str, Any] = {
                "model": candidate,
                "temperature": profile.temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            if profile.uses_json_schema and json_schema is not None:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": json_schema.get("title", "result"),
                        "schema": json_schema,
                        "strict": profile.strict,
                    },
                }

            started = time.perf_counter()
            try:
                completion = client.chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempts.append({
                    "model": candidate,
                    "outcome": "error",
                    "status": _status_of(exc),
                    "error": type(exc).__name__,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                })
                if _is_retryable(exc) and candidate != profile.routes[-1]:
                    continue
                raise

            latency_ms = int((time.perf_counter() - started) * 1000)
            attempts.append({"model": candidate, "outcome": "ok",
                             "latency_ms": latency_ms})

            text = (completion.choices[0].message.content or "") \
                if completion.choices else ""
            parsed: dict[str, Any] | None = None
            schema_ok = True
            if profile.uses_json_schema and json_schema is not None:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    schema_ok = False
            usage = getattr(completion, "usage", None)
            return ModelResponse(
                text=text,
                parsed=parsed,
                route=candidate,  # 実際に成功した候補（第一候補で固定しない）
                resolved_model=getattr(completion, "model", None),
                input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
                cost_usd=None,
                latency_ms=latency_ms,
                schema_ok=schema_ok,
                outcome=("ok" if len(attempts) == 1 else "ok_after_fallback")
                if schema_ok else "schema_violation",
                extra={"attempts": attempts},
            )

        raise last_error if last_error else RuntimeError("候補が1つもありません")


#: 次の候補を試す価値がある失敗（5xx/429/408/409/404/接続断・タイムアウト）。
#: 400/401/403/422 は要求そのものが不正なので候補を替えても同じ → 総当たりしない。
_RETRYABLE_STATUS: Final[frozenset[int]] = frozenset(
    {404, 408, 409, 429, 500, 502, 503, 504})


def _status_of(exc: Exception) -> int | None:
    return getattr(exc, "status_code", None)


def _is_retryable(exc: Exception) -> bool:
    status = _status_of(exc)
    if status is None:
        return type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}
    return status in _RETRYABLE_STATUS or status >= 500
