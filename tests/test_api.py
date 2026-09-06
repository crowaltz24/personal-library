import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.openlibrary import BookNotFoundError, OpenLibraryError
from app.routes import books


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_invalid_isbn(client):
    response = client.get("/api/books/isbn/not-an-isbn")
    assert response.status_code == 400


def test_not_found(monkeypatch, client):
    async def missing(_: str):
        raise BookNotFoundError("missing")

    monkeypatch.setattr(books.service, "get_book_by_isbn", missing)
    async def fallback_missing(_: str):
        from app.services.googlebooks import GoogleBooksNotFoundError
        raise GoogleBooksNotFoundError("missing")

    monkeypatch.setattr(books.fallback_service, "get_book_by_isbn", fallback_missing)
    assert client.get("/api/books/isbn/9780306406157").status_code == 404


def test_google_books_fallback(monkeypatch, client):
    async def missing(_: str):
        raise BookNotFoundError("missing")

    async def fallback(_: str):
        from app.schemas.book import BookMetadata
        return BookMetadata(title="Fallback book", isbn13="9780306406157")

    monkeypatch.setattr(books.service, "get_book_by_isbn", missing)
    monkeypatch.setattr(books.fallback_service, "get_book_by_isbn", fallback)
    response = client.get("/api/books/isbn/9780306406157")
    assert response.status_code == 200
    assert response.json()["title"] == "Fallback book"


def test_external_failure(monkeypatch, client):
    async def failed(_: str):
        raise OpenLibraryError("down")

    monkeypatch.setattr(books.service, "get_book_by_isbn", failed)
    assert client.get("/api/books/isbn/9780306406157").status_code == 502


def test_successful_lookup(monkeypatch, client):
    async def fake_get(self, url):
        return httpx.Response(
            200,
            json={
                "key": "/books/OL1M",
                "title": "A Book",
                "authors": [{"name": "An Author"}],
                "publishers": ["A Publisher"],
                "publish_date": "2020",
                "description": {"value": "A description."},
                "subjects": [{"name": "Fiction"}],
                "cover_i": 123,
                "works": [{"key": "/works/OL2W"}],
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    response = client.get("/api/books/isbn/978-0-306-40615-7")
    assert response.status_code == 200
    assert response.json()["title"] == "A Book"
    assert response.json()["authors"] == ["An Author"]
    assert response.json()["openlibrary_work_id"] == "OL2W"