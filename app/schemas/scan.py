from pydantic import BaseModel, Field


class BarcodeCandidate(BaseModel):
    isbn: str
    format: str


class BarcodeScanResponse(BaseModel):
    detected: bool
    candidates: list[BarcodeCandidate] = Field(default_factory=list)