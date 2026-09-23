// Watch a golden set decay when you change your chunker.
// Run: node demo.mjs
//
// Works from a fresh clone: if `retrieval-eval` is not installed, the in-repo build is used.
let lib;
try {
  lib = await import("retrieval-eval");
} catch {
  try {
    lib = await import("../../packages/retrieval-eval/dist/index.js");
  } catch {
    console.error(
      "retrieval-eval is not installed and the in-repo build is missing.\n" +
        "Run `pnpm install && pnpm -r build` from the repo root, or `npm install retrieval-eval`.",
    );
    process.exit(2);
  }
}
const { chunkId, drift, fix, score, textSha } = lib;

// ── a tiny corpus ────────────────────────────────────────────────────────────
const DOCS = [
  {
    uri: "wiki://refunds",
    revision: "r3",
    paragraphs: [
      "Annual plans may be refunded within 30 days of renewal.",
      "Monthly plans are non-refundable after the billing date.",
      "Enterprise refunds are negotiated per contract.",
    ],
  },
  {
    uri: "wiki://billing",
    revision: "r1",
    paragraphs: [
      "Invoices are issued on the first business day of each month.",
      "Failed payments retry three times over six days.",
    ],
  },
];

/**
 * A stand-in for a real chunker. `size` controls how many paragraphs go in a chunk, which is
 * enough to reproduce the only thing that matters here: the same text landing in different
 * chunks under a different configuration.
 */
function chunkCorpus(size, fingerprint) {
  const chunks = [];
  for (const doc of DOCS) {
    for (let i = 0, ordinal = 0; i < doc.paragraphs.length; i += size, ordinal++) {
      const text = doc.paragraphs.slice(i, i + size).join("\n\n");
      chunks.push({
        chunk_id: chunkId({
          docUri: doc.uri,
          docRevision: doc.revision,
          ordinal,
          text,
          chunkerFingerprint: fingerprint,
        }),
        doc_uri: doc.uri,
        doc_revision: doc.revision,
        ordinal,
        text,
        text_sha: textSha(text),
      });
    }
  }
  return { corpus_fingerprint: fingerprint, chunker_fingerprint: fingerprint, chunks };
}

// ── 1. chunk at "512 tokens": one paragraph per chunk ────────────────────────
const before = chunkCorpus(1, "recursive/512");

// ── 2. a human labels 4 chunks as relevant ───────────────────────────────────
const label = (queryId, query, chunk, relevance, stratum) => ({
  query_id: queryId,
  query,
  doc_uri: chunk.doc_uri,
  chunk_id: chunk.chunk_id,
  text_sha: chunk.text_sha,
  chunk_text: chunk.text,
  relevance,
  corpus_fingerprint: before.corpus_fingerprint,
  labeled_by: "human:ana",
  stratum,
});

const judgments = [
  label("q1", "annual plan refund window", before.chunks[0], 2, "refunds"),
  label("q2", "are monthly plans refundable", before.chunks[1], 2, "refunds"),
  label("q3", "enterprise refund policy", before.chunks[2], 1, "refunds"),
  label("q4", "when are invoices issued", before.chunks[3], 2, "billing"),
];

/**
 * A flawless retriever: for every query it returns the live chunk holding the answer.
 *
 * Modelling retrieval as perfect is the point of the demo. Any metric movement below cannot be
 * the retriever's fault, because the retriever never makes a mistake.
 */
function perfectRun(corpus, labels) {
  return labels.map((j) => {
    const wanted = (j.chunk_text ?? "").trim();
    const hit = corpus.chunks.find((c) => (c.text ?? "").includes(wanted));
    return { query_id: j.query_id, ranking: hit ? [hit.chunk_id] : [] };
  });
}

const recallOn = (corpus, labels) =>
  score(labels, perfectRun(corpus, labels), { k: 3 }).metrics["recall@3"].value;

const baseline = recallOn(before, judgments);
console.log(`\n  1. chunked @ ${before.chunker_fingerprint}`);
console.log(`     recall@3 = ${baseline.toFixed(4)}   <- your baseline, retrieval is perfect\n`);

// ── 3. re-chunk at "384 tokens": two paragraphs per chunk ────────────────────
const after = chunkCorpus(2, "recursive/384");
console.log(`  2. re-chunked @ ${after.chunker_fingerprint}`);
console.log("     the corpus text is byte-for-byte identical. Only the chunking changed.");
console.log("     retrieval is still perfect: it returns the chunk holding the answer.\n");

// ── 4. the metric collapses, and the naive reading is "my change broke retrieval" ──
const stale = recallOn(after, judgments);
console.log(
  `     recall@3 = ${stale.toFixed(4)}   <- a ${(baseline - stale).toFixed(2)} collapse, and the retriever`,
);
console.log("                            did nothing wrong. Your labels point at ids");
console.log("                            that no longer exist.");

// ── 5. ask what actually happened ────────────────────────────────────────────
const result = drift(judgments, after);
console.log("\n  3. drift against the live corpus:");
console.log(`     VALID          ${result.summary.valid}`);
console.log(`     RE_ANCHORABLE  ${result.summary.re_anchorable}`);
console.log(`     MERGED         ${result.summary.merged}`);
console.log(`     SPLIT          ${result.summary.split}`);
console.log(`     ORPHANED       ${result.summary.orphaned}`);
console.log(
  `     -> ${(result.summary.invalid_ratio * 100).toFixed(0)}% of your labels no longer match the corpus\n`,
);

for (const finding of result.findings) {
  const detail = finding.reanchor_to
    ? `-> ${finding.reanchor_to.slice(0, 14)}...`
    : finding.split_into
      ? `-> spans ${finding.split_into.length} chunks`
      : "";
  console.log(`     ${finding.query_id}  ${finding.status.padEnd(14)} ${detail}`);
}

// ── 6. recover what can be recovered, refuse to invent the rest ──────────────
const fixed = fix(judgments, result);
console.log(`\n  4. --fix re-anchored ${fixed.reanchored} label(s).`);
console.log(
  `     ${fixed.needsReview.length} still need a human; SPLIT and ORPHANED are never guessed.`,
);

const restored = recallOn(after, fixed.judgments);
console.log(`\n     recall@3 = ${restored.toFixed(4)}   <- back where it started, because nothing`);
console.log("                            about retrieval had changed in the first place.");
console.log(
  `\n     Without step 4, you would have chased a ${(baseline - stale).toFixed(2)} regression`,
);
console.log("     that never existed.\n");
