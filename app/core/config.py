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

    HOST: str = "127.0.0.1"
    PORT: int = 8000

    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "capacitor://localhost",
        "ionic://localhost",
    ]
    # Regex to allow localhost, 127.0.0.1, and private LAN IP ranges (10.x, 192.168.x, 172.16-31.x) on any port
    CORS_ORIGIN_REGEX: str | None = (
        r"^https?://(localhost|127\.0\.0\.1|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?$"
    )

    STORAGE_PATH: str = "./storage"
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB limit

    # JWT & Mobile PWA Session Authentication
    SECRET_KEY: str = "ewnet-secret-key-change-in-production-super-secure-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1 hour short-lived access token
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30 days persistent mobile PWA session

    # Media & Resource Storage (Database / S3 Cloud switchable)
    MEDIA_STORAGE_BACKEND: str = "database"  # "database" or "s3"
    S3_BUCKET_NAME: str = "ewnet-media"
    S3_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    S3_PUBLIC_URL_PREFIX: str | None = None

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
