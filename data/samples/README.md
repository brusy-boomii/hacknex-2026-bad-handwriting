# Handwriting Demo Samples Guide (`data/samples/`)

**Project:** HNX26EPS04 — Extreme Bad-Handwriting Digitizing Stack

This directory is reserved for genuine handwritten document images used for local interactive testing and live hackathon demonstrations.

---

## How to Add Genuine Team Handwriting Samples

1. **Capture Real Difficult Handwriting:**
   Write on physical paper (lined, unlined, prescription pad, or sticky note) and photograph or scan the page. Include realistic challenges required by HACKNEX 2026:
   - **Cramped writing** and squeezed inter-line additions
   - **Inconsistent word/character spacing** and variable slant
   - **Crossed-out or overwritten words**
   - **Margin notes** and angled annotations
   - **Poor lighting / shadows / low contrast**
   - **Mixed alphanumeric codes, punctuation, or scripts**

2. **Supported File Formats:**
   Save images in `data/samples/` as `.png`, `.jpg`, `.jpeg`, `.tiff`, `.tif`, or `.bmp` (up to `10 MB` by default).

3. **Test via the Web UI or CLI:**
   - **Web UI:** Drag and drop any image from `data/samples/` into the upload zone at `http://localhost:5173`.
   - **CLI / API:**
     ```powershell
     curl.exe -X POST "http://127.0.0.1:8000/analyze" -F "file=@data/samples/your_sample.jpg;type=image/jpeg"
     ```
   - **Promote to Evaluation Set:** To measure CER and WER on a sample, copy the image into `data/evaluation/<sample_name>/image.jpg` alongside a human-verified `ground_truth.txt` file and run `scripts/evaluate_recognition.py`.
