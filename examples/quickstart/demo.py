"""Watch a golden set decay when you change your chunker.

Run: python3 demo.py

Works from a fresh clone with nothing installed: if ``retrieval-eval`` is not on the path, the
in-repo source is used instead. Zero runtime dependencies is what makes that possible.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import retrieval_eval  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(
        0,
        str(Path(__file__).resolve().parents[2] / "python" / "retrieval-eval" / "src"),
    )

from retrieval_eval import (
    Corpus,
    CorpusChunk,
    Judgment,
    RunEntry,
    chunk_id,
    drift,
    fix,
    score,
    text_sha,
)

# -- a tiny corpus ----------------------------------------------------------------
DOCS = [
    (
        "wiki://refunds",
        "r3",
        [
            "Annual plans may be refunded within 30 days of renewal.",
            "Monthly plans are non-refundable after the billing date.",
            "Enterprise refunds are negotiated per contract.",
        ],
    ),
    (
        "wiki://billing",
        "r1",
        [
            "Invoices are issued on the first business day of each month.",
            "Failed payments retry three times over six days.",
        ],
    ),
]


def chunk_corpus(size: int, fingerprint: str) -> Corpus:
    """Stand in for a real chunker.

    ``size`` is how many paragraphs go in a chunk, which is enough to reproduce the only thing
    that matters here: the same text landing in different chunks under a different config.
    """
    chunks: list[CorpusChunk] = []
    for uri, revision, paragraphs in DOCS:
        for ordinal, start in enumerate(range(0, len(paragraphs), size)):
            text = "\n\n".join(paragraphs[start : start + size])
            chunks.append(
                CorpusChunk(
                    chunk_id=chunk_id(uri, revision, ordinal, text, fingerprint),
                    doc_uri=uri,
                    doc_revision=revision,
                    ordinal=ordinal,
                    text=text,
                    text_sha=text_sha(text),
                )
            )
    return Corpus(
        chunks=chunks, corpus_fingerprint=fingerprint, chunker_fingerprint=fingerprint
    )


# -- 1. chunk at "512 tokens": one paragraph per chunk -----------------------------
before = chunk_corpus(1, "recursive/512")


def label(
    query_id: str, query: str, chunk: CorpusChunk, relevance: int, stratum: str
) -> Judgment:
    """Record a judgment the way a human labeler would."""
    return Judgment(
        query_id=query_id,
        query=query,
        doc_uri=chunk.doc_uri,
        chunk_id=chunk.chunk_id,
        text_sha=chunk.text_sha,
        chunk_text=chunk.text,
        relevance=relevance,
        corpus_fingerprint=before.corpus_fingerprint,
        labeled_by="human:ana",
        stratum=stratum,
    )


# -- 2. a human labels 4 chunks as relevant ----------------------------------------
judgments = [
    label("q1", "annual plan refund window", before.chunks[0], 2, "refunds"),
    label("q2", "are monthly plans refundable", before.chunks[1], 2, "refunds"),
    label("q3", "enterprise refund policy", before.chunks[2], 1, "refunds"),
    label("q4", "when are invoices issued", before.chunks[3], 2, "billing"),
]


def perfect_run(corpus: Corpus) -> list[RunEntry]:
    """A flawless retriever: for every query it returns the live chunk holding the answer.

    Modelling retrieval as perfect is the point of the demo. Any metric movement below cannot
    be the retriever's fault, because the retriever never makes a mistake.
    """
    entries: list[RunEntry] = []
    for judgment in judgments:
        wanted = (judgment.chunk_text or "").strip()
        hit = next((c for c in corpus.chunks if wanted in (c.text or "")), None)
        entries.append(
            RunEntry(query_id=judgment.query_id, ranking=[hit.chunk_id] if hit else [])
        )
    return entries


baseline = score(judgments, perfect_run(before), k=3).metrics["recall@3"].value
print(f"\n  1. chunked @ {before.chunker_fingerprint}")
print(f"     recall@3 = {baseline:.4f}   <- your baseline, retrieval is perfect\n")

# -- 3. re-chunk at "384 tokens": two paragraphs per chunk --------------------------
after = chunk_corpus(2, "recursive/384")
print(f"  2. re-chunked @ {after.chunker_fingerprint}")
print("     the corpus text is byte-for-byte identical. Only the chunking changed.")
print("     retrieval is still perfect: it returns the chunk holding the answer.\n")

stale = score(judgments, perfect_run(after), k=3).metrics["recall@3"].value
print(
    f"     recall@3 = {stale:.4f}   <- a {baseline - stale:.2f} collapse, and the retriever"
)
print("                            did nothing wrong. Your labels point at ids")
print("                            that no longer exist.")

# -- 4. ask what actually happened -------------------------------------------------
result = drift(judgments, after)
print("\n  3. drift against the live corpus:")
print(f"     VALID          {result.summary.valid}")
print(f"     RE_ANCHORABLE  {result.summary.re_anchorable}")
print(f"     MERGED         {result.summary.merged}")
print(f"     SPLIT          {result.summary.split}")
print(f"     ORPHANED       {result.summary.orphaned}")
print(
    f"     -> {result.summary.invalid_ratio * 100:.0f}% of your labels "
    "no longer match the corpus\n"
)

for finding in result.findings:
    if finding.reanchor_to:
        detail = f"-> {finding.reanchor_to[:14]}..."
    elif finding.split_into:
        detail = f"-> spans {len(finding.split_into)} chunks"
    else:
        detail = ""
    print(f"     {finding.query_id}  {finding.status:<14} {detail}")

# -- 5. recover what can be recovered, refuse to invent the rest --------------------
fixed = fix(judgments, result)
print(f"\n  4. --fix re-anchored {fixed.reanchored} label(s).")
print(
    f"     {len(fixed.needs_review)} still need a human; "
    "SPLIT and ORPHANED are never guessed."
)

judgments = fixed.judgments
restored = score(judgments, perfect_run(after), k=3).metrics["recall@3"].value
print(f"\n     recall@3 = {restored:.4f}   <- back where it started, because nothing")
print("                            about retrieval had changed in the first place.")
print(
    f"\n     Without step 4, you would have chased a {baseline - stale:.2f} regression"
)
print("     that never existed.\n")
