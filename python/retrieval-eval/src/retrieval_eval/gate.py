"""CI gates.

Deltas rather than absolutes, because absolute thresholds get tuned until they pass. And a
third verdict, ``INDETERMINATE``, because "I cannot tell" is different from "it failed" and
collapsing the two is how noisy measurements get treated as evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from .metrics import worst_stratum
from .models import Status
from .report import Report

GateKind = Literal["absolute", "delta", "worst-stratum", "ci-lower"]


@dataclass(slots=True)
class Gate:
    """A parsed gate expression."""

    raw: str
    kind: GateKind
    metric: str
    threshold: float


@dataclass(slots=True)
class GateResult:
    """The outcome of one gate."""

    expression: str
    status: Status
    observed: float | None = None
    baseline: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize, omitting unset fields."""
        out: dict[str, Any] = {"expression": self.expression, "status": self.status}
        if self.observed is not None:
            out["observed"] = self.observed
        if self.baseline is not None:
            out["baseline"] = self.baseline
        return out


#: Finite decimal numbers only.
#:
#: ``float`` accepts 'nan' and 'infinity', and JavaScript's ``parseFloat`` reads '0.5abc' as
#: 0.5. Either way the two implementations disagree about what a gate means, and a threshold
#: they cannot agree on is worse than no threshold at all.
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _parse_number(value: str, expression: str) -> float:
    if not _NUMBER_RE.match(value):
        raise ValueError(f"gate '{expression}': '{value}' is not a number")
    return float(value)


def worse_status(a: Status, b: Status) -> Status:
    """Return the more serious of two verdicts: FAIL beats INDETERMINATE beats PASS.

    A gate only knows about the numbers it was pointed at. It cannot clear a finding it never
    looked at, such as a judgment set ``validate`` rejects, so a passing gate never upgrades a
    verdict that was already worse.
    """
    if a == "FAIL" or b == "FAIL":
        return "FAIL"
    if a == "INDETERMINATE" or b == "INDETERMINATE":
        return "INDETERMINATE"
    return "PASS"


def parse_gate(expression: str) -> Gate:
    """Parse a gate expression.

    Four forms::

        recall@5:0.8                   absolute floor
        recall@5:-0.02                 delta against a baseline
        worst-stratum:recall@5:0.7     floor on the weakest query class
        faithfulness:ci-lower:0.8      floor on the lower confidence bound
    """
    parts = expression.split(":")

    if parts[0] == "worst-stratum":
        if len(parts) != 3:
            raise ValueError(f"gate '{expression}': expected worst-stratum:<metric>:<floor>")
        return Gate(expression, "worst-stratum", parts[1], _parse_number(parts[2], expression))

    if len(parts) == 3 and parts[1] == "ci-lower":
        return Gate(expression, "ci-lower", parts[0], _parse_number(parts[2], expression))

    if len(parts) != 2:
        raise ValueError(f"gate '{expression}': expected <metric>:<threshold>")

    value = parts[1]
    kind: GateKind = "delta" if value.startswith(("-", "+")) else "absolute"
    return Gate(expression, kind, parts[0], _parse_number(value, expression))


def _evaluate_gate(gate: Gate, report: Report, baseline: Report | None) -> GateResult:
    if gate.kind == "worst-stratum":
        if not report.per_stratum:
            return GateResult(gate.raw, "INDETERMINATE")
        worst = worst_stratum(report.per_stratum, gate.metric)
        if worst is None:
            return GateResult(gate.raw, "INDETERMINATE")
        return GateResult(
            gate.raw,
            "PASS" if worst.value >= gate.threshold else "FAIL",
            observed=worst.value,
        )

    measurement = report.metrics.get(gate.metric)
    if measurement is None:
        return GateResult(gate.raw, "INDETERMINATE")

    if gate.kind == "ci-lower":
        # A metric with no interval cannot satisfy a confidence-bound gate. Refusing to guess
        # is the point: one sample from a non-deterministic judge is not evidence.
        if measurement.ci is None:
            return GateResult(gate.raw, "INDETERMINATE", observed=measurement.value)
        lower = measurement.ci[0]
        return GateResult(gate.raw, "PASS" if lower >= gate.threshold else "FAIL", observed=lower)

    if gate.kind == "delta":
        previous = baseline.metrics.get(gate.metric) if baseline else None
        if previous is None:
            return GateResult(gate.raw, "INDETERMINATE", observed=measurement.value)
        delta = measurement.value - previous.value
        return GateResult(
            gate.raw,
            "PASS" if delta >= gate.threshold else "FAIL",
            observed=measurement.value,
            baseline=previous.value,
        )

    return GateResult(
        gate.raw,
        "PASS" if measurement.value >= gate.threshold else "FAIL",
        observed=measurement.value,
    )


def _describe(gate: Gate, result: GateResult, report: Report) -> str:
    if result.status == "INDETERMINATE":
        nothing_scored = report.judgments.get("queries_scored") == 0 and result.observed is None
        if nothing_scored and gate.kind != "worst-stratum":
            return f"{gate.raw}: no query was scored, so '{gate.metric}' was not computed"
        if gate.kind == "ci-lower":
            return (
                f"{gate.raw}: no confidence interval on '{gate.metric}', sample it more than once"
            )
        if gate.kind == "delta":
            return f"{gate.raw}: no baseline value for '{gate.metric}'"
        if gate.kind == "worst-stratum":
            strata = report.per_stratum or {}
            if strata and all(stratum.n == 0 for stratum in strata.values()):
                return f"{gate.raw}: no stratum was scored for '{gate.metric}'"
            return f"{gate.raw}: no per-stratum data for '{gate.metric}'"
        return f"{gate.raw}: metric '{gate.metric}' not present in the report"

    observed = result.observed or 0.0
    if gate.kind == "delta":
        previous = result.baseline or 0.0
        change = observed - previous
        direction = f"fell {-change:.4f}" if change < 0 else f"rose {change:.4f}"
        return (
            f"{gate.metric} {direction}, from {previous:.4f} to {observed:.4f}, "
            f"outside {gate.threshold}"
        )
    if gate.kind == "worst-stratum":
        return f"worst stratum {gate.metric} is {observed:.4f}, below {gate.threshold}"
    if gate.kind == "ci-lower":
        return f"{gate.metric} lower bound is {observed:.4f}, below {gate.threshold}"
    return f"{gate.metric} is {observed:.4f}, below {gate.threshold}"


@dataclass(slots=True)
class GateEvaluation:
    """The combined verdict over every gate."""

    status: Status
    results: list[GateResult]
    reasons: list[str]


def evaluate_gates(
    report: Report, gates: list[Gate], baseline: Report | None = None
) -> GateEvaluation:
    """Evaluate every gate against a report, worst status winning."""
    results: list[GateResult] = []
    reasons: list[str] = []

    for gate in gates:
        result = _evaluate_gate(gate, report, baseline)
        results.append(result)
        if result.status in ("FAIL", "INDETERMINATE"):
            reasons.append(_describe(gate, result, report))

    if any(r.status == "FAIL" for r in results):
        status: Status = "FAIL"
    elif any(r.status == "INDETERMINATE" for r in results):
        status = "INDETERMINATE"
    else:
        status = "PASS"

    return GateEvaluation(status=status, results=results, reasons=reasons)
