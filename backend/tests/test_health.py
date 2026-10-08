from fastapi.testclient import TestClient
from app.main import app
from app.schemas import HealthResponse
from app.utils.config import get_allowed_origins

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    parsed = HealthResponse(**data)
    assert parsed.status == "healthy"
    assert parsed.application == "Extreme Bad-Handwriting Digitizing Stack"
    assert parsed.version == "0.4.0"
    assert parsed.phase == 4
    assert "Phase 4" in parsed.description


def test_api_prefixed_health_and_docs():
    api_health = client.get("/api/health")
    assert api_health.status_code == 200
    assert api_health.json()["status"] == "healthy"

    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200


def test_cors_allowed_origins_normalization(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173/, *")
    monkeypatch.setenv("FRONTEND_URL", "https://example-frontend.vercel.app/")
    origins = get_allowed_origins()
    assert "http://localhost:5173" in origins
    assert "https://example-frontend.vercel.app" in origins
    assert "*" not in origins


