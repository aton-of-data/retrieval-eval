import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { drift, fix } from "../src/drift.js";
import { evaluateGates, parseGate, worseStatus } from "../src/gate.js";
import { chunkId, normalize, textSha } from "../src/identity.js";
import {
  byCodePoint,
  parseCorpus,
  parseJudgments,
  parseRun,
  serializeJudgments,
  validate,
} from "../src/judgments.js";
import { dedupe, score, scoreByStratum, summarize, worstStratum } from "../src/metrics.js";
import { fromQrels, toQrels } from "../src/qrels.js";
import { buildReport } from "../src/report.js";

const SPEC = join(import.meta.dirname, "..", "..", "..", "spec", "fixtures");
const load = (...parts: string[]): string => readFileSync(join(SPEC, ...parts), "utf8");
const loadJson = <T>(...parts: string[]): T => JSON.parse(load(...parts)) as T;

/** Fixtures are shared with the Python implementation, so both must agree to the 12th decimal. */
const closeTo = (actual: number, expected: number) => expect(actual).toBeCloseTo(expected, 10);

describe("chunk identity", () => {
  const expected = loadJson<{
    normalize: { in: string; out: string }[];
    text_sha: { text: string; out: string }[];
    chunk_id: {
      doc_uri: string;
      doc_revision: string;
      ordinal: number;
      text: string;
      chunker_fingerprint: string;
      out: string;
    }[];
  }>("chunk-id", "expected.json");

  it("normalizes exactly as the spec says", () => {
    for (const vector of expected.normalize) {
      expect(normalize(vector.in)).toBe(vector.out);
    }
  });

  it("matches the text_sha vectors", () => {
    for (const vector of expected.text_sha) {
      expect(textSha(vector.text)).toBe(vector.out);
    }
  });

  it("matches the chunk_id vectors", () => {
    for (const vector of expected.chunk_id) {
      expect(
        chunkId({
          docUri: vector.doc_uri,
          docRevision: vector.doc_revision,
          ordinal: vector.ordinal,
          text: vector.text,
          chunkerFingerprint: vector.chunker_fingerprint,
        }),
      ).toBe(vector.out);
    }
  });

  it("is stable across whitespace and unicode form", () => {
    const base = {
      docUri: "s3://b/k",
      docRevision: "v1",
      ordinal: 0,
      chunkerFingerprint: "recursive/512/64",
    };
    expect(chunkId({ ...base, text: "  café  " })).toBe(chunkId({ ...base, text: "café" }));
  });

  it("changes when the chunker configuration changes", () => {
    const base = { docUri: "s3://b/k", docRevision: "v1", ordinal: 0, text: "hello" };
    expect(chunkId({ ...base, chunkerFingerprint: "a" })).not.toBe(
      chunkId({ ...base, chunkerFingerprint: "b" }),
    );
  });
});

describe("metrics, basic fixture", () => {
  const judgments = parseJudgments(load("basic", "judgments.jsonl"));
  const run = parseRun(load("basic", "run.jsonl"));
  const expected = loadJson<{
    k: number;
    metrics: Record<string, number>;
    metrics_k1: Record<string, number>;
    per_query: Record<string, Record<string, number>>;
    qrels_lines: string[];
  }>("basic", "expected.json");

  it("reproduces the aggregate metrics at k=3", () => {
    const result = score(judgments, run, { k: 3 });
    for (const [name, value] of Object.entries(expected.metrics)) {
      closeTo(result.metrics[name]?.value ?? Number.NaN, value);
    }
  });

  it("reproduces the aggregate metrics at k=1", () => {
    const result = score(judgments, run, { k: 1 });
    for (const [name, value] of Object.entries(expected.metrics_k1)) {
      closeTo(result.metrics[name]?.value ?? Number.NaN, value);
    }
  });

  it("reproduces per-query metrics", () => {
    const result = score(judgments, run, { k: 3 });
    for (const [queryId, metrics] of Object.entries(expected.per_query)) {
      const actual = result.perQuery.get(queryId);
      expect(actual, queryId).toBeDefined();
      const actualRecord = actual as unknown as Record<string, number>;
      for (const [name, value] of Object.entries(metrics)) {
        closeTo(actualRecord[name] as number, value);
      }
    }
  });

  it("marks deterministic metrics as such", () => {
    const result = score(judgments, run, { k: 3 });
    for (const measurement of Object.values(result.metrics)) {
      expect(measurement.deterministic).toBe(true);
    }
  });

  it("scores a judged query with no run entry as zero rather than dropping it", () => {
    const result = score(judgments, [{ query_id: "q1", ranking: ["d3", "d1", "d2"] }], { k: 3 });
    expect(result.missingQueries).toEqual(["q2"]);
    expect(result.perQuery.get("q2")?.recall).toBe(0);
  });
});

