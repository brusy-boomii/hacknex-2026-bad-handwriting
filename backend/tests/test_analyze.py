import io
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from app.main import app
from app.schemas import AnalyzeResponse

client = TestClient(app)


def _create_image_bytes(
    fmt: str = "PNG",
    mode: str = "RGB",
    size: tuple[int, int] = (120, 80),
) -> bytes:
    buf = io.BytesIO()
    color = 240 if mode == "L" else (245, 245, 245)
    Image.new(mode, size, color=color).save(buf, format=fmt)
    return buf.getvalue()


def _create_text_image_bytes(text: str = "HACKNEX 2026", size: tuple[int, int] = (420, 120)) -> bytes:
    img = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    for dx in (0, 1):
        for dy in (0, 1):
            draw.text((28 + dx, 42 + dy), text, fill=(15, 15, 15))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
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
    assert parsed.status == "success"
    assert parsed.filename == "sample_note.png"
    assert parsed.image.format == "PNG"
    assert parsed.image.mode == "RGB"
    assert parsed.image.width == 120
    assert parsed.image.height == 80
    assert parsed.image.channels == 3
    assert parsed.metadata == parsed.image
    assert parsed.pipeline_status == "recognition_complete"
    assert parsed.recognition.engine == "rapidocr-onnxruntime (PP-OCRv3)"
    assert parsed.recognition.processing_time_ms >= 0.0
    assert parsed.uncertainty is not None
    assert parsed.uncertainty.overall_level == "UNREADABLE"
    assert parsed.uncertainty.review_recommended is True


def test_analyze_valid_text_image_performs_real_recognition():
    img_bytes = _create_text_image_bytes("HACKNEX 2026")
    response = client.post(
        "/analyze",
        files={"file": ("handwriting_line.png", io.BytesIO(img_bytes), "image/png")},
    )
    assert response.status_code == 200
    parsed = AnalyzeResponse(**response.json())
    assert parsed.status == "success"
    assert "HACKNEX" in parsed.recognition.text.upper()
    assert len(parsed.recognition.regions) >= 1
    first_region = parsed.recognition.regions[0]
    assert first_region.bbox is not None
    assert first_region.bbox.width > 0
    assert first_region.bbox.height > 0
    assert first_region.confidence is not None
    assert 0.0 <= first_region.confidence <= 1.0
    assert first_region.uncertainty_level in ("HIGH", "MEDIUM", "LOW", "UNREADABLE")
    assert first_region.quality_indicators is not None
    assert parsed.uncertainty is not None
    assert parsed.uncertainty.total_regions == len(parsed.recognition.regions)


def test_analyze_valid_grayscale_jpeg():
    img_bytes = _create_image_bytes(fmt="JPEG", mode="L", size=(64, 48))
    response = client.post(
        "/analyze",
        files={"file": ("scan.jpg", io.BytesIO(img_bytes), "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    parsed = AnalyzeResponse(**data)
    assert parsed.image.format == "JPEG"
    assert parsed.image.mode == "L"
    assert parsed.image.width == 64
    assert parsed.image.height == 48
    assert parsed.image.channels == 1
    assert parsed.uncertainty is not None


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
