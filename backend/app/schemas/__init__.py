from typing import List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema for the GET /health endpoint response."""

    status: str = Field(..., description="Current operational status of the service.")
    application: str = Field(..., description="Application name.")
    version: str = Field(..., description="Semantic version of the backend API.")
    phase: int = Field(..., description="Current active development phase.")
    description: str = Field(..., description="Human-readable phase status summary.")


class ImageMetadata(BaseModel):
    """Schema for validated original image properties."""

    format: str = Field(..., description="Detected image container format (e.g., PNG, JPEG).")
    mode: str = Field(..., description="Pillow pixel color mode (e.g., RGB, L, RGBA).")
    width: int = Field(..., gt=0, description="Image width in pixels.")
    height: int = Field(..., gt=0, description="Image height in pixels.")
    channels: int = Field(..., gt=0, description="Number of color channels/bands in the image.")


class PreprocessingMetadata(BaseModel):
    """Schema describing preprocessing operations applied before OCR."""

    original_width: int = Field(..., gt=0, description="Original image width in pixels.")
    original_height: int = Field(..., gt=0, description="Original image height in pixels.")
    processed_width: int = Field(..., gt=0, description="Recognition-ready image width in pixels.")
    processed_height: int = Field(..., gt=0, description="Recognition-ready image height in pixels.")
    scale_factor: float = Field(..., gt=0, description="Resize scale factor applied to image.")
    operations: List[str] = Field(
        default_factory=list,
        description="Ordered list of preprocessing operations applied.",
    )


class BoundingBox(BaseModel):
    """Schema for a detected text region's bounding box in original image coordinates."""

    x_min: int = Field(..., ge=0, description="Leftmost X coordinate in pixels.")
    y_min: int = Field(..., ge=0, description="Topmost Y coordinate in pixels.")
    x_max: int = Field(..., ge=0, description="Rightmost X coordinate in pixels.")
    y_max: int = Field(..., ge=0, description="Bottommost Y coordinate in pixels.")
    width: int = Field(..., ge=0, description="Bounding box width in pixels.")
    height: int = Field(..., ge=0, description="Bounding box height in pixels.")
    polygon: List[List[int]] = Field(
        default_factory=list,
        description="Four-point quadrilateral coordinates [[x1,y1], [x2,y2], [x3,y3], [x4,y4]].",
    )


class RecognitionRegion(BaseModel):
    """Schema for an individual recognized text line or region."""

    id: int = Field(..., ge=1, description="1-based index of the detected region.")
    text: str = Field(..., description="Recognized text within this region.")
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Engine-reported recognition confidence in [0.0, 1.0], or null if unavailable.",
    )
    bbox: Optional[BoundingBox] = Field(
        default=None,
        description="Bounding box of the region in original image coordinates.",
    )
    region_type: str = Field(
        default="line",
        description="Granularity of the detected region (e.g., 'line', 'full_image_fallback').",
    )


class RecognitionResult(BaseModel):
    """Schema for the output of the handwriting recognition engine."""

    text: str = Field(..., description="Full recognized text across all detected regions.")
    engine: str = Field(..., description="Identifier of the OCR/HTR engine and model used.")
    processing_time_ms: float = Field(
        ...,
        ge=0.0,
        description="Measured recognition execution time in milliseconds.",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Mean recognition confidence across regions, or null if no regions detected.",
    )
    regions: List[RecognitionRegion] = Field(
        default_factory=list,
        description="Ordered list of detected and recognized text regions.",
    )


class AnalyzeResponse(BaseModel):
    """Schema for the POST /analyze endpoint response in Phase 2."""

    status: str = Field(..., description="Processing status of the analysis request ('success').")
    filename: str = Field(..., description="Original filename of the uploaded image.")
    image: ImageMetadata = Field(..., description="Validated metadata of the original uploaded image.")
    metadata: ImageMetadata = Field(..., description="Alias for original image metadata (Phase 1 compatibility).")
    preprocessing: PreprocessingMetadata = Field(
        ...,
        description="Details of preprocessing steps applied to produce the recognition-ready image.",
    )
    recognition: RecognitionResult = Field(
        ...,
        description="Actual recognition output from the OCR/HTR engine.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings generated during preprocessing or recognition.",
    )
    message: str = Field(..., description="Human-readable summary of the analysis result.")
    pipeline_status: str = Field(..., description="Identifier for the completed pipeline stage.")


class ErrorResponse(BaseModel):
    """Schema for structured HTTP error responses."""

    detail: str = Field(..., description="Clean human-readable error message.")


__all__ = [
    "HealthResponse",
    "ImageMetadata",
    "PreprocessingMetadata",
    "BoundingBox",
    "RecognitionRegion",
    "RecognitionResult",
    "AnalyzeResponse",
    "ErrorResponse",
]
