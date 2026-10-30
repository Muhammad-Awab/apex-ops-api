import json
import logging

from app.logging_config import JsonFormatter


def test_request_id_is_generated_and_propagated(client):
    generated = client.get("/healthz").headers["X-Request-ID"]
    assert len(generated) == 32

    echoed = client.get("/healthz", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"]
    assert echoed == "abc-123"

    # Header injection attempts are replaced, not echoed.
    unsafe = client.get("/healthz", headers={"X-Request-ID": "bad value;<script>"}).headers["X-Request-ID"]
    assert unsafe != "bad value;<script>"


def test_metrics_expose_request_counters_with_route_templates(client):
    client.get("/api/v1/incidents/1")  # 404, but must be labelled by template not raw id
    body = client.get("/metrics").text
    assert "apex_http_requests_total" in body
    assert 'route="/api/v1/incidents/{incident_id}"' in body
    assert "apex_http_request_duration_seconds_bucket" in body
    assert 'apex_build_info{environment="test",git_sha="deadbeef",version="9.9.9-test"}' in body
    assert "apex_db_up 1.0" in body


def test_db_up_gauge_drops_when_database_unreachable(client_factory, tmp_path):
    client = client_factory(database_url=f"sqlite:///{tmp_path / 'no-such-dir' / 'x.db'}")
    assert "apex_db_up 0.0" in client.get("/metrics").text


def test_logs_are_single_line_json_with_context():
    formatter = JsonFormatter("apex-ops-api", "1.2.3", "test")
    record = logging.LogRecord("apex.api", logging.INFO, __file__, 1, "request", None, None)
    record.request_id = "rid-1"
    record.status = 200

    line = formatter.format(record)
    assert "\n" not in line
    payload = json.loads(line)
    assert payload["msg"] == "request"
    assert payload["request_id"] == "rid-1"
    assert payload["version"] == "1.2.3"
    assert payload["level"] == "INFO"
