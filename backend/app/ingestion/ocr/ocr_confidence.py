# app/ingestion/ocr/ocr_confidence.py

import logging
from io import BytesIO

from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)


class OCRConfidence:

    def __init__(
        self,
        psm: int = 6,
        oem: int = 3,
        timeout: int = 30,
    ):
        self.config = f"--psm {psm} --oem {oem}"
        self.timeout = timeout

    def calculate(
        self,
        image_data: bytes,
        language: str = "eng",
    ) -> float:
        """
        Compute a length-weighted average OCR confidence for an image.

        Each recognized word contributes to the average in proportion
        to its character length, so a handful of short noise tokens
        can't skew the score as much as real, longer words.

        Returns a value in [0.0, 100.0]. Returns 0.0 if no text
        with valid confidence was found.
        """

        if not image_data:
            raise ValueError("Image data is empty")

        try:
            image = Image.open(BytesIO(image_data))

            data = pytesseract.image_to_data(
                image,
                lang=language,
                config=self.config,
                timeout=self.timeout,
                output_type=pytesseract.Output.DICT,
            )

            weighted_sum = 0.0
            total_weight = 0

            for confidence, text in zip(data["conf"], data["text"]):
                text = text.strip()

                if not text:
                    continue

                try:
                    confidence = float(confidence)
                except (TypeError, ValueError):
                    continue

                if confidence < 0:
                    continue

                weight = len(text)
                weighted_sum += confidence * weight
                total_weight += weight

            if total_weight == 0:
                return 0.0

            return weighted_sum / total_weight

        except RuntimeError as exc:
            logger.error("OCR confidence calculation timed out: %s", exc)
            raise RuntimeError(
                "Failed to calculate OCR confidence: timed out"
            ) from exc

        except Exception as exc:
            logger.error("Failed to calculate OCR confidence: %s", exc)
            raise RuntimeError(
                "Failed to calculate OCR confidence"
            ) from exc