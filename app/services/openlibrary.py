from typing import Any

import httpx

from app.schemas.book import BookMetadata
from app.services.isbn import InvalidISBNError, normalize_isbn


class BookNotFoundError(LookupError):
    pass


class OpenLibraryError(RuntimeError):
    pass


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("value"), str):
        return value["value"]
    return None


def _names(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        if isinstance(value, str):
            result.append(value)
        elif isinstance(value, dict):
            name = value.get("name") or value.get("key")
            if isinstance(name, str):
                result.append(name.rsplit("/", 1)[-1] if name.startswith("/") else name)
    return result


def parse_openlibrary_book(data: dict[str, Any], isbn: str) -> BookMetadata:
    key = data.get("key")
    edition_id = key.rsplit("/", 1)[-1] if isinstance(key, str) else None
    works = data.get("works")
    work_id = None
    if isinstance(works, list) and works and isinstance(works[0], dict):
        work_key = works[0].get("key")
        work_id = work_key.rsplit("/", 1)[-1] if isinstance(work_key, str) else None

    isbn10_values = data.get("isbn_10")
    isbn13_values = data.get("isbn_13")
    isbn10 = isbn10_values[0] if isinstance(isbn10_values, list) and isbn10_values else None
    isbn13 = isbn13_values[0] if isinstance(isbn13_values, list) and isbn13_values else None
    if len(isbn) == 10:
        isbn10 = isbn
    else:
        isbn13 = isbn

    cover_id = data.get("cover_i")
    cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None
    return BookMetadata(
        isbn10=isbn10,
        isbn13=isbn13,
        title=data.get("title"),
        authors=_names(data.get("authors")),
        publisher=(data.get("publishers") or [None])[0],
        publication_date=data.get("publish_date"),
        description=_text(data.get("description")),
        subjects=_names(data.get("subjects")),
        cover_url=cover_url,
        openlibrary_work_id=work_id,
        openlibrary_edition_id=edition_id,
    )


class OpenLibraryService:
    base_url = "https://openlibrary.org/isbn"

    async def get_book_by_isbn(self, isbn: str) -> BookMetadata:
        normalized = normalize_isbn(isbn)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/{normalized}.json")
        except httpx.HTTPError as exc:
            raise OpenLibraryError("Open Library could not be reached") from exc

        if response.status_code == 404:
            raise BookNotFoundError(f"No book found for ISBN {normalized}")
        if response.status_code >= 400:
            raise OpenLibraryError(f"Open Library returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenLibraryError("Open Library returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise OpenLibraryError("Open Library returned an unexpected response")
        return parse_openlibrary_book(payload, normalized)