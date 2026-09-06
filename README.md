# Personal Library API

Initial backend for scanning book barcodes and looking up book metadata by ISBN through Open Library/Google Books API.

## Setup

Create and activate a virtual environment, then install dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

```powershell
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Try `GET /api/health`, `GET /api/books/isbn/{isbn}`, or scan an image with `POST /api/scan/barcode`. The SQLite database is created as `library.db` when the application starts.

Google Books is used as a fallback when Open Library does not have an ISBN. It works with the public API during development, but you can optionally configure a Google Books API key as `GOOGLE_BOOKS_API_KEY` in your env.

### Barcode scan

Send a multipart image upload:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/scan/barcode -F "image=@book.jpg"
```

The response includes `detected` and a `candidates` list containing each valid ISBN barcode, for example `{"isbn":"9780306406157","format":"EAN13"}`. EAN-13 values are accepted only when they have a valid ISBN check digit and begin with `978` or `979`; arbitrary product barcodes are ignored. ZXing handles common 1D barcodes, but difficult photographs may still require better focus, lighting, or cropping.

### Single command scan

Scan an image and query book metadata without starting the API server:

```powershell
python scan_book.py --image test-images/tbk1.png
```

The script prints JSON containing the detected ISBN candidates and metadata from Open Library or Google Books. Use the `.venv` interpreter if the virtual environment is not activated: `\.venv\Scripts\python.exe scan_book.py --image test-images/tbk1.png`.