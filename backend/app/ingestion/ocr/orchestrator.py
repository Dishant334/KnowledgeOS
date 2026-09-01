# app/ingestion/ocr/orchestrator.py

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from app.ingestion.ocr.detector import OCRDetector
from app.ingestion.ocr.rasterizer import PDFRasterizer
from app.ingestion.ocr.prepreocessor import ImagePreprocessor
from app.ingestion.ocr.tesseract import TesseractOCR
from app.ingestion.ocr.ocr_confidence import OCRConfidence

logger = logging.getLogger(__name__)


class OCRStageError(RuntimeError):
    """Raised when a specific stage of the OCR pipeline fails."""

    def __init__(self, stage: str, original: Exception):
        self.stage = stage
        self.original = original
        super().__init__(f"OCR pipeline failed at stage '{stage}': {original}")


@dataclass
class OCRAttempt:
    variant: str
    text: str
    confidence: Optional[float]


@dataclass
class OCRResult:
    text: str
    used_ocr: bool
    confidence: Optional[float] = None
    low_confidence: bool = False
    preprocessing_variant: Optional[str] = None
    attempts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class OCROrchestrator:

    # Order matters: first is the default, subsequent entries are
    # tried on retry if confidence is low.
    RETRY_VARIANTS = ["default", "no_binarize", "high_contrast"]

    def __init__(
        self,
        min_characters: int = 20,
        dpi: int = 300,
        language: str = "eng",
        psm: int = 6,
        oem: int = 3,
        timeout: int = 30,
        min_confidence: float = 60.0,
        max_retries: int = 1,
    ):
        self.detector = OCRDetector(min_characters=min_characters)
        self.rasterizer = PDFRasterizer(dpi=dpi)
        self.preprocessor = ImagePreprocessor()
        self.ocr = TesseractOCR(
            language=language,
            psm=psm,
            oem=oem,
            timeout=timeout,
        )
        self.confidence_checker = OCRConfidence(
            psm=psm,
            oem=oem,
            timeout=timeout,
        )
        self.language = language
        self.min_confidence = min_confidence
        self.max_retries = max_retries

    def process_page(
        self,
        pdf_data: bytes,
        page_number: int,
        extracted_text: str = "",
    ) -> OCRResult:

        warnings = []

        if not self.detector.needs_ocr(extracted_text):
            return OCRResult(
                text=extracted_text.strip(),
                used_ocr=False,
            )

        logger.info(
            "Page %s needs OCR (extracted text insufficient)",
            page_number,
        )

        # Stage: rasterize (done once, reused across retries)
        start = time.monotonic()
        try:
            image_data = self.rasterizer.rasterize(pdf_data, page_number)
        except Exception as exc:
            raise OCRStageError("rasterize", exc) from exc
        logger.debug(
            "Rasterized page %s in %.2fs",
            page_number,
            time.monotonic() - start,
        )

        attempts: list[OCRAttempt] = []
        variants_to_try = self.RETRY_VARIANTS[: self.max_retries + 1]

        for variant in variants_to_try:
            attempt = self._run_attempt(
                image_data=image_data,
                variant=variant,
                page_number=page_number,
            )
            attempts.append(attempt)

            confidence_ok = (
                attempt.confidence is not None
                and attempt.confidence >= self.min_confidence
            )
            if confidence_ok:
                break

            logger.info(
                "Page %s low confidence (%s) with variant '%s', "
                "trying next variant if available",
                page_number,
                attempt.confidence,
                variant,
            )

        # Pick the best attempt by confidence (None treated as worst).
        best = max(
            attempts,
            key=lambda a: (a.confidence if a.confidence is not None else -1),
        )

        low_confidence = (
            best.confidence is not None and best.confidence < self.min_confidence
        )

        if len(attempts) > 1:
            warnings.append(
                f"retried_preprocessing ({len(attempts)} attempts, "
                f"best='{best.variant}')"
            )

        if best.confidence is None:
            warnings.append("confidence_check_failed")

        if low_confidence:
            warnings.append(
                f"low_confidence ({best.confidence:.1f} < {self.min_confidence})"
            )
            logger.warning(
                "Page %s still low confidence after retries: best=%.1f (%s)",
                page_number,
                best.confidence,
                best.variant,
            )

        if self.detector.needs_ocr(best.text):
            warnings.append("ocr_output_still_insufficient")
            logger.warning(
                "OCR output for page %s still fails quality checks",
                page_number,
            )

        return OCRResult(
            text=best.text,
            used_ocr=True,
            confidence=best.confidence,
            low_confidence=low_confidence,
            preprocessing_variant=best.variant,
            attempts=attempts,
            warnings=warnings,
        )

    def _run_attempt(
        self,
        image_data: bytes,
        variant: str,
        page_number: int,
    ) -> OCRAttempt:
        start = time.monotonic()
        try:
            preprocessed = self.preprocessor.preprocess(image_data, variant=variant)
        except Exception as exc:
            raise OCRStageError(f"preprocess[{variant}]", exc) from exc
        logger.debug(
            "Preprocessed page %s (variant=%s) in %.2fs",
            page_number,
            variant,
            time.monotonic() - start,
        )

        start = time.monotonic()
        try:
            text = self.ocr.extract_text(preprocessed)
        except Exception as exc:
            raise OCRStageError(f"ocr_extract[{variant}]", exc) from exc
        logger.debug(
            "OCR extracted page %s (variant=%s) in %.2fs",
            page_number,
            variant,
            time.monotonic() - start,
        )

        try:
            confidence = self.confidence_checker.calculate(
                preprocessed,
                language=self.language,
            )
        except Exception as exc:
            logger.warning(
                "Confidence check failed for page %s (variant=%s): %s",
                page_number,
                variant,
                exc,
            )
            confidence = None

        return OCRAttempt(variant=variant, text=text, confidence=confidence)