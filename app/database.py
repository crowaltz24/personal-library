import os
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./library.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    if not DATABASE_URL.startswith("sqlite"):
        return
    columns = {column["name"] for column in inspect(engine).get_columns("books")}
    additions = {
        "google_volume_id": "VARCHAR(100)",
        "metadata_source": "VARCHAR(50)",
        "reading_status": "VARCHAR(20) NOT NULL DEFAULT 'unread'",
        "rating": "FLOAT",
        "notes": "TEXT",
        "date_started": "DATETIME",
        "date_finished": "DATETIME",
        "created_at": "DATETIME",
        "updated_at": "DATETIME",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE books ADD COLUMN {name} {definition}"))