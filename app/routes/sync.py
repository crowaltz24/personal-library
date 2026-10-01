from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import Book, LibraryEntry, ProcessedMutation, SyncChange, User
from app.models.user import utc_now
from app.routes.books import _response
from app.schemas.book import LibraryBook
from app.schemas.sync import SyncChangeResponse, SyncPullResponse, SyncPushRequest, SyncPushResponse

router = APIRouter(prefix="/sync")


def _change_response(change: SyncChange) -> SyncChangeResponse:
    return SyncChangeResponse(revision=change.id, entity_type=change.entity_type, entity_id=change.entity_id,
                              operation=change.operation, version=change.version, payload=change.payload,
                              created_at=change.created_at)


def _record_change(db: Session, user_id: int, entry: LibraryEntry, operation: str) -> SyncChange:
    change = SyncChange(user_id=user_id, entity_type="library_entry", entity_id=entry.id,
                        operation=operation, version=entry.version,
                        payload=LibraryBook.model_validate(_response(entry)).model_dump(mode="json"))
    db.add(change)
    db.flush()
    return change


@router.get("/pull", response_model=SyncPullResponse)
def pull_changes(since: int = 0, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> SyncPullResponse:
    changes = db.scalars(select(SyncChange).where(SyncChange.user_id == user.id, SyncChange.id > since).order_by(SyncChange.id)).all()
    revision = changes[-1].id if changes else since
    return SyncPullResponse(changes=[_change_response(change) for change in changes], revision=revision)


@router.post("/push", response_model=SyncPushResponse)
def push_changes(request: SyncPushRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> SyncPushResponse:
    results = []
    for mutation in request.mutations:
        existing = db.scalar(select(ProcessedMutation).where(ProcessedMutation.user_id == user.id,
                                                             ProcessedMutation.client_mutation_id == mutation.client_mutation_id))
        if existing:
            results.append(SyncChangeResponse.model_validate(existing.result))
            continue
        if mutation.operation == "create":
            metadata_fields = set(Book.__table__.columns.keys()) - {"id", "created_at", "updated_at", "date_added"}
            metadata = {key: value for key, value in mutation.payload.items() if key in metadata_fields}
            personal_fields = {key: value for key, value in mutation.payload.items() if key in {"reading_status", "rating", "notes", "date_started", "date_finished"}}
            book = Book(**metadata)
            db.add(book)
            db.flush()
            entry = LibraryEntry(user_id=user.id, book=book, **personal_fields)
            db.add(entry)
            db.flush()
        else:
            if mutation.entity_id is None:
                raise HTTPException(status_code=422, detail="entity_id is required for update/delete")
            entry = db.scalar(select(LibraryEntry).where(LibraryEntry.id == mutation.entity_id, LibraryEntry.user_id == user.id))
            if entry is None:
                raise HTTPException(status_code=404, detail="Library entry not found")
            if mutation.operation == "update" and entry.deleted_at is None:
                for field in {"reading_status", "rating", "notes", "date_started", "date_finished"}:
                    if field in mutation.payload:
                        setattr(entry, field, mutation.payload[field])
                entry.version += 1
            elif mutation.operation == "delete" and entry.deleted_at is None:
                entry.deleted_at = utc_now()
                entry.version += 1
        change = _record_change(db, user.id, entry, mutation.operation)
        db.flush()
        response = _change_response(change)
        db.add(ProcessedMutation(user_id=user.id, client_mutation_id=mutation.client_mutation_id,
                                 result=response.model_dump(mode="json")))
        results.append(response)
    db.commit()
    revision = results[-1].revision if results else 0
    return SyncPushResponse(results=results, revision=revision)