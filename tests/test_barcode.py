from types import SimpleNamespace
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services import barcode


def image_upload():
    buffer = BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, format="PNG")
    return {"image": ("book.png", buffer.getvalue(), "image/png")}


def test_successful_barcode_extraction(monkeypatch):
    monkeypatch.setattr(
        barcode,
        "_decode",
        lambda _: [SimpleNamespace(text="9780306406157", format="EAN13")],
    )
    response = TestClient(app).post("/api/scan/barcode", files=image_upload())
    assert response.status_code == 200
    assert response.json() == {"detected": True, "candidates": [{"isbn": "9780306406157", "format": "EAN13"}]}


def test_no_barcode_detected(monkeypatch):
    monkeypatch.setattr(barcode, "_decode", lambda _: [])
    response = TestClient(app).post("/api/scan/barcode", files=image_upload())
    assert response.status_code == 200
    assert response.json() == {"detected": False, "candidates": []}


def test_invalid_image():
    response = TestClient(app).post(
        "/api/scan/barcode",
        files={"image": ("book.png", b"not-an-image", "image/png")},
    )
    assert response.status_code == 400


def test_non_isbn_barcode_is_ignored(monkeypatch):
    monkeypatch.setattr(
        barcode,
        "_decode",
        lambda _: [SimpleNamespace(text="4006381333931", format="EAN13")],
    )
    response = TestClient(app).post("/api/scan/barcode", files=image_upload())
    assert response.status_code == 200
    assert response.json() == {"detected": False, "candidates": []}


def test_multiple_isbn_barcodes(monkeypatch):
    monkeypatch.setattr(
        barcode,
        "_decode",
        lambda _: [
            SimpleNamespace(text="9780306406157", format="EAN13"),
            SimpleNamespace(text="9780131103627", format="EAN13"),
        ],
    )
    response = TestClient(app).post("/api/scan/barcode", files=image_upload())
    assert response.status_code == 200
    assert {item["isbn"] for item in response.json()["candidates"]} == {"9780306406157", "9780131103627"}