# Phase 4 Architecture: Selective Secondary Verification, Human-in-the-Loop Review & Provenance Export

**Project ID:** HNX26EPS04 — Extreme Bad-Handwriting Digitizing Stack (HACKNEX 2026)

---

## 1. Core Architectural Principle

> *"Don't blindly trust OCR — know what needs human verification."*

```text
IMAGE
  ↓
VALIDATION & PREPROCESSING
  ↓
OPTICAL RECOGNITION (RapidOCR / PP-OCRv3)
  ↓
MULTI-SIGNAL UNCERTAINTY ANALYSIS (HIGH / MEDIUM / LOW / UNREADABLE)
  ↓
SELECTIVE SECONDARY VERIFICATION (Only LOW / UNREADABLE / needs_review)
  ↓
HUMAN-IN-THE-LOOP REVIEW (PENDING / ACCEPTED / CORRECTED / REJECTED)
  ↓
PROVENANCE-PRESERVING EXPORT (.txt / .json)
```

---

## 2. Phase 4A — Selective Secondary Verification (`backend/app/services/verification.py`)

### Routing Rule
`SecondaryVerificationService.should_verify_region(region)` returns `True` **only** when:
- `region.uncertainty_level in ("LOW", "UNREADABLE")`, **OR**
- `region.needs_review == True`

Regions classified as `HIGH` reliability (`needs_review == False`) bypass secondary verification (`attempted = False`, `status = "skipped_reliable_region"`, `requires_human_review = False`).

### Non-Destructive Candidate Contract
Secondary verification **never** overwrites `region.text` or `region.raw_ocr`. Instead, it attaches a `SecondaryVerificationResult` object:
```json
{
  "original_text": "severe headahe",
  "candidate_text": "severe headache",
  "confidence": 0.81,
  "source": "secondary_verification",
  "requires_human_review": true,
  "attempted": true,
  "status": "candidate_available",
  "message": "Secondary candidate interpretation available for human review."
}
```

### Graceful Operation Without External VLM/LLM APIs
When no external secondary verification provider is configured in environment variables (`SECONDARY_VERIFICATION_ENABLED=false` by default):
- The service does **not** fabricate candidates or guess text.
- Flagged regions return `candidate_text = null` (`None`), `confidence = null`, `status = "secondary verification unavailable"`, and `requires_human_review = true`.

---

## 3. Phase 4B — Human-in-the-Loop Review & Provenance

Each detected region tracks an explicit `ReviewStatus`:
- `PENDING` — Initial state prior to human review; `final_text` defaults to `raw_ocr` (`human_verified = False`).
- `ACCEPTED` — Human verified and accepted either the original raw OCR text (`accept_ocr_region`) or a secondary candidate (`accept_candidate_region`).
- `CORRECTED` — Human entered a manual transcription override (`correct_region_text`); stored in `final_text` while `text` and `raw_ocr` remain untouched.
- `REJECTED` — Human explicitly rejected a secondary candidate (`reject_candidate_region`) and retained `raw_ocr` (`human_verified = True`).

---

## 4. Export & Provenance Formats

### 1. Provenance JSON (`POST /export/json` & UI Download)
Preserves document metadata, immutable `raw_ocr_text`, per-region provenance (`raw_ocr`, `uncertainty`, `review_status`, `final_text`, `human_verified`), and the full `final_text`:
```json
{
  "document": {
    "filename": "clinical_note.png",
    "engine": "RapidOCR (PP-OCRv3 ONNX CPU)",
    "overall_uncertainty": "LOW"
  },
  "raw_ocr_text": "Patient has severe headahe",
  "regions": [
    {
      "id": 1,
      "raw_ocr": "Patient has severe headahe",
      "uncertainty": "LOW",
      "needs_review": true,
      "reasons": ["low_ocr_confidence"],
      "candidate_text": null,
      "review_status": "CORRECTED",
      "final_text": "Patient has severe headache",
      "human_verified": true
    }
  ],
  "final_text": "Patient has severe headache",
  "human_verified": true
}
```

### 2. Plain Text (`POST /export/txt` & UI Download)
Produces a human-readable `.txt` file containing the `FINAL VERIFIED TRANSCRIPTION`, the `RAW OCR OUTPUT (UNMODIFIED PROVENANCE)`, and the per-region provenance log.
