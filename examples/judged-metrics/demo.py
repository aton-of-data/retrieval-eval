"""Gate a judged metric without pretending its instrument is deterministic.

Run: python3 demo.py

Works from a fresh clone with nothing installed: if ``retrieval-eval`` is not on the path, the
in-repo source is used instead.

No model is called here. The judge's scores are a fixed table, because the point is what you do
with repeated samples, not how you obtain them.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import retrieval_eval  # noqa: F401
except ModuleNotFoundError:
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT / "python" / "retrieval-eval" / "src"))

from retrieval_eval import (
    Judgment,
    RunEntry,
    build_report,
    evaluate_gates,
    parse_gate,
    summarize,
)

# One human-labeled query per row, and the retrieval that answered it.
JUDGMENTS = [
    Judgment(query_id="q1", doc_uri="kb://refunds", chunk_id=None, relevance=2, stratum="billing"),
    Judgment(
        query_id="q2", doc_uri="kb://delivery", chunk_id=None, relevance=2, stratum="shipping"
    ),
]
RUN = [
    RunEntry(query_id="q1", ranking=["kb://refunds", "kb://delivery"]),
    RunEntry(query_id="q2", ranking=["kb://delivery", "kb://refunds"]),
]

# The same (question, context, answer) triple, scored five times by the same judge at
# temperature 0. This is not a contrived spread: tokenization, batching and backend routing
# all leak into the score, and 0.6 to 1.0 across five runs is an ordinary result.
FAITHFULNESS_SAMPLES = [0.8, 1.0, 0.6, 0.9, 0.7]

GATES = ["recall@2:0.9", "faithfulness:ci-lower:0.8"]


def main() -> None:
    """Score retrieval, attach a judged metric with error bars, then gate on both."""
    report = build_report(JUDGMENTS, RUN, k=2)

    print("\n  1. Retrieval, deterministic. Same inputs, same bytes, every run.\n")
    for name, measurement in report.metrics.items():
        print(f"     {name.ljust(14)} {measurement.value:.4f}   n={measurement.n} deterministic")

    print("\n  2. The judge, sampled once. The number a dashboard would show.\n")
    single = summarize(FAITHFULNESS_SAMPLES[:1])
    print(f"     faithfulness   {single.value:.4f}   n=1, no interval")

    report.metrics["faithfulness"] = single
    verdict = evaluate_gates(report, [parse_gate(g) for g in GATES])
    print(f"\n     {verdict.status}")
    for reason in verdict.reasons:
        print(f"     -> {reason}")

    print("\n  3. The same judge, sampled five times. Same model, same prompt, same temperature.\n")
    print(f"     samples        {', '.join(f'{s:.2f}' for s in FAITHFULNESS_SAMPLES)}")
    sampled = summarize(FAITHFULNESS_SAMPLES)
    assert sampled.ci is not None
    print(f"     faithfulness   {sampled.value:.4f}   n={sampled.n}  stdev={sampled.stdev:.4f}")
    print(f"     95% interval   [{sampled.ci[0]:.4f}, {sampled.ci[1]:.4f}]")

    report.metrics["faithfulness"] = sampled
    verdict = evaluate_gates(report, [parse_gate(g) for g in GATES])
    print(f"\n     {verdict.status}")
    for reason in verdict.reasons:
        print(f"     -> {reason}")

    print(
        "\n  One sample said 0.8000, which clears a 0.8 floor exactly.\n"
        "  Five samples of the same judge, same prompt, same temperature, put the\n"
        "  truth somewhere in [0.6037, 0.9963]. The floor is inside that interval,\n"
        "  so the honest answer is that this build cannot be judged on this metric yet.\n"
    )


if __name__ == "__main__":
    main()
