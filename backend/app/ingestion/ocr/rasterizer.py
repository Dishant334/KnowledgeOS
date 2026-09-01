import fitz


class PDFRasterizer:

    def __init__(self, dpi: int = 300):
        if dpi <= 0:
            raise ValueError("dpi must be a positive integer")
        self.dpi = dpi

    def rasterize(
        self,
        data: bytes,
        page_number: int,
    ) -> bytes:

        if not data:
            raise ValueError("PDF data is empty")

        if not isinstance(page_number, int) or page_number < 1:
            raise ValueError("Page number must be an integer >= 1")

        pdf = None

        try:
            try:
                pdf = fitz.open(stream=data, filetype="pdf")
            except Exception as exc:
                raise ValueError("Failed to open PDF data") from exc

            if page_number > len(pdf):
                raise ValueError(
                    f"Page number {page_number} "
                    f"exceeds PDF page count {len(pdf)}"
                )

            # Our page_number is 1-based.
            # PyMuPDF uses 0-based indexing.
            page = pdf[page_number - 1]

            # PDF points are based on 72 DPI.
            scale = self.dpi / 72
            matrix = fitz.Matrix(scale, scale)

            pixmap = page.get_pixmap(matrix=matrix, alpha=False)

            return pixmap.tobytes("png")

        finally:
            if pdf is not None:
                pdf.close()