"""Optional production OpenTelemetry bootstrap with safe PII boundaries."""
from __future__ import annotations

import logging
from typing import Any

from src.config import settings

log = logging.getLogger(__name__)
_configured = False


def configure_telemetry(app: Any) -> None:
    """Configure HTTP/DB/Redis tracing once when explicitly enabled.

    Telemetry is opt-in so local development remains dependency-light; production
    deployments can fail closed on missing exporters through deployment config.
    No request bodies, authorization headers, prompts, transcripts, or claim data
    are added to spans here.
    """
    global _configured
    if _configured or not settings.OTEL_ENABLED:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        kwargs = {}
        if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
            kwargs["endpoint"] = settings.OTEL_EXPORTER_OTLP_ENDPOINT
        if settings.OTEL_EXPORTER_OTLP_HEADERS:
            kwargs["headers"] = settings.OTEL_EXPORTER_OTLP_HEADERS
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(**kwargs)))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        _configured = True
        log.info("OpenTelemetry configured for %s", settings.OTEL_SERVICE_NAME)
    except Exception as exc:
        if settings.ENVIRONMENT in ("production", "staging"):
            raise RuntimeError("OpenTelemetry is enabled but could not be initialized") from exc
        log.warning("OpenTelemetry disabled after initialization failure: %s", type(exc).__name__)
