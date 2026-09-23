import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { drift, fix } from "../src/drift.js";
import { evaluateGates, parseGate } from "../src/gate.js";
import { chunkId, normalize, textSha } from "../src/identity.js";
import { parseCorpus, parseJudgments, parseRun, validate } from "../src/judgments.js";
import { score, scoreByStratum, worstStratum } from "../src/metrics.js";
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
