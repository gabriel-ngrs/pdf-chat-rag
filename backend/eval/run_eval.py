"""Eval de retrieval: mede o que o RAG recupera, contra um dataset versionado.

Existe porque construir retrieval é fácil e **medir** retrieval é o que separa
uma implementação que entendeu o problema de uma que seguiu tutorial. E porque
`SIMILARITY_THRESHOLD` precisa sair de um número medido, não de um palpite: o
modelo de embeddings deste projeto vive numa faixa alta e comprimida (cos ≈
0,7156 entre "gato" e "mecânica quântica", medido em `eval/README.md`), então
nenhum limiar herdado de intuição sobrevive ao contato com os dados.

Três decisões de método que o resto do arquivo assume:

* **O PDF não é reingerido.** O `--document-id` vem pronto por parâmetro. A
  calibração exige olhar os números várias vezes, e reingerir a cada rodada
  queimaria a quota que o free tier não tem.
* **Cada pergunta é embedada uma única vez** e o resultado da busca é guardado.
  A varredura de limiares (`--sweep`) recalcula tudo offline sobre esses scores,
  o que torna a calibração gratuita depois da primeira rodada.
* **`recall@k` não depende do limiar.** Ele mede a **ordenação**; quem mede o
  limiar são as duas taxas de recusa. Misturar os dois é o erro que torna a
  calibração circular — recall melhora monotonicamente com limiar mais baixo, e
  otimizar por ele empurraria o corte para zero, destruindo a recusa (OQ-10).

Uso (a partir de `backend/`):

    uv run python -m eval.run_eval --document-id <uuid>
    uv run python -m eval.run_eval --document-id <uuid> --threshold 0.62 --top-k 5

Exige o Postgres do compose no ar e a `GEMINI_API_KEY` no `.env` da raiz do
worktree. Consome quota real (uma requisição de embedding por pergunta), por
isso está fora do `make check`.
"""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog

from app.adapters.db import Database
from app.adapters.gemini import EmbeddingClient, GeminiEmbeddingClient
from app.adapters.repository import ConversationRepository, PostgresConversationRepository
from app.config import Settings
from app.core.condensation import fallback_query, should_condense
from app.core.models import Message, MessageRole, RetrievedChunk

EVAL_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = EVAL_ROOT.parent
# O `.env` vive na raiz do worktree, um nível acima de `backend/`; apontar para
# ele explicitamente faz o script funcionar de qualquer diretório de trabalho.
ENV_FILE = BACKEND_ROOT.parent / ".env"
DEFAULT_DATASET = EVAL_ROOT / "dataset.json"

POSITIVE = "positive"
NEGATIVE = "negative"

# Os `k` de recall que o relatório mostra. O 3 é o que importa: com ~10 chunks
# no documento de avaliação, `recall@5` seria quase 1,0 por construção — uma
# métrica que não pode falhar não mede nada.
RECALL_KS = (1, 3)
GATE_RECALL_K = 3

# Pisos de NFR-7. Não são configuráveis de propósito: um gate que o operador
# afrouxa pela linha de comando não é gate.
MIN_RECALL_AT_3 = 0.8
MIN_MRR = 0.7

SWEEP_STEPS = 13
SWEEP_MARGIN = 0.02

_CHUNK_COUNT_SQL = "SELECT count(*) FROM chunks WHERE document_id = $1"


@dataclass(frozen=True, slots=True)
class EvalItem:
    """Uma pergunta do dataset, com o que se espera dela.

    `expected_page` é `None` exatamente nas negativas — é o campo que separa os
    dois grupos, e por isso o grupo é derivado dele e conferido contra o campo
    `group` do JSON: dataset com os dois discordando é erro de dataset, não
    resultado ruim de retrieval.
    """

    id: str
    group: str
    kind: str
    question: str
    expected_page: int | None
    history: tuple[Message, ...]


@dataclass(frozen=True, slots=True)
class Retrieval:
    """O que uma busca devolveu, guardado para ser reanalisado offline.

    Guardar os chunks (e não só um veredito) é o que permite varrer limiares sem
    gastar quota de novo: o limiar é aplicado sobre `chunks`, não sobre a rede.
    """

    query: str
    condensed: bool
    chunks: tuple[RetrievedChunk, ...]

    @property
    def pages(self) -> tuple[int, ...]:
        """Páginas recuperadas, na ordem do ranking."""
        return tuple(chunk.page_number for chunk in self.chunks)

    @property
    def scores(self) -> tuple[float, ...]:
        """Similaridades recuperadas, na ordem do ranking."""
        return tuple(chunk.score for chunk in self.chunks)


