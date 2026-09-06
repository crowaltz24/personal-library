from pydantic import BaseModel, ConfigDict


class BookMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isbn10: str | None = None
    isbn13: str | None = None
    title: str | None = None
    authors: list[str] = []
    publisher: str | None = None
    publication_date: str | None = None
    description: str | None = None
    subjects: list[str] = []
    cover_url: str | None = None
    openlibrary_work_id: str | None = None
    openlibrary_edition_id: str | None = None