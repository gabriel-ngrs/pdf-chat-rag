"""Ponto de entrada da API do TalkDoc.

Monta o app, o lifespan e as rotas de infraestrutura. As rotas de documento
vivem em `app/api/documents.py`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request

from app.adapters.db import Database
from app.adapters.gemini import GeminiEmbeddingClient
from app.adapters.repository import PostgresDocumentRepository
from app.api.documents import router as documents_router
from app.api.middleware import RequestIdMiddleware
from app.api.schemas import ConfigResponse, HealthResponse
from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.logging_setup import configure_logging, get_logger

logger = get_logger(__name__)

router = APIRouter()


def get_database(request: Request) -> Database:
    """Devolve o `Database` criado no lifespan.

    É uma dependência, e não um import de módulo, para que os testes offline
    injetem um dublê sem precisar de banco nenhum.
    """
    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:
        raise RuntimeError("O banco de dados não foi inicializado.")
    return database


DatabaseDep = Annotated[Database, Depends(get_database)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/health", response_model=HealthResponse)
async def health(database: DatabaseDep) -> HealthResponse:
    """Sonda de saúde. Reporta o banco separadamente para distinguir as falhas."""
    reachable = await database.ping()
    return HealthResponse(status="ok", database="ok" if reachable else "unavailable")


@router.get("/config", response_model=ConfigResponse)
async def read_config(settings: SettingsDep) -> ConfigResponse:
    """Publica os limites que o servidor aplica, para o cliente não duplicá-los."""
    return ConfigResponse(
        max_upload_mb=settings.max_upload_mb,
        max_pdf_pages=settings.max_pdf_pages,
        max_extracted_chars=settings.max_extracted_chars,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepara o processo: logging, pool, coerência do schema e varredura de órfãos."""
    configure_logging()
    settings = get_settings()
    database = Database(settings.database_url)
    await database.connect()
    await database.verify_embedding_dimension(settings.embedding_dim)
    repository = PostgresDocumentRepository(database)
    swept = await repository.sweep_orphans()
    app.state.database = database
    app.state.repository = repository
    app.state.embedder = GeminiEmbeddingClient(settings)
    logger.info("app.started", orphans_swept=swept)
    try:
        yield
    finally:
        await database.close()
        logger.info("app.stopped")


def create_app() -> FastAPI:
    """Constrói a aplicação. Fábrica para que cada teste tenha uma instância limpa."""
    app = FastAPI(title="TalkDoc API", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(router, prefix="/api")
    app.include_router(documents_router, prefix="/api")
    return app


app = create_app()