describe("qrels interop", () => {
  const judgments = parseJudgments(load("basic", "judgments.jsonl"));
  const expected = loadJson<{ qrels_lines: string[] }>("basic", "expected.json");

  it("emits the TREC qrels format", () => {
    expect(toQrels(judgments).trim().split("\n")).toEqual(expected.qrels_lines);
  });

  it("round-trips through qrels without losing relevance", () => {
    const back = fromQrels(toQrels(judgments));
    expect(back.map((j) => [j.query_id, j.doc_uri, j.relevance])).toEqual(
      judgments.map((j) => [j.query_id, j.doc_uri, j.relevance]),
    );
  });

  it("clamps negative relevance found in some TREC collections", () => {
    expect(fromQrels("q1 0 d1 -1\n")[0]?.relevance).toBe(0);
  });

  it("ignores comments and blank lines", () => {
    expect(fromQrels("# header\n\nq1 0 d1 1\n")).toHaveLength(1);
  });
});

describe("queries with nothing relevant to find", () => {
  const judgments = parseJudgments(load("no-positives", "judgments.jsonl"));
  const run = parseRun(load("no-positives", "run.jsonl"));
  const expected = loadJson<{
    queries_scored: number;
    queries_without_positives: string[];
    metrics: Record<string, number>;
  }>("no-positives", "expected.json");

  it("excludes them from the averages rather than scoring them zero", () => {
    const result = score(judgments, run, { k: 3 });
    for (const [name, value] of Object.entries(expected.metrics)) {
      closeTo(result.metrics[name]?.value as number, value);
    }
  });

  it("names them, so the exclusion is visible rather than silent", () => {
    const result = score(judgments, run, { k: 3 });
    expect(result.queriesWithoutPositives).toEqual(expected.queries_without_positives);
  });

  it("reports how many queries the averages were computed from", () => {
    const report = buildReport({ judgments, run, k: 3 });
    expect(report.judgments.queries).toBe(2);
    expect(report.judgments.queries_scored).toBe(expected.queries_scored);
    expect(report.verdict.reasons.join(" ")).toContain("excluded from the averages");
  });

  it("follows the threshold: a graded label below it is not a positive", () => {
    const graded = parseJudgments('{"query_id":"q1","doc_uri":"d1","relevance":1}\n');
    const ranking = parseRun('{"query_id":"q1","ranking":["d1"]}\n');
    expect(score(graded, ranking, { k: 3 }).queriesWithoutPositives).toEqual([]);
    expect(score(graded, ranking, { k: 3, threshold: 2 }).queriesWithoutPositives).toEqual(["q1"]);
  });
});

describe("a stratum with nothing to score", () => {
  const judgments = parseJudgments(
    '{"query_id":"q1","doc_uri":"d1","relevance":2,"stratum":"answerable"}\n' +
      '{"query_id":"q2","doc_uri":"d2","relevance":1,"stratum":"context-only"}\n',
  );
  const run = parseRun('{"query_id":"q1","ranking":["d1"]}\n{"query_id":"q2","ranking":["d2"]}\n');

  it("reports n=0 rather than a zero score", () => {
    const perStratum = scoreByStratum(judgments, run, { k: 3, threshold: 2 });
    expect(perStratum["context-only"]?.n).toBe(0);
    expect(perStratum.answerable?.n).toBe(1);
  });

  it("is never the worst stratum, because it has no number to compare", () => {
    const perStratum = scoreByStratum(judgments, run, { k: 3, threshold: 2 });
    expect(worstStratum(perStratum, "recall@3")?.name).toBe("answerable");
  });

  it("cannot fail a worst-stratum gate on its own", () => {
    const report = buildReport({ judgments, run, k: 3, threshold: 2 });
    const evaluated = evaluateGates({
      report,
      gates: [parseGate("worst-stratum:recall@3:0.9")],
    });
    expect(evaluated.status).toBe("PASS");
  });
});

