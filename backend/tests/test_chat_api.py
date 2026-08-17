"""Um turno de chat de ponta a ponta, com os dublês no lugar do banco e do provedor.

O que este arquivo prova é o que o uso normal esconde. Quatro dos caminhos do
chat só existem sob falha — recusa, erro antes do primeiro evento, erro depois
dele e desconexão do cliente — e nenhum deles aparece numa conversa que dá
certo. Sem teste, os quatro só seriam descobertos na frente de quem avalia.

Duas disciplinas organizam as asserções, porque o texto que um modelo gera não é
determinístico e asserir sobre ele seria testar o provedor:

* **Estrutura**, não conteúdo: a ordem dos eventos SSE, os campos de cada
  payload, o status e o envelope de erro.
* **O que chegou aos colaboradores**: a query que foi ao retrieval (pelo vetor
  que o `search_chunks` recebeu), o prompt que chegou ao cliente de chat, e o
  que foi gravado no repositório.

A desconexão é o único caso exercitado sem o servidor HTTP: sob
`httpx.ASGITransport` o `is_disconnected()` do Starlette responde sempre `False`
— não há socket para cair —, então o gerador é consumido diretamente, que é
justamente o que a separação entre `app.chat` e `app.api.conversations` existe
para permitir.
"""

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import httpx

from app.adapters.gemini import (
    CHAT_QUOTA_MESSAGE,
    ChatProviderError,
    ChatQuotaError,
    EmbeddingQuotaError,
)
from app.api.conversations import NOT_READY_MESSAGE
from app.chat import stream_turn
from app.config import Settings
from app.core.condensation import CONDENSATION_INSTRUCTIONS
from app.core.models import DocumentStatus, MessageRole, RetrievedChunk
from app.core.prompt import REFUSAL_MESSAGE
from app.core.retrieval import SNIPPET_MAX_LENGTH
from tests.fakes import (
    FakeChatClient,
    FakeConversationRepository,
    FakeEmbeddingClient,
    FakeRepository,
    matches_embedding,
)

PERGUNTA = "quais servicos a YAITEC oferece?"
CONTINUACAO = "e quanto a isso?"

# Um trecho longo o bastante para o recorte da citação ter o que cortar: o
# `snippet` promete no máximo 240 caracteres em fronteira de palavra, e um texto
# curto tornaria a promessa vacuamente verdadeira.
TRECHO_LONGO = (
    "A YAITEC desenvolve software sob medida para empresas que precisam de "
    "integracao entre sistemas legados e plataformas modernas, cobrindo "
    "descoberta, arquitetura, implementacao e sustentacao do que foi entregue, "
    "com equipes dedicadas por projeto e prazos acordados antes do inicio."
)


def chunk(
    score: float, *, index: int = 0, page: int = 2, texto: str = TRECHO_LONGO
) -> RetrievedChunk:
    """Um chunk recuperado com o score que o teste quer exercitar."""
    return RetrievedChunk(chunk_index=index, page_number=page, content=texto, score=score)


# Acima do `similarity_threshold` de 0,625 da fixture de configuração.
FUNDAMENTADOS = [
    chunk(0.91, index=3, page=2),
    chunk(0.71, index=7, page=5, texto="Contato: sao paulo."),
]
# Abaixo dele: é o que o retrieval devolve para uma pergunta sem relação nenhuma.
SEM_FUNDAMENTO = [chunk(0.41, index=1), chunk(0.12, index=2)]


def eventos(response: httpx.Response) -> list[tuple[str, dict[str, Any]]]:
    """Quebra o corpo SSE nos pares `(evento, payload)` que ele carrega.

    O parser é escrito aqui de propósito: ele lê o frame exatamente como o
    cliente do navegador lê (`event:` e `data:` separados por linha em branco),
    então uma mudança no formato do fio quebra este teste — que é o ponto.
    """
    frames = []
    for bloco in response.text.split("\n\n"):
        if not bloco.strip():
            continue
        campos = dict(linha.split(": ", 1) for linha in bloco.splitlines() if ": " in linha)
        frames.append((campos["event"], json.loads(campos["data"])))
    return frames


