import argparse
import asyncio
import json
from pathlib import Path

from app.services.barcode import InvalidImageError, decode_isbn_barcodes
from app.services.googlebooks import GoogleBooksError, GoogleBooksNotFoundError, GoogleBooksService
from app.services.openlibrary import BookNotFoundError, OpenLibraryError, OpenLibraryService


async def scan_book(image_path: Path) -> dict:
    candidates = decode_isbn_barcodes(image_path.read_bytes())
    result = {
        "image": str(image_path),
        "detected": bool(candidates),
        "candidates": [
            {"isbn": candidate.isbn, "format": candidate.format}
            for candidate in candidates
        ],
        "books": [],
    }
    openlibrary = OpenLibraryService()
    googlebooks = GoogleBooksService()
    for candidate in candidates:
        try:
            book = await openlibrary.get_book_by_isbn(candidate.isbn)
            provider = "openlibrary"
        except BookNotFoundError:
            try:
                book = await googlebooks.get_book_by_isbn(candidate.isbn)
                provider = "googlebooks"
            except GoogleBooksNotFoundError:
                result["books"].append({"isbn": candidate.isbn, "metadata_found": False})
                continue
            except GoogleBooksError as exc:
                result["books"].append({"isbn": candidate.isbn, "metadata_found": False, "error": str(exc)})
                continue
        except OpenLibraryError as exc:
            result["books"].append({"isbn": candidate.isbn, "metadata_found": False, "error": str(exc)})
            continue
        result["books"].append({"isbn": candidate.isbn, "provider": provider, "metadata_found": True, "metadata": book.model_dump()})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a book image for ISBN barcodes and metadata.")
    parser.add_argument("--image", required=True, help="Path to the book image")
    args = parser.parse_args()
    image_path = Path(args.image)
    if not image_path.is_file():
        parser.error(f"Image file not found: {image_path}")
    try:
        result = asyncio.run(scan_book(image_path))
    except InvalidImageError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())