@dataclass(frozen=True, slots=True)
class ItemResult:
    """O resultado de um item: a busca principal e, se houver, a da pergunta crua.

    `raw` só existe nos itens com histórico. Ele não entra em nenhuma métrica —
    serve para o relatório mostrar o **delta** entre perguntar cru e perguntar
    condensado. Sem esse contraste, a afirmação "a condensação importa" seria
    uma alegação de arquitetura sem evidência.
    """

    item: EvalItem
    main: Retrieval
    raw: Retrieval | None


@dataclass(frozen=True, slots=True)
class Distribution:
    """Mínimo, média e máximo de um conjunto de similaridades.

    Existe como tipo próprio porque o número que decide o limiar não é uma
    métrica de qualidade e sim o **contraste entre duas distribuições**: a das
    positivas e a das negativas. Uma sozinha não diz nada.
    """

    count: int
    minimum: float
    mean: float
    maximum: float


@dataclass(frozen=True, slots=True)
class Metrics:
    """As seis métricas que FR-13 exige, todas para um mesmo limiar.

    * `recall@1` e `recall@3` — a página certa aparece entre os `k` primeiros
      chunks? Mede a **ordenação**, que é o que o retrieval controla.
    * `MRR` — média do inverso da posição do primeiro acerto. Diferencia
      "acertou em primeiro" de "acertou em terceiro", que o recall trata igual.
    * `correct_refusal_rate` — fração das negativas corretamente recusadas. É o
      contrapeso do recall: sem ele, o ótimo é limiar zero.
    * `false_refusal_rate` — fração das positivas recusadas por engano. É o
      contrapeso da recusa: sem ele, o ótimo é limiar 1.
    * `positive_scores` / `negative_scores` — as distribuições que justificam o
      valor escolhido do limiar em vez de o legitimarem depois do fato.
    """

    threshold: float
    recall_at_1: float
    recall_at_3: float
    mrr: float
    correct_refusal_rate: float
    false_refusal_rate: float
    positive_scores: Distribution
    negative_scores: Distribution


# ── Métricas puras ────────────────────────────────────────────────────────────
# Estas quatro funções não tocam rede, banco nem configuração: recebem listas e
# devolvem números. É o que torna `tests/test_eval_metrics.py` determinístico e
# o que permite que a varredura de limiares rode offline.


def first_hit_rank(pages: Sequence[int], expected_page: int) -> int | None:
    """Posição (base 1) do primeiro chunk da página esperada, ou `None`.

    Base 1 porque é a convenção de `MRR`: o inverso da posição precisa valer 1,0
    para o primeiro lugar. Com base 0 a conta explodiria por divisão por zero,
    que é a forma mais barata de errar esta métrica.
    """
    for position, page in enumerate(pages, start=1):
        if page == expected_page:
            return position
    return None


def recall_at_k(ranks: Sequence[int | None], k: int) -> float:
    """Fração de perguntas cujo primeiro acerto caiu dentro dos `k` primeiros.

    Recebe ranks já calculados, e não os chunks, porque assim a métrica não
    conhece nem página nem documento — e um teste com listas literais consegue
    exercitá-la sem construir meio domínio.

    Lista vazia devolve `0,0` em vez de levantar: um grupo vazio é um dataset
    quebrado, e o relatório precisa conseguir imprimir isso em vez de morrer.
    """
    if not ranks:
        return 0.0
    hits = sum(1 for rank in ranks if rank is not None and rank <= k)
    return hits / len(ranks)


def reciprocal_rank(rank: int | None) -> float:
    """Inverso da posição do acerto; zero quando não houve acerto nenhum."""
    if rank is None:
        return 0.0
    return 1.0 / rank


