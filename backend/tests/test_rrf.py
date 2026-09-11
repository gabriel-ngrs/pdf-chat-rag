"""Fusão RRF: a aritmética offline e o efeito dela contra o Postgres real.

A parte pura roda sem nada no ar. O que só o banco pode responder — que o
trecho com termo exato raro é achado pela via lexical, e não pela densa — fica
no fim, marcado `db`.
"""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest

from app.adapters.db import Database
from app.adapters.repository import PostgresConversationRepository, PostgresDocumentRepository
from app.config import Settings
from app.core.models import Chunk, RetrievedChunk
from app.core.retrieval import RRF_K, reciprocal_rank_fusion
from tests.fakes import deterministic_vector

EMBEDDING_DIM = 768
_DELETE_SQL = "DELETE FROM documents WHERE session_id = $1"

# O termo exato que a busca densa borra: um endereço de e-mail não tem vizinho
# semântico útil, e o vetor do trecho que o contém é quase idêntico ao de
# qualquer outro trecho do mesmo assunto.
EMAIL = "encarregado@exemplo.gov.br"


def _vetor_pergunta() -> list[float]:
    """A direção da pergunta: o primeiro eixo do espaço."""
    vetor = [0.0] * EMBEDDING_DIM
    vetor[0] = 1.0
    return vetor


def _vetor_proximo(semente: int) -> list[float]:
    """Quase paralelo à pergunta — cosseno acima de 0,99, com desempate estável."""
    vetor = _vetor_pergunta()
    vetor[2 + semente] = 0.02 * (semente + 1)
    norma = sum(valor * valor for valor in vetor) ** 0.5
    return [valor / norma for valor in vetor]


def _vetor_ortogonal() -> list[float]:
    """Perpendicular à pergunta: cosseno zero, como um endereço literal."""
    vetor = [0.0] * EMBEDDING_DIM
    vetor[1] = 1.0
    return vetor


def _chunk(index: int, score: float, page: int = 1, content: str = "") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_index=index,
        page_number=page,
        content=content or f"trecho {index}",
        score=score,
    )


# ─── A aritmética, offline ───────────────────────────────────────────────────


def test_chunk_presente_nas_duas_listas_sobe_na_frente_de_quem_lidera_uma_so() -> None:
    """O ponto da fusão: concordância entre as vias vale mais que liderança numa.

    O chunk 2 é o segundo colocado nas duas listas; o chunk 1 é o primeiro da
    densa e não aparece na lexical. Com `k = 60`, `2/(60+2) = 0,0323` supera
    `1/(60+1) = 0,0164`.
    """
    densa = [_chunk(1, 0.80), _chunk(2, 0.70), _chunk(3, 0.60)]
    lexical = [_chunk(4, 0.50), _chunk(2, 0.70)]

    fundida = reciprocal_rank_fusion(densa, lexical)

    assert [chunk.chunk_index for chunk in fundida][0] == 2


def test_ordenacao_completa_de_listas_conhecidas() -> None:
    """A ordem inteira, conferida contra a soma feita à mão."""
    densa = [_chunk(1, 0.90), _chunk(2, 0.80)]
    lexical = [_chunk(3, 0.70), _chunk(1, 0.90)]

    fundida = reciprocal_rank_fusion(densa, lexical)

    # 1: 1/61 + 1/62 = 0,03253 | 3: 1/61 = 0,01639 | 2: 1/62 = 0,01613
    assert [chunk.chunk_index for chunk in fundida] == [1, 3, 2]


def test_score_que_sai_e_o_denso_e_nao_o_da_fusao() -> None:
    """O limiar mede cosseno; trocar o campo apagaria a calibração da fase A.5."""
    densa = [_chunk(1, 0.812)]
    lexical = [_chunk(2, 0.640)]

    fundida = reciprocal_rank_fusion(densa, lexical)

    assert {chunk.chunk_index: chunk.score for chunk in fundida} == {1: 0.812, 2: 0.640}


def test_lista_lexical_vazia_devolve_a_densa_intacta() -> None:
    """Pergunta que não casa com termo nenhum não pode degradar a busca densa."""
    densa = [_chunk(1, 0.80), _chunk(2, 0.70), _chunk(3, 0.60)]

    assert reciprocal_rank_fusion(densa, []) == densa


