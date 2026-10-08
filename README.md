# Extreme Bad-Handwriting Digitizing Stack

**Project ID:** HNX26EPS04 — HACKNEX 2026

## Problem Statement
Traditional OCR systems frequently fail when encountering "extreme" handwriting: doctor scrawls, cramped margin notes, inconsistent spacing, crossed-out words, and poor image quality. These systems often hallucinate text when uncertain, leading to critical errors in digitization.

## Proposed Solution
A confidence-aware handwriting digitization system that prioritizes integrity over hallucination. The core design is a modular pipeline that **validates and preprocesses**, **recognizes**, **measures multi-signal confidence & image quality**, **flags uncertainty (`HIGH` / `MEDIUM` / `LOW` / `UNREADABLE`)**, and supports **human-in-the-loop review** instead of inventing results.

## Current Status: Phase 3 — Confidence-Aware Uncertainty Detection
- [x] **Phase 1 — Foundation:** FastAPI backend, Pydantic schemas, upload validation, React 19 + Vite frontend with drag-and-drop, ESLint v9 flat config.
- [x] **Phase 2 — Recognition Pipeline:** Handwriting-safe preprocessing (`PreprocessingService`), modular optical recognition (`HandwritingOCRService` via `rapidocr-onnxruntime` PP-OCRv3 on CPU), and CER/WER evaluation script (`scripts/evaluate_recognition.py`).
- [x] **Phase 3 — Confidence-Aware Uncertainty Detection:**
  - Dedicated decoupled `UncertaintyService` (`backend/app/services/uncertainty.py`) combining raw PP-OCRv3 confidence ($60\%$), local OpenCV image quality ($25\%$: Laplacian sharpness, $P_{95}-P_{5}$ contrast, Otsu stroke visibility, median residual noise, box geometry), and structural text plausibility ($15\%$).
  - Transparent region-level classification into `HIGH`, `MEDIUM`, `LOW`, and `UNREADABLE` tiers with explainable reason codes and configurable thresholds.
  - Frontend SVG bounding-box overlay on the original document image, accessibility-friendly tier badges + legend, uncertainty-aware transcription view, and interactive human-in-the-loop region inspector & correction panel.
  - 31 automated `pytest` tests covering foundation, recognition, and all 10 Phase 3 uncertainty scenarios.

## Technology Stack
- **Backend:** Python 3.13, FastAPI, Uvicorn, Pillow, NumPy, OpenCV (`opencv-python-headless`), RapidOCR (`rapidocr-onnxruntime` / ONNX Runtime CPU), Pydantic
- **Frontend:** React 19, Vite 6, ESLint 9, SVG Document Overlay, CSS
- **Testing & Evaluation:** pytest, httpx, CER/WER Levenshtein evaluation utility

## Folder Structure
```text
hacknex-2026-bad-handwriting/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py              # GET /health and POST /analyze endpoints
│   │   ├── schemas/
│   │   │   └── __init__.py            # Typed Pydantic models (AnalyzeResponse, UncertaintySummary, etc.)
│   │   ├── services/
│   │   │   ├── preprocessing.py       # Handwriting-safe preprocessing & dual-image preservation
│   │   │   ├── handwriting_ocr.py     # Modular RapidOCR (PP-OCRv3) recognition service
│   │   │   └── uncertainty.py         # Phase 3 multi-signal uncertainty & image quality service
│   │   ├── utils/
│   │   │   └── config.py              # Environment config & configurable uncertainty thresholds
│   │   └── main.py                    # FastAPI application entry point
│   ├── tests/
│   │   ├── test_health.py             # Health endpoint tests
│   │   ├── test_analyze.py            # Upload validation & /analyze pipeline tests
│   │   ├── test_recognition.py        # Preprocessing, OCR service, & CER/WER evaluation tests
│   │   └── test_uncertainty.py        # Phase 3 uncertainty classification & image quality tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                    # Upload, SVG bbox overlay, uncertainty transcription & review UI
│   │   ├── index.css                  # Forensic document-analysis & tier badge styling
│   │   └── main.jsx                   # React root mount
│   ├── eslint.config.js               # ESLint v9 flat config
│   ├── package.json
│   └── vite.config.js                 # Dev server & /api proxy configuration
├── data/
│   ├── evaluation/
│   │   └── README.md                  # Ground-truth dataset format for CER/WER evaluation
│   └── samples/
│       └── README.md                  # Guide for adding genuine team handwriting samples
├── docs/
│   ├── architecture/
│   │   ├── phase-1.md                 # Phase 1 foundation architecture
│   │   ├── phase-2-recognition.md     # Phase 2 recognition engine selection & pipeline design
│   │   └── phase-3-uncertainty.md     # Phase 3 multi-signal uncertainty algorithm & thresholds
│   └── evaluation/
├── scripts/
│   └── evaluate_recognition.py        # Real CER/WER evaluation runner
├── .env.example
├── GEMINI.md
└── README.md
```

