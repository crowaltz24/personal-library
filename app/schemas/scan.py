from pydantic import BaseModel, Field

from app.schemas.book import BookMetadata


class BarcodeCandidate(BaseModel):
    isbn: str
    format: str


class BarcodeScanResponse(BaseModel):
    detected: bool
    candidates: list[BarcodeCandidate] = Field(default_factory=list)


class IdentifiedBook(BaseModel):
    isbn: str
    format: str
    metadata_found: bool
    metadata: BookMetadata | None = None
    error: str | None = None


class BookIdentificationResponse(BaseModel):
    detected: bool
    books: list[IdentifiedBook] = Field(default_factory=list)