describe("summarize: error bars on a non-deterministic metric", () => {
  const fixture = loadJson<{
    cases: Record<string, { samples: number[]; expected: Record<string, unknown> }>;
  }>("summarize", "expected.json");

  for (const [name, testCase] of Object.entries(fixture.cases)) {
    it(name.replace(/_/g, " "), () => {
      const measurement = summarize(testCase.samples);
      const expected = testCase.expected as {
        value: number;
        n: number;
        stdev?: number;
        ci?: [number, number];
        deterministic: boolean;
      };

      closeTo(measurement.value, expected.value);
      expect(measurement.n).toBe(expected.n);
      expect(measurement.deterministic).toBe(false);

      if (expected.stdev === undefined) expect(measurement.stdev).toBeUndefined();
      else closeTo(measurement.stdev as number, expected.stdev);

      if (expected.ci === undefined) {
        expect(measurement.ci).toBeUndefined();
      } else {
        closeTo((measurement.ci as [number, number])[0], expected.ci[0]);
        closeTo((measurement.ci as [number, number])[1], expected.ci[1]);
      }
    });
  }

  it("refuses an empty sample set rather than inventing a zero", () => {
    expect(() => summarize([])).toThrow(/at least one sample/);
  });

  it("makes a ci-lower gate decidable, and INDETERMINATE when it is not", () => {
    const report = buildReport({ judgments: [], run: [], k: 5 });
    report.metrics.faithfulness = summarize([0.8, 1.0, 0.6, 0.9, 0.7]);
    expect(evaluateGates({ report, gates: [parseGate("faithfulness:ci-lower:0.8")] }).status).toBe(
      "FAIL",
    );

    report.metrics.faithfulness = summarize([0.82]);
    expect(evaluateGates({ report, gates: [parseGate("faithfulness:ci-lower:0.8")] }).status).toBe(
      "INDETERMINATE",
    );
  });

  it("does not raise a negative lower bound, so a boundary gate cannot pass by clamping", () => {
    const report = buildReport({ judgments: [], run: [], k: 5 });
    report.metrics.faithfulness = summarize([0, 0, 1]);
    const evaluated = evaluateGates({ report, gates: [parseGate("faithfulness:ci-lower:0")] });
    expect(evaluated.status).toBe("FAIL");
    expect(report.metrics.faithfulness?.ci?.[0]).toBeLessThan(0);
  });
});

describe("nothing scored: an empty average is not a zero", () => {
  const expected = loadJson<{
    queries: number;
    queries_scored: number;
    status: "INDETERMINATE";
    reason: string;
    gate_reason: string;
    threshold: number;
  }>("nothing-scored", "expected.json");
  const judgments = parseJudgments(load("nothing-scored", "judgments.jsonl"));
  const run = parseRun(load("nothing-scored", "run.jsonl"));

  it("omits the metrics instead of emitting zero", () => {
    const result = score(judgments, run, { k: 3, threshold: expected.threshold });
    expect(result.metrics).toEqual({});
    expect(result.queriesWithoutPositives).toEqual(["q1"]);
  });

  it("does not say an excluded query scored zero when the run is also missing", () => {
    const report = buildReport({
      judgments: parseJudgments('{"query_id":"q1","doc_uri":"d1","relevance":0}\n'),
      run: [],
    });
    expect(report.verdict.reasons.join(" ")).not.toMatch(/scored zero/);
  });

  it("is INDETERMINATE, and an absolute gate cannot fail at 0.0000", () => {
    const report = buildReport({ judgments, run, k: 3, threshold: expected.threshold });
    expect(report.judgments.queries).toBe(expected.queries);
    expect(report.judgments.queries_scored).toBe(expected.queries_scored);
    expect(report.verdict.status).toBe(expected.status);
    expect(report.verdict.reasons).toContain(expected.reason);
    expect(report.per_stratum?.billing?.n).toBe(0);
    expect(report.per_stratum?.billing?.metrics).toEqual({});

    const evaluated = evaluateGates({ report, gates: [parseGate("recall@3:0.5")] });
    expect(evaluated.status).toBe("INDETERMINATE");
    expect(evaluated.reasons).toContain(expected.gate_reason);

    const worst = evaluateGates({ report, gates: [parseGate("worst-stratum:recall@3:0.5")] });
    expect(worst.status).toBe("INDETERMINATE");
    expect(worst.reasons).toEqual([
      "worst-stratum:recall@3:0.5: no stratum was scored for 'recall@3'",
    ]);
  });
});

