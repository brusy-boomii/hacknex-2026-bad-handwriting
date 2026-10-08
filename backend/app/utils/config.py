import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB (10,485,760 bytes)
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}


def get_max_upload_size_bytes() -> int:
    """
    Retrieve the maximum allowed upload size in bytes from MAX_UPLOAD_SIZE_BYTES.
    Defaults to 10,485,760 bytes (10 MB) if unset or invalid.
    """
    raw_value = os.getenv("MAX_UPLOAD_SIZE_BYTES")
    if not raw_value:
        return DEFAULT_MAX_UPLOAD_SIZE_BYTES
    # Strip any trailing inline comment if present in .env
    cleaned = raw_value.split("#")[0].strip()
    try:
        parsed = int(cleaned)
        return parsed if parsed > 0 else DEFAULT_MAX_UPLOAD_SIZE_BYTES
    except ValueError:
        return DEFAULT_MAX_UPLOAD_SIZE_BYTES


def get_allowed_origins() -> List[str]:
    """
    Retrieve the list of allowed CORS origins from ALLOWED_ORIGINS.
    """
    raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
