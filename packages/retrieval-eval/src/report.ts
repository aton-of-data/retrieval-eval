import { validate } from "./judgments.js";
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
  if (scored.missingQueries.length > 0) {
    reasons.push(`${scored.missingQueries.length} judged queries had no run entry and scored zero`);
  }

  // Key insertion order follows spec/report.schema.json, so this serializes to the same bytes
  // as the Python implementation. `per_stratum` must sit between metrics and verdict.
  const report: Report = {
    spec_version: SPEC_VERSION,
    tool: { name: TOOL_NAME, version: TOOL_VERSION },
    generated_at: (options.now ?? new Date()).toISOString(),
    corpus: corpusInfo,
    judgments: {
      queries: validation.queries,
      labels: validation.labels,
      fingerprint: validation.fingerprint,
      human_labels: validation.humanLabels,
      synthetic_labels: validation.syntheticLabels,
      ...(driftResult ? { drift: driftResult.summary } : {}),
    },
    metrics: scored.metrics,
    ...(hasStrata ? { per_stratum: scoreByStratum(judgments, run, metricOptions) } : {}),
    verdict: { status: "PASS", reasons },
  };

  return report;
}
