"""
Centralized application settings and environment validation.
Uses pydantic-settings to validate required configurations across
development, staging, and production environments.
"""
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings with environment validation."""

    model_config = SettingsConfigDict(env_file=str(_BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = Field("development")
    DEBUG: bool = Field(True)
    SECRET_KEY: str = Field("dev-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, ge=5, le=1440)

    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "no-reply@insurance-claims.local"
    SMTP_USE_TLS: bool = True
    OTP_LENGTH: int = Field(6, ge=4, le=8)
    OTP_EXPIRY_MINUTES: int = Field(10, ge=1, le=60)
    OTP_MAX_ATTEMPTS: int = Field(5, ge=1, le=20)
    OTP_RESEND_COOLDOWN_SECONDS: int = Field(60, ge=0)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = Field(10, ge=1, le=60)

    DATABASE_URL: str = Field("postgresql://postgres:DBpassword@localhost:5433/insurance_claims")
    DB_POOL_SIZE: int = Field(5, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(10, ge=0, le=100)
    DB_POOL_RECYCLE: int = Field(3600, ge=60)

    # LLM Settings
    LLM_PROVIDER: str = "ollama"  # "ollama" for local, "cloud" for OpenAI-compatible cloud endpoint
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # Cloud LLM Settings
    CLOUD_LLM_MODEL: str = "Qwen/Qwen3.5-27B"
    CLOUD_LLM_BASE_URL: Optional[str] = "https://openrouter.ai/api/v1"
    CLOUD_LLM_API_KEY: Optional[str] = None

    # Pipecat voice pipeline
    STT_MODEL_SIZE: str = "small"
    STT_DEVICE: str = "cuda"
    STT_COMPUTE_TYPE: str = "float16"
    VAD_AGGRESSIVENESS: int = Field(1, ge=0, le=3)
    PIPER_MODEL_PATH: str = "piper/en_US-ryan-medium.onnx"
    PIPER_HTTP_URL: Optional[str] = "http://localhost:5000/synthesize"
    PIPER_VOICE: Optional[str] = "en_US-lessac-medium"
    MAX_VOICE_SESSION_SECONDS: int = Field(1800, ge=60, le=7200)

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()] or ["http://localhost:3000"]

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
                raise ValueError("SECRET_KEY must be changed in production/staging.")
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production/staging.")
        return self

    def validate_startup(self) -> None:
        if self.ENVIRONMENT in ("production", "staging"):
            if len(self.SECRET_KEY) < 32:
                raise RuntimeError("SECRET_KEY must be at least 32 characters.")
            if "sqlite" in self.DATABASE_URL.lower():
                raise RuntimeError("SQLite is not supported for production/staging.")
        Path(self.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


settings = Settings()
