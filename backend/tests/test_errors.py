"""Toda saída de erro da API usa o envelope `{code, message}`."""

import httpx
import pytest
from fastapi import APIRouter

from app.errors import FileTooLargeError, NotFoundError
from app.main import create_app


def build_app_with_failing_routes() -> httpx.AsyncClient:
    app = create_app()
    router = APIRouter()

    @router.get("/boom-dominio")
    async def boom_dominio() -> None:
        raise FileTooLargeError("O arquivo excede o limite de 25 MB.")

    @router.get("/boom-inesperado")
    async def boom_inesperado() -> None:
        raise ValueError("detalhe interno que não pode vazar")

    @router.get("/precisa-de-numero")
    async def precisa_de_numero(quantidade: int) -> dict[str, int]:
        return {"quantidade": quantidade}

    app.include_router(router, prefix="/api")
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    )


@pytest.mark.asyncio
async def test_erro_de_dominio_sai_no_envelope() -> None:
    async with build_app_with_failing_routes() as client:
        response = await client.get("/api/boom-dominio")

    assert response.status_code == 413
    assert response.json() == {
        "code": "arquivo_grande",
        "message": "O arquivo excede o limite de 25 MB.",
    }


@pytest.mark.asyncio
async def test_erro_de_validacao_do_framework_sai_no_envelope() -> None:
    async with build_app_with_failing_routes() as client:
        response = await client.get("/api/precisa-de-numero?quantidade=abc")

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "arquivo_invalido"


@pytest.mark.asyncio
async def test_erro_inesperado_nao_vaza_detalhe_interno() -> None:
    async with build_app_with_failing_routes() as client:
        response = await client.get("/api/boom-inesperado")

    assert response.status_code == 500
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "erro_interno"
    assert "detalhe interno" not in response.text


def test_cada_erro_de_dominio_tem_codigo_e_status_proprios() -> None:
    assert (NotFoundError.code, NotFoundError.status_code) == ("nao_encontrado", 404)
    assert (FileTooLargeError.code, FileTooLargeError.status_code) == ("arquivo_grande", 413)
