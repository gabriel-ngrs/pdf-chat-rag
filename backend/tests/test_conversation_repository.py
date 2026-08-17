"""Persistência de conversas: a ida e volta das citações, offline e no Postgres.

O arquivo tem duas metades de propósito.

A primeira é **offline**, sem marcador: cobre `serialize_citations` e
`deserialize_citations`, que são o ponto onde o tipo do domínio e a coluna
`jsonb` se encontram. É ali que o erro nasce calado — o asyncpg devolve `jsonb`
como `str`, e um código que aceite a string como se fosse lista produz zero
citações sem levantar nada. Este par de funções não precisa de banco para ser
provado, e um teste que exigisse container para verificá-lo seria obstáculo.

A segunda é marcada `db` e roda contra o Postgres do compose, como
`test_ingestion_db.py`. O que só ela prova: que `db/002_conversations.sql`
aplica depois de `001` sem erro, que o SQL escrito à mão casa com as colunas
reais, que a ordem cronológica sobrevive à ida e volta (AC-11) e que o
`ON DELETE CASCADE` declarado na origem leva conversas e mensagens junto com o
documento.

Cada teste de banco cria os próprios dados sob um `session_id` exclusivo e os
apaga no fim; nada que já esteja no banco é lido ou removido.
"""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest

from app.adapters.db import Database
from app.adapters.repository import (
    PostgresConversationRepository,
    PostgresDocumentRepository,
    deserialize_citations,
    serialize_citations,
)
from app.config import Settings
from app.core.models import Citation, MessageRole
from app.errors import InternalError

_DELETE_SQL = "DELETE FROM documents WHERE session_id = $1"

_COUNT_CONVERSATIONS_SQL = "SELECT count(*) FROM conversations WHERE id = $1"

_COUNT_MESSAGES_SQL = "SELECT count(*) FROM messages WHERE conversation_id = $1"

_RAW_CITATIONS_SQL = """
    SELECT citations, pg_typeof(citations)::text AS tipo
      FROM messages
     WHERE id = $1
"""

_UMA_CITACAO_JSON = '[{"page_number": 2, "snippet": "t", "chunk_index": 1, "score": 0.5}]'

_UMA_CITACAO = (Citation(page_number=2, snippet="t", chunk_index=1, score=0.5),)


def citacoes_de_exemplo() -> tuple[Citation, ...]:
    """Duas citações com acento, aspas e score fracionário — os três riscos."""
    return (
        Citation(
            page_number=3,
            snippet='Trecho da página três com acentuação e aspas: "serviços".',
            chunk_index=7,
            score=0.812,
        ),
        Citation(
            page_number=1,
            snippet="Trecho da primeira página.",
            chunk_index=0,
            score=0.6,
        ),
    )


# ── Serialização de citações (offline, sem banco) ────────────────────────────


def test_citacoes_voltam_iguais_depois_de_virar_texto_json() -> None:
    """O par serializa/desserializa é identidade: nenhum campo se perde no caminho."""
    citacoes = citacoes_de_exemplo()

    voltaram = deserialize_citations(serialize_citations(citacoes))

    assert voltaram == citacoes


def test_a_desserializacao_devolve_tupla_e_nao_lista() -> None:
    """`Message.citations` é `tuple` para que `frozen=True` signifique algo."""
    voltaram = deserialize_citations(serialize_citations(citacoes_de_exemplo()))

    assert isinstance(voltaram, tuple)


def test_o_json_gravado_preserva_acentuacao_em_vez_de_escapar() -> None:
    """`ensure_ascii=False`: o `jsonb` guarda texto legível, não escape unicode."""
    texto = serialize_citations(citacoes_de_exemplo())

    assert "página" in texto
    assert "\\u" not in texto


def test_serializar_sem_citacao_produz_lista_json_vazia() -> None:
    """É o valor que a pergunta do usuário e a recusa gravam na coluna."""
    assert serialize_citations(()) == "[]"


