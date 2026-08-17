"""Score, limiar, top-k e recorte do trecho da citação.

As regras puras rodam offline. O que só o Postgres pode responder — que a busca
por `<=>` não atravessa a fronteira do documento e que ela volta ordenada — fica
no fim do arquivo, marcado `db`, fora de `make test`.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.adapters.db import Database
from app.adapters.repository import PostgresConversationRepository, PostgresDocumentRepository
from app.config import Settings
from app.core.models import Chunk, RetrievedChunk
from app.core.retrieval import (
    SNIPPET_MAX_LENGTH,
    build_snippet,
    filter_by_threshold,
    has_grounding,
    similarity_from_distance,
    take_top_k,
)
from tests.fakes import deterministic_vector

EMBEDDING_DIM = 768

_DELETE_SQL = "DELETE FROM documents WHERE session_id = $1"

TRECHOS_DO_DOCUMENTO_A = [
    "A YAITEC Solutions é uma startup brasileira de inteligência artificial.",
    "O time se reúne uma vez por semana num coworking em João Pessoa.",
    "Entre os clientes estão ATC Analytics, ChatADV, Langflow e PagBank.",
]

TRECHOS_DO_DOCUMENTO_B = [
    "O manual descreve a manutenção preventiva de compressores industriais.",
    "A troca do filtro de ar segue o intervalo de duas mil horas de operação.",
]


def _chunk(score: float, chunk_index: int = 0, page_number: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_index=chunk_index,
        page_number=page_number,
        content=f"trecho {chunk_index}",
        score=score,
    )


def test_distancia_de_cosseno_vira_similaridade_em_zero_um() -> None:
    assert similarity_from_distance(0.0) == 1.0
    assert similarity_from_distance(0.25) == 0.75
    assert similarity_from_distance(2.0) == 0.0


def test_residuo_de_ponto_flutuante_nao_escapa_do_intervalo() -> None:
    assert similarity_from_distance(-0.000000002) == 1.0
    assert similarity_from_distance(1.0000000004) == 0.0


def test_score_e_arredondado_a_tres_casas() -> None:
    assert similarity_from_distance(0.1234567) == 0.877


def test_limiar_descarta_o_que_esta_abaixo_e_mantem_o_valor_exato() -> None:
    chunks = [_chunk(0.9, 0), _chunk(0.55, 1), _chunk(0.3, 2)]

    sobreviventes = filter_by_threshold(chunks, 0.55)

    assert [chunk.chunk_index for chunk in sobreviventes] == [0, 1]


def test_tudo_abaixo_do_limiar_deixa_a_lista_vazia_e_sem_fundamento() -> None:
    chunks = [_chunk(0.4, 0), _chunk(0.2, 1)]

    sobreviventes = filter_by_threshold(chunks, 0.7)

    assert sobreviventes == []
    assert not has_grounding(sobreviventes)


def test_com_algum_sobrevivente_ha_fundamento() -> None:
    assert has_grounding([_chunk(0.8)])


def test_top_k_devolve_os_melhores_em_ordem_decrescente() -> None:
    chunks = [_chunk(0.5, 0), _chunk(0.9, 1), _chunk(0.7, 2), _chunk(0.8, 3)]

    melhores = take_top_k(chunks, 2)

    assert [chunk.chunk_index for chunk in melhores] == [1, 3]
    assert [chunk.score for chunk in melhores] == [0.9, 0.8]


def test_top_k_menor_que_a_lista_respeita_o_limite_configurado() -> None:
    chunks = [_chunk(0.9 - index / 10, index) for index in range(5)]

    assert len(take_top_k(chunks, 2)) == 2
    assert len(take_top_k(chunks, 5)) == 5


def test_top_k_maior_que_a_lista_devolve_o_que_existe() -> None:
    chunks = [_chunk(0.9, 0), _chunk(0.8, 1)]

    assert len(take_top_k(chunks, 5)) == 2


def test_top_k_zero_desliga_o_retrieval() -> None:
    assert take_top_k([_chunk(0.9)], 0) == []


def test_snippet_curto_passa_inteiro() -> None:
    assert build_snippet("A YAITEC atua com dados.") == "A YAITEC atua com dados."


def test_snippet_colapsa_quebras_de_linha_da_extracao() -> None:
    assert build_snippet("A YAITEC\n  atua\ncom dados.") == "A YAITEC atua com dados."


def test_snippet_longo_cabe_no_limite_e_termina_em_reticencias() -> None:
    content = " ".join(f"palavra{index}" for index in range(100))

    snippet = build_snippet(content)

    assert len(snippet) <= SNIPPET_MAX_LENGTH
    assert snippet.endswith("…")


def test_snippet_nunca_corta_palavra_ao_meio() -> None:
    content = " ".join(f"palavra{index:03d}" for index in range(100))

    snippet = build_snippet(content)

    ultima = snippet.removesuffix("…").split()[-1]
    assert ultima in content.split()


def test_limite_do_snippet_e_configuravel_pelo_chamador() -> None:
    snippet = build_snippet("uma frase razoavelmente longa para o teste", max_len=20)

    assert len(snippet) <= 20
    assert snippet.endswith("…")


def test_palavra_unica_maior_que_o_limite_ainda_respeita_o_limite() -> None:
    snippet = build_snippet("a" * 300)

    assert len(snippet) <= SNIPPET_MAX_LENGTH
    assert snippet.endswith("…")


def test_top_k_configurado_no_ambiente_e_respeitado(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-26: mudar `RETRIEVAL_TOP_K` no ambiente muda o corte, sem tocar no código."""
    monkeypatch.setenv("RETRIEVAL_TOP_K", "2")
    settings = Settings(_env_file=None)
    chunks = [_chunk(0.9 - index / 10, index) for index in range(5)]

    assert settings.retrieval_top_k == 2
    assert len(take_top_k(chunks, settings.retrieval_top_k)) == 2


