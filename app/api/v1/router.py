from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    books,
    explore,
    library,
    reader,
    resources,
    upload,
    works,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(books.router)
api_router.include_router(explore.router)
api_router.include_router(library.router)
api_router.include_router(reader.router)
api_router.include_router(resources.router)
api_router.include_router(upload.router)
api_router.include_router(works.router)

