# Extreme Bad-Handwriting Digitizing Stack

**Project ID:** HNX26EPS04 — HACKNEX 2026

> **Key Innovation:** *"Don't blindly trust OCR — know what needs human verification."*

---

## 1. Problem Statement
Traditional OCR pipelines fail silently when encountering extreme real-world handwriting: rapid clinical scrawls, cramped margin notes, crossed-out words, uneven illumination, low contrast, and motion blur. Worse, standard OCR/LLM wrappers frequently hallucinate plausible-sounding words over illegible ink strokes, creating high-risk errors in medical, archival, and field-note digitization without alerting the user.

---

## 2. Solution
**Extreme Bad-Handwriting Digitizing Stack** replaces blind OCR trust with a **confidence-aware, provenance-preserving digitization workflow**:
1. **Reliable OCR → Accept Efficiently:** Regions with strong optical confidence, crisp stroke contrast, and structural plausibility are classified as `HIGH` reliability and bypass secondary overhead.
2. **Uncertain OCR → Investigate & Verify:** Regions degraded by low optical confidence, blur, faint contrast, or implausible character patterns are classified as `MEDIUM`, `LOW`, or `UNREADABLE` with explainable reason codes, routed through selective secondary verification, and surfaced in an interactive **Human-in-the-Loop (HITL)** review interface.
3. **Strict Provenance Preservation:** Raw OCR output is **never** silently overwritten. Both the unmodified `RAW OCR OUTPUT` and the `HUMAN-VERIFIED OUTPUT` are preserved side-by-side and in exported `.txt` and `.json` files.

---

## 3. Architecture
```text
IMAGE UPLOAD (.png, .jpg, .jpeg, .tiff, .bmp)
  ↓
1. VALIDATION & PREPROCESSING (PreprocessingService)
   ├── EXIF transpose, RGB normalization, safe max-dimension bounding (2048px)
   └── Preserves both Original Image and Grayscale Auto-Contrast Recognition Image
  ↓
2. OPTICAL HANDWRITING RECOGNITION (HandwritingOCRService — RapidOCR / PP-OCRv3 CPU)
   └── Line/phrase bounding boxes (mapped to original coordinates), recognized text, raw CTC confidence
  ↓
3. CONFIDENCE & UNCERTAINTY DETECTION (UncertaintyService — OpenCV + NumPy)
   ├── Local region crop metrics: Laplacian sharpness, P95-P5 contrast, Otsu stroke visibility, noise
   ├── Text & geometry plausibility checks (empty/symbol noise, repeated runs, width-to-text ratio)
   └── Classifies each region into HIGH | MEDIUM | LOW | UNREADABLE + explainable reason codes
  ↓
4. SELECTIVE SECONDARY VERIFICATION (SecondaryVerificationService)
   ├── Triggered ONLY when uncertainty_level in (LOW, UNREADABLE) or needs_review == true
   ├── Skips HIGH reliability regions
   └── Returns candidate interpretations separately (or reports "secondary verification unavailable")
  ↓
5. HUMAN-IN-THE-LOOP REVIEW & PROVENANCE EXPORT (React UI + /export/txt & /export/json)
   ├── Region review states: PENDING | ACCEPTED | CORRECTED | REJECTED
   └── Exports final verified text + immutable raw OCR provenance in .txt and .json formats
```

---

## 4. OCR Pipeline
- **Engine:** `rapidocr-onnxruntime` running pretrained **PP-OCRv3** detection, angle classification, and CTC text recognition models on CPU via ONNX Runtime.
- **Outputs:** Full document transcription, measured inference latency (`processing_time_ms`), mean raw confidence, and per-region quadrilateral polygons + axis-aligned bounding boxes rescaled to original image coordinates.

---