# ─── Contra o Postgres de verdade ────────────────────────────────────────────
#
# O que nenhum dublê prova: que a query com `<=>` casa com o schema, que o
# filtro por `document_id` isola de fato, e que a ordem que chega já vem do
# banco. Cada teste cria os próprios dados sob um `session_id` exclusivo e os
# apaga no fim; nada que já esteja no banco é lido ou removido.


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    database = Database(Settings().database_url)
    await database.connect(timeout_seconds=5.0)
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
def session_id() -> str:
    return f"teste-a3-{uuid4()}"


@pytest.fixture
async def documentos(
    database: Database, session_id: str
) -> AsyncIterator[tuple[PostgresDocumentRepository, PostgresConversationRepository]]:
    """Dois documentos ingeridos na mesma sessão, com chunks de assuntos distintos."""
    documents = PostgresDocumentRepository(database)
    conversations = PostgresConversationRepository(database)
    try:
        yield documents, conversations
    finally:
        await database.pool.execute(_DELETE_SQL, session_id)


async def _ingest(
    repository: PostgresDocumentRepository, session_id: str, filename: str, trechos: list[str]
) -> UUID:
    document_id = await repository.create(filename, uuid4().hex, session_id)
    chunks = [
        Chunk(chunk_index=index, page_number=index + 1, content=trecho)
        for index, trecho in enumerate(trechos)
    ]
    embeddings = [deterministic_vector(chunk.content, EMBEDDING_DIM) for chunk in chunks]
    await repository.insert_chunks(document_id, chunks, embeddings)
    return document_id


@pytest.mark.db
async def test_busca_nao_atravessa_a_fronteira_do_documento(
    documentos: tuple[PostgresDocumentRepository, PostgresConversationRepository],
    session_id: str,
) -> None:
    """AC-6: perguntar na conversa do documento A nunca traz chunk do documento B."""
    documents, conversations = documentos
    document_a = await _ingest(documents, session_id, "a.pdf", TRECHOS_DO_DOCUMENTO_A)
    await _ingest(documents, session_id, "b.pdf", TRECHOS_DO_DOCUMENTO_B)
    query = deterministic_vector(TRECHOS_DO_DOCUMENTO_B[0], EMBEDDING_DIM)

    recuperados = await conversations.search_chunks(document_a, query, limit=5)

    assert recuperados
    assert {chunk.content for chunk in recuperados} <= set(TRECHOS_DO_DOCUMENTO_A)
    for trecho in TRECHOS_DO_DOCUMENTO_B:
        assert all(chunk.content != trecho for chunk in recuperados)


@pytest.mark.db
async def test_busca_devolve_o_chunk_certo_com_score_maximo(
    documentos: tuple[PostgresDocumentRepository, PostgresConversationRepository],
    session_id: str,
) -> None:
    """O vetor da própria frase recupera aquela frase, com similaridade ~1."""
    documents, conversations = documentos
    document_a = await _ingest(documents, session_id, "a.pdf", TRECHOS_DO_DOCUMENTO_A)
    alvo = TRECHOS_DO_DOCUMENTO_A[1]
    query = deterministic_vector(alvo, EMBEDDING_DIM)

    recuperados = await conversations.search_chunks(document_a, query, limit=3)

    assert recuperados[0].content == alvo
    assert recuperados[0].score == 1.0
    assert recuperados[0].page_number == 2


@pytest.mark.db
async def test_busca_volta_ordenada_e_respeita_o_limite(
    documentos: tuple[PostgresDocumentRepository, PostgresConversationRepository],
    session_id: str,
) -> None:
    """AC-7: no máximo `limit` chunks, do mais similar para o menos, em `[0,1]`."""
    documents, conversations = documentos
    document_a = await _ingest(documents, session_id, "a.pdf", TRECHOS_DO_DOCUMENTO_A)
    query = deterministic_vector(TRECHOS_DO_DOCUMENTO_A[0], EMBEDDING_DIM)

    recuperados = await conversations.search_chunks(document_a, query, limit=2)

    assert len(recuperados) == 2
    scores = [chunk.score for chunk in recuperados]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= score <= 1.0 for score in scores)


