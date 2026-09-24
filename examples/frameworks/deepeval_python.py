"""DeepEval beside this tool: two layers, one judgment set, one report each.

Written against deepeval 2.x.

Retrieval metrics answer "did the right context come back". Judged metrics answer "did the
model use it". Neither answers the other, and running only the second is how a chunking
regression gets diagnosed as a prompt problem for a week.

    pip install deepeval retrieval-eval
    python deepeval_python.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from deepeval import evaluate
from deepeval.metrics import ContextualPrecisionMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase


def load_labels(path: str = "judgments.jsonl") -> dict[str, list[str]]:
    """The judged text for each query, from the same labels the retrieval layer uses."""
    expected: dict[str, list[str]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        label = json.loads(line)
        if label["relevance"] >= 1 and label.get("chunk_text"):
            expected.setdefault(label["query_id"], []).append(label["chunk_text"])
    return expected


def build_cases(answers: dict[str, dict]) -> list[LLMTestCase]:
    """One DeepEval case per query, carrying the retrieved context your pipeline used."""
    expected = load_labels()
    return [
        LLMTestCase(
            input=answer["query"],
            actual_output=answer["output"],
            retrieval_context=answer["contexts"],
            expected_output=answer.get("expected_output"),
            context=expected.get(query_id),
        )
        for query_id, answer in answers.items()
    ]


def retrieval_layer() -> int:
    """Run the deterministic half first. It is the cheap half, and it localizes the failure."""
    result = subprocess.run(
        [
            "retrieval-eval", "score",
            "--judgments", "judgments.jsonl",
            "--run", "hits.jsonl",
            "-k", "5",
            "--gate", "worst-stratum:recall@5:0.7",
            "--out", "retrieval-report.json",
        ],
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    # 1. Retrieval, deterministic, no model call. If this fails, stop here: a judged metric
    #    computed over context that does not contain the answer measures the wrong thing.
    if retrieval_layer() != 0:
        raise SystemExit("retrieval gate failed, see retrieval-report.json")

    # 2. Generation, judged. Sampled more than once, because the instrument is not
    #    deterministic and a single sample is a point estimate of an unknown spread.
    answers = json.loads(Path("answers.json").read_text(encoding="utf-8"))
    evaluate(
        test_cases=build_cases(answers),
        metrics=[FaithfulnessMetric(threshold=0.8), ContextualPrecisionMetric(threshold=0.7)],
    )
