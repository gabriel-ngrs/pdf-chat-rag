"""Geradores de PDF mínimos, em memória, para os testes de extração.

Os PDFs são montados byte a byte em vez de virem de fixture binária: um
arquivo commitado esconderia o que está sendo testado e obrigaria a abrir um
visualizador para saber qual texto deveria sair da extração. Montar à mão
também evita dependência nova só para teste.

O PDF gerado é o mínimo que o `pypdf` aceita: catálogo, árvore de páginas, uma
fonte Type1 padrão e um content stream com `BT ... Tj ET` por linha. A
verificação empírica de que o texto sai igual ao que entrou está em
`test_pdf_extraction.py`.
"""

from collections.abc import Sequence

_MEDIA_BOX = "[0 0 612 792]"
_FIRST_PAGE_OBJECT = 3


def build_pdf(pages: Sequence[Sequence[str]]) -> bytes:
    """Monta um PDF com uma página por item, cada uma com as linhas dadas.

    Uma página com lista vazia de linhas sai sem camada de texto — é o caso do
    documento escaneado, que a extração precisa recusar.
    """
    objects = _build_objects(pages)
    return _serialize(objects)


def build_text_pdf(page_texts: Sequence[str]) -> bytes:
    """Atalho para PDFs cujo texto de página já vem como uma string com `\\n`."""
    return build_pdf([text.split("\n") for text in page_texts])


def build_pdf_without_text_layer(page_count: int = 1) -> bytes:
    """Monta um PDF com páginas de verdade e nenhum caractere extraível."""
    return build_pdf([[] for _ in range(page_count)])


def _build_objects(pages: Sequence[Sequence[str]]) -> list[tuple[int, bytes]]:
    """Numera os objetos do PDF: páginas e conteúdos intercalados, fonte no fim."""
    page_ids = [_FIRST_PAGE_OBJECT + 2 * index for index in range(len(pages))]
    font_id = _FIRST_PAGE_OBJECT + 2 * len(pages)
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)

    objects: list[tuple[int, bytes]] = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()),
    ]
    for page_id, lines in zip(page_ids, pages, strict=True):
        objects.append(
            (
                page_id,
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox {_MEDIA_BOX} "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                    f"/Contents {page_id + 1} 0 R >>"
                ).encode(),
            )
        )
        stream = _content_stream(lines)
        objects.append(
            (
                page_id + 1,
                b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
            )
        )
    objects.append((font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    return objects


def _content_stream(lines: Sequence[str]) -> bytes:
    """Escreve as linhas com `T*`, que é o que faz o `pypdf` emitir `\\n`."""
    if not lines:
        return b""
    operators = ["BT", "/F1 12 Tf", "14 TL", "1 0 0 1 72 720 Tm"]
    for position, line in enumerate(lines):
        if position:
            operators.append("T*")
        operators.append(f"({_escape(line)}) Tj")
    operators.append("ET")
    return "\n".join(operators).encode("ascii")


def _escape(line: str) -> str:
    """Escapa os caracteres que terminariam a string literal do PDF."""
    return line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _serialize(objects: list[tuple[int, bytes]]) -> bytes:
    """Escreve os objetos e a tabela xref com os offsets reais de cada um."""
    document = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number, body in sorted(objects):
        offsets[number] = len(document)
        document += b"%d 0 obj\n%s\nendobj\n" % (number, body)

    xref_offset = len(document)
    size = max(offsets) + 1
    document += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for number in range(1, size):
        document += b"%010d 00000 n \n" % offsets[number]
    document += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        size,
        xref_offset,
    )
    return bytes(document)
