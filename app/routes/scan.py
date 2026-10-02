from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.scan import (
    BarcodeScanResponse,
    BarcodeCandidate,
    BookIdentificationResponse,
    IdentifiedBook,
    OCRBlockResponse,
    OCRIdentificationCandidate,
    OCRIdentificationOCR,
    OCRIdentificationResponse,
    OCRResponse,
)
from app.services.barcode import InvalidImageError, decode_isbn_barcodes
from app.services.identification import identify_book_image
from app.services.ocr import OCREngineUnavailableError, ocr_image
from app.services.ocr_identification import identify_ocr_image

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
        candidates=[
            BarcodeCandidate(isbn=candidate.isbn, format=candidate.format)
            for candidate in candidates
        ],
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


@router.post("/ocr", response_model=OCRResponse)
async def scan_ocr(image: UploadFile = File(...)) -> OCRResponse:
    try:
        result = ocr_image(await image.read())
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OCREngineUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return OCRResponse(
        text=result.text,
        normalized_text=result.normalized_text,
        blocks=[
            OCRBlockResponse(
                text=block.text,
                confidence=block.confidence,
                bbox=list(block.bbox),
            )
            for block in result.blocks
        ],
        width=result.width,
        height=result.height,
        orientation=result.orientation,
        engine=result.engine,
        message="No readable text detected" if not result.normalized_text else None,
    )


@router.post("/identify-ocr", response_model=OCRIdentificationResponse)
async def identify_book_from_ocr(image: UploadFile = File(...)) -> OCRIdentificationResponse:
    try:
        result = await identify_ocr_image(await image.read())
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OCREngineUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return OCRIdentificationResponse(
        detected=bool(result.candidates),
        ocr=OCRIdentificationOCR(
            text=result.ocr.text,
            normalized_text=result.ocr.normalized_text,
            confidence=result.signals.confidence,
            orientation=result.ocr.orientation,
        ),
        candidates=[
            OCRIdentificationCandidate(
                title=candidate.metadata.title,
                authors=candidate.metadata.authors,
                isbn10=candidate.metadata.isbn10,
                isbn13=candidate.metadata.isbn13,
                cover_url=candidate.metadata.cover_url,
                provider=candidate.metadata.metadata_source,
                match_score=candidate.match_score,
            )
            for candidate in result.candidates
        ],
        message=result.message,
    )