def test_lista_densa_vazia_ainda_devolve_o_que_a_lexical_achou() -> None:
    lexical = [_chunk(7, 0.66)]

    assert [chunk.chunk_index for chunk in reciprocal_rank_fusion([], lexical)] == [7]


def test_duas_listas_vazias_devolvem_lista_vazia() -> None:
    assert reciprocal_rank_fusion([], []) == []


def test_empate_de_pontos_e_desempatado_pelo_score_denso() -> None:
    """Sem desempate, a ordem sairia do dicionário — não determinística."""
    densa = [_chunk(1, 0.70)]
    lexical = [_chunk(2, 0.90)]

    fundida = reciprocal_rank_fusion(densa, lexical)

    assert [chunk.chunk_index for chunk in fundida] == [2, 1]


def test_k_grande_faz_a_concordancia_pesar_mais_que_a_lideranca() -> None:
    """O porquê de `k` ser grande, medido nos dois extremos.

    O chunk 1 lidera a densa e não aparece na lexical; o chunk 3 é **terceiro
    nas duas**. Com `k = 60` as posições ficam achatadas e a concordância vence
    (`2/63 = 0,0317` contra `1/61 = 0,0164`); com `k = 0` a primeira posição
    domina (`1/1 = 1,0` contra `2/3 = 0,667`) e a liderança volta a ganhar.

    É essa a escolha que `k` faz, e é por isso que ele não é um número mágico:
    fundir duas listas com `k` pequeno é quase o mesmo que obedecer à lista que
    falou mais alto.
    """
    densa = [_chunk(1, 0.80), _chunk(2, 0.70), _chunk(3, 0.60)]
    lexical = [_chunk(4, 0.50), _chunk(5, 0.40), _chunk(3, 0.60)]

    assert reciprocal_rank_fusion(densa, lexical, k=RRF_K)[0].chunk_index == 3
    assert reciprocal_rank_fusion(densa, lexical, k=0)[0].chunk_index == 1


def test_fusao_e_pura_e_nao_altera_as_listas_recebidas() -> None:
    densa = [_chunk(1, 0.80), _chunk(2, 0.70)]
    lexical = [_chunk(2, 0.70)]
    copia_densa = list(densa)
    copia_lexical = list(lexical)

    reciprocal_rank_fusion(densa, lexical)

    assert densa == copia_densa
    assert lexical == copia_lexical


# ─── Contra o Postgres de verdade ────────────────────────────────────────────


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
    return f"teste-a7-{uuid4()}"


@pytest.fixture
async def documento(
    database: Database, session_id: str
) -> AsyncIterator[tuple[UUID, PostgresConversationRepository]]:
    """Um documento cujo e-mail vive num trecho, e o assunto "contato" noutros.

    O desenho é o do corpus real: vários trechos falam de contato e atendimento,
    e só um carrega o endereço literal. É exatamente o caso em que a distância
    de cosseno não separa — na fase A.5 o trecho certo ganhou por 0,001.
    """
    documents = PostgresDocumentRepository(database)
    conversations = PostgresConversationRepository(database)
    # Os vetores são construídos à mão, e não derivados de hash: o dublê de
    # embedding produz direções aleatórias, e sobre elas "a busca densa não acha
    # o trecho" seria sorte, não desenho. Aqui os quatro trechos de assunto
    # ficam quase paralelos à pergunta e o do e-mail fica ortogonal — que é o
    # retrato do problema real, onde o endereço literal não tem vizinho
    # semântico e o assunto tem vários.
    trechos = [
        "O controlador atende titulares no Brasil e no exterior, com contato direto.",
        "O time responde dúvidas de atendimento e contato comercial todo dia.",
        "Canais de contato e atendimento ao cliente funcionam em horário comercial.",
        f"Encarregado pelo tratamento de dados · {EMAIL} · Brasília, DF",
        "O contato com o time de suporte acontece pelo canal de atendimento.",
    ]
    document_id = await documents.create("contato.pdf", uuid4().hex, session_id)
    chunks = [
        Chunk(chunk_index=index, page_number=index + 1, content=trecho)
        for index, trecho in enumerate(trechos)
    ]
    embeddings = [
        _vetor_ortogonal() if EMAIL in chunk.content else _vetor_proximo(index)
        for index, chunk in enumerate(chunks)
    ]
    await documents.insert_chunks(document_id, chunks, embeddings)
    try:
        yield document_id, conversations
    finally:
        await database.pool.execute(_DELETE_SQL, session_id)


