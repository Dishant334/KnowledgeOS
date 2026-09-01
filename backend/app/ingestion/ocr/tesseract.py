import logging
from io import BytesIO

from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)


class TesseractOCR:

    def __init__(
        self,
        language: str = "eng",
        psm: int = 6,
        oem: int = 3,
        timeout: int = 30,
    ):
        try:
            available = pytesseract.get_languages(config="")
        except Exception:
            available = None  # skip check if tesseract can't report langs

        if available is not None and language not in available:
            raise ValueError(
                f"Language '{language}' is not installed. "
                f"Available: {available}"
            )

        self.language = language
        self.config = f"--psm {psm} --oem {oem}"
        self.timeout = timeout

    def extract_text(
        self,
        image_data: bytes,
    ) -> str:

        if not image_data:
            raise ValueError("Image data is empty")

        try:
            image = Image.open(BytesIO(image_data))

            text = pytesseract.image_to_string(
                image,
                lang=self.language,
                config=self.config,
                timeout=self.timeout,
            )

            return text.strip()

        except RuntimeError as exc:
            # pytesseract raises RuntimeError on timeout
            logger.error("Tesseract OCR timed out: %s", exc)
            raise RuntimeError("Tesseract OCR timed out") from exc

        except Exception as exc:
            logger.error("Tesseract OCR failed: %s", exc)
            raise RuntimeError("Tesseract OCR failed") from exc