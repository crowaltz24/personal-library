from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import utc_now


class LibraryEntry(Base):
    __tablename__ = "library_entries"
    __table_args__ = (UniqueConstraint("user_id", "book_id", name="uq_library_user_book"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True, nullable=False)
    reading_status: Mapped[str] = mapped_column(String(20), default="unread", nullable=False)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_started: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_finished: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_added: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    user = relationship("User", back_populates="library_entries")
    book = relationship("Book")


class SyncChange(Base):
    __tablename__ = "sync_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class ProcessedMutation(Base):
    __tablename__ = "processed_mutations"
    __table_args__ = (UniqueConstraint("user_id", "client_mutation_id", name="uq_processed_user_mutation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    client_mutation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)