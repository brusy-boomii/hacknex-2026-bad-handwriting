import io
from PIL import Image, UnidentifiedImageError
from app.schemas import ImageMetadata


class PreprocessingService:
    """
    Service for image loading, structural validation, and metadata extraction.
    Acts as the entry point for the handwriting digitization pipeline.
    """

    def validate_and_get_info(self, image_bytes: bytes) -> ImageMetadata:
        """
        Loads the image from raw bytes, verifies both header and pixel stream
        integrity, and returns typed ImageMetadata.

        Raises:
            ValueError: If the payload is empty, corrupt, or not a readable image.
        """
        if not image_bytes:
            raise ValueError("Uploaded image payload is empty.")

        try:
            with Image.open(io.BytesIO(image_bytes)) as img_verify:
                img_verify.verify()

            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()
                if not image.format or image.width <= 0 or image.height <= 0:
                    raise ValueError("Image has invalid dimensions or unknown format.")

                return ImageMetadata(
                    format=image.format,
                    mode=image.mode,
                    width=image.width,
                    height=image.height,
                    channels=len(image.getbands()),
                )
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            raise ValueError("Uploaded file contains corrupt or unreadable image data.") from exc
        except Exception as exc:
            raise ValueError("Uploaded file could not be decoded as a valid image.") from exc
