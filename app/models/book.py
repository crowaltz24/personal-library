from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    isbn10: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    isbn13: Mapped[str | None] = mapped_column(String(13), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    authors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publication_date: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    subjects: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    openlibrary_work_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    openlibrary_edition_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_added: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)