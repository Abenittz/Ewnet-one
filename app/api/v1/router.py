from fastapi import APIRouter

from app.api.v1.endpoints import books, reader, upload

api_router = APIRouter()
api_router.include_router(books.router)
api_router.include_router(reader.router)
api_router.include_router(upload.router)
