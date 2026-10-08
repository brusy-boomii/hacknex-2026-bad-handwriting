"""
Baseline Evaluation Script for HNX26EPS04 — Extreme Bad-Handwriting Digitizing Stack.

Computes real Character Error Rate (CER) and Word Error Rate (WER) on genuine
handwriting samples stored in `data/evaluation/`.

If no ground-truth dataset is present in `data/evaluation/`, the script reports
that evaluation data is unavailable and exits cleanly without fabricating metrics.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


@dataclass
class EvaluationPair:
    sample_id: str
    image_path: Path
    ground_truth_path: Path
    metadata_path: Optional[Path] = None


@dataclass
class SampleEvaluationResult:
    sample_id: str
    image_file: str
    reference_text: str
    recognized_text: str
    cer: float
    wer: float
    confidence: Optional[float]
    processing_time_ms: float
    region_count: int


def _levenshtein_distance(seq_a: Sequence[object], seq_b: Sequence[object]) -> int:
    """Compute exact Levenshtein edit distance between two sequences."""
    len_a = len(seq_a)
    len_b = len(seq_b)
    if len_a == 0:
        return len_b
    if len_b == 0:
        return len_a

    prev_row = list(range(len_b + 1))
    for i, item_a in enumerate(seq_a, start=1):
        curr_row = [i] + [0] * len_b
        for j, item_b in enumerate(seq_b, start=1):
            cost = 0 if item_a == item_b else 1
            curr_row[j] = min(
                curr_row[j - 1] + 1,       # insertion
                prev_row[j] + 1,           # deletion
                prev_row[j - 1] + cost,    # substitution
            )
        prev_row = curr_row
    return prev_row[len_b]


def calculate_cer(reference: str, hypothesis: str) -> float:
    """
    Calculate Character Error Rate (CER) = EditDistance(ref_chars, hyp_chars) / len(ref_chars).
    Whitespace is normalized (collapsed to single spaces and stripped).
    """
    ref_norm = " ".join(reference.split())
    hyp_norm = " ".join(hypothesis.split())
    if not ref_norm:
        return 0.0 if not hyp_norm else 1.0
    distance = _levenshtein_distance(list(ref_norm), list(hyp_norm))
    return round(distance / len(ref_norm), 4)


def calculate_wer(reference: str, hypothesis: str) -> float:
    """
    Calculate Word Error Rate (WER) = EditDistance(ref_words, hyp_words) / len(ref_words).
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    distance = _levenshtein_distance(ref_words, hyp_words)
    return round(distance / len(ref_words), 4)


def discover_evaluation_samples(eval_dir: Path) -> List[EvaluationPair]:
    """
    Discover valid (image, ground_truth.txt) evaluation pairs inside `eval_dir`.
    Supports both:
      1. Subdirectory layout: `eval_dir/<sample_id>/image.<ext>` + `ground_truth.txt`
      2. Flat file layout: `eval_dir/<stem>.<ext>` + `<stem>.ground_truth.txt` (or `<stem>.txt`)
    """
    if not eval_dir.exists() or not eval_dir.is_dir():
        return []

    pairs: List[EvaluationPair] = []

    # 1. Check subdirectories
    for item in sorted(eval_dir.iterdir()):
        if item.is_dir():
            gt_file = item / "ground_truth.txt"
            if not gt_file.is_file():
                continue
            image_candidates = [
                p for p in sorted(item.iterdir())
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            ]
            if image_candidates:
                meta_file = item / "metadata.json"
                pairs.append(
                    EvaluationPair(
                        sample_id=item.name,
                        image_path=image_candidates[0],
                        ground_truth_path=gt_file,
                        metadata_path=meta_file if meta_file.is_file() else None,
                    )
                )

    # 2. Check flat files in eval_dir
    for img_path in sorted(eval_dir.iterdir()):
        if not img_path.is_file() or img_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        stem = img_path.stem
        gt_candidates = [
            eval_dir / f"{stem}.ground_truth.txt",
            eval_dir / f"{stem}.gt.txt",
            eval_dir / f"{stem}.txt",
        ]
        for gt_candidate in gt_candidates:
            if gt_candidate.is_file():
                pairs.append(
                    EvaluationPair(
                        sample_id=stem,
                        image_path=img_path,
                        ground_truth_path=gt_candidate,
                    )
                )
                break

    return pairs


def run_evaluation(eval_dir: Path, output_json: Optional[Path] = None) -> Tuple[int, List[SampleEvaluationResult]]:
    """
    Run recognition evaluation on all discovered samples in `eval_dir`.
    Returns (exit_code, results).
    """
    pairs = discover_evaluation_samples(eval_dir)
    if not pairs:
        print(
            f"[INFO] No ground-truth evaluation samples found in '{eval_dir}'.\n"
            "       Add genuine handwriting images with matching 'ground_truth.txt' files\n"
            "       (see data/evaluation/README.md). No metrics were calculated or fabricated."
        )
        return 0, []

    from app.services.preprocessing import PreprocessingService
    from app.services.handwriting_ocr import HandwritingOCRService

    preprocessing_service = PreprocessingService()
    ocr_service = HandwritingOCRService()

    results: List[SampleEvaluationResult] = []
    for pair in pairs:
        raw_bytes = pair.image_path.read_bytes()
        reference_text = pair.ground_truth_path.read_text(encoding="utf-8").strip()

        prepared = preprocessing_service.prepare_for_pipeline(raw_bytes)
        recognition = ocr_service.recognize(
            prepared.recognition_image,
            original_size=(prepared.metadata.width, prepared.metadata.height),
        )

        cer = calculate_cer(reference_text, recognition.text)
        wer = calculate_wer(reference_text, recognition.text)

        sample_result = SampleEvaluationResult(
            sample_id=pair.sample_id,
            image_file=pair.image_path.name,
            reference_text=reference_text,
            recognized_text=recognition.text,
            cer=cer,
            wer=wer,
            confidence=recognition.confidence,
            processing_time_ms=recognition.processing_time_ms,
            region_count=len(recognition.regions),
        )
        results.append(sample_result)
        print(
            f"[{sample_result.sample_id}] CER={sample_result.cer:.4f} | "
            f"WER={sample_result.wer:.4f} | "
            f"Time={sample_result.processing_time_ms:.1f}ms | "
            f"Regions={sample_result.region_count}"
        )

    mean_cer = round(sum(r.cer for r in results) / len(results), 4)
    mean_wer = round(sum(r.wer for r in results) / len(results), 4)
    print("-" * 60)
    print(f"Evaluated {len(results)} sample(s) | Mean CER: {mean_cer:.4f} | Mean WER: {mean_wer:.4f}")

    if output_json:
        summary = {
            "sample_count": len(results),
            "mean_cer": mean_cer,
            "mean_wer": mean_wer,
            "samples": [asdict(r) for r in results],
        }
        output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Saved evaluation report to {output_json}")

    return 0, results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate handwriting recognition CER/WER on data/evaluation/."
    )
    parser.add_argument(
        "--eval-dir",
        type=Path,
        default=REPO_ROOT / "data" / "evaluation",
        help="Path to evaluation dataset directory (default: data/evaluation).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write JSON evaluation summary.",
    )
    args = parser.parse_args()
    exit_code, _ = run_evaluation(args.eval_dir, args.output)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
