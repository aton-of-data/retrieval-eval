/**
 * retrieval-eval: portable relevance judgments, deterministic retrieval metrics, and drift
 * detection for RAG.
 *
 * Zero runtime dependencies. No API key. Nothing here calls a model.
 */

export { chunkId, normalize, textSha } from "./identity.js";
export type { ChunkIdInput } from "./identity.js";

export {
  dedupe,
  judgmentKey,
  queryMetrics,
  relevanceByQuery,
  score,
  scoreByStratum,
  summarize,
  worstStratum,
} from "./metrics.js";
export type { MetricOptions, QueryMetrics, ScoreResult, StratumScore } from "./metrics.js";

export {
  parseCorpus,
  parseJudgments,
  parseRun,
  serializeJudgments,
  validate,
} from "./judgments.js";
export type { Severity, ValidationIssue, ValidationResult } from "./judgments.js";

export { fromQrels, fromTrecRun, toQrels, toTrecRun } from "./qrels.js";
export type { FromQrelsOptions } from "./qrels.js";

export { drift, fix } from "./drift.js";
export type { DriftOptions, FixResult } from "./drift.js";

export { evaluateGates, parseGate, worseStatus } from "./gate.js";
export type { EvaluateGatesOptions, Gate } from "./gate.js";

export { buildReport, SPEC_VERSION, TOOL_NAME, TOOL_VERSION } from "./report.js";
export type { BuildReportOptions } from "./report.js";

export type {
  Corpus,
  CorpusChunk,
  DriftFinding,
  DriftResult,
  DriftStatus,
  DriftSummary,
  GateResult,
  Judgment,
  Measurement,
  Report,
  RunEntry,
  Status,
} from "./types.js";