@pytest.mark.parametrize(
    "gravado",
    [
        pytest.param(_UMA_CITACAO_JSON, id="str-como-o-asyncpg-devolve"),
        pytest.param(_UMA_CITACAO_JSON.encode("utf-8"), id="bytes"),
        pytest.param(
            [{"page_number": 2, "snippet": "t", "chunk_index": 1, "score": 0.5}],
            id="lista-ja-decodificada",
        ),
    ],
)
def test_a_leitura_aceita_as_formas_em_que_o_jsonb_pode_chegar(gravado: object) -> None:
    """O asyncpg entrega `jsonb` como `str`; um codec no pool entregaria lista.

    As três formas produzem a mesma citação — é isso que impede o bug de iterar
    a string caractere a caractere e devolver lixo sem nenhuma exceção.
    """
    assert deserialize_citations(gravado) == _UMA_CITACAO


@pytest.mark.parametrize(
    "vazio",
    [
        pytest.param("[]", id="json-vazio"),
        pytest.param([], id="lista-vazia"),
        pytest.param(None, id="nulo"),
    ],
)
def test_ausencia_de_citacao_vira_tupla_vazia(vazio: object) -> None:
    """Recusa e pergunta do usuário não têm citação, e isso não é erro."""
    assert deserialize_citations(vazio) == ()


@pytest.mark.parametrize(
    "corrompido",
    [
        pytest.param("nao é json", id="texto-solto"),
        pytest.param('{"page_number": 1}', id="objeto-em-vez-de-lista"),
        pytest.param('[{"page_number": 1, "snippet": "t"}]', id="campo-faltando"),
        pytest.param(
            '[{"page_number": "x", "snippet": "t", "chunk_index": 1, "score": 0.5}]',
            id="tipo-errado",
        ),
        pytest.param("[42]", id="item-que-nao-e-objeto"),
    ],
)
def test_citacao_corrompida_falha_alto_em_vez_de_sumir(corrompido: str) -> None:
    """Payload fora do formato é inconsistência de schema, não resposta vazia.

    Devolver `()` aqui faria a UI exibir uma resposta fundamentada como se não
    tivesse fundamento — o erro mais caro que este módulo pode cometer.
    """
    with pytest.raises(InternalError):
        deserialize_citations(corrompido)


# ── Round-trip contra o Postgres ─────────────────────────────────────────────


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
    return f"teste-a1-chat-{uuid4()}"


@pytest.fixture
async def conversas(
    database: Database, session_id: str
) -> AsyncIterator[PostgresConversationRepository]:
    repository = PostgresConversationRepository(database)
    try:
        yield repository
    finally:
        # `ON DELETE CASCADE` leva conversas e mensagens junto com o documento;
        # nada fora desta sessão é tocado.
        await database.pool.execute(_DELETE_SQL, session_id)


@pytest.fixture
async def documento(database: Database, session_id: str) -> UUID:
    """Um documento da sessão do teste, para a conversa ter a que se prender."""
    documentos = PostgresDocumentRepository(database)
    return await documentos.create("documento.pdf", uuid4().hex, session_id)


@pytest.mark.db
async def test_o_historico_atravessa_o_banco_na_ordem_e_com_as_citacoes(
    conversas: PostgresConversationRepository, documento: UUID
) -> None:
    """AC-11: três trocas voltam como seis mensagens, em ordem e com citações."""
    conversation_id = await conversas.create_conversation(documento, "sessao-de-teste")
    citacoes = citacoes_de_exemplo()

    for turno in range(3):
        await conversas.add_message(conversation_id, MessageRole.USER, f"Pergunta {turno}?")
        await conversas.add_message(
            conversation_id, MessageRole.ASSISTANT, f"Resposta {turno}.", citacoes
        )

    historico = await conversas.list_messages(conversation_id)

    assert [mensagem.content for mensagem in historico] == [
        "Pergunta 0?",
        "Resposta 0.",
        "Pergunta 1?",
        "Resposta 1.",
        "Pergunta 2?",
        "Resposta 2.",
    ]
    assert [mensagem.role for mensagem in historico] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ] * 3
    respostas = [mensagem for mensagem in historico if mensagem.role is MessageRole.ASSISTANT]
    perguntas = [mensagem for mensagem in historico if mensagem.role is MessageRole.USER]
    assert all(mensagem.citations == citacoes for mensagem in respostas)
    assert all(mensagem.citations == () for mensagem in perguntas)
    assert all(mensagem.truncated is False for mensagem in historico)


