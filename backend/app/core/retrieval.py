"""Regras puras do retrieval: score, limiar, top-k e trecho da citação.

A busca em si é do adapter — é ela que fala com o banco. O que vive aqui é o que
decide **o que fazer com o que voltou**: converter a distância do pgvector em
similaridade, descartar o que não sustenta resposta, cortar o excedente e
recortar o trecho que a citação exibe.

Essa separação é o que torna a fundamentação testável sem Postgres: o limiar é a
única defesa contra o modelo responder com base nos "cinco chunks menos ruins"
quando o documento simplesmente não tem a resposta, e uma regra dessas não pode
depender de um banco no ar para ser verificada.
"""

from app.core.models import RetrievedChunk

SNIPPET_MAX_LENGTH = 240
ELLIPSIS = "…"

_SCORE_DECIMALS = 3


def similarity_from_distance(distance: float) -> float:
    """Converte a distância de cosseno do pgvector em similaridade em `[0,1]`.

    O operador `<=>` devolve `1 - cos(a,b)`, então a similaridade é `1 - d`. Os
    vetores já chegam normalizados em L2 do adapter de embeddings, o que é a
    condição para essa conta significar cosseno de verdade — sem a normalização
    o número continuaria saindo, só que mentindo.

    O grampo em `[0,1]` existe porque o float do banco volta com resíduo de
    ponto flutuante (`-2e-8`, `1.0000000004`), e um score negativo vazando para
    a citação faria a interface exibir relevância impossível. Três casas porque
    é a precisão que alguém lê num chip de citação; o resto é ruído.
    """
    return round(min(1.0, max(0.0, 1.0 - distance)), _SCORE_DECIMALS)


def filter_by_threshold(chunks: list[RetrievedChunk], threshold: float) -> list[RetrievedChunk]:
    """Descarta os chunks que não alcançam o limiar de similaridade.

    É o mecanismo da recusa: sem ele, uma pergunta sem relação nenhuma com o
    documento ainda traria os cinco vizinhos mais próximos, e o modelo
    responderia com aparência de fundamento sobre um contexto que não sustenta
    nada. O corte é `>=` para que o limiar configurado seja um valor aceito, e
    não o primeiro valor recusado.
    """
    return [chunk for chunk in chunks if chunk.score >= threshold]


def take_top_k(chunks: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
    """Devolve os `k` melhores chunks, do mais similar para o menos.

    A ordenação é refeita aqui, e não herdada do `ORDER BY` do banco, porque
    esta função também recebe listas fundidas ou filtradas — depender da ordem
    de chegada tornaria o resultado sensível a quem chamou antes.

    `k <= 0` devolve lista vazia: é o que faz `RETRIEVAL_TOP_K=0` desligar o
    retrieval por configuração em vez de virar um caso especial no chamador.
    """
    if k <= 0:
        return []
    return sorted(chunks, key=lambda chunk: chunk.score, reverse=True)[:k]


def has_grounding(chunks: list[RetrievedChunk]) -> bool:
    """Diz se sobrou algum trecho capaz de fundamentar a resposta.

    Existe como função nomeada, e não como `if chunks:` na rota, porque é a
    decisão de negócio que separa "responder" de "recusar sem chamar o LLM" —
    e é ela que o teste da recusa (AC-8) precisa poder apontar.
    """
    return bool(chunks)


def build_snippet(content: str, max_len: int = SNIPPET_MAX_LENGTH) -> str:
    """Recorta o trecho da citação em fronteira de palavra.

    O recorte acontece no servidor, uma vez, e viaja pronto no evento de
    citação: recortar de novo no cliente duplicaria a regra e faria as duas
    versões divergirem no primeiro ajuste.

    Cortar no caractere `max_len` partiria a última palavra ao meio, o que na
    tela parece defeito. O corte recua ao último espaço e as reticências entram
    **dentro** do limite, para que o texto exibido nunca passe do que a spec
    promete.
    """
    normalized = " ".join(content.split())
    if len(normalized) <= max_len:
        return normalized
    window = normalized[: max_len - len(ELLIPSIS)]
    cut = window.rfind(" ")
    return (window[:cut] if cut > 0 else window).rstrip() + ELLIPSIS
