"""The portable report format.

SARIF's lesson applied to retrieval: any tool may emit this, any CI or dashboard may read it.
Two fields are mandatory, ``per_stratum`` when strata exist and ``ci`` on any LLM-judged
metric, because both encode a lesson the field keeps relearning.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .metrics import DEFAULT_K, DEFAULT_THRESHOLD, StratumScore, score, score_by_stratum
from .models import Corpus, DriftResult, Judgment, Measurement, RunEntry, Status


def _as_ci(value: Any) -> tuple[float, float] | None:
    """Coerce a two-element JSON array into the CI tuple, or None."""
    if not value:
        return None
    lower, upper = value
    return (float(lower), float(upper))


TOOL_NAME = "retrieval-eval"
TOOL_VERSION = "0.1.0"
SPEC_VERSION = "1"


@dataclass(slots=True)
class Verdict:
    """The overall outcome plus why."""

    status: Status = "PASS"
    reasons: list[str] = field(default_factory=list)
    gates: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize, omitting empty gate lists."""
        out: dict[str, Any] = {"status": self.status, "reasons": self.reasons}
        if self.gates:
            out["gates"] = [g.to_dict() for g in self.gates]
        return out


@dataclass(slots=True)
class Report:
    """A complete retrieval-eval report."""

    generated_at: str
    corpus: dict[str, Any]
    judgments: dict[str, Any]
    metrics: dict[str, Measurement]
    verdict: Verdict
    per_stratum: dict[str, StratumScore] | None = None
    spec_version: str = SPEC_VERSION
    tool: dict[str, str] = field(
        default_factory=lambda: {"name": TOOL_NAME, "version": TOOL_VERSION}
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the shape ``spec/report.schema.json`` describes."""
        out: dict[str, Any] = {
            "spec_version": self.spec_version,
            "tool": self.tool,
            "generated_at": self.generated_at,
            "corpus": self.corpus,
            "judgments": self.judgments,
            "metrics": {name: m.to_dict() for name, m in self.metrics.items()},
        }
        if self.per_stratum is not None:
            out["per_stratum"] = {
                name: {"n": s.n, "metrics": {k: m.to_dict() for k, m in s.metrics.items()}}
                for name, s in self.per_stratum.items()
            }
        out["verdict"] = self.verdict.to_dict()
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Report:
        """Rebuild a report, used for ``--baseline`` comparison."""
        metrics = {
            name: Measurement(
                value=m["value"],
                n=m.get("n"),
                stdev=m.get("stdev"),
                ci=_as_ci(m.get("ci")),
                deterministic=m.get("deterministic"),
            )
            for name, m in data.get("metrics", {}).items()
        }
        per_stratum = None
        if data.get("per_stratum"):
            per_stratum = {
                name: StratumScore(
                    n=s["n"],
                    metrics={
                        k: Measurement(value=m["value"], ci=_as_ci(m.get("ci")))
                        for k, m in s.get("metrics", {}).items()
                    },
                )
                for name, s in data["per_stratum"].items()
            }
        verdict_data = data.get("verdict", {})
        return cls(
            generated_at=data.get("generated_at", ""),
            corpus=data.get("corpus", {}),
            judgments=data.get("judgments", {}),
            metrics=metrics,
            verdict=Verdict(
                status=verdict_data.get("status", "PASS"),
                reasons=verdict_data.get("reasons", []),
            ),
            per_stratum=per_stratum,
            spec_version=data.get("spec_version", SPEC_VERSION),
            tool=data.get("tool", {"name": TOOL_NAME, "version": TOOL_VERSION}),
        )


def build_report(
    judgments: Sequence[Judgment],
    run: Sequence[RunEntry],
    k: int = DEFAULT_K,
    threshold: int = DEFAULT_THRESHOLD,
    corpus: Corpus | None = None,
    drift_result: DriftResult | None = None,
    now: datetime | None = None,
) -> Report:
    """Score a run and assemble the report."""
    from .judgments import validate  # imported here to keep module import order simple

    scored = score(judgments, run, k=k, threshold=threshold)
    validation = validate(judgments)
    has_strata = any(j.stratum is not None for j in judgments)

    corpus_info: dict[str, Any] = {"fingerprint": corpus.corpus_fingerprint if corpus else None}
    if corpus is not None:
        corpus_info["documents"] = len({c.doc_uri for c in corpus.chunks})
        corpus_info["chunks"] = len(corpus.chunks)

    queries_scored = validation.queries - len(scored.queries_without_positives)
    judgments_info: dict[str, Any] = {
        "queries": validation.queries,
        "queries_scored": queries_scored,
        "labels": validation.labels,
        "fingerprint": validation.fingerprint,
        "human_labels": validation.human_labels,
        "synthetic_labels": validation.synthetic_labels,
    }
    if drift_result is not None:
        judgments_info["drift"] = drift_result.summary.to_dict()

    # Findings that should colour the verdict even when no gate was requested. A metric computed
    # over decayed labels is worse than no metric, because it looks trustworthy.
    reasons: list[str] = []
    if drift_result is not None and drift_result.summary.invalid_ratio > 0:
        percent = round(drift_result.summary.invalid_ratio * 100)
        reasons.append(f"{percent}% of judgments no longer match the live corpus")
    # A query with no label at the threshold is excluded, not scored. Only the ones that were
    # actually averaged can have "scored zero" said of them.
    missing_and_scored = [
        query_id
        for query_id in scored.missing_queries
        if query_id not in scored.queries_without_positives
    ]
    if missing_and_scored:
        reasons.append(f"{len(missing_and_scored)} judged queries had no run entry and scored zero")
    if scored.queries_without_positives and queries_scored > 0:
        reasons.append(
            f"{len(scored.queries_without_positives)} judged queries have no label at "
            f"relevance >= {threshold} and were excluded from the averages"
        )
    if queries_scored == 0:
        if validation.queries == 0:
            reasons.append("no judged queries, so no metric was computed")
        else:
            reasons.append(
                f"no query had a label at relevance >= {threshold}, so no metric was computed"
            )
    # The numbers above already count a repeated key once. Saying so keeps the correction
    # visible: a quiet fix to someone's ranking is its own kind of wrong number.
    if scored.queries_with_duplicates:
        reasons.append(
            f"{len(scored.queries_with_duplicates)} queries repeated a key in their ranking; "
            "only the first occurrence of each was counted"
        )
    # `validate` calls these errors and exits non-zero on them. Scoring the same set and
    # reporting PASS is exactly the measurement lie this tool exists to expose, so the verdict
    # cannot be PASS either. Warnings are left to `validate`, which is where they belong.
    validation_errors = [i for i in validation.issues if i.severity == "error"]
    if validation_errors:
        codes = sorted({issue.code for issue in validation_errors})
        reasons.append(
            f"the judgment set is unsound ({', '.join(codes)}); run 'retrieval-eval validate' "
            "for detail. No metric computed from it can be trusted"
        )

    # An empty scored set is not a pass: there is no number, so the verdict cannot be PASS.
    status: Status = "INDETERMINATE" if queries_scored == 0 or validation_errors else "PASS"
    return Report(
        generated_at=(now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
        corpus=corpus_info,
        judgments=judgments_info,
        metrics=scored.metrics,
        verdict=Verdict(status=status, reasons=reasons),
        per_stratum=score_by_stratum(judgments, run, k=k, threshold=threshold)
        if has_strata
        else None,
    )
