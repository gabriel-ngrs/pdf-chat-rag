"""Rotas de conversa: criação, envio de pergunta por SSE e leitura do histórico.

A responsabilidade aqui é estreita de propósito: validar a entrada, resolver as
dependências, traduzir `ChatEvent` em frame SSE e — o ponto que organiza o
módulo — **puxar o primeiro evento antes de abrir a resposta**.

Esse detalhe é o que faz FR-11 funcionar. Enquanto nenhum byte saiu, uma
`AppError` ainda pode virar `{code, message}` com o status certo; depois disso o
status já foi enviado e o erro só cabe como evento `error`. Como o `429` do
provedor chega majoritariamente na primeira chamada, a metade "antes" não é caso
de borda: é o caso comum.
"""

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.sse import EventSourceResponse, format_sse_event

from app.adapters.gemini import ChatClient
from app.adapters.repository import ConversationRepository
from app.api.documents import EmbedderDep, RepositoryDep, SettingsDep
from app.api.schemas import (
    CitationResponse,
    ConversationCreateRequest,
    ConversationResponse,
    MessageResponse,
    QuestionRequest,
)
from app.chat import ChatEvent, stream_turn
from app.core.models import DocumentStatus, Message
from app.errors import DocumentNotReadyError, InternalError, NotFoundError, error_body
from app.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter()

DOCUMENT_NOT_FOUND_MESSAGE = "Documento não encontrado."
CONVERSATION_NOT_FOUND_MESSAGE = "Conversa não encontrada."
NOT_READY_MESSAGE = "O documento ainda está sendo processado. Espere ele ficar pronto."
EMPTY_TURN_MESSAGE = "Não foi possível responder por uma falha interna. Tente perguntar de novo."

# `EventSourceResponse` cuida do `Content-Type`, mas os dois cabeçalhos abaixo
# ficam por conta de quem constrói a resposta quando ela é devolvida pela rota
# (em vez de produzida por um *path operation* gerador) — verificado no
# ambiente, em 0.141.1. Sem `X-Accel-Buffering: no`, um proxy que bufferize
# entrega a resposta inteira de uma vez e o streaming vira ilusão.
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def get_conversation_repository(request: Request) -> ConversationRepository:
    """Devolve o repositório de conversas montado no lifespan."""
    repository: ConversationRepository | None = getattr(request.app.state, "conversations", None)
    if repository is None:
        raise RuntimeError("O repositório de conversas não foi inicializado.")
    return repository


def get_chat_client(request: Request) -> ChatClient:
    """Devolve o cliente de chat montado no lifespan."""
    client: ChatClient | None = getattr(request.app.state, "chat_client", None)
    if client is None:
        raise RuntimeError("O cliente de chat não foi inicializado.")
    return client


ConversationsDep = Annotated[ConversationRepository, Depends(get_conversation_repository)]
ChatClientDep = Annotated[ChatClient, Depends(get_chat_client)]


@router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationResponse,
)
async def create_conversation(
    payload: ConversationCreateRequest,
    documents: RepositoryDep,
    conversations: ConversationsDep,
    session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> ConversationResponse:
    """Abre uma conversa sobre um documento já processado.

    A checagem de `ready` acontece aqui e não no repositório porque é uma regra
    de produto — perguntar sobre um documento sem chunks devolveria a recusa
    padrão em toda pergunta, o diagnóstico errado (FR-1).
    """
    record = await documents.get(payload.document_id)
    if record is None:
        raise NotFoundError(DOCUMENT_NOT_FOUND_MESSAGE)
    if record.status is not DocumentStatus.READY:
        raise DocumentNotReadyError(NOT_READY_MESSAGE)

    conversation_id = await conversations.create_conversation(payload.document_id, session_id)
    logger.info(
        "conversation.created",
        conversation_id=str(conversation_id),
        document_id=str(payload.document_id),
    )
    return ConversationResponse(id=conversation_id)


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    request: Request,
    conversation_id: UUID,
    payload: QuestionRequest,
    conversations: ConversationsDep,
    embedder: EmbedderDep,
    chat_client: ChatClientDep,
    settings: SettingsDep,
) -> EventSourceResponse:
    """Responde a pergunta em streaming, com citações ao final.

    O primeiro evento é puxado **antes** de a resposta ser construída: é o que
    permite ao handler global converter uma falha pré-stream no envelope HTTP,
    com o status certo, em vez de abrir um `text/event-stream` que morre no
    primeiro byte (FR-11).
    """
    conversation = await conversations.get_conversation(conversation_id)
    if conversation is None:
        raise NotFoundError(CONVERSATION_NOT_FOUND_MESSAGE)

    events = stream_turn(
        conversation,
        payload.question,
        repository=conversations,
        embedder=embedder,
        chat_client=chat_client,
        settings=settings,
        is_disconnected=request.is_disconnected,
    )
    first = await anext(events, None)
    if first is None:
        # O turno sempre emite ao menos um evento; chegar aqui significa que a
        # orquestração mudou sem que esta rota soubesse.
        raise InternalError(EMPTY_TURN_MESSAGE)

    return EventSourceResponse(_frames(first, events), headers=SSE_HEADERS)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: UUID, conversations: ConversationsDep
) -> list[MessageResponse]:
    """Devolve o histórico da conversa, com as citações presas às respostas.

    É esta rota que sustenta a restauração depois de um `F5`: o cliente guarda
    só os dois ids e recompõe a conversa a partir daqui.
    """
    conversation = await conversations.get_conversation(conversation_id)
    if conversation is None:
        raise NotFoundError(CONVERSATION_NOT_FOUND_MESSAGE)
    messages = await conversations.list_messages(conversation_id)
    return [_to_response(message) for message in messages]


async def _frames(first: ChatEvent, rest: AsyncIterator[ChatEvent]) -> AsyncIterator[bytes]:
    """Serializa os eventos do turno no formato de fio do SSE.

    A formatação vem de `format_sse_event`, do próprio FastAPI, e não de uma
    string montada à mão: o frame precisa casar exatamente com o parser do
    cliente, e reimplementá-lo seria assumir esse risco de graça.

    A rede de segurança do `except` cobre o que a orquestração não previu: uma
    exceção crua aqui derrubaria a conexão no meio, e o cliente veria um stream
    truncado sem nenhum motivo. Melhor um `error` com fechamento limpo.
    """
    yield _frame(first)
    try:
        async for event in rest:
            yield _frame(event)
    except Exception:
        logger.exception("chat.stream_failed")
        yield _frame(
            ChatEvent("error", error_body(InternalError.code, EMPTY_TURN_MESSAGE)),
        )


def _frame(event: ChatEvent) -> bytes:
    return format_sse_event(
        event=event.name, data_str=json.dumps(event.data, ensure_ascii=False)
    )


def _to_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=[
            CitationResponse(
                page_number=citation.page_number,
                snippet=citation.snippet,
                chunk_index=citation.chunk_index,
                score=citation.score,
            )
            for citation in message.citations
        ],
        truncated=message.truncated,
        created_at=message.created_at,
    )
