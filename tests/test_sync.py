from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


def make_client(tmp_path, username):
    engine = create_engine(f"sqlite:///{tmp_path / f'{username}.db'}", connect_args={"check_same_thread": False})
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
    auth = client.post("/api/auth/register", json={"username": username, "password": "password123"})
    client.headers.update({"Authorization": f"Bearer {auth.json()['access_token']}"})
    return client


def create_mutation(client, mutation_id="create-1", title="Offline book"):
    return {
        "client_mutation_id": mutation_id,
        "entity_type": "library_entry",
        "operation": "create",
        "payload": {"isbn13": "9780306406157", "title": title, "authors": ["Author"], "metadata_source": "local"},
    }


def test_initial_incremental_delete_and_idempotency(tmp_path):
    client = make_client(tmp_path, "sync-user")
    try:
        pushed = client.post("/api/sync/push", json={"mutations": [create_mutation(client)]})
        assert pushed.status_code == 200
        change = pushed.json()["results"][0]
        assert change["operation"] == "create"
        entry_id = change["entity_id"]
        revision = pushed.json()["revision"]

        retry = client.post("/api/sync/push", json={"mutations": [create_mutation(client)]})
        assert retry.status_code == 200
        assert retry.json()["results"][0]["entity_id"] == entry_id

        initial = client.get("/api/sync/pull?since=0")
        assert initial.status_code == 200
        assert initial.json()["changes"][0]["entity_id"] == entry_id

        update = client.post("/api/sync/push", json={"mutations": [{
            "client_mutation_id": "update-1", "entity_type": "library_entry", "entity_id": entry_id,
            "operation": "update", "base_version": 1, "payload": {"notes": "changed"},
        }]})
        assert update.status_code == 200
        incremental = client.get(f"/api/sync/pull?since={revision}").json()
        assert len(incremental["changes"]) == 1
        assert incremental["changes"][0]["payload"]["notes"] == "changed"

        deleted = client.post("/api/sync/push", json={"mutations": [{
            "client_mutation_id": "delete-1", "entity_type": "library_entry", "entity_id": entry_id,
            "operation": "delete", "base_version": 2, "payload": {},
        }]})
        assert deleted.status_code == 200
        tombstone = client.get(f"/api/sync/pull?since={incremental['revision']}").json()["changes"][0]
        assert tombstone["operation"] == "delete"
        assert tombstone["payload"]["deleted_at"] is not None
    finally:
        app.dependency_overrides.clear()


def test_conflict_is_last_arrival_wins(tmp_path):
    client = make_client(tmp_path, "conflict-user")
    try:
        entry_id = client.post("/api/sync/push", json={"mutations": [create_mutation(client)]}).json()["results"][0]["entity_id"]
        client.post("/api/sync/push", json={"mutations": [{
            "client_mutation_id": "stale-a", "entity_type": "library_entry", "entity_id": entry_id,
            "operation": "update", "base_version": 1, "payload": {"notes": "A"},
        }]})
        result = client.post("/api/sync/push", json={"mutations": [{
            "client_mutation_id": "stale-b", "entity_type": "library_entry", "entity_id": entry_id,
            "operation": "update", "base_version": 1, "payload": {"notes": "B"},
        }]})
        assert result.status_code == 200
        assert client.get(f"/api/books/{entry_id}").json()["notes"] == "B"
    finally:
        app.dependency_overrides.clear()


def test_user_isolation(tmp_path):
    client_a = make_client(tmp_path, "user-a")
    try:
        created = client_a.post("/api/sync/push", json={"mutations": [create_mutation(client_a)]}).json()
        entry_id = created["results"][0]["entity_id"]
        token_b = client_a.post("/api/auth/register", json={"username": "user-b", "password": "password123"}).json()["access_token"]
        client_a.headers.update({"Authorization": f"Bearer {token_b}"})
        assert client_a.get("/api/sync/pull?since=0").json()["changes"] == []
        assert client_a.get(f"/api/books/{entry_id}").status_code == 404
        forbidden = client_a.post("/api/sync/push", json={"mutations": [{
            "client_mutation_id": "attack", "entity_type": "library_entry", "entity_id": entry_id,
            "operation": "delete", "payload": {},
        }]})
        assert forbidden.status_code == 404
    finally:
        app.dependency_overrides.clear()