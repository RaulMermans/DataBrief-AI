from dataclasses import dataclass
import os


VALID_ENVIRONMENTS = {"development", "test", "production"}


@dataclass(frozen=True)
class Settings:
    environment: str
    cors_origins: list[str]
    max_upload_mb: int
    data_run_ttl_hours: int


def load_settings() -> Settings:
    environment = os.getenv("DATABRIEF_ENV", "development")
    if environment not in VALID_ENVIRONMENTS:
        raise RuntimeError(
            "DATABRIEF_ENV must be one of: development, test, production"
        )

    raw_origins = os.getenv("DATABRIEF_CORS_ORIGINS", "http://localhost:3000")
    cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    if not cors_origins:
        raise RuntimeError("DATABRIEF_CORS_ORIGINS must include at least one origin")

    raw_max_upload_mb = os.getenv("DATABRIEF_MAX_UPLOAD_MB", "5")
    try:
        max_upload_mb = int(raw_max_upload_mb)
    except ValueError as exc:
        raise RuntimeError("DATABRIEF_MAX_UPLOAD_MB must be an integer") from exc

    if max_upload_mb <= 0:
        raise RuntimeError("DATABRIEF_MAX_UPLOAD_MB must be greater than zero")

    raw_ttl = os.getenv("DATA_RUN_TTL_HOURS", "24")
    try:
        data_run_ttl_hours = int(raw_ttl)
    except ValueError as exc:
        raise RuntimeError("DATA_RUN_TTL_HOURS must be an integer") from exc
    if data_run_ttl_hours <= 0:
        raise RuntimeError("DATA_RUN_TTL_HOURS must be greater than zero")

    return Settings(
        environment=environment,
        cors_origins=cors_origins,
        max_upload_mb=max_upload_mb,
        data_run_ttl_hours=data_run_ttl_hours,
    )
