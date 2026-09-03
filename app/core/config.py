from functools import lru_cache
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# libpq-style query params that asyncpg rejects as connect() kwargs.
_ASYNCPG_UNSUPPORTED_QUERY_PARAMS = frozenset(
    {
        "sslmode",
        "channel_binding",
        "sslcert",
        "sslkey",
        "sslrootcert",
        "sslcrl",
        "sslpassword",
        "gssencmode",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    DATABASE_URL: PostgresDsn
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "EWNet Reader API"
    DEBUG: bool = False

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    STORAGE_PATH: str = "./storage"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async URL with libpq-only query params removed for asyncpg."""
        url = str(self.DATABASE_URL)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        parsed = urlparse(url)
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        cleaned = [
            (key, value)
            for key, value in query_pairs
            if key.lower() not in _ASYNCPG_UNSUPPORTED_QUERY_PARAMS
        ]
        return urlunparse(parsed._replace(query=urlencode(cleaned)))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_connect_args(self) -> dict[str, Any]:
        """Enable TLS for Neon/cloud URLs that use sslmode=require."""
        raw = str(self.DATABASE_URL).lower()
        parsed = urlparse(raw)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        sslmode = query.get("sslmode", "").lower()
        needs_ssl = sslmode in {"require", "verify-ca", "verify-full"} or "neon.tech" in (
            parsed.hostname or ""
        )
        if needs_ssl:
            return {"ssl": True}
        return {}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
