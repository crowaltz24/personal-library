from io import BytesIO

from PIL import Image, ImageEnhance, ImageOps


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_DIMENSION = 2400


class InvalidImageError(ValueError):
    pass


def load_image(image_bytes: bytes) -> Image.Image:
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise InvalidImageError("The uploaded image is empty or too large")
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Exception as exc:
        raise InvalidImageError("The uploaded file is not a readable image") from exc
    return image


def prepare_for_ocr(image: Image.Image) -> Image.Image:
    if max(image.size) > MAX_IMAGE_DIMENSION:
        scale = MAX_IMAGE_DIMENSION / max(image.size)
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    grayscale = ImageOps.grayscale(image)
    enhanced = ImageOps.autocontrast(grayscale)
    return ImageEnhance.Contrast(enhanced).enhance(1.4)