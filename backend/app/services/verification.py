from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from app.schemas import (
    ExportDocumentMetadata,
    ExportJsonResponse,
    ExportRegionProvenance,
    RecognitionRegion,
    ReviewExportRequest,
    SecondaryVerificationResult,
    VerificationSummary,
)
from app.utils.config import (
    SecondaryVerificationConfig,
    get_secondary_verification_config,
)

VerifierCallable = Callable[[RecognitionRegion], Tuple[Optional[str], Optional[float]]]


class SecondaryVerificationService:
    """
    Phase 4A Selective Secondary Verification Service.

    Design principles:
    - Reliable OCR (HIGH, needs_review == False) -> accept efficiently (skip secondary verification).
    - Uncertain OCR (LOW, UNREADABLE, or needs_review == True) -> investigate further.
    - Never silently overwrite the original OCR output (`region.text` / `region.raw_ocr`).
    - Return candidate interpretations separately (`SecondaryVerificationResult`).
    - When no external verification model/API is configured or no trustworthy candidate
      can be produced, return `candidate_text = None` and report
      `"secondary verification unavailable"`.
    """

    def __init__(
        self,
        config: Optional[SecondaryVerificationConfig] = None,
        verifier_fn: Optional[VerifierCallable] = None,
    ) -> None:
        self._config = config
        self._verifier_fn = verifier_fn

    def _get_config(self) -> SecondaryVerificationConfig:
        return (
            self._config
            if self._config is not None
            else get_secondary_verification_config()
        )

    @staticmethod
    def should_verify_region(region: RecognitionRegion) -> bool:
        """
        Return True ONLY when the region requires secondary investigation:
        - uncertainty_level is LOW
        - OR uncertainty_level is UNREADABLE
        - OR needs_review is True
        """
        return (
            region.uncertainty_level in ("LOW", "UNREADABLE")
            or bool(region.needs_review)
        )

    def verify_region(self, region: RecognitionRegion) -> RecognitionRegion:
        """
        Evaluate a single OCR region for selective secondary verification.
        Never overwrites `region.text`.
        """
        raw_ocr = region.raw_ocr if region.raw_ocr is not None else region.text
        final_text = region.final_text if region.final_text is not None else raw_ocr
        review_status = region.review_status or "PENDING"

        if not self.should_verify_region(region):
            verification_result = SecondaryVerificationResult(
                original_text=raw_ocr,
                candidate_text=None,
                confidence=None,
                source="secondary_verification",
                requires_human_review=False,
                attempted=False,
                status="skipped_reliable_region",
                message="Skipped: region classified as reliable OCR.",
            )
            return region.model_copy(
                update={
                    "raw_ocr": raw_ocr,
                    "secondary_verification": verification_result,
                    "review_status": review_status,
                    "final_text": final_text,
                    "human_verified": bool(region.human_verified),
                }
            )

        config = self._get_config()
        active_verifier = self._verifier_fn is not None or config.enabled

        if not active_verifier:
            verification_result = SecondaryVerificationResult(
                original_text=raw_ocr,
                candidate_text=None,
                confidence=None,
                source="secondary_verification",
                requires_human_review=True,
                attempted=True,
                status="secondary verification unavailable",
                message="secondary verification unavailable",
            )
            return region.model_copy(
                update={
                    "raw_ocr": raw_ocr,
                    "secondary_verification": verification_result,
                    "review_status": review_status,
                    "final_text": final_text,
                    "human_verified": bool(region.human_verified),
                }
            )

        if self._verifier_fn is None:
            verification_result = SecondaryVerificationResult(
                original_text=raw_ocr,
                candidate_text=None,
                confidence=None,
                source="secondary_verification",
                requires_human_review=True,
                attempted=True,
                status="secondary verification unavailable",
                message="secondary verification unavailable",
            )
        else:
            try:
                cand_text, cand_conf = self._verifier_fn(region)
                cleaned_cand = cand_text.strip() if isinstance(cand_text, str) else None
                if not cleaned_cand:
                    verification_result = SecondaryVerificationResult(
                        original_text=raw_ocr,
                        candidate_text=None,
                        confidence=None,
                        source="secondary_verification",
                        requires_human_review=True,
                        attempted=True,
                        status="no_trustworthy_candidate",
                        message="No trustworthy secondary interpretation could be produced.",
                    )
                else:
                    norm_conf: Optional[float] = None
                    if cand_conf is not None:
                        norm_conf = round(max(0.0, min(1.0, float(cand_conf))), 4)
                    verification_result = SecondaryVerificationResult(
                        original_text=raw_ocr,
                        candidate_text=cleaned_cand,
                        confidence=norm_conf,
                        source="secondary_verification",
                        requires_human_review=True,
                        attempted=True,
                        status="candidate_available",
                        message="Secondary candidate interpretation available for human review.",
                    )
            except Exception:
                verification_result = SecondaryVerificationResult(
                    original_text=raw_ocr,
                    candidate_text=None,
                    confidence=None,
                    source="secondary_verification",
                    requires_human_review=True,
                    attempted=True,
                    status="secondary verification unavailable",
                    message="secondary verification unavailable",
                )

        return region.model_copy(
            update={
                "raw_ocr": raw_ocr,
                "secondary_verification": verification_result,
                "review_status": review_status,
                "final_text": final_text,
                "human_verified": bool(region.human_verified),
            }
        )

    def verify_regions(
        self, regions: Sequence[RecognitionRegion]
    ) -> Tuple[List[RecognitionRegion], VerificationSummary]:
        """
        Run selective secondary verification across a sequence of OCR regions.
        """
        config = self._get_config()
        is_enabled = self._verifier_fn is not None or config.enabled
        provider_name = (
            "custom_verifier"
            if self._verifier_fn is not None
            else (config.provider if config.enabled else "none")
        )

        verified_regions: List[RecognitionRegion] = []
        verified_count = 0
        skipped_count = 0
        candidates_count = 0

        for reg in regions:
            updated = self.verify_region(reg)
            verified_regions.append(updated)
            sv = updated.secondary_verification
            if sv and sv.attempted:
                verified_count += 1
                if sv.candidate_text is not None:
                    candidates_count += 1
            else:
                skipped_count += 1

        if is_enabled:
            status_str = "active"
            msg = (
                f"Selective secondary verification inspected {verified_count} uncertain region(s), "
                f"skipped {skipped_count} reliable region(s), and generated {candidates_count} candidate(s)."
            )
        else:
            status_str = "secondary verification unavailable"
            msg = (
                f"secondary verification unavailable ({verified_count} uncertain region(s) "
                f"routed directly to manual human review; {skipped_count} reliable region(s) skipped)."
            )

        summary = VerificationSummary(
            enabled=is_enabled,
            provider=provider_name,
            status=status_str,
            total_regions=len(verified_regions),
            verified_region_count=verified_count,
            skipped_region_count=skipped_count,
            candidates_generated=candidates_count,
            message=msg,
        )
        return verified_regions, summary