describe("canonical serialization", () => {
  const line = '{"stratum":"legal","relevance":2,"doc_uri":"d1","query_id":"q1","house":{"a":1}}';

  it("writes schema order, then unknown fields, compactly", () => {
    expect(serializeJudgments(parseJudgments(line)).trim()).toBe(
      '{"query_id":"q1","doc_uri":"d1","relevance":2,"stratum":"legal","house":{"a":1}}',
    );
  });

  it("is idempotent, so a rewrite is a diff of the labels that changed", () => {
    const once = serializeJudgments(parseJudgments(line));
    expect(serializeJudgments(parseJudgments(once))).toBe(once);
  });
});

describe("qrels: the two shapes that exist in the wild", () => {
  const expected = loadJson<{
    beir: { query_id: string; doc_uri: string; relevance: number }[];
    trec: { query_id: string; doc_uri: string; relevance: number }[];
  }>("qrels", "expected.json");

  const shape = (judgments: ReturnType<typeof fromQrels>) =>
    judgments.map((j) => ({
      query_id: j.query_id,
      doc_uri: j.doc_uri,
      relevance: j.relevance,
    }));

  it("reads the BEIR form: three columns behind a header row", () => {
    expect(shape(fromQrels(load("qrels", "beir.tsv")))).toEqual(expected.beir);
  });

  it("reads the TREC form: four columns, comments, negative grades clamped", () => {
    expect(shape(fromQrels(load("qrels", "trec.qrels")))).toEqual(expected.trec);
  });

  it("emits the TREC form from either", () => {
    expect(
      toQrels(fromQrels(load("qrels", "beir.tsv")))
        .trim()
        .split("\n"),
    ).toEqual(loadJson<{ qrels_lines: string[] }>("qrels", "expected.json").qrels_lines);
  });

  it("still rejects a row that is neither shape", () => {
    expect(() => fromQrels("q1 d1\n")).toThrow(/expected 3 or 4 fields/);
    expect(() => fromQrels("q1 0 d1 high\n")).toThrow(/not an integer/);
  });
});

describe("strata: averages hide broken query classes", () => {
  const judgments = parseJudgments(load("strata", "judgments.jsonl"));
  const run = parseRun(load("strata", "run.jsonl"));
  const expected = loadJson<{
    metrics: Record<string, number>;
    per_stratum: Record<string, { n: number; metrics: Record<string, number> }>;
    worst_stratum: { metric: string; name: string; value: number };
  }>("strata", "expected.json");

  it("reproduces the overall metrics", () => {
    const result = score(judgments, run, { k: 3 });
    closeTo(
      result.metrics["recall@3"]?.value ?? Number.NaN,
      expected.metrics["recall@3"] as number,
    );
  });

  it("reproduces per-stratum metrics and counts", () => {
    const perStratum = scoreByStratum(judgments, run, { k: 3 });
    for (const [name, stratum] of Object.entries(expected.per_stratum)) {
      expect(perStratum[name]?.n, name).toBe(stratum.n);
      closeTo(
        perStratum[name]?.metrics["recall@3"]?.value ?? Number.NaN,
        stratum.metrics["recall@3"] as number,
      );
    }
  });

  it("identifies the worst stratum", () => {
    const perStratum = scoreByStratum(judgments, run, { k: 3 });
    const worst = worstStratum(perStratum, expected.worst_stratum.metric);
    expect(worst?.name).toBe(expected.worst_stratum.name);
    closeTo(worst?.value ?? Number.NaN, expected.worst_stratum.value);
  });

  it("passes an average gate while failing the worst-stratum gate", () => {
    const report = buildReport({ judgments, run, k: 3 });
    const evaluated = evaluateGates({
      report,
      gates: [parseGate("recall@3:0.5"), parseGate("worst-stratum:recall@3:0.5")],
    });
    expect(evaluated.results[0]?.status).toBe("PASS");
    expect(evaluated.results[1]?.status).toBe("FAIL");
    expect(evaluated.status).toBe("FAIL");
  });
});

