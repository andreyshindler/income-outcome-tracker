import io

import pytesseract
from PIL import Image


def ocr_image(image_bytes: bytes) -> str:
    """Run Tesseract OCR (Hebrew + English) and return extracted text."""
    image = Image.open(io.BytesIO(image_bytes))
    return pytesseract.image_to_string(image, lang='heb+eng')
