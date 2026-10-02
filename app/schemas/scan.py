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


class OCRBlockResponse(BaseModel):
    text: str
    confidence: float | None = None
    bbox: list[int]


class OCRResponse(BaseModel):
    text: str
    normalized_text: str
    blocks: list[OCRBlockResponse] = Field(default_factory=list)
    width: int
    height: int
    orientation: int | None = None
    engine: str
    message: str | None = None