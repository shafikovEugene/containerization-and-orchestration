import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request, g, has_request_context
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

app = Flask(__name__)

# ---------- OpenTelemetry ----------

resource = Resource.create({"service.name": "api"})
provider = TracerProvider(resource=resource)

otlp_endpoint = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://otel-collector:4318",
).rstrip("/")

if not otlp_endpoint.endswith("/v1/traces"):
    otlp_endpoint += "/v1/traces"

provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
)
trace.set_tracer_provider(provider)

# ---------- JSON logging ----------

class JsonFormatter(logging.Formatter):
    def format(self, record):
        span_context = trace.get_current_span().get_span_context()

        if span_context.is_valid:
            trace_id = f"{span_context.trace_id:032x}"
            span_id = f"{span_context.span_id:016x}"
        elif has_request_context():
            trace_id = getattr(g, "trace_id", None)
            span_id = None
        else:
            trace_id = None
            span_id = None

        log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id,
        }

        if span_id:
            log["span_id"] = span_id

        if has_request_context():
            log["http_method"] = request.method
            log["http_path"] = request.path

        # Добавляем поля, переданные через logging extra={...}.
        standard_fields = set(logging.makeLogRecord({}).__dict__)
        for key, value in record.__dict__.items():
            if key not in standard_fields and key not in {
                "message", "asctime"
            }:
                log[key] = value

        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)

        return json.dumps(log, ensure_ascii=False, default=str)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())

app.logger.handlers.clear()
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)
app.logger.propagate = False

# ---------- Prometheus RED metrics ----------

REQUESTS = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)

ERRORS = Counter(
    "http_errors_total",
    "Total number of HTTP errors",
    ["endpoint"],
)

RESPONSE_TIME = Histogram(
    "http_response_time_seconds",
    "HTTP response time in seconds",
    ["endpoint"],
)


@app.before_request
def start_timer():
    g.start_time = time.time()

    span_context = trace.get_current_span().get_span_context()
    g.trace_id = (
        f"{span_context.trace_id:032x}"
        if span_context.is_valid
        else uuid.uuid4().hex
    )

    app.logger.info("request_started")


@app.after_request
def record_metrics(response):
    endpoint = request.url_rule.rule if request.url_rule else "unknown"
    duration = time.time() - getattr(g, "start_time", time.time())

    REQUESTS.labels(
        method=request.method,
        endpoint=endpoint,
        status=response.status_code,
    ).inc()

    RESPONSE_TIME.labels(endpoint=endpoint).observe(duration)

    log_fields = {
        "status_code": response.status_code,
        "duration_seconds": round(duration, 4),
    }

    if response.status_code >= 500:
        ERRORS.labels(endpoint=endpoint).inc()
        app.logger.error("request_failed", extra=log_fields)
    else:
        app.logger.info("request_completed", extra=log_fields)

    return response


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.exception("unhandled_exception")
    return jsonify(error="Internal Server Error"), 500


@app.route("/health")
def health():
    return "ok", 200


@app.route("/fail")
def fail():
    app.logger.error(
        "simulated_failure",
        extra={"reason": "endpoint /fail intentionally returns 500"},
    )
    return jsonify(error="Internal Server Error"), 500


@app.route("/slow")
def slow():
    delay = random.uniform(1, 3)

    app.logger.info(
        "slow_request_started",
        extra={"delay_seconds": round(delay, 2)},
    )

    time.sleep(delay)

    return jsonify(
        status="ok",
        delay_seconds=round(delay, 2),
    )


@app.route("/load")
def load():
    url = "http://127.0.0.1:5000/health"
    count = 30

    app.logger.info(
        "load_test_started",
        extra={"generated_requests": count},
    )

    for _ in range(count):
        requests.get(url, timeout=5)

    return jsonify(
        status="ok",
        generated_requests=count,
    )


@app.route("/metrics")
def metrics():
    return (
        generate_latest(),
        200,
        {"Content-Type": CONTENT_TYPE_LATEST},
    )


# Automatically create spans for incoming Flask requests and outgoing requests.
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)