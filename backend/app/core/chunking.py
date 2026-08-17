"""Quebra do texto extraído em chunks citáveis.

Vive em `core/` porque é lógica pura: recebe texto e devolve texto, sem tocar
em PDF, banco ou provedor de IA. Não há splitter de terceiros aqui — a regra
que interessa (não cruzar página) é justamente a que nenhum splitter genérico
garante, porque eles enxergam o documento como uma string única.
"""

import re

from app.core.models import Chunk, PageText

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n\s*")
_WHITESPACE_RUN = re.compile(r"\s+")
_SENTENCE_ENDINGS = (". ", "! ", "? ")
_GAP = re.compile(r"\s+")

PARAGRAPH_SEPARATOR = "\n\n"


def normalize_whitespace(text: str) -> str:
    """Colapsa espaços em branco excessivos preservando a fronteira de parágrafo.

    Extração de PDF produz quebras de linha espúrias no meio de frases, porque
    o texto é reconstruído a partir da posição dos glifos. Se essas quebras
    sobrevivessem, elas estragariam duas coisas: o corte por parágrafo, que
    passaria a acertar meio de frase, e o trecho que vai para o chip de
    citação, que apareceria picotado na tela.

    Uma quebra isolada vira espaço (era espúria); duas ou mais viram
    exatamente uma fronteira de parágrafo (`\\n\\n`), que é um limite de corte
    legítimo e por isso é mantida.
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = _PARAGRAPH_BREAK.split(unified)
    paragraphs = (_WHITESPACE_RUN.sub(" ", part).strip() for part in parts)
    return PARAGRAPH_SEPARATOR.join(part for part in paragraphs if part)


def chunk_pages(pages: list[PageText], size: int, overlap: int) -> list[Chunk]:
    """Quebra cada página em chunks de até `size` caracteres, com `overlap`.

    A janela **reseta a cada página**: nenhum chunk mistura texto de duas
    páginas. É essa regra que torna a citação exata por construção — o
    `page_number` do chunk é o da página de onde cada caractere saiu, sem
    heurística de "de qual página este trecho provavelmente veio". Um único
    chunk que cruzasse a fronteira já bastaria para o avaliador ver uma
    citação apontando para a página errada.

    `chunk_index` é sequencial no documento inteiro para servir de ordem
    estável na persistência; `page_number` é o da página iterada. Páginas sem
    texto após a normalização não geram chunk algum.
    """
    if size <= 0:
        raise ValueError("O tamanho do chunk precisa ser positivo.")
    if not 0 <= overlap < size:
        raise ValueError("O overlap precisa ser menor que o tamanho do chunk.")

    chunks: list[Chunk] = []
    for page in pages:
        for content in _split_text(normalize_whitespace(page.text), size, overlap):
            chunks.append(
                Chunk(chunk_index=len(chunks), page_number=page.page_number, content=content)
            )
    return chunks


def _split_text(text: str, size: int, overlap: int) -> list[str]:
    """Aplica a janela deslizante dentro de uma única página."""
    pieces: list[str] = []
    start = 0
    while start < len(text):
        if len(text) - start <= size:
            pieces.append(text[start:].strip())
            break
        end = _cut_point(text, start, size)
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        start = _next_start(text, start, end, overlap)
    return [piece for piece in pieces if piece]


def _cut_point(text: str, start: int, size: int) -> int:
    """Escolhe onde cortar a janela `text[start:start + size]`.

    A preferência é parágrafo, depois fim de sentença, depois espaço — da
    fronteira semântica mais forte para a mais fraca. Só se a janela inteira
    for uma palavra sem separador o corte cai no limite duro, porque aí não
    existe fronteira alguma para respeitar.

    O corte é procurado apenas na segunda metade da janela: aceitar o primeiro
    parágrafo disponível produziria chunks minúsculos e um número de chunks que
    varia demais com a formatação do PDF.
    """
    window = text[start : start + size]
    floor = max(1, size // 2)

    paragraph = window.rfind(PARAGRAPH_SEPARATOR, floor)
    if paragraph != -1:
        return start + paragraph

    sentence = max(window.rfind(ending, floor) for ending in _SENTENCE_ENDINGS)
    if sentence != -1:
        return start + sentence + 2

    space = window.rfind(" ", floor)
    if space != -1:
        return start + space

    return start + size


def _next_start(text: str, start: int, end: int, overlap: int) -> int:
    """Recua `overlap` caracteres a partir do corte, sem partir palavra.

    O recuo é alinhado para trás, ao espaço anterior, e não para frente: assim
    o trecho compartilhado nunca fica menor que o `overlap` pedido, que é o
    que garante que uma frase partida entre dois chunks continue recuperável
    inteira por pelo menos um deles.
    """
    lower = start + 1
    target = max(end - overlap, lower)

    behind = list(_GAP.finditer(text, lower, target))
    if behind:
        return behind[-1].end()

    ahead = _GAP.search(text, target, end)
    if ahead is not None:
        return ahead.end()

    return end
