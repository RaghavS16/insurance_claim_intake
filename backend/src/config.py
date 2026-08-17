"""
Centralized application settings and environment validation.
Uses pydantic-settings to validate required configurations across
development, staging, and production environments.
"""
import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine backend root for .env loading
_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings with environment validation."""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: str = Field("development", description="deployment environment: development, staging, production")
    DEBUG: bool = Field(True, description="debug mode flag")
    SECRET_KEY: str = Field("dev-secret-key-change-in-production", description="app secret key")

    # Database
    DATABASE_URL: str = Field(
        "postgresql://postgres:DBpassword@localhost:5433/insurance_claims",
        description="Database connection URL (PostgreSQL or SQLite)",
    )

    # LLM / Ollama
    OLLAMA_BASE_URL: str = Field("http://localhost:11434", description="Ollama API base URL")
    OLLAMA_MODEL: str = Field("qwen2.5:1.5b", description="Ollama model name")

    # Voice Pipeline
    PIPER_BIN: str = Field("piper", description="Path or command for Piper TTS executable")
    PIPER_VOICE_MODEL: Optional[str] = Field("en_US-lessac-medium.onnx", description="Piper ONNX voice model path")
    STT_MODEL_SIZE: str = Field("small", description="faster-whisper model size")
    VAD_AGGRESSIVENESS: int = Field(1, ge=0, le=3, description="WebRTC VAD aggressiveness mode (0-3)")
    # Silence duration (ms) after which speech endpoint is declared and ASR finalizes.
    # Lower values reduce turn-detection latency. Default 800ms balances accuracy vs. responsiveness.
    VAD_SILENCE_MS: int = Field(800, ge=200, le=3000, description="Silence duration (ms) before utterance endpoint")
    # How many ms of audio to accumulate before running a partial Whisper transcription.
    # Lower = more frequent partials but higher CPU. 1500ms gives one partial ~every 1.5s.
    ASR_CHUNK_MS: int = Field(1500, ge=500, le=5000, description="Audio chunk size (ms) for partial ASR runs")
    # Minimum interval (ms) between sending partial transcript events to the client.
    # Prevents flooding the WebSocket with too many partial updates.
    ASR_PARTIAL_INTERVAL_MS: int = Field(400, ge=100, le=2000, description="Min interval (ms) between partial transcript events")

    # CORS
    ALLOWED_ORIGINS: str = Field("http://localhost:3000", description="Comma-separated list of allowed CORS origins")

    @property
    def allowed_origins_list(self) -> List[str]:
        """Return parsed list of CORS origins."""
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


# Global settings singleton
settings = Settings()
