import io
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.schemas import AnalyzeResponse

client = TestClient(app)


def _create_image_bytes(fmt: str = "PNG", mode: str = "RGB", size: tuple[int, int] = (120, 80)) -> bytes:
    buf = io.BytesIO()
    color = 128 if mode == "L" else (200, 100, 50)
    Image.new(mode, size, color=color).save(buf, format=fmt)
    return buf.getvalue()


def test_analyze_valid_png_image():
    img_bytes = _create_image_bytes(fmt="PNG", mode="RGB", size=(120, 80))
    response = client.post(
        "/analyze",
        files={"file": ("sample_note.png", io.BytesIO(img_bytes), "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    parsed = AnalyzeResponse(**data)
    assert parsed.status == "received"
    assert parsed.filename == "sample_note.png"
    assert parsed.metadata.format == "PNG"
    assert parsed.metadata.mode == "RGB"
    assert parsed.metadata.width == 120
    assert parsed.metadata.height == 80
    assert parsed.metadata.channels == 3
    assert parsed.pipeline_status == "foundation_active"


def test_analyze_valid_grayscale_jpeg():
    img_bytes = _create_image_bytes(fmt="JPEG", mode="L", size=(64, 48))
    response = client.post(
        "/analyze",
        files={"file": ("scan.jpg", io.BytesIO(img_bytes), "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    parsed = AnalyzeResponse(**data)
    assert parsed.metadata.format == "JPEG"
    assert parsed.metadata.mode == "L"
    assert parsed.metadata.width == 64
    assert parsed.metadata.height == 48
    assert parsed.metadata.channels == 1


def test_analyze_missing_file():
    response = client.post("/analyze")
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert isinstance(data["detail"], str)


def test_analyze_missing_filename():
    img_bytes = _create_image_bytes()
    response = client.post(
        "/analyze",
        files={"file": ("   ", io.BytesIO(img_bytes), "image/png")},
    )
    assert response.status_code == 400
    assert "missing a filename" in response.json()["detail"].lower()


def test_analyze_empty_file():
    response = client.post(
        "/analyze",
        files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_analyze_invalid_mime_type():
    response = client.post(
        "/analyze",
        files={"file": ("test.png", io.BytesIO(b"not an image"), "text/plain")},
    )
    assert response.status_code == 400
    assert "mime type" in response.json()["detail"].lower()


def test_analyze_unsupported_extension():
    response = client.post(
        "/analyze",
        files={"file": ("document.pdf", io.BytesIO(b"%PDF-1.4"), "image/pdf")},
    )
    assert response.status_code == 400
    assert "extension '.pdf' is not supported" in response.json()["detail"].lower()


def test_analyze_corrupt_image_bytes():
    corrupt_bytes = b"\x89PNG\r\n\x1a\ncorrupt_payload_not_a_real_image"
    response = client.post(
        "/analyze",
        files={"file": ("corrupt.png", io.BytesIO(corrupt_bytes), "image/png")},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "corrupt or unreadable" in detail.lower()
    assert "Traceback" not in detail


def test_analyze_oversized_upload_via_env_config(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_SIZE_BYTES", "100")
    img_bytes = _create_image_bytes(fmt="PNG", mode="RGB", size=(100, 100))
    assert len(img_bytes) > 100

    response = client.post(
        "/analyze",
        files={"file": ("large.png", io.BytesIO(img_bytes), "image/png")},
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed limit" in response.json()["detail"].lower()


def test_analyze_oversized_upload_default_limit():
    oversized_bytes = b"\x00" * (10 * 1024 * 1024 + 1)
    response = client.post(
        "/analyze",
        files={"file": ("huge.png", io.BytesIO(oversized_bytes), "image/png")},
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed limit" in response.json()["detail"].lower()
