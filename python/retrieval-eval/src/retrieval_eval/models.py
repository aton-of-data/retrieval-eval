"""Core record types.

Dataclasses rather than a validation library, because zero runtime dependencies is a feature:
this package must be installable into any environment without an opinion about pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Status = Literal["PASS", "FAIL", "INDETERMINATE"]
DriftStatus = Literal["VALID", "RE_ANCHORABLE", "MERGED", "SPLIT", "ORPHANED"]

#: Fields the schema knows about. Anything else round-trips through ``extra``.
_KNOWN_JUDGMENT_FIELDS = frozenset(
    {
        "query_id",
        "query",
        "doc_uri",
        "chunk_id",
        "text_sha",
        "chunk_text",
        "relevance",
        "corpus_fingerprint",
        "labeled_by",
        "labeled_at",
        "stratum",
        "notes",
    }
)


@dataclass(slots=True)
class Judgment:
    """One relevance judgment. A judgments file is JSONL: one of these per line."""

    query_id: str
    doc_uri: str
    relevance: int
    query: str | None = None
    chunk_id: str | None = None
    text_sha: str | None = None
    chunk_text: str | None = None
    corpus_fingerprint: str | None = None
    labeled_by: str | None = None
    labeled_at: str | None = None
    stratum: str | None = None
    notes: str | None = None
    #: Unknown fields are preserved, never rejected.
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """The key used to match this judgment against a ranking entry."""
        return self.chunk_id if self.chunk_id is not None else self.doc_uri

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> Judgment:
        """Build a judgment from a parsed JSON object, keeping unknown fields."""
        known = {k: v for k, v in row.items() if k in _KNOWN_JUDGMENT_FIELDS}
        extra = {k: v for k, v in row.items() if k not in _KNOWN_JUDGMENT_FIELDS}
        return cls(**known, extra=extra)

    def to_dict(self) -> dict[str, Any]:
        """Serialize, omitting unset optional fields and re-inlining unknown ones."""
        out: dict[str, Any] = {"query_id": self.query_id}
        if self.query is not None:
            out["query"] = self.query
        out["doc_uri"] = self.doc_uri
        for name in ("chunk_id", "text_sha", "chunk_text"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        out["relevance"] = self.relevance
        for name in ("corpus_fingerprint", "labeled_by", "labeled_at", "stratum", "notes"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        out.update(self.extra)
        return out


@dataclass(slots=True)
class RunEntry:
    """One query's ranked result: chunk_ids, or doc_uris for document-level evaluation."""

    query_id: str
    ranking: list[str]


@dataclass(slots=True)
class CorpusChunk:
    """A chunk as it currently exists in the live index."""

    chunk_id: str
    doc_uri: str
    doc_revision: str | None = None
    ordinal: int | None = None
    text: str | None = None
    text_sha: str | None = None


@dataclass(slots=True)
class Corpus:
    """A snapshot of the live index, enough to judge label validity against."""

    chunks: list[CorpusChunk]
    corpus_fingerprint: str | None = None
    chunker_fingerprint: str | None = None


@dataclass(slots=True)
class Measurement:
    """A metric value plus the honesty fields a non-deterministic metric requires."""

    value: float
    n: int | None = None
    stdev: float | None = None
    #: Required for any LLM-judged metric: a one-sample point estimate is a measurement lie.
    ci: tuple[float, float] | None = None
    deterministic: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize, omitting unset fields."""
        out: dict[str, Any] = {"value": self.value}
        if self.n is not None:
            out["n"] = self.n
        if self.stdev is not None:
            out["stdev"] = self.stdev
        if self.ci is not None:
            out["ci"] = list(self.ci)
        if self.deterministic is not None:
            out["deterministic"] = self.deterministic
        return out


@dataclass(slots=True)
class QueryMetrics:
    """Per-query metric values."""

    precision: float
    recall: float
    ndcg: float
    mrr: float
    ap: float
    hit_rate: float


@dataclass(slots=True)
class DriftFinding:
    """What happened to one label when the corpus moved underneath it."""

    query_id: str
    doc_uri: str
    status: DriftStatus
    chunk_id: str | None = None
    #: The live chunk_id this label should move to, when RE_ANCHORABLE or MERGED.
    reanchor_to: str | None = None
    #: The live chunk_ids the labeled text now spans, when SPLIT.
    split_into: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize, omitting unset fields."""
        out: dict[str, Any] = {
            "query_id": self.query_id,
            "doc_uri": self.doc_uri,
            "status": self.status,
        }
        if self.chunk_id is not None:
            out["chunk_id"] = self.chunk_id
        if self.reanchor_to is not None:
            out["reanchor_to"] = self.reanchor_to
        if self.split_into is not None:
            out["split_into"] = self.split_into
        return out


@dataclass(slots=True)
class DriftSummary:
    """Counts by status, plus the headline number."""

    valid: int
    re_anchorable: int
    merged: int
    split: int
    orphaned: int
    #: Share of labels that are not straightforwardly VALID.
    invalid_ratio: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the spec's field names."""
        return {
            "valid": self.valid,
            "re_anchorable": self.re_anchorable,
            "merged": self.merged,
            "split": self.split,
            "orphaned": self.orphaned,
            "invalid_ratio": self.invalid_ratio,
        }


@dataclass(slots=True)
class DriftResult:
    """The full answer to "which of my labels are still true?"."""

    findings: list[DriftFinding]
    summary: DriftSummary
    judgments_fingerprint: str | None
    corpus_fingerprint: str | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for ``--json`` output."""
        return {
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary.to_dict(),
            "judgments_fingerprint": self.judgments_fingerprint,
            "corpus_fingerprint": self.corpus_fingerprint,
        }
