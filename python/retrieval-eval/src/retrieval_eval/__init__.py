"""retrieval-eval: portable relevance judgments, deterministic retrieval metrics, and drift.

Zero runtime dependencies. No API key. Nothing here calls a model.

The Python and TypeScript implementations are peers, not ports: both prove themselves against
the same fixtures in ``spec/fixtures``.

    >>> from retrieval_eval import drift, parse_corpus, parse_judgments
    >>> judgments = parse_judgments(open("judgments.jsonl").read())
    >>> corpus = parse_corpus(open("corpus.json").read())
    >>> drift(judgments, corpus).summary.invalid_ratio
    0.75
"""

from __future__ import annotations

from .drift import FixResult, drift, fix
from .gate import Gate, GateEvaluation, GateResult, evaluate_gates, parse_gate
from .identity import chunk_id, normalize, text_sha
from .judgments import (
    ValidationIssue,
    ValidationResult,
    parse_corpus,
    parse_judgments,
    parse_run,
    serialize_judgments,
    validate,
)
from .metrics import (
    ScoreResult,
    StratumScore,
    query_metrics,
    relevance_by_query,
    score,
    score_by_stratum,
    worst_stratum,
)
from .models import (
    Corpus,
    CorpusChunk,
    DriftFinding,
    DriftResult,
    DriftSummary,
    Judgment,
    Measurement,
    QueryMetrics,
    RunEntry,
)
from .qrels import from_qrels, from_trec_run, to_qrels, to_trec_run
from .report import SPEC_VERSION, TOOL_NAME, TOOL_VERSION, Report, Verdict, build_report

__version__ = TOOL_VERSION

__all__ = [
    "SPEC_VERSION",
    "TOOL_NAME",
    "TOOL_VERSION",
    "Corpus",
    "CorpusChunk",
    "DriftFinding",
    "DriftResult",
    "DriftSummary",
    "FixResult",
    "Gate",
    "GateEvaluation",
    "GateResult",
    "Judgment",
    "Measurement",
    "QueryMetrics",
    "Report",
    "RunEntry",
    "ScoreResult",
    "StratumScore",
    "ValidationIssue",
    "ValidationResult",
    "Verdict",
    "__version__",
    "build_report",
    "chunk_id",
    "drift",
    "evaluate_gates",
    "fix",
    "from_qrels",
    "from_trec_run",
    "normalize",
    "parse_corpus",
    "parse_gate",
    "parse_judgments",
    "parse_run",
    "query_metrics",
    "relevance_by_query",
    "score",
    "score_by_stratum",
    "serialize_judgments",
    "text_sha",
    "to_qrels",
    "to_trec_run",
    "validate",
    "worst_stratum",
]
