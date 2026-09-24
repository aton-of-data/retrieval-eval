import { byCodePoint, validate } from "./judgments.js";
import { score, scoreByStratum } from "./metrics.js";
import type { MetricOptions } from "./metrics.js";
import type { Corpus, DriftResult, Judgment, Report, RunEntry } from "./types.js";

export const TOOL_NAME = "retrieval-eval";
export const TOOL_VERSION = "0.1.0";
export const SPEC_VERSION = "1" as const;

export interface BuildReportOptions extends MetricOptions {
  judgments: Judgment[];
  run: RunEntry[];
  corpus?: Corpus | undefined;
  driftResult?: DriftResult | undefined;
  now?: Date;
}

export function buildReport(options: BuildReportOptions): Report {
  const { judgments, run, corpus, driftResult } = options;
  const metricOptions: MetricOptions = { k: options.k ?? 10, threshold: options.threshold ?? 1 };

  const scored = score(judgments, run, metricOptions);
  const validation = validate(judgments);
  const hasStrata = judgments.some((j) => j.stratum !== undefined);

  const corpusInfo: Report["corpus"] = { fingerprint: corpus?.corpus_fingerprint ?? null };
  if (corpus) {
    corpusInfo.documents = new Set(corpus.chunks.map((c) => c.doc_uri)).size;
    corpusInfo.chunks = corpus.chunks.length;
  }

  // Findings that should colour the verdict even when no gate was requested. A metric computed
  // over decayed labels is worse than no metric, because it looks trustworthy.
  const reasons: string[] = [];
  if (driftResult && driftResult.summary.invalid_ratio > 0) {
    reasons.push(
      `${Math.round(driftResult.summary.invalid_ratio * 100)}% of judgments no longer match the live corpus`,
    );
  }
  // A query with no label at the threshold is excluded, not scored. Only the ones that were
  // actually averaged can have "scored zero" said of them.
  const missingAndScored = scored.missingQueries.filter(
    (id) => !scored.queriesWithoutPositives.includes(id),
  );
  if (missingAndScored.length > 0) {
    reasons.push(`${missingAndScored.length} judged queries had no run entry and scored zero`);
  }
  const queriesScored = validation.queries - scored.queriesWithoutPositives.length;
  if (scored.queriesWithoutPositives.length > 0 && queriesScored > 0) {
    reasons.push(
      `${scored.queriesWithoutPositives.length} judged queries have no label at relevance >= ${metricOptions.threshold} and were excluded from the averages`,
    );
  }
  if (queriesScored === 0) {
    reasons.push(
      validation.queries === 0
        ? "no judged queries, so no metric was computed"
        : `no query had a label at relevance >= ${metricOptions.threshold}, so no metric was computed`,
    );
  }
  // The numbers above already count a repeated key once. Saying so keeps the correction
  // visible: a quiet fix to someone's ranking is its own kind of wrong number.
  if (scored.queriesWithDuplicates.length > 0) {
    reasons.push(
      `${scored.queriesWithDuplicates.length} queries repeated a key in their ranking; only the first occurrence of each was counted`,
    );
  }
  // `validate` calls these errors and exits non-zero on them. Scoring the same set and
  // reporting PASS is exactly the measurement lie this tool exists to expose, so the verdict
  // cannot be PASS either. Warnings are left to `validate`, which is where they belong.
  const validationErrors = validation.issues.filter((issue) => issue.severity === "error");
  if (validationErrors.length > 0) {
    const codes = [...new Set(validationErrors.map((issue) => issue.code))].sort(byCodePoint);
    reasons.push(
      `the judgment set is unsound (${codes.join(", ")}); run 'retrieval-eval validate' for detail. No metric computed from it can be trusted`,
    );
  }

  // Key insertion order follows spec/report.schema.json, so this serializes to the same bytes
  // as the Python implementation. `per_stratum` must sit between metrics and verdict.
  // An empty scored set is not a pass: there is no number, so the verdict cannot be PASS.
  const report: Report = {
    spec_version: SPEC_VERSION,
    tool: { name: TOOL_NAME, version: TOOL_VERSION },
    generated_at: (options.now ?? new Date()).toISOString(),
    corpus: corpusInfo,
    judgments: {
      queries: validation.queries,
      queries_scored: queriesScored,
      labels: validation.labels,
      fingerprint: validation.fingerprint,
      human_labels: validation.humanLabels,
      synthetic_labels: validation.syntheticLabels,
      ...(driftResult ? { drift: driftResult.summary } : {}),
    },
    metrics: scored.metrics,
    ...(hasStrata ? { per_stratum: scoreByStratum(judgments, run, metricOptions) } : {}),
    verdict: {
      status: queriesScored === 0 || validationErrors.length > 0 ? "INDETERMINATE" : "PASS",
      reasons,
    },
  };

  return report;
}