## 5. Preprocessing
Implemented in [`backend/app/services/preprocessing.py`](file:///d:/Extreme%20Bad-Handwriting%20Digitizing%20Stack/backend/app/services/preprocessing.py):
- Validates container format, MIME type, byte size (`MAX_UPLOAD_SIZE_BYTES`, default 10 MB), and image integrity via `Pillow`.
- Applies lossless EXIF orientation correction (`exif_transpose`), RGB conversion, proportional downscaling only if max dimension exceeds `2048px`, and gentle grayscale auto-contrast (`cutoff=1%`).
- Avoids destructive hard binarization or morphological erosion that would sever faint cursive loops.

---

## 6. Confidence Analysis
Implemented in [`backend/app/services/uncertainty.py`](file:///d:/Extreme%20Bad-Handwriting%20Digitizing%20Stack/backend/app/services/uncertainty.py):
- Combines three grounded, non-fabricated signals for each detected region:
  1. **Raw Optical Confidence ($60\%$):** PP-OCRv3 CTC character probability (`ocr_confidence` $\in [0.0, 1.0]$).
  2. **Local Image Quality Score ($25\%$):** Measured on the region's grayscale pixel crop using OpenCV (`laplacian_variance` for sharpness, `dynamic_range` $P_{95}-P_5$ and `rms_contrast` for contrast, Otsu `stroke_ratio` and `fg_bg_separation`, and $3\times 3$ median residual `noise_level`).
  3. **Structural Text Plausibility ($15\%$):** Deterministic checks for empty strings, non-alphanumeric symbol dominance, suspicious repeated character runs, and bounding-box width vs. character count consistency.
- If raw OCR confidence is unavailable (`None`), `normalized_confidence` remains `None` and is never fabricated.

---

## 7. Uncertainty Detection
Each region is assigned one of four reliability tiers using configurable thresholds (`backend/app/utils/config.py`):
- **`HIGH` (`needs_review = False`):** `ocr_confidence >= 0.82`, `normalized_confidence >= 0.78`, `image_quality_score >= 0.50`, `plausibility_score >= 0.80`, and zero warning flags.
- **`MEDIUM` (`needs_review = False` or `True`):** Usable recognition (`ocr_confidence >= 0.60`, `normalized_confidence >= 0.62`) with minor warning signals.
- **`LOW` (`needs_review = True`):** Weak optical confidence (`0.35 <= ocr_confidence < 0.60`) or severe image quality / plausibility degradation (`blurry_region`, `low_local_contrast`, `faint_stroke_visibility`, `suspicious_repeated_characters`, etc.).
- **`UNREADABLE` (`needs_review = True`):** Empty text, pure symbol noise, or critically low optical/calibrated reliability (`ocr_confidence < 0.35` or `normalized_confidence < 0.38`).

---

## 8. Human-in-the-Loop Workflow
Implemented in [`frontend/src/App.jsx`](file:///d:/Extreme%20Bad-Handwriting%20Digitizing%20Stack/frontend/src/App.jsx) and [`backend/app/services/verification.py`](file:///d:/Extreme%20Bad-Handwriting%20Digitizing%20Stack/backend/app/services/verification.py):
- Interactive SVG bounding-box overlay on the original document image color-coded by uncertainty tier (`HIGH`, `MEDIUM`, `LOW`, `UNREADABLE`).
- Clicking any region opens the **Region Inspector & Human Verification** panel where the reviewer can:
  1. Inspect immutable raw OCR text, confidence scores, local image quality metrics, and flagged reason codes.
  2. Inspect secondary verification status/candidate.
  3. **Accept Raw OCR** (`review_status = "ACCEPTED"`).
  4. **Accept Candidate** (`review_status = "ACCEPTED"`, when a secondary candidate is present).
  5. **Reject Candidate** (`review_status = "REJECTED"`).
  6. **Save Manual Correction** (`review_status = "CORRECTED"`).
  7. Batch-accept all reliable (`HIGH`) regions with one click.

---

## 9. Secondary Verification
Implemented in [`backend/app/services/verification.py`](file:///d:/Extreme%20Bad-Handwriting%20Digitizing%20Stack/backend/app/services/verification.py):
- **Selective Triggering:** Invoked **only** when `uncertainty_level in ("LOW", "UNREADABLE")` or `needs_review == True`. Reliable `HIGH` regions are skipped (`status = "skipped_reliable_region"`).
- **Non-Destructive:** Returns candidate interpretations in `secondary_verification` (`original_text`, `candidate_text`, `confidence`, `source`, `requires_human_review`, `status`) without overwriting `region.text`.
- **Clean Offline Operation:** When no external VLM/LLM verifier is configured in `.env` (default), the service operates without external calls, returns `candidate_text = null`, and explicitly reports `"secondary verification unavailable"`.

---

## 10. Export & Provenance
Supports two export formats via both UI download buttons and FastAPI endpoints:
1. **Plain Text (`POST /export/txt` — `.txt`):** Exports the `FINAL VERIFIED TRANSCRIPTION`, the `RAW OCR OUTPUT (UNMODIFIED PROVENANCE)`, and a region-by-region provenance log.
2. **Provenance JSON (`POST /export/json` — `.json`):** Exports structured JSON preserving `document.filename`, `raw_ocr_text`, per-region provenance (`raw_ocr`, `uncertainty`, `review_status`, `final_text`, `human_verified`), and `final_text`.

---

## 11. Implementation Status vs. Future Work & Limitations

### IMPLEMENTED (Phases 1–4 Complete)
- [x] Upload validation (`.png`, `.jpg`, `.jpeg`, `.tiff`, `.tif`, `.bmp`), MIME/extension/size checks, corrupt-byte protection.
- [x] Handwriting-safe preprocessing preserving both original and recognition-ready images.
- [x] Real CPU optical recognition via `rapidocr-onnxruntime` (PP-OCRv3) with bounding boxes and raw confidence scores.
- [x] Multi-signal uncertainty detection combining OCR confidence, OpenCV local crop quality, and text plausibility into `HIGH`, `MEDIUM`, `LOW`, and `UNREADABLE` tiers.
- [x] Selective secondary verification abstraction triggered only on `LOW`, `UNREADABLE`, or `needs_review` regions (cleanly reporting `"secondary verification unavailable"` when no external API is configured).
- [x] Interactive SVG bounding-box overlay, per-region human review workflow (`PENDING`, `ACCEPTED`, `CORRECTED`, `REJECTED`), side-by-side raw vs. verified provenance view, and `.txt` / `.json` exports.
- [x] Ground-truth CER/WER evaluation script (`scripts/evaluate_recognition.py`) and 42 automated `pytest` tests.

### KNOWN LIMITATIONS & FUTURE WORK
- **Extreme Cursive Ceiling (Limitation):** PP-OCRv3 optical recognition struggles to decode heavily connected cursive scrawls and crossed-out medical shorthand. The stack reliably flags these regions as `LOW` or `UNREADABLE` for human verification rather than hallucinating text.
- **External VLM/Contextual Verifier Provider (Future Work):** The `SecondaryVerificationService` interface is implemented and tested, but no external paid VLM/LLM API is bundled by default (`status: "secondary verification unavailable"`). Connecting a local vision-language model (e.g., TrOCR / Florence-2 / Qwen-VL) to `SecondaryVerificationService` is future work.
- **Word-Level Segmentation Inside Long Lines (Future Work):** Bounding boxes and uncertainty scores are computed at the detected phrase/text-line level rather than sub-line individual word tokens.

---

## 12. Setup Instructions

### Backend
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```
Run backend test suite (from repository root):
```powershell
backend\.venv\Scripts\pytest.exe -v backend\tests
```

### Frontend
```powershell
cd frontend
npm install
npm run lint
npm run build
npm run dev
```

---

## 13. Usage Instructions
1. Start the FastAPI backend on `http://127.0.0.1:8000` and the Vite frontend on `http://localhost:5173`.
2. **Upload Handwriting:** Drag and drop or select a handwritten image (`.png`, `.jpg`, `.tiff`, `.bmp`).
3. **Analyze:** Click **Run Digitization Analysis** to execute validation, preprocessing, PP-OCRv3 recognition, uncertainty classification, and selective secondary verification.
4. **Inspect Uncertainty Overlay:** Review color-coded bounding boxes (`HIGH`, `MEDIUM`, `LOW`, `UNREADABLE`) over the original image.
5. **Review Doubtful Regions:** Click any `LOW` or `UNREADABLE` region to inspect its flagged reasons and either **Accept Raw OCR**, **Accept Candidate** (if available), **Reject Candidate**, or **Save Manual Correction**.
6. **Compare Provenance & Export:** Review the side-by-side **RAW OCR OUTPUT** vs. **HUMAN-VERIFIED OUTPUT** panel and click **Export Plain Text (`.txt`)** or **Export Provenance JSON (`.json`)**.

---

## 14. Production Deployment (Render + Vercel)

### Backend on Render (`render.yaml`)
- **Root Directory:** `backend`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path:** `/health`
- **Required Environment Variables:**
  - `PYTHON_VERSION=3.11.11`
  - `ENVIRONMENT=production`
  - `FRONTEND_URL=https://<your-vercel-domain>.vercel.app` (or include in comma-separated `ALLOWED_ORIGINS`)
  - `MAX_UPLOAD_SIZE_BYTES=10485760`
  - `SECONDARY_VERIFICATION_ENABLED=false`

### Frontend on Vercel
- **Framework Preset:** `Vite`
- **Root Directory:** `frontend`
- **Build Command:** `npm run build`
- **Output Directory:** `dist`
- **Required Environment Variable:**
  - `VITE_API_BASE_URL=https://<your-render-service>.onrender.com` (no trailing slash)