def mean_reciprocal_rank(ranks: Sequence[int | None]) -> float:
    """Média dos inversos das posições de acerto.

    Existe ao lado do recall porque os dois discordam de propósito: recuperar a
    página certa em primeiro e em terceiro dá o mesmo `recall@3`, e o usuário
    que lê a citação sente a diferença. `MRR` é a métrica que sente também.
    """
    if not ranks:
        return 0.0
    return sum(reciprocal_rank(rank) for rank in ranks) / len(ranks)


def summarize(values: Sequence[float]) -> Distribution:
    """Reduz uma lista de similaridades a mínimo, média e máximo."""
    if not values:
        return Distribution(count=0, minimum=0.0, mean=0.0, maximum=0.0)
    return Distribution(
        count=len(values),
        minimum=min(values),
        mean=sum(values) / len(values),
        maximum=max(values),
    )


def is_refused(scores: Sequence[float], threshold: float) -> bool:
    """Diz se a pergunta seria recusada: nenhum chunk alcançou o limiar.

    Espelha `core.retrieval.filter_by_threshold` + `has_grounding` — o corte é
    `>=`, para que o limiar configurado seja um valor aceito e não o primeiro
    valor recusado. Reimplementado aqui em uma linha, e não importado, porque
    aquele par trabalha sobre `RetrievedChunk` e este trabalha sobre a lista de
    scores que a varredura offline manipula.
    """
    return not any(score >= threshold for score in scores)


def compute_metrics(results: Sequence[ItemResult], threshold: float, top_k: int) -> Metrics:
    """Calcula as seis métricas para um limiar, sobre resultados já buscados.

    Recebe `threshold` como parâmetro em vez de lê-lo da configuração porque é
    exatamente isso que a varredura precisa variar sem tocar na rede.
    """
    positives = [result for result in results if result.item.group == POSITIVE]
    negatives = [result for result in results if result.item.group == NEGATIVE]

    # O `is not None` nunca descarta nada: `_parse_item` garante que positiva
    # tem página. Está aqui porque estreitar o tipo com um `if` custa uma linha,
    # e um `assert` que some sob `python -O` não é garantia nenhuma.
    ranks: list[int | None] = [
        first_hit_rank(result.main.pages[:top_k], result.item.expected_page)
        for result in positives
        if result.item.expected_page is not None
    ]

    positive_best = [_best_score(result.main.scores[:top_k]) for result in positives]
    negative_best = [_best_score(result.main.scores[:top_k]) for result in negatives]

    false_refusals = sum(
        1 for result in positives if is_refused(result.main.scores[:top_k], threshold)
    )
    correct_refusals = sum(
        1 for result in negatives if is_refused(result.main.scores[:top_k], threshold)
    )

    return Metrics(
        threshold=threshold,
        recall_at_1=recall_at_k(ranks, 1),
        recall_at_3=recall_at_k(ranks, GATE_RECALL_K),
        mrr=mean_reciprocal_rank(ranks),
        correct_refusal_rate=_rate(correct_refusals, len(negatives)),
        false_refusal_rate=_rate(false_refusals, len(positives)),
        positive_scores=summarize(positive_best),
        negative_scores=summarize(negative_best),
    )


def meets_nfr7(metrics: Metrics) -> bool:
    """Diz se a configuração medida cumpre NFR-7.

    Os quatro pisos juntos, e não um "score" combinado: uma média esconderia
    exatamente o caso que o requisito proíbe — recall alto pago com falsa
    recusa, ou recusa perfeita paga com recall no chão.
    """
    return (
        metrics.recall_at_3 >= MIN_RECALL_AT_3
        and metrics.mrr >= MIN_MRR
        and metrics.correct_refusal_rate >= 1.0
        and metrics.false_refusal_rate <= 0.0
    )


def _best_score(scores: Sequence[float]) -> float:
    """Maior similaridade recuperada — é ela que decide recusar ou não."""
    return max(scores) if scores else 0.0


def _rate(count: int, total: int) -> float:
    """Fração `count/total`; grupo vazio conta como 1,0 (nada a errar)."""
    if total == 0:
        return 1.0
    return count / total


# ── Dataset ───────────────────────────────────────────────────────────────────


