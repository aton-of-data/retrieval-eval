"""Which of your labels are still true?

No other evaluation tool answers this. Teams change a chunker, the metric moves, and they
credit the change, when part of the movement is their labels quietly decaying underneath.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from .identity import normalize, text_sha
from .models import (
    Corpus,
    CorpusChunk,
    DriftFinding,
    DriftResult,
    DriftStatus,
    DriftSummary,
    Judgment,
)


@dataclass(slots=True)
class _Index:
    by_chunk_id: dict[str, CorpusChunk] = field(default_factory=dict)
    by_text_sha: dict[str, list[CorpusChunk]] = field(default_factory=dict)
    by_doc: dict[str, list[CorpusChunk]] = field(default_factory=dict)


def _build_index(corpus: Corpus) -> _Index:
    index = _Index()
    for chunk in corpus.chunks:
        index.by_chunk_id[chunk.chunk_id] = chunk

        sha = chunk.text_sha or (text_sha(chunk.text) if chunk.text is not None else None)
        if sha:
            index.by_text_sha.setdefault(sha, []).append(chunk)

        index.by_doc.setdefault(chunk.doc_uri, []).append(chunk)

    for chunks in index.by_doc.values():
        chunks.sort(key=lambda c: c.ordinal if c.ordinal is not None else 0)
    return index


def _find_split(labeled_text: str, doc_chunks: Sequence[CorpusChunk]) -> list[CorpusChunk] | None:
    """Live chunks the labeled text now spans: a coarse label broken into finer chunks.

    Two or more live chunks being substrings of the labeled text is what a re-chunk that split a
    paragraph looks like. A single match is left to exact re-anchoring or to :func:`_find_merged`.
    """
    haystack = normalize(labeled_text)
    if not haystack:
        return None

    covering = [
        chunk
        for chunk in doc_chunks
        if chunk.text is not None
        and normalize(chunk.text) != ""
        and normalize(chunk.text) in haystack
    ]
    return covering if len(covering) >= 2 else None


def _find_merged(labeled_text: str, doc_chunks: Sequence[CorpusChunk]) -> CorpusChunk | None:
    """The live chunk now containing the labeled text: a fine label absorbed into a coarser one.

    The mirror image of a split, and at least as common: raising ``chunk_size`` merges
    paragraphs. The label stays sound, because a chunk containing text a human judged relevant
    still contains the answer, so it re-anchors rather than needing re-judgment. Reported
    separately from an exact match because the new chunk carries extra material.

    When several live chunks contain the text, the shortest wins: it is the tightest evidence.
    """
    needle = normalize(labeled_text)
    if not needle:
        return None

    containing = [
        chunk for chunk in doc_chunks if chunk.text is not None and needle in normalize(chunk.text)
    ]
    if not containing:
        return None
    return min(containing, key=lambda chunk: len(normalize(chunk.text or "")))


def drift(
    judgments: Sequence[Judgment],
    corpus: Corpus,
    corpus_fingerprint: str | None = None,
) -> DriftResult:
    """Classify every judgment against a live corpus.

    Statuses:
        ``VALID``          the labeled chunk_id is still present.
        ``RE_ANCHORABLE``  the id is stale, but the exact text is still a live chunk.
        ``MERGED``         the text was absorbed into a coarser chunk; re-anchors safely.
        ``SPLIT``          the labeled text now spans two or more chunks; needs re-judgment.
        ``ORPHANED``       the text or its document is gone.
    """
    index = _build_index(corpus)
    findings: list[DriftFinding] = []
    fingerprints: set[str] = set()

    for judgment in judgments:
        if judgment.corpus_fingerprint:
            fingerprints.add(judgment.corpus_fingerprint)

        doc_chunks = index.by_doc.get(judgment.doc_uri, [])

        # Document-level labels have no chunk to track; valid while the document exists.
        if judgment.chunk_id is None:
            findings.append(
                DriftFinding(
                    query_id=judgment.query_id,
                    doc_uri=judgment.doc_uri,
                    status="VALID" if doc_chunks else "ORPHANED",
                )
            )
            continue

        if judgment.chunk_id in index.by_chunk_id:
            findings.append(
                DriftFinding(
                    query_id=judgment.query_id,
                    doc_uri=judgment.doc_uri,
                    chunk_id=judgment.chunk_id,
                    status="VALID",
                )
            )
            continue

        # Exact text match first: cheapest and most precise.
        sha = judgment.text_sha or (
            text_sha(judgment.chunk_text) if judgment.chunk_text is not None else None
        )
        if sha:
            matches = index.by_text_sha.get(sha, [])
            same_doc = [c for c in matches if c.doc_uri == judgment.doc_uri]
            target = same_doc[0] if same_doc else (matches[0] if matches else None)
            if target is not None:
                findings.append(
                    DriftFinding(
                        query_id=judgment.query_id,
                        doc_uri=judgment.doc_uri,
                        chunk_id=judgment.chunk_id,
                        status="RE_ANCHORABLE",
                        reanchor_to=target.chunk_id,
                    )
                )
                continue

        # Then the two re-chunk shapes. Without these, a label whose text plainly still exists
        # would be reported ORPHANED, which is wrong in the way that erodes trust.
        if judgment.chunk_text is not None:
            split = _find_split(judgment.chunk_text, doc_chunks)
            if split:
                findings.append(
                    DriftFinding(
                        query_id=judgment.query_id,
                        doc_uri=judgment.doc_uri,
                        chunk_id=judgment.chunk_id,
                        status="SPLIT",
                        split_into=[chunk.chunk_id for chunk in split],
                    )
                )
                continue

            merged = _find_merged(judgment.chunk_text, doc_chunks)
            if merged is not None:
                findings.append(
                    DriftFinding(
                        query_id=judgment.query_id,
                        doc_uri=judgment.doc_uri,
                        chunk_id=judgment.chunk_id,
                        status="MERGED",
                        reanchor_to=merged.chunk_id,
                    )
                )
                continue

        findings.append(
            DriftFinding(
                query_id=judgment.query_id,
                doc_uri=judgment.doc_uri,
                chunk_id=judgment.chunk_id,
                status="ORPHANED",
            )
        )

    def count(status: DriftStatus) -> int:
        return sum(1 for finding in findings if finding.status == status)

    valid = count("VALID")
    total = len(findings)

    return DriftResult(
        findings=findings,
        summary=DriftSummary(
            valid=valid,
            re_anchorable=count("RE_ANCHORABLE"),
            merged=count("MERGED"),
            split=count("SPLIT"),
            orphaned=count("ORPHANED"),
            invalid_ratio=0.0 if total == 0 else round((total - valid) / total, 12),
        ),
        judgments_fingerprint=next(iter(fingerprints)) if len(fingerprints) == 1 else None,
        corpus_fingerprint=corpus.corpus_fingerprint or corpus_fingerprint,
    )


@dataclass(slots=True)
class FixResult:
    """The outcome of re-anchoring."""

    judgments: list[Judgment]
    reanchored: int
    #: Labels left untouched because they need a human: SPLIT and ORPHANED.
    needs_review: list[DriftFinding]


def fix(judgments: Sequence[Judgment], result: DriftResult) -> FixResult:
    """Re-anchor recoverable labels onto their new chunk_ids and stamp the new fingerprint.

    RE_ANCHORABLE and MERGED are recoverable: in both cases the text a human judged is still
    there. SPLIT and ORPHANED are deliberately left alone, because guessing at them would
    silently fabricate ground truth, the exact failure this tool exists to expose.
    """
    by_key = {(f.query_id, f.chunk_id or ""): f for f in result.findings}

    out: list[Judgment] = []
    reanchored = 0
    needs_review: list[DriftFinding] = []

    for judgment in judgments:
        finding = by_key.get((judgment.query_id, judgment.chunk_id or ""))
        if finding is None:
            out.append(judgment)
            continue

        if finding.status in ("RE_ANCHORABLE", "MERGED") and finding.reanchor_to:
            reanchored += 1
            out.append(
                replace(
                    judgment,
                    chunk_id=finding.reanchor_to,
                    corpus_fingerprint=result.corpus_fingerprint or judgment.corpus_fingerprint,
                )
            )
            continue

        if finding.status in ("SPLIT", "ORPHANED"):
            needs_review.append(finding)
            out.append(judgment)
            continue

        if finding.status == "VALID" and result.corpus_fingerprint:
            out.append(replace(judgment, corpus_fingerprint=result.corpus_fingerprint))
            continue

        out.append(judgment)

    return FixResult(judgments=out, reanchored=reanchored, needs_review=needs_review)
