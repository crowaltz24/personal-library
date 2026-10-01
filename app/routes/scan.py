from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.scan import BarcodeScanResponse, BookIdentificationResponse, IdentifiedBook
from app.services.barcode import InvalidImageError, decode_isbn_barcodes
from app.services.identification import identify_book_image

router = APIRouter(prefix="/scan")


@router.post("/barcode", response_model=BarcodeScanResponse)
async def scan_barcode(image: UploadFile = File(...)) -> BarcodeScanResponse:
    try:
        image_bytes = await image.read()
        candidates = decode_isbn_barcodes(image_bytes)
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BarcodeScanResponse(
        detected=bool(candidates),
        candidates=[{"isbn": candidate.isbn, "format": candidate.format} for candidate in candidates],
    )


@router.post("/identify", response_model=BookIdentificationResponse)
async def identify_book(image: UploadFile = File(...)) -> BookIdentificationResponse:
    try:
        books = await identify_book_image(await image.read())
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BookIdentificationResponse(
        detected=bool(books),
        books=[IdentifiedBook(**book) for book in books],
    )