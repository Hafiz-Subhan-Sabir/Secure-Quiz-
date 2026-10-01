from functools import lru_cache
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="IQ_", extra="ignore")

    app_name: str = "intelliquiz-api"
    app_version: str = "1.0.0"
    api_prefix: str = "/api/v1"
    debug: bool = True

    # Dev defaults — override via env in production
    database_url: str = "sqlite:///./intelliquiz.dev.db"
    jwt_secret: str = "change-me-in-production-use-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,https://localhost:5173,https://127.0.0.1:5173"

    ssl_enabled: bool = False
    ssl_certfile: str = ""
    ssl_keyfile: str = ""
    # When set (Railway Docker), FastAPI also serves the built Admin Web SPA.
    admin_static_dir: str = ""
    port: int = int(os.environ.get("PORT", "8080"))

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
