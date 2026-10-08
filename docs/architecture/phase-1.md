# Phase 1 Architecture: Foundation & Ingestion Pipeline

**Project:** HNX26EPS04 — Extreme Bad-Handwriting Digitizing Stack  
**Event:** HACKNEX 2026  
**Phase:** 1 (Foundation)

---

## 1. Project Goal
Traditional Optical Character Recognition (OCR) pipelines routinely fail on extreme bad handwriting—such as rushed clinical notes, cramped margin annotations, variable slant, and low-contrast scans—and frequently hallucinate plausible-sounding text when uncertain.

The goal of the **Extreme Bad-Handwriting Digitizing Stack** is to build a modular, confidence-aware handwriting digitization pipeline that:
1. Validates and preprocesses document images cleanly.
2. Performs handwriting recognition while explicitly measuring token/line confidence (Phase 2+).
3. Flags uncertain regions rather than fabricating transcriptions (Phase 3+).

---

## 2. Current Phase-1 Architecture
Phase 1 establishes the decoupled full-stack foundation, typed API contracts, environment-driven configuration, and strict upload validation layer.

```text
+-------------------------------------------------------------------+
|                     React 19 + Vite Frontend                      |
|  - Live system health indicator (GET /api/health)                 |
|  - Click-to-select & Drag-and-Drop upload zone (App.jsx)          |
|  - Image preview & structured JSON response/error display         |
+-------------------------------------------------------------------+
                                  |
                                  | Vite Dev Proxy (/api/* -> 127.0.0.1:8000/*)
                                  v
+-------------------------------------------------------------------+
|                        FastAPI Backend API                        |
|  - CORS middleware & RequestValidationError handler (main.py)     |
|  - Environment config loader (app/utils/config.py)                |
|  - Typed Pydantic response schemas (app/schemas/__init__.py)      |
|  - API router: GET /health, POST /analyze (app/api/routes.py)     |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                 PreprocessingService (Phase 1)                    |
|  - Binary stream header verification (Pillow Image.verify())      |
|  - Full pixel stream decoding check (Pillow Image.load())         |
|  - Structural metadata extraction (format, mode, width, height,   |
|    channel count) returned as ImageMetadata                       |
+-------------------------------------------------------------------+
```

---

## 3. Frontend / Backend Relationship
- **Frontend (`frontend/`):** Single-page application built with React 19 and Vite.
- **Dev Server Proxy (`frontend/vite.config.js`):** All frontend requests prefixed with `/api` (e.g., `/api/health`, `/api/analyze`) are proxied to `http://127.0.0.1:8000` with the `/api` prefix stripped.
- **CORS (`backend/app/main.py`):** Configured via the `ALLOWED_ORIGINS` environment variable (defaulting to `http://localhost:5173,http://127.0.0.1:5173`).

---

## 4. Upload Flow
1. **Selection:** The user selects an image via the file picker (`onClick` $\rightarrow$ `<input type="file">`) or drags and drops a file onto `.upload-section` (`onDragEnter`, `onDragOver`, `onDragLeave`, `onDrop`).
2. **Client Preview:** Both selection paths invoke a shared `selectFile()` handler in `frontend/src/App.jsx`, generating an object URL preview for image files and revoking stale URLs on cleanup.
3. **Submission:** Clicking **Run Analysis** packages the file into a `FormData` payload under the `file` field and sends `POST /api/analyze`.
4. **Validation & Inspection:** FastAPI validates the multipart upload, checks size against `MAX_UPLOAD_SIZE_BYTES`, decodes the image via `PreprocessingService`, and returns a typed `AnalyzeResponse` JSON payload (or a structured `ErrorResponse` on failure).
5. **Presentation:** The frontend renders either the actual validated metadata returned by the backend or the clean error message.

---

## 5. Current Preprocessing Stage
Implemented in `backend/app/services/preprocessing.py` (`PreprocessingService`):
- Accepts raw uploaded bytes (`image_bytes: bytes`).
- Rejects empty payloads immediately.
- Opens the byte stream with Pillow (`PIL.Image.open`) and runs `.verify()` to validate container headers.
- Re-opens the byte stream and runs `.load()` to force full pixel decoding, ensuring truncated or corrupt image streams are caught before any downstream processing.
- Extracts and returns a validated `ImageMetadata` Pydantic model containing:
  - `format` (e.g., `PNG`, `JPEG`, `BMP`, `TIFF`)
  - `mode` (e.g., `RGB`, `RGBA`, `L`)
  - `width` (pixels, $> 0$)
  - `height` (pixels, $> 0$)
  - `channels` (number of image bands, $> 0$)

---

## 6. API Endpoints

### `GET /health`
- **Response Model:** `HealthResponse`
- **Status Code:** `200 OK`
- **Payload:**
  ```json
  {
    "status": "healthy",
    "application": "Extreme Bad-Handwriting Digitizing Stack",
    "version": "0.1.0",
    "phase": 1,
    "description": "Foundation phase established."
  }
  ```

### `POST /analyze`
- **Request:** `multipart/form-data` with field `file`
- **Response Model:** `AnalyzeResponse` (`200 OK`)
- **Payload:**
  ```json
  {
    "status": "received",
    "filename": "sample_note.png",
    "metadata": {
      "format": "PNG",
      "mode": "RGB",
      "width": 120,
      "height": 80,
      "channels": 3
    },
    "message": "Image received and validated. Recognition pipeline will be implemented in Phase 2.",
    "pipeline_status": "foundation_active"
  }
  ```

---

## 7. Validation & Error Handling
All client upload errors return clean structured JSON (`{"detail": "..."}`) without exposing internal Python stack traces:

| Condition | HTTP Status | Behavior |
| :--- | :--- | :--- |
| Missing `file` field or malformed multipart request | `400 Bad Request` | Caught by route check / `RequestValidationError` handler |
| Missing or blank filename | `400 Bad Request` | Rejects blank/whitespace filenames |
| Unsupported file extension (not in `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.bmp`) | `400 Bad Request` | Rejects with list of allowed extensions |
| Missing or non-`image/*` MIME content type | `400 Bad Request` | Rejects non-image MIME types |
| Empty file (`0` bytes) | `400 Bad Request` | Rejects before Pillow decoding |
| File exceeds `MAX_UPLOAD_SIZE_BYTES` (default 10 MB) | `413 Content Too Large` | Configurable via environment variable |
| Corrupt, truncated, or unreadable image bytes | `400 Bad Request` | `PreprocessingService` raises `ValueError` $\rightarrow$ mapped to `HTTP 400` |

---

## 8. What Is Intentionally NOT Implemented Yet
In accordance with project integrity rules, Phase 1 does **not** implement or simulate:
- Optical Character Recognition (OCR) or Handwritten Text Recognition (HTR).
- Pixel-level image transformations (grayscale conversion, deskewing, denoising, contrast normalization, or adaptive binarization).
- Line/word segmentation or layout analysis.
- Confidence scoring, token probabilities, or uncertainty flagging.
- Character Error Rate (CER) or Word Error Rate (WER) evaluation metrics.

---

## 9. Planned Phase 2 Recognition Layer
Phase 2 will extend this foundation by adding:
1. **Pixel Preprocessing Pipeline:** Grayscale normalization, contrast enhancement, denoising, and line/region segmentation for degraded handwriting images.
2. **Pluggable Recognition Engine Interface:** Decoupled HTR/OCR service layer behind typed Pydantic schemas so recognition models can be evaluated and swapped cleanly.
3. **Baseline Transcription Output:** Real transcribed text output integrated into the `/analyze` pipeline response and displayed in the frontend UI.
