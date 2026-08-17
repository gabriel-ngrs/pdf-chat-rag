"""Decisão e montagem do passo que antecede o retrieval.

Perguntas de continuação — "e quanto a isso?" — não recuperam nada num índice
vetorial: o pronome não carrega semântica, e a memória que existe no prompt não
existe na busca. Este módulo decide quando a pergunta precisa ser reescrita como
pergunta autocontida, monta o prompt dessa reescrita e define o que usar quando
a reescrita falha.

A chamada ao provedor **não acontece aqui** — este módulo só decide booleanos e
monta strings; quem chama é `app.chat`. É o que mantém a regra testável sem rede
e sem mock de HTTP.
"""

import re
import unicodedata

from app.core.models import Message, MessageRole
from app.core.prompt import render_history

# Marcadores de FR-3: palavras e expressões que só significam alguma coisa em
# relação ao que foi dito antes. Escritos sem acento porque a comparação roda
# sobre o texto normalizado — assim "por quê" e "por que" caem no mesmo caso,
# que é como as duas formas chegam de quem digita apressado.
ANAPHORIC_MARKERS = (
    "isso",
    "isto",
    "esse",
    "essa",
    "ele",
    "ela",
    "la",
    "e quanto a",
    "e sobre",
    "detalhe mais",
    "por que",
    "quais deles",
)

# Abaixo disto a pergunta é curta demais para carregar contexto próprio ("e os
# preços?", "e agora?"), mesmo sem nenhum marcador da lista.
#
# DESVIO DELIBERADO de FR-3, que escreve "< 12 palavras": com 12, o AC-3 fica
# impossível de cumprir, porque "qual o endereço da empresa?" tem cinco palavras
# e o AC exige que ela **não** seja condensada. Os dois não podem valer ao mesmo
# tempo, e o AC é o critério verificável. O número baixo também é o que preserva
# o motivo da heurística existir: cada condensação é uma chamada a mais num teto
# de ~10 RPM, e um limiar de 12 palavras condensaria quase toda pergunta real.
SELF_CONTAINED_MIN_WORDS = 4

_ANAPHORA_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(marker) for marker in ANAPHORIC_MARKERS) + r")\b"
)
_WORD_PATTERN = re.compile(r"\w+")

CONDENSATION_INSTRUCTIONS = """Reescreva a pergunta atual como uma pergunta completa e \
autocontida, resolvendo pronomes e referências com o que foi dito na conversa acima.
Se a pergunta já for autocontida, repita-a sem mudanças.
Responda apenas com a pergunta reescrita, em português do Brasil, sem preâmbulo, \
sem aspas e sem explicação."""


def should_condense(history: list[Message], question: str) -> bool:
    """Diz se a pergunta parece depender do que foi dito antes.

    Determinístico e sem LLM de propósito: decidir isto com uma chamada extra
    custaria a mesma quota que a heurística existe para economizar.

    Sem histórico não há o que resolver, e a pergunta vai direto ao retrieval.
    Com histórico, a pergunta é tratada como dependente quando traz um marcador
    anafórico ou quando é curta demais para significar alguma coisa sozinha.

    "Só condensar quando há histórico" não serviria: a partir da segunda
    pergunta sempre há histórico, e a condensação dobraria o consumo de todo
    turno — que é o que o teto de ~10 RPM do chat não suporta.
    """
    if not history:
        return False
    normalized = _normalize(question)
    if _ANAPHORA_PATTERN.search(normalized):
        return True
    return len(_WORD_PATTERN.findall(normalized)) < SELF_CONTAINED_MIN_WORDS


def build_condensation_prompt(history: list[Message], question: str) -> str:
    """Monta o prompt que pede a pergunta reescrita como autocontida.

    O histórico vem antes da pergunta porque é dele que o referente sai, e a
    instrução vem por último pelo mesmo motivo do prompt de resposta: é a
    última coisa lida que o modelo tende a obedecer.

    O `history` chega já recortado por `select_history_window` — a janela é
    aplicada uma vez por turno pelo chamador e vale para os dois prompts.
    """
    return "\n".join(
        [
            "Conversa até agora:",
            render_history(history),
            "",
            "Pergunta atual:",
            question,
            "",
            CONDENSATION_INSTRUCTIONS,
        ]
    )


def fallback_query(history: list[Message], question: str) -> str:
    """Devolve a query a usar quando a condensação falha ou estoura o timeout.

    Concatenar a última pergunta do usuário com a atual restaura o referente da
    anáfora sem custo, sem latência e sem erro visível: "quais serviços a YAITEC
    oferece?" + "e quanto a isso?" ainda embeda perto dos chunks sobre serviços,
    porque os termos que importam voltaram ao texto da busca.

    É pior que a reescrita do modelo — carrega palavras a mais —, e é por isso
    que é fallback e não o caminho principal. Sem histórico de usuário, a
    pergunta atual já é tudo que existe.
    """
    previous = _last_user_question(history)
    if previous is None:
        return question
    return f"{previous} {question}"


def _last_user_question(history: list[Message]) -> str | None:
    """Última mensagem do usuário na janela, ou `None` se não houver."""
    for message in reversed(history):
        if message.role == MessageRole.USER:
            return message.content
    return None


def _normalize(text: str) -> str:
    """Baixa a caixa e remove acentos, para a lista de marcadores ser uma só.

    Sem isto, "por quê", "por que" e "Por Quê" exigiriam três entradas na lista
    — e a que faltasse seria descoberta por uma pergunta de continuação que
    voltou vazia do retrieval.
    """
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
