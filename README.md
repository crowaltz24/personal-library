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

### Identify and add a book

Identify an uploaded image for a confirmation screen. This does not save anything:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/scan/identify -F "image=@test-images/tbk1.png"
```

After reviewing the returned metadata, explicitly add it to the library:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/books -H "Content-Type: application/json" -d '{"isbn13":"9789352763344","title":"The Originals: The Brothers Karamazov","authors":["Fyodor Dostoevsky"],"metadata_source":"google_books"}'
```

Library records are available through `GET /api/books`, `GET /api/books/{id}`, `PATCH /api/books/{id}`, and `DELETE /api/books/{id}`. Use `skip` and `limit` on the list endpoint for basic pagination. Duplicate ISBN editions return HTTP 409; different ISBNs remain separate records.

## Offline-first synchronization

The server is the canonical store. Clients keep a local replica and an outbox:

```text
Offline: UI -> Local DB -> Outbox
Online:  UI -> Local DB -> Outbox -> Sync API -> Server
		 Server -> Sync API -> Local DB
```

Register or log in through `POST /api/auth/register` or `POST /api/auth/login`, then send the returned bearer token on library and sync requests. `POST /api/sync/push` accepts queued mutations with a unique `client_mutation_id`; retrying that ID is idempotent. `GET /api/sync/pull?since=0` performs initial sync, and subsequent pulls use the last returned revision.

Each sync payload identifies a `library_entry`, includes its server `entity_id`, `version`, timestamps, and deletion state. Updates use simple last-arrival-wins semantics; `base_version` is advisory and the server returns the authoritative resulting version. Deletes set `deleted_at` and remain as permanent tombstones so other devices can receive them.

A future client can use these local tables:

- `LocalBook`: cached shared bibliographic metadata.
- `LocalLibraryEntry`: user-owned reading state plus server ID/version and `deleted_at`.
- `PendingChange`: entity, operation, payload, `client_mutation_id`, retry count, and last error.
- `SyncState`: last successful server revision and last sync timestamp.

The sync layer never calls Open Library or Google Books. Identification remains a separate, non-persistent operation; the client confirms metadata before creating a library entry.

### Single command scan

Scan an image and query book metadata without starting the API server:

```powershell
python scan_book.py --image test-images/tbk1.png
```

The script prints JSON containing the detected ISBN candidates and metadata from Open Library or Google Books. Use the `.venv` interpreter if the virtual environment is not activated: `\.venv\Scripts\python.exe scan_book.py --image test-images/tbk1.png`.