from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable, List, Optional, Tuple
import numpy as np
from PIL import Image
from app.schemas import BoundingBox, RecognitionRegion, RecognitionResult


class OCRModelUnavailableError(RuntimeError):
    """Raised when the underlying OCR/HTR model runtime cannot be initialized."""


class OCRExecutionError(RuntimeError):
    """Raised when the OCR/HTR engine fails during image recognition."""


@dataclass
class OCRServiceOutput:
    """Container combining the structured RecognitionResult with any engine warnings."""

    result: RecognitionResult
    warnings: List[str] = field(default_factory=list)


class HandwritingOCRService:
    """
    Modular handwriting and document text recognition service backed by
    RapidOCR (PP-OCRv4 detection + direction classification + SVTR/CRNN recognition
    on ONNX Runtime CPU).
    """

    ENGINE_NAME = "rapidocr-onnxruntime (PP-OCRv3)"

    def __init__(self, engine_factory: Optional[Callable[[], Any]] = None) -> None:
        self._engine_factory = engine_factory
        self._engine: Optional[Any] = None

    def _get_engine(self) -> Any:
        """Lazily initialize and cache the ONNX Runtime OCR engine."""
        if self._engine is not None:
            return self._engine

        try:
            if self._engine_factory is not None:
                self._engine = self._engine_factory()
            else:
                from rapidocr_onnxruntime import RapidOCR

                self._engine = RapidOCR()
            return self._engine
        except Exception as exc:
            raise OCRModelUnavailableError(
                "Recognition engine model could not be initialized."
            ) from exc

    def recognize(
        self,
        image: Image.Image,
        original_size: Optional[Tuple[int, int]] = None,
    ) -> RecognitionResult:
        """
        Run recognition and return the structured RecognitionResult directly.
        """
        return self.recognize_with_warnings(image=image, original_size=original_size).result

    def recognize_with_warnings(
        self,
        image: Image.Image,
        original_size: Optional[Tuple[int, int]] = None,
    ) -> OCRServiceOutput:
        """
        Perform text region detection and recognition on a validated PIL Image.

        Args:
            image: Preprocessed (or original) PIL Image.
            original_size: Optional (width, height) of the original uploaded image
                so bounding boxes are mapped back to original pixel coordinates.

        Returns:
            OCRServiceOutput containing RecognitionResult and non-fatal warnings.
        """
        if image is None or image.width <= 0 or image.height <= 0:
            raise ValueError("Invalid image supplied to recognition service.")

        engine = self._get_engine()
        warnings: List[str] = []

        rgb_image = image.convert("RGB") if image.mode != "RGB" else image
        img_array = np.asarray(rgb_image, dtype=np.uint8)
        proc_w, proc_h = rgb_image.width, rgb_image.height
        orig_w, orig_h = original_size if original_size else (proc_w, proc_h)

        scale_x = float(orig_w) / float(proc_w) if proc_w > 0 else 1.0
        scale_y = float(orig_h) / float(proc_h) if proc_h > 0 else 1.0

        start_perf = time.perf_counter()
        try:
            raw_output, _elapse = engine(img_array)
        except OCRModelUnavailableError:
            raise
        except Exception as exc:
            raise OCRExecutionError(
                "Recognition engine encountered an error while processing the image."
            ) from exc

        regions: List[RecognitionRegion] = []

        if raw_output:
            regions = self._parse_detected_regions(
                raw_output=raw_output,
                scale_x=scale_x,
                scale_y=scale_y,
                orig_w=orig_w,
                orig_h=orig_h,
            )
        elif float(np.std(img_array)) > 8.0 and proc_h <= 260:
            # Fallback for tightly cropped single-line handwriting where page detector finds no box
            try:
                fallback_output, _ = engine(
                    img_array,
                    use_det=False,
                    use_cls=False,
                    use_rec=True,
                )
                regions = self._parse_fallback_recognition(
                    fallback_output=fallback_output,
                    orig_w=orig_w,
                    orig_h=orig_h,
                )
                if regions:
                    warnings.append(
                        "Page-level text detector found no bounding boxes; applied single-line recognition fallback."
                    )
            except Exception:
                # Non-fatal fallback attempt
                pass

        elapsed_ms = round((time.perf_counter() - start_perf) * 1000.0, 2)

        if not regions:
            warnings.append("No legible text or handwriting regions were detected in the image.")
            return OCRServiceOutput(
                result=RecognitionResult(
                    text="",
                    engine=self.ENGINE_NAME,
                    processing_time_ms=elapsed_ms,
                    confidence=None,
                    regions=[],
                ),
                warnings=warnings,
            )

        # Sort regions top-to-bottom (grouped by approximate line band) then left-to-right
        regions.sort(
            key=lambda r: (
                (r.bbox.y_min // max(12, int(r.bbox.height * 0.5))) if r.bbox else 0,
                r.bbox.x_min if r.bbox else 0,
            )
        )

        # Re-index region IDs sequentially after sorting
        valid_confidences: List[float] = []
        text_lines: List[str] = []
        for idx, region in enumerate(regions, start=1):
            region.id = idx
            if region.text:
                text_lines.append(region.text)
            if region.confidence is not None:
                valid_confidences.append(region.confidence)

        mean_confidence: Optional[float] = None
        if valid_confidences:
            mean_confidence = round(sum(valid_confidences) / len(valid_confidences), 4)
            if mean_confidence < 0.65:
                warnings.append(
                    f"Low overall recognition confidence ({mean_confidence:.2f}); image may contain difficult or degraded handwriting."
                )

        full_text = "\n".join(text_lines)

        return OCRServiceOutput(
            result=RecognitionResult(
                text=full_text,
                engine=self.ENGINE_NAME,
                processing_time_ms=elapsed_ms,
                confidence=mean_confidence,
                regions=regions,
            ),
            warnings=warnings,
        )

    def _parse_detected_regions(
        self,
        raw_output: List[Any],
        scale_x: float,
        scale_y: float,
        orig_w: int,
        orig_h: int,
    ) -> List[RecognitionRegion]:
        regions: List[RecognitionRegion] = []
        for idx, item in enumerate(raw_output, start=1):
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            raw_box, raw_text, raw_score = item[0], item[1], item[2]
            text = str(raw_text).strip() if raw_text is not None else ""
            if not text:
                continue

            confidence = self._parse_confidence(raw_score)
            bbox = self._build_bounding_box(raw_box, scale_x, scale_y, orig_w, orig_h)

            regions.append(
                RecognitionRegion(
                    id=idx,
                    text=text,
                    confidence=confidence,
                    bbox=bbox,
                    region_type="line",
                )
            )
        return regions

    def _parse_fallback_recognition(
        self,
        fallback_output: Any,
        orig_w: int,
        orig_h: int,
    ) -> List[RecognitionRegion]:
        if not fallback_output or not isinstance(fallback_output, (list, tuple)):
            return []
        first = fallback_output[0]
        if not isinstance(first, (list, tuple)) or len(first) < 2:
            return []
        raw_text, raw_score = first[0], first[1]
        text = str(raw_text).strip() if raw_text is not None else ""
        confidence = self._parse_confidence(raw_score)
        if not text or (confidence is not None and confidence < 0.35):
            return []

        bbox = BoundingBox(
            x_min=0,
            y_min=0,
            x_max=orig_w,
            y_max=orig_h,
            width=orig_w,
            height=orig_h,
            polygon=[[0, 0], [orig_w, 0], [orig_w, orig_h], [0, orig_h]],
        )
        return [
            RecognitionRegion(
                id=1,
                text=text,
                confidence=confidence,
                bbox=bbox,
                region_type="full_image_fallback",
            )
        ]

    @staticmethod
    def _parse_confidence(raw_score: Any) -> Optional[float]:
        if raw_score is None:
            return None
        try:
            val = float(raw_score)
            if np.isnan(val):
                return None
            return round(max(0.0, min(1.0, val)), 4)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_bounding_box(
        raw_box: Any,
        scale_x: float,
        scale_y: float,
        orig_w: int,
        orig_h: int,
    ) -> Optional[BoundingBox]:
        if not isinstance(raw_box, (list, tuple)) or len(raw_box) < 4:
            return None
        try:
            polygon: List[List[int]] = []
            xs: List[int] = []
            ys: List[int] = []
            for pt in raw_box[:4]:
                px = int(round(float(pt[0]) * scale_x))
                py = int(round(float(pt[1]) * scale_y))
                px = max(0, min(orig_w, px))
                py = max(0, min(orig_h, py))
                polygon.append([px, py])
                xs.append(px)
                ys.append(py)

            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            return BoundingBox(
                x_min=x_min,
                y_min=y_min,
                x_max=x_max,
                y_max=y_max,
                width=max(0, x_max - x_min),
                height=max(0, y_max - y_min),
                polygon=polygon,
            )
        except (TypeError, ValueError, IndexError):
            return None
