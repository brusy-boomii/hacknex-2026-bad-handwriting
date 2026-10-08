from pathlib import Path
from typing import Optional
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from app.schemas import AnalyzeResponse, ErrorResponse, HealthResponse
from app.services.handwriting_ocr import (
    HandwritingOCRService,
    OCRExecutionError,
    OCRModelUnavailableError,
)
from app.services.preprocessing import PreprocessingService
from app.services.uncertainty import UncertaintyService
from app.utils.config import ALLOWED_IMAGE_EXTENSIONS, get_max_upload_size_bytes

router = APIRouter()
preprocessing_service = PreprocessingService()
ocr_service = HandwritingOCRService()
uncertainty_service = UncertaintyService()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health Check",
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint providing application status and Phase 3 metadata.
    """
    return HealthResponse(
        status="healthy",
        application="Extreme Bad-Handwriting Digitizing Stack",
        version="0.3.0",
        phase=3,
        description="Phase 3 confidence-aware uncertainty detection active.",
    )


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Validate, Preprocess, Recognize, and Evaluate Uncertainty on Handwritten Image",
)
async def analyze_handwriting(
    file: Optional[UploadFile] = File(default=None),
) -> AnalyzeResponse:
    """
    Phase 3 endpoint for confidence-aware handwriting digitization.
    Validates the uploaded image, runs handwriting-safe preprocessing, executes
    PP-OCRv3 optical recognition, evaluates multi-signal region uncertainty,
    and returns structured recognition and uncertainty results.
    """
    if file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No image file was provided in the request.",
        )

    try:
        filename = (file.filename or "").strip()
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is missing a filename.",
            )

        extension = Path(filename).suffix.lower()
        if not extension or extension not in ALLOWED_IMAGE_EXTENSIONS:
            allowed_list = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Extension '{extension or '(none)'}' is not supported. Allowed: {allowed_list}",
            )

        content_type = (file.content_type or "").strip().lower()
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' is not a valid image MIME type. Received: '{file.content_type or 'none'}'.",
            )

        content = await file.read()

        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' is empty (0 bytes).",
            )

        max_size = get_max_upload_size_bytes()
        if len(content) > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File size ({len(content)} bytes) exceeds maximum allowed limit ({max_size} bytes).",
            )

        try:
            prepared = preprocessing_service.prepare_for_pipeline(content)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        try:
            ocr_output = ocr_service.recognize_with_warnings(
                image=prepared.recognition_image,
                original_size=(prepared.metadata.width, prepared.metadata.height),
            )
        except OCRModelUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Recognition engine model is currently unavailable.",
            ) from exc
        except OCRExecutionError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Recognition engine failed while processing the uploaded image.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        uncertainty_summary = uncertainty_service.analyze_uncertainty(
            image=prepared.original_image,
            ocr_regions=ocr_output.result.regions,
        )

        # Keep recognition.regions synchronized with the enriched region-level uncertainty fields
        enriched_recognition = ocr_output.result.model_copy(
            update={"regions": uncertainty_summary.regions}
        )

        combined_warnings = list(prepared.warnings) + list(ocr_output.warnings)
        if uncertainty_summary.flagged_region_count > 0:
            combined_warnings.append(
                f"{uncertainty_summary.flagged_region_count} of {uncertainty_summary.total_regions} "
                f"region(s) flagged for human review (overall reliability: {uncertainty_summary.overall_level})."
            )

        region_count = len(enriched_recognition.regions)
        if region_count > 0:
            summary_msg = (
                f"Recognition completed ({region_count} region(s) detected in "
                f"{enriched_recognition.processing_time_ms:.1f} ms; "
                f"overall reliability: {uncertainty_summary.overall_level})."
            )
        else:
            summary_msg = "Image validated and processed, but no legible text regions were detected."

        return AnalyzeResponse(
            status="success",
            filename=filename,
            image=prepared.metadata,
            metadata=prepared.metadata,
            preprocessing=prepared.preprocessing,
            recognition=enriched_recognition,
            uncertainty=uncertainty_summary,
            warnings=combined_warnings,
            message=summary_msg,
            pipeline_status="recognition_complete",
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred while processing the upload.",
        ) from exc
    finally:
        await file.close()