def load_dataset(path: Path) -> list[EvalItem]:
    """Lê e valida o dataset versionado.

    A validação é estrita porque um dataset silenciosamente errado produz uma
    métrica bonita e falsa: negativa com `expected_page`, positiva sem página,
    ou um grupo inteiro faltando. Todos viram erro aqui, não número no relatório.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_items = payload["items"]
    if not isinstance(raw_items, list):
        raise ValueError("O dataset precisa ter uma lista em `items`.")

    items = [_parse_item(raw) for raw in raw_items]
    if not any(item.group == POSITIVE for item in items):
        raise ValueError("O dataset não tem nenhuma pergunta positiva.")
    if not any(item.group == NEGATIVE for item in items):
        raise ValueError("O dataset não tem nenhuma pergunta negativa.")
    return items


def _parse_item(raw: object) -> EvalItem:
    if not isinstance(raw, dict):
        raise ValueError("Cada item do dataset precisa ser um objeto.")
    expected_page = raw.get("expected_page")
    if expected_page is not None and not isinstance(expected_page, int):
        raise ValueError(f"`expected_page` de {raw.get('id')!r} precisa ser inteiro ou nulo.")

    declared = str(raw.get("group", ""))
    derived = NEGATIVE if expected_page is None else POSITIVE
    if declared != derived:
        raise ValueError(
            f"O item {raw.get('id')!r} declara `group={declared!r}` mas "
            f"`expected_page` indica {derived!r}."
        )

    return EvalItem(
        id=str(raw["id"]),
        group=derived,
        kind=str(raw.get("kind", "")),
        question=str(raw["question"]),
        history=_parse_history(raw.get("history", [])),
        expected_page=expected_page,
    )


def _parse_history(raw: object) -> tuple[Message, ...]:
    """Converte o histórico do JSON nas `Message` que `core.condensation` espera.

    `id` e `created_at` são preenchidos com valores sintéticos: nem
    `should_condense` nem `fallback_query` os leem, e inventar um formato de
    histórico só para o eval faria o eval exercitar um caminho que a aplicação
    não tem.
    """
    if not isinstance(raw, list):
        raise ValueError("`history` precisa ser uma lista de mensagens.")
    messages: list[Message] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError("Cada mensagem do histórico precisa ser um objeto.")
        messages.append(
            Message(
                id=index,
                role=MessageRole(str(entry["role"])),
                content=str(entry["content"]),
                citations=(),
                truncated=False,
                created_at=datetime(1970, 1, 1, tzinfo=UTC),
            )
        )
    return tuple(messages)


def build_query(item: EvalItem) -> tuple[str, bool]:
    """Monta a query de retrieval do item e diz se ela foi reescrita.

    Usa `should_condense` + `fallback_query`, e não a condensação por LLM: os
    dois são determinísticos, não custam quota e não introduzem variância entre
    rodadas — que é o que um eval de retrieval precisa medir sem ruído. A
    reescrita por LLM (fase A.4) só pode ser melhor que este fallback, então o
    número medido aqui é um **piso** da qualidade em produção, nunca um teto
    otimista.
    """
    if not should_condense(list(item.history), item.question):
        return item.question, False
    return fallback_query(list(item.history), item.question), True


# ── Execução ──────────────────────────────────────────────────────────────────


async def run_retrievals(
    items: Sequence[EvalItem],
    repository: ConversationRepository,
    embedder: EmbeddingClient,
    document_id: UUID,
    limit: int,
    hybrid: bool = False,
) -> list[ItemResult]:
    """Embeda cada query uma vez e busca os chunks correspondentes.

    O cache por texto não é micro-otimização: itens de continuação são buscados
    duas vezes (condensada e crua) e perguntas podem repetir termos entre
    rodadas de calibração. Cada entrada evitada é uma requisição a menos num
    free tier que é o gargalo declarado da spec.
    """
    vectors: dict[str, list[float]] = {}

    async def search(text: str) -> tuple[RetrievedChunk, ...]:
        vector = vectors.get(text)
        if vector is None:
            # O SDK do provedor é bloqueante: chamá-lo direto no laço `async`
            # seguraria o event loop. Aqui isso só custaria tempo de script, mas
            # manter o padrão da aplicação evita que alguém copie daqui um
            # trecho que na API seria um travamento.
            vector = await asyncio.to_thread(embedder.embed_query, text)
            vectors[text] = vector
        # `query` só é passada no modo híbrido: sem ela o repositório faz a
        # busca densa pura, que é a baseline. É o mesmo caminho de código nos
        # dois modos — o que isola o efeito da fusão de qualquer outra
        # variável, inclusive de uma reingestão diferente.
        return tuple(
            await repository.search_chunks(
                document_id, vector, limit, text if hybrid else None
            )
        )

    results: list[ItemResult] = []
    for item in items:
        query, condensed = build_query(item)
        main = Retrieval(query=query, condensed=condensed, chunks=await search(query))
        raw: Retrieval | None = None
        if item.history:
            raw = Retrieval(
                query=item.question, condensed=False, chunks=await search(item.question)
            )
        results.append(ItemResult(item=item, main=main, raw=raw))
    return results


async def count_chunks(database: Database, document_id: UUID) -> int:
    """Quantos chunks o documento tem no banco.

    Conferido **antes** de gastar qualquer embedding: um `--document-id` errado
    ou um documento ainda não ingerido daria recall zero em tudo, e a leitura
    natural seria culpar o retrieval. O número também vai para o relatório,
    porque é ele que sustenta a afirmação de que `recall@3` pode falhar.
    """
    value = await database.pool.fetchval(_CHUNK_COUNT_SQL, document_id)
    return int(value or 0)


# ── Relatório ─────────────────────────────────────────────────────────────────


def format_report(
    results: Sequence[ItemResult],
    metrics: Metrics,
    sweep: Sequence[Metrics],
    *,
    document_id: UUID,
    chunk_count: int,
    top_k: int,
) -> str:
    """Monta o relatório inteiro em markdown, pronto para colar no README.

    Markdown e não JSON porque o consumidor é humano: a fase de entrega manda
    colar estes números no README, e o avaliador não vai rodar `make eval`.
    """
    lines: list[str] = []
    lines.append("## Eval de retrieval — `Exemplo-YAITEC.pdf`")
    lines.append("")
    lines.append(f"- `document_id`: `{document_id}`")
    lines.append(f"- chunks no banco: **{chunk_count}**")
    lines.append(
        f"- `RETRIEVAL_TOP_K`: **{top_k}** | "
        f"`SIMILARITY_THRESHOLD`: **{metrics.threshold:.3f}**"
    )
    lines.append(
        f"- itens: {len(results)} ({metrics.positive_scores.count} positivas, "
        f"{metrics.negative_scores.count} negativas)"
    )
    lines.append("")
    lines.extend(_per_item_table(results, metrics.threshold, top_k))
    lines.append("")
    lines.extend(_condensation_table(results, top_k))
    lines.append("")
    lines.extend(_aggregate_table(metrics))
    lines.append("")
    lines.extend(_distribution_table(results, top_k))
    lines.append("")
    lines.extend(_sweep_table(sweep))
    lines.append("")
    lines.extend(_gate_block(metrics))
    return "\n".join(lines)


def _per_item_table(results: Sequence[ItemResult], threshold: float, top_k: int) -> list[str]:
    lines = ["### Por pergunta", ""]
    lines.append(
        "| id | grupo | query | esperada | páginas recuperadas "
        "| rank | melhor score | recusada? |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for result in results:
        item = result.item
        scores = result.main.scores[:top_k]
        pages = result.main.pages[:top_k]
        rank = (
            None
            if item.expected_page is None
            else first_hit_rank(pages, item.expected_page)
        )
        refused = is_refused(scores, threshold)
        expected = "—" if item.expected_page is None else str(item.expected_page)
        rendered_pages = ", ".join(
            f"p{page}({score:.3f})" for page, score in zip(pages, scores, strict=True)
        )
        verdict = _refusal_verdict(item.group, refused)
        lines.append(
            f"| {item.id} | {item.group} | {_escape(result.main.query)} | {expected} | "
            f"{rendered_pages} | {rank if rank is not None else '—'} | "
            f"{_best_score(scores):.3f} | {verdict} |"
        )
    return lines


def _refusal_verdict(group: str, refused: bool) -> str:
    """Traduz a decisão de recusa no veredito que o grupo espera dela."""
    if group == NEGATIVE:
        return "sim ✓" if refused else "**não ✗**"
    return "**sim ✗ (falsa recusa)**" if refused else "não ✓"


def _condensation_table(results: Sequence[ItemResult], top_k: int) -> list[str]:
    """Delta entre perguntar cru e perguntar condensado, nos itens com histórico.

    Não é métrica — é a evidência de que o passo de condensação faz diferença.
    Sem esta tabela, "a pergunta de continuação funciona" seria uma alegação.
    """
    with_history = [result for result in results if result.raw is not None]
    lines = ["### Continuação: pergunta crua × pergunta condensada", ""]
    if not with_history:
        lines.append("_Nenhum item com histórico no dataset._")
        return lines
    lines.append("| id | esperada | query crua | rank cru | query condensada | rank condensado |")
    lines.append("|---|---|---|---|---|---|")
    for result in with_history:
        raw = result.raw
        expected = result.item.expected_page
        if raw is None or expected is None:  # pragma: no cover - filtrado acima
            continue
        raw_rank = first_hit_rank(raw.pages[:top_k], expected)
        main_rank = first_hit_rank(result.main.pages[:top_k], expected)
        lines.append(
            f"| {result.item.id} | {expected} | {_escape(raw.query)} | "
            f"{raw_rank if raw_rank is not None else '— (não recuperou)'} | "
            f"{_escape(result.main.query)} | "
            f"{main_rank if main_rank is not None else '— (não recuperou)'} |"
        )
    return lines


def _aggregate_table(metrics: Metrics) -> list[str]:
    lines = ["### Agregado", ""]
    lines.append("| métrica | valor | piso NFR-7 | situação |")
    lines.append("|---|---|---|---|")
    lines.append(f"| `recall@1` (positivas) | {metrics.recall_at_1:.3f} | — | — |")
    lines.append(
        f"| `recall@3` (positivas) | {metrics.recall_at_3:.3f} | ≥ {MIN_RECALL_AT_3:.2f} | "
        f"{_ok(metrics.recall_at_3 >= MIN_RECALL_AT_3)} |"
    )
    lines.append(
        f"| `MRR` (positivas) | {metrics.mrr:.3f} | ≥ {MIN_MRR:.2f} | "
        f"{_ok(metrics.mrr >= MIN_MRR)} |"
    )
    lines.append(
        f"| taxa de recusa correta (negativas) | {metrics.correct_refusal_rate:.3f} | 1.00 | "
        f"{_ok(metrics.correct_refusal_rate >= 1.0)} |"
    )
    lines.append(
        f"| taxa de falsa recusa (positivas) | {metrics.false_refusal_rate:.3f} | 0.00 | "
        f"{_ok(metrics.false_refusal_rate <= 0.0)} |"
    )
    return lines


def _distribution_table(results: Sequence[ItemResult], top_k: int) -> list[str]:
    """Distribuição por grupo, mais a folga que justifica o limiar escolhido."""
    positive_best = [
        _best_score(result.main.scores[:top_k])
        for result in results
        if result.item.group == POSITIVE
    ]
    negative_best = [
        _best_score(result.main.scores[:top_k])
        for result in results
        if result.item.group == NEGATIVE
    ]
    positive_all = [
        score
        for result in results
        if result.item.group == POSITIVE
        for score in result.main.scores[:top_k]
    ]
    negative_all = [
        score
        for result in results
        if result.item.group == NEGATIVE
        for score in result.main.scores[:top_k]
    ]

    lines = ["### Distribuição de similaridade, por grupo", ""]
    lines.append("| conjunto | n | mín | média | máx |")
    lines.append("|---|---|---|---|---|")
    for label, values in (
        ("positivas — melhor chunk", positive_best),
        ("negativas — melhor chunk", negative_best),
        ("positivas — todos os chunks do top-k", positive_all),
        ("negativas — todos os chunks do top-k", negative_all),
    ):
        stats = summarize(values)
        lines.append(
            f"| {label} | {stats.count} | {stats.minimum:.3f} | "
            f"{stats.mean:.3f} | {stats.maximum:.3f} |"
        )

    lines.append("")
    highest_negative = summarize(negative_best).maximum
    lowest_positive = summarize(positive_best).minimum
    gap = lowest_positive - highest_negative
    lines.append(f"- maior similaridade entre as **negativas**: **{highest_negative:.3f}**")
    lines.append(f"- menor similaridade entre as **positivas**: **{lowest_positive:.3f}**")
    lines.append(f"- folga entre os dois grupos: **{gap:+.3f}**")
    if gap > 0:
        lines.append(
            f"- ponto médio da folga (candidato a `SIMILARITY_THRESHOLD`): "
            f"**{(highest_negative + lowest_positive) / 2:.3f}**"
        )
    else:
        lines.append(
            "- **os grupos se sobrepõem**: nenhum limiar separa positivas de negativas "
            "sem errar de um dos dois lados."
        )
    return lines


def _sweep_table(sweep: Sequence[Metrics]) -> list[str]:
    """Varredura de limiares, recalculada offline sobre os mesmos embeddings.

    Só as duas taxas de recusa aparecem porque só elas dependem do limiar:
    `recall` e `MRR` medem a ordenação e são constantes ao longo da varredura.
    Mostrar as quatro daria a impressão falsa de que existe um limiar que
    melhora o recall.
    """
    lines = ["### Varredura de limiar (offline, sem custo de quota)", ""]
    lines.append("| limiar | recusa correta (negativas) | falsa recusa (positivas) | NFR-7 |")
    lines.append("|---|---|---|---|")
    for metrics in sweep:
        lines.append(
            f"| {metrics.threshold:.3f} | {metrics.correct_refusal_rate:.3f} | "
            f"{metrics.false_refusal_rate:.3f} | {_ok(meets_nfr7(metrics))} |"
        )
    return lines


def _gate_block(metrics: Metrics) -> list[str]:
    passed = meets_nfr7(metrics)
    verdict = "**NFR-7 ATINGIDO**" if passed else "**NFR-7 NÃO ATINGIDO**"
    return ["### Gate", "", f"{verdict} com `SIMILARITY_THRESHOLD={metrics.threshold:.3f}`."]


def _ok(passed: bool) -> str:
    return "ok" if passed else "**falha**"


def _escape(text: str) -> str:
    """Neutraliza o `|` para não quebrar a tabela markdown."""
    return text.replace("|", "\\|")


def sweep_thresholds(results: Sequence[ItemResult], top_k: int) -> list[float]:
    """Escala de limiares que cobre a faixa realmente observada nos dados.

    Fixa (`0,50 … 0,70`) ela poderia cair inteira fora da região interessante —
    a faixa deste modelo é alta e comprimida, e uma escala herdada de intuição é
    justamente o que esta fase existe para eliminar. Derivá-la dos scores
    medidos garante que a tabela mostre onde as duas taxas realmente mudam.
    """
    best = [_best_score(result.main.scores[:top_k]) for result in results]
    if not best:
        return []
    low = max(0.0, min(best) - SWEEP_MARGIN)
    high = min(1.0, max(best) + SWEEP_MARGIN)
    if high <= low:
        return [round(low, 3)]
    step = (high - low) / (SWEEP_STEPS - 1)
    return [round(low + step * index, 3) for index in range(SWEEP_STEPS)]


# ── Entrada ───────────────────────────────────────────────────────────────────


def route_logs_to_stderr() -> None:
    """Manda o log estruturado para o `stderr`, deixando o `stdout` só com o relatório.

    O relatório existe para ser redirecionado (`make eval > eval.md`) e colado no
    README. Sem isto, cada `embedding.batch` do adapter cairia no meio das
    tabelas markdown — e a fase de entrega pede o relatório colável, não um
    relatório para limpar à mão.
    """
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))


def load_env_file(path: Path) -> None:
    """Copia o `.env` da raiz do worktree para o ambiente do processo.

    `Settings` procura o `.env` no diretório de trabalho, e o `make eval` roda a
    partir de `backend/` — um nível abaixo de onde o arquivo vive. Passar
    `_env_file=` funcionaria em runtime, mas a assinatura de `Settings` que o
    mypy enxerga tem só os campos do modelo, e `mypy --strict` reprova a
    chamada; copiar as chaves para `os.environ` funciona nos dois lados.

    Variável já presente no ambiente ganha do arquivo: quem exporta
    `DATABASE_URL` antes de rodar quer aquele valor, não o do disco.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_settings() -> Settings:
    """Configuração do processo, com o `.env` da raiz já no ambiente."""
    load_env_file(ENV_FILE)
    return Settings()


