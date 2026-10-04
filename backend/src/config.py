"""Centralized application settings and environment validation."""
from pathlib import Path
from typing import List, Optional
import os
import socket
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = Field("development")
    DEBUG: bool = Field(True)
    SECRET_KEY: str = Field("dev-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(30, ge=1, le=90)
    CLAIM_SLA_HOURS: int = Field(72, ge=1, le=720)
    VOICE_LATENCY_TARGET_MS: int = Field(1800, ge=250, le=10000)

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
    MFA_CHALLENGE_EXPIRE_SECONDS: int = Field(120, ge=30, le=600)
    MFA_MAX_ATTEMPTS: int = Field(5, ge=1, le=10)
    MFA_ISSUER: str = "InsureClaim AI"
    MFA_ENCRYPTION_KEY: Optional[str] = None
    MFA_RECOVERY_CODE_COUNT: int = Field(10, ge=5, le=20)

    DATABASE_URL: str = Field("postgresql://postgres:DBpassword@localhost:5433/insurance_claims")
    DB_POOL_SIZE: int = Field(5, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(10, ge=0, le=100)
    DB_POOL_RECYCLE: int = Field(3600, ge=60)
    REDIS_URL: Optional[str] = None
    OUTBOX_MAX_ATTEMPTS: int = Field(12, ge=1, le=100)

    # OpenTelemetry is enabled explicitly in production/staging when an OTLP endpoint is configured.
    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "insurance-claim-intake"
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    OTEL_EXPORTER_OTLP_HEADERS: Optional[str] = None

    LLM_PROVIDER: str = "huggingface"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    CLOUD_LLM_MODEL: str = ""

    # Production conversational AI routing.
    FAST_LLM_PROVIDER: str = "huggingface"
    FAST_LLM_MODEL: str = "openai/gpt-oss-20b:groq"
    REASONING_LLM_PROVIDER: str = "huggingface"
    REASONING_LLM_MODEL: str = "openai/gpt-oss-120b:groq"
    HF_TOKEN: Optional[str] = None
    HF_BASE_URL: str = "https://router.huggingface.co/v1"
    GROQ_API_KEY: Optional[str] = None
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    FAST_LLM_TIMEOUT_SECONDS: float = Field(8.0, ge=2.0, le=60.0)
    REASONING_LLM_TIMEOUT_SECONDS: float = Field(20.0, ge=3.0, le=120.0)
    FAST_LLM_RETRY_ATTEMPTS: int = Field(1, ge=1, le=2)
    REASONING_LLM_RETRY_ATTEMPTS: int = Field(1, ge=1, le=2)
    # Voice turns are finalized only after VAD confirms silence, then an
    # additional short debounce protects against trailing STT packets.
    VOICE_TURN_SILENCE_SECONDS: float = Field(0.3, ge=0.15, le=2.0)
    VOICE_VAD_STOP_SECONDS: float = Field(0.65, ge=0.3, le=2.0)
    VOICE_MAX_QUEUED_TURNS: int = Field(1, ge=1, le=3)
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
    S3_SERVER_SIDE_ENCRYPTION: str = "aws:kms"
    S3_KMS_KEY_ID: Optional[str] = None
    S3_PRESIGNED_URL_EXPIRE_SECONDS: int = Field(300, ge=60, le=3600)
    S3_KNOWLEDGE_PREFIX: str = "knowledge"
    S3_EVIDENCE_PREFIX: str = "claims"
    KNOWLEDGE_MAX_UPLOAD_BYTES: int = 150 * 1024 * 1024
    LLM_TIMEOUT_SECONDS: int = Field(20, ge=5, le=120)
    LLM_RETRY_ATTEMPTS: int = Field(3, ge=1, le=5)
    LLM_RETRY_BASE_DELAY_SECONDS: float = Field(1.0, ge=0.1, le=10.0)

    # Self-hosted Pipecat voice channel.
    # No paid realtime/voice provider is required by this voice path.
    VOICE_ENABLED: bool = True
    VOICE_PROVIDER: str = "pipecat_local"
    VOICE_STT_MODEL: str = "Systran/faster-distil-whisper-medium.en"
    VOICE_STT_DEVICE: str = "auto"
    VOICE_STT_COMPUTE_TYPE: str = "int8"
    VOICE_STT_LANGUAGE: str = "en"
    VOICE_STT_NO_SPEECH_PROB: float = Field(0.4, ge=0.0, le=1.0)
    VOICE_TTS_BASE_URL: str = "http://localhost:5001"
    VOICE_TTS_VOICE_ID: str = "en_US-ryan-high"
    VOICE_WORKER_ID: str = Field(default_factory=lambda: os.getenv("VOICE_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}")
    VOICE_STICKY_COOKIE_NAME: str = "voice_worker_id"
    VOICE_ICE_SERVERS: str = ""  # comma-separated STUN/TURN URLs; production requires TURN
    VOICE_EVENT_RETENTION_SECONDS: int = Field(86400, ge=300, le=2592000)
    VOICE_MAX_EVENT_TEXT_CHARS: int = Field(4000, ge=0, le=50000)
    VOICE_WORKER_DRAINING: bool = False
    VOICE_WEBRTC_CONNECTION_TIMEOUT_SECONDS: int = Field(60, ge=10, le=300)
    VOICE_PIPELINE_IDLE_TIMEOUT_SECONDS: int = Field(300, ge=30, le=3600)
    VOICE_EVENT_STREAM_MAXLEN: int = Field(1000, ge=100, le=10000)
    MAX_VOICE_SDP_BYTES: int = Field(256 * 1024, ge=16 * 1024, le=2 * 1024 * 1024)
    MAX_VOICE_SESSION_SECONDS: int = Field(1800, ge=60, le=3600)
    MAX_REQUEST_BODY_BYTES: int = Field(50 * 1024 * 1024, ge=1024, le=500 * 1024 * 1024)
    MAX_PDF_PAGES: int = Field(200, ge=1, le=2000)
    MAX_IMAGE_PIXELS: int = Field(40_000_000, ge=1_000_000, le=200_000_000)
    MAX_EXTRACTED_TEXT_CHARS: int = Field(2_000_000, ge=10_000, le=20_000_000)
    MAX_OCR_SECONDS: int = Field(30, ge=5, le=300)
    MAX_ARCHIVE_EXPANDED_BYTES: int = Field(200 * 1024 * 1024, ge=10 * 1024 * 1024, le=2 * 1024 * 1024 * 1024)
    SECURITY_FAIL_CLOSED: bool = Field(True)
    REQUIRE_REDIS_IN_PRODUCTION: bool = Field(True)
    REQUIRE_MIGRATIONS_IN_PRODUCTION: bool = Field(True)
    REQUIRE_EMAIL_VERIFICATION: bool = Field(False)
    SESSION_VERSION_CLAIM: str = "sv"
    EMBEDDING_DIMENSION: int = Field(768, ge=1, le=4096)

    # AI governance and tenant-level resource controls.
    AI_PROMPT_VERSION: str = "v4"
    AI_MAX_TURNS_PER_TENANT_PER_MINUTE: int = Field(120, ge=10, le=10000)
    AI_MAX_CONCURRENT_TURNS_PER_TENANT: int = Field(8, ge=1, le=100)
    AI_MAX_RAG_REQUESTS_PER_TENANT_PER_MINUTE: int = Field(120, ge=10, le=10000)
    AI_MAX_ESTIMATED_TOKENS_PER_TENANT_PER_DAY: int = Field(200000, ge=1000, le=100000000)
    AI_ALLOWED_MODELS: str = ""  # optional comma-separated approved exact model identifiers
    AI_ALLOW_LOCAL_FALLBACK: bool = True
    AI_REQUIRE_MODEL_GOVERNANCE_IN_PRODUCTION: bool = True
    PASSKEY_ENABLED: bool = True
    PASSKEY_RP_ID: str = "localhost"
    PASSKEY_RP_NAME: str = "InsureClaim AI"
    PASSKEY_ORIGIN: str = "http://localhost:3000"
    PASSKEY_REQUIRE_USER_VERIFICATION: bool = True
    PRIVILEGED_PASSKEY_REQUIRED: bool = False

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    MAX_EVIDENCE_UPLOAD_BYTES: int = 25 * 1024 * 1024
    REQUIRE_S3_IN_PRODUCTION: bool = True
    REQUIRE_MALWARE_SCAN: bool = True
    CLAMAV_HOST: Optional[str] = None
    CLAMAV_PORT: int = Field(3310, ge=1, le=65535)
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def voice_ice_servers_list(self) -> List[str]:
        return [item.strip() for item in self.VOICE_ICE_SERVERS.split(",") if item.strip()]

    @property
    def ai_allowed_models_list(self) -> List[str]:
        return [item.strip() for item in self.AI_ALLOWED_MODELS.split(",") if item.strip()]

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
        allowed = {"huggingface", "hf", "inference-providers", "gemini", "google", "openai", "cloud", "ollama", "groq"}
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
            if not self.REDIS_URL or not self.REDIS_URL.strip():
                raise RuntimeError("REDIS_URL is required in production/staging for distributed rate limiting and AI governance.")
        if self.ENVIRONMENT == "development" or self.ENVIRONMENT == "test":
            Path(self.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
        if self.ENVIRONMENT in ("production", "staging") and self.REQUIRE_MALWARE_SCAN and not self.CLAMAV_HOST:
            raise RuntimeError("CLAMAV_HOST is required when malware scanning is enabled.")
        if self.ENVIRONMENT in ("production", "staging") and self.REQUIRE_EMAIL_VERIFICATION and not self.SMTP_HOST:
            raise RuntimeError("SMTP_HOST is required when email verification is enabled.")
        if self.ENVIRONMENT in ("production", "staging") and self.REQUIRE_S3_IN_PRODUCTION and not self.S3_BUCKET:
            raise RuntimeError("S3_BUCKET must be configured in production/staging.")
        if self.ENVIRONMENT in ("production", "staging") and self.S3_SERVER_SIDE_ENCRYPTION == "aws:kms" and not self.S3_KMS_KEY_ID:
            raise RuntimeError("S3_KMS_KEY_ID is required when S3_SERVER_SIDE_ENCRYPTION=aws:kms.")
        if self.ENVIRONMENT in ("production", "staging") and self.LLM_PROVIDER == "gemini" and not (self.GEMINI_API_KEY or self.GOOGLE_API_KEY):
            raise RuntimeError("A Gemini/Google API key is required when LLM_PROVIDER=gemini.")
        hf_needed = (
            self.FAST_LLM_PROVIDER in ("huggingface", "hf", "inference-providers")
            or self.REASONING_LLM_PROVIDER in ("huggingface", "hf", "inference-providers")
            or self.LLM_PROVIDER in ("huggingface", "hf", "inference-providers")
        )
        if self.ENVIRONMENT in ("production", "staging") and hf_needed and not self.HF_TOKEN:
            raise RuntimeError("HF_TOKEN is required when a production LLM profile uses Hugging Face Inference Providers.")
        if self.ENVIRONMENT in ("production", "staging") and self.VOICE_ENABLED and self.VOICE_PROVIDER == "pipecat_local":
            if not self.VOICE_TTS_BASE_URL:
                raise RuntimeError("VOICE_TTS_BASE_URL is required when production/staging voice uses Pipecat.")
            ice = [x.strip() for x in self.VOICE_ICE_SERVERS.split(",") if x.strip()]
            if not any(x.lower().startswith(("turn:", "turns:")) for x in ice):
                raise RuntimeError("VOICE_ICE_SERVERS must include a TURN server in production/staging.")
            if self.PRIVILEGED_PASSKEY_REQUIRED and not self.PASSKEY_ENABLED:
                raise RuntimeError("PASSKEY_ENABLED must remain true when privileged passkeys are required.")
        groq_needed = self.FAST_LLM_PROVIDER == "groq" or self.REASONING_LLM_PROVIDER == "groq" or self.LLM_PROVIDER == "groq"
        if self.ENVIRONMENT in ("production", "staging") and groq_needed and not self.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is required only when the direct Groq provider is selected.")
        if self.ENVIRONMENT in ("production", "staging") and self.EMBEDDING_PROVIDER == "gemini" and not (self.GEMINI_API_KEY or self.GOOGLE_API_KEY or self.EMBEDDING_API_KEY):
            raise RuntimeError("A Gemini/Google embedding API key is required when EMBEDDING_PROVIDER=gemini.")
        if self.ENVIRONMENT in ("production", "staging") and "openrouter.ai" in (self.EMBEDDING_BASE_URL or "").lower():
            raise RuntimeError("OpenRouter cannot be used as the embedding endpoint; configure a real embedding provider.")
        if self.ENVIRONMENT in ("production", "staging") and self.AI_REQUIRE_MODEL_GOVERNANCE_IN_PRODUCTION and not self.AI_ALLOWED_MODELS:
            raise RuntimeError("AI_ALLOWED_MODELS must be configured in production/staging.")
        if self.ENVIRONMENT in ("production", "staging") and self.PRIVILEGED_PASSKEY_REQUIRED and not self.PASSKEY_ORIGIN.startswith("https://"):
            raise RuntimeError("PASSKEY_ORIGIN must use HTTPS when privileged passkeys are required in production/staging.")
        if self.ENVIRONMENT == "production" and not self.PRIVILEGED_PASSKEY_REQUIRED:
            raise RuntimeError("PRIVILEGED_PASSKEY_REQUIRED must be true in production. Privileged accounts require phishing-resistant authentication.")


settings = Settings()
