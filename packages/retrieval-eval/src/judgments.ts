import type { Corpus, Judgment, RunEntry } from "./types.js";

function parseJsonl<T>(content: string, label: string): T[] {
  const out: T[] = [];
  const lines = content.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = (lines[i] as string).trim();
    if (line === "" || line.startsWith("//")) continue;
    try {
      out.push(JSON.parse(line) as T);
    } catch (error) {
      throw new Error(`${label}:${i + 1}: invalid JSON, ${(error as Error).message}`);
    }
  }
  return out;
}

export function parseJudgments(content: string, label = "judgments"): Judgment[] {
  const rows = parseJsonl<Judgment>(content, label);
  for (const [i, row] of rows.entries()) {
    if (typeof row.query_id !== "string" || row.query_id === "")
      throw new Error(`${label}:${i + 1}: missing query_id`);
    if (typeof row.doc_uri !== "string" || row.doc_uri === "")
      throw new Error(`${label}:${i + 1}: missing doc_uri`);
    if (!Number.isInteger(row.relevance) || row.relevance < 0)
      throw new Error(`${label}:${i + 1}: relevance must be a non-negative integer`);
  }
  return rows;
}

export function parseRun(content: string, label = "run"): RunEntry[] {
  const rows = parseJsonl<RunEntry>(content, label);
  for (const [i, row] of rows.entries()) {
    if (typeof row.query_id !== "string") throw new Error(`${label}:${i + 1}: missing query_id`);
    if (!Array.isArray(row.ranking)) throw new Error(`${label}:${i + 1}: ranking must be an array`);
  }
  return rows;
}

export function serializeJudgments(judgments: Judgment[]): string {
  return `${judgments.map((j) => JSON.stringify(j)).join("\n")}\n`;
}

export function parseCorpus(content: string, label = "corpus"): Corpus {
  const parsed = JSON.parse(content) as Corpus;
  if (!Array.isArray(parsed.chunks)) throw new Error(`${label}: missing chunks array`);
  return parsed;
}

export type Severity = "error" | "warning";

export interface ValidationIssue {
  severity: Severity;
  code: string;
  message: string;
}

export interface ValidationResult {
  issues: ValidationIssue[];
  queries: number;
  labels: number;
  humanLabels: number;
  syntheticLabels: number;
  fingerprint: string | null;
  strata: Record<string, number>;
  ok: boolean;
}

/**
 * Structural and statistical sanity checks. The warnings matter as much as the errors: a
 * judgment set with no positives, no human labels, or a two-query stratum will produce
 * confident-looking numbers that mean nothing.
 */
export function validate(judgments: Judgment[]): ValidationResult {
  const issues: ValidationIssue[] = [];
  const queries = new Set<string>();
  const strata: Record<string, number> = {};
  const fingerprints = new Set<string>();
  const seen = new Set<string>();
  const queryText = new Map<string, string>();

  let humanLabels = 0;
  let syntheticLabels = 0;
  let positives = 0;

  for (const j of judgments) {
    queries.add(j.query_id);
    if (j.relevance >= 1) positives++;
    if (j.corpus_fingerprint) fingerprints.add(j.corpus_fingerprint);
    if (j.labeled_by?.startsWith("human:")) humanLabels++;
    else if (j.labeled_by?.startsWith("synthetic:")) syntheticLabels++;

    const stratum = j.stratum ?? "_unstratified";
    strata[stratum] = (strata[stratum] ?? 0) + 1;

    const key = `${j.query_id}\u0000${j.chunk_id ?? j.doc_uri}`;
    if (seen.has(key)) {
      issues.push({
        severity: "error",
        code: "duplicate-label",
        message: `duplicate judgment for query ${j.query_id} and target ${j.chunk_id ?? j.doc_uri}`,
      });
    }
    seen.add(key);

    if (j.query) {
      const existing = queryText.get(j.query_id);
      if (existing !== undefined && existing !== j.query) {
        issues.push({
          severity: "error",
          code: "inconsistent-query-text",
          message: `query ${j.query_id} has two different query strings`,
        });
      }
      queryText.set(j.query_id, j.query);
    }

    if (j.chunk_id && !/^c1:[0-9a-f]{32}$/.test(j.chunk_id)) {
      issues.push({
        severity: "error",
        code: "bad-chunk-id",
        message: `malformed chunk_id on query ${j.query_id}: ${j.chunk_id}`,
      });
    }
    if (j.text_sha && !/^t1:[0-9a-f]{32}$/.test(j.text_sha)) {
      issues.push({
        severity: "error",
        code: "bad-text-sha",
        message: `malformed text_sha on query ${j.query_id}: ${j.text_sha}`,
      });
    }
  }

  for (const queryId of queries) {
    if (!queryText.has(queryId)) {
      issues.push({
        severity: "warning",
        code: "missing-query-text",
        message: `query ${queryId} has no query text on any row`,
      });
    }
  }

  if (judgments.length === 0) {
    issues.push({ severity: "error", code: "empty", message: "no judgments" });
  }
  if (positives === 0 && judgments.length > 0) {
    issues.push({
      severity: "error",
      code: "no-positives",
      message: "no judgment has relevance >= 1, so recall is undefined for every query",
    });
  }
  if (humanLabels === 0 && syntheticLabels > 0) {
    issues.push({
      severity: "warning",
      code: "no-human-labels",
      message:
        "every label is synthetic. Without human labels you cannot measure judge calibration, " +
        "and synthetic labels quietly become ground truth",
    });
  }
  if (fingerprints.size > 1) {
    issues.push({
      severity: "warning",
      code: "mixed-fingerprints",
      message: `judgments span ${fingerprints.size} corpus fingerprints; run 'drift' before trusting any metric`,
    });
  }
  for (const [name, count] of Object.entries(strata)) {
    if (name !== "_unstratified" && count < 5) {
      issues.push({
        severity: "warning",
        code: "thin-stratum",
        message: `stratum '${name}' has only ${count} labels, too few to gate on`,
      });
    }
  }

  const withChunkId = judgments.filter((j) => j.chunk_id).length;
  if (withChunkId > 0 && withChunkId < judgments.length) {
    issues.push({
      severity: "warning",
      code: "mixed-granularity",
      message: `${withChunkId}/${judgments.length} labels have chunk_id; the rest are document-level`,
    });
  }
  if (withChunkId === 0 && judgments.length > 0) {
    issues.push({
      severity: "warning",
      code: "no-chunk-ids",
      message:
        "no label has a chunk_id, so drift can only work at document granularity. " +
        "See spec/chunk-id.md",
    });
  }

  const fingerprint = fingerprints.size === 1 ? ([...fingerprints][0] as string) : null;
  return {
    issues,
    queries: queries.size,
    labels: judgments.length,
    humanLabels,
    syntheticLabels,
    fingerprint,
    strata,
    ok: !issues.some((i) => i.severity === "error"),
  };
}
