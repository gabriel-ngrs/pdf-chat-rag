"""AC-11 contra o Postgres de verdade: colunas reais e índice HNSW de cosseno.

Único arquivo da suíte marcado `db`. Fica fora de `make test` de propósito: o
gate de fase precisa rodar na máquina de quem clona o projeto, e uma suíte que
exige container no ar não é gate, é obstáculo. Aqui é `make test-db`.

O que estes testes provam e nenhum dublê poderia provar: que o SQL escrito à mão
casa com o schema de `db/001_init.sql`, que o vetor sobrevive à ida e volta pelo
tipo `vector`, e que o índice criado é mesmo o de cosseno — um índice L2 seria
silenciosamente ignorado pelo operador `<=>` do retrieval, e a busca ficaria
lenta sem nenhum erro para denunciar.

Cada teste cria os próprios dados sob um `session_id` exclusivo e os apaga no
fim; nada que já esteja no banco é lido ou removido.
"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from app.adapters.db import Database
from app.adapters.repository import PostgresDocumentRepository
from app.config import Settings
from app.core.models import Chunk, DocumentStatus
from tests.fakes import deterministic_vector

pytestmark = pytest.mark.db

EMBEDDING_DIM = 768

_CHUNKS_SQL = """
    SELECT chunk_index, page_number, content, embedding,
           vector_dims(embedding) AS dims
      FROM chunks
     WHERE document_id = $1
     ORDER BY chunk_index
"""

_INDEX_SQL = """
    SELECT indexdef
      FROM pg_indexes
     WHERE tablename = 'chunks'
"""

_DELETE_SQL = "DELETE FROM documents WHERE session_id = $1"


def chunks_de_exemplo() -> list[Chunk]:
    return [
        Chunk(chunk_index=0, page_number=1, content="Primeiro trecho da primeira pagina."),
        Chunk(chunk_index=1, page_number=1, content="Segundo trecho da primeira pagina."),
        Chunk(chunk_index=2, page_number=2, content="Unico trecho da segunda pagina."),
    ]


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    """Pool conectado ao Postgres do compose, fechado ao fim do teste."""
    database = Database(Settings().database_url)
    await database.connect(timeout_seconds=5.0)
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
def session_id() -> str:
    """Sessão exclusiva deste teste — é por ela que a limpeza se orienta."""
    return f"teste-a5-{uuid4()}"


@pytest.fixture
async def repository(
    database: Database, session_id: str
) -> AsyncIterator[PostgresDocumentRepository]:
    repository = PostgresDocumentRepository(database)
    try:
        yield repository
    finally:
        # `ON DELETE CASCADE` leva os chunks junto; nada fora desta sessão é tocado.
        await database.pool.execute(_DELETE_SQL, session_id)


async def test_chunks_gravados_tem_todas_as_colunas_preenchidas(
    database: Database, repository: PostgresDocumentRepository, session_id: str
) -> None:
    """AC-11: `document_id`, `chunk_index`, `page_number`, `content` e `embedding`."""
    chunks = chunks_de_exemplo()
    embeddings = [deterministic_vector(chunk.content, EMBEDDING_DIM) for chunk in chunks]
    document_id = await repository.create("documento.pdf", uuid4().hex, session_id)

    await repository.insert_chunks(document_id, chunks, embeddings)

    linhas = await database.pool.fetch(_CHUNKS_SQL, document_id)
    assert len(linhas) == len(chunks)
    for linha, chunk in zip(linhas, chunks, strict=True):
        assert linha["chunk_index"] == chunk.chunk_index
        assert linha["page_number"] == chunk.page_number
        assert linha["content"] == chunk.content
        assert linha["embedding"] is not None
        assert linha["dims"] == EMBEDDING_DIM


async def test_o_indice_de_chunks_e_hnsw_de_cosseno(database: Database) -> None:
    """AC-11: o opclass precisa ser `vector_cosine_ops`, senão o `<=>` ignora o índice."""
    definicoes = [linha["indexdef"] for linha in await database.pool.fetch(_INDEX_SQL)]

    hnsw = [definicao for definicao in definicoes if "USING hnsw" in definicao]
    assert len(hnsw) == 1
    assert "vector_cosine_ops" in hnsw[0]
    assert "embedding" in hnsw[0]


async def test_a_dimensao_declarada_no_schema_e_a_que_a_aplicacao_espera(
    database: Database,
) -> None:
    """A verificação que o lifespan faz no startup, contra o schema real."""
    assert await database.embedding_dimension() == EMBEDDING_DIM

    await database.verify_embedding_dimension(EMBEDDING_DIM)


async def test_estado_e_progresso_atravessam_o_banco_sem_perda(
    repository: PostgresDocumentRepository, session_id: str
) -> None:
    """As escritas do pipeline batem com as colunas reais de `documents`."""
    content_hash = uuid4().hex
    document_id = await repository.create("documento.pdf", content_hash, session_id)

    await repository.set_status(document_id, DocumentStatus.PROCESSING)
    await repository.set_totals(document_id, page_count=2, chunks_total=3)
    await repository.update_progress(document_id, 3)
    await repository.set_status(document_id, DocumentStatus.READY)

    registro = await repository.get(document_id)
    assert registro is not None
    assert registro.status is DocumentStatus.READY
    assert registro.page_count == 2
    assert registro.chunks_total == 3
    assert registro.chunks_processed == 3
    assert registro.error_message is None


async def test_reenvio_identico_e_reconhecido_pelo_hash_na_mesma_sessao(
    repository: PostgresDocumentRepository, session_id: str
) -> None:
    """AC-15 contra o banco: é a chave `(session_id, content_hash)` que dedupe."""
    content_hash = uuid4().hex
    document_id = await repository.create("documento.pdf", content_hash, session_id)

    encontrado = await repository.find_by_hash(session_id, content_hash)
    outra_sessao = await repository.find_by_hash(f"{session_id}-outra", content_hash)

    assert encontrado is not None
    assert encontrado.id == document_id
    assert outra_sessao is None
