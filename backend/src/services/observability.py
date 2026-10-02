"""Application telemetry with OpenTelemetry and safe, low-cardinality metrics."""
from __future__ import annotations

from threading import Lock
from typing import Any

from opentelemetry import metrics, trace

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger

_meter = metrics.get_meter("insurance-claim-intake")
_claim_turns = _meter.create_counter("claim_intake.turns.total", description="Claimant conversation turns processed.")
_claim_submissions = _meter.create_counter("claim_intake.submissions.total", description="Claim submissions attempted.")
_voice_turns = _meter.create_counter("claim_intake.voice.turns.total", description="Voice turns processed.")
_rag_answers = _meter.create_counter("claim_intake.rag.answers.total", description="Claimant RAG answers returned.")
_evidence_verifications = _meter.create_counter("claim_intake.evidence.verifications.total", description="Evidence verification outcomes.")
_outbox_events = _meter.create_counter("claim_intake.outbox.events.total", description="Outbox dispatcher outcomes.")
_ai_fallbacks = _meter.create_counter("claim_intake.ai.fallbacks.total", description="Governed AI fallback invocations.")
_ai_rejections = _meter.create_counter("claim_intake.ai.rejections.total", description="Tenant AI quota/concurrency rejections.")
_db_errors = _meter.create_counter("claim_intake.database.errors.total", description="Database operation failures.")
_voice_latency = _meter.create_histogram("claim_intake.voice.turn.latency_ms", unit="ms", description="End-to-end voice turn latency in milliseconds.")

_config_lock = Lock()
_configured = False


def configure_otel() -> None:
    """Configure OTLP traces and metrics once when explicitly enabled."""
    global _configured
    if _configured or not settings.OTEL_ENABLED:
        return
    with _config_lock:
        if _configured or not settings.OTEL_ENABLED:
            return
        endpoint = (settings.OTEL_EXPORTER_OTLP_ENDPOINT or "").strip()
        if not endpoint:
            raise RuntimeError("OTEL_EXPORTER_OTLP_ENDPOINT is required when OTEL_ENABLED=true.")

        headers: dict[str, str] = {}
        raw_headers = (settings.OTEL_EXPORTER_OTLP_HEADERS or "").strip()
        if raw_headers:
            for item in raw_headers.split(","):
                if "=" in item:
                    key, value = item.split("=", 1)
                    if key.strip():
                        headers[key.strip()] = value.strip()

        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
            trace_provider = TracerProvider(resource=resource)
            trace_provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(endpoint=endpoint, headers=headers),
                )
            )
            trace.set_tracer_provider(trace_provider)

            metric_reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=endpoint, headers=headers),
                export_interval_millis=15000,
            )
            metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))
            _configured = True
        except Exception as exc:
            logger.exception("OpenTelemetry configuration failed: %s", type(exc).__name__)
            if settings.ENVIRONMENT in {"production", "staging"}:
                raise RuntimeError("OpenTelemetry could not be configured.") from exc


def _attrs(**kwargs: Any) -> dict[str, str]:
    # Never place raw tenant IDs, claim IDs, transcripts, filenames, or other PII in metric labels.
    return {str(k): str(v) for k, v in kwargs.items() if v not in (None, "")}


def record_claim_turn(*, input_mode: str, outcome: str) -> None:
    _claim_turns.add(1, _attrs(input_mode=input_mode, outcome=outcome))


def record_claim_submission(*, outcome: str) -> None:
    _claim_submissions.add(1, _attrs(outcome=outcome))


def record_voice_turn(*, outcome: str, latency_ms: float | None = None) -> None:
    attrs = _attrs(outcome=outcome)
    _voice_turns.add(1, attrs)
    if latency_ms is not None:
        _voice_latency.record(float(latency_ms), attrs)


def record_rag_answer(*, status: str, grounded: bool) -> None:
    _rag_answers.add(1, _attrs(status=status, grounded=str(bool(grounded)).lower()))


def record_evidence_verification(*, status: str) -> None:
    _evidence_verifications.add(1, _attrs(status=status))


def record_outbox(*, outcome: str) -> None:
    _outbox_events.add(1, _attrs(outcome=outcome))


def record_ai_fallback(*, operation: str) -> None:
    _ai_fallbacks.add(1, _attrs(operation=operation))


def record_ai_rejection(*, operation: str, reason: str) -> None:
    _ai_rejections.add(1, _attrs(operation=operation, reason=reason))


def record_database_error(*, operation: str) -> None:
    _db_errors.add(1, _attrs(operation=operation))


def tracer():
    return trace.get_tracer("insurance-claim-intake")
