"""Prometheus metrics (RED method: Rate, Errors, Duration + dependency health)."""

from prometheus_client import Counter, Gauge, Histogram, Info

HTTP_REQUESTS = Counter(
    "apex_http_requests_total",
    "HTTP requests processed",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "apex_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
DB_UP = Gauge("apex_db_up", "1 if the last readiness check reached the database, else 0")
INCIDENTS_CREATED = Counter("apex_incidents_created_total", "Incidents created via the API")
BUILD_INFO = Info("apex_build", "Build/version information of the running service")