def accept_ocr_region(region: RecognitionRegion) -> RecognitionRegion:
    """
    Human review action: accept the original raw OCR text for a region.
    Preserves `text` and `raw_ocr` untouched.
    """
    raw_ocr = region.raw_ocr if region.raw_ocr is not None else region.text
    return region.model_copy(
        update={
            "raw_ocr": raw_ocr,
            "review_status": "ACCEPTED",
            "final_text": raw_ocr,
            "human_verified": True,
        }
    )


def accept_candidate_region(region: RecognitionRegion) -> RecognitionRegion:
    """
    Human review action: accept the secondary verification candidate for a region.
    Preserves `region.text` and `region.raw_ocr` untouched while setting `final_text`
    to the accepted candidate.
    """
    sv = region.secondary_verification
    if sv is None or not sv.candidate_text:
        raise ValueError(
            "Cannot accept candidate: no secondary verification candidate is available for this region."
        )
    raw_ocr = region.raw_ocr if region.raw_ocr is not None else region.text
    return region.model_copy(
        update={
            "raw_ocr": raw_ocr,
            "review_status": "ACCEPTED",
            "final_text": sv.candidate_text,
            "human_verified": True,
        }
    )


def reject_candidate_region(region: RecognitionRegion) -> RecognitionRegion:
    """
    Human review action: reject the secondary verification candidate and retain
    the original raw OCR text (until manually corrected).
    Preserves `region.text` and `region.raw_ocr` untouched.
    """
    raw_ocr = region.raw_ocr if region.raw_ocr is not None else region.text
    return region.model_copy(
        update={
            "raw_ocr": raw_ocr,
            "review_status": "REJECTED",
            "final_text": raw_ocr,
            "human_verified": True,
        }
    )


