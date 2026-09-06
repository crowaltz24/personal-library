from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routes.books import router as books_router
from app.routes.health import router as health_router
from app.routes.scan import router as scan_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Personal Library API", lifespan=lifespan)
app.include_router(health_router, prefix="/api")
app.include_router(books_router, prefix="/api")
app.include_router(scan_router, prefix="/api")