from dataclasses import dataclass, field
import io
from typing import List
import numpy as np
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
from app.schemas import ImageMetadata, PreprocessingMetadata

MAX_IMAGE_PIXELS = 40_000_000  # 40 megapixels safety cap
MAX_RECOGNITION_DIMENSION = 2400
MIN_RECOGNITION_HEIGHT = 48


@dataclass
class PreparedImageBundle:
    """
    Holds both the original validated PIL image and the recognition-ready PIL image,
    along with structured metadata and any non-fatal preprocessing warnings.
    """

    original_image: Image.Image
    recognition_image: Image.Image
    metadata: ImageMetadata
    preprocessing: PreprocessingMetadata
    warnings: List[str] = field(default_factory=list)


class PreprocessingService:
    """
    Service for image loading, structural validation, and handwriting-safe
    preprocessing prior to optical recognition.
    """

    def validate_and_get_info(self, image_bytes: bytes) -> ImageMetadata:
        """
        Loads the image from raw bytes, verifies both header and pixel stream
        integrity, and returns typed ImageMetadata.

        Raises:
            ValueError: If the payload is empty, corrupt, excessively large in pixel
                dimensions, or not a readable image.
        """
        bundle = self.prepare_for_pipeline(image_bytes)
        return bundle.metadata

    def prepare_for_pipeline(self, image_bytes: bytes) -> PreparedImageBundle:
        """
        Validates raw image bytes, preserves the original image, and produces a
        recognition-ready image using non-destructive handwriting-safe steps:
          1. Header & full pixel stream decoding verification
          2. EXIF orientation normalization
          3. Aspect-ratio-preserving resize for extreme dimensions
          4. Grayscale conversion & gentle contrast normalization
          5. Light denoising only when background noise warrants it
        """
        if not image_bytes:
            raise ValueError("Uploaded image payload is empty.")

        try:
            with Image.open(io.BytesIO(image_bytes)) as img_verify:
                img_verify.verify()

            with Image.open(io.BytesIO(image_bytes)) as opened:
                opened.load()
                if not opened.format or opened.width <= 0 or opened.height <= 0:
                    raise ValueError("Image has invalid dimensions or unknown format.")

                total_pixels = opened.width * opened.height
                if total_pixels > MAX_IMAGE_PIXELS:
                    raise ValueError(
                        f"Image resolution ({opened.width}x{opened.height} = {total_pixels:,} pixels) "
                        f"exceeds maximum safe limit ({MAX_IMAGE_PIXELS:,} pixels)."
                    )

                detected_format = opened.format
                detected_mode = opened.mode
                detected_channels = len(opened.getbands())
                original_copy = opened.copy()
        except ValueError:
            raise
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
            raise ValueError("Uploaded file contains corrupt or unreadable image data.") from exc
        except Exception as exc:
            raise ValueError("Uploaded file could not be decoded as a valid image.") from exc

        warnings: List[str] = []
        operations: List[str] = []

        # 1. EXIF orientation handling
        work_img = ImageOps.exif_transpose(original_copy)
        if work_img.size != original_copy.size:
            operations.append("exif_orientation_transpose")

        orig_w, orig_h = work_img.size

        if orig_w < 32 or orig_h < 16:
            warnings.append(
                f"Image dimensions ({orig_w}x{orig_h}px) are very small; recognition accuracy may be degraded."
            )

        # 2. Composite alpha channel onto white background if RGBA / LA / P
        if work_img.mode in ("RGBA", "LA") or (work_img.mode == "P" and "transparency" in work_img.info):
            rgba = work_img.convert("RGBA")
            white_bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            work_img = Image.alpha_composite(white_bg, rgba).convert("RGB")
            operations.append("alpha_white_background_composite")
        elif work_img.mode != "RGB" and work_img.mode != "L":
            work_img = work_img.convert("RGB")
            operations.append("convert_to_rgb")

        # 3. Aspect-ratio-preserving resize for very large or very tiny images
        scale_factor = 1.0
        max_dim = max(work_img.width, work_img.height)
        if max_dim > MAX_RECOGNITION_DIMENSION:
            scale_factor = MAX_RECOGNITION_DIMENSION / float(max_dim)
            new_w = max(1, int(round(work_img.width * scale_factor)))
            new_h = max(1, int(round(work_img.height * scale_factor)))
            work_img = work_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            operations.append(f"downscale_aspect_preserved({new_w}x{new_h})")
            warnings.append(
                f"Large image downscaled from {orig_w}x{orig_h} to {new_w}x{new_h} for CPU recognition."
            )
        elif work_img.height < MIN_RECOGNITION_HEIGHT:
            scale_factor = MIN_RECOGNITION_HEIGHT / float(work_img.height)
            new_w = max(1, int(round(work_img.width * scale_factor)))
            new_h = MIN_RECOGNITION_HEIGHT
            work_img = work_img.resize((new_w, new_h), Image.Resampling.BICUBIC)
            operations.append(f"upscale_small_height({new_w}x{new_h})")

        # 4. Grayscale conversion for contrast & noise inspection
        gray_img = ImageOps.grayscale(work_img)
        operations.append("grayscale_conversion")

        gray_np = np.asarray(gray_img, dtype=np.uint8)
        std_dev = float(np.std(gray_np))
        dynamic_range = int(np.percentile(gray_np, 98)) - int(np.percentile(gray_np, 2))

        if std_dev < 5.0 or dynamic_range < 15:
            warnings.append("Image has extremely low contrast or appears nearly blank.")
        elif dynamic_range < 180:
            gray_img = ImageOps.autocontrast(gray_img, cutoff=1)
            operations.append("contrast_normalization_autocontrast")

        # 5. Gentle denoising only when high-frequency grain is elevated on medium/large images
        if min(gray_img.width, gray_img.height) >= 120:
            # Estimate pixel-to-pixel high-frequency variation
            diff_h = np.abs(np.diff(gray_np.astype(np.int16), axis=1))
            noise_estimate = float(np.percentile(diff_h, 75))
            if noise_estimate > 8.0:
                gray_img = gray_img.filter(ImageFilter.MedianFilter(size=3))
                operations.append("median_denoise_3x3")

        # Convert back to 3-channel RGB so 3-channel ONNX detectors/recognizers receive standard input
        recognition_img = gray_img.convert("RGB")

        metadata = ImageMetadata(
            format=detected_format,
            mode=detected_mode,
            width=original_copy.width,
            height=original_copy.height,
            channels=detected_channels,
        )

        preprocessing_meta = PreprocessingMetadata(
            original_width=orig_w,
            original_height=orig_h,
            processed_width=recognition_img.width,
            processed_height=recognition_img.height,
            scale_factor=round(scale_factor, 4),
            operations=operations,
        )

        return PreparedImageBundle(
            original_image=original_copy,
            recognition_image=recognition_img,
            metadata=metadata,
            preprocessing=preprocessing_meta,
            warnings=warnings,
        )
