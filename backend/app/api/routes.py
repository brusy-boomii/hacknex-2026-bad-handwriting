from pathlib import Path
from typing import Optional
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from app.schemas import (
    AnalyzeResponse,
    ErrorResponse,
    ExportJsonResponse,
    HealthResponse,
    ReviewExportRequest,
)
from app.services.handwriting_ocr import (
    HandwritingOCRService,
    OCRExecutionError,
    OCRModelUnavailableError,
)
from app.services.preprocessing import PreprocessingService
from app.services.uncertainty import UncertaintyService
from app.services.verification import (
    SecondaryVerificationService,
    build_export_json,
    build_export_txt,
)
from app.utils.config import ALLOWED_IMAGE_EXTENSIONS, get_max_upload_size_bytes

router = APIRouter()
preprocessing_service = PreprocessingService()
ocr_service = HandwritingOCRService()
uncertainty_service = UncertaintyService()
verification_service = SecondaryVerificationService()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health Check",
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint providing application status and Phase 4 metadata.
    """
    return HealthResponse(
        status="healthy",
        application="Extreme Bad-Handwriting Digitizing Stack",
        version="0.4.0",
        phase=4,
        description="Phase 4 selective verification, human review, and export workflow active.",
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
    summary="Validate, Preprocess, Recognize, Evaluate Uncertainty, and Run Selective Verification",
)
async def analyze_handwriting(
    file: Optional[UploadFile] = File(default=None),
) -> AnalyzeResponse:
    """
    Phase 4 endpoint for confidence-aware handwriting digitization.
    Validates the uploaded image, runs handwriting-safe preprocessing, executes
    PP-OCRv3 optical recognition, evaluates multi-signal region uncertainty,
    triggers selective secondary verification only on uncertain regions,
    and returns structured recognition, uncertainty, verification, and provenance fields.
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

        verified_regions, verification_summary = verification_service.verify_regions(
            uncertainty_summary.regions
        )

        enriched_uncertainty = uncertainty_summary.model_copy(
            update={"regions": verified_regions}
        )
        enriched_recognition = ocr_output.result.model_copy(
            update={"regions": verified_regions}
        )

        combined_warnings = list(prepared.warnings) + list(ocr_output.warnings)
        if enriched_uncertainty.flagged_region_count > 0:
            combined_warnings.append(
                f"{enriched_uncertainty.flagged_region_count} of {enriched_uncertainty.total_regions} "
                f"region(s) flagged for human review (overall reliability: {enriched_uncertainty.overall_level})."
            )

        region_count = len(enriched_recognition.regions)
        if region_count > 0:
            summary_msg = (
                f"Recognition completed ({region_count} region(s) detected in "
                f"{enriched_recognition.processing_time_ms:.1f} ms; "
                f"overall reliability: {enriched_uncertainty.overall_level})."
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
            uncertainty=enriched_uncertainty,
            verification=verification_summary,
            raw_ocr_text=enriched_recognition.text,
            final_text=enriched_recognition.text,
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


@router.post(
    "/export/json",
    response_model=ExportJsonResponse,
    responses={status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse}},
    summary="Export Provenance-Preserving JSON Transcription",
)
async def export_json_endpoint(request: ReviewExportRequest) -> ExportJsonResponse:
    """
    Generate a structured JSON export preserving raw OCR output, uncertainty tier,
    human review status, and final human-verified transcription.
    """
    try:
        return build_export_json(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/export/txt",
    response_class=PlainTextResponse,
    responses={status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse}},
    summary="Export Plain-Text (.txt) Transcription with Provenance",
)
async def export_txt_endpoint(request: ReviewExportRequest) -> PlainTextResponse:
    """
    Generate a plain-text (.txt) export containing the final verified transcription
    and unmodified raw OCR provenance.
    """
    try:
        txt_content = build_export_txt(request)
        return PlainTextResponse(content=txt_content, media_type="text/plain; charset=utf-8")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

