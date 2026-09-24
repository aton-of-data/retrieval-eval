import type { Corpus, Judgment, RunEntry } from "./types.js";

/** A parsed row, with the line it came from: an error that points at the wrong line is noise. */
interface Row<T> {
  value: T;
  line: number;
}

function parseJsonl<T>(content: string, label: string): Row<T>[] {
  const out: Row<T>[] = [];
  const lines = content.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = (lines[i] as string).trim();
    if (line === "" || line.startsWith("//")) continue;
    try {
      out.push({ value: JSON.parse(line) as T, line: i + 1 });
    } catch (error) {
      throw new Error(`${label}:${i + 1}: invalid JSON, ${(error as Error).message}`);
    }
  }
  return out;
}

export function parseJudgments(content: string, label = "judgments"): Judgment[] {
  const rows = parseJsonl<Judgment>(content, label);
  for (const { value, line } of rows) {
    if (typeof value.query_id !== "string" || value.query_id === "")
      throw new Error(`${label}:${line}: missing query_id`);
    if (typeof value.doc_uri !== "string" || value.doc_uri === "")
      throw new Error(`${label}:${line}: missing doc_uri`);
    if (!Number.isInteger(value.relevance) || value.relevance < 0)
      throw new Error(`${label}:${line}: relevance must be a non-negative integer`);
  }
  return rows.map((row) => row.value);
}

/**
 * Parse a run JSONL file.
 *
 * The run is the one input that used to be taken on trust, and an unchecked run is how a
 * metric goes out of range: a ranking holding a non-string, or two entries claiming the same
 * query, produce numbers that mean nothing and say nothing about it.
 *
 * Two entries for one query are rejected rather than resolved, because the file no longer says
 * what the ranking for that query is, and picking one silently is a guess. A key repeated
 * *within* one ranking is a different thing: the ranking is still unambiguous, so it is
 * accepted here and counted once by `score`, which reports that it did.
 */
export function parseRun(content: string, label = "run"): RunEntry[] {
  const rows = parseJsonl<RunEntry>(content, label);
  const firstSeen = new Map<string, number>();
  for (const { value, line } of rows) {
    if (typeof value.query_id !== "string" || value.query_id === "")
      throw new Error(`${label}:${line}: missing query_id`);
    if (!Array.isArray(value.ranking))
      throw new Error(`${label}:${line}: ranking must be an array`);
    for (let i = 0; i < value.ranking.length; i++) {
      const key = value.ranking[i];
      if (typeof key !== "string" || key === "")
        throw new Error(`${label}:${line}: ranking[${i}] must be a non-empty string`);
    }
    const previous = firstSeen.get(value.query_id);
    if (previous !== undefined)
      throw new Error(
        `${label}:${line}: duplicate entry for query ${value.query_id}, already on line ${previous}`,
      );
    firstSeen.set(value.query_id, line);
  }
  return rows.map((row) => row.value);
}

/**
 * Compare by Unicode code point, which is what Python's `sorted` does.
 *
 * JavaScript's default sort compares UTF-16 code units, and the two disagree for anything
 * above the basic multilingual plane. Anywhere an ordering reaches the output, the two
 * implementations have to agree on it, so both sort the same way.
 */
export function byCodePoint(a: string, b: string): number {
  const left = [...a];
  const right = [...b];
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    const difference =
      ((left[i] as string).codePointAt(0) ?? 0) - ((right[i] as string).codePointAt(0) ?? 0);
    if (difference !== 0) return difference;
  }
  return left.length - right.length;
}

/**
 * The canonical field order from the schema. Both implementations emit it, so a file written by
 * one is byte-identical to the same file written by the other, and `drift --fix` produces a diff
 * of the labels that changed rather than of the whole file.
 */
const FIELD_ORDER = [
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
] as const;

export function serializeJudgments(judgments: Judgment[]): string {
  const lines = judgments.map((judgment) => {
    const ordered: Record<string, unknown> = {};
    for (const field of FIELD_ORDER) {
      if (judgment[field] !== undefined) ordered[field] = judgment[field];
    }
    // Unknown fields keep their own order and come last: the spec requires round-tripping
    // fields an implementation does not understand.
    for (const [key, value] of Object.entries(judgment)) {
      if (!(FIELD_ORDER as readonly string[]).includes(key)) ordered[key] = value;
    }
    return JSON.stringify(ordered);
  });
  return `${lines.join("\n")}\n`;
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

  // Sorted, not insertion order: this ordering reaches `--json` and the rendered report,
  // so it is part of what the two implementations must agree on.
  for (const queryId of [...queries].sort(byCodePoint)) {
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
  for (const [name, count] of Object.entries(strata).sort(([a], [b]) => byCodePoint(a, b))) {
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