@pytest.mark.db
async def test_a_mensagem_gravada_volta_com_o_id_e_o_instante_do_banco(
    conversas: PostgresConversationRepository, documento: UUID
) -> None:
    """O `id` de `add_message` é o que o evento SSE `done` publica (§4.3)."""
    conversation_id = await conversas.create_conversation(documento, None)

    gravada = await conversas.add_message(conversation_id, MessageRole.USER, "Olá?")

    assert isinstance(gravada.id, int)
    assert gravada.created_at is not None
    assert gravada.role is MessageRole.USER
    historico = await conversas.list_messages(conversation_id)
    assert [mensagem.id for mensagem in historico] == [gravada.id]


@pytest.mark.db
async def test_resposta_parcial_e_gravada_como_truncada(
    conversas: PostgresConversationRepository, documento: UUID
) -> None:
    """AC-11: um stream interrompido não pode ser lido como resposta completa."""
    conversation_id = await conversas.create_conversation(documento, None)

    parcial = await conversas.add_message(
        conversation_id, MessageRole.ASSISTANT, "Resposta pela met", (), True
    )

    assert parcial.truncated is True
    historico = await conversas.list_messages(conversation_id)
    assert historico[0].truncated is True


@pytest.mark.db
async def test_as_citacoes_ficam_na_coluna_como_jsonb(
    database: Database, conversas: PostgresConversationRepository, documento: UUID
) -> None:
    """O tipo real da coluna é `jsonb`, e não `text` com JSON dentro.

    Sem esta verificação, gravar sem o cast `$4::jsonb` passaria despercebido
    até o dia em que alguém consultasse a coluna por operador de JSON.
    """
    conversation_id = await conversas.create_conversation(documento, None)
    gravada = await conversas.add_message(
        conversation_id, MessageRole.ASSISTANT, "Resposta.", citacoes_de_exemplo()
    )

    linha = await database.pool.fetchrow(_RAW_CITATIONS_SQL, gravada.id)

    assert linha is not None
    assert linha["tipo"] == "jsonb"
    assert deserialize_citations(linha["citations"]) == citacoes_de_exemplo()


@pytest.mark.db
async def test_conversa_inexistente_devolve_none(
    conversas: PostgresConversationRepository,
) -> None:
    """`None`, não exceção: virar `404` é decisão da rota, não do repositório."""
    assert await conversas.get_conversation(uuid4()) is None


@pytest.mark.db
async def test_a_conversa_lida_aponta_para_o_documento_de_origem(
    conversas: PostgresConversationRepository, documento: UUID
) -> None:
    """É esse `document_id` que o retrieval usa para não vazar outro documento."""
    conversation_id = await conversas.create_conversation(documento, "sessao-de-teste")

    registro = await conversas.get_conversation(conversation_id)

    assert registro is not None
    assert registro.id == conversation_id
    assert registro.document_id == documento
    assert registro.session_id == "sessao-de-teste"


@pytest.mark.db
async def test_apagar_o_documento_leva_conversa_e_mensagens_junto(
    database: Database,
    conversas: PostgresConversationRepository,
    documento: UUID,
    session_id: str,
) -> None:
    """O `ON DELETE CASCADE` declarado em `002`, exercido de ponta a ponta."""
    conversation_id = await conversas.create_conversation(documento, session_id)
    await conversas.add_message(conversation_id, MessageRole.USER, "Pergunta?")

    await database.pool.execute(_DELETE_SQL, session_id)

    assert await database.pool.fetchval(_COUNT_CONVERSATIONS_SQL, conversation_id) == 0
    assert await database.pool.fetchval(_COUNT_MESSAGES_SQL, conversation_id) == 0
