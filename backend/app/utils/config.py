from dataclasses import dataclass
import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB (10,485,760 bytes)
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}

# Default Phase 3 Uncertainty & Image Quality Thresholds
DEFAULT_HIGH_CONFIDENCE_THRESHOLD = 0.82
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.60
DEFAULT_UNREADABLE_CONFIDENCE_THRESHOLD = 0.35
DEFAULT_LEGACY_MEAN_CONFIDENCE_WARNING_THRESHOLD = 0.65

DEFAULT_HIGH_RELIABILITY_THRESHOLD = 0.78
DEFAULT_LOW_RELIABILITY_THRESHOLD = 0.62
DEFAULT_UNREADABLE_RELIABILITY_THRESHOLD = 0.38

DEFAULT_BLUR_LAPLACIAN_THRESHOLD = 45.0
DEFAULT_LOW_CONTRAST_RANGE_THRESHOLD = 45.0
DEFAULT_FAINT_STROKE_SEPARATION_THRESHOLD = 30.0
DEFAULT_HIGH_NOISE_THRESHOLD = 14.0


@dataclass(frozen=True)
class UncertaintyConfig:
    """Configurable thresholds for Phase 3 confidence & uncertainty classification."""

    high_confidence_threshold: float = DEFAULT_HIGH_CONFIDENCE_THRESHOLD
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD
    unreadable_confidence_threshold: float = DEFAULT_UNREADABLE_CONFIDENCE_THRESHOLD
    legacy_mean_warning_threshold: float = DEFAULT_LEGACY_MEAN_CONFIDENCE_WARNING_THRESHOLD

    high_reliability_threshold: float = DEFAULT_HIGH_RELIABILITY_THRESHOLD
    low_reliability_threshold: float = DEFAULT_LOW_RELIABILITY_THRESHOLD
    unreadable_reliability_threshold: float = DEFAULT_UNREADABLE_RELIABILITY_THRESHOLD

    blur_laplacian_threshold: float = DEFAULT_BLUR_LAPLACIAN_THRESHOLD
    low_contrast_range_threshold: float = DEFAULT_LOW_CONTRAST_RANGE_THRESHOLD
    faint_stroke_separation_threshold: float = DEFAULT_FAINT_STROKE_SEPARATION_THRESHOLD
    high_noise_threshold: float = DEFAULT_HIGH_NOISE_THRESHOLD


def _parse_float_env(var_name: str, default: float) -> float:
    raw_value = os.getenv(var_name)
    if not raw_value:
        return default
    cleaned = raw_value.split("#")[0].strip()
    try:
        return float(cleaned)
    except ValueError:
        return default


def get_uncertainty_config() -> UncertaintyConfig:
    """Load Phase 3 uncertainty thresholds from environment variables with defaults."""
    return UncertaintyConfig(
        high_confidence_threshold=_parse_float_env(
            "UNCERTAINTY_HIGH_CONFIDENCE_THRESHOLD", DEFAULT_HIGH_CONFIDENCE_THRESHOLD
        ),
        low_confidence_threshold=_parse_float_env(
            "UNCERTAINTY_LOW_CONFIDENCE_THRESHOLD", DEFAULT_LOW_CONFIDENCE_THRESHOLD
        ),
        unreadable_confidence_threshold=_parse_float_env(
            "UNCERTAINTY_UNREADABLE_CONFIDENCE_THRESHOLD", DEFAULT_UNREADABLE_CONFIDENCE_THRESHOLD
        ),
        legacy_mean_warning_threshold=_parse_float_env(
            "UNCERTAINTY_LEGACY_MEAN_WARNING_THRESHOLD", DEFAULT_LEGACY_MEAN_CONFIDENCE_WARNING_THRESHOLD
        ),
        high_reliability_threshold=_parse_float_env(
            "UNCERTAINTY_HIGH_RELIABILITY_THRESHOLD", DEFAULT_HIGH_RELIABILITY_THRESHOLD
        ),
        low_reliability_threshold=_parse_float_env(
            "UNCERTAINTY_LOW_RELIABILITY_THRESHOLD", DEFAULT_LOW_RELIABILITY_THRESHOLD
        ),
        unreadable_reliability_threshold=_parse_float_env(
            "UNCERTAINTY_UNREADABLE_RELIABILITY_THRESHOLD", DEFAULT_UNREADABLE_RELIABILITY_THRESHOLD
        ),
        blur_laplacian_threshold=_parse_float_env(
            "UNCERTAINTY_BLUR_LAPLACIAN_THRESHOLD", DEFAULT_BLUR_LAPLACIAN_THRESHOLD
        ),
        low_contrast_range_threshold=_parse_float_env(
            "UNCERTAINTY_LOW_CONTRAST_RANGE_THRESHOLD", DEFAULT_LOW_CONTRAST_RANGE_THRESHOLD
        ),
        faint_stroke_separation_threshold=_parse_float_env(
            "UNCERTAINTY_FAINT_STROKE_SEPARATION_THRESHOLD", DEFAULT_FAINT_STROKE_SEPARATION_THRESHOLD
        ),
        high_noise_threshold=_parse_float_env(
            "UNCERTAINTY_HIGH_NOISE_THRESHOLD", DEFAULT_HIGH_NOISE_THRESHOLD
        ),
    )


def get_max_upload_size_bytes() -> int:
    """
    Retrieve the maximum allowed upload size in bytes from MAX_UPLOAD_SIZE_BYTES.
    Defaults to 10,485,760 bytes (10 MB) if unset or invalid.
    """
    raw_value = os.getenv("MAX_UPLOAD_SIZE_BYTES")
    if not raw_value:
        return DEFAULT_MAX_UPLOAD_SIZE_BYTES
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


@dataclass(frozen=True)
class SecondaryVerificationConfig:
    """
    Configuration for Phase 4 selective secondary verification.
    Operates without an external API by default and cleanly reports
    'secondary verification unavailable' when no external provider is configured.
    """

    enabled: bool = False
    provider: str = "none"
    api_key_configured: bool = False


def get_secondary_verification_config() -> SecondaryVerificationConfig:
    """
    Load Phase 4 secondary verification settings from environment variables.
    Never exposes or logs secret values.
    """
    raw_enabled = (os.getenv("SECONDARY_VERIFICATION_ENABLED") or "").split("#")[0].strip().lower()
    enabled = raw_enabled in {"1", "true", "yes", "on"}
    provider = (os.getenv("SECONDARY_VERIFICATION_PROVIDER") or "none").split("#")[0].strip() or "none"
    raw_key = (os.getenv("SECONDARY_VERIFICATION_API_KEY") or "").split("#")[0].strip()
    api_key_configured = bool(raw_key)
    return SecondaryVerificationConfig(
        enabled=enabled and provider.lower() != "none" and api_key_configured,
        provider=provider if (enabled and api_key_configured) else "none",
        api_key_configured=api_key_configured,
    )

