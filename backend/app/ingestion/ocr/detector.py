import re


class OCRDetector:

    def __init__(
        self,
        min_characters: int = 20,
        min_words: int = 3,
        max_whitespace_ratio: float = 0.6,
        min_alnum_ratio: float = 0.4,
    ):
        self.min_characters = min_characters
        self.min_words = min_words
        self.max_whitespace_ratio = max_whitespace_ratio
        self.min_alnum_ratio = min_alnum_ratio

    def needs_ocr(self, content: str) -> bool:
        """
        Decide whether OCR is required for a page.

        Returns True when the extracted text is empty, too small,
        mostly whitespace, mostly non-alphanumeric junk, or has too
        few real words to be considered useful.
        """

        if not content:
            return True

        content = content.strip()

        if len(content) < self.min_characters:
            return True

        # Ratio 1: whitespace vs total length.
        # Catches pages that "have characters" but are mostly
        # blank space, tabs, or newlines
        whitespace_count = sum(1 for ch in content if ch.isspace())
        whitespace_ratio = whitespace_count / len(content)
        if whitespace_ratio > self.max_whitespace_ratio:
            return True

        # Ratio 2: alphanumeric vs total length.
        # Catches pages full of symbols/noise (e.g. "----- ### ---")
        alnum_count = sum(1 for ch in content if ch.isalnum())
        alnum_ratio = alnum_count / len(content)
        if alnum_ratio < self.min_alnum_ratio:
            return True

        # Word count: guards against long single "words"
        # (e.g. repeated characters, no real spacing) that pass
        word_count = len(re.findall(r"\b\w+\b", content))
        if word_count < self.min_words:
            return True

        return False