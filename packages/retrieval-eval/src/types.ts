/** One relevance judgment. A judgments file is JSONL: one of these per line. */
export interface Judgment {
  query_id: string;
  query?: string;
  doc_uri: string;
  chunk_id?: string;
  text_sha?: string;
  chunk_text?: string;
  relevance: number;
  corpus_fingerprint?: string;
  labeled_by?: string;
  labeled_at?: string;
  stratum?: string;
  notes?: string;
  /** Unknown fields are preserved, never rejected. */
  [key: string]: unknown;
}

/** One query's ranked result: chunk_ids, or doc_uris for document-level evaluation. */
export interface RunEntry {
  query_id: string;
  ranking: string[];
}

export interface CorpusChunk {
  chunk_id: string;
  doc_uri: string;
  doc_revision?: string;
  ordinal?: number;
  text?: string;
  text_sha?: string;
}

export interface Corpus {
  corpus_fingerprint?: string;
  chunker_fingerprint?: string;
  chunks: CorpusChunk[];
}

export interface Measurement {
  value: number;
  /** Samples. Greater than 1 for non-deterministic (LLM-judged) metrics. */
  n?: number;
  stdev?: number;
  /** Required for any LLM-judged metric: a one-sample point estimate is a measurement lie. */
  ci?: [number, number];
  deterministic?: boolean;
}

export type Status = "PASS" | "FAIL" | "INDETERMINATE";

export interface GateResult {
  expression: string;
  status: Status;
  observed?: number;
  baseline?: number | null;
}

export interface Report {
  spec_version: "1";
  tool: { name: string; version: string };
  generated_at: string;
  corpus: { fingerprint: string | null; documents?: number; chunks?: number };
  judgments: {
    queries: number;
    /** Queries the averages were computed from: those with at least one label at the threshold. */
    queries_scored: number;
    labels: number;
    fingerprint: string | null;
    human_labels?: number;
    synthetic_labels?: number;
    drift?: DriftSummary;
  };
  metrics: Record<string, Measurement>;
  /** Mandatory when judgments carry strata: averages hide broken query classes. */
  per_stratum?: Record<string, { n: number; metrics: Record<string, Measurement> }>;
  verdict: { status: Status; reasons: string[]; gates?: GateResult[] };
}

export type DriftStatus = "VALID" | "RE_ANCHORABLE" | "MERGED" | "SPLIT" | "ORPHANED";

export interface DriftFinding {
  query_id: string;
  doc_uri: string;
  chunk_id?: string;
  status: DriftStatus;
  /** The live chunk_id this label should move to, when RE_ANCHORABLE or MERGED. */
  reanchor_to?: string;
  /** The live chunk_ids the labeled text now spans, when SPLIT. */
  split_into?: string[];
}

export interface DriftSummary {
  valid: number;
  re_anchorable: number;
  merged: number;
  split: number;
  orphaned: number;
  /** Share of labels that are not straightforwardly VALID. */
  invalid_ratio: number;
}

export interface DriftResult {
  findings: DriftFinding[];
  summary: DriftSummary;
  judgments_fingerprint: string | null;
  corpus_fingerprint: string | null;
}
