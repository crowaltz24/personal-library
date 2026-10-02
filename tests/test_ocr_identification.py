from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.schemas.book import BookMetadata
from app.services import ocr_identification
from app.services.googlebooks import GoogleBooksError
from app.services.openlibrary import OpenLibraryError
from app.services.ocr import OCRBlock, OCRResult


def result(text: str, confidence: float = 90.0) -> OCRResult:
    return OCRResult(
        text=text,
        normalized_text="\n".join(line.strip() for line in text.splitlines() if line.strip()),
        blocks=[OCRBlock(text=text.splitlines()[0], confidence=confidence, bbox=(0, 0, 100, 20))],
        width=500,
        height=300,
        orientation=0,
        engine="fake",
    )


def image_upload():
    buffer = BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, format="PNG")
    return {"image": ("book.png", buffer.getvalue(), "image/png")}


def book(title: str, authors: list[str], isbn13: str | None = None) -> BookMetadata:
    return BookMetadata(
        title=title,
        authors=authors,
        isbn13=isbn13,
        metadata_source="openlibrary",
    )


@pytest.mark.anyio
async def test_clear_title_and_author_returns_strong_candidate(monkeypatch):
    monkeypatch.setattr(ocr_identification, "ocr_image", lambda _: result("The Hobbit\nJ.R.R. Tolkien"))

    async def search(self, **kwargs):
        return [book("The Hobbit", ["J.R.R. Tolkien"])]

    async def empty_search(self, **kwargs):
        return []

    monkeypatch.setattr(ocr_identification.OpenLibraryService, "search_books", search)
    monkeypatch.setattr(ocr_identification.GoogleBooksService, "search_books", empty_search)

    identified = await ocr_identification.identify_ocr_image(b"image")

    assert identified.candidates[0].metadata.title == "The Hobbit"
    assert identified.candidates[0].match_score > 0.8


@pytest.mark.anyio
async def test_imperfect_ocr_still_ranks_candidate(monkeypatch):
    monkeypatch.setattr(ocr_identification, "ocr_image", lambda _: result("THE HOBB1T\nJ R R TOLK1EN"))

    async def search(self, **kwargs):
        return [book("The Hobbit", ["J.R.R. Tolkien"])]

    async def empty_search(self, **kwargs):
        return []

    monkeypatch.setattr(ocr_identification.OpenLibraryService, "search_books", search)
    monkeypatch.setattr(ocr_identification.GoogleBooksService, "search_books", empty_search)

    identified = await ocr_identification.identify_ocr_image(b"image")

    assert identified.candidates
    assert identified.candidates[0].metadata.title == "The Hobbit"


@pytest.mark.anyio
async def test_valid_ocr_isbn_prefers_isbn_lookup(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr_identification, "ocr_image", lambda _: result("The Hobbit\n9780306406157"))

    async def isbn_lookup(self, isbn):
        calls.append(isbn)
        return book("The Hobbit", ["J.R.R. Tolkien"], isbn)

    async def search_books(self, **kwargs):
        raise AssertionError("ISBN OCR should not use title search")

    monkeypatch.setattr(ocr_identification.OpenLibraryService, "get_book_by_isbn", isbn_lookup)
    monkeypatch.setattr(ocr_identification.OpenLibraryService, "search_books", search_books)
    monkeypatch.setattr(ocr_identification.GoogleBooksService, "search_books", search_books)

    identified = await ocr_identification.identify_ocr_image(b"image")

    assert calls == ["9780306406157"]
    assert identified.candidates[0].match_score == 1.0


@pytest.mark.anyio
async def test_returns_multiple_ranked_candidates(monkeypatch):
    monkeypatch.setattr(ocr_identification, "ocr_image", lambda _: result("The Hobbit\nTolkien"))

    async def search(self, **kwargs):
        return [
            book("The Hobbit", ["J.R.R. Tolkien"], "9780306406157"),
            book("The Hobbit: Illustrated Edition", ["J.R.R. Tolkien"], "9780007525515"),
        ]

    async def empty_search(self, **kwargs):
        return []

    monkeypatch.setattr(ocr_identification.OpenLibraryService, "search_books", search)
    monkeypatch.setattr(ocr_identification.GoogleBooksService, "search_books", empty_search)

    identified = await ocr_identification.identify_ocr_image(b"image")

    assert len(identified.candidates) == 2
    assert identified.candidates[0].match_score >= identified.candidates[1].match_score


@pytest.mark.anyio
async def test_no_useful_ocr_returns_empty_candidates(monkeypatch):
    monkeypatch.setattr(ocr_identification, "ocr_image", lambda _: result("! | --"))

    identified = await ocr_identification.identify_ocr_image(b"image")

    assert identified.candidates == []
    assert identified.message == "No useful text detected"


