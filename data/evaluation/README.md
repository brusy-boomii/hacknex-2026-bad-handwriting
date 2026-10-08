# Evaluation Dataset Format (`data/evaluation/`)

**Project:** HNX26EPS04 — Extreme Bad-Handwriting Digitizing Stack

This directory holds ground-truth evaluation pairs used by `scripts/evaluate_recognition.py` to compute real **Character Error Rate (CER)** and **Word Error Rate (WER)**.

> **Integrity Rule:** Never place synthetic/fabricated metrics in this folder or claim random internet images as the team's evaluation benchmark. Only genuine handwritten samples with human-verified ground truth should be added here.

---

## Supported Directory Layouts

`scripts/evaluate_recognition.py` supports two convenient layouts inside `data/evaluation/`:

### Option A: Per-Sample Subdirectory (Recommended for Rich Metadata)
```text
data/evaluation/
└── sample_001/
    ├── image.png            # (or .jpg, .jpeg, .tiff, .tif, .bmp)
    ├── ground_truth.txt     # Exact human-transcribed ground truth text (UTF-8)
    └── metadata.json        # Optional: handwriting difficulty tags
```

### Option B: Paired Flat Files
```text
data/evaluation/
├── doctor_note_01.jpg
├── doctor_note_01.ground_truth.txt   # (or doctor_note_01.txt)
```

---

## Optional `metadata.json` Schema
To evaluate across difficult handwriting categories (cramped writing, inconsistent spacing, crossed-out words, margin notes, poor image quality, mixed scripts), each sample folder may include an optional `metadata.json`:

```json
{
  "sample_id": "sample_001",
  "writer_id": "writer_a",
  "conditions": [
    "cramped_writing",
    "inconsistent_spacing",
    "crossed_out_words",
    "margin_notes",
    "poor_image_quality"
  ],
  "script": "latin",
  "notes": "Handwritten lecture margin note photographed under low light"
}
```

---

## Running the Evaluation Script

From the repository root:

```powershell
backend\.venv\Scripts\python.exe scripts\evaluate_recognition.py
```

If no ground-truth samples are present in `data/evaluation/`, the script honestly reports that no evaluation dataset is available and outputs zero fabricated metrics.
