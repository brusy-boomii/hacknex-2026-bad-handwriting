# Phase 3 Architecture: Confidence-Aware Uncertainty Detection

**Project:** HNX26EPS04 — Extreme Bad-Handwriting Digitizing Stack  
**Event:** HACKNEX 2026  
**Phase:** 3 (Multi-Signal Confidence Calibration & Uncertainty Detection)

---

## 1. Why Raw OCR Confidence Alone Is Insufficient

Optical sequence recognizers (such as the SVTR/CRNN CTC head inside PP-OCRv3) compute character probabilities over localized image crops. Relying solely on raw OCR softmax confidence fails on extreme bad handwriting for four documented reasons:
1. **CTC Overconfidence on Degraded Crops:** A blurry smudge, crossed-out stroke, or paper crease can closely match a punctuation mark or short character pattern, producing a high softmax probability (`> 0.75`) on garbage output (e.g., `"||||"`, `"..."`).
2. **Blindness to Local Image Degradation:** Raw OCR confidence does not directly report whether the underlying crop suffered from motion blur, washed-out lighting, or heavy background grain.
3. **Segmentation & Geometry Mismatches:** When a text detector groups a wide handwritten phrase into a bounding box (`width = 240px`) but the recognizer only decodes 1–2 characters due to faint ink, the confidence of those 1–2 characters may still appear moderate even though most of the region was missed.
4. **Silent Failure Risk:** Downstream clinical, archival, or legal workflows require knowing *which* specific regions are untrustworthy and *why*, rather than receiving an undifferentiated text block.

---

## 2. Multi-Signal Uncertainty Pipeline (`UncertaintyService`)

Implemented in `backend/app/services/uncertainty.py`, `UncertaintyService` is strictly decoupled from the OCR engine. It accepts the **original validated image** and the **list of detected `RecognitionRegion` objects** and evaluates three orthogonal families of evidence for every region:

```text
Original Image + PP-OCRv3 Regions
                │
                ├──► [Signal 1: Raw OCR Engine Confidence]
                │      - PP-OCRv3 CTC/softmax score in [0.0, 1.0] (or null)
                │
                ├──► [Signal 2: Local Image Quality Analysis (OpenCV + NumPy)]
                │      - Sharpness: Variance of 2D Laplacian (cv2.Laplacian)
                │      - Local Contrast: P95 - P5 intensity range & RMS std dev
                │      - Stroke Visibility: Otsu foreground/background separation & stroke ratio
                │      - Noise: Mean absolute residual against 3x3 median filter
                │      - Geometry: Tiny dimension check, aspect ratio, fallback region check
                │
                └──► [Signal 3: Structural Text Plausibility]
                       - Empty / whitespace-only detection
                       - Alphanumeric vs. non-alphanumeric symbol ratio
                       - Repeated character / punctuation run detection
                       - Region width vs. character count density consistency
                │
                ▼
[Transparent Reliability Scoring & Classification]
  - Calibrated normalized_confidence in [0.0, 1.0] (when OCR confidence is present)
  - Tier classification: HIGH | MEDIUM | LOW | UNREADABLE
  - Explainable reason codes + needs_review boolean
```

---

## 3. Exact Mathematical Formulation & Thresholds

### 3.1 Local Image Quality Score (`image_quality_score` $\in [0.0, 1.0]$)
For each region's bounding box crop on the grayscale original image:
- **Sharpness Score:** $\text{sharpness\_score} = \min(1.0,\ \text{Var}(\nabla^2 I) / 250.0)$
- **Contrast Score:** $\text{contrast\_score} = \min(1.0,\ (P_{95}(I) - P_{5}(I)) / 140.0)$
- **Stroke Visibility Score:** $\text{stroke\_score} = \min(1.0,\ |\mu_{\text{bg}} - \mu_{\text{fg}}| / 110.0)$ (attenuated by $0.4\times$ if foreground stroke fraction $< 1\%$ or $> 60\%$)
- **Composite Image Quality:**
  $$\text{image\_quality\_score} = \text{clip}_{[0,1]}\left(0.40 \cdot \text{contrast\_score} + 0.35 \cdot \text{sharpness\_score} + 0.25 \cdot \text{stroke\_score} - P_{\text{geom}} - P_{\text{noise}}\right)$$

