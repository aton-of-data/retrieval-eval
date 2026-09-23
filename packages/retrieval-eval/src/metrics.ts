import type { Judgment, Measurement, RunEntry } from "./types.js";

export interface MetricOptions {
  /** Cutoff for @k metrics. */
  k?: number;
  /** Minimum graded relevance that counts as relevant. */
  threshold?: number;
}

export interface QueryMetrics {
  precision: number;
  recall: number;
  ndcg: number;
  mrr: number;
  ap: number;
  hit_rate: number;
}

/** Key used to match a judgment against a ranking entry: chunk_id when present, else doc_uri. */
export function judgmentKey(j: Judgment): string {
  return j.chunk_id ?? j.doc_uri;
}

function dcg(gains: number[]): number {
  let total = 0;
  for (let i = 0; i < gains.length; i++) total += (gains[i] as number) / Math.log2(i + 2);
  return total;
}

/**
 * Metrics for a single query.
 *
 * `relevance` maps a ranking key to its graded relevance. Keys absent from the map are treated
 * as relevance 0, so unjudged means not-relevant, the standard closed-world assumption. That is
 * a real limitation of shallow judgment pools, and `validate` warns when pools look too thin.
 */
export function queryMetrics(
  relevance: Map<string, number>,
  ranking: string[],
  options: MetricOptions = {},
): QueryMetrics {
  const k = options.k ?? 10;
  const threshold = options.threshold ?? 1;
  const topK = ranking.slice(0, k);

  const relevantKeys = new Set(
    [...relevance.entries()].filter(([, r]) => r >= threshold).map(([key]) => key),
  );
  const hits = topK.filter((key) => relevantKeys.has(key));

  const gains = topK.map((key) => 2 ** (relevance.get(key) ?? 0) - 1);
  const idealGains = [...relevance.values()]
    .map((r) => 2 ** r - 1)
    .sort((a, b) => b - a)
    .slice(0, k);
  const idcg = dcg(idealGains);

  let mrr = 0;
  for (let i = 0; i < topK.length; i++) {
    if (relevantKeys.has(topK[i] as string)) {
      mrr = 1 / (i + 1);
      break;
    }
  }

  let found = 0;
  let apSum = 0;
  for (let i = 0; i < topK.length; i++) {
    if (relevantKeys.has(topK[i] as string)) {
      found++;
      apSum += found / (i + 1);
    }
  }

  return {
    precision: hits.length / k,
    recall: relevantKeys.size > 0 ? hits.length / relevantKeys.size : 0,
    ndcg: idcg > 0 ? dcg(gains) / idcg : 0,
    mrr,
    ap: relevantKeys.size > 0 ? apSum / relevantKeys.size : 0,
    hit_rate: hits.length > 0 ? 1 : 0,
  };
}

/** Group judgments by query, as `query_id -> (ranking key -> relevance)`. */
export function relevanceByQuery(judgments: Judgment[]): Map<string, Map<string, number>> {
  const out = new Map<string, Map<string, number>>();
  for (const j of judgments) {
    let inner = out.get(j.query_id);
    if (!inner) {
      inner = new Map();
      out.set(j.query_id, inner);
    }
    inner.set(judgmentKey(j), j.relevance);
  }
  return out;
}

/** Key order follows `spec/report.schema.json` so both implementations emit identical bytes. */
const deterministic = (value: number): Measurement => ({
  value: round(value),
  n: 1,
  deterministic: true,
});

function round(value: number): number {
  return Math.round(value * 1e12) / 1e12;
}

export interface ScoreResult {
  metrics: Record<string, Measurement>;
  perQuery: Map<string, QueryMetrics>;
  /** Queries present in the judgments but missing from the run. */
  missingQueries: string[];
}

/**
 * Macro-average metrics over queries. Queries with judgments but no run entry score zero
 * rather than being dropped, because silently skipping them inflates every metric.
 */
export function score(
  judgments: Judgment[],
  run: RunEntry[],
  options: MetricOptions = {},
): ScoreResult {
  const k = options.k ?? 10;
  const byQuery = relevanceByQuery(judgments);
  const rankings = new Map(run.map((r) => [r.query_id, r.ranking]));

  const perQuery = new Map<string, QueryMetrics>();
  const missingQueries: string[] = [];
  for (const [queryId, relevance] of byQuery) {
    const ranking = rankings.get(queryId);
    if (!ranking) missingQueries.push(queryId);
    perQuery.set(queryId, queryMetrics(relevance, ranking ?? [], options));
  }

  const n = perQuery.size;
  const mean = (pick: (m: QueryMetrics) => number): number =>
    n === 0 ? 0 : [...perQuery.values()].reduce((sum, m) => sum + pick(m), 0) / n;

  return {
    metrics: {
      [`precision@${k}`]: deterministic(mean((m) => m.precision)),
      [`recall@${k}`]: deterministic(mean((m) => m.recall)),
      [`ndcg@${k}`]: deterministic(mean((m) => m.ndcg)),
      mrr: deterministic(mean((m) => m.mrr)),
      map: deterministic(mean((m) => m.ap)),
      [`hit_rate@${k}`]: deterministic(mean((m) => m.hit_rate)),
    },
    perQuery,
    missingQueries,
  };
}

export interface StratumScore {
  n: number;
  metrics: Record<string, Measurement>;
}

/**
 * Per-stratum scores. A system can improve on the mean while failing an entire query class,
 * so coverage across strata is reported rather than one average.
 */
export function scoreByStratum(
  judgments: Judgment[],
  run: RunEntry[],
  options: MetricOptions = {},
): Record<string, StratumScore> {
  const strata = new Map<string, Judgment[]>();
  for (const j of judgments) {
    const name = j.stratum ?? "_unstratified";
    const list = strata.get(name);
    if (list) list.push(j);
    else strata.set(name, [j]);
  }

  const out: Record<string, StratumScore> = {};
  for (const [name, subset] of strata) {
    const result = score(subset, run, options);
    out[name] = { n: result.perQuery.size, metrics: result.metrics };
  }
  return out;
}

/** The lowest-scoring stratum for a metric. This is what gates should watch. */
export function worstStratum(
  perStratum: Record<string, StratumScore>,
  metric: string,
): { name: string; value: number; n: number } | null {
  let worst: { name: string; value: number; n: number } | null = null;
  for (const [name, stratum] of Object.entries(perStratum)) {
    const measurement = stratum.metrics[metric];
    if (!measurement) continue;
    if (!worst || measurement.value < worst.value) {
      worst = { name, value: measurement.value, n: stratum.n };
    }
  }
  return worst;
}
