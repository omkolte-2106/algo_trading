import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_app_endpoints():
    client = TestClient(app)
    
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json() == {"status": "ok"}

    resp_status = client.get("/status")
    assert resp_status.status_code == 200
    assert "equity" in resp_status.json()

    resp_kill = client.post("/api/kill")
    assert resp_kill.status_code == 200
    assert resp_kill.json()["status"] == "killed"
