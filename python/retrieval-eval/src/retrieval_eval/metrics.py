"""Deterministic retrieval metrics.

Thirty years old, no LLM, no API key, and absent from most RAG tooling. These are the metrics
that localize a failure: ``recall@20`` high with ``recall@5`` low says retrieval found the
answer and ranking buried it, which points at the reranker rather than the chunker.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .models import Judgment, Measurement, QueryMetrics, RunEntry

DEFAULT_K = 10
DEFAULT_THRESHOLD = 1
_ROUND = 12


def _round(value: float) -> float:
    return round(value, _ROUND)


def _dcg(gains: Sequence[float]) -> float:
    return sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))


def query_metrics(
    relevance: dict[str, int],
    ranking: Sequence[str],
    k: int = DEFAULT_K,
    threshold: int = DEFAULT_THRESHOLD,
) -> QueryMetrics:
    """Compute metrics for a single query.

    Keys absent from ``relevance`` count as relevance 0, the standard closed-world
    assumption. That is a real limitation of shallow judgment pools, which is why
    :func:`retrieval_eval.judgments.validate` warns when a pool looks too thin.
    """
    top_k = list(ranking[:k])
    relevant = {key for key, rel in relevance.items() if rel >= threshold}
    hits = [key for key in top_k if key in relevant]

    gains = [2 ** relevance.get(key, 0) - 1 for key in top_k]
    ideal = sorted((2**rel - 1 for rel in relevance.values()), reverse=True)[:k]
    idcg = _dcg(ideal)

    mrr = 0.0
    for index, key in enumerate(top_k):
        if key in relevant:
            mrr = 1.0 / (index + 1)
            break

    found = 0
    ap_sum = 0.0
    for index, key in enumerate(top_k):
        if key in relevant:
            found += 1
            ap_sum += found / (index + 1)

    return QueryMetrics(
        precision=len(hits) / k,
        recall=len(hits) / len(relevant) if relevant else 0.0,
        ndcg=_dcg(gains) / idcg if idcg > 0 else 0.0,
        mrr=mrr,
        ap=ap_sum / len(relevant) if relevant else 0.0,
        hit_rate=1.0 if hits else 0.0,
    )


def relevance_by_query(judgments: Iterable[Judgment]) -> dict[str, dict[str, int]]:
    """Group judgments as ``query_id -> {ranking key: relevance}``."""
    out: dict[str, dict[str, int]] = {}
    for judgment in judgments:
        out.setdefault(judgment.query_id, {})[judgment.key] = judgment.relevance
    return out


def _deterministic(value: float) -> Measurement:
    return Measurement(value=_round(value), deterministic=True, n=1)


@dataclass(slots=True)
class ScoreResult:
    """Aggregate metrics plus the per-query detail needed to debug one bad query."""

    metrics: dict[str, Measurement]
    per_query: dict[str, QueryMetrics]
    #: Queries present in the judgments but missing from the run.
    missing_queries: list[str]


def score(
    judgments: Sequence[Judgment],
    run: Sequence[RunEntry],
    k: int = DEFAULT_K,
    threshold: int = DEFAULT_THRESHOLD,
) -> ScoreResult:
    """Macro-average metrics over queries.

    Queries with judgments but no run entry score zero rather than being dropped; silently
    skipping them inflates every metric, which is a common and very quiet bug.
    """
    by_query = relevance_by_query(judgments)
    rankings = {entry.query_id: entry.ranking for entry in run}

    per_query: dict[str, QueryMetrics] = {}
    missing: list[str] = []
    for query_id, relevance in by_query.items():
        ranking = rankings.get(query_id)
        if ranking is None:
            missing.append(query_id)
        per_query[query_id] = query_metrics(relevance, ranking or [], k=k, threshold=threshold)

    count = len(per_query)

    def mean(attribute: str) -> float:
        if count == 0:
            return 0.0
        total: float = sum(float(getattr(m, attribute)) for m in per_query.values())
        return total / count

    metrics = {
        f"precision@{k}": _deterministic(mean("precision")),
        f"recall@{k}": _deterministic(mean("recall")),
        f"ndcg@{k}": _deterministic(mean("ndcg")),
        "mrr": _deterministic(mean("mrr")),
        "map": _deterministic(mean("ap")),
        f"hit_rate@{k}": _deterministic(mean("hit_rate")),
    }
    return ScoreResult(metrics=metrics, per_query=per_query, missing_queries=missing)


@dataclass(slots=True)
class StratumScore:
    """Metrics for one query class, with its size so thin strata can be discounted."""

    n: int
    metrics: dict[str, Measurement]


def score_by_stratum(
    judgments: Sequence[Judgment],
    run: Sequence[RunEntry],
    k: int = DEFAULT_K,
    threshold: int = DEFAULT_THRESHOLD,
) -> dict[str, StratumScore]:
    """Score each stratum separately.

    A system can improve on the mean while failing an entire query class, so coverage across
    strata is reported instead of one average.
    """
    strata: dict[str, list[Judgment]] = {}
    for judgment in judgments:
        strata.setdefault(judgment.stratum or "_unstratified", []).append(judgment)

    out: dict[str, StratumScore] = {}
    for name, subset in strata.items():
        result = score(subset, run, k=k, threshold=threshold)
        out[name] = StratumScore(n=len(result.per_query), metrics=result.metrics)
    return out


def worst_stratum(
    per_stratum: dict[str, StratumScore], metric: str
) -> tuple[str, float, int] | None:
    """Return ``(name, value, n)`` for the lowest-scoring stratum, or ``None``."""
    worst: tuple[str, float, int] | None = None
    for name, stratum in per_stratum.items():
        measurement = stratum.metrics.get(metric)
        if measurement is None:
            continue
        if worst is None or measurement.value < worst[1]:
            worst = (name, measurement.value, stratum.n)
    return worst
