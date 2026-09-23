"""Reading, writing and sanity-checking judgment files."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from .models import Corpus, CorpusChunk, Judgment, RunEntry

CHUNK_ID_RE = re.compile(r"^c1:[0-9a-f]{32}$")
TEXT_SHA_RE = re.compile(r"^t1:[0-9a-f]{32}$")

Severity = Literal["error", "warning"]


def _parse_jsonl(content: str, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(content.split("\n"), start=1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"{label}:{number}: invalid JSON, {error}") from error
    return rows


def parse_judgments(content: str, label: str = "judgments") -> list[Judgment]:
    """Parse a judgments JSONL file, failing loudly on the three required fields."""
    out: list[Judgment] = []
    for number, row in enumerate(_parse_jsonl(content, label), start=1):
        if not isinstance(row.get("query_id"), str) or not row["query_id"]:
            raise ValueError(f"{label}:{number}: missing query_id")
        if not isinstance(row.get("doc_uri"), str) or not row["doc_uri"]:
            raise ValueError(f"{label}:{number}: missing doc_uri")
        relevance = row.get("relevance")
        if not isinstance(relevance, int) or isinstance(relevance, bool) or relevance < 0:
            raise ValueError(f"{label}:{number}: relevance must be a non-negative integer")
        out.append(Judgment.from_dict(row))
    return out


def parse_run(content: str, label: str = "run") -> list[RunEntry]:
    """Parse a run JSONL file."""
    out: list[RunEntry] = []
    for number, row in enumerate(_parse_jsonl(content, label), start=1):
        if not isinstance(row.get("query_id"), str):
            raise ValueError(f"{label}:{number}: missing query_id")
        if not isinstance(row.get("ranking"), list):
            raise ValueError(f"{label}:{number}: ranking must be an array")
        out.append(RunEntry(query_id=row["query_id"], ranking=list(row["ranking"])))
    return out


def serialize_judgments(judgments: Iterable[Judgment]) -> str:
    """Serialize judgments back to JSONL."""
    lines = [json.dumps(j.to_dict(), ensure_ascii=False) for j in judgments]
    return "\n".join(lines) + "\n"


def parse_corpus(content: str, label: str = "corpus") -> Corpus:
    """Parse a corpus snapshot."""
    parsed = json.loads(content)
    chunks = parsed.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError(f"{label}: missing chunks array")
    return Corpus(
        chunks=[
            CorpusChunk(
                chunk_id=c["chunk_id"],
                doc_uri=c["doc_uri"],
                doc_revision=c.get("doc_revision"),
                ordinal=c.get("ordinal"),
                text=c.get("text"),
                text_sha=c.get("text_sha"),
            )
            for c in chunks
        ],
        corpus_fingerprint=parsed.get("corpus_fingerprint"),
        chunker_fingerprint=parsed.get("chunker_fingerprint"),
    )


@dataclass(slots=True)
class ValidationIssue:
    """One problem found in a judgment set."""

    severity: Severity
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize for ``--json`` output."""
        return {"severity": self.severity, "code": self.code, "message": self.message}


@dataclass(slots=True)
class ValidationResult:
    """Structural and statistical findings about a judgment set."""

    issues: list[ValidationIssue] = field(default_factory=list)
    queries: int = 0
    labels: int = 0
    human_labels: int = 0
    synthetic_labels: int = 0
    fingerprint: str | None = None
    strata: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when nothing is an error. Warnings do not fail validation."""
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for ``--json`` output."""
        return {
            "issues": [i.to_dict() for i in self.issues],
            "queries": self.queries,
            "labels": self.labels,
            "humanLabels": self.human_labels,
            "syntheticLabels": self.synthetic_labels,
            "fingerprint": self.fingerprint,
            "strata": self.strata,
            "ok": self.ok,
        }


