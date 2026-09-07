from pathlib import Path

import pytest

from app.schemas.book import BookMetadata
from app.services.barcode import BarcodeCandidate
from app.services.openlibrary import OpenLibraryError
from scan_book import scan_book


@pytest.mark.anyio
async def test_scan_falls_back_after_openlibrary_error(monkeypatch, tmp_path: Path):
    image_path = tmp_path / "book.png"
    image_path.write_bytes(b"image")

    monkeypatch.setattr(
        "scan_book.decode_isbn_barcodes",
        lambda _: [BarcodeCandidate(isbn="9780306406157", format="EAN13")],
    )

    async def openlibrary_failure(self, isbn):
        raise OpenLibraryError("Open Library returned invalid JSON")

    async def googlebooks_success(self, isbn):
        return BookMetadata(isbn13=isbn, title="Fallback book")

    monkeypatch.setattr("scan_book.OpenLibraryService.get_book_by_isbn", openlibrary_failure)
    monkeypatch.setattr("scan_book.GoogleBooksService.get_book_by_isbn", googlebooks_success)

    result = await scan_book(image_path)

    assert result["books"][0]["provider"] == "googlebooks"
    assert result["books"][0]["metadata"]["title"] == "Fallback book"