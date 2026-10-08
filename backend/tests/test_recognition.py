import io
from pathlib import Path
import sys
from PIL import Image, ImageDraw
import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.services.handwriting_ocr import (
    HandwritingOCRService,
    OCRExecutionError,
    OCRModelUnavailableError,
)
from app.services.preprocessing import PreprocessingService

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate_recognition import (  # noqa: E402
    calculate_cer,
    calculate_wer,
    discover_evaluation_samples,
    run_evaluation,
)

client = TestClient(app)


def _make_handwriting_like_image(
    lines: list[str],
    size: tuple[int, int] = (520, 180),
) -> bytes:
    """Create an in-memory multi-line image with irregular stroke offsets."""
    img = Image.new("RGB", size, color=(250, 248, 242))
    draw = ImageDraw.Draw(img)
    y_cursor = 28
    for idx, line in enumerate(lines):
        x_offset = 24 + (idx * 7)
        for dx, dy in ((0, 0), (1, 0), (0, 1)):
            draw.text((x_offset + dx, y_cursor + dy), line, fill=(25, 25, 30))
        y_cursor += 48
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_preprocessing_preserves_original_and_recognition_image():
    service = PreprocessingService()
    raw_bytes = _make_handwriting_like_image(["Rx Amoxicillin 500mg", "Take 1 tab TID"])
    bundle = service.prepare_for_pipeline(raw_bytes)

    assert bundle.original_image is not None
    assert bundle.recognition_image is not None
    assert bundle.original_image.size == (520, 180)
    assert bundle.metadata.width == 520
    assert bundle.metadata.height == 180
    assert "grayscale_conversion" in bundle.preprocessing.operations


def test_preprocessing_downscales_very_large_image():
    service = PreprocessingService()
    img = Image.new("RGB", (3000, 1500), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    bundle = service.prepare_for_pipeline(buf.getvalue())
    assert bundle.original_image.size == (3000, 1500)
    assert bundle.recognition_image.width == 2400
    assert bundle.recognition_image.height == 1200
    assert bundle.preprocessing.scale_factor == pytest.approx(0.8, rel=1e-3)
    assert any("downscaled" in w.lower() for w in bundle.warnings)


def test_recognition_service_initializes_and_recognizes_multiline():
    prep = PreprocessingService()
    ocr = HandwritingOCRService()

    raw_bytes = _make_handwriting_like_image(["PATIENT NOTE 104", "DOSE 25 MG"])
    bundle = prep.prepare_for_pipeline(raw_bytes)
    output = ocr.recognize_with_warnings(
        bundle.recognition_image,
        original_size=(bundle.metadata.width, bundle.metadata.height),
    )

    assert output.result.engine == HandwritingOCRService.ENGINE_NAME
    assert output.result.processing_time_ms > 0.0
    assert len(output.result.regions) >= 1
    recognized_upper = output.result.text.upper()
    assert "PATIENT" in recognized_upper or "104" in recognized_upper or "DOSE" in recognized_upper


def test_recognition_service_handles_engine_init_failure():
    def broken_factory():
        raise RuntimeError("Simulated missing ONNX model file")

    ocr = HandwritingOCRService(engine_factory=broken_factory)
    img = Image.new("RGB", (200, 80), color=(255, 255, 255))
    with pytest.raises(OCRModelUnavailableError):
        ocr.recognize(img)


def test_recognition_service_handles_runtime_inference_failure():
    def failing_engine(_img_array, **_kwargs):
        raise RuntimeError("Simulated ONNX runtime execution error")

    ocr = HandwritingOCRService(engine_factory=lambda: failing_engine)
    img = Image.new("RGB", (200, 80), color=(255, 255, 255))
    with pytest.raises(OCRExecutionError):
        ocr.recognize(img)


def test_analyze_route_handles_recognition_execution_error_cleanly(monkeypatch):
    def mock_fail(*_args, **_kwargs):
        raise OCRExecutionError("Engine crashed")

    monkeypatch.setattr(routes.ocr_service, "recognize_with_warnings", mock_fail)
    raw_bytes = _make_handwriting_like_image(["Test line"])
    response = client.post(
        "/analyze",
        files={"file": ("note.png", io.BytesIO(raw_bytes), "image/png")},
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "recognition engine failed" in detail.lower()
    assert "Traceback" not in detail


def test_analyze_route_handles_model_unavailable_cleanly(monkeypatch):
    def mock_unavailable(*_args, **_kwargs):
        raise OCRModelUnavailableError("Model missing")

    monkeypatch.setattr(routes.ocr_service, "recognize_with_warnings", mock_unavailable)
    raw_bytes = _make_handwriting_like_image(["Test line"])
    response = client.post(
        "/analyze",
        files={"file": ("note.png", io.BytesIO(raw_bytes), "image/png")},
    )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "unavailable" in detail.lower()
    assert "Traceback" not in detail


def test_evaluation_cer_and_wer_calculations():
    assert calculate_cer("take 1 tablet daily", "take 1 tablet daily") == 0.0
    assert calculate_wer("take 1 tablet daily", "take 1 tablet daily") == 0.0

    # 1 word substitution out of 4 words -> WER = 0.25
    assert calculate_wer("take 1 tablet daily", "take 2 tablet daily") == 0.25
    assert 0.0 < calculate_cer("take 1 tablet daily", "take 2 tablet daily") < 0.2


def test_evaluation_empty_directory_reports_no_samples(tmp_path: Path):
    pairs = discover_evaluation_samples(tmp_path)
    assert pairs == []
    exit_code, results = run_evaluation(tmp_path)
    assert exit_code == 0
    assert results == []
