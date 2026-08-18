"""Testes determinísticos do cálculo das métricas do eval.

O eval de verdade custa quota e exige Postgres — e é exatamente por isso que a
**aritmética** dele precisa de teste offline: um `recall@k` com erro de um na
posição, ou um `MRR` com base 0, produziria um número plausível e errado que
ninguém questionaria, porque o eval só roda à mão e o resultado vai colado para
o README.

Nada aqui toca rede, banco ou `GEMINI_API_KEY`: são listas literais entrando em
funções puras. Por isso o arquivo entra no `make test`.
"""

import json
from pathlib import Path

from eval.run_eval import (
    NEGATIVE,
    POSITIVE,
    Distribution,
    first_hit_rank,
    is_refused,
    load_dataset,
    mean_reciprocal_rank,
    recall_at_k,
    reciprocal_rank,
    summarize,
    sweep_thresholds,
)

DATASET = Path(__file__).resolve().parents[1] / "eval" / "dataset.json"


class TestFirstHitRank:
    def test_returns_one_based_position_of_the_expected_page(self) -> None:
        assert first_hit_rank([3, 1, 2], 1) == 2

    def test_returns_the_first_occurrence_when_the_page_repeats(self) -> None:
        assert first_hit_rank([2, 2, 2], 2) == 1

    def test_returns_none_when_the_page_was_not_retrieved(self) -> None:
        assert first_hit_rank([1, 1, 3], 2) is None

    def test_returns_none_for_an_empty_ranking(self) -> None:
        assert first_hit_rank([], 1) is None


class TestRecallAtK:
    def test_counts_only_hits_inside_the_first_k_positions(self) -> None:
        ranks: list[int | None] = [1, 3, 4, None]
        assert recall_at_k(ranks, 1) == 0.25
        assert recall_at_k(ranks, 3) == 0.5
        assert recall_at_k(ranks, 5) == 0.75

    def test_is_one_when_every_question_hits_in_first_place(self) -> None:
        assert recall_at_k([1, 1, 1], 1) == 1.0

    def test_is_zero_when_nothing_was_retrieved(self) -> None:
        assert recall_at_k([None, None], 3) == 0.0

    def test_empty_input_is_zero_instead_of_raising(self) -> None:
        assert recall_at_k([], 3) == 0.0


class TestReciprocalRank:
    def test_is_the_inverse_of_the_position(self) -> None:
        assert reciprocal_rank(1) == 1.0
        assert reciprocal_rank(2) == 0.5
        assert reciprocal_rank(4) == 0.25

    def test_is_zero_without_a_hit(self) -> None:
        assert reciprocal_rank(None) == 0.0


class TestMeanReciprocalRank:
    def test_averages_the_reciprocals_of_a_known_list(self) -> None:
        # (1 + 1/2 + 1/4 + 0) / 4 = 0.4375
        assert mean_reciprocal_rank([1, 2, 4, None]) == 0.4375

    def test_distinguishes_first_place_from_third_place(self) -> None:
        """É a razão de `MRR` existir ao lado do recall: `recall@3` daria 1,0 nos dois."""
        assert recall_at_k([3, 3], 3) == recall_at_k([1, 1], 3)
        assert mean_reciprocal_rank([1, 1]) > mean_reciprocal_rank([3, 3])

    def test_empty_input_is_zero_instead_of_raising(self) -> None:
        assert mean_reciprocal_rank([]) == 0.0


class TestSummarize:
    def test_reports_count_min_mean_and_max(self) -> None:
        stats = summarize([0.25, 0.5, 0.75])
        assert stats == Distribution(count=3, minimum=0.25, mean=0.5, maximum=0.75)

    def test_empty_input_is_a_zeroed_distribution(self) -> None:
        assert summarize([]) == Distribution(count=0, minimum=0.0, mean=0.0, maximum=0.0)


class TestIsRefused:
    def test_refuses_when_no_chunk_reaches_the_threshold(self) -> None:
        assert is_refused([0.4, 0.3], 0.5) is True

    def test_the_threshold_itself_is_accepted(self) -> None:
        """O corte é `>=`, igual ao de `core.retrieval.filter_by_threshold`."""
        assert is_refused([0.5], 0.5) is False

    def test_refuses_when_nothing_was_retrieved(self) -> None:
        assert is_refused([], 0.5) is True


class TestSweepThresholds:
    def test_empty_results_produce_an_empty_ladder(self) -> None:
        assert sweep_thresholds([], 5) == []


class TestDataset:
    """O dataset versionado é entrada do eval: um erro nele falsifica a métrica."""

    def test_loads_and_validates(self) -> None:
        items = load_dataset(DATASET)
        positives = [item for item in items if item.group == POSITIVE]
        negatives = [item for item in items if item.group == NEGATIVE]
        # O teto subiu de 12 para 20 no BUG-002: as sete positivas sem âncora
        # (P11–P16 e C03) são o que revela o piso real de similaridade de quem
        # pergunta sem repetir o nome da empresa. O intervalo continua existindo
        # para que mexer no dataset seja deliberado, não acidental.
        assert 8 <= len(positives) <= 20
        assert len(negatives) == 4

    def test_every_positive_has_a_page_and_every_negative_has_none(self) -> None:
        for item in load_dataset(DATASET):
            if item.group == POSITIVE:
                assert item.expected_page is not None
            else:
                assert item.expected_page is None

    def test_positives_cover_more_than_one_page(self) -> None:
        """Dataset concentrado numa página só mediria uma página, não o retrieval."""
        pages = {item.expected_page for item in load_dataset(DATASET) if item.expected_page}
        assert len(pages) >= 3

    def test_has_at_least_one_continuation_question(self) -> None:
        assert any(item.history for item in load_dataset(DATASET))

    def test_carries_no_api_key(self) -> None:
        """Guarda contra o vazamento mais bobo possível: chave colada no dataset."""
        raw = DATASET.read_text(encoding="utf-8")
        assert "AIza" not in raw
        assert "GEMINI_API_KEY" not in raw
        json.loads(raw)
