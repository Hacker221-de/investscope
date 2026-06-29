from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint_returns_utc_timestamp() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    assert timestamp.utcoffset().total_seconds() == 0


def test_unknown_asset_returns_404() -> None:
    response = client.get("/api/v1/assets/UNKNOWN")

    assert response.status_code == 404
    assert response.json() == {"detail": "Asset not found"}
