from dataclasses import dataclass
from io import BytesIO

import zxingcpp
from PIL import Image, ImageEnhance, ImageOps

from app.services.isbn import isbn_from_barcode


class InvalidImageError(ValueError):
    pass


@dataclass(frozen=True)
class BarcodeCandidate:
    isbn: str
    format: str


def _format_name(barcode) -> str:
    value = str(barcode.format)
    return value.removeprefix("BarcodeFormat.")


def _decode(image: Image.Image) -> list:
    return list(zxingcpp.read_barcodes(image))


def decode_isbn_barcodes(image_bytes: bytes) -> list[BarcodeCandidate]:
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise InvalidImageError("The uploaded file is not a readable image") from exc

    attempts = [image]
    grayscale = ImageOps.grayscale(image)
    attempts.extend([
        ImageOps.autocontrast(grayscale),
        ImageEnhance.Contrast(ImageOps.autocontrast(grayscale)).enhance(1.8),
    ])
    if max(image.size) < 1200:
        scale = 1200 / max(image.size)
        attempts.append(image.resize((round(image.width * scale), round(image.height * scale))))

    candidates: dict[str, BarcodeCandidate] = {}
    for attempt in attempts:
        for barcode in _decode(attempt):
            isbn = isbn_from_barcode(barcode.text)
            if isbn:
                candidates[isbn] = BarcodeCandidate(isbn=isbn, format=_format_name(barcode))
    return list(candidates.values())