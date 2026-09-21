"""OrcaRouter adapter（tsumugi-agreement-compiler から移植・実証済みパターン）。

実装上の重要な制約（実測に基づく）:

1. **ストリームしない。** OrcaRouter は 1 バイトでも送出した後は fallback が
   効かない。応答はサーバ内で完結させ、UI へは型付きイベントだけを流す。
2. **Anthropic は response_format 非対応。** 構造化出力プロファイルの候補列に
   入れない（route_policy.yaml 側で宣言）。
3. **fallback は自前で回す。** extra_body による宣言的 fallback はこの
   デプロイでは無効と実測済み。候補列を complete() が順に試し、
   どれが落ちてなぜ移ったかを attempts に残す。
4. **Named Router（orcarouter/auto 等）は構造化出力に対応している**（2026-09-21 実測）。
   製品側のルーティング判断は `X-Orca-*` ヘッダで返るので、
   with_raw_response でヘッダごと受け取り、画面に「どのモデルをなぜ選んだか」を出す。
5. **実費は GET /v1/generation?id=<X-Orca-Request-Id> で取れる**（total_cost・USD）。
   単価表からの推定ではなく確定請求額なので、評価・表示はこちらを使う。
   ただし呼出前には取得できないため、**予算の事前チェックは単価表のまま**。
"""

from __future__ import annotations

import json
import time
from jsonschema import validate, ValidationError
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
    outcome: str  # ok | ok_after_fallback | schema_violation | error | fallback_to_mock | mock | guardrail_blocked
    error: str | None = None
    # ---- OrcaRouter のルーティング判断（X-Orca-* ヘッダ由来） ----
    router: str | None = None           # 使われた Named Router（auto / fusion-flash …）
    strategy: str | None = None         # 選択戦略（balanced 等）
    fallback_level: int | None = None   # 何段目の候補で成功したか
    request_id: str | None = None       # 実費照会（GET /v1/generation）のキー
    actual_cost_usd: float | None = None  # 確定請求額（事後に埋める）
    extra: dict[str, Any] = field(default_factory=dict)


class GuardrailBlocked(Exception):
    """ゲートウェイのガードレールが送信内容を遮断した（設計どおりの防御動作）。

    400 を「再試行不可の異常終了」として扱うと、**防御が発動した瞬間に調査が
    落ちる**。これは不具合なので、遮断は専用の例外として持ち上げ、
    案件は安全停止（NEEDS_HUMAN）させる。
    """

    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


#: ガードレール遮断を示す語（OrcaRouter のエラー本文に現れるもの）。
_GUARDRAIL_MARKERS: Final[tuple[str, ...]] = (
    "guardrail", "guard rail", "blocked by policy", "content_filter",
    "content filter", "moderation", "policy_violation", "policy violation",
    "denylist", "deny list", "prohibited", "flagged",
)


def _error_body(exc: Exception) -> str:
    """例外から本文テキストを取り出す（SDK のバージョン差を吸収する）。"""
    parts: list[str] = [str(exc)]
    body = getattr(exc, "body", None)
    if body is not None:
        parts.append(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False))
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            parts.append(resp.text)
        except Exception:  # noqa: BLE001
            pass
    return " ".join(p for p in parts if p)[:4000]


def is_guardrail_block(exc: Exception) -> bool:
    """400 のうちガードレール起因かを判別する（それ以外の 400 は従来どおり）。"""
    if _status_of(exc) != 400:
        return False
    text = _error_body(exc).lower()
    return any(m in text for m in _GUARDRAIL_MARKERS)


def _parse_route_header(value: str | None) -> dict[str, str]:
    """`model=qwen/qwen3.7-plus; by=balanced; class=chat; fallback=0` を辞書にする。"""
    out: dict[str, str] = {}
    for part in (value or "").split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


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
                # ヘッダごと受け取る（ルーティング判断と実費照会IDはヘッダにしか無い）
                raw = client.chat.completions.with_raw_response.create(**kwargs)
                completion = raw.parse()
                headers = raw.headers
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                latency_ms = int((time.perf_counter() - started) * 1000)
                if is_guardrail_block(exc):
                    # 設計どおりの防御動作。候補を替えても同じ内容なので総当たりしない
                    attempts.append({"model": candidate, "outcome": "guardrail_blocked",
                                     "status": 400, "latency_ms": latency_ms})
                    raise GuardrailBlocked(
                        "ゲートウェイのガードレールが送信内容を遮断しました",
                        {"model": candidate, "attempts": attempts,
                         "body": _error_body(exc)[:600]}) from exc
                attempts.append({
                    "model": candidate,
                    "outcome": "error",
                    "status": _status_of(exc),
                    "error": type(exc).__name__,
                    "latency_ms": latency_ms,
                })
                if _is_retryable(exc) and candidate != profile.routes[-1]:
                    continue
                raise

            latency_ms = int((time.perf_counter() - started) * 1000)
            route_hdr = _parse_route_header(headers.get("x-orca-route"))
            attempts.append({"model": candidate, "outcome": "ok",
                             "latency_ms": latency_ms,
                             "resolved": route_hdr.get("model"),
                             "by": route_hdr.get("by")})

            text = (completion.choices[0].message.content or "") \
                if completion.choices else ""
            parsed: dict[str, Any] | None = None
            schema_ok = True
            if profile.uses_json_schema and json_schema is not None:
                try:
                    parsed = json.loads(text)
                    validate(parsed, json_schema)
                except (json.JSONDecodeError, ValidationError):
                    schema_ok = False
            usage = getattr(completion, "usage", None)
            # ヘッダの解決済みモデルは "qwen/qwen3.7-plus" のように提供元付きで、
            # 単価表のキーと一致する。body の model はプレフィクスが落ちることがある。
            resolved = (headers.get("x-orca-resolved-model")
                        or route_hdr.get("model")
                        or getattr(completion, "model", None))
            fb = route_hdr.get("fallback")
            hdr_fb = headers.get("x-orca-fallback-level")
            return ModelResponse(
                text=text,
                parsed=parsed,
                route=candidate,  # 実際に成功した候補（第一候補で固定しない）
                resolved_model=resolved,
                input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
                cost_usd=None,
                latency_ms=latency_ms,
                schema_ok=schema_ok,
                outcome=("ok" if len(attempts) == 1 else "ok_after_fallback")
                if schema_ok else "schema_violation",
                router=headers.get("x-orca-router"),
                strategy=route_hdr.get("by"),
                fallback_level=_as_int(hdr_fb if hdr_fb is not None else fb),
                request_id=headers.get("x-orca-request-id"),
                extra={"attempts": attempts},
            )

        raise last_error if last_error else RuntimeError("候補が1つもありません")

    def fetch_actual_cost(self, request_id: str,
                          retries: int = 3, delay: float = 1.0) -> dict[str, Any] | None:
        """GET /v1/generation で確定請求額を引く。未確定(404)は数回だけ待って諦める。

        推定ではなく実請求額なので、評価と画面表示はこちらを使う。
        取れなかった場合は None を返し、「未確定」として正直に出す（0 と偽らない）。
        """
        import httpx

        url = f"{self._base_url.rstrip('/')}/generation"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        with httpx.Client(timeout=15) as c:
            for i in range(retries):
                try:
                    r = c.get(url, params={"id": request_id}, headers=headers)
                except Exception:  # noqa: BLE001  ネットワーク不調は諦める（費用は推定のまま）
                    return None
                if r.status_code == 200:
                    return (r.json() or {}).get("data")
                if r.status_code != 404:
                    return None
                if i < retries - 1:
                    time.sleep(delay)
        return None


def _as_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


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
