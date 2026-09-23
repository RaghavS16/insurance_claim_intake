"""Centralized application settings and environment validation."""
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
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
    SMTP_FROM_NAME: str = "InsureClaim AI"
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
    REDIS_URL: Optional[str] = None

    LLM_PROVIDER: str = "gemini"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    CLOUD_LLM_MODEL: str = ""
    CLOUD_LLM_BASE_URL: Optional[str] = None
    CLOUD_LLM_FALLBACK_MODELS: str = ""
    CLOUD_LLM_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_FAST_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_MAX_OUTPUT_TOKENS: int = Field(2048, ge=256, le=65536)
    EMBEDDING_PROVIDER: str = "ollama"
    EMBEDDING_BASE_URL: Optional[str] = "http://localhost:11434/v1"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_TIMEOUT_SECONDS: int = Field(30, ge=5, le=120)
    RERANK_MODEL: Optional[str] = None
    RERANK_TIMEOUT_SECONDS: int = Field(30, ge=5, le=120)

    AWS_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_SESSION_TOKEN: Optional[str] = None
    S3_BUCKET: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None
    S3_SERVER_SIDE_ENCRYPTION: str = "AES256"
    S3_PRESIGNED_URL_EXPIRE_SECONDS: int = Field(300, ge=60, le=3600)
    S3_KNOWLEDGE_PREFIX: str = "knowledge"
    S3_EVIDENCE_PREFIX: str = "claims"
    KNOWLEDGE_MAX_UPLOAD_BYTES: int = 150 * 1024 * 1024
    LLM_TIMEOUT_SECONDS: int = Field(20, ge=5, le=120)
    LLM_RETRY_ATTEMPTS: int = Field(3, ge=1, le=5)
    LLM_RETRY_BASE_DELAY_SECONDS: float = Field(1.0, ge=0.1, le=10.0)

    STT_MODEL_SIZE: str = "small"
    STT_LANGUAGE: str = "en"
    STT_DEVICE: str = "cuda"
    STT_COMPUTE_TYPE: str = "float16"
    VAD_AGGRESSIVENESS: int = Field(1, ge=0, le=3)
    PIPER_MODEL_PATH: str = "piper/en_US-ryan-medium.onnx"
    PIPER_HTTP_URL: Optional[str] = "http://localhost:5000/synthesize"
    PIPER_VOICE: Optional[str] = "en_US-lessac-medium"
    MAX_VOICE_SESSION_SECONDS: int = Field(1800, ge=60, le=7200)

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    MAX_EVIDENCE_UPLOAD_BYTES: int = 25 * 1024 * 1024
    REQUIRE_S3_IN_PRODUCTION: bool = True
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

    @field_validator("LLM_PROVIDER")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        norm = v.lower().strip()
        allowed = {"gemini", "google", "openai", "cloud", "ollama"}
        if norm not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {sorted(allowed)}.")
        return "gemini" if norm == "google" else ("openai" if norm == "cloud" else norm)

    @field_validator("EMBEDDING_PROVIDER")
    @classmethod
    def validate_embedding_provider(cls, v: str) -> str:
        norm = v.lower().strip()
        allowed = {"ollama", "gemini", "fastembed", "local", "inmemory", "openai"}
        if norm not in allowed:
            raise ValueError(f"EMBEDDING_PROVIDER must be one of {sorted(allowed)}.")
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
            if "DBpassword" in self.DATABASE_URL or "REPLACE_WITH" in self.DATABASE_URL:
                raise RuntimeError("DATABASE_URL still contains a development/example credential.")
        if self.ENVIRONMENT == "development" or self.ENVIRONMENT == "test":
            Path(self.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
        if self.ENVIRONMENT in ("production", "staging") and self.REQUIRE_S3_IN_PRODUCTION and not self.S3_BUCKET:
            raise RuntimeError("S3_BUCKET must be configured in production/staging.")
        if self.ENVIRONMENT in ("production", "staging") and self.LLM_PROVIDER == "gemini" and not (self.GEMINI_API_KEY or self.GOOGLE_API_KEY):
            raise RuntimeError("A Gemini/Google API key is required when LLM_PROVIDER=gemini.")
        if self.ENVIRONMENT in ("production", "staging") and self.EMBEDDING_PROVIDER == "gemini" and not (self.GEMINI_API_KEY or self.GOOGLE_API_KEY or self.EMBEDDING_API_KEY):
            raise RuntimeError("A Gemini/Google embedding API key is required when EMBEDDING_PROVIDER=gemini.")
        if self.ENVIRONMENT in ("production", "staging") and "openrouter.ai" in (self.EMBEDDING_BASE_URL or "").lower():
            raise RuntimeError("OpenRouter cannot be used as the embedding endpoint; configure a real embedding provider.")


settings = Settings()
