def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "keys_present" in body
    assert "scout_backend" in body


def test_request_id_header_roundtrip(client):
    r = client.get("/api/v1/health", headers={"x-request-id": "test-123"})
    assert r.status_code == 200
    assert r.headers.get("x-request-id") == "test-123"


def test_404_on_unknown_route(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404


def test_openapi_schema_loads(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert "/api/v1/health" in spec["paths"]
    assert "/api/v1/scout" in spec["paths"]
    assert "/api/v1/posts" in spec["paths"]