@pytest.mark.db
async def test_termo_exato_raro_entra_no_resultado_pela_via_lexical(
    documento: tuple[UUID, PostgresConversationRepository],
) -> None:
    """O teste que dá sentido à fase: o trecho do e-mail entra porque a lexical o achou.

    As duas chamadas são a mesma busca, no mesmo corpus, com e sem a via
    lexical. A densa sozinha não traz o trecho do endereço — ele é ortogonal à
    pergunta. Com a fusão ele entra no conjunto, e é essa diferença que prova de
    quem foi o mérito.
    """
    document_id, conversations = documento
    pergunta = _vetor_pergunta()

    so_densa = await conversations.search_chunks(document_id, pergunta, 3)
    hibrida = await conversations.search_chunks(document_id, pergunta, 3, EMAIL)

    assert all(EMAIL not in chunk.content for chunk in so_densa), (
        "a busca densa já achava o e-mail — o teste não provaria nada"
    )
    assert any(EMAIL in chunk.content for chunk in hibrida), (
        "a via lexical não trouxe o trecho do termo exato"
    )


@pytest.mark.db
async def test_busca_lexical_isola_por_documento(
    documento: tuple[UUID, PostgresConversationRepository],
    database: Database,
    session_id: str,
) -> None:
    """AC-6 vale para a via nova também: termo exato não atravessa documento."""
    document_id, conversations = documento
    documents = PostgresDocumentRepository(database)
    vizinho = await documents.create("vizinho.pdf", uuid4().hex, session_id)
    texto = f"Outro documento, com o mesmo {EMAIL} dentro."
    await documents.insert_chunks(
        vizinho,
        [Chunk(chunk_index=0, page_number=1, content=texto)],
        [deterministic_vector(texto, EMBEDDING_DIM)],
    )

    achados = await conversations.search_chunks_lexical(
        document_id, EMAIL, 5, deterministic_vector("contato", EMBEDDING_DIM)
    )

    assert achados
    assert all(texto != chunk.content for chunk in achados)


@pytest.mark.db
async def test_pergunta_sem_termo_no_documento_nao_quebra_a_busca(
    documento: tuple[UUID, PostgresConversationRepository],
) -> None:
    """Lexical vazia é caso normal: a híbrida vira a densa, sem caminho especial."""
    document_id, conversations = documento
    embedding = deterministic_vector("qual o canal de contato?", EMBEDDING_DIM)

    so_densa = await conversations.search_chunks(document_id, embedding, 3)
    hibrida = await conversations.search_chunks(document_id, embedding, 3, "xilofone quântico")

    assert [chunk.chunk_index for chunk in hibrida] == [chunk.chunk_index for chunk in so_densa]


@pytest.mark.db
async def test_pergunta_com_pontuacao_nao_vira_erro_de_sintaxe(
    documento: tuple[UUID, PostgresConversationRepository],
) -> None:
    """`plainto_tsquery` existe para isto: gente digita `?`, `&` e aspas."""
    document_id, conversations = documento
    embedding = deterministic_vector("contato", EMBEDDING_DIM)

    achados = await conversations.search_chunks(
        document_id, embedding, 3, "qual o e-mail & o telefone de contato?"
    )

    assert achados


@pytest.mark.db
async def test_fusao_nao_devolve_mais_do_que_o_limite_pedido(
    documento: tuple[UUID, PostgresConversationRepository],
) -> None:
    """Duas listas de até `limit` cada não podem virar uma de `2 * limit`."""
    document_id, conversations = documento
    embedding = deterministic_vector("contato e atendimento", EMBEDDING_DIM)

    hibrida = await conversations.search_chunks(document_id, embedding, 2, "contato atendimento")

    assert len(hibrida) == 2
