"""
Centralized application settings and environment validation.
Uses pydantic-settings to validate required configurations across
development, staging, and production environments.
"""
import os
import secrets
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings with environment validation."""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: str = Field("development", description="deployment environment: development, staging, production")
    DEBUG: bool = Field(True, description="debug mode flag")
    SECRET_KEY: str = Field("dev-secret-key-change-in-production", description="app secret key")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, ge=5, le=1440, description="JWT access token expiry in minutes")

    SMTP_HOST: Optional[str] = Field(None, description="SMTP server host")
    SMTP_PORT: int = Field(587, description="SMTP server port")
    SMTP_USERNAME: Optional[str] = Field(None, description="SMTP auth username")
    SMTP_PASSWORD: Optional[str] = Field(None, description="SMTP auth password")
    SMTP_FROM_EMAIL: str = Field("no-reply@insurance-claims.local", description="From address")
    SMTP_USE_TLS: bool = Field(True, description="Use STARTTLS")
    OTP_LENGTH: int = Field(6, ge=4, le=8)
    OTP_EXPIRY_MINUTES: int = Field(10, ge=1, le=60)
    OTP_MAX_ATTEMPTS: int = Field(5, ge=1, le=20)
    OTP_RESEND_COOLDOWN_SECONDS: int = Field(60, ge=0)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = Field(10, ge=1, le=60)

    DATABASE_URL: str = Field("postgresql://postgres:DBpassword@localhost:5433/insurance_claims")
    DB_POOL_SIZE: int = Field(5, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(10, ge=0, le=100)
    DB_POOL_RECYCLE: int = Field(3600, ge=60)

    OLLAMA_BASE_URL: str = Field("http://localhost:11434")
    OLLAMA_MODEL: str = Field("qwen2.5:1.5b")

    # Pipecat voice pipeline
    STT_MODEL_SIZE: str = Field("small", description="faster-whisper model used by Pipecat")
    VAD_AGGRESSIVENESS: int = Field(1, ge=0, le=3, description="WebRTC VAD aggressiveness")
    PIPER_HTTP_URL: str = Field("http://localhost:5000", description="External Piper HTTP server URL")
    PIPER_VOICE: Optional[str] = Field("en_US-lessac-medium", description="Piper voice identifier")
    MAX_VOICE_SESSION_SECONDS: int = Field(1800, ge=60, le=7200)

    UPLOAD_DIR: str = Field("uploads")
    MAX_UPLOAD_SIZE_BYTES: int = Field(10 * 1024 * 1024)
    ALLOWED_ORIGINS: str = Field("http://localhost:3000")

    @property
    def allowed_origins_list(self) -> List[str]:
        if not self.ALLOWED_ORIGINS:
            return ["http://localhost:3000"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        valid_envs = {"development", "staging", "production", "test"}
        norm = v.lower().strip()
        if norm not in valid_envs:
            raise ValueError(f"ENVIRONMENT must be one of {valid_envs}, got '{v}'")
        return norm

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("DATABASE_URL must not be empty.")
        return v.strip()

    @model_validator(mode="after")
    def enforce_production_security(self) -> "Settings":
        if self.ENVIRONMENT in ("production", "staging"):
            if self.SECRET_KEY == "dev-secret-key-change-in-production":
                raise ValueError("FATAL: SECRET_KEY must be changed from the default value in production/staging environments.")
            if self.DEBUG:
                raise ValueError("FATAL: DEBUG must be set to False in production/staging environments.")
        return self

    def validate_startup(self) -> None:
        if self.ENVIRONMENT in ("production", "staging"):
            if len(self.SECRET_KEY) < 32:
                raise RuntimeError(f"Startup validation failed: SECRET_KEY must be at least 32 characters in {self.ENVIRONMENT} environment.")
            if "sqlite" in self.DATABASE_URL.lower():
                raise RuntimeError(f"Startup validation failed: SQLite is not supported for {self.ENVIRONMENT} environment. Use PostgreSQL.")
        upload_path = Path(self.UPLOAD_DIR)
        try:
            upload_path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise RuntimeError(f"Startup validation failed: Cannot create UPLOAD_DIR at '{upload_path}': {exc}")


settings = Settings()
