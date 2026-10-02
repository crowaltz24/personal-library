from dataclasses import dataclass
from typing import Any

from PIL import Image

from app.services.image_preprocessing import load_image, prepare_for_ocr
from app.services.text_normalization import normalize_ocr_text

try:
    import pytesseract
except ImportError:  # pragma: no cover - exercised in deployment environments
    pytesseract = None


class OCREngineUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class OCRBlock:
    text: str
    confidence: float | None
    bbox: tuple[int, int, int, int]


@dataclass(frozen=True)
class OCRResult:
    text: str
    normalized_text: str
    blocks: list[OCRBlock]
    width: int
    height: int
    orientation: int | None
    engine: str


def _require_engine():
    if pytesseract is None:
        raise OCREngineUnavailableError("Tesseract OCR is not installed")
    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:
        raise OCREngineUnavailableError(
            "Tesseract OCR is not installed or is not available on PATH"
        ) from exc
    return pytesseract


def _detect_orientation(engine, image: Image.Image) -> int | None:
    try:
        output = engine.image_to_osd(image)
    except Exception:
        return None
    for line in output.splitlines():
        if line.startswith("Rotate:"):
            try:
                return int(line.split(":", 1)[1].strip()) % 360
            except ValueError:
                return None
    return None


def _blocks_from_data(data: dict[str, list[Any]]) -> list[OCRBlock]:
    blocks = []
    for index, value in enumerate(data.get("text", [])):
        text = str(value).strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index])
        except (KeyError, IndexError, TypeError, ValueError):
            confidence = None
        if confidence is not None and confidence < 0:
            confidence = None
        try:
            bbox = tuple(
                int(data[key][index]) for key in ("left", "top", "width", "height")
            )
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        blocks.append(OCRBlock(text=text, confidence=confidence, bbox=bbox))
    return blocks


def ocr_image(image_bytes: bytes) -> OCRResult:
    image = load_image(image_bytes)
    prepared = prepare_for_ocr(image)
    engine = _require_engine()
    orientation = _detect_orientation(engine, prepared)
    if orientation:
        prepared = prepared.rotate(-orientation, expand=True)

    raw_text = engine.image_to_string(prepared, config="--psm 11")
    data = engine.image_to_data(prepared, config="--psm 11", output_type=engine.Output.DICT)
    return OCRResult(
        text=raw_text,
        normalized_text=normalize_ocr_text(raw_text),
        blocks=_blocks_from_data(data),
        width=prepared.width,
        height=prepared.height,
        orientation=orientation,
        engine="tesseract",
    )