@pytest.mark.db
async def test_documento_sem_chunks_devolve_lista_vazia(
    documentos: tuple[PostgresDocumentRepository, PostgresConversationRepository],
    session_id: str,
) -> None:
    """Sem candidato nenhum não há exceção — a recusa é decisão de `core`."""
    documents, conversations = documentos
    document_id = await documents.create("vazio.pdf", uuid4().hex, session_id)

    recuperados = await conversations.search_chunks(
        document_id, deterministic_vector("qualquer pergunta", EMBEDDING_DIM), limit=5
    )

    assert recuperados == []


class PoolFixo:
    """Um `Database` mínimo: só o `pool`, que é tudo que o repositório alcança.

    Existe para que o teste possa abrir a conexão com opções de planejamento
    próprias sem acrescentar um parâmetro a `Database` que só o teste usaria.
    """

    def __init__(self, pool: "asyncpg.Pool[Any]") -> None:
        self.pool = pool


@pytest.fixture
async def busca_com_indice_forcado() -> AsyncIterator[PostgresConversationRepository]:
    """Entrega um repositório que roda no regime em que o índice HNSW é usado.

    Com poucas dezenas de linhas o planejador escolhe varredura sequencial, que
    é exata — e nesse regime o defeito que este teste persegue **não aparece**.
    Desligar o `seqscan` e apertar o `ef_search` reproduz, com dados pequenos, o
    que aconteceria naturalmente num corpus grande: o índice devolve os vizinhos
    globais mais próximos, e o filtro por documento descarta parte deles.

    As duas opções viajam no `server_settings` da conexão, e **não** num
    `ALTER ROLE`: aqui elas nascem e morrem com este pool, enquanto no papel
    valeriam para toda conexão do projeto — inclusive as de outro teste rodando
    ao lado, e inclusive depois, se a suíte morresse antes de restaurá-las.
    """
    pool = await asyncpg.create_pool(
        dsn=Settings().database_url,
        min_size=1,
        max_size=2,
        server_settings={"enable_seqscan": "off", "hnsw.ef_search": "2"},
    )
    assert pool is not None
    try:
        yield PostgresConversationRepository(PoolFixo(pool))  # type: ignore[arg-type]
    finally:
        await pool.close()


@pytest.mark.db
async def test_busca_entrega_o_limite_pedido_mesmo_com_o_indice_em_uso(
    documentos: tuple[PostgresDocumentRepository, PostgresConversationRepository],
    session_id: str,
    busca_com_indice_forcado: PostgresConversationRepository,
) -> None:
    """O `LIMIT` pedido é o `LIMIT` entregue — senão a falta vira recusa falsa.

    Este é o teste do achado I-1 da avaliação da fase. Sem a varredura iterativa,
    o índice entrega os vizinhos globais e o `WHERE document_id` descarta o que
    veio do documento vizinho **sem repor**: a busca devolve uma ou duas linhas
    de um documento que tem dezenas, `has_grounding` dá falso, e o turno recusa
    uma pergunta que o documento responde — sem erro e sem log anômalo.

    O documento vizinho é maior de propósito: é ele que ocupa os candidatos
    globais e empurra os chunks do documento certo para fora do `ef_search`.
    """
    documents, _ = documentos
    alvo = [f"trecho {index} do documento consultado" for index in range(20)]
    vizinho = [f"trecho {index} do documento vizinho e maior" for index in range(200)]
    document_a = await _ingest(documents, session_id, "alvo.pdf", alvo)
    await _ingest(documents, session_id, "vizinho.pdf", vizinho)
    query = deterministic_vector("pergunta qualquer sobre o documento", EMBEDDING_DIM)

    recuperados = await busca_com_indice_forcado.search_chunks(document_a, query, limit=5)

    assert len(recuperados) == 5
    assert {chunk.content for chunk in recuperados} <= set(alvo)


@pytest.mark.db
async def test_a_varredura_iterativa_nao_vaza_para_as_outras_consultas(
    database: Database,
    documentos: tuple[PostgresDocumentRepository, PostgresConversationRepository],
    session_id: str,
) -> None:
    """`SET LOCAL` morre com a transação da busca, e não fica preso na conexão.

    Uma opção de planejamento que sobrevivesse à transação mudaria em silêncio o
    comportamento de toda consulta que pegasse aquela conexão do pool depois.
    """
    documents, conversations = documentos
    document_a = await _ingest(documents, session_id, "a.pdf", TRECHOS_DO_DOCUMENTO_A)

    await conversations.search_chunks(
        document_a, deterministic_vector("pergunta", EMBEDDING_DIM), limit=3
    )

    for _ in range(3):
        assert await database.pool.fetchval("SHOW hnsw.iterative_scan") == "off"
