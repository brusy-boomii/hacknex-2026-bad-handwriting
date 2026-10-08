from typing import List, Literal, Optional
from pydantic import BaseModel, Field

UncertaintyLevel = Literal["HIGH", "MEDIUM", "LOW", "UNREADABLE"]
ReviewStatus = Literal["PENDING", "ACCEPTED", "CORRECTED", "REJECTED"]


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


class RegionQualityIndicators(BaseModel):
    """Measurable image-quality and plausibility signals computed for a region."""

    laplacian_variance: float = Field(
        ..., ge=0.0, description="Variance of Laplacian (edge sharpness indicator)."
    )
    rms_contrast: float = Field(
        ..., ge=0.0, description="Standard deviation of grayscale pixel intensities."
    )
    dynamic_range: float = Field(
        ..., ge=0.0, description="P95 - P5 grayscale intensity spread in [0, 255]."
    )
    stroke_ratio: float = Field(
        ..., ge=0.0, le=1.0, description="Estimated foreground stroke pixel fraction."
    )
    fg_bg_separation: float = Field(
        ..., ge=0.0, description="Mean intensity separation between foreground ink and background."
    )
    noise_level: float = Field(
        ..., ge=0.0, description="Mean absolute residual from 3x3 median filter."
    )
    sharpness_score: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized sharpness score in [0.0, 1.0]."
    )
    contrast_score: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized local contrast score in [0.0, 1.0]."
    )
    image_quality_score: float = Field(
        ..., ge=0.0, le=1.0, description="Composite local image quality score in [0.0, 1.0]."
    )
    plausibility_score: float = Field(
        ..., ge=0.0, le=1.0, description="Text and geometry plausibility score in [0.0, 1.0]."
    )


class SecondaryVerificationResult(BaseModel):
    """
    Phase 4A selective secondary verification output for a single region.
    Never overwrites raw OCR text; returns candidate interpretations separately.
    """

    original_text: str = Field(
        ..., description="Untouched original OCR output for this region."
    )
    candidate_text: Optional[str] = Field(
        default=None,
        description="Secondary candidate interpretation if trustworthy, or null when unavailable.",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score of the secondary candidate in [0.0, 1.0], or null.",
    )
    source: str = Field(
        default="secondary_verification",
        description="Source identifier for the secondary verification layer.",
    )
    requires_human_review: bool = Field(
        default=True,
        description="Whether human review is required before trusting this region.",
    )
    attempted: bool = Field(
        default=False,
        description="True if selective secondary verification was triggered for this region.",
    )
    status: str = Field(
        default="skipped_reliable_region",
        description="Execution status (e.g. 'skipped_reliable_region', 'secondary verification unavailable', 'candidate_available').",
    )
    message: str = Field(
        default="",
        description="Human-readable explanation of secondary verification status.",
    )


