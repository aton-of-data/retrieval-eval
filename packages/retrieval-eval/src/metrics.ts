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

/**
 * Drop repeated keys from a ranking, keeping the first occurrence.
 *
 * A retriever that returns the same chunk twice is routine: a hybrid search merges two indexes,
 * or a multi-query expansion unions its results, and nothing deduplicates. Counted naively the
 * repeat scores as a second hit, which pushes `recall@k`, `map@k` and `ndcg@k` above 1.0 and
 * can carry a failing run past a gate. A repeat is not new evidence, so only the first
 * occurrence counts. `score` names the queries it happened to rather than correcting quietly.
 */
export function dedupe(ranking: readonly string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const key of ranking) {
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out;
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
  // Deduplicated before the cutoff is applied: a repeat occupies no rank of its own.
  const topK = dedupe(ranking).slice(0, k);

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

/**
 * Two-sided 95% Student-t critical values. The index is the degrees of freedom.
 *
 * A normal critical value is too small for the sample sizes this is built for: five draws from
 * a judge, the case in `examples/judged-metrics`, gives df=4, where t is 2.776 and z is 1.960.
 * The narrower interval can clear a `ci-lower` gate that the t interval fails. Above 120 degrees
 * of freedom the df=120 value is used, which is slightly wide, so the approximation cannot
 * shrink the interval.
 *
 * The interval is not clamped to the metric's range. Raising a negative lower bound to 0 turns
 * a failing `ci-lower:0` gate into a pass.
 */
const T_95 = [
  0, 12.706204736175, 4.302652729749, 3.182446305284, 2.776445105198, 2.570581835636,
  2.446911851145, 2.364624251593, 2.306004135204, 2.262157162798, 2.228138851986, 2.200985160092,
  2.178812829667, 2.160368656463, 2.144786687918, 2.13144954556, 2.119905299221, 2.109815577833,
  2.100922040241, 2.093024054408, 2.085963447266, 2.079613844728, 2.073873067904, 2.068657610419,
  2.063898561628, 2.059538552753, 2.055529438643, 2.05183051648, 2.048407141795, 2.045229642133,
  2.042272456301, 2.039513446396, 2.03693334346, 2.034515297449, 2.032244509318, 2.03010792825,
  2.02809400098, 2.026192463029, 2.024394163912, 2.022690920037, 2.021075390306, 2.019540970441,
  2.018081702818, 2.016692199228, 2.015367574444, 2.014103388881, 2.012895598919, 2.01174051373,
  2.010634757624, 2.009575237129, 2.008559112101, 2.007583770316, 2.006646805062, 2.005745995318,
  2.004879288188, 2.004044783289, 2.003240718848, 2.002465459291, 2.001717484145, 2.000995378088,
  2.000297822014, 1.999623584995, 1.998971517033, 1.998340542521, 1.997729654318, 1.997137908392,
  1.996564418952, 1.996008354025, 1.99546893143, 1.994945415107, 1.994437111771, 1.993943367846,
  1.993463566662, 1.99299712589, 1.992543495181, 1.992102154002, 1.991672609645, 1.991254395388,
  1.990847068812, 1.99045021023, 1.990063421254, 1.989686323457, 1.989318557137, 1.988959780175,
  1.988609666976, 1.988267907477, 1.987934206239, 1.987608281589, 1.987289864831, 1.986978699506,
  1.986674540704, 1.986377154419, 1.986086316951, 1.985801814346, 1.985523441867, 1.985251003505,
  1.984984311522, 1.984723186014, 1.984467454508, 1.984216951586, 1.983971518524, 1.983731002956,
  1.983495258563, 1.983264144773, 1.983037526484, 1.982815273795, 1.982597261765, 1.982383370176,
  1.982173483308, 1.981967489736, 1.981765282132, 1.981566757075, 1.981371814876, 1.981180359415,
  1.980992297976, 1.980807541104, 1.980626002459, 1.980447598683, 1.980272249273, 1.980099876457,
  1.979930405082,
];

/**
 * Turn repeated samples of a non-deterministic metric into a measurement with error bars.
 *
 * LLM judges vary even at temperature 0: the same triple scored three times can come back 0.8,
 * 1.0 and 0.6. A point estimate from one sample reports that spread as certainty, which is the
 * most common measurement lie in RAG evaluation and the reason the report format carries `n`,
 * `stdev` and `ci` at all.
 *
 * One sample yields no interval rather than a zero-width one, so a `ci-lower` gate over it is
 * INDETERMINATE instead of quietly passing. The interval is a Student-t interval on the sample
 * mean and is not clamped: a bound outside the metric's range is what the samples support.
 */
export function summarize(samples: number[]): Measurement {
  if (samples.length === 0) throw new Error("summarize needs at least one sample");

  const n = samples.length;
  const mean = samples.reduce((sum, value) => sum + value, 0) / n;
  if (n < 2) return { value: round(mean), n, deterministic: false };

  const variance = samples.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (n - 1);
  const stdev = Math.sqrt(variance);
  const df = Math.min(n - 1, T_95.length - 1);
  const margin = ((T_95[df] as number) * stdev) / Math.sqrt(n);

  return {
    value: round(mean),
    n,
    stdev: round(stdev),
    ci: [round(mean - margin), round(mean + margin)],
    deterministic: false,
  };
}

export interface ScoreResult {
  metrics: Record<string, Measurement>;
  perQuery: Map<string, QueryMetrics>;
  /** Queries present in the judgments but missing from the run. */
  missingQueries: string[];
  /**
   * Queries with no label at or above the threshold, excluded from the averages.
   *
   * Recall, nDCG, MRR and AP are all undefined when a query has nothing relevant to find.
   * Scoring such a query as zero would quietly drag every average down and make a judgment set
   * look like a retrieval failure, so they are excluded and counted instead.
   */
  queriesWithoutPositives: string[];
  /**
   * Queries whose ranking repeated a key. The metrics above already count each key once; this
   * says so, because a correction nobody is told about is its own kind of wrong number.
   */
  queriesWithDuplicates: string[];
}

/**
 * Macro-average metrics over queries.
 *
 * Queries with judgments but no run entry score zero rather than being dropped, because
 * silently skipping them inflates every metric. Queries with no relevant label are excluded
 * rather than scored zero, because there is nothing for retrieval to have found.
 *
 * Every metric is computed over the top `k` results and is named for it. `mrr@k` and `map@k`
 * are reciprocal rank and average precision within that cutoff, not over an unbounded run:
 * the name says so because a number that means something other than its name is how a report
 * stops being trustworthy.
 */
export function score(
  judgments: Judgment[],
  run: RunEntry[],
  options: MetricOptions = {},
): ScoreResult {
  const k = options.k ?? 10;
  const threshold = options.threshold ?? 1;
  const byQuery = relevanceByQuery(judgments);
  const rankings = new Map(run.map((r) => [r.query_id, r.ranking]));

  const perQuery = new Map<string, QueryMetrics>();
  const missingQueries: string[] = [];
  const queriesWithoutPositives: string[] = [];
  const queriesWithDuplicates: string[] = [];
  const scored: QueryMetrics[] = [];

  for (const [queryId, relevance] of byQuery) {
    const ranking = rankings.get(queryId);
    if (!ranking) missingQueries.push(queryId);
    else if (dedupe(ranking).length !== ranking.length) queriesWithDuplicates.push(queryId);

    const metrics = queryMetrics(relevance, ranking ?? [], options);
    perQuery.set(queryId, metrics);

    if ([...relevance.values()].some((r) => r >= threshold)) scored.push(metrics);
    else queriesWithoutPositives.push(queryId);
  }

  // Nothing at the threshold means the averages are undefined. Emitting 0 would let an absolute
  // gate fail a build over an empty set, which is the same lie as scoring an unscored query.
  if (scored.length === 0) {
    return {
      metrics: {},
      perQuery,
      missingQueries,
      queriesWithoutPositives,
      queriesWithDuplicates,
    };
  }

  const mean = (pick: (m: QueryMetrics) => number): number =>
    scored.reduce((sum, m) => sum + pick(m), 0) / scored.length;

  return {
    metrics: {
      [`precision@${k}`]: deterministic(mean((m) => m.precision)),
      [`recall@${k}`]: deterministic(mean((m) => m.recall)),
      [`ndcg@${k}`]: deterministic(mean((m) => m.ndcg)),
      [`mrr@${k}`]: deterministic(mean((m) => m.mrr)),
      [`map@${k}`]: deterministic(mean((m) => m.ap)),
      [`hit_rate@${k}`]: deterministic(mean((m) => m.hit_rate)),
    },
    perQuery,
    missingQueries,
    queriesWithoutPositives,
    queriesWithDuplicates,
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
    // `n` counts the queries the numbers were computed from, so a stratum whose labels are all
    // negative reads as n=0 rather than as a stratum that scored zero.
    out[name] = {
      n: result.perQuery.size - result.queriesWithoutPositives.length,
      metrics: result.metrics,
    };
  }
  return out;
}

/**
 * The lowest-scoring stratum for a metric. This is what gates should watch.
 *
 * Strata with no scored query are skipped rather than treated as zero. A class whose labels are
 * all below the relevance threshold has nothing for retrieval to have found, and reporting it as
 * the worst class would fail a build over an empty set.
 */
export function worstStratum(
  perStratum: Record<string, StratumScore>,
  metric: string,
): { name: string; value: number; n: number } | null {
  let worst: { name: string; value: number; n: number } | null = null;
  for (const [name, stratum] of Object.entries(perStratum)) {
    if (stratum.n === 0) continue;
    const measurement = stratum.metrics[metric];
    if (!measurement) continue;
    if (!worst || measurement.value < worst.value) {
      worst = { name, value: measurement.value, n: stratum.n };
    }
  }
  return worst;
}
