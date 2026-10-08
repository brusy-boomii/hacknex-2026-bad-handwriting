from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema for the GET /health endpoint response."""

    status: str = Field(..., description="Current operational status of the service.")
    application: str = Field(..., description="Application name.")
    version: str = Field(..., description="Semantic version of the backend API.")
    phase: int = Field(..., description="Current active development phase.")
    description: str = Field(..., description="Human-readable phase status summary.")


class ImageMetadata(BaseModel):
    """Schema for validated image properties extracted during Phase 1 preprocessing."""

    format: str = Field(..., description="Detected image container format (e.g., PNG, JPEG).")
    mode: str = Field(..., description="Pillow pixel color mode (e.g., RGB, L, RGBA).")
    width: int = Field(..., gt=0, description="Image width in pixels.")
    height: int = Field(..., gt=0, description="Image height in pixels.")
    channels: int = Field(..., gt=0, description="Number of color channels/bands in the image.")


class AnalyzeResponse(BaseModel):
    """Schema for the POST /analyze endpoint response in Phase 1."""

    status: str = Field(..., description="Processing status of the uploaded image.")
    filename: str = Field(..., description="Original filename of the uploaded image.")
    metadata: ImageMetadata = Field(..., description="Validated structural metadata of the image.")
    message: str = Field(..., description="Informational message regarding pipeline stage.")
    pipeline_status: str = Field(..., description="Identifier for the active pipeline stage.")


class ErrorResponse(BaseModel):
    """Schema for structured HTTP error responses."""

    detail: str = Field(..., description="Clean human-readable error message.")


__all__ = [
    "HealthResponse",
    "ImageMetadata",
    "AnalyzeResponse",
    "ErrorResponse",
]
