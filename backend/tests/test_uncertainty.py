import io
from PIL import Image, ImageDraw, ImageFilter
from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.schemas import (
    AnalyzeResponse,
    BoundingBox,
    RecognitionRegion,
    RecognitionResult,
)
from app.services.handwriting_ocr import OCRServiceOutput
from app.services.uncertainty import UncertaintyService, analyze_uncertainty

client = TestClient(app)


def _make_box(x_min: int = 20, y_min: int = 20, width: int = 240, height: int = 44) -> BoundingBox:
    x_max = x_min + width
    y_max = y_min + height
    return BoundingBox(
        x_min=x_min,
        y_min=y_min,
        x_max=x_max,
        y_max=y_max,
        width=width,
        height=height,
        polygon=[[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]],
    )


def _make_sharp_high_contrast_image(
    size: tuple[int, int] = (320, 100),
    bg_color: int = 250,
    fg_color: int = 15,
) -> Image.Image:
    """Create a crisp high-contrast synthetic handwriting region image."""
    img = Image.new("L", size, color=bg_color)
    draw = ImageDraw.Draw(img)
    for x in range(28, 240, 14):
        draw.line([(x, 26), (x + 8, 56)], fill=fg_color, width=2)
        draw.line([(x + 8, 56), (x + 12, 32)], fill=fg_color, width=2)
    draw.text((30, 30), "Amoxicillin 500mg", fill=fg_color)
    return img.convert("RGB")


def test_1_high_confidence_region():
    img = _make_sharp_high_contrast_image()
    region = RecognitionRegion(
        id=1,
        text="Amoxicillin 500mg",
        confidence=0.94,
        bbox=_make_box(),
    )
    summary = analyze_uncertainty(img, [region])

    assert summary.total_regions == 1
    analyzed = summary.regions[0]
    assert analyzed.uncertainty_level == "HIGH"
    assert analyzed.needs_review is False
    assert analyzed.reasons == []
    assert analyzed.ocr_confidence == 0.94
    assert analyzed.normalized_confidence is not None
    assert analyzed.normalized_confidence >= 0.78
    assert summary.overall_level == "HIGH"
    assert summary.review_recommended is False
    assert summary.counts.HIGH == 1


def test_2_medium_confidence_region():
    img = _make_sharp_high_contrast_image()
    region = RecognitionRegion(
        id=1,
        text="Paracetamol 650mg",
        confidence=0.72,
        bbox=_make_box(),
    )
    summary = analyze_uncertainty(img, [region])

    analyzed = summary.regions[0]
    assert analyzed.uncertainty_level == "MEDIUM"
    assert analyzed.needs_review is True
    assert "moderate_ocr_confidence" in analyzed.reasons
    assert summary.overall_level == "MEDIUM"
    assert summary.review_recommended is True
    assert summary.counts.MEDIUM == 1


def test_3_low_confidence_region():
    img = _make_sharp_high_contrast_image()
    region = RecognitionRegion(
        id=1,
        text="headache",
        confidence=0.49,
        bbox=_make_box(),
    )
    summary = analyze_uncertainty(img, [region])

    analyzed = summary.regions[0]
    assert analyzed.uncertainty_level == "LOW"
    assert analyzed.needs_review is True
    assert "low_ocr_confidence" in analyzed.reasons
    assert summary.overall_level == "LOW"
    assert summary.review_recommended is True
    assert "[headache? (LOW CONFIDENCE)]" in summary.annotated_text


def test_4_unreadable_or_empty_recognition():
    img = _make_sharp_high_contrast_image()
    empty_region = RecognitionRegion(
        id=1,
        text="   ",
        confidence=0.20,
        bbox=_make_box(),
    )
    very_low_region = RecognitionRegion(
        id=2,
        text="x",
        confidence=0.18,
        bbox=_make_box(y_min=50, height=36),
    )
    summary = analyze_uncertainty(img, [empty_region, very_low_region])

    assert summary.regions[0].uncertainty_level == "UNREADABLE"
    assert "empty_ocr_text" in summary.regions[0].reasons
    assert summary.regions[1].uncertainty_level == "UNREADABLE"
    assert "very_low_ocr_confidence" in summary.regions[1].reasons
    assert summary.overall_level == "UNREADABLE"
    assert summary.counts.UNREADABLE == 2


def test_5_low_contrast_image_region():
    # Faint strokes (intensity 218 on 232 background -> dynamic range ~14 < 45)
    faint_img = _make_sharp_high_contrast_image(bg_color=232, fg_color=218)
    region = RecognitionRegion(
        id=1,
        text="faint margin note",
        confidence=0.81,
        bbox=_make_box(),
    )
    summary = analyze_uncertainty(faint_img, [region])

    analyzed = summary.regions[0]
    assert "low_local_contrast" in analyzed.reasons
    assert analyzed.uncertainty_level in ("LOW", "UNREADABLE")
    assert analyzed.needs_review is True


def test_6_blurry_region():
    sharp_img = _make_sharp_high_contrast_image()
    blurry_img = sharp_img.filter(ImageFilter.GaussianBlur(radius=5.0))
    region = RecognitionRegion(
        id=1,
        text="blurred scrawl",
        confidence=0.79,
        bbox=_make_box(),
    )
    summary = analyze_uncertainty(blurry_img, [region])

    analyzed = summary.regions[0]
    assert "blurry_region" in analyzed.reasons
    assert analyzed.quality_indicators is not None
    assert analyzed.quality_indicators.laplacian_variance < 45.0
    assert analyzed.uncertainty_level in ("LOW", "UNREADABLE")
    assert analyzed.needs_review is True


