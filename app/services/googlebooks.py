import os
from typing import Any

import httpx
from dotenv import load_dotenv

from app.schemas.book import BookMetadata
from app.services.isbn import InvalidISBNError, isbn10_to_isbn13, isbn13_to_isbn10, normalize_isbn

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
        google_volume_id=data.get("id") if isinstance(data.get("id"), str) else None,
        metadata_source="google_books",
    )


def _equivalent_isbns(isbn: str) -> set[str]:
    normalized = normalize_isbn(isbn)
    values = {normalized}
    try:
        values.add(isbn10_to_isbn13(normalized) if len(normalized) == 10 else isbn13_to_isbn10(normalized))
    except InvalidISBNError:
        pass
    return values


def _book_has_isbn(data: dict[str, Any], isbns: set[str]) -> bool:
    info = data.get("volumeInfo")
    if not isinstance(info, dict):
        return False
    identifiers = info.get("industryIdentifiers")
    if not isinstance(identifiers, list):
        return False
    for identifier in identifiers:
        if not isinstance(identifier, dict) or not isinstance(identifier.get("identifier"), str):
            continue
        try:
            if _equivalent_isbns(identifier["identifier"]) & isbns:
                return True
        except InvalidISBNError:
            continue
    return False


class GoogleBooksService:
    base_url = "https://www.googleapis.com/books/v1/volumes"

    async def get_book_by_isbn(self, isbn: str) -> BookMetadata:
        normalized = normalize_isbn(isbn)
        accepted_isbns = _equivalent_isbns(normalized)
        query_values = [normalized]
        alternate = next((value for value in accepted_isbns if value != normalized), None)
        if alternate:
            query_values.append(alternate)
        api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                queries = [
                    *(f"isbn:{value}" for value in query_values),
                    *(f'"{value}"' for value in query_values),
                    *query_values,
                ]
                for query in queries:
                    params = {"q": query, "maxResults": 10}
                    if api_key:
                        params["key"] = api_key
                    response = await client.get(self.base_url, params=params)
                    if response.status_code >= 400:
                        raise GoogleBooksError(f"Google Books returned HTTP {response.status_code}")
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise GoogleBooksError("Google Books returned invalid JSON") from exc
                    items = payload.get("items") if isinstance(payload, dict) else None
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if isinstance(item, dict) and _book_has_isbn(item, accepted_isbns):
                            return parse_google_book(item, normalized)
        except httpx.HTTPError as exc:
            raise GoogleBooksError("Google Books could not be reached") from exc
        raise GoogleBooksNotFoundError(f"No book found for ISBN {normalized}")