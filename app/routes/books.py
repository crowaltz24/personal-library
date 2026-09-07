from fastapi import APIRouter, HTTPException

from app.schemas.book import BookMetadata
from app.services.openlibrary import (
    BookNotFoundError,
    InvalidISBNError,
    OpenLibraryError,
    OpenLibraryService,
)
from app.services.googlebooks import GoogleBooksError, GoogleBooksNotFoundError, GoogleBooksService

router = APIRouter(prefix="/books")
service = OpenLibraryService()
fallback_service = GoogleBooksService()


@router.get("/isbn/{isbn}", response_model=BookMetadata)
async def get_book_by_isbn(isbn: str) -> BookMetadata:
    try:
        return await service.get_book_by_isbn(isbn)
    except InvalidISBNError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (BookNotFoundError, OpenLibraryError):
        try:
            return await fallback_service.get_book_by_isbn(isbn)
        except GoogleBooksNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GoogleBooksError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    except OpenLibraryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc