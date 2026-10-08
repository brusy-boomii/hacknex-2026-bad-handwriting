# Extreme Bad-Handwriting Digitizing Stack

**Project ID:** HNX26EPS04 — HACKNEX 2026

## Problem Statement
Traditional OCR systems frequently fail when encountering "extreme" handwriting: doctor scrawls, cramped margin notes, inconsistent spacing, crossed-out words, and poor image quality. These systems often hallucinate text when uncertain, leading to critical errors in digitization.

## Proposed Solution
A confidence-aware handwriting digitization system that prioritizes integrity over hallucination. The core design is a modular pipeline that **validates and preprocesses**, **recognizes** (Phase 2), **measures confidence** (Phase 3), and **flags uncertainty** instead of inventing results.

## Phase 1 Status: Foundation
Phase 1 establishes the modular repository structure, typed FastAPI backend, image ingestion/validation service, React frontend with drag-and-drop upload, and automated test suite.
- [x] Backend infrastructure (FastAPI + Uvicorn)
- [x] Typed Pydantic response schemas (`HealthResponse`, `ImageMetadata`, `AnalyzeResponse`, `ErrorResponse`)
- [x] `GET /health` and `POST /analyze` API endpoints
- [x] Strict upload validation (missing file, filename, MIME type, extension, empty file, configurable `MAX_UPLOAD_SIZE_BYTES`, and Pillow header + pixel stream integrity verification)
- [x] Frontend foundation (React 19 + Vite) with click-to-select and drag-and-drop image upload
- [x] ESLint flat configuration (`frontend/eslint.config.js`) and production build verification
- [x] Environment configuration via `.env.example` and `app/utils/config.py`
- [x] Automated `pytest` backend test suite (11 tests covering valid and invalid/corrupt/oversized uploads)
- [x] Phase 1 architecture documentation (`docs/architecture/phase-1.md`)

## Technology Stack
- **Backend:** Python 3.13, FastAPI, Uvicorn, Pillow, Pydantic, python-dotenv
- **Frontend:** React 19, Vite 6, ESLint 9, CSS
- **Testing & Tooling:** pytest, httpx, npm, Git

## Folder Structure
```text
hacknex-2026-bad-handwriting/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py          # GET /health and POST /analyze endpoints
│   │   ├── schemas/
│   │   │   └── __init__.py        # Pydantic response & error models
│   │   ├── services/
│   │   │   └── preprocessing.py   # Pillow image verification & metadata extraction
│   │   ├── utils/
│   │   │   └── config.py          # Environment config (MAX_UPLOAD_SIZE_BYTES, CORS)
│   │   └── main.py                # FastAPI application entry point
│   ├── tests/
│   │   ├── test_health.py         # Health endpoint tests
│   │   └── test_analyze.py        # Upload validation & analysis endpoint tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Upload UI (click + drag-and-drop) & API client
│   │   ├── index.css              # Application styling
│   │   └── main.jsx               # React root mount
│   ├── eslint.config.js           # ESLint v9 flat config
│   ├── package.json
│   └── vite.config.js             # Dev server & /api proxy configuration
├── data/
│   ├── evaluation/
│   └── samples/
├── docs/
│   ├── architecture/
│   │   └── phase-1.md             # Phase 1 architecture & data flow documentation
│   └── evaluation/
├── scripts/
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

## API Endpoints (Phase 1)
- `GET /health`: Returns `HealthResponse` (`status`, `application`, `version`, `phase`, `description`).
- `POST /analyze`: Accepts a `multipart/form-data` image upload (`file`), validates extension (`.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.bmp`), MIME type (`image/*`), byte size (`MAX_UPLOAD_SIZE_BYTES`, default 10 MB), and full Pillow image decodability. Returns `AnalyzeResponse` with extracted `ImageMetadata` (`format`, `mode`, `width`, `height`, `channels`), or a structured `400` / `413` JSON error on invalid/corrupt uploads.

## Current Limitations (What Is Not Implemented Yet)
- **No OCR/HTR engine is active in Phase 1:** `POST /analyze` validates the uploaded image and extracts structural metadata only; it does not transcribe handwriting yet.
- **No pixel transformations yet:** Grayscale conversion, denoising, deskewing, and binarization are scheduled for Phase 2.
- **No accuracy metrics reported:** CER/WER and confidence calibration metrics are not calculated until a real recognition engine and evaluation dataset are active.

## Roadmap
- **Phase 2:** Image preprocessing transformations, layout/line segmentation, and Handwriting Recognition (HTR) engine integration.
- **Phase 3:** Token/line confidence scoring and uncertainty detection.
- **Phase 4:** Selective verification and human-in-the-loop review interface.
