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
        metadata_source="openlibrary",
    )


def parse_openlibrary_search_book(data: dict[str, Any], isbn: str) -> BookMetadata:
    isbn10 = None
    isbn13 = None
    identifiers = data.get("isbn")
    if isinstance(identifiers, list):
        for identifier in identifiers:
            if not isinstance(identifier, str):
                continue
            try:
                normalized_identifier = normalize_isbn(identifier)
            except InvalidISBNError:
                continue
            if len(normalized_identifier) == 10:
                isbn10 = normalized_identifier
            else:
                isbn13 = normalized_identifier
    if len(isbn) == 10:
        isbn10 = isbn
    else:
        isbn13 = isbn
    return BookMetadata(
        isbn10=isbn10,
        isbn13=isbn13,
        title=data.get("title"),
        authors=_names(data.get("author_name")),
        publisher=(data.get("publisher") or [None])[0] if isinstance(data.get("publisher"), list) else None,
        publication_date=(data.get("publish_date") or [None])[0] if isinstance(data.get("publish_date"), list) else None,
        subjects=_names(data.get("subject")),
        cover_url=(
            f"https://covers.openlibrary.org/b/id/{data['cover_i']}-L.jpg"
            if data.get("cover_i")
            else None
        ),
        metadata_source="openlibrary",
    )


class OpenLibraryService:
    base_url = "https://openlibrary.org/isbn"
    search_url = "https://openlibrary.org/search.json"

    async def get_book_by_isbn(self, isbn: str) -> BookMetadata:
        normalized = normalize_isbn(isbn)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/{normalized}.json")
        except httpx.HTTPError as exc:
            raise OpenLibraryError("Open Library could not be reached") from exc

        if response.status_code == 404 or 300 <= response.status_code < 400:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    search_response = await client.get(
                        self.search_url,
                        params={"q": f"isbn:{normalized}", "limit": 5, "fields": "*,isbn"},
                    )
            except httpx.HTTPError as exc:
                raise OpenLibraryError("Open Library could not be reached") from exc
            if search_response.status_code >= 400:
                raise OpenLibraryError(f"Open Library returned HTTP {search_response.status_code}")
            try:
                search_payload = search_response.json()
            except ValueError as exc:
                raise OpenLibraryError("Open Library returned invalid JSON") from exc
            docs = search_payload.get("docs") if isinstance(search_payload, dict) else None
            if isinstance(docs, list):
                for document in docs:
                    if not isinstance(document, dict):
                        continue
                    identifiers = document.get("isbn")
                    normalized_identifiers = set()
                    if isinstance(identifiers, list):
                        for identifier in identifiers:
                            if not isinstance(identifier, str):
                                continue
                            try:
                                normalized_identifiers.add(normalize_isbn(identifier))
                            except InvalidISBNError:
                                continue
                    if normalized in normalized_identifiers:
                        return parse_openlibrary_search_book(document, normalized)
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