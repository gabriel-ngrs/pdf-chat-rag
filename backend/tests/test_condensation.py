"""Heurística de condensação, prompt de reescrita e fallback determinístico."""

from datetime import UTC, datetime

from app.core.condensation import (
    build_condensation_prompt,
    fallback_query,
    should_condense,
)
from app.core.models import Message, MessageRole

PERGUNTA_INICIAL = "quais serviços a YAITEC oferece?"


def _message(role: MessageRole, content: str, message_id: int = 1) -> Message:
    """Mensagem mínima: a condensação só olha `role` e `content`."""
    return Message(
        id=message_id,
        role=role,
        content=content,
        citations=(),
        truncated=False,
        created_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
    )


def _history(*contents: str) -> list[Message]:
    """Conversa alternando usuário e assistente, começando pelo usuário."""
    return [
        _message(MessageRole.USER if index % 2 == 0 else MessageRole.ASSISTANT, content, index + 1)
        for index, content in enumerate(contents)
    ]


def test_pergunta_com_marcador_anaforico_e_historico_e_condensada() -> None:
    assert should_condense(_history(PERGUNTA_INICIAL, "Consultoria e dados."), "e quanto a isso?")


def test_pergunta_autocontida_nao_e_condensada() -> None:
    history = _history(PERGUNTA_INICIAL, "Consultoria e dados.")

    assert not should_condense(history, "qual o endereço da empresa?")


def test_sem_historico_nunca_condensa() -> None:
    assert not should_condense([], "e quanto a isso?")


def test_pergunta_curta_demais_para_se_sustentar_e_condensada() -> None:
    history = _history(PERGUNTA_INICIAL, "Consultoria e dados.")

    assert should_condense(history, "e os preços?")


def test_marcador_e_reconhecido_sem_acento_e_em_qualquer_caixa() -> None:
    history = _history(PERGUNTA_INICIAL, "Consultoria e dados.")

    assert should_condense(history, "Por que a empresa mudou de sede em 2019 segundo o documento?")


def test_marcador_nao_dispara_dentro_de_outra_palavra() -> None:
    history = _history(PERGUNTA_INICIAL, "Consultoria e dados.")

    assert not should_condense(history, "qual o valor da canela usada na receita industrial?")


def test_prompt_de_condensacao_traz_a_ultima_pergunta_e_pede_so_a_reescrita() -> None:
    history = _history(PERGUNTA_INICIAL, "Consultoria, dados e automação.")

    prompt = build_condensation_prompt(history, "e quanto a isso?")

    assert PERGUNTA_INICIAL in prompt
    assert "e quanto a isso?" in prompt
    assert "apenas com a pergunta reescrita" in prompt
    assert prompt.index(PERGUNTA_INICIAL) < prompt.index("apenas com a pergunta reescrita")


def test_prompt_de_condensacao_e_deterministico() -> None:
    history = _history(PERGUNTA_INICIAL, "Consultoria e dados.")

    assert build_condensation_prompt(history, "e quanto a isso?") == build_condensation_prompt(
        history, "e quanto a isso?"
    )


def test_fallback_concatena_a_ultima_pergunta_do_usuario_com_a_atual() -> None:
    history = _history(PERGUNTA_INICIAL, "Consultoria, dados e automação.")

    assert fallback_query(history, "e quanto a isso?") == f"{PERGUNTA_INICIAL} e quanto a isso?"


def test_fallback_ignora_as_respostas_do_assistente() -> None:
    history = _history(PERGUNTA_INICIAL, "Consultoria e dados.", "quem são os fundadores?")

    query = fallback_query(history, "e ele?")

    assert query.startswith("quem são os fundadores?")
    assert "Consultoria e dados." not in query


def test_fallback_sem_pergunta_anterior_devolve_a_pergunta_atual() -> None:
    assert fallback_query([], "e quanto a isso?") == "e quanto a isso?"
