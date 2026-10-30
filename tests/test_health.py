def test_liveness_returns_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_ok_when_database_reachable(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["checks"]["database"] == "ok"


def test_readiness_fails_but_liveness_passes_when_database_unreachable(client_factory, tmp_path):
    # Directory does not exist -> SQLite cannot open the file -> OperationalError.
    client = client_factory(database_url=f"sqlite:///{tmp_path / 'no-such-dir' / 'x.db'}")

    ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json() == {"status": "not_ready", "checks": {"database": "unreachable"}}
    # Liveness must stay green: restarting the app would not fix a DB outage.
    assert client.get("/healthz").status_code == 200


def test_readiness_fails_under_not_ready_fault(client_factory):
    resp = client_factory(fault_mode="not_ready").get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


def test_version_reports_build_metadata(client):
    body = client.get("/version").json()
    assert body["version"] == "9.9.9-test"
    assert body["git_sha"] == "deadbeef"
