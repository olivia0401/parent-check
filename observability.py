"""
Observability: structured logging + OpenTelemetry tracing + Prometheus metrics.

The three pillars, wired so the app degrades gracefully when the optional
dependencies aren't installed (local dev / minimal CI) or no collector is
configured:

- **Logs**: always-on JSON lines carrying request_id and, when tracing is
  active, the trace_id - so a log line can be joined back to its trace.
- **Traces**: OpenTelemetry auto-instruments Flask, outbound `requests`, and
  SQLAlchemy, producing one trace per HTTP request that spans the route, its DB
  queries, and any external article fetch. Spans export to an OTLP collector if
  OTEL_EXPORTER_OTLP_ENDPOINT is set; otherwise they stay in-process.
- **Metrics**: a Prometheus /metrics endpoint with request count and a latency
  histogram (P50/P95 are computed by Prometheus/Grafana from the buckets).

setup(app, engine) is a no-op for whichever pillar's libraries are missing.
"""
import json
import logging
import time
import uuid

from flask import g, request

# --- optional deps: import-guarded so the app runs without them --------------
try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    _OTEL = True
except ImportError:
    _OTEL = False

try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    _PROM = True
except ImportError:
    _PROM = False

SERVICE_NAME = "parent-check"


# --- structured logging ------------------------------------------------------
class _JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # attach correlation ids when present
        for attr in ("request_id", "trace_id", "latency_ms", "status", "path", "method"):
            val = getattr(record, attr, None)
            if val is not None:
                payload[attr] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _current_trace_id():
    if not _OTEL:
        return None
    ctx = _otel_trace.get_current_span().get_span_context()
    if ctx and ctx.trace_id:
        return f"{ctx.trace_id:032x}"
    return None


# --- Prometheus metrics ------------------------------------------------------
if _PROM:
    _REQ_COUNT = Counter(
        "http_requests_total", "HTTP requests", ["method", "path", "status"]
    )
    _REQ_LATENCY = Histogram(
        "http_request_duration_seconds", "HTTP request latency", ["method", "path"]
    )


def setup(app, engine=None):
    """Instrument the Flask app. Safe to call regardless of which optional
    observability libraries are installed."""

    # 1. JSON logging on the root + Flask logger
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    app.logger.handlers = [handler]
    app.logger.setLevel(logging.INFO)
    # Don't let app.logger records also bubble to root, or every line logs twice.
    app.logger.propagate = False

    # 2. OpenTelemetry tracing (exports only if a collector endpoint is set)
    if _OTEL:
        provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
        import os
        if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        _otel_trace.set_tracer_provider(provider)
        FlaskInstrumentor().instrument_app(app)
        RequestsInstrumentor().instrument()
        if engine is not None:
            SQLAlchemyInstrumentor().instrument(engine=engine)

    # 3. per-request correlation + latency
    @app.before_request
    def _start_timer():
        g._t0 = time.perf_counter()
        g._rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]

    @app.after_request
    def _log_and_measure(response):
        latency_ms = round((time.perf_counter() - getattr(g, "_t0", time.perf_counter())) * 1000, 1)
        # Prometheus (use url_rule so paths don't explode metric cardinality)
        path = request.url_rule.rule if request.url_rule else request.path
        if _PROM:
            _REQ_COUNT.labels(request.method, path, response.status_code).inc()
            _REQ_LATENCY.labels(request.method, path).observe(latency_ms / 1000)
        # structured access log with correlation ids
        app.logger.info(
            "request",
            extra={
                "request_id": getattr(g, "_rid", None),
                "trace_id": _current_trace_id(),
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "latency_ms": latency_ms,
            },
        )
        response.headers["X-Request-ID"] = getattr(g, "_rid", "")
        return response

    # 4. metrics endpoint
    if _PROM:
        @app.route("/metrics")
        def metrics():
            return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    app.logger.info(
        "observability configured",
        extra={"path": "startup", "method": "-", "status": 0,
               "request_id": f"otel={_OTEL},prom={_PROM}"},
    )
