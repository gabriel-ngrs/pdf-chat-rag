"""A sonda de saúde reporta o app e o banco separadamente."""

import httpx
import pytest

from app.api.middleware import REQUEST_ID_HEADER
from app.main import create_app, get_database


class StubDatabase:
    """Dublê que responde a sonda sem banco nenhum."""

    def __init__(self, reachable: bool) -> None:
        self._reachable = reachable

    async def ping(self) -> bool:
        return self._reachable


def build_client(reachable: bool = True) -> httpx.AsyncClient:
    app = create_app()
    app.dependency_overrides[get_database] = lambda: StubDatabase(reachable)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


@pytest.mark.asyncio
async def test_health_reporta_banco_disponivel() -> None:
    async with build_client(reachable=True) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.asyncio
async def test_health_distingue_banco_indisponivel() -> None:
    async with build_client(reachable=False) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["database"] == "unavailable"


@pytest.mark.asyncio
async def test_resposta_carrega_request_id() -> None:
    async with build_client() as client:
        response = await client.get("/api/health")

    assert response.headers[REQUEST_ID_HEADER]


@pytest.mark.asyncio
async def test_request_id_do_cliente_e_preservado() -> None:
    async with build_client() as client:
        response = await client.get("/api/health", headers={REQUEST_ID_HEADER: "id-externo"})

    assert response.headers[REQUEST_ID_HEADER] == "id-externo"
