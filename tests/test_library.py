from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.routes import scan
from app.schemas.book import BookMetadata


def client_with_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    auth = client.post("/api/auth/register", json={"username": f"user-{tmp_path.name}", "password": "password123"})
    client.headers.update({"Authorization": f"Bearer {auth.json()['access_token']}"})
    return client, engine


def test_identification_returns_confirmation_without_saving(monkeypatch, tmp_path):
    async def identified(_):
        return [{
            "isbn": "9780306406157",
            "format": "EAN13",
            "metadata_found": True,
            "metadata": BookMetadata(
                isbn13="9780306406157",
                title="A Book",
                metadata_source="google_books",
            ),
        }]

    monkeypatch.setattr(scan, "identify_book_image", identified)
    client, _ = client_with_database(tmp_path)
    try:
        response = client.post(
            "/api/scan/identify",
            files={"image": ("book.png", b"image", "image/png")},
        )
        assert response.status_code == 200
        assert response.json()["books"][0]["metadata"]["title"] == "A Book"
        assert client.get("/api/books").json() == []
    finally:
        app.dependency_overrides.clear()


def test_library_crud_and_personal_fields(tmp_path):
    client, _ = client_with_database(tmp_path)
    try:
        payload = {
            "isbn13": "9780306406157",
            "title": "A Book",
            "authors": ["An Author"],
            "metadata_source": "google_books",
            "reading_status": "unread",
        }
        created = client.post("/api/books", json=payload)
        assert created.status_code == 201
        book = created.json()
        assert book["metadata_source"] == "google_books"
        assert book["reading_status"] == "unread"

        listing = client.get("/api/books?limit=10")
        assert listing.status_code == 200
        assert listing.json()[0]["id"] == book["id"]

        updated = client.patch(
            f"/api/books/{book['id']}",
            json={"reading_status": "read", "rating": 4.5, "notes": "Keep this edition"},
        )
        assert updated.status_code == 200
        assert updated.json()["reading_status"] == "read"
        assert updated.json()["rating"] == 4.5
        assert updated.json()["title"] == "A Book"

        assert client.get(f"/api/books/{book['id']}").status_code == 200
        assert client.delete(f"/api/books/{book['id']}").status_code == 204
        assert client.get(f"/api/books/{book['id']}").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_duplicate_isbn_and_incomplete_metadata(tmp_path):
    client, _ = client_with_database(tmp_path)
    try:
        first = client.post("/api/books", json={"isbn13": "9780306406157", "title": "First edition"})
        assert first.status_code == 201
        duplicate = client.post("/api/books", json={"isbn13": "9780306406157", "title": "Duplicate"})
        assert duplicate.status_code == 409

        incomplete = client.post("/api/books", json={"title": "Metadata unavailable"})
        assert incomplete.status_code == 201
        invalid = client.post("/api/books", json={})
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()