"""Evaluation inside your own test suite, with no CLI involved.

Run: python3 harness.py

The CLI is a thin layer over these functions. When evaluation belongs inside pytest, a nightly
job or a service, call them directly: same numbers, same guarantees, no subprocess.

Reads the support-bot example's data so the numbers are comparable with what `retrieval-eval
score` prints for the same files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import retrieval_eval  # noqa: F401
except ModuleNotFoundError:
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT / "python" / "retrieval-eval" / "src"))

from retrieval_eval import (
    build_report,
    drift,
    evaluate_gates,
    from_trec_run,
    parse_corpus,
    parse_gate,
    parse_judgments,
    parse_run,
    query_metrics,
    relevance_by_query,
    score_by_stratum,
    serialize_judgments,
    summarize,
    to_qrels,
    to_trec_run,
    validate,
    worst_stratum,
)

DATA = Path(__file__).resolve().parent.parent / "support-bot"
K = 3


def read(name: str) -> str:
    return (DATA / name).read_text(encoding="utf-8")


def main() -> None:
    """Everything the CLI does, and two things it cannot."""
    judgments = parse_judgments(read("judgments.jsonl"))
    run = parse_run(read("hits.jsonl"))
    corpus = parse_corpus(read("corpus.json"))

    print("\n  1. Refuse to measure with a judgment set you have not checked.\n")
    result = validate(judgments)
    print(f"     {result.labels} labels, {result.queries} queries, ok={str(result.ok).lower()}")
    for issue in result.issues[:2]:
        print(f"     {issue.severity}: [{issue.code}]")
    if not result.ok:
        raise SystemExit("judgment set has errors")

    print("\n  2. Per-query metrics: which queries are actually failing, not just the mean.\n")
    relevance = relevance_by_query(judgments)
    rankings = {entry.query_id: entry.ranking for entry in run}
    per_query = {
        query_id: query_metrics(grades, rankings.get(query_id, []), k=K)
        for query_id, grades in relevance.items()
    }
    worst_queries = sorted(per_query.items(), key=lambda row: row[1].recall)[:3]
    for query_id, metrics in worst_queries:
        query = next(j.query for j in judgments if j.query_id == query_id and j.query)
        print(f"     {query_id}  recall={metrics.recall:.2f}  {query}")

    print("\n  3. Per-stratum, and the class a gate should watch.\n")
    per_stratum = score_by_stratum(judgments, run, k=K)
    worst = worst_stratum(per_stratum, f"recall@{K}")
    assert worst is not None
    for name, stratum in sorted(per_stratum.items()):
        mark = "  <- worst" if name == worst.name else ""
        value = stratum.metrics[f"recall@{K}"].value
        print(f"     {name.ljust(10)} recall@{K}={value:.4f}  n={stratum.n}{mark}")

    print("\n  4. A report, a judged metric beside the deterministic ones, and gates.\n")
    report = build_report(judgments, run, k=K, corpus=corpus, drift_result=drift(judgments, corpus))
    report.metrics["faithfulness"] = summarize([0.91, 0.88, 0.95, 0.9])
    expressions = (
        f"recall@{K}:0.7",
        f"worst-stratum:recall@{K}:0.6",
        "faithfulness:ci-lower:0.8",
    )
    verdict = evaluate_gates(report, [parse_gate(expression) for expression in expressions])
    report.verdict.status = verdict.status
    report.verdict.gates = verdict.results
    for gate in verdict.results:
        print(f"     {gate.status.ljust(13)} {gate.expression}")
    print(f"     verdict: {verdict.status}")

    out = Path("report.json")
    out.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    print(f"     wrote {out.name}, the same shape the CLI writes with --out")

    print("\n  5. Hand the same labels to the thirty-year-old tooling, and read its run back.\n")
    qrels = to_qrels(judgments)
    trec_run = to_trec_run(run)
    print(f"     qrels line   {qrels.splitlines()[0]}")
    print(f"     run line     {trec_run.splitlines()[0]}")
    recovered = from_trec_run(trec_run)
    preserved = str(recovered[0].ranking == run[0].ranking).lower()
    print(f"     read back    {len(recovered)} queries, ranking order preserved: {preserved}")

    print("\n  6. Write the labels back out, canonically.\n")
    canonical = serialize_judgments(judgments)
    print(f"     {len(canonical.splitlines())} lines, byte-identical in either implementation")
    print(f"     first: {canonical.splitlines()[0][:72]}...")

    print(
        "\n  The CLI does 1, 3, 4 and 5 for you. Steps 2 and 6 are why the library is public:\n"
        "  per-query detail belongs in your own reporting, and a canonical writer lets you\n"
        "  generate and repair judgment files from your own tooling.\n"
    )
    out.unlink()


if __name__ == "__main__":
    main()