describe("drift: which labels are still true", () => {
  const judgments = parseJudgments(load("drift", "judgments.jsonl"));
  const corpus = parseCorpus(load("drift", "corpus.json"));
  const expected = loadJson<{
    statuses: Record<string, string>;
    summary: Record<string, number>;
    reanchor: Record<string, string>;
    split_into: Record<string, string[]>;
  }>("drift", "expected.json");

  const result = drift(judgments, corpus);
  const byQuery = new Map(result.findings.map((f) => [f.query_id, f]));

  it("classifies every judgment as the fixture expects", () => {
    for (const [queryId, status] of Object.entries(expected.statuses)) {
      expect(byQuery.get(queryId)?.status, queryId).toBe(status);
    }
  });

  it("reproduces the summary", () => {
    expect(result.summary.valid).toBe(expected.summary.valid);
    expect(result.summary.re_anchorable).toBe(expected.summary.re_anchorable);
    expect(result.summary.split).toBe(expected.summary.split);
    expect(result.summary.orphaned).toBe(expected.summary.orphaned);
    closeTo(result.summary.invalid_ratio, expected.summary.invalid_ratio as number);
  });

  it("points re-anchorable labels at the right live chunk", () => {
    for (const [queryId, chunk] of Object.entries(expected.reanchor)) {
      expect(byQuery.get(queryId)?.reanchor_to, queryId).toBe(chunk);
    }
  });

  it("reports every chunk a split label now spans", () => {
    for (const [queryId, chunks] of Object.entries(expected.split_into)) {
      expect(byQuery.get(queryId)?.split_into, queryId).toEqual(chunks);
    }
  });

  it("re-anchors recoverable labels and refuses to guess the rest", () => {
    const fixed = fix(judgments, result);
    expect(fixed.reanchored).toBe(1);
    // SPLIT and ORPHANED are left for a human: guessing would fabricate ground truth.
    expect(fixed.needsReview.map((f) => f.status).sort()).toEqual(["ORPHANED", "SPLIT"]);

    const reanchored = drift(fixed.judgments, corpus);
    expect(reanchored.summary.re_anchorable).toBe(0);
    expect(reanchored.summary.valid).toBe(2);
  });

  it("is idempotent", () => {
    const once = fix(judgments, result);
    const twice = fix(once.judgments, drift(once.judgments, corpus));
    expect(twice.reanchored).toBe(0);
  });

  it("reports a clean corpus as fully valid", () => {
    const self = corpus.chunks.map((chunk, index) => ({
      query_id: `q${index}`,
      doc_uri: chunk.doc_uri,
      chunk_id: chunk.chunk_id,
      relevance: 1,
    }));
    const clean = drift(self, corpus);
    expect(clean.summary.invalid_ratio).toBe(0);
    expect(clean.summary.valid).toBe(corpus.chunks.length);
  });
});

describe("drift: a re-chunk that merges paragraphs", () => {
  // The mirror of a split, found by running examples/quickstart: raising chunk_size absorbs a
  // labeled paragraph into a coarser chunk. Reporting that as ORPHANED would be wrong, since
  // the text is plainly still there, and wrong in a way that teaches people to distrust the tool.
  const judgments = parseJudgments(load("merge", "judgments.jsonl"));
  const corpus = parseCorpus(load("merge", "corpus.json"));
  const expected = loadJson<{
    statuses: Record<string, string>;
    summary: Record<string, number>;
    reanchor: Record<string, string>;
  }>("merge", "expected.json");

  const result = drift(judgments, corpus);
  const byQuery = new Map(result.findings.map((f) => [f.query_id, f]));

  it("classifies merged labels as MERGED, not ORPHANED", () => {
    for (const [queryId, status] of Object.entries(expected.statuses)) {
      expect(byQuery.get(queryId)?.status, queryId).toBe(status);
    }
    expect(result.summary.orphaned).toBe(0);
  });

  it("reproduces the summary", () => {
    expect(result.summary.merged).toBe(expected.summary.merged);
    expect(result.summary.re_anchorable).toBe(expected.summary.re_anchorable);
  });

  it("re-anchors two labels onto the same coarser chunk", () => {
    for (const [queryId, chunk] of Object.entries(expected.reanchor)) {
      expect(byQuery.get(queryId)?.reanchor_to, queryId).toBe(chunk);
    }
    expect(byQuery.get("m1")?.reanchor_to).toBe(byQuery.get("m2")?.reanchor_to);
  });

  it("fixes every label, because merged text is recoverable", () => {
    const fixed = fix(judgments, result);
    expect(fixed.reanchored).toBe(3);
    expect(fixed.needsReview).toHaveLength(0);
    expect(drift(fixed.judgments, corpus).summary.invalid_ratio).toBe(0);
  });
});

