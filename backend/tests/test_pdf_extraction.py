"""Extração de texto de PDF e as validações que só o parse consegue fazer."""

import pytest

from app.adapters.pdf import extract_pages
from app.errors import (
    InvalidFileError,
    PdfPageLimitError,
    PdfTextLimitError,
    PdfWithoutTextError,
)
from tests.factories import build_pdf, build_pdf_without_text_layer, build_text_pdf

LIMITS = {"max_pages": 20, "max_chars": 60000}


def test_o_gerador_de_pdf_devolve_exatamente_o_texto_escrito() -> None:
    data = build_pdf([["Primeira linha da pagina.", "Segunda linha da pagina."]])

    pages = extract_pages(data, **LIMITS)

    assert pages[0].text == "Primeira linha da pagina.\nSegunda linha da pagina."


def test_cada_pagina_vira_um_pagetext_numerado_a_partir_de_um() -> None:
    data = build_text_pdf(["Texto da pagina um.", "Texto da pagina dois.", "Texto da tres."])

    pages = extract_pages(data, **LIMITS)

    assert [page.page_number for page in pages] == [1, 2, 3]
    assert pages[1].text == "Texto da pagina dois."


def test_paginas_acima_do_limite_levantam_erro_de_paginas() -> None:
    data = build_text_pdf([f"Pagina numero {numero}." for numero in range(1, 6)])

    with pytest.raises(PdfPageLimitError) as erro:
        extract_pages(data, max_pages=4, max_chars=60000)

    assert "5" in str(erro.value)
    assert "4" in str(erro.value)


def test_pagina_no_limite_exato_de_paginas_e_aceita() -> None:
    data = build_text_pdf(["Uma.", "Duas.", "Tres."])

    assert len(extract_pages(data, max_pages=3, max_chars=60000)) == 3


def test_texto_acima_do_limite_de_caracteres_levanta_erro_de_texto() -> None:
    data = build_text_pdf(["a" * 200, "b" * 200])

    with pytest.raises(PdfTextLimitError) as erro:
        extract_pages(data, max_pages=20, max_chars=300)

    assert "300" in str(erro.value)


def test_pdf_sem_camada_de_texto_avisa_que_ocr_nao_e_suportado() -> None:
    data = build_pdf_without_text_layer(page_count=2)

    with pytest.raises(PdfWithoutTextError) as erro:
        extract_pages(data, **LIMITS)

    mensagem = str(erro.value).lower()
    assert "sem texto extraível" in mensagem
    assert "ocr" in mensagem


def test_arquivo_que_nao_e_pdf_levanta_erro_de_arquivo_invalido() -> None:
    with pytest.raises(InvalidFileError):
        extract_pages(b"isto nao e um pdf", **LIMITS)


def test_extracao_e_deterministica_entre_execucoes() -> None:
    data = build_text_pdf(["Conteudo estavel.", "Outro conteudo estavel."])

    assert extract_pages(data, **LIMITS) == extract_pages(data, **LIMITS)


def test_as_tres_violacoes_de_parse_tem_codigos_distintos() -> None:
    codigos = {PdfPageLimitError.code, PdfTextLimitError.code, PdfWithoutTextError.code}

    assert len(codigos) == 3
