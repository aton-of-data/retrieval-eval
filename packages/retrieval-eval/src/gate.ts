import { worstStratum } from "./metrics.js";
import type { GateResult, Measurement, Report, Status } from "./types.js";

/**
 * A gate expression. Four forms, because absolute thresholds get tuned until they pass:
 *
 *   recall@5:0.8              absolute floor
 *   recall@5:-0.02            delta against a baseline (regression tolerance)
 *   worst-stratum:recall@5:0.7  floor on the weakest query class
 *   faithfulness:ci-lower:0.8   floor on the lower confidence bound, so judge noise cannot pass
 */
export interface Gate {
  raw: string;
  kind: "absolute" | "delta" | "worst-stratum" | "ci-lower";
  metric: string;
  threshold: number;
}

export function parseGate(expression: string): Gate {
  const parts = expression.split(":");

  if (parts[0] === "worst-stratum") {
    if (parts.length !== 3)
      throw new Error(`gate '${expression}': expected worst-stratum:<metric>:<floor>`);
    return {
      raw: expression,
      kind: "worst-stratum",
      metric: parts[1] as string,
      threshold: parseNumber(parts[2] as string, expression),
    };
  }

  if (parts.length === 3 && parts[1] === "ci-lower") {
    return {
      raw: expression,
      kind: "ci-lower",
      metric: parts[0] as string,
      threshold: parseNumber(parts[2] as string, expression),
    };
  }

  if (parts.length !== 2) throw new Error(`gate '${expression}': expected <metric>:<threshold>`);
  const value = parts[1] as string;
  return {
    raw: expression,
    kind: value.startsWith("-") || value.startsWith("+") ? "delta" : "absolute",
    metric: parts[0] as string,
    threshold: parseNumber(value, expression),
  };
}

/**
 * Finite decimal numbers only.
 *
 * `Number.parseFloat` would read '0.5abc' as 0.5, and Python's `float` accepts 'nan' and
 * 'infinity'. Either way the two implementations disagree about what a gate means, and a
 * threshold they cannot agree on is worse than no threshold at all.
 */
const NUMBER = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

function parseNumber(value: string, expression: string): number {
  if (!NUMBER.test(value)) throw new Error(`gate '${expression}': '${value}' is not a number`);
  return Number.parseFloat(value);
}

/**
 * The more serious of two verdicts: FAIL beats INDETERMINATE beats PASS.
 *
 * A gate only knows about the numbers it was pointed at. It cannot clear a finding it never
 * looked at, such as a judgment set `validate` rejects, so a passing gate never upgrades a
 * verdict that was already worse.
 */
export function worseStatus(a: Status, b: Status): Status {
  if (a === "FAIL" || b === "FAIL") return "FAIL";
  if (a === "INDETERMINATE" || b === "INDETERMINATE") return "INDETERMINATE";
  return "PASS";
}

export interface EvaluateGatesOptions {
  report: Report;
  baseline?: Report | undefined;
  gates: Gate[];
}

export function evaluateGates({ report, baseline, gates }: EvaluateGatesOptions): {
  status: Status;
  results: GateResult[];
  reasons: string[];
} {
  const results: GateResult[] = [];
  const reasons: string[] = [];

  for (const gate of gates) {
    const result = evaluateGate(gate, report, baseline);
    results.push(result);
    if (result.status === "FAIL" || result.status === "INDETERMINATE") {
      reasons.push(describe(gate, result, report));
    }
  }

  const status: Status = results.some((r) => r.status === "FAIL")
    ? "FAIL"
    : results.some((r) => r.status === "INDETERMINATE")
      ? "INDETERMINATE"
      : "PASS";

  return { status, results, reasons };
}

function evaluateGate(gate: Gate, report: Report, baseline?: Report): GateResult {
  if (gate.kind === "worst-stratum") {
    if (!report.per_stratum) {
      return { expression: gate.raw, status: "INDETERMINATE" };
    }
    const worst = worstStratum(report.per_stratum, gate.metric);
    if (!worst) return { expression: gate.raw, status: "INDETERMINATE" };
    return {
      expression: gate.raw,
      status: worst.value >= gate.threshold ? "PASS" : "FAIL",
      observed: worst.value,
    };
  }

  const measurement: Measurement | undefined = report.metrics[gate.metric];
  if (!measurement) return { expression: gate.raw, status: "INDETERMINATE" };

  if (gate.kind === "ci-lower") {
    // A metric with no interval cannot satisfy a confidence-bound gate. Refusing to guess is
    // the point: a single sample from a non-deterministic judge is not evidence.
    if (!measurement.ci) {
      return { expression: gate.raw, status: "INDETERMINATE", observed: measurement.value };
    }
    const lower = measurement.ci[0];
    return {
      expression: gate.raw,
      status: lower >= gate.threshold ? "PASS" : "FAIL",
      observed: lower,
    };
  }

  if (gate.kind === "delta") {
    const previous = baseline?.metrics[gate.metric];
    if (!previous) {
      return {
        expression: gate.raw,
        status: "INDETERMINATE",
        observed: measurement.value,
        baseline: null,
      };
    }
    const delta = measurement.value - previous.value;
    return {
      expression: gate.raw,
      status: delta >= gate.threshold ? "PASS" : "FAIL",
      observed: measurement.value,
      baseline: previous.value,
    };
  }

  return {
    expression: gate.raw,
    status: measurement.value >= gate.threshold ? "PASS" : "FAIL",
    observed: measurement.value,
  };
}

function describe(gate: Gate, result: GateResult, report: Report): string {
  if (result.status === "INDETERMINATE") {
    const nothingScored = report.judgments.queries_scored === 0 && result.observed === undefined;
    if (nothingScored && gate.kind !== "worst-stratum") {
      return `${gate.raw}: no query was scored, so '${gate.metric}' was not computed`;
    }
    if (gate.kind === "ci-lower") {
      return `${gate.raw}: no confidence interval on '${gate.metric}', sample it more than once`;
    }
    if (gate.kind === "delta") return `${gate.raw}: no baseline value for '${gate.metric}'`;
    if (gate.kind === "worst-stratum") {
      const strata = Object.values(report.per_stratum ?? {});
      if (strata.length > 0 && strata.every((stratum) => stratum.n === 0)) {
        return `${gate.raw}: no stratum was scored for '${gate.metric}'`;
      }
      return `${gate.raw}: no per-stratum data for '${gate.metric}'`;
    }
    return `${gate.raw}: metric '${gate.metric}' not present in the report`;
  }
  if (gate.kind === "delta") {
    const from = result.baseline ?? 0;
    const to = result.observed ?? 0;
    const change = to - from;
    const direction = change < 0 ? `fell ${(-change).toFixed(4)}` : `rose ${change.toFixed(4)}`;
    return `${gate.metric} ${direction}, from ${from.toFixed(4)} to ${to.toFixed(4)}, outside ${gate.threshold}`;
  }
  if (gate.kind === "worst-stratum") {
    return `worst stratum ${gate.metric} is ${(result.observed ?? 0).toFixed(4)}, below ${gate.threshold}`;
  }
  if (gate.kind === "ci-lower") {
    return `${gate.metric} lower bound is ${(result.observed ?? 0).toFixed(4)}, below ${gate.threshold}`;
  }
  return `${gate.metric} is ${(result.observed ?? 0).toFixed(4)}, below ${gate.threshold}`;
}