describe("validate", () => {
  it("accepts the fixtures", () => {
    expect(validate(parseJudgments(load("basic", "judgments.jsonl"))).ok).toBe(true);
  });

  it("rejects a judgment set with no positives", () => {
    const result = validate([{ query_id: "q1", query: "q", doc_uri: "d1", relevance: 0 }]);
    expect(result.ok).toBe(false);
    expect(result.issues.some((i) => i.code === "no-positives")).toBe(true);
  });

  it("rejects duplicate labels", () => {
    const row = { query_id: "q1", query: "q", doc_uri: "d1", relevance: 1 };
    expect(validate([row, { ...row }]).issues.some((i) => i.code === "duplicate-label")).toBe(true);
  });

  it("warns when every label is synthetic", () => {
    const result = validate([
      { query_id: "q1", query: "q", doc_uri: "d1", relevance: 1, labeled_by: "synthetic:haiku" },
    ]);
    expect(result.issues.some((i) => i.code === "no-human-labels")).toBe(true);
    expect(result.ok).toBe(true);
  });

  it("warns when judgments span several corpus fingerprints", () => {
    const result = validate([
      { query_id: "q1", query: "a", doc_uri: "d1", relevance: 1, corpus_fingerprint: "a" },
      { query_id: "q2", query: "b", doc_uri: "d2", relevance: 1, corpus_fingerprint: "b" },
    ]);
    expect(result.issues.some((i) => i.code === "mixed-fingerprints")).toBe(true);
  });

  it("rejects a malformed chunk_id", () => {
    const result = validate([
      { query_id: "q1", query: "q", doc_uri: "d1", relevance: 1, chunk_id: "c1:nope" },
    ]);
    expect(result.issues.some((i) => i.code === "bad-chunk-id")).toBe(true);
  });
});

describe("gates", () => {
  it("parses all four forms", () => {
    expect(parseGate("recall@5:0.8").kind).toBe("absolute");
    expect(parseGate("recall@5:-0.02").kind).toBe("delta");
    expect(parseGate("worst-stratum:recall@5:0.7").kind).toBe("worst-stratum");
    expect(parseGate("faithfulness:ci-lower:0.8").kind).toBe("ci-lower");
  });

  it("rejects nonsense", () => {
    expect(() => parseGate("recall@5")).toThrow();
    expect(() => parseGate("recall@5:abc")).toThrow();
  });

  const report = buildReport({
    judgments: parseJudgments(load("basic", "judgments.jsonl")),
    run: parseRun(load("basic", "run.jsonl")),
    k: 3,
  });

  it("is INDETERMINATE for a delta gate with no baseline", () => {
    const evaluated = evaluateGates({ report, gates: [parseGate("recall@3:-0.02")] });
    expect(evaluated.status).toBe("INDETERMINATE");
  });

  it("fails a delta gate when the metric regressed", () => {
    const baseline = structuredClone(report);
    baseline.metrics["recall@3"] = { value: 0.9 };
    const evaluated = evaluateGates({ report, baseline, gates: [parseGate("recall@3:-0.02")] });
    expect(evaluated.status).toBe("FAIL");
    expect(evaluated.reasons[0]).toContain("recall@3 fell");
  });

  it("is INDETERMINATE for a ci-lower gate on a single-sample metric", () => {
    const evaluated = evaluateGates({ report, gates: [parseGate("recall@3:ci-lower:0.5")] });
    expect(evaluated.status).toBe("INDETERMINATE");
    expect(evaluated.reasons[0]).toContain("sample it more than once");
  });

  it("is INDETERMINATE for an unknown metric rather than silently passing", () => {
    const evaluated = evaluateGates({ report, gates: [parseGate("nonexistent@3:0.5")] });
    expect(evaluated.status).toBe("INDETERMINATE");
  });
});

