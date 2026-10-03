from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ITOPS_", extra="ignore")

    app_name: str = "ITOps Control Center API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [AnyHttpUrl("http://localhost:5173")]
    )
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://itops:replace-with-a-local-only-password@localhost:5432/itops"
    )
    database_pool_size: int = Field(default=10, ge=1, le=50)
    database_max_overflow: int = Field(default=20, ge=0, le=100)
    database_pool_timeout_seconds: int = Field(default=10, ge=1, le=60)
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    jwt_secret: SecretStr | None = None
    jwt_issuer: str = "itops-control-center"
    jwt_audience: str = "itops-control-center-api"
    access_token_minutes: int = Field(default=10, ge=2, le=30)
    refresh_token_days: int = Field(default=7, ge=1, le=30)
    refresh_cookie_name: Literal["itops_refresh"] = "itops_refresh"
    secure_cookies: bool = False
    login_rate_limit_attempts: int = Field(default=5, ge=2, le=100)
    login_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    refresh_rate_limit_attempts: int = Field(default=20, ge=2, le=500)
    refresh_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    initial_admin_email: str | None = None
    initial_admin_name: str = "Platform Administrator"
    initial_admin_password: SecretStr | None = None
    enterprise_seed_password: SecretStr | None = None
    attachment_storage_path: Path = Path(".data/attachments")
    attachment_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    attachment_clamav_host: str | None = None
    attachment_clamav_port: int = Field(default=3310, ge=1, le=65535)
    attachment_scan_timeout_seconds: int = Field(default=5, ge=1, le=30)
    attachment_scan_required: bool = False
    sla_worker_interval_seconds: int = Field(default=60, ge=5, le=3600)
    sla_worker_batch_size: int = Field(default=100, ge=1, le=1000)
    ai_provider: Literal["disabled", "openai"] = "disabled"
    ai_model: str = "gpt-5.6-luna"
    ai_embedding_model: str = "text-embedding-3-small"
    ai_embedding_dimensions: int = Field(default=1536, ge=1536, le=1536)
    ai_provider_timeout_seconds: int = Field(default=20, ge=1, le=120)
    ai_max_input_characters: int = Field(default=6000, ge=500, le=20000)
    ai_moderate_confidence_threshold: float = Field(default=0.70, ge=0, le=1)
    ai_high_confidence_threshold: float = Field(default=0.90, ge=0, le=1)
    rag_chunk_characters: int = Field(default=1200, ge=400, le=4000)
    rag_chunk_overlap_characters: int = Field(default=150, ge=0, le=500)
    rag_top_k: int = Field(default=5, ge=1, le=12)
    rag_min_similarity: float = Field(default=0.25, ge=-1, le=1)
    similar_ticket_candidate_pool: int = Field(default=100, ge=10, le=500)
    similar_ticket_top_k: int = Field(default=5, ge=1, le=12)
    similar_ticket_min_similarity: float = Field(default=0.60, ge=-1, le=1)
    monitoring_expected_heartbeat_seconds: int = Field(default=60, ge=10, le=3600)
    monitoring_heartbeat_timeout_seconds: int = Field(default=180, ge=30, le=86400)
    monitoring_metric_min_interval_seconds: int = Field(default=30, ge=10, le=3600)
    monitoring_retention_days: int = Field(default=30, ge=1, le=365)
    monitoring_worker_interval_seconds: int = Field(default=60, ge=10, le=3600)
    realtime_auth_timeout_seconds: int = Field(default=5, ge=1, le=30)
    realtime_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=10)
    realtime_heartbeat_seconds: int = Field(default=20, ge=5, le=120)
    realtime_batch_size: int = Field(default=100, ge=10, le=1000)
    realtime_retention_hours: int = Field(default=24, ge=1, le=168)
    openai_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def confidence_thresholds_are_ordered(self) -> "Settings":
        normalized_origins: list[str] = []
        for origin in self.cors_origins:
            if origin.username or origin.password or origin.query or origin.fragment:
                raise ValueError(
                    "CORS origins cannot contain credentials, query strings, or fragments"
                )
            if origin.path not in (None, "", "/") or "*" in str(origin):
                raise ValueError("CORS origins must be exact origins without paths or wildcards")
            normalized_origins.append(str(origin).rstrip("/").lower())
        if len(normalized_origins) != len(set(normalized_origins)):
            raise ValueError("CORS origins must be unique")
        if self.attachment_scan_required and not self.attachment_clamav_host:
            raise ValueError("A ClamAV host is required when attachment scanning is required")
        if self.ai_moderate_confidence_threshold > self.ai_high_confidence_threshold:
            raise ValueError("Moderate AI confidence threshold must not exceed high threshold")
        if self.rag_chunk_overlap_characters >= self.rag_chunk_characters:
            raise ValueError("RAG chunk overlap must be smaller than the chunk size")
        if self.monitoring_heartbeat_timeout_seconds <= self.monitoring_expected_heartbeat_seconds:
            raise ValueError("Monitoring timeout must exceed the expected heartbeat interval")
        if self.environment.lower() == "production":
            database_url = self.database_url.get_secret_value()
            jwt_secret = self.jwt_secret.get_secret_value() if self.jwt_secret else ""
            if (
                not database_url.startswith("postgresql+psycopg://")
                or "replace-with" in database_url
            ):
                raise ValueError("Production requires an explicit PostgreSQL database URL")
            if len(jwt_secret) < 32:
                raise ValueError("Production requires a JWT secret of at least 32 characters")
            if not self.secure_cookies:
                raise ValueError("Production requires secure cookies")
            if any(origin.scheme != "https" for origin in self.cors_origins):
                raise ValueError("Production CORS origins must use HTTPS")
            if not self.attachment_scan_required:
                raise ValueError("Production requires attachment malware scanning")
            if self.enterprise_seed_password and self.enterprise_seed_password.get_secret_value():
                raise ValueError("Enterprise demo seeding is unavailable in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