class RecognitionRegion(BaseModel):
    """Schema for an individual recognized text line or region with Phase 3/4 uncertainty & review state."""

    id: int = Field(..., ge=1, description="1-based index of the detected region.")
    text: str = Field(..., description="Immutable raw OCR text within this region.")
    raw_ocr: Optional[str] = Field(
        default=None,
        description="Explicit immutable copy of raw OCR text for provenance preservation.",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Engine-reported recognition confidence in [0.0, 1.0], or null if unavailable.",
    )
    ocr_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Raw OCR engine confidence score in [0.0, 1.0], or null if unavailable.",
    )
    normalized_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Composite reliability score combining OCR confidence, image quality, and plausibility.",
    )
    bbox: Optional[BoundingBox] = Field(
        default=None,
        description="Bounding box of the region in original image coordinates.",
    )
    region_type: str = Field(
        default="line",
        description="Granularity of the detected region (e.g., 'line', 'full_image_fallback').",
    )
    uncertainty_level: UncertaintyLevel = Field(
        default="MEDIUM",
        description="Reliability classification: HIGH, MEDIUM, LOW, or UNREADABLE.",
    )
    needs_review: bool = Field(
        default=False,
        description="Whether human inspection/review is recommended for this region.",
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="Explainable reason codes for uncertainty classification.",
    )
    uncertainty_reasons: List[str] = Field(
        default_factory=list,
        description="Alias for explainable uncertainty reason codes.",
    )
    quality_indicators: Optional[RegionQualityIndicators] = Field(
        default=None,
        description="Measured local image quality and plausibility indicators for this region.",
    )
    secondary_verification: Optional[SecondaryVerificationResult] = Field(
        default=None,
        description="Phase 4A selective secondary verification candidate/evidence.",
    )
    review_status: ReviewStatus = Field(
        default="PENDING",
        description="Phase 4B human review status: PENDING, ACCEPTED, CORRECTED, or REJECTED.",
    )
    final_text: Optional[str] = Field(
        default=None,
        description="Final region text after human review, or raw OCR text when PENDING.",
    )
    human_verified: bool = Field(
        default=False,
        description="True if a human has explicitly reviewed (accepted, corrected, or rejected) this region.",
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


class UncertaintyCounts(BaseModel):
    """Breakdown of region counts by reliability/uncertainty level."""

    HIGH: int = Field(default=0, ge=0, description="Number of HIGH reliability regions.")
    MEDIUM: int = Field(default=0, ge=0, description="Number of MEDIUM reliability regions.")
    LOW: int = Field(default=0, ge=0, description="Number of LOW reliability regions.")
    UNREADABLE: int = Field(default=0, ge=0, description="Number of UNREADABLE regions.")


class UncertaintySummary(BaseModel):
    """Document-level and region-level Phase 3 uncertainty analysis summary."""

    overall_level: UncertaintyLevel = Field(
        ..., description="Document-level reliability state (HIGH, MEDIUM, LOW, or UNREADABLE)."
    )
    mean_ocr_confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Mean raw OCR engine confidence across regions."
    )
    mean_normalized_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Mean composite normalized reliability score across regions.",
    )
    mean_image_quality_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Mean local image quality score across regions (or full image if 0 regions).",
    )
    total_regions: int = Field(default=0, ge=0, description="Total number of analyzed regions.")
    flagged_region_count: int = Field(
        default=0, ge=0, description="Number of regions where needs_review is True."
    )
    counts: UncertaintyCounts = Field(
        default_factory=UncertaintyCounts,
        description="Count of regions in each uncertainty/reliability tier.",
    )
    review_recommended: bool = Field(
        ..., description="True if human review is recommended for this document."
    )
    annotated_text: str = Field(
        default="",
        description="Uncertainty-aware transcription marking uncertain segments without altering raw text.",
    )
    summary_reasons: List[str] = Field(
        default_factory=list,
        description="Aggregated reason codes observed across the document.",
    )
    processing_time_ms: float = Field(
        default=0.0, ge=0.0, description="Execution time of the uncertainty analysis in milliseconds."
    )
    regions: List[RecognitionRegion] = Field(
        default_factory=list,
        description="Region-level uncertainty analysis entries.",
    )


class VerificationSummary(BaseModel):
    """Document-level summary of Phase 4A selective secondary verification."""

    enabled: bool = Field(
        default=False, description="Whether an external secondary verification provider is active."
    )
    provider: str = Field(
        default="none", description="Configured secondary verification provider name."
    )
    status: str = Field(
        default="secondary verification unavailable",
        description="Service availability status ('active' or 'secondary verification unavailable').",
    )
    total_regions: int = Field(default=0, ge=0, description="Total OCR regions evaluated.")
    verified_region_count: int = Field(
        default=0,
        ge=0,
        description="Number of LOW/UNREADABLE/needs_review regions routed to secondary verification.",
    )
    skipped_region_count: int = Field(
        default=0,
        ge=0,
        description="Number of reliable (HIGH) regions that bypassed secondary verification.",
    )
    candidates_generated: int = Field(
        default=0,
        ge=0,
        description="Number of trustworthy candidate interpretations produced.",
    )
    message: str = Field(
        default="secondary verification unavailable",
        description="Human-readable summary of secondary verification execution.",
    )


class AnalyzeResponse(BaseModel):
    """Schema for the POST /analyze endpoint response in Phase 4."""

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
    uncertainty: Optional[UncertaintySummary] = Field(
        default=None,
        description="Phase 3 multi-signal confidence and uncertainty analysis output.",
    )
    verification: Optional[VerificationSummary] = Field(
        default=None,
        description="Phase 4A selective secondary verification summary.",
    )
    raw_ocr_text: Optional[str] = Field(
        default=None,
        description="Immutable full-document raw OCR output for provenance tracking.",
    )
    final_text: Optional[str] = Field(
        default=None,
        description="Current full-document transcription (preserves raw OCR until human review modifies regions).",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings generated during preprocessing, recognition, or uncertainty analysis.",
    )
    message: str = Field(..., description="Human-readable summary of the analysis result.")
    pipeline_status: str = Field(..., description="Identifier for the completed pipeline stage.")


