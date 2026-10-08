import io
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    AnalyzeResponse,
    RecognitionRegion,
    RegionReviewInput,
    ReviewExportRequest,
)
from app.services.verification import (
    SecondaryVerificationService,
    accept_candidate_region,
    accept_ocr_region,
    build_export_json,
    build_export_txt,
    correct_region_text,
    reject_candidate_region,
)

client = TestClient(app)


def test_1_reliable_ocr_region_skips_secondary_verification():
    """
    1. Reliable OCR region (HIGH, needs_review=False) must NOT trigger secondary verification.
    """
    called = False

    def spy_verifier(_region: RecognitionRegion):
        nonlocal called
        called = True
        return ("should not run", 0.99)

    service = SecondaryVerificationService(verifier_fn=spy_verifier)
    high_region = RecognitionRegion(
        id=1,
        text="Patient vitals stable",
        confidence=0.95,
        ocr_confidence=0.95,
        normalized_confidence=0.92,
        uncertainty_level="HIGH",
        needs_review=False,
        reasons=[],
    )

    verified = service.verify_region(high_region)
    assert called is False
    assert verified.text == "Patient vitals stable"
    assert verified.raw_ocr == "Patient vitals stable"
    assert verified.secondary_verification is not None
    assert verified.secondary_verification.attempted is False
    assert verified.secondary_verification.status == "skipped_reliable_region"
    assert verified.secondary_verification.candidate_text is None
    assert verified.secondary_verification.requires_human_review is False


def test_2_low_uncertainty_region_triggers_secondary_verification():
    """
    2. LOW uncertainty region triggers selective secondary verification and returns
       candidate separately without overwriting original OCR text.
    """
    service = SecondaryVerificationService(
        verifier_fn=lambda r: ("severe headache", 0.81)
    )
    low_region = RecognitionRegion(
        id=1,
        text="severe headahe",
        confidence=0.49,
        ocr_confidence=0.49,
        normalized_confidence=0.51,
        uncertainty_level="LOW",
        needs_review=True,
        reasons=["low_ocr_confidence"],
    )

    verified = service.verify_region(low_region)
    # Original OCR must NEVER be silently overwritten
    assert verified.text == "severe headahe"
    assert verified.raw_ocr == "severe headahe"
    assert verified.final_text == "severe headahe"
    assert verified.review_status == "PENDING"
    assert verified.human_verified is False

    sv = verified.secondary_verification
    assert sv is not None
    assert sv.attempted is True
    assert sv.original_text == "severe headahe"
    assert sv.candidate_text == "severe headache"
    assert sv.confidence == 0.81
    assert sv.source == "secondary_verification"
    assert sv.requires_human_review is True
    assert sv.status == "candidate_available"


def test_3_unreadable_region_triggers_secondary_verification():
    """
    3. UNREADABLE region triggers secondary verification; when no trustworthy
       interpretation can be produced, candidate_text is None and original OCR is preserved.
    """
    service = SecondaryVerificationService(verifier_fn=lambda _r: (None, None))
    unreadable_region = RecognitionRegion(
        id=2,
        text="///",
        confidence=0.18,
        ocr_confidence=0.18,
        normalized_confidence=0.22,
        uncertainty_level="UNREADABLE",
        needs_review=True,
        reasons=["very_low_ocr_confidence", "non_alphanumeric_only"],
    )

    verified = service.verify_region(unreadable_region)
    assert verified.text == "///"
    assert verified.raw_ocr == "///"
    sv = verified.secondary_verification
    assert sv is not None
    assert sv.attempted is True
    assert sv.original_text == "///"
    assert sv.candidate_text is None
    assert sv.confidence is None
    assert sv.requires_human_review is True
    assert sv.status == "no_trustworthy_candidate"


