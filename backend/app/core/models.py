"""Tipos de domínio compartilhados pelo pipeline de ingestão.

Vivem em `core/` porque são dados puros: nenhum deles conhece HTTP, banco ou
provedor de IA. Estão todos declarados aqui, e não espalhados pelas fases que
os introduzem, para que extração, chunking e persistência falem exatamente o
mesmo vocabulário.
"""

from dataclasses import dataclass
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
