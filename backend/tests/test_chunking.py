"""Quebra em chunks: página correta, corte em fronteira e overlap."""

import pytest

from app.core.chunking import chunk_pages, normalize_whitespace
from app.core.models import Chunk, PageText

SIZE = 500
OVERLAP = 100


def _long_text(sentences: int, marker: str) -> str:
    """Texto longo e determinístico, com um marcador que identifica a página."""
    frases = (f"Sentenca {marker}{numero} do documento de teste." for numero in range(sentences))
    return " ".join(frases)


def _shared_length(first: str, second: str) -> int:
    """Maior sufixo de `first` que é prefixo de `second`."""
    for length in range(min(len(first), len(second)), 0, -1):
        if first.endswith(second[:length]):
            return length
    return 0


def test_cada_chunk_carrega_o_numero_da_pagina_de_origem() -> None:
    pages = [PageText(1, _long_text(30, "A")), PageText(2, _long_text(30, "B"))]

    chunks = chunk_pages(pages, SIZE, OVERLAP)

    for chunk in chunks:
        marker = "A" if chunk.page_number == 1 else "B"
        assert f"Sentenca {marker}" in chunk.content


def test_nenhum_chunk_contem_texto_de_duas_paginas() -> None:
    pages = [PageText(1, _long_text(30, "A")), PageText(2, _long_text(30, "B"))]

    chunks = chunk_pages(pages, SIZE, OVERLAP)

    assert len(chunks) > 2
    for chunk in chunks:
        assert not ("Sentenca A" in chunk.content and "Sentenca B" in chunk.content)


def test_paginas_sao_processadas_na_ordem_e_o_indice_e_sequencial() -> None:
    pages = [PageText(1, _long_text(30, "A")), PageText(2, _long_text(30, "B"))]

    chunks = chunk_pages(pages, SIZE, OVERLAP)

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert [chunk.page_number for chunk in chunks] == sorted(
        chunk.page_number for chunk in chunks
    )


def test_duas_execucoes_produzem_resultado_identico() -> None:
    pages = [PageText(1, _long_text(40, "A")), PageText(2, _long_text(25, "B"))]

    assert chunk_pages(pages, SIZE, OVERLAP) == chunk_pages(pages, SIZE, OVERLAP)


def test_nenhum_chunk_comeca_ou_termina_no_meio_de_palavra() -> None:
    page = PageText(1, _long_text(40, "A"))

    chunks = chunk_pages([page], SIZE, OVERLAP)

    texto = normalize_whitespace(page.text)
    for chunk in chunks:
        inicio = texto.find(chunk.content)
        fim = inicio + len(chunk.content)
        assert inicio != -1
        assert inicio == 0 or texto[inicio - 1].isspace()
        assert fim == len(texto) or texto[fim].isspace()


def test_chunks_consecutivos_da_mesma_pagina_compartilham_o_overlap_minimo() -> None:
    chunks = chunk_pages([PageText(1, _long_text(40, "A"))], SIZE, OVERLAP)

    assert len(chunks) > 1
    for anterior, seguinte in zip(chunks, chunks[1:], strict=False):
        assert _shared_length(anterior.content, seguinte.content) >= OVERLAP // 2


def test_pagina_menor_que_a_janela_vira_um_unico_chunk() -> None:
    page = PageText(7, "Uma pagina curta, bem menor que a janela de corte.")

    chunks = chunk_pages([page], SIZE, OVERLAP)

    assert chunks == [Chunk(chunk_index=0, page_number=7, content=page.text)]


def test_pagina_sem_texto_nao_gera_chunk() -> None:
    pages = [PageText(1, "   \n\n  "), PageText(2, "Pagina com conteudo.")]

    chunks = chunk_pages(pages, SIZE, OVERLAP)

    assert [chunk.page_number for chunk in chunks] == [2]
    assert chunks[0].chunk_index == 0


def test_o_corte_prefere_a_fronteira_de_paragrafo() -> None:
    primeiro = "P" * 60 + "."
    texto = f"{primeiro}\n\n" + "S" * 60 + "."

    chunks = chunk_pages([PageText(1, texto)], 100, 10)

    assert chunks[0].content == primeiro


def test_o_corte_cai_no_fim_de_sentenca_quando_nao_ha_paragrafo() -> None:
    texto = "a" * 55 + ". " + "b" * 60

    chunks = chunk_pages([PageText(1, texto)], 100, 10)

    assert chunks[0].content == "a" * 55 + "."


def test_o_corte_cai_no_espaco_quando_nao_ha_sentenca_nem_paragrafo() -> None:
    texto = " ".join(f"palavra{numero}" for numero in range(20))

    chunks = chunk_pages([PageText(1, texto)], 100, 10)

    assert chunks[0].content.endswith("palavra10")
    assert len(chunks[0].content) <= 100


def test_palavra_maior_que_a_janela_e_cortada_no_limite_duro() -> None:
    """Sem separador não há fronteira a respeitar; o corte não pode travar."""
    chunks = chunk_pages([PageText(1, "x" * 250)], 100, 10)

    assert [len(chunk.content) for chunk in chunks] == [100, 100, 50]


def test_normalizacao_colapsa_quebra_espuria_e_preserva_paragrafo() -> None:
    texto = "Uma frase\nquebrada  no meio.\r\n\r\n  Outro   paragrafo.\n"

    assert normalize_whitespace(texto) == "Uma frase quebrada no meio.\n\nOutro paragrafo."


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (100, 100), (100, -1)])
def test_parametros_incoerentes_de_janela_sao_recusados(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_pages([PageText(1, "Texto.")], size, overlap)