def test_4_human_acceptance():
    """
    4. Human can accept raw OCR or accept a secondary candidate while preserving raw_ocr.
    """
    service = SecondaryVerificationService(
        verifier_fn=lambda _r: ("amoxicillin 500mg", 0.84)
    )
    region = service.verify_region(
        RecognitionRegion(
            id=1,
            text="amoxicllin 500mg",
            confidence=0.52,
            uncertainty_level="LOW",
            needs_review=True,
            reasons=["low_ocr_confidence"],
        )
    )

    # Case A: Accept raw OCR directly
    accepted_raw = accept_ocr_region(region)
    assert accepted_raw.review_status == "ACCEPTED"
    assert accepted_raw.human_verified is True
    assert accepted_raw.text == "amoxicllin 500mg"
    assert accepted_raw.raw_ocr == "amoxicllin 500mg"
    assert accepted_raw.final_text == "amoxicllin 500mg"

    # Case B: Accept secondary candidate
    accepted_cand = accept_candidate_region(region)
    assert accepted_cand.review_status == "ACCEPTED"
    assert accepted_cand.human_verified is True
    assert accepted_cand.text == "amoxicllin 500mg"
    assert accepted_cand.raw_ocr == "amoxicllin 500mg"
    assert accepted_cand.final_text == "amoxicillin 500mg"


def test_5_human_correction():
    """
    5. Human can manually correct text; status becomes CORRECTED and raw OCR remains intact.
    """
    region = RecognitionRegion(
        id=1,
        text="Patient has severe headahe",
        raw_ocr="Patient has severe headahe",
        confidence=0.48,
        uncertainty_level="LOW",
        needs_review=True,
        reasons=["low_ocr_confidence"],
    )

    corrected = correct_region_text(region, "Patient has severe headache")
    assert corrected.review_status == "CORRECTED"
    assert corrected.human_verified is True
    assert corrected.text == "Patient has severe headahe"
    assert corrected.raw_ocr == "Patient has severe headahe"
    assert corrected.final_text == "Patient has severe headache"


def test_6_rejected_candidate():
    """
    6. Human can reject a secondary candidate; status becomes REJECTED and raw OCR is retained.
    """
    service = SecondaryVerificationService(
        verifier_fn=lambda _r: ("wrong suggestion", 0.62)
    )
    region = service.verify_region(
        RecognitionRegion(
            id=1,
            text="paracetamol 650mg",
            confidence=0.55,
            uncertainty_level="LOW",
            needs_review=True,
            reasons=["low_ocr_confidence"],
        )
    )

    rejected = reject_candidate_region(region)
    assert rejected.review_status == "REJECTED"
    assert rejected.human_verified is True
    assert rejected.text == "paracetamol 650mg"
    assert rejected.raw_ocr == "paracetamol 650mg"
    assert rejected.final_text == "paracetamol 650mg"


def test_7_provenance_preservation():
    """
    7. Provenance preservation: RAW OCR OUTPUT and HUMAN-VERIFIED OUTPUT remain strictly distinct.
    """
    req = ReviewExportRequest(
        filename="rx_note_01.png",
        engine="RapidOCR (PP-OCRv3 ONNX CPU)",
        overall_uncertainty="LOW",
        regions=[
            RegionReviewInput(
                id=1,
                raw_ocr="Patient has severe headahe",
                uncertainty="LOW",
                needs_review=True,
                reasons=["low_ocr_confidence"],
                review_status="CORRECTED",
                final_text="Patient has severe headache",
                human_verified=True,
            ),
            RegionReviewInput(
                id=2,
                raw_ocr="Take 1 tablet daily",
                uncertainty="HIGH",
                needs_review=False,
                reasons=[],
                review_status="ACCEPTED",
                final_text="Take 1 tablet daily",
                human_verified=True,
            ),
        ],
    )

    exported = build_export_json(req)
    assert exported.raw_ocr_text == "Patient has severe headahe\nTake 1 tablet daily"
    assert exported.final_text == "Patient has severe headache\nTake 1 tablet daily"
    assert exported.human_verified is True
    assert exported.regions[0].raw_ocr == "Patient has severe headahe"
    assert exported.regions[0].final_text == "Patient has severe headache"
    assert exported.regions[0].review_status == "CORRECTED"
    assert exported.regions[0].human_verified is True


def test_8_export_txt():
    """
    8. Export TXT works via service and POST /export/txt endpoint, and handles invalid input cleanly.
    """
    payload = {
        "filename": "clinical_note.png",
        "regions": [
            {
                "id": 1,
                "raw_ocr": "Patient has severe headahe",
                "uncertainty": "LOW",
                "review_status": "CORRECTED",
                "final_text": "Patient has severe headache",
                "human_verified": True,
            }
        ],
    }

    response = client.post("/export/txt", json=payload)
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    txt_body = response.text
    assert "DOCUMENT: clinical_note.png" in txt_body
    assert "Patient has severe headache" in txt_body
    assert "Patient has severe headahe" in txt_body
    assert "status=CORRECTED" in txt_body

    # Empty filename should fail cleanly with HTTP 400
    bad_response = client.post("/export/txt", json={"filename": "   ", "regions": []})
    assert bad_response.status_code == 400


