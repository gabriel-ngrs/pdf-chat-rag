"""Extração de texto de PDF, página a página.

É o único ponto do sistema que conhece `pypdf`. O resto do pipeline trabalha
sobre `PageText`, o que mantém o chunking puro e testável sem gerar PDF.
"""

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.models import PageText
from app.errors import (
    InvalidFileError,
    PdfPageLimitError,
    PdfTextLimitError,
    PdfWithoutTextError,
)

NO_TEXT_MESSAGE = (
    "PDF sem texto extraível; OCR não é suportado. "
    "Envie um PDF com camada de texto, não um documento escaneado."
)
UNREADABLE_MESSAGE = (
    "Não foi possível ler o PDF. O arquivo pode estar corrompido ou protegido por senha."
)


def extract_pages(data: bytes, *, max_pages: int, max_chars: int) -> list[PageText]:
    """Extrai o texto de cada página do PDF, preservando o número base 1.

    **Bloqueante e CPU-bound.** `pypdf` é síncrono e o parse de um PDF no teto
    desta spec leva tempo suficiente para travar o event loop. O chamador (a
    rotina de processamento assíncrono) precisa invocar esta função dentro de
    `asyncio.to_thread` — a decisão de sair da thread não é tomada aqui porque
    este módulo não deve conhecer o modelo de concorrência de quem o usa.

    Os limites chegam por parâmetro em vez de serem lidos de `Settings` aqui
    dentro: assim a função continua pura em relação ao ambiente, os testes
    exercitam os limites sem mexer em variável de ambiente, e a configuração
    permanece resolvida num lugar só, na borda da aplicação.

    Levanta `InvalidFileError` se o arquivo não for um PDF legível,
    `PdfPageLimitError` acima de `max_pages`, `PdfTextLimitError` acima de
    `max_chars` e `PdfWithoutTextError` quando não há um caractere sequer —
    exceções distintas porque cada uma pede uma ação diferente do usuário.
    """
    reader = _open(data)

    if len(reader.pages) > max_pages:
        raise PdfPageLimitError(
            f"O PDF tem {len(reader.pages)} páginas e o limite é {max_pages}. "
            "Envie um documento menor."
        )

    pages = _extract(reader)

    total = sum(len(page.text) for page in pages)
    if total > max_chars:
        raise PdfTextLimitError(
            f"O PDF tem {total} caracteres de texto e o limite é {max_chars}. "
            "Envie um documento menor."
        )
    # `strip()` e não `len(text)`: há gerador de PDF que emite operadores de texto
    # vazios, e documento vindo de imagem costuma trazer uma camada só de espaço.
    # Contando bytes, esses passariam pelo guarda e o chunking os reduziria a
    # zero chunks — o documento terminaria "pronto" e sem conteúdo, dando ao
    # usuário o diagnóstico errado no lugar do aviso de OCR.
    if not any(page.text.strip() for page in pages):
        raise PdfWithoutTextError(NO_TEXT_MESSAGE)

    return pages


def _open(data: bytes) -> PdfReader:
    """Abre os bytes como PDF, trocando o erro do `pypdf` por um de domínio.

    O erro da biblioteca vaza detalhe de implementação na resposta da API e
    não diz ao usuário o que fazer; a troca acontece aqui, na fronteira.
    """
    try:
        return PdfReader(io.BytesIO(data))
    except (PdfReadError, ValueError, OSError) as erro:
        raise InvalidFileError(UNREADABLE_MESSAGE) from erro


def _extract(reader: PdfReader) -> list[PageText]:
    """Percorre as páginas na ordem do documento, numerando a partir de 1.

    O `or ""` cobre a página que existe mas não tem camada de texto: ela entra
    vazia e é o total do documento, e não a página isolada, que decide se o
    PDF é escaneado.
    """
    try:
        return [
            PageText(page_number=number, text=page.extract_text() or "")
            for number, page in enumerate(reader.pages, start=1)
        ]
    except (PdfReadError, ValueError, OSError, KeyError) as erro:
        raise InvalidFileError(UNREADABLE_MESSAGE) from erro
