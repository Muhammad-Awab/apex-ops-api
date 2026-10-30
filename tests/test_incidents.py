def test_create_get_and_list_incident(client):
    created = client.post("/api/v1/incidents", json={"title": "Disk 90% on node-3", "severity": "high"})
    assert created.status_code == 201
    incident = created.json()
    assert incident["status"] == "open"

    fetched = client.get(f"/api/v1/incidents/{incident['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Disk 90% on node-3"

    listed = client.get("/api/v1/incidents").json()
    assert [i["id"] for i in listed] == [incident["id"]]


def test_create_incident_rejects_invalid_severity(client):
    resp = client.post("/api/v1/incidents", json={"title": "Bad input", "severity": "urgent"})
    assert resp.status_code == 422


def test_get_missing_incident_returns_404(client):
    assert client.get("/api/v1/incidents/424242").status_code == 404


def test_errors_fault_returns_500_with_request_id(client_factory):
    client = client_factory(fault_mode="errors")
    resp = client.get("/api/v1/incidents", headers={"X-Request-ID": "trace-abc-123"})
    assert resp.status_code == 500
    assert resp.json()["request_id"] == "trace-abc-123"
    assert "injected fault" not in resp.text  # internals are not leaked to clients
