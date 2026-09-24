/**
 * Gate a judged metric without pretending its instrument is deterministic.
 *
 * Run: node demo.mjs
 *
 * Works from a fresh clone: if `retrieval-eval` is not installed, the in-repo build is used.
 * No model is called here. The judge's scores are a fixed table, because the point is what you
 * do with repeated samples, not how you obtain them.
 */

let lib;
try {
  lib = await import("retrieval-eval");
} catch {
  lib = await import("../../packages/retrieval-eval/dist/index.js");
}
const { buildReport, evaluateGates, parseGate, summarize } = lib;

// One human-labeled query per row, and the retrieval that answered it.
const judgments = [
  { query_id: "q1", doc_uri: "kb://refunds", relevance: 2, stratum: "billing" },
  { query_id: "q2", doc_uri: "kb://delivery", relevance: 2, stratum: "shipping" },
];
const run = [
  { query_id: "q1", ranking: ["kb://refunds", "kb://delivery"] },
  { query_id: "q2", ranking: ["kb://delivery", "kb://refunds"] },
];

// The same (question, context, answer) triple, scored five times by the same judge at
// temperature 0. This is not a contrived spread: tokenization, batching and backend routing all
// leak into the score, and 0.6 to 1.0 across five runs is an ordinary result.
const samples = [0.8, 1.0, 0.6, 0.9, 0.7];
const gates = ["recall@2:0.9", "faithfulness:ci-lower:0.8"].map(parseGate);

const pad = (text, width) => String(text).padEnd(width);
const fixed = (value) => value.toFixed(4);

const report = buildReport({ judgments, run, k: 2 });

console.log("\n  1. Retrieval, deterministic. Same inputs, same bytes, every run.\n");
for (const [name, measurement] of Object.entries(report.metrics)) {
  console.log(
    `     ${pad(name, 14)} ${fixed(measurement.value)}   n=${measurement.n} deterministic`,
  );
}

console.log("\n  2. The judge, sampled once. The number a dashboard would show.\n");
const single = summarize(samples.slice(0, 1));
console.log(`     faithfulness   ${fixed(single.value)}   n=1, no interval`);

report.metrics.faithfulness = single;
let verdict = evaluateGates({ report, gates });
console.log(`\n     ${verdict.status}`);
for (const reason of verdict.reasons) console.log(`     -> ${reason}`);

console.log(
  "\n  3. The same judge, sampled five times. Same model, same prompt, same temperature.\n",
);
console.log(`     samples        ${samples.map((s) => s.toFixed(2)).join(", ")}`);
const sampled = summarize(samples);
console.log(
  `     faithfulness   ${fixed(sampled.value)}   n=${sampled.n}  stdev=${fixed(sampled.stdev)}`,
);
console.log(`     95% interval   [${fixed(sampled.ci[0])}, ${fixed(sampled.ci[1])}]`);

report.metrics.faithfulness = sampled;
verdict = evaluateGates({ report, gates });
console.log(`\n     ${verdict.status}`);
for (const reason of verdict.reasons) console.log(`     -> ${reason}`);

console.log(
  "\n  One sample said 0.8000, which clears a 0.8 floor exactly.\n" +
    "  Five samples of the same judge, same prompt, same temperature, put the\n" +
    "  truth somewhere in [0.6037, 0.9963]. The floor is inside that interval,\n" +
    "  so the honest answer is that this build cannot be judged on this metric yet.\n",
);
