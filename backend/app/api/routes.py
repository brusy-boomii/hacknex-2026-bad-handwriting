from pathlib import Path
from typing import Optional
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from app.schemas import AnalyzeResponse, ErrorResponse, HealthResponse
from app.services.preprocessing import PreprocessingService
from app.utils.config import ALLOWED_IMAGE_EXTENSIONS, get_max_upload_size_bytes

router = APIRouter()
preprocessing_service = PreprocessingService()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health Check",
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint providing application status and Phase 1 metadata.
    """
    return HealthResponse(
        status="healthy",
        application="Extreme Bad-Handwriting Digitizing Stack",
        version="0.1.0",
        phase=1,
        description="Foundation phase established.",
    )


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse},
    },
    summary="Validate and Inspect Uploaded Handwriting Image",
)
async def analyze_handwriting(
    file: Optional[UploadFile] = File(default=None),
) -> AnalyzeResponse:
    """
    Foundation endpoint for handwriting image ingestion.
    Validates upload presence, filename, extension, MIME type, byte size,
    and structural image integrity before returning verified image metadata.
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
            image_info = preprocessing_service.validate_and_get_info(content)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        return AnalyzeResponse(
            status="received",
            filename=filename,
            metadata=image_info,
            message="Image received and validated. Recognition pipeline will be implemented in Phase 2.",
            pipeline_status="foundation_active",
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