def test_9_export_json():
    """
    9. Export JSON works via POST /export/json and preserves full region provenance structure.
    """
    payload = {
        "filename": "discharge_summary.png",
        "engine": "RapidOCR (PP-OCRv3 ONNX CPU)",
        "overall_uncertainty": "LOW",
        "regions": [
            {
                "id": 1,
                "raw_ocr": "severe headahe",
                "uncertainty": "LOW",
                "needs_review": True,
                "reasons": ["low_ocr_confidence"],
                "candidate_text": "severe headache",
                "review_status": "CORRECTED",
                "final_text": "severe headache",
                "human_verified": True,
            }
        ],
    }

    response = client.post("/export/json", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["document"]["filename"] == "discharge_summary.png"
    assert data["raw_ocr_text"] == "severe headahe"
    assert data["final_text"] == "severe headache"
    assert data["human_verified"] is True
    assert len(data["regions"]) == 1
    reg = data["regions"][0]
    assert reg["raw_ocr"] == "severe headahe"
    assert reg["uncertainty"] == "LOW"
    assert reg["review_status"] == "CORRECTED"
    assert reg["final_text"] == "severe headache"
    assert reg["human_verified"] is True


def test_10_secondary_verification_unavailable(monkeypatch):
    """
    10. When no external verification service/API is configured, the service operates cleanly
        and reports 'secondary verification unavailable' with candidate_text = None.
    """
    monkeypatch.delenv("SECONDARY_VERIFICATION_ENABLED", raising=False)
    monkeypatch.delenv("SECONDARY_VERIFICATION_API_KEY", raising=False)

    service = SecondaryVerificationService()
    regions = [
        RecognitionRegion(
            id=1,
            text="CLEAR HEADER",
            confidence=0.94,
            uncertainty_level="HIGH",
            needs_review=False,
        ),
        RecognitionRegion(
            id=2,
            text="faint scrawl",
            confidence=0.41,
            uncertainty_level="LOW",
            needs_review=True,
            reasons=["low_ocr_confidence"],
        ),
    ]

    verified_regions, summary = service.verify_regions(regions)
    assert summary.enabled is False
    assert summary.status == "secondary verification unavailable"
    assert "secondary verification unavailable" in summary.message
    assert summary.total_regions == 2
    assert summary.verified_region_count == 1
    assert summary.skipped_region_count == 1
    assert summary.candidates_generated == 0

    # Region 1 (HIGH) skipped
    assert verified_regions[0].secondary_verification.attempted is False
    assert verified_regions[0].secondary_verification.status == "skipped_reliable_region"

    # Region 2 (LOW) attempted -> reports 'secondary verification unavailable' and candidate_text=None
    assert verified_regions[1].secondary_verification.attempted is True
    assert (
        verified_regions[1].secondary_verification.status
        == "secondary verification unavailable"
    )
    assert verified_regions[1].secondary_verification.candidate_text is None
    assert verified_regions[1].text == "faint scrawl"


def test_11_existing_analyze_compatibility():
    """
    11. POST /analyze preserves full backward compatibility with Phases 1-3 while
        returning Phase 4 verification summary and provenance fields.
    """
    img = Image.new("RGB", (650, 180), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((30, 60), "PATIENT HANDWRITING TEST 2026", fill=(10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    response = client.post(
        "/analyze",
        files={"file": ("phase4_compat.png", buf.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    parsed = AnalyzeResponse(**data)

    assert parsed.status == "success"
    assert parsed.filename == "phase4_compat.png"
    assert parsed.pipeline_status == "recognition_complete"
    assert parsed.uncertainty is not None
    assert parsed.verification is not None
    assert parsed.raw_ocr_text == parsed.recognition.text
    assert parsed.final_text == parsed.recognition.text
    assert parsed.verification.total_regions == len(parsed.recognition.regions)
    for reg in parsed.recognition.regions:
        assert reg.raw_ocr == reg.text
        assert reg.review_status == "PENDING"
        assert reg.final_text == reg.text
        assert reg.secondary_verification is not None