def nomes(frames: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [nome for nome, _ in frames]


def payload(frames: list[tuple[str, dict[str, Any]]], nome: str) -> dict[str, Any]:
    """O payload do primeiro evento com aquele nome; falha se não houver."""
    for evento, dados in frames:
        if evento == nome:
            return dados
    raise AssertionError(f"o evento {nome!r} não foi emitido: {nomes(frames)}")


def texto_gerado(frames: list[tuple[str, dict[str, Any]]]) -> str:
    """Os tokens concatenados, que é como a interface monta a resposta."""
    return "".join(dados["text"] for nome, dados in frames if nome == "token")


async def documento_pronto(repository: FakeRepository) -> UUID:
    document_id = await repository.create("documento.pdf", "hash-chat", None)
    await repository.set_status(document_id, DocumentStatus.READY)
    return document_id


async def abrir_conversa(client: httpx.AsyncClient, repository: FakeRepository) -> str:
    """Cria documento pronto e conversa, devolvendo o id da conversa."""
    document_id = await documento_pronto(repository)
    response = await client.post("/api/conversations", json={"document_id": str(document_id)})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def perguntar(
    client: httpx.AsyncClient, conversation_id: str, question: str = PERGUNTA, **kwargs: Any
) -> httpx.Response:
    return await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"question": question}, **kwargs
    )


# ─── Criação da conversa ─────────────────────────────────────────────────────


async def test_conversa_sobre_documento_pronto_devolve_201_com_id(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
) -> None:
    """O id devolvido é o que o cliente guarda para o resto da conversa (FR-1)."""
    async with build_client() as client:
        document_id = await documento_pronto(repository)
        response = await client.post(
            "/api/conversations",
            json={"document_id": str(document_id)},
            headers={"X-Session-Id": "sessao-1"},
        )

    assert response.status_code == 201
    conversation_id = UUID(response.json()["id"])
    registro = conversations.conversations[conversation_id]
    assert registro.document_id == document_id
    assert registro.session_id == "sessao-1"


async def test_documento_ainda_processando_recusa_a_conversa_com_409(
    build_client: Callable[..., httpx.AsyncClient], repository: FakeRepository
) -> None:
    """AC-1: `409` e `documento_nao_pronto`, não `404` nem `422`."""
    async with build_client() as client:
        document_id = await repository.create("documento.pdf", "hash-chat", None)
        await repository.set_status(document_id, DocumentStatus.PROCESSING)
        response = await client.post("/api/conversations", json={"document_id": str(document_id)})

    assert response.status_code == 409
    assert response.json() == {"code": "documento_nao_pronto", "message": NOT_READY_MESSAGE}


async def test_documento_inexistente_recusa_a_conversa_com_404(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """Documento que nunca existiu é `nao_encontrado`, e não documento não pronto."""
    async with build_client() as client:
        response = await client.post("/api/conversations", json={"document_id": str(uuid4())})

    assert response.status_code == 404
    assert response.json()["code"] == "nao_encontrado"


async def test_pergunta_em_conversa_inexistente_devolve_404(
    build_client: Callable[..., httpx.AsyncClient],
) -> None:
    """A conversa é verificada antes de o turno começar, com envelope HTTP normal."""
    async with build_client() as client:
        response = await perguntar(client, str(uuid4()))

    assert response.status_code == 404
    assert response.json()["code"] == "nao_encontrado"


# ─── O turno que dá certo ────────────────────────────────────────────────────


async def test_tokens_concatenados_formam_a_resposta_gravada(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    chat_client: FakeChatClient,
) -> None:
    """AC-2: a resposta chega em pedaços e o que foi gravado é a soma deles."""
    conversations.chunks = FUNDAMENTADOS
    async with build_client() as client:
        conversation_id = await abrir_conversa(client, repository)
        response = await perguntar(client, conversation_id)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = eventos(response)
    assert nomes(frames) == ["token"] * len(chat_client.pieces) + ["citations", "done"]
    assert texto_gerado(frames) == "".join(chat_client.pieces)

    gravadas = conversations.contents_of(UUID(conversation_id))
    assert gravadas == [
        (MessageRole.USER.value, PERGUNTA),
        (MessageRole.ASSISTANT.value, "".join(chat_client.pieces)),
    ]
    assert payload(frames, "done") == {"message_id": 2, "truncated": False}


async def test_pergunta_e_gravada_antes_de_qualquer_chamada_ao_provedor(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    journal: list[str],
) -> None:
    """FR-9: o histórico fica coerente mesmo se o processo morrer no meio do turno."""
    conversations.chunks = FUNDAMENTADOS
    async with build_client() as client:
        conversation_id = await abrir_conversa(client, repository)
        await perguntar(client, conversation_id)

    do_turno = journal[journal.index("list_messages") :]
    assert do_turno.index("add_message") < do_turno.index("search_chunks")
    assert do_turno.index("add_message") < do_turno.index("stream_answer")


async def test_citacoes_trazem_pagina_trecho_indice_e_score(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
) -> None:
    """AC-10: a citação é dado estruturado, e o trecho já vem recortado do servidor."""
    conversations.chunks = [chunk(0.91, index=3, page=2, texto=TRECHO_LONGO * 2)]
    async with build_client() as client:
        conversation_id = await abrir_conversa(client, repository)
        response = await perguntar(client, conversation_id)

    citacoes = payload(eventos(response), "citations")["citations"]
    assert len(citacoes) == 1
    citacao = citacoes[0]
    assert citacao["page_number"] == 2
    assert citacao["chunk_index"] == 3
    assert citacao["score"] == 0.91
    assert len(citacao["snippet"]) <= SNIPPET_MAX_LENGTH
    # Recorte em fronteira de palavra: o texto antes das reticências é prefixo do
    # trecho original, sem nenhuma palavra partida ao meio.
    assert (TRECHO_LONGO * 2).startswith(citacao["snippet"].removesuffix("…").rstrip())


async def test_historico_devolve_as_seis_mensagens_na_ordem_com_citacoes(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
) -> None:
    """AC-11: três trocas, seis mensagens, citações presas às respostas."""
    conversations.chunks = FUNDAMENTADOS
    async with build_client() as client:
        conversation_id = await abrir_conversa(client, repository)
        for numero in (1, 2, 3):
            resposta = await perguntar(client, conversation_id, f"pergunta numero {numero}?")
            assert resposta.status_code == 200
        historico = await client.get(f"/api/conversations/{conversation_id}/messages")

    assert historico.status_code == 200
    mensagens = historico.json()
    assert [mensagem["role"] for mensagem in mensagens] == ["user", "assistant"] * 3
    assert [mensagem["id"] for mensagem in mensagens] == sorted(
        mensagem["id"] for mensagem in mensagens
    )
    perguntas = [mensagem["content"] for mensagem in mensagens if mensagem["role"] == "user"]
    assert perguntas == [f"pergunta numero {numero}?" for numero in (1, 2, 3)]
    for mensagem in mensagens:
        esperado = 2 if mensagem["role"] == "assistant" else 0
        assert len(mensagem["citations"]) == esperado
        assert mensagem["truncated"] is False


# ─── Recusa ──────────────────────────────────────────────────────────────────


async def test_pergunta_sem_fundamento_recusa_sem_chamar_o_modelo(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    chat_client: FakeChatClient,
) -> None:
    """AC-8: nada acima do limiar, resposta de recusa, citações vazias, zero geração."""
    conversations.chunks = SEM_FUNDAMENTO
    async with build_client() as client:
        conversation_id = await abrir_conversa(client, repository)
        response = await perguntar(client, conversation_id, "qual a cotacao do dolar hoje?")

    frames = eventos(response)
    assert nomes(frames) == ["token", "citations", "done"]
    assert texto_gerado(frames) == REFUSAL_MESSAGE
    assert payload(frames, "citations") == {"citations": []}
    assert payload(frames, "done")["truncated"] is False
    assert chat_client.stream_calls == 0, "a recusa não pode custar uma chamada ao provedor"
    assert conversations.contents_of(UUID(conversation_id))[-1] == (
        MessageRole.ASSISTANT.value,
        REFUSAL_MESSAGE,
    )


async def test_recusa_emite_o_evento_de_log_com_o_top_score(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    captured_logs: list[dict[str, Any]],
) -> None:
    """§4.6: a decisão de recusar é registrada com o score que a motivou."""
    conversations.chunks = SEM_FUNDAMENTO
    async with build_client() as client:
        conversation_id = await abrir_conversa(client, repository)
        await perguntar(client, conversation_id, "qual a cotacao do dolar hoje?")

    recusas = [entrada for entrada in captured_logs if entrada["event"] == "chat.refused"]
    assert len(recusas) == 1
    assert recusas[0]["conversation_id"] == conversation_id
    assert recusas[0]["top_score"] == 0.41


# ─── Condensação ─────────────────────────────────────────────────────────────


async def test_pergunta_de_continuacao_chega_condensada_ao_retrieval(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    chat_client: FakeChatClient,
    embedder: FakeEmbeddingClient,
) -> None:
    """FR-3: o retrieval busca a query reescrita, não o pronome que ninguém indexa."""
    conversations.chunks = FUNDAMENTADOS
    async with build_client() as client:
        conversation_id = await abrir_conversa(client, repository)
        await perguntar(client, conversation_id)
        chat_client.stream_prompts.clear()
        await perguntar(client, conversation_id, CONTINUACAO)

    assert len(chat_client.generate_prompts) == 1, "a primeira pergunta não devia condensar"
    assert CONDENSATION_INSTRUCTIONS in chat_client.generate_prompts[0]
    assert PERGUNTA in chat_client.generate_prompts[0]

    assert embedder.query_calls[-1] == chat_client.condensed
    assert matches_embedding(
        conversations.searches[-1].embedding, chat_client.condensed, embedder.dim
    )


async def test_condensacao_que_estoura_o_timeout_cai_no_fallback_sem_erro_visivel(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    settings: Settings,
    embedder: FakeEmbeddingClient,
    captured_logs: list[dict[str, Any]],
) -> None:
    """AC-5: a query vira "pergunta anterior + atual" e o usuário não vê nada quebrar."""
    conversations.chunks = FUNDAMENTADOS
    lento = FakeChatClient(generate_delay=30.0)
    config = settings.model_copy(update={"condense_timeout_seconds": 0})

    async with build_client(chat=lento, config=config) as client:
        conversation_id = await abrir_conversa(client, repository)
        await perguntar(client, conversation_id)
        response = await perguntar(client, conversation_id, CONTINUACAO)

    frames = eventos(response)
    assert "error" not in nomes(frames)
    assert nomes(frames)[-1] == "done"

    esperada = f"{PERGUNTA} {CONTINUACAO}"
    assert embedder.query_calls[-1] == esperada
    assert matches_embedding(conversations.searches[-1].embedding, esperada, embedder.dim)

    condensacoes = [item for item in captured_logs if item["event"] == "chat.condensed"]
    assert condensacoes[-1]["fallback"] is True
    assert condensacoes[-1]["used_llm"] is False


async def test_pergunta_autocontida_nao_gasta_chamada_de_condensacao(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    chat_client: FakeChatClient,
    embedder: FakeEmbeddingClient,
) -> None:
    """FR-3: sem histórico não há o que resolver, e a query é a própria pergunta."""
    conversations.chunks = FUNDAMENTADOS
    async with build_client() as client:
        conversation_id = await abrir_conversa(client, repository)
        await perguntar(client, conversation_id)

    assert chat_client.generate_prompts == []
    assert embedder.query_calls == [PERGUNTA]


# ─── Erro do provedor: antes e depois do primeiro evento ─────────────────────


async def test_erro_antes_do_primeiro_evento_vira_resposta_http_com_envelope(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    chat_client: FakeChatClient,
    captured_logs: list[dict[str, Any]],
) -> None:
    """AC-12, metade `pre_stream`: quota estourada no embedding da query.

    Nenhum byte de SSE saiu ainda, então o erro cabe no envelope `{code,
    message}` com o status certo — e não num `text/event-stream` que abre para
    morrer no primeiro frame.
    """
    conversations.chunks = FUNDAMENTADOS
    quebrado = FakeEmbeddingClient(error=EmbeddingQuotaError(CHAT_QUOTA_MESSAGE))

    async with build_client(embedding_client=quebrado) as client:
        conversation_id = await abrir_conversa(client, repository)
        response = await perguntar(client, conversation_id)

    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"code": "limite_de_uso", "message": CHAT_QUOTA_MESSAGE}
    assert chat_client.stream_calls == 0

    erros = [item for item in captured_logs if item["event"] == "chat.error"]
    assert [item["phase"] for item in erros] == ["pre_stream"]
    assert erros[0]["conversation_id"] == conversation_id
    assert erros[0]["code"] == "limite_de_uso"


async def test_erro_depois_do_primeiro_token_vira_evento_error_e_grava_parcial(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    captured_logs: list[dict[str, Any]],
) -> None:
    """AC-12, metade `mid_stream`, e AC-11: o parcial é gravado como parcial."""
    conversations.chunks = FUNDAMENTADOS
    quebrado = FakeChatClient(stream_error=ChatQuotaError(CHAT_QUOTA_MESSAGE), error_after=1)

    async with build_client(chat=quebrado) as client:
        conversation_id = await abrir_conversa(client, repository)
        response = await perguntar(client, conversation_id)

    assert response.status_code == 200
    frames = eventos(response)
    assert nomes(frames) == ["token", "error"]
    assert payload(frames, "error") == {"code": "limite_de_uso", "message": CHAT_QUOTA_MESSAGE}

    gravadas = conversations.messages[UUID(conversation_id)]
    assert gravadas[-1].content == quebrado.pieces[0]
    assert gravadas[-1].truncated is True

    erros = [item for item in captured_logs if item["event"] == "chat.error"]
    assert [item["phase"] for item in erros] == ["mid_stream"]
    assert erros[0]["conversation_id"] == conversation_id


async def test_falha_do_provedor_na_abertura_do_stream_nao_vira_mensagem_vazia(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    captured_logs: list[dict[str, Any]],
) -> None:
    """Turno sem texto nenhum é registrado em log e **não** vira balão em branco.

    Uma linha de assistente vazia apareceria na tela e entraria na janela de
    histórico do turno seguinte como se fosse resposta.
    """
    conversations.chunks = FUNDAMENTADOS
    quebrado = FakeChatClient(stream_error=ChatProviderError("provedor fora do ar"))

    async with build_client(chat=quebrado) as client:
        conversation_id = await abrir_conversa(client, repository)
        response = await perguntar(client, conversation_id)

    # A falha aconteceu antes de qualquer evento, então ela ainda cabe no
    # envelope HTTP — é a metade `pre_stream` de FR-11, e é o caso comum.
    assert response.status_code == 502
    assert response.json()["code"] == "provedor"
    assert conversations.contents_of(UUID(conversation_id)) == [(MessageRole.USER.value, PERGUNTA)]
    assert [item["event"] for item in captured_logs].count("chat.answer_empty") == 1

    erros = [item for item in captured_logs if item["event"] == "chat.error"]
    assert [item["phase"] for item in erros] == ["pre_stream"]


async def test_quota_na_abertura_do_stream_sai_como_http_429(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
) -> None:
    """AC-12: `429` antes do primeiro evento é resposta HTTP, não evento `error`."""
    conversations.chunks = FUNDAMENTADOS
    quebrado = FakeChatClient(stream_error=ChatQuotaError(CHAT_QUOTA_MESSAGE))

    async with build_client(chat=quebrado) as client:
        conversation_id = await abrir_conversa(client, repository)
        response = await perguntar(client, conversation_id)

    assert response.status_code == 429
    assert response.json() == {"code": "limite_de_uso", "message": CHAT_QUOTA_MESSAGE}


async def test_repetir_a_pergunta_que_falhou_nao_a_grava_duas_vezes(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    chat_client: FakeChatClient,
) -> None:
    """Repetir depois da falha retoma o turno em vez de duplicar a pergunta.

    O caminho é o do botão "Tentar de novo" da interface, e o erro é o mais
    provável na demonstração (o `429`). A pergunta já foi persistida antes da
    chamada ao provedor (FR-9): gravá-la outra vez deixaria duas linhas
    idênticas no histórico e as duas entrariam na janela do turno seguinte.
    """
    conversations.chunks = FUNDAMENTADOS
    quebrado = FakeChatClient(stream_error=ChatQuotaError(CHAT_QUOTA_MESSAGE))

    async with build_client(chat=quebrado) as client:
        conversation_id = await abrir_conversa(client, repository)
        falha = await perguntar(client, conversation_id)
    assert falha.status_code == 429

    # Mesma conversa, provedor de volta ao ar: é a repetição do mesmo turno.
    async with build_client() as client:
        response = await perguntar(client, conversation_id)

    assert response.status_code == 200
    assert conversations.contents_of(UUID(conversation_id)) == [
        (MessageRole.USER.value, PERGUNTA),
        (MessageRole.ASSISTANT.value, "".join(chat_client.pieces)),
    ]


async def test_repetir_pergunta_diferente_depois_da_falha_grava_as_duas(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
) -> None:
    """Pergunta nova depois de uma falha continua sendo pergunta nova.

    O contrapeso do teste acima: o que dispensa a gravação é a repetição exata
    do turno interrompido, não o fato de a última linha ser do usuário.
    """
    conversations.chunks = FUNDAMENTADOS
    quebrado = FakeChatClient(stream_error=ChatQuotaError(CHAT_QUOTA_MESSAGE))

    async with build_client(chat=quebrado) as client:
        conversation_id = await abrir_conversa(client, repository)
        await perguntar(client, conversation_id)

    async with build_client() as client:
        response = await perguntar(client, conversation_id, question=CONTINUACAO)

    assert response.status_code == 200
    gravadas = conversations.contents_of(UUID(conversation_id))
    assert [conteudo for _, conteudo in gravadas][:2] == [PERGUNTA, CONTINUACAO]


# ─── Desconexão do cliente ───────────────────────────────────────────────────


async def test_desconexao_encerra_o_gerador_e_grava_a_resposta_parcial(
    conversations: FakeConversationRepository,
    embedder: FakeEmbeddingClient,
    settings: Settings,
    captured_logs: list[dict[str, Any]],
) -> None:
    """AC-13: o laço para no primeiro sinal de desconexão e não consome mais nada.

    Chamado sem servidor de propósito: o `is_disconnected` da requisição real é
    injetado no turno, e é ele que este teste substitui por um interruptor —
    sob `ASGITransport` não existe socket para derrubar.
    """
    conversations.chunks = FUNDAMENTADOS
    conversation_id = await conversations.create_conversation(uuid4(), None)
    conversa = conversations.conversations[conversation_id]
    cliente = FakeChatClient(pieces=("um ", "dois ", "tres ", "quatro"))

    desconectado = False

    async def is_disconnected() -> bool:
        return desconectado

    eventos_recebidos = []
    async for evento in stream_turn(
        conversa,
        PERGUNTA,
        repository=conversations,
        embedder=embedder,
        chat_client=cliente,
        settings=settings,
        is_disconnected=is_disconnected,
    ):
        eventos_recebidos.append(evento)
        if evento.name == "token":
            desconectado = True

    assert [evento.name for evento in eventos_recebidos] == ["token", "citations", "done"]
    # O pedaço que já estava em voo quando a desconexão foi notada ainda chega —
    # a checagem acontece depois de o `async for` puxar o próximo item, e não há
    # como saber antes de pedir. O que AC-13 exige é que o consumo **pare** ali:
    # os dois últimos pedaços nunca são pedidos ao provedor.
    assert cliente.emitted == ["um ", "dois "], "o consumo do provedor não parou"

    # O fechamento é síncrono com a saída do laço: `app.chat` chama `aclose()`
    # no `finally`, e não deixa para o finalizador de async generators do event
    # loop. Sem isso a conexão com o provedor ficaria aberta por mais algumas
    # voltas depois de o usuário já ter ido embora — que é o custo que FR-12
    # existe para cortar.
    assert cliente.closed, "o iterador do provedor não foi fechado ao sair do laço"

    gravada = conversations.messages[conversation_id][-1]
    assert gravada.role is MessageRole.ASSISTANT
    assert gravada.content == "um "
    assert gravada.truncated is True

    desconexoes = [item for item in captured_logs if item["event"] == "chat.client_disconnected"]
    assert len(desconexoes) == 1
    assert desconexoes[0]["conversation_id"] == str(conversation_id)
    assert desconexoes[0]["tokens_emitted"] == 1


# ─── Logging do turno (§4.6) ─────────────────────────────────────────────────


async def test_eventos_do_turno_trazem_conversation_id_e_o_mesmo_request_id(
    build_client: Callable[..., httpx.AsyncClient],
    repository: FakeRepository,
    conversations: FakeConversationRepository,
    captured_logs: list[dict[str, Any]],
) -> None:
    """AC-15: condensação, retrieval, geração e conclusão num único `grep`."""
    conversations.chunks = FUNDAMENTADOS
    async with build_client() as client:
        conversation_id = await abrir_conversa(client, repository)
        await perguntar(client, conversation_id)
        await perguntar(
            client, conversation_id, CONTINUACAO, headers={"X-Request-Id": "req-do-turno"}
        )

    do_turno = [
        item
        for item in captured_logs
        if item["event"].startswith("chat.") and item.get("request_id") == "req-do-turno"
    ]
    assert [item["event"] for item in do_turno] == [
        "chat.turn_started",
        "chat.condensed",
        "chat.retrieved",
        "chat.generated",
    ]
    assert {item["conversation_id"] for item in do_turno} == {conversation_id}
    retrieval = next(item for item in do_turno if item["event"] == "chat.retrieved")
    assert retrieval["candidates"] == len(FUNDAMENTADOS)
    assert retrieval["above_threshold"] == len(FUNDAMENTADOS)
    assert retrieval["top_score"] == 0.91
    geracao = next(item for item in do_turno if item["event"] == "chat.generated")
    assert geracao["truncated"] is False
    assert geracao["token_count"] == 3
    assert all(isinstance(item["duration_ms"], int) for item in do_turno[1:])
