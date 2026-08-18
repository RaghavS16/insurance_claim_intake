"""
Centralized application settings and environment validation.
"""
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: str = Field("development")
    DEBUG: bool = Field(True)
    SECRET_KEY: str = Field("dev-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, ge=5, le=1440)
    ADJUSTER_SIGNUP_CODE: str = Field("", description="Private code required to self-register an adjuster")

    DATABASE_URL: str = Field("postgresql://postgres:DBpassword@localhost:5433/insurance_claims")
    DB_POOL_SIZE: int = Field(5, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(10, ge=0, le=100)
    DB_POOL_RECYCLE: int = Field(3600, ge=60)

    OLLAMA_BASE_URL: str = Field("http://localhost:11434")
    OLLAMA_MODEL: str = Field("qwen2.5:1.5b")

    PIPER_BIN: str = Field("piper")
    PIPER_VOICE_MODEL: Optional[str] = Field("en_US-lessac-medium.onnx")
    STT_MODEL_SIZE: str = Field("small")
    VAD_AGGRESSIVENESS: int = Field(1, ge=0, le=3)
    VAD_SILENCE_MS: int = Field(800, ge=200, le=3000)
    ASR_CHUNK_MS: int = Field(1500, ge=500, le=5000)
    ASR_PARTIAL_INTERVAL_MS: int = Field(400, ge=100, le=2000)

    UPLOAD_DIR: str = Field("uploads")
    MAX_UPLOAD_SIZE_BYTES: int = Field(10 * 1024 * 1024)
    MAX_VOICE_SESSION_SECONDS: int = Field(1800, ge=60, le=7200)
    ALLOWED_ORIGINS: str = Field("http://localhost:3000")

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()] or ["http://localhost:3000"]

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"development", "staging", "production", "test"}:
            raise ValueError("ENVIRONMENT must be development, staging, production, or test")
        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("DATABASE_URL must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def enforce_production_security(self) -> "Settings":
        if self.ENVIRONMENT in {"production", "staging"}:
            if self.SECRET_KEY == "dev-secret-key-change-in-production":
                raise ValueError("SECRET_KEY must be changed in production/staging")
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production/staging")
            if not self.ADJUSTER_SIGNUP_CODE:
                raise ValueError("ADJUSTER_SIGNUP_CODE must be configured in production/staging")
        return self


settings = Settings()
