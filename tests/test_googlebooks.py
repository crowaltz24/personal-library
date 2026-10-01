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


@pytest.mark.anyio
async def test_google_books_uses_exact_match_after_qualified_queries(monkeypatch):
    async def fake_get(self, url, params):
        if params["q"].startswith("isbn:"):
            return httpx.Response(200, json={"totalItems": 0}, request=httpx.Request("GET", url))
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "exact-volume",
                        "volumeInfo": {
                            "title": "Exact match",
                            "industryIdentifiers": [
                                {"type": "ISBN_13", "identifier": "9780306406157"},
                            ],
                        },
                    }
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    book = await GoogleBooksService().get_book_by_isbn("9780306406157")

    assert book.title == "Exact match"
    assert book.google_volume_id == "exact-volume"


@pytest.mark.anyio
async def test_google_books_rejects_unrelated_raw_results(monkeypatch):
    async def fake_get(self, url, params):
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "wrong-volume",
                        "volumeInfo": {
                            "title": "Wrong book",
                            "industryIdentifiers": [
                                {"type": "ISBN_13", "identifier": "9781491934494"},
                            ],
                        },
                    }
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    with pytest.raises(GoogleBooksNotFoundError):
        await GoogleBooksService().get_book_by_isbn("9780306406157")


@pytest.mark.anyio
async def test_google_books_uses_quoted_exact_isbn_query(monkeypatch):
    async def fake_get(self, url, params):
        if params["q"] != '"9789352763344"':
            return httpx.Response(200, json={"totalItems": 0}, request=httpx.Request("GET", url))
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "P1FnDwAAQBAJ",
                        "volumeInfo": {
                            "title": "The Originals: The Brothers Karamazov",
                            "industryIdentifiers": [
                                {"type": "ISBN_13", "identifier": "9789352763344"},
                                {"type": "ISBN_10", "identifier": "9352763343"},
                            ],
                        },
                    }
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    book = await GoogleBooksService().get_book_by_isbn("9789352763344")

    assert book.title == "The Originals: The Brothers Karamazov"
    assert book.google_volume_id == "P1FnDwAAQBAJ"