describe("report", () => {
  it("validates against the shape the spec requires", () => {
    const report = buildReport({
      judgments: parseJudgments(load("strata", "judgments.jsonl")),
      run: parseRun(load("strata", "run.jsonl")),
      k: 3,
    });
    expect(report.spec_version).toBe("1");
    expect(report.tool.name).toBe("retrieval-eval");
    // per_stratum is mandatory once judgments carry strata.
    expect(report.per_stratum).toBeDefined();
    expect(Object.keys(report.per_stratum ?? {}).sort()).toEqual(["billing", "legal"]);
  });

  it("surfaces label decay in the verdict even with no gates", () => {
    const judgments = parseJudgments(load("drift", "judgments.jsonl"));
    const corpus = parseCorpus(load("drift", "corpus.json"));
    const report = buildReport({
      judgments,
      run: [],
      corpus,
      driftResult: drift(judgments, corpus),
    });
    expect(report.judgments.drift?.invalid_ratio).toBeGreaterThan(0);
    expect(report.verdict.reasons.join(" ")).toContain("no longer match");
  });
});

describe("a ranking that repeats a key", () => {
  const judgments = parseJudgments(load("duplicate-ranking", "judgments.jsonl"));
  const run = parseRun(load("duplicate-ranking", "run.jsonl"));
  const expected = loadJson<{
    queries_with_duplicates: string[];
    deduped_rankings: Record<string, string[]>;
    metrics: Record<string, number>;
    reason: string;
    rejected: { cases: { file: string; message: string }[] };
  }>("duplicate-ranking", "expected.json");

  it("counts a repeated key once, so no metric leaves its range", () => {
    const result = score(judgments, run, { k: 5 });
    for (const [name, value] of Object.entries(expected.metrics)) {
      closeTo(result.metrics[name]?.value as number, value);
    }
    // The bug this fixture exists for: naively, q1 returning d1 five times scores recall 2.5.
    expect(result.metrics["recall@5"]?.value as number).toBeLessThanOrEqual(1);
  });

  it("keeps the first occurrence and drops the rest", () => {
    for (const [queryId, ranking] of Object.entries(expected.deduped_rankings)) {
      const entry = run.find((r) => r.query_id === queryId);
      expect(dedupe(entry?.ranking as string[])).toEqual(ranking);
    }
  });

  it("names the queries it corrected rather than correcting them silently", () => {
    expect(score(judgments, run, { k: 5 }).queriesWithDuplicates).toEqual(
      expected.queries_with_duplicates,
    );
    expect(buildReport({ judgments, run, k: 5 }).verdict.reasons).toContain(expected.reason);
  });

  it("cannot carry a failing run past a gate", () => {
    const report = buildReport({ judgments, run, k: 5 });
    // Truthful recall is 0.75. Counted with the repeats it was 2.5, which cleared this floor.
    expect(evaluateGates({ report, gates: [parseGate("recall@5:0.9")] }).status).toBe("FAIL");
  });

  it("rejects a run that is malformed rather than merely unsound", () => {
    for (const { file, message } of expected.rejected.cases) {
      expect(() => parseRun(load("duplicate-ranking", file))).toThrow(message);
    }
  });
});

describe("a judgment set validate rejects", () => {
  const judgments = parseJudgments(load("unsound-judgments", "judgments.jsonl"));
  const run = parseRun(load("unsound-judgments", "run.jsonl"));
  const expected = loadJson<{
    validate: { ok: boolean; error_codes: string[] };
    verdict: string;
    reason: string;
    gate: { expression: string; gate_status: string; verdict: string };
  }>("unsound-judgments", "expected.json");

  it("is an error, not a warning", () => {
    const result = validate(judgments);
    expect(result.ok).toBe(expected.validate.ok);
    expect(
      [...new Set(result.issues.filter((i) => i.severity === "error").map((i) => i.code))].sort(),
    ).toEqual(expected.validate.error_codes);
  });

  it("cannot be scored to a PASS, because the ground truth contradicts itself", () => {
    const report = buildReport({ judgments, run, k: 2 });
    expect(report.verdict.status).toBe(expected.verdict);
    expect(report.verdict.reasons).toContain(expected.reason);
  });

  it("is not cleared by a gate that happens to pass", () => {
    const report = buildReport({ judgments, run, k: 2 });
    const evaluated = evaluateGates({ report, gates: [parseGate(expected.gate.expression)] });
    expect(evaluated.status).toBe(expected.gate.gate_status);
    expect(worseStatus(report.verdict.status, evaluated.status)).toBe(expected.gate.verdict);
  });
});