def parse_args(argv: Sequence[str], settings: Settings) -> argparse.Namespace:
    """Argumentos da linha de comando, com defaults vindos de `Settings`.

    `--threshold` e `--top-k` existem para varrer valores **sem editar código**
    e sem mexer no `.env` — é a diferença entre calibrar e chutar. Os defaults
    saem da configuração real para que uma execução sem argumentos meça
    exatamente o que a aplicação faria.
    """
    parser = argparse.ArgumentParser(
        prog="eval.run_eval",
        description="Mede a qualidade do retrieval contra o dataset versionado.",
    )
    # O id continua obrigatório — o que muda é por onde ele entra. O alvo
    # `make eval` do Makefile roda `python -m eval.run_eval` sem argumentos, e
    # `make` não tem como repassar um flag; aceitar `EVAL_DOCUMENT_ID` do
    # ambiente é o que torna `EVAL_DOCUMENT_ID=<uuid> make eval` executável sem
    # mexer no Makefile. Sem flag e sem variável, o argparse recusa.
    default_document_id = os.environ.get("EVAL_DOCUMENT_ID")
    parser.add_argument(
        "--document-id",
        default=default_document_id,
        required=default_document_id is None,
        help="UUID de um documento já ingerido e `ready` (ou a variável "
        "EVAL_DOCUMENT_ID). O eval NÃO reingere o PDF.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=settings.similarity_threshold,
        help="Limiar de similaridade avaliado (default: SIMILARITY_THRESHOLD).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=settings.retrieval_top_k,
        help="Quantos chunks considerar por pergunta (default: RETRIEVAL_TOP_K).",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Funde a busca densa com a lexical por RRF (fase A.7). Sem esta flag, "
        "a busca é só densa — que é a baseline contra a qual o delta é medido.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Caminho do dataset JSON.",
    )
    parser.add_argument(
        "--sweep",
        default=None,
        help="Limiares extras a varrer, separados por vírgula. Sem isto, a escala "
        "é derivada dos scores observados.",
    )
    return parser.parse_args(list(argv))


