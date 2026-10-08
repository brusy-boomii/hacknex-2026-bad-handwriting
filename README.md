# Extreme Bad-Handwriting Digitizing Stack

**Project ID:** HNX26EPS04 — HACKNEX 2026

## Problem Statement
Traditional OCR systems frequently fail when encountering "extreme" handwriting: doctor scrawls, cramped margin notes, inconsistent spacing, crossed-out words, and poor image quality. These systems often hallucinate text when uncertain, leading to critical errors in digitization.

## Proposed Solution
A confidence-aware handwriting digitization system that prioritizes integrity over hallucination. The core design is a modular pipeline that **validates and preprocesses**, **recognizes** (Phase 2), **measures confidence** (Phase 3), and **flags uncertainty** instead of inventing results.

## Current Status: Phase 2 — Baseline Handwriting Recognition Pipeline
- [x] **Phase 1 — Foundation:** FastAPI backend, Pydantic schemas, upload validation, React 19 + Vite frontend with drag-and-drop, ESLint v9 flat config.
- [x] **Phase 2 — Recognition Pipeline:**
  - Handwriting-safe preprocessing (`PreprocessingService`) preserving both original image and recognition-ready image (EXIF orientation, aspect-ratio-preserving scaling, grayscale, contrast normalization, and conditional denoising).
  - Modular optical recognition engine (`HandwritingOCRService`) powered by **RapidOCR (`rapidocr-onnxruntime` / PP-OCRv3 on ONNX Runtime CPU)**.
  - Real text detection, line/region bounding boxes, and genuine engine confidence scores returned via `POST /analyze`.
  - Updated document-analysis frontend displaying recognition telemetry, editable recognized text, warnings, and detected region coordinates.
  - Baseline CER/WER evaluation script (`scripts/evaluate_recognition.py`) and dataset structure (`data/evaluation/`).

## Technology Stack
- **Backend:** Python 3.13, FastAPI, Uvicorn, Pillow, NumPy, RapidOCR (`rapidocr-onnxruntime` / ONNX Runtime CPU), Pydantic
- **Frontend:** React 19, Vite 6, ESLint 9, CSS
- **Testing & Evaluation:** pytest, httpx, CER/WER Levenshtein evaluation utility

## Folder Structure
```text
hacknex-2026-bad-handwriting/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py              # GET /health and POST /analyze endpoints
│   │   ├── schemas/
│   │   │   └── __init__.py            # Typed Pydantic models (AnalyzeResponse, RecognitionResult, etc.)
│   │   ├── services/
│   │   │   ├── preprocessing.py       # Handwriting-safe preprocessing & dual-image preservation
│   │   │   └── handwriting_ocr.py     # Modular RapidOCR (PP-OCRv3) recognition service
│   │   ├── utils/
│   │   │   └── config.py              # Environment config (MAX_UPLOAD_SIZE_BYTES, CORS)
│   │   └── main.py                    # FastAPI application entry point
│   ├── tests/
│   │   ├── test_health.py             # Health endpoint tests
│   │   ├── test_analyze.py            # Upload validation & /analyze pipeline tests
│   │   └── test_recognition.py        # Preprocessing, OCR service, error handling & evaluation tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                    # Document upload, telemetry, editable text & region table UI
│   │   ├── index.css                  # Forensic document-analysis styling
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
│   │   └── phase-2-recognition.md     # Phase 2 recognition engine selection & pipeline design
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

### Baseline Evaluation (`CER` / `WER`)
```powershell
backend\.venv\Scripts\python.exe scripts\evaluate_recognition.py
```

## API Documentation (Phase 2)

### `GET /health`
Returns `HealthResponse` (`status: "healthy"`, `version: "0.2.0"`, `phase: 2`).

### `POST /analyze`
- **Accepted Input:** `multipart/form-data` with field `file` (`.png`, `.jpg`, `.jpeg`, `.tiff`, `.tif`, `.bmp`, up to `MAX_UPLOAD_SIZE_BYTES` = 10 MB default).
- **Response Structure (`200 OK` — `AnalyzeResponse`):**
  ```json
  {
    "status": "success",
    "filename": "note.png",
    "image": {
      "format": "PNG",
      "mode": "RGB",
      "width": 600,
      "height": 160,
      "channels": 3
    },
    "metadata": {
      "format": "PNG",
      "mode": "RGB",
      "width": 600,
      "height": 160,
      "channels": 3
    },
    "preprocessing": {
      "original_width": 600,
      "original_height": 160,
      "processed_width": 600,
      "processed_height": 160,
      "scale_factor": 1.0,
      "operations": ["grayscale_conversion"]
    },
    "recognition": {
      "text": "Patient Rx 50mg daily",
      "engine": "rapidocr-onnxruntime (PP-OCRv3)",
      "processing_time_ms": 145.2,
      "confidence": 0.8912,
      "regions": [
        {
          "id": 1,
          "text": "Patient Rx 50mg daily",
          "confidence": 0.8912,
          "bbox": {
            "x_min": 24,
            "y_min": 38,
            "x_max": 380,
            "y_max": 86,
            "width": 356,
            "height": 48,
            "polygon": [[24, 38], [380, 38], [380, 86], [24, 86]]
          },
          "region_type": "line"
        }
      ]
    },
    "warnings": [],
    "message": "Recognition completed (1 region(s) detected in 145.2 ms).",
    "pipeline_status": "recognition_complete"
  }
  ```
- **Error Responses:**
  - `400 Bad Request`: Missing file, missing filename, unsupported extension, non-`image/*` MIME type, empty file (`0` bytes), corrupt/unreadable image bytes, or image pixel count exceeding safety cap (`40,000,000` pixels).
  - `413 Content Too Large`: File byte size exceeds `MAX_UPLOAD_SIZE_BYTES`.
  - `502 Bad Gateway`: Recognition engine execution failure during inference.
  - `503 Service Unavailable`: Recognition model runtime unavailable.

## Current Limitations
- **Baseline Optical Recognizer Limitations:** RapidOCR (`PP-OCRv3` ONNX) runs locally on CPU and handles clear-to-moderate handwriting, alphanumeric notes, and multi-line layouts well, but severely degraded cursive or overlapping doctor scrawls can still cause character substitutions or low confidence scores.
- **No VLM/LLM Correction or Uncertainty Highlighting Yet:** Token-level uncertainty flagging, calibration, and selective contextual verification are scheduled for Phases 3 and 4.
- **No Fabricated Benchmarks:** CER/WER numbers are only reported when `scripts/evaluate_recognition.py` is run against genuine ground-truth handwriting pairs in `data/evaluation/`.

## Roadmap
- **Phase 3:** Token/region confidence calibration and explicit uncertainty detection & flagging.
- **Phase 4:** Selective context-aware verification and human-in-the-loop correction UI.
