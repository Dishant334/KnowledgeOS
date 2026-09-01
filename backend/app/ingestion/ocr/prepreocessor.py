from io import BytesIO

from PIL import Image, ImageEnhance, ImageFilter


class ImagePreprocessor:

    VARIANTS = ("default", "no_binarize", "high_contrast")

    def __init__(self, min_dimension: int = 1000):
        self.min_dimension = min_dimension

    def preprocess(self, image_data: bytes, variant: str = "default") -> bytes:
        """
        Prepare an image for OCR.

        variant:
            "default"       - grayscale, upscale, contrast, denoise, binarize
            "no_binarize"   - same as default but skips thresholding
                               (better for faint/low-contrast text that
                               binarization would erase)
            "high_contrast" - stronger contrast, no median filter
                               (better for faded scans where denoising
                               blurs thin strokes)
        """

        if not image_data:
            raise ValueError("Image data is empty")

        if variant not in self.VARIANTS:
            raise ValueError(f"Unknown variant '{variant}'. Options: {self.VARIANTS}")

        try:
            image = Image.open(BytesIO(image_data))
            image = image.convert("L")

            longest_side = max(image.size)
            if longest_side < self.min_dimension:
                factor = self.min_dimension / longest_side
                new_size = (
                    int(image.width * factor),
                    int(image.height * factor),
                )
                image = image.resize(new_size, Image.LANCZOS)

            if variant == "high_contrast":
                image = ImageEnhance.Contrast(image).enhance(2.2)
            else:
                image = ImageEnhance.Contrast(image).enhance(1.5)
                image = image.filter(ImageFilter.MedianFilter(size=3))

            if variant != "no_binarize":
                threshold = self._compute_threshold(image)
                image = image.point(lambda x: 255 if x > threshold else 0)

            output = BytesIO()
            image.save(output, format="PNG")

            return output.getvalue()

        except Exception as exc:
            raise ValueError("Failed to preprocess image") from exc

    @staticmethod
    def _compute_threshold(image: Image.Image) -> int:
        histogram = image.histogram()
        pixels = sum(histogram)
        mean = sum(i * count for i, count in enumerate(histogram)) / pixels
        return int(mean)