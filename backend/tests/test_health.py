from app.main import app
from conftest import SyncASGIClient


def test_health() -> None:
    response = SyncASGIClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