describe("orderings that reach the output", () => {
  const judgments = parseJudgments(load("unsorted-queries", "judgments.jsonl"));
  const expected = loadJson<{
    missing_query_text_order: string[];
    thin_stratum_order: string[];
    issue_order: string[];
  }>("unsorted-queries", "expected.json");

  // Insertion order here and sorted order in Python is a parity break that no fixture with
  // already-sorted ids can catch, which is why this one arrives deliberately out of order.
  it("reports missing query text sorted, not in file order", () => {
    const issues = validate(judgments).issues.filter((i) => i.code === "missing-query-text");
    expect(issues.map((i) => i.message.split(" ")[1])).toEqual(expected.missing_query_text_order);
  });

  it("reports thin strata sorted, not in insertion order", () => {
    const issues = validate(judgments).issues.filter((i) => i.code === "thin-stratum");
    expect(issues.map((i) => i.message.split("'")[1])).toEqual(expected.thin_stratum_order);
  });

  it("sorts by code point, which is what Python's sorted does", () => {
    // Above the BMP the JS default comparator disagrees with Python: "\u{1f600}" sorts before
    // "" by UTF-16 code unit and after it by code point.
    expect(["\u{1f600}", ""].sort(byCodePoint)).toEqual(["", "\u{1f600}"]);
  });
});

describe("gate thresholds both implementations must read the same way", () => {
  // `parseFloat` took '0.5abc' as 0.5 while Python's `float` rejected it, and Python's `float`
  // took 'nan' and 'infinity' while `parseFloat` rejected them. Three silent disagreements
  // about what a gate means.
  for (const bad of ["0.5abc", "nan", "infinity", "inf", "1d0", ""]) {
    it(`rejects '${bad}'`, () => {
      expect(() => parseGate(`recall@5:${bad}`)).toThrow("is not a number");
    });
  }

  for (const [good, value] of [
    ["0.8", 0.8],
    ["-0.02", -0.02],
    ["1e-1", 0.1],
    [".5", 0.5],
    ["+1", 1],
  ] as const) {
    it(`accepts '${good}'`, () => {
      expect(parseGate(`recall@5:${good}`).threshold).toBeCloseTo(value, 12);
    });
  }
});

describe("stratum table ordering", () => {
  const judgments = parseJudgments(load("stratum-order", "judgments.jsonl"));
  const run = parseRun(load("stratum-order", "run.jsonl"));
  const expected = loadJson<{
    scored_order: string[];
    unscored_order: string[];
    locale_order_would_be: string[];
    per_stratum_n: Record<string, number>;
  }>("stratum-order", "expected.json");

  it("breaks ties by code point, not by locale collation", () => {
    const perStratum = scoreByStratum(judgments, run, { k: 3, threshold: 2 });
    const scored = Object.entries(perStratum)
      .filter(([, stratum]) => stratum.n > 0)
      .map(([name]) => name)
      .sort(byCodePoint);
    const unscored = Object.entries(perStratum)
      .filter(([, stratum]) => stratum.n === 0)
      .map(([name]) => name)
      .sort(byCodePoint);

    expect(scored).toEqual(expected.scored_order);
    expect(unscored).toEqual(expected.unscored_order);
    // These names were chosen so the two orderings disagree. What `localeCompare` actually
    // returns depends on the machine's locale, which is the whole objection to it, so that is
    // asserted as "different" rather than pinned to one machine's answer.
    const names = [...scored, ...unscored];
    expect([...names].sort((a, b) => a.localeCompare(b))).not.toEqual([...names].sort(byCodePoint));
  });

  it("counts each stratum's scored queries", () => {
    const perStratum = scoreByStratum(judgments, run, { k: 3, threshold: 2 });
    for (const [name, n] of Object.entries(expected.per_stratum_n)) {
      expect(perStratum[name]?.n).toBe(n);
    }
  });
});
