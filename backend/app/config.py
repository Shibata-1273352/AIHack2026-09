"""設定。APIキーは SecretStr で保持し、値をログ・画面・推論入力へ出さない（N-01）。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # シミュレータ制御API
    sim_url: str = "http://127.0.0.1:9000"

    # OrcaRouter（キー未設定でも scripted/mock で動作する）
    orcarouter_api_key: SecretStr | None = None
    orcarouter_base_url: str = "https://api.orcarouter.ai/v1"

    # mock | record | live（record: 実応答を golden 保存 / live: 失敗時 golden 再生）
    nw_route_mode: Literal["mock", "record", "live"] = "live"

    # auto: キーがあれば llm、なければ scripted
    nw_agent_mode: Literal["auto", "scripted", "llm"] = "auto"

    # 承認の有効期限（§10.4）
    approval_ttl_seconds: int = 300
    # 観測前提の鮮度（適用直前の再観測、§10.4）
    observation_freshness_seconds: int = 30

    data_dir: Path = BASE_DIR / "var"
    golden_dir: Path = BASE_DIR / "golden"
    assets_dir: Path = BASE_DIR / "assets"

    @property
    def has_api_key(self) -> bool:
        return self.orcarouter_api_key is not None and \
            bool(self.orcarouter_api_key.get_secret_value())

    @property
    def agent_mode(self) -> str:
        if self.nw_agent_mode == "auto":
            return "llm" if self.has_api_key else "scripted"
        return self.nw_agent_mode


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.golden_dir.mkdir(parents=True, exist_ok=True)
