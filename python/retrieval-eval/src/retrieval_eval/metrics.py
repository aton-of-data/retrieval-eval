"""Deterministic retrieval metrics.

Thirty years old, no LLM, no API key, and absent from most RAG tooling. These are the metrics
that localize a failure: ``recall@20`` high with ``recall@5`` low says retrieval found the
answer and ranking buried it, which points at the reranker rather than the chunker.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import NamedTuple

from .models import Judgment, Measurement, QueryMetrics, RunEntry

DEFAULT_K = 10
DEFAULT_THRESHOLD = 1
_ROUND = 12


def _round(value: float) -> float:
    return round(value, _ROUND)


def dedupe(ranking: Sequence[str]) -> list[str]:
    """Drop repeated keys from a ranking, keeping the first occurrence.

    A retriever that returns the same chunk twice is routine: a hybrid search merges two indexes,
    or a multi-query expansion unions its results, and nothing deduplicates. Counted naively the
    repeat scores as a second hit, which pushes ``recall@k``, ``map@k`` and ``ndcg@k`` above 1.0
    and can carry a failing run past a gate. A repeat is not new evidence, so only the first
    occurrence counts. :func:`score` names the queries it happened to rather than correcting
    quietly.
    """
    seen: set[str] = set()
    out: list[str] = []
    for key in ranking:
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


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
    # Deduplicated before the cutoff is applied: a repeat occupies no rank of its own.
    top_k = dedupe(ranking)[:k]
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


# Two-sided 95% Student-t critical values. The index is the degrees of freedom.
# Identical to the TypeScript table. A normal critical value is too small at the sample sizes
# this is built for, and clamping a negative lower bound up to 0 lets a ci-lower gate pass.
# Above 120 degrees of freedom the df=120 value is used, which is slightly wide.
_T_95: tuple[float, ...] = (
    0,
    12.706204736175,
    4.302652729749,
    3.182446305284,
    2.776445105198,
    2.570581835636,
    2.446911851145,
    2.364624251593,
    2.306004135204,
    2.262157162798,
    2.228138851986,
    2.200985160092,
    2.178812829667,
    2.160368656463,
    2.144786687918,
    2.13144954556,
    2.119905299221,
    2.109815577833,
    2.100922040241,
    2.093024054408,
    2.085963447266,
    2.079613844728,
    2.073873067904,
    2.068657610419,
    2.063898561628,
    2.059538552753,
    2.055529438643,
    2.05183051648,
    2.048407141795,
    2.045229642133,
    2.042272456301,
    2.039513446396,
    2.03693334346,
    2.034515297449,
    2.032244509318,
    2.03010792825,
    2.02809400098,
    2.026192463029,
    2.024394163912,
    2.022690920037,
    2.021075390306,
    2.019540970441,
    2.018081702818,
    2.016692199228,
    2.015367574444,
    2.014103388881,
    2.012895598919,
    2.01174051373,
    2.010634757624,
    2.009575237129,
    2.008559112101,
    2.007583770316,
    2.006646805062,
    2.005745995318,
    2.004879288188,
    2.004044783289,
    2.003240718848,
    2.002465459291,
    2.001717484145,
    2.000995378088,
    2.000297822014,
    1.999623584995,
    1.998971517033,
    1.998340542521,
    1.997729654318,
    1.997137908392,
    1.996564418952,
    1.996008354025,
    1.99546893143,
    1.994945415107,
    1.994437111771,
    1.993943367846,
    1.993463566662,
    1.99299712589,
    1.992543495181,
    1.992102154002,
    1.991672609645,
    1.991254395388,
    1.990847068812,
    1.99045021023,
    1.990063421254,
    1.989686323457,
    1.989318557137,
    1.988959780175,
    1.988609666976,
    1.988267907477,
    1.987934206239,
    1.987608281589,
    1.987289864831,
    1.986978699506,
    1.986674540704,
    1.986377154419,
    1.986086316951,
    1.985801814346,
    1.985523441867,
    1.985251003505,
    1.984984311522,
    1.984723186014,
    1.984467454508,
    1.984216951586,
    1.983971518524,
    1.983731002956,
    1.983495258563,
    1.983264144773,
    1.983037526484,
    1.982815273795,
    1.982597261765,
    1.982383370176,
    1.982173483308,
    1.981967489736,
    1.981765282132,
    1.981566757075,
    1.981371814876,
    1.981180359415,
    1.980992297976,
    1.980807541104,
    1.980626002459,
    1.980447598683,
    1.980272249273,
    1.980099876457,
    1.979930405082,
)


def summarize(samples: Sequence[float]) -> Measurement:
    """Turn repeated samples of a non-deterministic metric into a measurement with error bars.

    LLM judges vary even at temperature 0: the same triple scored three times can come back
    0.8, 1.0 and 0.6. A point estimate from one sample reports that spread as certainty, which
    is the most common measurement lie in RAG evaluation and the reason the report format
    carries ``n``, ``stdev`` and ``ci`` at all.

    One sample yields no interval rather than a zero-width one, so a ``ci-lower`` gate over it
    is INDETERMINATE instead of quietly passing. The interval is a Student-t interval on the
    sample mean and is not clamped: a bound outside the metric's range is what the samples
    support.

    Args:
        samples: One score per run of the judge. At least one.
    """
    if not samples:
        raise ValueError("summarize needs at least one sample")

    n = len(samples)
    mean = sum(samples) / n
    if n < 2:
        return Measurement(value=_round(mean), n=n, deterministic=False)

    variance = sum((sample - mean) ** 2 for sample in samples) / (n - 1)
    stdev = math.sqrt(variance)
    df = min(n - 1, len(_T_95) - 1)
    margin = _T_95[df] * stdev / math.sqrt(n)

    return Measurement(
        value=_round(mean),
        n=n,
        stdev=_round(stdev),
        ci=(_round(mean - margin), _round(mean + margin)),
        deterministic=False,
    )


@dataclass(slots=True)
class ScoreResult:
    """Aggregate metrics plus the per-query detail needed to debug one bad query."""

    metrics: dict[str, Measurement]
    per_query: dict[str, QueryMetrics]
    #: Queries present in the judgments but missing from the run.
    missing_queries: list[str]
    #: Queries with no label at or above the threshold, excluded from the averages. Recall,
    #: nDCG, MRR and AP are undefined when a query has nothing relevant to find, so scoring
    #: them as zero would quietly drag every average down.
    queries_without_positives: list[str] = field(default_factory=list)
    #: Queries whose ranking repeated a key. The metrics above already count each key once;
    #: this says so, because a correction nobody is told about is its own kind of wrong number.
    queries_with_duplicates: list[str] = field(default_factory=list)


def score(
    judgments: Sequence[Judgment],
    run: Sequence[RunEntry],
    k: int = DEFAULT_K,
    threshold: int = DEFAULT_THRESHOLD,
) -> ScoreResult:
    """Macro-average metrics over queries.

    Queries with judgments but no run entry score zero rather than being dropped; silently
    skipping them inflates every metric, which is a common and very quiet bug. Queries with no
    relevant label are excluded rather than scored zero, because there is nothing for retrieval
    to have found.

    Every metric is computed over the top ``k`` results and is named for it. ``mrr@k`` and
    ``map@k`` are reciprocal rank and average precision within that cutoff, not over an
    unbounded run: the name says so, because a number that means something other than its name
    is how a report stops being trustworthy.
    """
    by_query = relevance_by_query(judgments)
    rankings = {entry.query_id: entry.ranking for entry in run}

    per_query: dict[str, QueryMetrics] = {}
    missing: list[str] = []
    without_positives: list[str] = []
    with_duplicates: list[str] = []
    scored: list[QueryMetrics] = []

    for query_id, relevance in by_query.items():
        ranking = rankings.get(query_id)
        if ranking is None:
            missing.append(query_id)
        elif len(dedupe(ranking)) != len(ranking):
            with_duplicates.append(query_id)

        metrics_for_query = query_metrics(relevance, ranking or [], k=k, threshold=threshold)
        per_query[query_id] = metrics_for_query

        if any(grade >= threshold for grade in relevance.values()):
            scored.append(metrics_for_query)
        else:
            without_positives.append(query_id)

    # Nothing at the threshold means the averages are undefined. Emitting 0 would let an absolute
    # gate fail a build over an empty set, which is the same lie as scoring an unscored query.
    if not scored:
        return ScoreResult(
            metrics={},
            per_query=per_query,
            missing_queries=missing,
            queries_without_positives=without_positives,
            queries_with_duplicates=with_duplicates,
        )

    def mean(attribute: str) -> float:
        total: float = sum(float(getattr(m, attribute)) for m in scored)
        return total / len(scored)

    metrics = {
        f"precision@{k}": _deterministic(mean("precision")),
        f"recall@{k}": _deterministic(mean("recall")),
        f"ndcg@{k}": _deterministic(mean("ndcg")),
        f"mrr@{k}": _deterministic(mean("mrr")),
        f"map@{k}": _deterministic(mean("ap")),
        f"hit_rate@{k}": _deterministic(mean("hit_rate")),
    }
    return ScoreResult(
        metrics=metrics,
        per_query=per_query,
        missing_queries=missing,
        queries_without_positives=without_positives,
        queries_with_duplicates=with_duplicates,
    )


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
        # `n` counts the queries the numbers were computed from, so a stratum whose labels
        # are all negative reads as n=0 rather than as a stratum that scored zero.
        out[name] = StratumScore(
            n=len(result.per_query) - len(result.queries_without_positives),
            metrics=result.metrics,
        )
    return out


class WorstStratum(NamedTuple):
    """The weakest query class for a metric. A tuple, so existing unpacking still works."""

    name: str
    value: float
    n: int


def worst_stratum(per_stratum: dict[str, StratumScore], metric: str) -> WorstStratum | None:
    """Return the lowest-scoring stratum for a metric, or ``None`` when it is not reported.

    This is what a gate should watch: an average sits above its floor while one query class
    returns nothing.

    Strata with no scored query are skipped rather than treated as zero. A class whose labels
    are all below the relevance threshold has nothing for retrieval to have found, and reporting
    it as the worst class would fail a build over an empty set.
    """
    worst: WorstStratum | None = None
    for name, stratum in per_stratum.items():
        if stratum.n == 0:
            continue
        measurement = stratum.metrics.get(metric)
        if measurement is None:
            continue
        if worst is None or measurement.value < worst.value:
            worst = WorstStratum(name, measurement.value, stratum.n)
    return worst
