import os
from typing import Any

import httpx
from dotenv import load_dotenv

from app.schemas.book import BookMetadata
from app.services.isbn import InvalidISBNError, normalize_isbn

load_dotenv()


class GoogleBooksNotFoundError(LookupError):
    pass


class GoogleBooksError(RuntimeError):
    pass


def _isbn_identifiers(values: Any) -> tuple[str | None, str | None]:
    isbn10 = None
    isbn13 = None
    if isinstance(values, list):
        for value in values:
            if not isinstance(value, dict):
                continue
            identifier = value.get("identifier")
            if not isinstance(identifier, str):
                continue
            try:
                normalized = normalize_isbn(identifier)
            except InvalidISBNError:
                continue
            if len(normalized) == 10:
                isbn10 = normalized
            else:
                isbn13 = normalized
    return isbn10, isbn13


def parse_google_book(data: dict[str, Any], requested_isbn: str) -> BookMetadata:
    info = data.get("volumeInfo")
    if not isinstance(info, dict):
        raise GoogleBooksError("Google Books returned an unexpected volume")

    isbn10, isbn13 = _isbn_identifiers(info.get("industryIdentifiers"))
    normalized_requested = normalize_isbn(requested_isbn)
    if len(normalized_requested) == 10:
        isbn10 = normalized_requested
    else:
        isbn13 = normalized_requested
    image_links = info.get("imageLinks")
    cover_url = image_links.get("thumbnail") if isinstance(image_links, dict) else None
    return BookMetadata(
        isbn10=isbn10,
        isbn13=isbn13,
        title=info.get("title"),
        authors=info.get("authors") if isinstance(info.get("authors"), list) else [],
        publisher=info.get("publisher"),
        publication_date=info.get("publishedDate"),
        description=info.get("description"),
        subjects=info.get("categories") if isinstance(info.get("categories"), list) else [],
        cover_url=cover_url,
    )


class GoogleBooksService:
    base_url = "https://www.googleapis.com/books/v1/volumes"

    async def get_book_by_isbn(self, isbn: str) -> BookMetadata:
        normalized = normalize_isbn(isbn)
        params = {"q": f"isbn:{normalized}", "maxResults": 1}
        api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
        if api_key:
            params["key"] = api_key
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
        except httpx.HTTPError as exc:
            raise GoogleBooksError("Google Books could not be reached") from exc

        if response.status_code >= 400:
            raise GoogleBooksError(f"Google Books returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleBooksError("Google Books returned invalid JSON") from exc
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            raise GoogleBooksNotFoundError(f"No book found for ISBN {normalized}")
        return parse_google_book(items[0], normalized)