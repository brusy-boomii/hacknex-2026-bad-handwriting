from fastapi.testclient import TestClient
from app.main import app
from app.schemas import HealthResponse

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    parsed = HealthResponse(**data)
    assert parsed.status == "healthy"
    assert parsed.application == "Extreme Bad-Handwriting Digitizing Stack"
    assert parsed.version == "0.1.0"
    assert parsed.phase == 1
    assert parsed.description == "Foundation phase established."
