from app.main import app
from conftest import SyncASGIClient


def test_health_has_request_id_and_metrics_are_not_public() -> None:
    client = SyncASGIClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.headers.get("x-request-id")
    assert client.get("/metrics").status_code == 404

