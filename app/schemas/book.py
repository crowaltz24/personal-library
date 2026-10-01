from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BookMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isbn10: str | None = None
    isbn13: str | None = None
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    publisher: str | None = None
    publication_date: str | None = None
    description: str | None = None
    subjects: list[str] = Field(default_factory=list)
    cover_url: str | None = None
    openlibrary_work_id: str | None = None
    openlibrary_edition_id: str | None = None
    google_volume_id: str | None = None
    metadata_source: str | None = None


class LibraryBookCreate(BookMetadata):
    reading_status: str = "unread"
    rating: float | None = Field(default=None, ge=0, le=5)
    notes: str | None = None
    date_started: datetime | None = None
    date_finished: datetime | None = None

    @model_validator(mode="after")
    def require_identity(self):
        if not (self.isbn10 or self.isbn13 or self.title):
            raise ValueError("At least one ISBN or a title is required")
        if self.reading_status not in {"unread", "reading", "read"}:
            raise ValueError("reading_status must be unread, reading, or read")
        return self


class LibraryBookUpdate(BaseModel):
    reading_status: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    notes: str | None = None
    date_started: datetime | None = None
    date_finished: datetime | None = None

    @model_validator(mode="after")
    def validate_status(self):
        if self.reading_status is not None and self.reading_status not in {"unread", "reading", "read"}:
            raise ValueError("reading_status must be unread, reading, or read")
        return self


class LibraryBook(BookMetadata):
    id: int
    reading_status: str
    rating: float | None = None
    notes: str | None = None
    date_started: datetime | None = None
    date_finished: datetime | None = None
    date_added: datetime
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    version: int