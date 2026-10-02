import shutil
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app
from app.services import ocr


def image_bytes(text: str = "") -> bytes:
    image = Image.new("RGB", (500, 160), "white")
    if text:
        ImageDraw.Draw(image).text((20, 50), text, fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeTesseract:
    class Output:
        DICT = object()

    @staticmethod
    def get_tesseract_version():
        return "fake"

    @staticmethod
    def image_to_osd(_image):
        return "Rotate: 0"

    @staticmethod
    def image_to_string(_image, config):
        assert config == "--psm 11"
        return "  THE   HOBBIT  \n\n"

    @staticmethod
    def image_to_data(_image, config, output_type):
        assert config == "--psm 11"
        assert output_type is FakeTesseract.Output.DICT
        return {
            "text": ["", "THE", "HOBBIT"],
            "conf": ["-1", "94.2", "88.0"],
            "left": ["0", "20", "80"],
            "top": ["0", "50", "50"],
            "width": ["0", "40", "60"],
            "height": ["0", "20", "20"],
        }


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_ocr_returns_text_and_structured_blocks(monkeypatch, client):
    monkeypatch.setattr(ocr, "pytesseract", FakeTesseract)

    response = client.post(
        "/api/scan/ocr",
        files={"image": ("book.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "  THE   HOBBIT  \n\n"
    assert body["normalized_text"] == "THE HOBBIT"
    assert body["blocks"] == [
        {"text": "THE", "confidence": 94.2, "bbox": [20, 50, 40, 20]},
        {"text": "HOBBIT", "confidence": 88.0, "bbox": [80, 50, 60, 20]},
    ]
    assert body["message"] is None


def test_ocr_empty_result_is_successful_no_text_response(monkeypatch, client):
    monkeypatch.setattr(
        ocr,
        "pytesseract",
        SimpleNamespace(
            Output=SimpleNamespace(DICT=object()),
            get_tesseract_version=lambda: "fake",
            image_to_osd=lambda _: "Rotate: 0",
            image_to_string=lambda _, config: "",
            image_to_data=lambda _, config, output_type: {
                "text": [], "conf": [], "left": [], "top": [], "width": [], "height": []
            },
        ),
    )

    response = client.post(
        "/api/scan/ocr",
        files={"image": ("blank.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["blocks"] == []
    assert response.json()["message"] == "No readable text detected"


def test_ocr_rejects_invalid_image(client):
    response = client.post(
        "/api/scan/ocr",
        files={"image": ("book.png", b"not-an-image", "image/png")},
    )
    assert response.status_code == 400


def test_ocr_rejects_oversized_image(client):
    response = client.post(
        "/api/scan/ocr",
        files={"image": ("book.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")},
    )
    assert response.status_code == 400


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_real_book_fixture_contains_readable_text():
    result = ocr.ocr_image(Path("test-images/cnfront.jpeg").read_bytes())
    assert result.blocks
    assert "COMPUTER NETWORKS" in " ".join(result.text.upper().split())