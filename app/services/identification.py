from typing import Any

from app.schemas.book import BookMetadata
from app.services.barcode import decode_isbn_barcodes
from app.services.googlebooks import GoogleBooksError, GoogleBooksNotFoundError, GoogleBooksService
from app.services.openlibrary import BookNotFoundError, OpenLibraryError, OpenLibraryService


async def identify_book_image(image_bytes: bytes) -> list[dict[str, Any]]:
    barcode_candidates = decode_isbn_barcodes(image_bytes)
    openlibrary = OpenLibraryService()
    googlebooks = GoogleBooksService()
    identified = []
    for barcode in barcode_candidates:
        metadata: BookMetadata | None = None
        source_error = None
        try:
            metadata = await openlibrary.get_book_by_isbn(barcode.isbn)
        except (BookNotFoundError, OpenLibraryError) as exc:
            source_error = str(exc)
            try:
                metadata = await googlebooks.get_book_by_isbn(barcode.isbn)
            except GoogleBooksNotFoundError as fallback_exc:
                source_error = str(fallback_exc)
            except GoogleBooksError as fallback_exc:
                source_error = str(fallback_exc)
        identified.append({
            "isbn": barcode.isbn,
            "format": barcode.format,
            "metadata": metadata,
            "metadata_found": metadata is not None,
            "error": source_error if metadata is None else None,
        })
    return identified