import io

import numpy as np
from PIL import Image

_reader = None


def get_reader():
    global _reader
    if _reader is None:
        import easyocr  # lazy: avoids loading torch at import time and during tests
        _reader = easyocr.Reader(['en', 'he'], gpu=False)
    return _reader


def ocr_image(image_bytes: bytes) -> str:
    """Run EasyOCR text detection and return the full extracted text block."""
    reader = get_reader()
    image = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    results = reader.readtext(image)
    return "\n".join(text for _, text, _ in results)
