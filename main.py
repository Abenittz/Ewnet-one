from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import register_exception_handlers
from app.services.storage import storage_service


@asynccontextmanager
async def lifespan(_app: FastAPI):
    storage_service.ensure_directories()
    yield


def create_app() -> FastAPI:
    storage_service.ensure_directories()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=settings.CORS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_private_network=True,
    )

    register_exception_handlers(app)

    # Mount storage directory for static file access (covers, extracted images)
    app.mount(
        "/storage",
        StaticFiles(directory=settings.STORAGE_PATH, check_dir=False),
        name="storage",
    )

    @app.get("/health", tags=["health"], status_code=status.HTTP_200_OK)
    async def health_check():
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "ok", "database": "connected"}
        except Exception as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "degraded",
                    "database": "disconnected",
                    "detail": str(exc),
                },
            )

    app.include_router(api_router, prefix=settings.API_V1_STR)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )

