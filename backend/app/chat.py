"""Orquestração de um turno de chat: da pergunta ao último evento emitido.

É a máquina de estados do turno, como `app.ingestion` é a do documento. A regra
que organiza o módulo: **nada é emitido antes de a decisão de fundamentar estar
tomada**. Enquanto nenhum evento saiu, uma falha ainda pode virar resposta HTTP
com o envelope `{code, message}`; depois do primeiro evento, o status já foi
enviado e o erro só cabe dentro do próprio stream (FR-11).

Este módulo não conhece `fastapi`: ele produz `ChatEvent`, e quem traduz para o
frame SSE é `app.api.conversations`. A separação é o que permite testar recusa,
timeout de condensação, erro mid-stream e desconexão sem levantar servidor.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.adapters.gemini import ChatClient, EmbeddingClient
from app.adapters.repository import ConversationRecord, ConversationRepository
from app.config import Settings
from app.core.condensation import build_condensation_prompt, fallback_query, should_condense
from app.core.models import Citation, Message, MessageRole, RetrievedChunk
from app.core.prompt import REFUSAL_MESSAGE, build_answer_prompt, select_history_window
from app.core.retrieval import build_snippet, filter_by_threshold, has_grounding, take_top_k
from app.errors import AppError
from app.logging_setup import get_logger

logger = get_logger(__name__)

TOKEN_EVENT = "token"
CITATIONS_EVENT = "citations"
ERROR_EVENT = "error"
DONE_EVENT = "done"

@dataclass(frozen=True, slots=True)
class ChatEvent:
    """Um evento do protocolo de §4.3, antes de virar frame SSE.

    Nome e payload viajam separados porque é assim que o SSE os transporta
    (`event:` e `data:`), e porque manter o payload como dado — e não como
    string já serializada — deixa o teste asserir sobre campos.
    """

    name: str
    data: dict[str, Any]


IsDisconnected = Callable[[], Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class TurnContext:
    """O que a fase pré-stream apurou: a janela de histórico e o que fundamenta.

    As duas coisas viajam juntas porque são apuradas juntas e consumidas juntas
    na montagem do prompt — separá-las obrigaria a reler o histórico do banco
    depois de a pergunta já ter sido gravada, só para descartar a última linha.
    """

    history: list[Message]
    chunks: list[RetrievedChunk]
    top_score: float | None


async def stream_turn(
    conversation: ConversationRecord,
    question: str,
    *,
    repository: ConversationRepository,
    embedder: EmbeddingClient,
    chat_client: ChatClient,
    settings: Settings,
    is_disconnected: IsDisconnected,
) -> AsyncIterator[ChatEvent]:
    """Executa o turno inteiro, emitindo os eventos na ordem do protocolo.

    A ordem das etapas não é arbitrária. A pergunta é persistida **antes** de
    qualquer chamada ao provedor (FR-9), para que o histórico continue coerente
    mesmo se o processo morrer no meio. O histórico é lido **antes** disso, para
    que a pergunta atual não entre na própria janela de contexto.

    Tudo que pode falhar antes do primeiro token acontece antes do primeiro
    `yield`: quem consome este gerador puxa o primeiro evento **antes** de abrir
    a resposta, e é essa disciplina que faz um `429` do provedor — que chega
    justamente na primeira chamada — sair como HTTP `429` e não como um stream
    que abre para morrer no primeiro byte.
    """
    started = time.perf_counter()
    conversation_id = str(conversation.id)
    logger.info("chat.turn_started", conversation_id=conversation_id, question_len=len(question))

    context = await _prepare(
        conversation,
        question,
        repository=repository,
        embedder=embedder,
        chat_client=chat_client,
        settings=settings,
    )

    if not has_grounding(context.chunks):
        logger.info("chat.refused", conversation_id=conversation_id, top_score=context.top_score)
        async for event in _refuse(conversation.id, repository):
            yield event
        return

    async for event in _answer(
        conversation,
        question,
        context,
        repository=repository,
        chat_client=chat_client,
        settings=settings,
        is_disconnected=is_disconnected,
        started=started,
    ):
        yield event


async def _prepare(
    conversation: ConversationRecord,
    question: str,
    *,
    repository: ConversationRepository,
    embedder: EmbeddingClient,
    chat_client: ChatClient,
    settings: Settings,
) -> TurnContext:
    """Faz tudo que antecede o primeiro evento e devolve o contexto do turno.

    Erro aqui sobe como `AppError` e vira resposta HTTP normal — é a metade
    `pre_stream` de FR-11. O `chat.error` é emitido neste ponto, e não só na
    rota, porque é aqui que a fase é conhecida.
    """
    try:
        history = select_history_window(
            await repository.list_messages(conversation.id), settings.history_window
        )
        await repository.add_message(conversation.id, MessageRole.USER, question)

        query = await _condense(conversation.id, history, question, chat_client, settings)

        started = time.perf_counter()
        embedding = await asyncio.to_thread(embedder.embed_query, query)
        candidates = await repository.search_chunks(
            conversation.document_id, embedding, settings.retrieval_top_k
        )
        above = take_top_k(
            filter_by_threshold(candidates, settings.similarity_threshold),
            settings.retrieval_top_k,
        )
        top_score = _top_score(candidates)
        logger.info(
            "chat.retrieved",
            conversation_id=str(conversation.id),
            candidates=len(candidates),
            above_threshold=len(above),
            top_score=top_score,
            duration_ms=_elapsed_ms(started),
        )
    except AppError as error:
        logger.error(
            "chat.error",
            conversation_id=str(conversation.id),
            code=error.code,
            phase="pre_stream",
        )
        raise
    return TurnContext(history=history, chunks=above, top_score=top_score)


async def _condense(
    conversation_id: UUID,
    history: list[Message],
    question: str,
    chat_client: ChatClient,
    settings: Settings,
) -> str:
    """Devolve a query autocontida que vai ao retrieval.

    A falha da condensação **não** é erro do turno: o fallback devolve uma query
    utilizável sem custo e sem latência, e transformar isso em erro visível
    gastaria a boa vontade do usuário com um detalhe que ele não pode resolver
    (FR-4). Só a exceção do provedor é engolida aqui; nada mais.
    """
    if not should_condense(history, question):
        return question

    started = time.perf_counter()
    used_llm = True
    fallback = False
    try:
        query = await chat_client.generate(
            build_condensation_prompt(history, question),
            timeout=settings.condense_timeout_seconds,
        )
        if not query:
            fallback = True
    except (AppError, TimeoutError):
        fallback = True
    if fallback:
        used_llm = False
        query = fallback_query(history, question)

    logger.info(
        "chat.condensed",
        conversation_id=str(conversation_id),
        used_llm=used_llm,
        fallback=fallback,
        duration_ms=_elapsed_ms(started),
    )
    return query


async def _refuse(
    conversation_id: UUID, repository: ConversationRepository
) -> AsyncIterator[ChatEvent]:
    """Emite a recusa padrão como resposta legítima, sem chamar o provedor.

    A recusa é persistida como qualquer outra resposta do assistente: ela é o
    que aquele turno respondeu, e some do histórico se não for gravada. As
    citações vêm vazias — é a ausência delas que a interface usa para distinguir
    recusa de resposta fundamentada.
    """
    yield ChatEvent(TOKEN_EVENT, {"text": REFUSAL_MESSAGE})
    stored = await repository.add_message(conversation_id, MessageRole.ASSISTANT, REFUSAL_MESSAGE)
    yield ChatEvent(CITATIONS_EVENT, {"citations": []})
    yield ChatEvent(DONE_EVENT, {"message_id": stored.id, "truncated": False})


async def _answer(
    conversation: ConversationRecord,
    question: str,
    context: TurnContext,
    *,
    repository: ConversationRepository,
    chat_client: ChatClient,
    settings: Settings,
    is_disconnected: IsDisconnected,
    started: float,
) -> AsyncIterator[ChatEvent]:
    """Streama a resposta, persiste o que saiu e fecha com citações e `done`.

    `truncated` começa **verdadeiro** e só é desligado quando o laço chega ao
    fim por conta própria. É o oposto do reflexo natural, e é o que torna a
    honestidade da persistência independente do caminho de saída: desconexão do
    cliente, erro do provedor e cancelamento da task saem todos pelo `finally`
    com a marca correta, sem que cada um precise lembrar de marcá-la (FR-9).
    """
    prompt = build_answer_prompt(context.chunks, context.history, question)
    citations = _to_citations(context.chunks)

    parts: list[str] = []
    truncated = True
    failure: AppError | None = None
    stored: Message | None = None
    try:
        try:
            async for piece in chat_client.stream_answer(prompt):
                if await is_disconnected():
                    logger.warning(
                        "chat.client_disconnected",
                        conversation_id=str(conversation.id),
                        tokens_emitted=len(parts),
                    )
                    break
                parts.append(piece)
                yield ChatEvent(TOKEN_EVENT, {"text": piece})
            else:
                truncated = False
        except AppError as error:
            failure = error
    finally:
        stored = await _persist_answer(
            conversation.id, repository, "".join(parts), citations, truncated
        )

    logger.info(
        "chat.generated",
        conversation_id=str(conversation.id),
        token_count=len(parts),
        truncated=truncated,
        duration_ms=_elapsed_ms(started),
    )

    if failure is not None:
        logger.error(
            "chat.error",
            conversation_id=str(conversation.id),
            code=failure.code,
            phase="mid_stream",
        )
        yield ChatEvent(ERROR_EVENT, {"code": failure.code, "message": failure.message})
        return

    yield ChatEvent(CITATIONS_EVENT, {"citations": [_citation_payload(item) for item in citations]})
    # `message_id` nulo quando a gravação falhou: é a única informação honesta a
    # dar ao cliente nesse caso, e inventar um id faria a UI prender a mensagem
    # a uma linha que não existe.
    yield ChatEvent(
        DONE_EVENT,
        {"message_id": stored.id if stored is not None else None, "truncated": truncated},
    )


async def _persist_answer(
    conversation_id: UUID,
    repository: ConversationRepository,
    content: str,
    citations: tuple[Citation, ...],
    truncated: bool,
) -> Message | None:
    """Grava a resposta, mesmo parcial, sem deixar a falha de gravar derrubar o turno.

    Roda no `finally` do streaming, inclusive quando o gerador está sendo
    fechado pela desconexão do cliente. Se o banco não responder neste momento,
    o usuário já viu o texto na tela — perder o registro é ruim, mas propagar a
    exceção daqui apagaria o evento de erro que ele precisa ver.

    Turno que não produziu texto nenhum — o `429` que estoura na abertura do
    stream é o caso comum — **não** vira mensagem: uma linha de assistente
    vazia apareceria como balão em branco na tela e entraria na janela de
    histórico do próximo turno como se fosse resposta. O que aconteceu fica no
    log, que é onde esse fato serve para alguma coisa.
    """
    if not content:
        logger.info("chat.answer_empty", conversation_id=str(conversation_id))
        return None
    try:
        return await repository.add_message(
            conversation_id, MessageRole.ASSISTANT, content, citations, truncated
        )
    except Exception:
        logger.exception("chat.answer_not_persisted", conversation_id=str(conversation_id))
        return None


def _to_citations(chunks: list[RetrievedChunk]) -> tuple[Citation, ...]:
    """Converte os chunks usados nas citações que viajam no payload.

    O recorte do trecho acontece aqui, no servidor, uma única vez: é o que a
    interface exibe sem recortar de novo, e é o que fica gravado no histórico.
    """
    return tuple(
        Citation(
            page_number=chunk.page_number,
            snippet=build_snippet(chunk.content),
            chunk_index=chunk.chunk_index,
            score=chunk.score,
        )
        for chunk in chunks
    )


def _citation_payload(citation: Citation) -> dict[str, Any]:
    return {
        "page_number": citation.page_number,
        "snippet": citation.snippet,
        "chunk_index": citation.chunk_index,
        "score": citation.score,
    }


def _top_score(chunks: list[RetrievedChunk]) -> float | None:
    return max((chunk.score for chunk in chunks), default=None)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
