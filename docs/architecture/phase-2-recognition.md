# Phase 2 Architecture: Handwriting & Document Recognition Engine

**Project:** HNX26EPS04 — Extreme Bad-Handwriting Digitizing Stack  
**Event:** HACKNEX 2026  
**Phase:** 2 (Baseline Recognition Pipeline)

---

## 1. Selected Recognition Engine

- **Engine:** **RapidOCR (`rapidocr-onnxruntime`)** backed by **ONNX Runtime (CPU)** and **OpenCV (`opencv-python-headless`)**.
- **Underlying Models:** Pretrained **PP-OCRv3** pipeline converted to ONNX format:
  1. **Text Detection (`ch_PP-OCRv3_det_infer.onnx`):** Differentiable Binarization (DBNet++) detector that localizes text lines and arbitrary quadrilateral regions.
  2. **Direction Classification (`ch_ppocr_mobile_v2.0_cls_infer.onnx`):** Orientation classifier ($0^\circ$ vs. $180^\circ$) for detected line crops.
  3. **Text Recognition (`ch_PP-OCRv3_rec_infer.onnx`):** SVTR-LCNet / CRNN sequence recognition model with CTC decoding that outputs recognized character strings and per-region softmax confidence scores.

---

## 2. Why This Engine Was Selected

The development and evaluation environment has specific constraints verified during system audit:
- **OS & Runtime:** Windows (`win32`) running **Python 3.13.12**.
- **Hardware:** CPU-only execution (`nvidia-smi` / CUDA GPU unavailable).
- **System Binaries:** No system-wide Tesseract installation in `PATH`.

`rapidocr-onnxruntime` was selected because:
1. **Native Python 3.13 & Windows CPU Compatibility:** Prebuilt `win_amd64` wheels exist for `onnxruntime`, `opencv-python-headless`, `numpy`, and `rapidocr-onnxruntime` on Python 3.13.
2. **Self-Contained Pretrained Models (Zero Runtime Download Fragility):** All three ONNX models (detection, classification, recognition) are packaged directly inside the Python wheel (~15 MB total). The backend initializes offline in `< 500 ms` without multi-gigabyte HuggingFace/PyTorch downloads that could stall or time out during live evaluation.
3. **Rich Region & Confidence Output:** Unlike bare whole-line recognizers, RapidOCR natively returns:
   - Polygon / bounding-box coordinates for every detected text line/region.
   - Recognized text string per region.
   - Genuine CTC/softmax confidence scores ($\in [0.0, 1.0]$) per region.
4. **CPU Inference Speed:** ONNX Runtime executes the detection + recognition pipeline in $50\text{--}400\text{ ms}$ per page on a standard laptop CPU.

---

## 3. Alternatives Considered

| Engine / Library | Pros | Why Not Selected as Primary in Phase 2 |
| :--- | :--- | :--- |
| **Microsoft TrOCR (`transformers` + `torch`)** | Strong transformer decoder for single-line cursive handwriting | Requires ~2.5 GB+ PyTorch + HuggingFace model downloads, lacks a built-in page/line detector (fails on multi-line pages without an external detector), and is slow on CPU-only machines. |
| **EasyOCR (`easyocr`)** | Popular Python OCR API with CRAFT detector | Pulls full PyTorch runtime and downloads external model weights on first run; significantly slower on CPU than ONNX Runtime. |
| **PaddleOCR (`paddlepaddle` + `paddleocr`)** | Same PP-OCRv3 models as RapidOCR | Native `paddlepaddle` C++ wheel support on Windows Python 3.13 is fragile compared to `onnxruntime`. |
| **Tesseract OCR (`pytesseract`)** | Classic open-source OCR | Requires an external Windows binary installer (`tesseract.exe`) not present on this machine, and performs poorly on unconstrained handwriting. |

---

## 4. Pipeline Architecture (Phase 2)

```text
Uploaded Image Bytes
        │
        ▼
[1. Upload & Structural Validation] (routes.py + PreprocessingService)
  - Extension, MIME type, non-empty, MAX_UPLOAD_SIZE_BYTES checks
  - Pillow .verify() + .load() pixel stream integrity check
  - Preserves original image dimensions & metadata
        │
        ▼
[2. Handwriting-Aware Preprocessing] (PreprocessingService.preprocess_for_ocr)
  - EXIF orientation normalization (ImageOps.exif_transpose)
  - Aspect-ratio-preserving downscaling if max dimension > 2400px
  - Grayscale conversion & gentle autocontrast normalization
  - Non-local means / median denoising for noisy scans
  - Preserves both Original Image and Preprocessed Recognition Image
        │
        ▼
[3. Modular Recognition Service] (HandwritingOCRService)
  - Runs RapidOCR (DBNet detection + SVTR/CRNN recognition) on preprocessed image
  - Fallback single-line recognition pass when faint/cramped strokes evade page-level detection
  - Extracts ordered text regions, bounding boxes, and genuine engine confidence scores
        │
        ▼
[4. Structured API Response] (AnalyzeResponse)
  - status, filename, image metadata, preprocessing metadata,
    recognition result (text, engine, processing_time_ms, confidence, regions), warnings
```

---

## 5. Expected Input & Output

### Input to `HandwritingOCRService.recognize()`
- Validated `PIL.Image.Image` (or preprocessed grayscale/RGB image array) produced by `PreprocessingService`.

### Output (`RecognitionResult` Pydantic Schema)
- `text` (`str`): Full concatenated transcription ordered top-to-bottom, left-to-right (empty string `""` if no text is detected; never fabricated).
- `engine` (`str`): `"rapidocr-onnxruntime (PP-OCRv3)"`.
- `processing_time_ms` (`float`): Actual measured inference time in milliseconds.
- `confidence` (`Optional[float]`): Mean confidence across detected regions in $[0.0, 1.0]$, or `null` if no regions were detected.
- `regions` (`List[RecognitionRegion]`):
  - `id` (`int`): 1-based region index.
  - `text` (`str`): Recognized text for the region.
  - `confidence` (`Optional[float]`): Engine-reported confidence in $[0.0, 1.0]$.
  - `bbox` (`BoundingBox`): Axis-aligned bounding box (`x_min`, `y_min`, `x_max`, `y_max`, `width`, `height`) and 4-point `polygon` in original image pixel coordinates.
  - `region_type` (`str`): `"line"`.

---

## 6. Honest Limitations

1. **Extreme Messy Cursive & Doctor Scrawls:** While PP-OCRv3 handles neat-to-moderate handwriting, mixed print/script, and form notes, severely degraded cursive or overlapping strokes can still yield character substitutions or missed words.
2. **Over-Segmentation / Missed Faint Strokes:** Very faint pencil strokes or crossed-out words may receive low detection scores or be split into multiple fragments.
3. **No Semantic Hallucination by Design:** Because this phase uses an optical CTC recognizer without an ungrounded LLM rewriter, illegible glyphs produce low-confidence characters or empty output rather than fluent hallucinated sentences—which directly supports Phase 3 uncertainty detection.
