from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import Book, LibraryEntry, User
from app.schemas.book import BookMetadata, LibraryBook, LibraryBookCreate, LibraryBookUpdate
from app.services.isbn import InvalidISBNError, isbn10_to_isbn13, isbn13_to_isbn10, normalize_isbn
from app.services.openlibrary import (
    BookNotFoundError,
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


def _response(entry: LibraryEntry) -> dict:
    metadata = {field: getattr(entry.book, field) for field in BookMetadata.model_fields}
    metadata["authors"] = metadata["authors"] or []
    metadata["subjects"] = metadata["subjects"] or []
    return {**metadata, "id": entry.id, "reading_status": entry.reading_status, "rating": entry.rating,
            "notes": entry.notes, "date_started": entry.date_started, "date_finished": entry.date_finished,
            "date_added": entry.date_added, "created_at": entry.created_at, "updated_at": entry.updated_at,
            "deleted_at": entry.deleted_at, "version": entry.version}


@router.get("", response_model=list[LibraryBook])
def list_books(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    entries = db.scalars(select(LibraryEntry).where(LibraryEntry.user_id == user.id, LibraryEntry.deleted_at.is_(None)).order_by(LibraryEntry.date_added.desc()).offset(skip).limit(limit))
    return [_response(entry) for entry in entries]


@router.get("/{book_id}", response_model=LibraryBook)
def get_library_book(book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    entry = db.scalar(select(LibraryEntry).where(LibraryEntry.id == book_id, LibraryEntry.user_id == user.id, LibraryEntry.deleted_at.is_(None)))
    if entry is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return _response(entry)


@router.post("", response_model=LibraryBook, status_code=status.HTTP_201_CREATED)
def add_book(data: LibraryBookCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        isbn10 = normalize_isbn(data.isbn10) if data.isbn10 else None
        isbn13 = normalize_isbn(data.isbn13) if data.isbn13 else None
    except InvalidISBNError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    duplicate_filters = []
    if isbn10:
        duplicate_filters.extend([Book.isbn10 == isbn10, Book.isbn13 == isbn10_to_isbn13(isbn10)])
    if isbn13:
        duplicate_filters.append(Book.isbn13 == isbn13)
        try:
            duplicate_filters.append(Book.isbn10 == isbn13_to_isbn10(isbn13))
        except InvalidISBNError:
            pass
    if duplicate_filters:
        duplicate = db.scalar(select(Book).where(or_(*duplicate_filters)))
        if duplicate:
            existing = db.scalar(select(LibraryEntry).where(LibraryEntry.user_id == user.id, LibraryEntry.book_id == duplicate.id, LibraryEntry.deleted_at.is_(None)))
            if existing:
                raise HTTPException(status_code=409, detail={"message": "Book edition already exists", "id": existing.id})
            book = duplicate
        else:
            book = None
    else:
        book = None
    if book is None:
        metadata = data.model_dump(include=set(BookMetadata.model_fields))
        metadata.update(isbn10=isbn10, isbn13=isbn13)
        book = Book(**metadata)
        db.add(book)
        db.flush()
    entry = LibraryEntry(user_id=user.id, book_id=book.id, **data.model_dump(include={"reading_status", "rating", "notes", "date_started", "date_finished"}))
    db.add(entry)
    db.flush()
    from app.routes.sync import _record_change
    _record_change(db, user.id, entry, "create")
    db.commit()
    db.refresh(entry)
    return _response(entry)


@router.patch("/{book_id}", response_model=LibraryBook)
def update_book(book_id: int, data: LibraryBookUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    entry = db.scalar(select(LibraryEntry).where(LibraryEntry.id == book_id, LibraryEntry.user_id == user.id, LibraryEntry.deleted_at.is_(None)))
    if entry is None:
        raise HTTPException(status_code=404, detail="Book not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    entry.version += 1
    from app.routes.sync import _record_change
    _record_change(db, user.id, entry, "update")
    db.commit()
    db.refresh(entry)
    return _response(entry)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    entry = db.scalar(select(LibraryEntry).where(LibraryEntry.id == book_id, LibraryEntry.user_id == user.id, LibraryEntry.deleted_at.is_(None)))
    if entry is None:
        raise HTTPException(status_code=404, detail="Book not found")
    from app.models.user import utc_now
    entry.deleted_at = utc_now()
    entry.version += 1
    from app.routes.sync import _record_change
    _record_change(db, user.id, entry, "delete")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)