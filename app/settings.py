from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    # Core
    ENV: str = "dev"
    API_PREFIX: str = "/api"
    DATA_DIR: Path = Path("data").absolute()

    # Redis / RQ
    REDIS_URL: str = "redis://localhost:6379/0"
    RQ_QUEUE: str = "default"

    # Safety flags
    REQUIRE_RIGHTS_CONFIRM: bool = True

    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