class ExportDocumentMetadata(BaseModel):
    """Document metadata preserved during export without inventing IDs."""

    filename: str = Field(..., description="Original uploaded filename.")
    engine: Optional[str] = Field(
        default=None, description="Recognition engine identifier if available."
    )
    overall_uncertainty: Optional[UncertaintyLevel] = Field(
        default=None, description="Overall document uncertainty level if available."
    )


class ExportRegionProvenance(BaseModel):
    """Per-region provenance record preserving raw OCR vs. human-verified output."""

    id: Optional[int] = Field(default=None, ge=1, description="1-based region index.")
    raw_ocr: str = Field(..., description="Immutable original OCR text for this region.")
    uncertainty: UncertaintyLevel = Field(
        ..., description="Uncertainty classification (HIGH, MEDIUM, LOW, UNREADABLE)."
    )
    needs_review: Optional[bool] = Field(
        default=None, description="Whether region was flagged for human review."
    )
    reasons: List[str] = Field(
        default_factory=list, description="Uncertainty reason codes for this region."
    )
    candidate_text: Optional[str] = Field(
        default=None, description="Secondary verification candidate if one was available."
    )
    review_status: ReviewStatus = Field(
        default="PENDING",
        description="Human review status: PENDING, ACCEPTED, CORRECTED, or REJECTED.",
    )
    final_text: str = Field(
        ..., description="Final text for this region after human review (or raw_ocr if PENDING)."
    )
    human_verified: bool = Field(
        default=False,
        description="True if a human explicitly accepted, corrected, or rejected this region.",
    )


class ExportJsonResponse(BaseModel):
    """Provenance-preserving JSON export structure."""

    document: ExportDocumentMetadata = Field(
        ..., description="Document-level provenance metadata."
    )
    raw_ocr_text: str = Field(
        ..., description="Complete immutable raw OCR transcription."
    )
    regions: List[ExportRegionProvenance] = Field(
        default_factory=list,
        description="Region-by-region provenance records.",
    )
    final_text: str = Field(
        ..., description="Final human-verified full transcription."
    )
    human_verified: bool = Field(
        default=False,
        description="True if at least one region in the document was verified/corrected by a human.",
    )


class RegionReviewInput(BaseModel):
    """Input payload representing a region's state for review/export."""

    id: Optional[int] = Field(default=None, ge=1)
    raw_ocr: str = Field(..., description="Original raw OCR text for this region.")
    uncertainty: UncertaintyLevel = Field(default="MEDIUM")
    needs_review: Optional[bool] = Field(default=None)
    reasons: List[str] = Field(default_factory=list)
    candidate_text: Optional[str] = Field(default=None)
    review_status: ReviewStatus = Field(default="PENDING")
    final_text: Optional[str] = Field(default=None)
    human_verified: Optional[bool] = Field(default=None)


class ReviewExportRequest(BaseModel):
    """Request payload for generating TXT or JSON provenance exports."""

    filename: str = Field(..., min_length=1, description="Original document filename.")
    engine: Optional[str] = Field(default=None)
    overall_uncertainty: Optional[UncertaintyLevel] = Field(default=None)
    regions: List[RegionReviewInput] = Field(default_factory=list)
    final_text: Optional[str] = Field(default=None)


class ErrorResponse(BaseModel):
    """Schema for structured HTTP error responses."""

    detail: str = Field(..., description="Clean human-readable error message.")


__all__ = [
    "UncertaintyLevel",
    "ReviewStatus",
    "HealthResponse",
    "ImageMetadata",
    "PreprocessingMetadata",
    "BoundingBox",
    "RegionQualityIndicators",
    "SecondaryVerificationResult",
    "RecognitionRegion",
    "RecognitionResult",
    "UncertaintyCounts",
    "UncertaintySummary",
    "VerificationSummary",
    "AnalyzeResponse",
    "ExportDocumentMetadata",
    "ExportRegionProvenance",
    "ExportJsonResponse",
    "RegionReviewInput",
    "ReviewExportRequest",
    "ErrorResponse",
]

