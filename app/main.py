from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import initialize_database
from app.models import Book
from app.routes.books import router as books_router
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.scan import router as scan_router
from app.routes.sync import router as sync_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Personal Library API", lifespan=lifespan)
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(books_router, prefix="/api")
app.include_router(scan_router, prefix="/api")
app.include_router(sync_router, prefix="/api")