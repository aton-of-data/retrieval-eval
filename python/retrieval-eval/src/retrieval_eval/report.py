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

    judgments_info: dict[str, Any] = {
        "queries": validation.queries,
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
    if scored.missing_queries:
        reasons.append(
            f"{len(scored.missing_queries)} judged queries had no run entry and scored zero"
        )

    return Report(
        generated_at=(now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
        corpus=corpus_info,
        judgments=judgments_info,
        metrics=scored.metrics,
        verdict=Verdict(status="PASS", reasons=reasons),
        per_stratum=score_by_stratum(judgments, run, k=k, threshold=threshold)
        if has_strata
        else None,
    )