def validate(judgments: Sequence[Judgment]) -> ValidationResult:
    """Check a judgment set for problems.

    The warnings matter as much as the errors: a set with no positives, no human labels, or a
    two-query stratum will produce confident-looking numbers that mean nothing.
    """
    result = ValidationResult(labels=len(judgments))
    queries: set[str] = set()
    fingerprints: set[str] = set()
    seen: set[tuple[str, str]] = set()
    query_text: dict[str, str] = {}
    positives = 0

    for judgment in judgments:
        queries.add(judgment.query_id)
        if judgment.relevance >= 1:
            positives += 1
        if judgment.corpus_fingerprint:
            fingerprints.add(judgment.corpus_fingerprint)
        if judgment.labeled_by:
            if judgment.labeled_by.startswith("human:"):
                result.human_labels += 1
            elif judgment.labeled_by.startswith("synthetic:"):
                result.synthetic_labels += 1

        stratum = judgment.stratum or "_unstratified"
        result.strata[stratum] = result.strata.get(stratum, 0) + 1

        key = (judgment.query_id, judgment.key)
        if key in seen:
            result.issues.append(
                ValidationIssue(
                    "error",
                    "duplicate-label",
                    f"duplicate judgment for query {judgment.query_id} and target {judgment.key}",
                )
            )
        seen.add(key)

        if judgment.query is not None:
            existing = query_text.get(judgment.query_id)
            if existing is not None and existing != judgment.query:
                result.issues.append(
                    ValidationIssue(
                        "error",
                        "inconsistent-query-text",
                        f"query {judgment.query_id} has two different query strings",
                    )
                )
            query_text[judgment.query_id] = judgment.query

        if judgment.chunk_id is not None and not CHUNK_ID_RE.match(judgment.chunk_id):
            result.issues.append(
                ValidationIssue(
                    "error",
                    "bad-chunk-id",
                    f"malformed chunk_id on query {judgment.query_id}: {judgment.chunk_id}",
                )
            )
        if judgment.text_sha is not None and not TEXT_SHA_RE.match(judgment.text_sha):
            result.issues.append(
                ValidationIssue(
                    "error",
                    "bad-text-sha",
                    f"malformed text_sha on query {judgment.query_id}: {judgment.text_sha}",
                )
            )

    for query_id in sorted(queries):
        if query_id not in query_text:
            result.issues.append(
                ValidationIssue(
                    "warning",
                    "missing-query-text",
                    f"query {query_id} has no query text on any row",
                )
            )

    if not judgments:
        result.issues.append(ValidationIssue("error", "empty", "no judgments"))
    if positives == 0 and judgments:
        result.issues.append(
            ValidationIssue(
                "error",
                "no-positives",
                "no judgment has relevance >= 1, so recall is undefined for every query",
            )
        )
    if result.human_labels == 0 and result.synthetic_labels > 0:
        result.issues.append(
            ValidationIssue(
                "warning",
                "no-human-labels",
                "every label is synthetic. Without human labels you cannot measure judge "
                "calibration, and synthetic labels quietly become ground truth",
            )
        )
    if len(fingerprints) > 1:
        result.issues.append(
            ValidationIssue(
                "warning",
                "mixed-fingerprints",
                f"judgments span {len(fingerprints)} corpus fingerprints; "
                "run 'drift' before trusting any metric",
            )
        )
    for name, count in sorted(result.strata.items()):
        if name != "_unstratified" and count < 5:
            result.issues.append(
                ValidationIssue(
                    "warning",
                    "thin-stratum",
                    f"stratum '{name}' has only {count} labels, too few to gate on",
                )
            )

    with_chunk_id = sum(1 for j in judgments if j.chunk_id is not None)
    if 0 < with_chunk_id < len(judgments):
        result.issues.append(
            ValidationIssue(
                "warning",
                "mixed-granularity",
                f"{with_chunk_id}/{len(judgments)} labels have chunk_id; "
                "the rest are document-level",
            )
        )
    if with_chunk_id == 0 and judgments:
        result.issues.append(
            ValidationIssue(
                "warning",
                "no-chunk-ids",
                "no label has a chunk_id, so drift can only work at document granularity. "
                "See spec/chunk-id.md",
            )
        )

    result.queries = len(queries)
    result.fingerprint = next(iter(fingerprints)) if len(fingerprints) == 1 else None
    return result
