from __future__ import annotations

import re
import time
from typing import List, Optional, Sequence, Tuple
import cv2
import numpy as np
from PIL import Image, ImageOps

from app.schemas import (
    BoundingBox,
    RecognitionRegion,
    RegionQualityIndicators,
    UncertaintyCounts,
    UncertaintyLevel,
    UncertaintySummary,
)
from app.utils.config import UncertaintyConfig, get_uncertainty_config

_REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{3,}")
_REPEATED_PUNCT_PATTERN = re.compile(r"([^\w\s])\1{2,}")

_SEVERE_QUALITY_OR_PLAUSIBILITY_REASONS = {
    "blurry_region",
    "low_local_contrast",
    "faint_stroke_visibility",
    "excessive_non_alphanumeric_symbols",
    "suspicious_repeated_characters",
    "width_text_length_mismatch",
    "saturated_or_heavily_crossed_region",
    "excessive_image_noise",
}


class UncertaintyService:
    """
    Decoupled Phase 3 service that evaluates OCR region confidence alongside
    measurable local image quality and structural text plausibility to classify
    each region into HIGH, MEDIUM, LOW, or UNREADABLE reliability tiers.

    This service never modifies or fabricates OCR transcriptions.
    """

    def __init__(self, config: Optional[UncertaintyConfig] = None) -> None:
        self._config = config

    def _get_config(self) -> UncertaintyConfig:
        return self._config if self._config is not None else get_uncertainty_config()

    def analyze_uncertainty(
        self,
        image: Image.Image,
        ocr_regions: Sequence[RecognitionRegion],
    ) -> UncertaintySummary:
        """
        Compute region-level and document-level uncertainty metrics from the
        original PIL image and the list of detected OCR regions.
        """
        if image is None or image.width <= 0 or image.height <= 0:
            raise ValueError("Valid PIL Image is required for uncertainty analysis.")

        start_perf = time.perf_counter()
        config = self._get_config()

        gray_pil = ImageOps.grayscale(ImageOps.exif_transpose(image))
        gray_full = np.asarray(gray_pil, dtype=np.uint8)
        img_h, img_w = gray_full.shape[:2]

        if not ocr_regions:
            full_quality, full_reasons = self._compute_image_quality(
                crop=gray_full,
                bbox=None,
                region_type="full_image",
                config=config,
                require_bbox=False,
            )
            summary_reasons = ["no_text_regions_detected"] + [
                r for r in full_reasons if r not in ("missing_or_degenerate_bbox",)
            ]
            elapsed_ms = round((time.perf_counter() - start_perf) * 1000.0, 2)
            return UncertaintySummary(
                overall_level="UNREADABLE",
                mean_ocr_confidence=None,
                mean_normalized_confidence=None,
                mean_image_quality_score=full_quality.image_quality_score,
                total_regions=0,
                flagged_region_count=0,
                counts=UncertaintyCounts(HIGH=0, MEDIUM=0, LOW=0, UNREADABLE=0),
                review_recommended=True,
                annotated_text="",
                summary_reasons=summary_reasons,
                processing_time_ms=elapsed_ms,
                regions=[],
            )

        analyzed_regions: List[RecognitionRegion] = []
        counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNREADABLE": 0}
        raw_confidences: List[float] = []
        norm_confidences: List[float] = []
        quality_scores: List[float] = []
        all_reasons_ordered: List[str] = []
        annotated_lines: List[str] = []

        for idx, reg in enumerate(ocr_regions, start=1):
            crop, bbox_valid = self._extract_region_crop(gray_full, reg.bbox, img_w, img_h)
            quality_indicators, quality_reasons = self._compute_image_quality(
                crop=crop,
                bbox=reg.bbox,
                region_type=reg.region_type,
                config=config,
                require_bbox=True,
                bbox_valid=bbox_valid,
            )

            plausibility_score, plausibility_reasons = self._compute_text_plausibility(
                text=reg.text,
                bbox=reg.bbox if bbox_valid else None,
            )
            quality_indicators.plausibility_score = plausibility_score

            raw_conf = reg.ocr_confidence if reg.ocr_confidence is not None else reg.confidence

            level, norm_conf, reasons, needs_review = self._classify_region(
                text=reg.text,
                raw_conf=raw_conf,
                quality_indicators=quality_indicators,
                quality_reasons=quality_reasons,
                plausibility_reasons=plausibility_reasons,
                config=config,
            )

            updated_region = reg.model_copy(
                update={
                    "id": reg.id if reg.id >= 1 else idx,
                    "confidence": raw_conf,
                    "ocr_confidence": raw_conf,
                    "normalized_confidence": norm_conf,
                    "uncertainty_level": level,
                    "needs_review": needs_review,
                    "reasons": reasons,
                    "uncertainty_reasons": list(reasons),
                    "quality_indicators": quality_indicators,
                }
            )
            analyzed_regions.append(updated_region)

            counts[level] += 1
            if raw_conf is not None:
                raw_confidences.append(raw_conf)
            if norm_conf is not None:
                norm_confidences.append(norm_conf)
            quality_scores.append(quality_indicators.image_quality_score)

            for r in reasons:
                if r not in all_reasons_ordered:
                    all_reasons_ordered.append(r)

            annotated_lines.append(self._format_annotated_segment(reg.text, level))

        total_regions = len(analyzed_regions)
        flagged_count = sum(1 for r in analyzed_regions if r.needs_review)

        mean_ocr = (
            round(sum(raw_confidences) / len(raw_confidences), 4)
            if raw_confidences
            else None
        )
        mean_norm = (
            round(sum(norm_confidences) / len(norm_confidences), 4)
            if norm_confidences
            else None
        )
        mean_quality = (
            round(sum(quality_scores) / len(quality_scores), 4)
            if quality_scores
            else None
        )

        overall_level = self._determine_overall_level(counts, total_regions)
        review_recommended = flagged_count > 0 or overall_level != "HIGH"

        elapsed_ms = round((time.perf_counter() - start_perf) * 1000.0, 2)

        return UncertaintySummary(
            overall_level=overall_level,
            mean_ocr_confidence=mean_ocr,
            mean_normalized_confidence=mean_norm,
            mean_image_quality_score=mean_quality,
            total_regions=total_regions,
            flagged_region_count=flagged_count,
            counts=UncertaintyCounts(**counts),
            review_recommended=review_recommended,
            annotated_text="\n".join(annotated_lines),
            summary_reasons=all_reasons_ordered,
            processing_time_ms=elapsed_ms,
            regions=analyzed_regions,
        )

    @staticmethod
    def _extract_region_crop(
        gray_full: np.ndarray,
        bbox: Optional[BoundingBox],
        img_w: int,
        img_h: int,
    ) -> Tuple[np.ndarray, bool]:
        if bbox is None or bbox.width <= 0 or bbox.height <= 0:
            return gray_full, False

        x0 = max(0, min(img_w - 1, int(bbox.x_min)))
        y0 = max(0, min(img_h - 1, int(bbox.y_min)))
        x1 = max(x0 + 1, min(img_w, int(bbox.x_max)))
        y1 = max(y0 + 1, min(img_h, int(bbox.y_max)))

        crop = gray_full[y0:y1, x0:x1]
        if crop.size == 0:
            return gray_full, False
        return crop, True

    def _compute_image_quality(
        self,
        crop: np.ndarray,
        bbox: Optional[BoundingBox],
        region_type: str,
        config: UncertaintyConfig,
        require_bbox: bool = True,
        bbox_valid: bool = True,
    ) -> Tuple[RegionQualityIndicators, List[str]]:
        reasons: List[str] = []
        if require_bbox and not bbox_valid:
            reasons.append("missing_or_degenerate_bbox")

        h, w = crop.shape[:2]

        # 1. Sharpness via Variance of Laplacian
        laplacian = cv2.Laplacian(crop, cv2.CV_64F)
        laplacian_var = float(np.var(laplacian))

        # 2. Local contrast (RMS std dev and P95 - P5 dynamic range)
        rms_contrast = float(np.std(crop))
        p95 = float(np.percentile(crop, 95))
        p5 = float(np.percentile(crop, 5))
        dynamic_range = max(0.0, p95 - p5)

        # 3. Foreground/background stroke separation via Otsu thresholding
        if dynamic_range < 5.0:
            stroke_ratio = 0.0
            fg_bg_separation = 0.0
        else:
            _, binary_inv = cv2.threshold(
                crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            fg_mask = binary_inv > 0
            fg_fraction = float(np.mean(fg_mask))
            # Ink strokes are normally the minority class on background paper;
            # only invert if foreground covers nearly the entire crop (> 0.75).
            if fg_fraction > 0.75:
                fg_mask = ~fg_mask
                fg_fraction = float(np.mean(fg_mask))

            stroke_ratio = fg_fraction
            bg_mask = ~fg_mask
            if np.any(fg_mask) and np.any(bg_mask):
                fg_mean = float(np.mean(crop[fg_mask]))
                bg_mean = float(np.mean(crop[bg_mask]))
                fg_bg_separation = abs(bg_mean - fg_mean)
            else:
                fg_bg_separation = 0.0

        # 4. High-frequency residual noise estimate
        if min(h, w) >= 3:
            median_filtered = cv2.medianBlur(crop, 3)
            noise_level = float(
                np.mean(np.abs(crop.astype(np.float32) - median_filtered.astype(np.float32)))
            )
        else:
            noise_level = 0.0

        # Flag specific measurable image quality concerns
        if dynamic_range < config.low_contrast_range_threshold or rms_contrast < 12.0:
            reasons.append("low_local_contrast")

        if laplacian_var < config.blur_laplacian_threshold:
            reasons.append("blurry_region")

        if fg_bg_separation < config.faint_stroke_separation_threshold or stroke_ratio < 0.01:
            if "low_local_contrast" not in reasons:
                reasons.append("faint_stroke_visibility")

        if stroke_ratio > 0.60:
            reasons.append("saturated_or_heavily_crossed_region")

        if noise_level > config.high_noise_threshold:
            reasons.append("excessive_image_noise")

        geometry_penalty = 0.0
        if bbox is not None and bbox_valid:
            if bbox.height < 12 or bbox.width < 12 or (bbox.width * bbox.height) < 180:
                reasons.append("tiny_region_dimensions")
                geometry_penalty += 0.15
            elif bbox.height > 0 and (bbox.width / float(bbox.height)) < 0.30:
                reasons.append("abnormal_region_aspect_ratio")
                geometry_penalty += 0.10

        if region_type == "full_image_fallback":
            reasons.append("detector_fallback_region")
            geometry_penalty += 0.10

        sharpness_score = round(min(1.0, laplacian_var / 250.0), 4)
        contrast_score = round(min(1.0, dynamic_range / 140.0), 4)
        stroke_score = round(min(1.0, fg_bg_separation / 110.0), 4)
        if stroke_ratio < 0.01 or stroke_ratio > 0.60:
            stroke_score = round(stroke_score * 0.4, 4)

        noise_penalty = 0.15 if noise_level > config.high_noise_threshold else 0.0

        raw_quality = (
            0.40 * contrast_score
            + 0.35 * sharpness_score
            + 0.25 * stroke_score
            - geometry_penalty
            - noise_penalty
        )
        image_quality_score = round(max(0.0, min(1.0, raw_quality)), 4)

        indicators = RegionQualityIndicators(
            laplacian_variance=round(laplacian_var, 2),
            rms_contrast=round(rms_contrast, 2),
            dynamic_range=round(dynamic_range, 2),
            stroke_ratio=round(stroke_ratio, 4),
            fg_bg_separation=round(fg_bg_separation, 2),
            noise_level=round(noise_level, 2),
            sharpness_score=sharpness_score,
            contrast_score=contrast_score,
            image_quality_score=image_quality_score,
            plausibility_score=1.0,
        )
        return indicators, reasons

    @staticmethod
    def _compute_text_plausibility(
        text: str,
        bbox: Optional[BoundingBox],
    ) -> Tuple[float, List[str]]:
        reasons: List[str] = []
        stripped = (text or "").strip()
        if not stripped:
            return 0.0, ["empty_ocr_text"]

        non_space = [c for c in stripped if not c.isspace()]
        if not non_space:
            return 0.0, ["empty_ocr_text"]

        score = 1.0
        alnum_count = sum(1 for c in non_space if c.isalnum())
        alnum_ratio = alnum_count / float(len(non_space))

        if len(non_space) == 1:
            if alnum_count == 0:
                reasons.append("single_punctuation_fragment")
                score -= 0.85
            else:
                reasons.append("very_short_ocr_token")
                score -= 0.30
        else:
            if alnum_count == 0:
                reasons.append("non_alphanumeric_only")
                score -= 0.85
            elif alnum_ratio < 0.45:
                reasons.append("excessive_non_alphanumeric_symbols")
                score -= 0.45
            elif alnum_ratio < 0.70 and len(non_space) >= 3:
                reasons.append("elevated_symbol_noise")
                score -= 0.20

        if _REPEATED_CHAR_PATTERN.search(stripped) or _REPEATED_PUNCT_PATTERN.search(stripped):
            reasons.append("suspicious_repeated_characters")
            score -= 0.40

        if bbox is not None and bbox.width > 0 and bbox.height > 0:
            aspect = bbox.width / float(bbox.height)
            if bbox.width >= 140 and aspect >= 3.5 and len(non_space) <= 2:
                reasons.append("width_text_length_mismatch")
                score -= 0.35
            elif len(non_space) >= 5 and (bbox.width / float(len(non_space))) < 3.5:
                reasons.append("cramped_character_density")
                score -= 0.20

        return round(max(0.0, min(1.0, score)), 4), reasons

    @staticmethod
    def _classify_region(
        text: str,
        raw_conf: Optional[float],
        quality_indicators: RegionQualityIndicators,
        quality_reasons: List[str],
        plausibility_reasons: List[str],
        config: UncertaintyConfig,
    ) -> Tuple[UncertaintyLevel, Optional[float], List[str], bool]:
        reasons: List[str] = []
        stripped = (text or "").strip()

        # 1. OCR confidence signal evaluation
        if raw_conf is None:
            reasons.append("missing_ocr_confidence")
        elif raw_conf < config.unreadable_confidence_threshold:
            reasons.append("very_low_ocr_confidence")
        elif raw_conf < config.low_confidence_threshold:
            reasons.append("low_ocr_confidence")
        elif raw_conf < config.high_confidence_threshold:
            reasons.append("moderate_ocr_confidence")

        # Append image-quality and plausibility reasons without duplicates
        for r in quality_reasons + plausibility_reasons:
            if r not in reasons:
                reasons.append(r)

        img_q = quality_indicators.image_quality_score
        plaus_q = quality_indicators.plausibility_score

        # 2. Compute composite normalized reliability score where evidence exists
        if not stripped:
            normalized_confidence: Optional[float] = 0.0
        elif raw_conf is None:
            normalized_confidence = None
        else:
            normalized_confidence = round(
                max(0.0, min(1.0, 0.60 * raw_conf + 0.25 * img_q + 0.15 * plaus_q)),
                4,
            )

        # 3. Classify into UNREADABLE, LOW, MEDIUM, or HIGH
        unreadable_reasons = {
            "empty_ocr_text",
            "non_alphanumeric_only",
            "single_punctuation_fragment",
        }
        has_unreadable_reason = any(r in unreadable_reasons for r in reasons)
        severe_reason_count = sum(
            1 for r in reasons if r in _SEVERE_QUALITY_OR_PLAUSIBILITY_REASONS
        )

        if (
            has_unreadable_reason
            or (raw_conf is not None and raw_conf < config.unreadable_confidence_threshold)
            or (
                normalized_confidence is not None
                and normalized_confidence < config.unreadable_reliability_threshold
            )
            or (img_q < 0.20 and (raw_conf is None or raw_conf < 0.65))
            or (plaus_q < 0.25 and (raw_conf is None or raw_conf < 0.70))
        ):
            level: UncertaintyLevel = "UNREADABLE"
        elif (
            raw_conf is None
            or raw_conf < config.low_confidence_threshold
            or (
                normalized_confidence is not None
                and normalized_confidence < config.low_reliability_threshold
            )
            or img_q < 0.42
            or plaus_q < 0.55
            or severe_reason_count >= 2
            or (severe_reason_count >= 1 and raw_conf < 0.88)
        ):
            level = "LOW"
        elif (
            raw_conf < config.high_confidence_threshold
            or (
                normalized_confidence is not None
                and normalized_confidence < config.high_reliability_threshold
            )
            or len(reasons) > 0
        ):
            level = "MEDIUM"
        else:
            level = "HIGH"

        needs_review = level != "HIGH"
        return level, normalized_confidence, reasons, needs_review

    @staticmethod
    def _determine_overall_level(
        counts: dict[str, int],
        total_regions: int,
    ) -> UncertaintyLevel:
        if total_regions <= 0:
            return "UNREADABLE"
        if counts["UNREADABLE"] == total_regions:
            return "UNREADABLE"
        if counts["UNREADABLE"] > 0 or counts["LOW"] > 0:
            return "LOW"
        if counts["MEDIUM"] > 0:
            return "MEDIUM"
        return "HIGH"

    @staticmethod
    def _format_annotated_segment(text: str, level: UncertaintyLevel) -> str:
        cleaned = (text or "").strip()
        if level == "HIGH":
            return cleaned
        if level == "MEDIUM":
            return f"[{cleaned}?]"
        if level == "LOW":
            return f"[{cleaned}? (LOW CONFIDENCE)]"
        return f"[{cleaned or 'UNREADABLE'}? (UNREADABLE)]"


def analyze_uncertainty(
    image: Image.Image,
    ocr_regions: Sequence[RecognitionRegion],
    config: Optional[UncertaintyConfig] = None,
) -> UncertaintySummary:
    """
    Convenience functional interface for Phase 3 uncertainty analysis.
    """
    service = UncertaintyService(config=config)
    return service.analyze_uncertainty(image=image, ocr_regions=ocr_regions)
