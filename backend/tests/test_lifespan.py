"""Verificações que o startup faz antes de o app aceitar tráfego."""

from typing import Any

import pytest

from app.adapters.db import ORPHAN_MESSAGE, Database
from app.errors import InternalError


class FakePool:
    """Pool que devolve respostas fixas e registra o SQL recebido."""

    def __init__(self, typmod: Any = 768, orphans: list[dict[str, Any]] | None = None) -> None:
        self._typmod = typmod
        self._orphans = orphans or []
        self.fetch_args: list[Any] = []

    async def fetchval(self, query: str, *args: Any) -> Any:
        return self._typmod

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self.fetch_args = list(args)
        return self._orphans


def build_database(pool: FakePool) -> Database:
    database = Database("postgresql://irrelevante")
    database._pool = pool  # type: ignore[assignment]
    return database


@pytest.mark.asyncio
async def test_dimensao_coerente_nao_aborta_o_startup() -> None:
    database = build_database(FakePool(typmod=768))

    await database.verify_embedding_dimension(768)


@pytest.mark.asyncio
async def test_dimensao_divergente_aborta_com_mensagem_clara() -> None:
    database = build_database(FakePool(typmod=1536))

    with pytest.raises(InternalError) as erro:
        await database.verify_embedding_dimension(768)

    assert "768" in str(erro.value)
    assert "1536" in str(erro.value)


@pytest.mark.asyncio
async def test_coluna_sem_dimensao_declarada_aborta() -> None:
    database = build_database(FakePool(typmod=-1))

    with pytest.raises(InternalError):
        await database.verify_embedding_dimension(768)


@pytest.mark.asyncio
async def test_varredura_marca_orfaos_como_failed() -> None:
    pool = FakePool(orphans=[{"id": "doc-1"}, {"id": "doc-2"}])
    database = build_database(pool)

    total = await database.sweep_orphans()

    assert total == 2
    assert pool.fetch_args == [ORPHAN_MESSAGE]


@pytest.mark.asyncio
async def test_varredura_sem_orfaos_nao_faz_nada() -> None:
    database = build_database(FakePool(orphans=[]))

    assert await database.sweep_orphans() == 0
