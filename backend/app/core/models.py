"""Tipos de domínio compartilhados pelos pipelines de ingestão e de chat.

Vivem em `core/` porque são dados puros: nenhum deles conhece HTTP, banco ou
provedor de IA. Estão todos declarados aqui, e não espalhados pelas fases que
os introduzem, para que extração, chunking, retrieval, prompting e persistência
falem exatamente o mesmo vocabulário.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DocumentStatus(StrEnum):
    """Estados pelos quais um documento passa durante a ingestão.

    A ordem é `pending → processing → ready`, com `failed` alcançável de
    qualquer ponto. Nenhum caminho pode deixar o documento parado em
    `processing`: é o que garante que a tela nunca mostre barra eterna.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PageText:
    """Texto extraído de uma única página, com o número de página base 1.

    O número vem da posição real no PDF e é propagado sem transformação até a
    citação — é ele que o avaliador confere à mão contra o documento.
    """

    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class Chunk:
    """Trecho indexável de uma página.

    `chunk_index` é sequencial no documento inteiro; `page_number` é o da
    página de origem. Um chunk nunca contém texto de duas páginas, e é isso
    que torna a citação exata por construção em vez de heurística.
    """

    chunk_index: int
    page_number: int
    content: str


class MessageRole(StrEnum):
    """Quem falou numa mensagem da conversa.

    Existe como enum, e não como `str` solto, pelo mesmo motivo de
    `DocumentStatus`: `role` é uma coluna `text` no banco e um campo de JSON na
    API, então nada além de disciplina impediria um `"assistent"` de entrar e
    sair sem nenhuma reclamação — quebrando a janela de histórico, que
    seleciona a última pergunta *do usuário*, muito longe de onde o erro nasceu.
    Sendo `StrEnum`, o valor continua serializando como a string crua, e o
    banco não precisa saber que existe um enum do lado de cá.
    """

    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class Citation:
    """Referência ao trecho do documento que sustenta uma resposta.

    É o campo próprio do payload que a constitution exige: a citação é dado
    estruturado, não texto embutido na resposta gerada — só assim a UI consegue
    exibir página e trecho como elemento próprio, e só assim o avaliador
    confere a página à mão contra o PDF.

    `snippet` já vem recortado para exibição (≤ 240 caracteres, em fronteira de
    palavra); `score` é a similaridade de cosseno em `[0,1]` do chunk que a
    originou, guardada porque é ela que explica por que aquele trecho entrou.
    """

    page_number: int
    snippet: str
    chunk_index: int
    score: float


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """Chunk recuperado pela busca vetorial, já com a similaridade calculada.

    É distinto de `Chunk` porque carrega `score`, que não é propriedade do
    trecho e sim da pergunta que o recuperou: o mesmo chunk tem score diferente
    a cada turno. Misturar os dois faria o tipo mentir sobre o que é fato do
    documento e o que é fato daquela busca.

    O `content` vem inteiro, e não recortado: o prompt precisa do texto todo, e
    o recorte só acontece ao montar a `Citation` para exibição.
    """

    chunk_index: int
    page_number: int
    content: str
    score: float


@dataclass(frozen=True, slots=True)
class Message:
    """Uma mensagem persistida da conversa, como a API a publica.

    `citations` é `tuple` e não `list` porque `frozen=True` só congela a
    referência: com uma lista, `message.citations.append(...)` continuaria
    funcionando e a imutabilidade seria decorativa. A tupla também mantém a
    dataclass hasheável, o que uma lista impediria.

    `truncated` é campo de primeira classe, e não algo inferido do texto,
    porque uma resposta parcial precisa ser gravada sem se passar por completa
    (FR-9): o stream pode morrer no meio, e o histórico tem de dizer isso.

    `id` é `int` para casar com `messages(id bigserial)` — é o mesmo valor que o
    evento SSE `done` devolve ao cliente.
    """

    id: int
    role: MessageRole
    content: str
    citations: tuple[Citation, ...]
    truncated: bool
    created_at: datetime