### 3.2 Structural Plausibility Score (`plausibility_score` $\in [0.0, 1.0]$)
Starts at $1.0$ and applies deterministic deductions for structural anomalies:
- Empty text: $\rightarrow 0.0$ (`empty_ocr_text`)
- Single non-alphanumeric symbol: $-0.85$ (`single_punctuation_fragment`)
- Non-alphanumeric only: $-0.85$ (`non_alphanumeric_only`)
- Alphanumeric ratio $< 0.45$: $-0.45$ (`excessive_non_alphanumeric_symbols`)
- Repeated character/symbol runs ($\ge 4$ identical chars or $\ge 3$ punctuation chars): $-0.40$ (`suspicious_repeated_characters`)
- Wide box ($\ge 140\text{px}$, aspect $\ge 3.5$) with $\le 2$ characters: $-0.35$ (`width_text_length_mismatch`)

### 3.3 Calibrated Reliability Score (`normalized_confidence`)
- If `ocr_confidence` is `null` (unavailable from engine), `normalized_confidence` remains `null`—the service never fabricates a numeric score without primary optical evidence.
- When `ocr_confidence` is available:
  $$\text{normalized\_confidence} = 0.60 \cdot \text{ocr\_confidence} + 0.25 \cdot \text{image\_quality\_score} + 0.15 \cdot \text{plausibility\_score}$$

### 3.4 Configurable Classification Thresholds (`backend/app/utils/config.py`)

| Tier | Meaning | Classification Rule | `needs_review` |
| :--- | :--- | :--- | :--- |
| **`HIGH`** | Strong optical confidence and clean local image & text signals | `ocr_confidence >= 0.82` AND `normalized_confidence >= 0.78` AND `0` warning reasons | `false` |
| **`MEDIUM`** | Usable recognition with minor warning signals or moderate confidence | `ocr_confidence >= 0.60` AND `normalized_confidence >= 0.62` with moderate confidence or minor non-severe warning | `true` |
| **`LOW`** | Weak OCR confidence or significant blur, low contrast, or plausibility warnings | `ocr_confidence < 0.60` OR `normalized_confidence < 0.62` OR `ocr_confidence is null` OR severe quality/plausibility warning | `true` |
| **`UNREADABLE`** | Insufficient evidence for trustworthy recognition | Empty/symbol-only text OR `ocr_confidence < 0.35` OR `normalized_confidence < 0.38` OR severe degradation (`image_quality < 0.20` with low confidence) | `true` |

---

## 4. Why Uncertain Text Is Never Silently Corrected

A core architectural principle of HNX26EPS04 (see `GEMINI.md` Rule #2) is **flagging uncertainty rather than hallucinating fluency**.
- In Phase 3, `recognition.text` and each `region.text` always preserve the exact optical recognizer output.
- Alongside raw text, `uncertainty.annotated_text` and the frontend transcription view explicitly mark uncertain segments (e.g., `"[headache? (LOW CONFIDENCE)]"`) together with their machine-verifiable reason codes (`low_ocr_confidence`, `blurry_region`, `low_local_contrast`).
- Users can click any region in the UI to inspect its evidence and manually enter a verified human correction.

---

## 5. Current Scope & Phase 4 Boundary

- **Implemented in Phase 3:** Multi-signal region uncertainty scoring, local OpenCV image quality indicators, structural plausibility checks, `HIGH`/`MEDIUM`/`LOW`/`UNREADABLE` classification, SVG bounding-box overlays on the original document, uncertainty-aware transcription view, and local human-in-the-loop region review/editing.
- **Not Yet Implemented (Scheduled for Phase 4):** Contextual VLM/LLM selective verification, secondary candidate generation for `LOW`/`UNREADABLE` regions, and persistent verification audit export.
