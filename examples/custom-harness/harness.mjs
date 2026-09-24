/**
 * Evaluation inside your own test suite, with no CLI involved.
 *
 * Run: node harness.mjs
 *
 * The CLI is a thin layer over these functions. When evaluation belongs inside vitest, a nightly
 * job or a service, call them directly: same numbers, same guarantees, no subprocess.
 *
 * Reads the support-bot example's data, so the numbers match what `retrieval-eval score` prints
 * for the same files.
 */

import { readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

let lib;
try {
  lib = await import("retrieval-eval");
} catch {
  lib = await import("../../packages/retrieval-eval/dist/index.js");
}
const {
  buildReport,
  drift,
  evaluateGates,
  fromTrecRun,
  parseCorpus,
  parseGate,
  parseJudgments,
  parseRun,
  queryMetrics,
  relevanceByQuery,
  scoreByStratum,
  serializeJudgments,
  summarize,
  toQrels,
  toTrecRun,
  validate,
  worstStratum,
} = lib;

const DATA = join(dirname(fileURLToPath(import.meta.url)), "..", "support-bot");
const K = 3;
const read = (name) => readFileSync(join(DATA, name), "utf8");

const judgments = parseJudgments(read("judgments.jsonl"));
const run = parseRun(read("hits.jsonl"));
const corpus = parseCorpus(read("corpus.json"));

console.log("\n  1. Refuse to measure with a judgment set you have not checked.\n");
const validation = validate(judgments);
console.log(`     ${validation.labels} labels, ${validation.queries} queries, ok=${validation.ok}`);
for (const issue of validation.issues.slice(0, 2)) {
  console.log(`     ${issue.severity}: [${issue.code}]`);
}
if (!validation.ok) throw new Error("judgment set has errors");

console.log("\n  2. Per-query metrics: which queries are actually failing, not just the mean.\n");
const relevance = relevanceByQuery(judgments);
const perQuery = [...relevance.entries()].map(([queryId, grades]) => [
  queryId,
  queryMetrics(grades, run.find((entry) => entry.query_id === queryId)?.ranking ?? [], { k: K }),
]);
for (const [queryId, metrics] of perQuery.sort((a, b) => a[1].recall - b[1].recall).slice(0, 3)) {
  const query = judgments.find((j) => j.query_id === queryId && j.query)?.query;
  console.log(`     ${queryId}  recall=${metrics.recall.toFixed(2)}  ${query}`);
}

console.log("\n  3. Per-stratum, and the class a gate should watch.\n");
const perStratum = scoreByStratum(judgments, run, { k: K });
const worst = worstStratum(perStratum, `recall@${K}`);
for (const [name, stratum] of Object.entries(perStratum).sort()) {
  const mark = name === worst.name ? "  <- worst" : "";
  const value = stratum.metrics[`recall@${K}`].value.toFixed(4);
  console.log(`     ${name.padEnd(10)} recall@${K}=${value}  n=${stratum.n}${mark}`);
}

console.log("\n  4. A report, a judged metric beside the deterministic ones, and gates.\n");
const report = buildReport({ judgments, run, k: K, corpus, driftResult: drift(judgments, corpus) });
report.metrics.faithfulness = summarize([0.91, 0.88, 0.95, 0.9]);
const verdict = evaluateGates({
  report,
  gates: [`recall@${K}:0.7`, `worst-stratum:recall@${K}:0.6`, "faithfulness:ci-lower:0.8"].map(
    parseGate,
  ),
});
report.verdict.status = verdict.status;
report.verdict.gates = verdict.results;
for (const gate of verdict.results) {
  console.log(`     ${gate.status.padEnd(13)} ${gate.expression}`);
}
console.log(`     verdict: ${verdict.status}`);

writeFileSync("report.json", `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log("     wrote report.json, the same shape the CLI writes with --out");

console.log("\n  5. Hand the same labels to the thirty-year-old tooling, and read its run back.\n");
const qrels = toQrels(judgments);
const trecRun = toTrecRun(run);
console.log(`     qrels line   ${qrels.split("\n")[0]}`);
console.log(`     run line     ${trecRun.split("\n")[0]}`);
const recovered = fromTrecRun(trecRun);
const preserved = JSON.stringify(recovered[0].ranking) === JSON.stringify(run[0].ranking);
console.log(`     read back    ${recovered.length} queries, ranking order preserved: ${preserved}`);

console.log("\n  6. Write the labels back out, canonically.\n");
const canonical = serializeJudgments(judgments);
console.log(
  `     ${canonical.trimEnd().split("\n").length} lines, byte-identical in either implementation`,
);
console.log(`     first: ${canonical.split("\n")[0].slice(0, 72)}...`);

console.log(
  "\n  The CLI does 1, 3, 4 and 5 for you. Steps 2 and 6 are why the library is public:\n" +
    "  per-query detail belongs in your own reporting, and a canonical writer lets you\n" +
    "  generate and repair judgment files from your own tooling.\n",
);
unlinkSync("report.json");
