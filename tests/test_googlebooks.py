import httpx
import pytest

from app.services.googlebooks import GoogleBooksNotFoundError, GoogleBooksService, parse_google_book


def test_parse_google_book():
    book = parse_google_book(
        {
            "volumeInfo": {
                "title": "A Google Book",
                "authors": ["An Author"],
                "publisher": "A Publisher",
                "publishedDate": "2024",
                "description": "A description",
                "categories": ["Fiction"],
                "imageLinks": {"thumbnail": "http://example.test/cover.jpg"},
                "industryIdentifiers": [
                    {"type": "ISBN_10", "identifier": "0306406152"},
                    {"type": "ISBN_13", "identifier": "9780306406157"},
                ],
            }
        },
        "9780306406157",
    )
    assert book.title == "A Google Book"
    assert book.isbn10 == "0306406152"
    assert book.isbn13 == "9780306406157"


@pytest.mark.anyio
async def test_google_books_not_found(monkeypatch):
    async def fake_get(self, url, params):
        return httpx.Response(200, json={"totalItems": 0}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    with pytest.raises(GoogleBooksNotFoundError):
        await GoogleBooksService().get_book_by_isbn("9780306406157")