"""Metricas HTTP e integracao opcional com Sentry."""
import time

from flask import g, request
from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "zokyo_http_requests_total",
    "Total de requisicoes HTTP.",
    ("method", "route", "status"),
)
HTTP_LATENCY = Histogram(
    "zokyo_http_request_duration_seconds",
    "Latencia das requisicoes HTTP.",
    ("method", "route"),
)


def start_request_metrics():
    g.request_started_at = time.perf_counter()


def observe_response(response):
    route = request.url_rule.rule if request.url_rule else "unmatched"
    method = request.method
    HTTP_REQUESTS.labels(method, route, str(response.status_code)).inc()
    started = getattr(g, "request_started_at", None)
    if started is not None:
        HTTP_LATENCY.labels(method, route).observe(time.perf_counter() - started)
    return response


def init_sentry(app):
    dsn = app.config.get("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=app.config.get("SENTRY_TRACES_SAMPLE_RATE", 0),
            send_default_pii=False,
            environment=app.config.get("ENV", "production"),
        )
        return True
    except ImportError:
        app.logger.warning("SENTRY_DSN configurado, mas sentry-sdk não está instalado.")
        return False
