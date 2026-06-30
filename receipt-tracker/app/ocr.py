import os

from google.cloud import vision

from app.config import GOOGLE_APPLICATION_CREDENTIALS

os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", GOOGLE_APPLICATION_CREDENTIALS)

_client = None


def get_client() -> vision.ImageAnnotatorClient:
    global _client
    if _client is None:
        _client = vision.ImageAnnotatorClient()
    return _client


def ocr_image(image_bytes: bytes) -> str:
    """Run Google Vision text detection and return the full extracted text block."""
    client = get_client()
    image = vision.Image(content=image_bytes)
    response = client.text_detection(image=image)

    if response.error.message:
        raise RuntimeError(f"Vision API error: {response.error.message}")

    if not response.text_annotations:
        return ""

    # First annotation is the full block of detected text.
    return response.text_annotations[0].description
