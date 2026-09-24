"""RAGAS: get your golden set out, anchored to chunks that can be checked later.

Written against ragas 0.2.x.

RAGAS testsets carry `reference_contexts` as raw text. That is enough to judge an answer and
not enough to survive a re-chunk: nothing in the file says which chunk the text came from, so
after the next chunking change no tool can tell you whether the set still describes the corpus.

This maps each reference context back onto the live corpus by content hash, which turns a
RAGAS testset into a judgment set that `drift` can check.

    pip install ragas retrieval-eval
    python ragas_export.py
    retrieval-eval validate --judgments judgments.jsonl
"""

from __future__ import annotations

import json
from pathlib import Path

from ragas.testset import TestsetGenerator  # noqa: F401  (shown for context, unused below)
from retrieval_eval import normalize, text_sha


def load_corpus(path: str = "corpus.json") -> dict[str, dict]:
    """Index the live corpus by the hash of its normalized text."""
    corpus = json.loads(Path(path).read_text(encoding="utf-8"))
    return {chunk.get("text_sha") or text_sha(chunk["text"]): chunk for chunk in corpus["chunks"]}


def export(testset, path: str = "judgments.jsonl", model: str = "gpt-4o-mini") -> tuple[int, int]:
    """Write one judgment per reference context that exists in the corpus.

    Returns (written, unmatched). Unmatched contexts are the interesting number: they are
    passages RAGAS synthesized against a corpus state you no longer have, and no amount of
    string similarity makes them trustworthy, so they are reported rather than guessed at.
    """
    by_hash = load_corpus()
    written = unmatched = 0

    with Path(path).open("w", encoding="utf-8") as out:
        for index, sample in enumerate(testset.samples, start=1):
            query_id = f"q{index:03d}"
            for context in sample.eval_sample.reference_contexts or []:
                chunk = by_hash.get(text_sha(normalize(context)))
                if chunk is None:
                    unmatched += 1
                    continue
                out.write(
                    json.dumps(
                        {
                            "query_id": query_id,
                            "query": sample.eval_sample.user_input,
                            "doc_uri": chunk["doc_uri"],
                            "chunk_id": chunk["chunk_id"],
                            "text_sha": chunk["text_sha"],
                            "chunk_text": chunk["text"],
                            "relevance": 2,
                            # Provenance is not decoration. A set that cannot distinguish
                            # synthetic labels from human ones cannot measure its own judge.
                            "labeled_by": f"synthetic:{model}",
                            "stratum": sample.eval_sample.metadata.get("theme", "unstratified"),
                        }
                    )
                    + "\n"
                )
                written += 1

    return written, unmatched


if __name__ == "__main__":
    # Generate with RAGAS as you normally would, then:
    #   written, unmatched = export(testset)
    #   print(f"{written} labels written, {unmatched} contexts had no match in the live corpus")
    #
    # Then keep the set honest over time:
    #   retrieval-eval validate --judgments judgments.jsonl
    #   retrieval-eval drift    --judgments judgments.jsonl --corpus corpus.json
    #
    # `validate` will warn that every label is synthetic, which is correct and the reason to
    # label a human subset before trusting any of it.
    print(__doc__)