def _parse_sweep(raw: str | None, results: Sequence[ItemResult], top_k: int) -> list[float]:
    if raw is None:
        return sweep_thresholds(results, top_k)
    return [float(piece) for piece in raw.split(",") if piece.strip()]


async def run(argv: Sequence[str]) -> int:
    """Executa o eval e devolve o código de saída do processo.

    Devolve `1` quando NFR-7 não é cumprido — a métrica precisa **poder
    reprovar**, senão o `make eval` seria decoração. O relatório é impresso
    antes do veredito nos dois casos: um eval que falha sem mostrar os números
    não ajuda ninguém a entender por que falhou.
    """
    route_logs_to_stderr()
    settings = load_settings()
    args = parse_args(argv, settings)
    document_id = UUID(str(args.document_id))
    hybrid = bool(args.hybrid)
    top_k = int(args.top_k)
    threshold = float(args.threshold)
    items = load_dataset(Path(args.dataset))

    database = Database(settings.database_url)
    await database.connect()
    try:
        chunk_count = await count_chunks(database, document_id)
        if chunk_count == 0:
            print(
                f"Nenhum chunk para o documento {document_id}. "
                "Ingira o PDF antes de rodar o eval — este script não reingere nada.",
                file=sys.stderr,
            )
            return 1
        repository = PostgresConversationRepository(database)
        embedder = GeminiEmbeddingClient(settings)
        # `max(top_k, 3)` para que `recall@3` continue calculável mesmo com
        # `RETRIEVAL_TOP_K` menor que 3 — a métrica do gate não pode depender de
        # uma variável de ambiente que alguém baixou por outro motivo.
        results = await run_retrievals(
            items, repository, embedder, document_id, max(top_k, GATE_RECALL_K), hybrid
        )
    finally:
        await database.close()

    metrics = compute_metrics(results, threshold, top_k)
    sweep = [
        compute_metrics(results, value, top_k)
        for value in _parse_sweep(args.sweep, results, top_k)
    ]
    print(
        format_report(
            results,
            metrics,
            sweep,
            document_id=document_id,
            chunk_count=chunk_count,
            top_k=top_k,
        )
    )
    return 0 if meets_nfr7(metrics) else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada síncrono. Nada roda no import — só aqui."""
    return asyncio.run(run(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