def test_7_malformed_ocr_output():
    img = _make_sharp_high_contrast_image()
    garbled_region = RecognitionRegion(
        id=1,
        text="|||||| #### @@@@",
        confidence=0.76,
        bbox=_make_box(),
    )
    summary = analyze_uncertainty(img, [garbled_region])

    analyzed = summary.regions[0]
    assert (
        "excessive_non_alphanumeric_symbols" in analyzed.reasons
        or "suspicious_repeated_characters" in analyzed.reasons
        or "non_alphanumeric_only" in analyzed.reasons
    )
    assert analyzed.uncertainty_level in ("LOW", "UNREADABLE")
    assert analyzed.needs_review is True
    # Verify raw text is never silently replaced
    assert analyzed.text == "|||||| #### @@@@"


def test_8_missing_optional_ocr_confidence():
    img = _make_sharp_high_contrast_image()
    region = RecognitionRegion(
        id=1,
        text="uncalibrated engine text",
        confidence=None,
        ocr_confidence=None,
        bbox=_make_box(),
    )
    summary = analyze_uncertainty(img, [region])

    analyzed = summary.regions[0]
    assert "missing_ocr_confidence" in analyzed.reasons
    assert analyzed.ocr_confidence is None
    assert analyzed.normalized_confidence is None
    assert analyzed.uncertainty_level == "LOW"
    assert analyzed.needs_review is True


def test_9_multiple_ocr_regions_mixed_tiers():
    img = _make_sharp_high_contrast_image(size=(360, 260))
    # Draw crisp strokes in all three vertical bands so image quality is high across bands
    draw = ImageDraw.Draw(img)
    for y_base in (20, 90, 160):
        for x in range(28, 250, 14):
            draw.line([(x, y_base + 6), (x + 8, y_base + 34)], fill=(15, 15, 15), width=2)
            draw.line([(x + 8, y_base + 34), (x + 12, y_base + 10)], fill=(15, 15, 15), width=2)

    regions = [
        RecognitionRegion(
            id=1,
            text="Patient Name: John Doe",
            confidence=0.93,
            bbox=_make_box(y_min=20, height=44),
        ),
        RecognitionRegion(
            id=2,
            text="The patient has severe",
            confidence=0.74,
            bbox=_make_box(y_min=90, height=44),
        ),
        RecognitionRegion(
            id=3,
            text="headache",
            confidence=0.51,
            bbox=_make_box(y_min=160, height=44),
        ),
    ]
    service = UncertaintyService()
    summary = service.analyze_uncertainty(img, regions)

    assert summary.total_regions == 3
    assert summary.counts.HIGH == 1
    assert summary.counts.MEDIUM == 1
    assert summary.counts.LOW == 1
    assert summary.counts.UNREADABLE == 0
    assert summary.flagged_region_count == 2
    assert summary.overall_level == "LOW"
    assert summary.review_recommended is True
    # Ensure original text is preserved while annotated_text highlights uncertain regions
    assert summary.regions[2].text == "headache"
    assert "[headache? (LOW CONFIDENCE)]" in summary.annotated_text


def test_10_backward_compatibility_and_legacy_low_confidence_warning(monkeypatch):
    img = _make_sharp_high_contrast_image()
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    low_conf_region = RecognitionRegion(
        id=1,
        text="illegible scrawl",
        confidence=0.52,
        bbox=_make_box(),
        region_type="line",
    )
    mock_ocr_output = OCRServiceOutput(
        result=RecognitionResult(
            text="illegible scrawl",
            engine="rapidocr-onnxruntime (PP-OCRv3)",
            processing_time_ms=42.5,
            confidence=0.52,
            regions=[low_conf_region],
        ),
        warnings=[
            "Low overall recognition confidence (0.52); image may contain difficult or degraded handwriting."
        ],
    )
    monkeypatch.setattr(routes.ocr_service, "recognize_with_warnings", lambda **_kw: mock_ocr_output)

    response = client.post(
        "/analyze",
        files={"file": ("scrawl.png", io.BytesIO(buf.getvalue()), "image/png")},
    )
    assert response.status_code == 200
    payload = response.json()
    parsed = AnalyzeResponse(**payload)

    # Phase 1 & Phase 2 fields preserved
    assert parsed.status == "success"
    assert parsed.filename == "scrawl.png"
    assert parsed.metadata == parsed.image
    assert parsed.recognition.text == "illegible scrawl"
    assert parsed.recognition.confidence == 0.52
    assert any("low overall recognition confidence" in w.lower() for w in parsed.warnings)

    # Phase 3 uncertainty fields populated
    assert parsed.uncertainty is not None
    assert parsed.uncertainty.overall_level == "LOW"
    assert parsed.uncertainty.review_recommended is True
    assert parsed.recognition.regions[0].uncertainty_level == "LOW"
    assert parsed.recognition.regions[0].needs_review is True
    assert "low_ocr_confidence" in parsed.recognition.regions[0].reasons