## Local Setup & Verification

### Backend
1. Navigate to `backend/`
2. Create a virtual environment: `py -m venv .venv`
3. Activate environment: `.venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Run development server: `python -m app.main`
6. Run automated tests (from project root): `backend\.venv\Scripts\pytest.exe -v backend\tests`

### Frontend
1. Navigate to `frontend/`
2. Install dependencies: `npm install`
3. Run linter: `npm run lint`
4. Run production build check: `npm run build`
5. Run development server: `npm run dev`

## API Documentation (Phase 3)

### `GET /health`
Returns `HealthResponse` (`status: "healthy"`, `version: "0.3.0"`, `phase: 3`).

### `POST /analyze`
- **Accepted Input:** `multipart/form-data` with field `file` (`.png`, `.jpg`, `.jpeg`, `.tiff`, `.tif`, `.bmp`, up to `MAX_UPLOAD_SIZE_BYTES` = 10 MB default).
- **Response Structure (`200 OK` — `AnalyzeResponse`):**
  Preserves all Phase 1 and Phase 2 fields (`status`, `filename`, `image`, `metadata`, `preprocessing`, `recognition`, `warnings`, `message`, `pipeline_status`) and adds:
  - Enriched `recognition.regions[]` entries with `ocr_confidence`, `normalized_confidence`, `uncertainty_level` (`"HIGH" | "MEDIUM" | "LOW" | "UNREADABLE"`), `needs_review`, `reasons`, and `quality_indicators` (`laplacian_variance`, `rms_contrast`, `dynamic_range`, `stroke_ratio`, `fg_bg_separation`, `noise_level`, `image_quality_score`, `plausibility_score`).
  - Top-level `uncertainty` (`UncertaintySummary`) containing `overall_level`, `mean_ocr_confidence`, `mean_normalized_confidence`, `mean_image_quality_score`, `total_regions`, `flagged_region_count`, `counts` (`HIGH`, `MEDIUM`, `LOW`, `UNREADABLE`), `review_recommended`, `annotated_text`, `summary_reasons`, and `regions`.

## Current Limitations
- **Extreme Cursive & Degraded Scrawls:** PP-OCRv3 optical recognition has known limitations on heavily connected cursive strokes, crossed-out words, and severe slant. Phase 3 explicitly detects and flags these low-reliability regions (`LOW` / `UNREADABLE`) so they are surfaced for human review rather than trusted silently.
- **Contextual / VLM Verification Not Yet Implemented:** Automated contextual verification or multi-engine adjudication on flagged regions is not implemented in Phase 3; uncertain regions are surfaced for manual human inspection in the UI.
- **No Fabricated Benchmarks:** CER/WER metrics are only computed when `scripts/evaluate_recognition.py` is run on real ground-truth samples in `data/evaluation/`.

## Roadmap
- **Phase 4:** Selective context-aware / VLM verification for flagged `LOW`/`UNREADABLE` regions and structured human-verified export workflow.
