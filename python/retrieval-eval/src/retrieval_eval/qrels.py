"""TREC qrels interoperability.

``query_id iteration doc_id relevance``, whitespace separated. Thirty years of tooling reads
this (trec_eval, ir_measures, BEIR, ir_datasets), which is why judgments are a strict
superset of it rather than a new idea.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .models import Judgment, RunEntry


def to_qrels(judgments: Iterable[Judgment]) -> str:
    """Emit the TREC qrels format."""
    lines = [f"{j.query_id} 0 {j.key} {j.relevance}" for j in judgments]
    return "\n".join(lines) + "\n"


def from_qrels(
    content: str,
    as_chunk_ids: bool = False,
    corpus_fingerprint: str | None = None,
    labeled_by: str | None = None,
) -> list[Judgment]:
    """Parse qrels into judgments.

    Both shapes that exist in the wild are accepted::

        query_id iteration doc_id relevance   the TREC form, 4 columns
        query-id  corpus-id  score            the BEIR form, 3 columns with a header row

    Accepting only the first means not being able to read BEIR or ``ir_datasets`` exports,
    which is most of the reason to speak qrels at all.

    Args:
        content: The qrels file contents.
        as_chunk_ids: Treat the qrels ``doc_id`` as a chunk_id rather than a doc_uri.
        corpus_fingerprint: Stamped onto every judgment when given.
        labeled_by: Provenance stamped onto every judgment when given.
    """
    out: list[Judgment] = []
    for number, raw in enumerate(content.split("\n"), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            raise ValueError(f"qrels:{number}: expected 3 or 4 fields, got {len(parts)}")
        query_id = parts[0]
        doc_id = parts[2] if len(parts) >= 4 else parts[1]
        relevance = parts[3] if len(parts) >= 4 else parts[2]
        try:
            parsed = int(relevance)
        except ValueError as error:
            # The BEIR header, `query-id corpus-id score`, is a row only by accident of format.
            if not out and re.fullmatch(r"query[-_ ]?id", query_id, re.IGNORECASE):
                continue
            raise ValueError(
                f"qrels:{number}: relevance '{relevance}' is not an integer"
            ) from error

        out.append(
            Judgment(
                query_id=query_id,
                doc_uri=doc_id,
                # Negative relevance appears in some TREC collections; clamp to the schema.
                relevance=max(0, parsed),
                chunk_id=doc_id if as_chunk_ids else None,
                corpus_fingerprint=corpus_fingerprint,
                labeled_by=labeled_by,
            )
        )
    return out


def to_trec_run(run: Sequence[RunEntry], run_name: str = "retrieval-eval") -> str:
    """Emit the TREC run format: ``query_id iteration doc_id rank score run_name``."""
    lines: list[str] = []
    for entry in run:
        total = len(entry.ranking)
        for index, doc_id in enumerate(entry.ranking):
            score = f"{total - index:.4f}"
            lines.append(f"{entry.query_id} Q0 {doc_id} {index + 1} {score} {run_name}")
    return "\n".join(lines) + "\n"


def from_trec_run(content: str) -> list[RunEntry]:
    """Parse the TREC run format back into run entries."""
    by_query: dict[str, list[tuple[int, str]]] = {}
    for raw in content.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        query_id, doc_id, rank = parts[0], parts[2], parts[3]
        by_query.setdefault(query_id, []).append((int(rank), doc_id))

    return [
        RunEntry(query_id=query_id, ranking=[doc for _, doc in sorted(rows)])
        for query_id, rows in by_query.items()
    ]