def correct_region_text(region: RecognitionRegion, corrected_text: str) -> RecognitionRegion:
    """
    Human review action: manually correct the transcription for a region.
    Never overwrites `region.text` or `region.raw_ocr`; stores the human-verified
    transcription in `final_text` with `review_status = "CORRECTED"`.
    """
    if corrected_text is None:
        raise ValueError("Corrected text must not be None.")
    raw_ocr = region.raw_ocr if region.raw_ocr is not None else region.text
    return region.model_copy(
        update={
            "raw_ocr": raw_ocr,
            "review_status": "CORRECTED",
            "final_text": corrected_text,
            "human_verified": True,
        }
    )


def build_export_json(request: ReviewExportRequest) -> ExportJsonResponse:
    """
    Build a provenance-preserving JSON export structure from a reviewed document state.
    Preserves both raw OCR output and human-verified final output for every region.
    """
    filename = (request.filename or "").strip()
    if not filename:
        raise ValueError("Document filename is required for export.")

    exported_regions: List[ExportRegionProvenance] = []
    raw_lines: List[str] = []
    final_lines: List[str] = []
    any_human_verified = False

    for idx, item in enumerate(request.regions, start=1):
        raw_ocr = item.raw_ocr if item.raw_ocr is not None else ""
        status = item.review_status or "PENDING"

        if item.final_text is not None:
            resolved_final = item.final_text
        else:
            resolved_final = raw_ocr

        is_verified = (
            item.human_verified
            if item.human_verified is not None
            else (status in ("ACCEPTED", "CORRECTED", "REJECTED"))
        )
        if is_verified:
            any_human_verified = True

        exported_regions.append(
            ExportRegionProvenance(
                id=item.id if item.id is not None else idx,
                raw_ocr=raw_ocr,
                uncertainty=item.uncertainty,
                needs_review=item.needs_review,
                reasons=list(item.reasons),
                candidate_text=item.candidate_text,
                review_status=status,
                final_text=resolved_final,
                human_verified=bool(is_verified),
            )
        )
        raw_lines.append(raw_ocr)
        final_lines.append(resolved_final)

    raw_ocr_text = "\n".join(raw_lines)
    if request.final_text is not None:
        final_text = request.final_text
        if final_text != raw_ocr_text:
            any_human_verified = True
    else:
        final_text = "\n".join(final_lines)

    return ExportJsonResponse(
        document=ExportDocumentMetadata(
            filename=filename,
            engine=request.engine,
            overall_uncertainty=request.overall_uncertainty,
        ),
        raw_ocr_text=raw_ocr_text,
        regions=exported_regions,
        final_text=final_text,
        human_verified=any_human_verified,
    )


def build_export_txt(request: ReviewExportRequest) -> str:
    """
    Build a provenance-aware plain-text (.txt) transcription export.
    Includes the final verified transcription alongside the immutable raw OCR output
    and per-region review statuses.
    """
    export_data = build_export_json(request)
    lines: List[str] = [
        f"DOCUMENT: {export_data.document.filename}",
        f"HUMAN VERIFIED: {'YES' if export_data.human_verified else 'NO (PENDING REVIEW)'}",
        "",
        "=== FINAL VERIFIED TRANSCRIPTION ===",
        export_data.final_text,
        "",
        "=== RAW OCR OUTPUT (UNMODIFIED PROVENANCE) ===",
        export_data.raw_ocr_text,
    ]
    if export_data.regions:
        lines.append("")
        lines.append("=== REGION PROVENANCE LOG ===")
        for reg in export_data.regions:
            lines.append(
                f"[Region #{reg.id}] uncertainty={reg.uncertainty} | "
                f"status={reg.review_status} | human_verified={reg.human_verified} | "
                f"raw_ocr={reg.raw_ocr!r} -> final_text={reg.final_text!r}"
            )
    return "\n".join(lines) + "\n"