@pytest.mark.anyio
async def test_no_metadata_match_returns_ocr_and_empty_candidates(monkeypatch):
    monkeypatch.setattr(ocr_identification, "ocr_image", lambda _: result("Unknown Book\nUnknown Author"))

    async def empty_search(self, **kwargs):
        return []

    monkeypatch.setattr(ocr_identification.OpenLibraryService, "search_books", empty_search)
    monkeypatch.setattr(ocr_identification.GoogleBooksService, "search_books", empty_search)

    identified = await ocr_identification.identify_ocr_image(b"image")

    assert identified.ocr.normalized_text == "Unknown Book\nUnknown Author"
    assert identified.candidates == []
    assert identified.message == "No matching books found"


@pytest.mark.anyio
async def test_provider_failure_is_not_an_opaque_server_error(monkeypatch):
    monkeypatch.setattr(ocr_identification, "ocr_image", lambda _: result("The Hobbit\nTolkien"))

    async def failed_openlibrary(self, **kwargs):
        raise OpenLibraryError("down")

    async def failed_googlebooks(self, **kwargs):
        raise GoogleBooksError("also down")

    monkeypatch.setattr(ocr_identification.OpenLibraryService, "search_books", failed_openlibrary)
    monkeypatch.setattr(ocr_identification.GoogleBooksService, "search_books", failed_googlebooks)

    identified = await ocr_identification.identify_ocr_image(b"image")

    assert identified.candidates == []
    assert identified.message == "Metadata providers were unavailable; no matching books found"


def test_identify_ocr_endpoint_is_frontend_ready(monkeypatch):
    async def fake_identify(_: bytes):
        return ocr_identification.OCRIdentificationResult(
            ocr=result("The Hobbit\nJ.R.R. Tolkien"),
            signals=ocr_identification.OCRSignals("The Hobbit", "J.R.R. Tolkien", [], 0.91),
            candidates=[
                ocr_identification.RankedBookCandidate(
                    book("The Hobbit", ["J.R.R. Tolkien"], "9780306406157"), 0.94
                )
            ],
            message=None,
        )

    monkeypatch.setattr("app.routes.scan.identify_ocr_image", fake_identify)
    response = TestClient(app).post("/api/scan/identify-ocr", files=image_upload())

    assert response.status_code == 200
    assert response.json()["detected"] is True
    assert response.json()["ocr"]["confidence"] == 0.91
    assert response.json()["candidates"][0]["match_score"] == 0.94


@pytest.mark.anyio
async def test_noisy_operating_systems_ocr_ranks_authors_over_sna(monkeypatch):
    monkeypatch.setattr(
        ocr_identification,
        "ocr_image",
        lambda _: result(
            "sna\nThe mati X book\nImplementation.\n6th\nAndrew § Tanenbaum\nAlbert § Woodhull"
        ),
    )
    correct = book(
        "Operating Systems: Design and Implementation",
        ["Andrew S. Tanenbaum", "Albert S. Woodhull"],
        "9780131429383",
    )
    unrelated = book("SNA", ["An Unrelated Author"], "9780000000002")

    async def search(self, **kwargs):
        return [unrelated, correct]

    monkeypatch.setattr(ocr_identification.OpenLibraryService, "search_books", search)
    monkeypatch.setattr(ocr_identification.GoogleBooksService, "search_books", search)

    identified = await ocr_identification.identify_ocr_image(b"image")

    assert identified.signals.authors == [
        "Andrew Tanenbaum",
        "Albert Woodhull",
    ]
    assert identified.signals.edition == "6th"
    assert identified.candidates[0].metadata.title.startswith("Operating Systems")
    assert identified.candidates[0].evidence["author_match"] > 0.8
    assert all(candidate.metadata.title != "SNA" for candidate in identified.candidates[:1])


def test_title_and_subtitle_are_kept_as_separate_signals():
    extracted = ocr_identification.extract_ocr_signals(
        result("Operating Systems\nDesign and Implementation\nAndrew S. Tanenbaum")
    )

    assert extracted.title == "Operating Systems"
    assert extracted.subtitle == "Design and Implementation"


@pytest.mark.anyio
async def test_low_information_ocr_does_not_create_candidate(monkeypatch):
    monkeypatch.setattr(ocr_identification, "ocr_image", lambda _: result("sna", confidence=15.0))

    async def search(self, **kwargs):
        return [book("SNA", ["Unrelated Author"])]

    monkeypatch.setattr(ocr_identification.OpenLibraryService, "search_books", search)
    monkeypatch.setattr(ocr_identification.GoogleBooksService, "search_books", search)

    identified = await ocr_identification.identify_ocr_image(b"image")

    assert identified.candidates == []