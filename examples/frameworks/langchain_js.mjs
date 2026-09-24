/**
 * LangChain.js: emit a corpus snapshot and a run file from an existing chain.
 *
 * Written against @langchain/core 1.x, @langchain/textsplitters 1.x, @langchain/openai 1.x,
 * with the in-memory store so the example needs no database.
 *
 *   npm install @langchain/core @langchain/textsplitters @langchain/openai retrieval-eval
 *   node langchain_js.mjs
 *   npx retrieval-eval drift --judgments judgments.jsonl --corpus corpus.json
 */

import { writeFileSync } from "node:fs";
import { Document } from "@langchain/core/documents";
import { OpenAIEmbeddings } from "@langchain/openai";
import { RecursiveCharacterTextSplitter } from "@langchain/textsplitters";
import { MemoryVectorStore } from "langchain/vectorstores/memory";
import { chunkId, textSha } from "retrieval-eval";

const CHUNK_SIZE = 512;
const CHUNK_OVERLAP = 64;
// Changes when the chunking changes, which is what makes a re-chunk detectable.
const FINGERPRINT = `recursive/${CHUNK_SIZE}/${CHUNK_OVERLAP}`;

const splitter = new RecursiveCharacterTextSplitter({
  chunkSize: CHUNK_SIZE,
  chunkOverlap: CHUNK_OVERLAP,
});

/**
 * Chunk and index, stamping each chunk with its content-addressed id. The id lives in the
 * metadata so it survives the round trip through the store and comes back on every hit:
 * without it, a retrieval result cannot be joined to a label.
 */
export async function index(documents) {
  const chunks = await splitter.splitDocuments(documents);

  const ordinals = new Map();
  for (const chunk of chunks) {
    const docUri = chunk.metadata.doc_uri;
    const docRevision = chunk.metadata.doc_revision ?? "1";
    const ordinal = (ordinals.get(docUri) ?? -1) + 1;
    ordinals.set(docUri, ordinal);
    chunk.metadata.ordinal = ordinal;
    chunk.metadata.chunk_id = chunkId({
      docUri,
      docRevision,
      ordinal,
      text: chunk.pageContent,
      chunkerFingerprint: FINGERPRINT,
    });
  }

  const store = await MemoryVectorStore.fromDocuments(
    chunks,
    new OpenAIEmbeddings({ model: "text-embedding-3-small" }),
  );
  return { store, chunks };
}

/** Integration point 1: what the index currently contains. */
export function writeCorpus(chunks, path = "corpus.json") {
  const corpus = {
    corpus_fingerprint: FINGERPRINT,
    chunker_fingerprint: FINGERPRINT,
    chunks: chunks.map((chunk) => ({
      chunk_id: chunk.metadata.chunk_id,
      doc_uri: chunk.metadata.doc_uri,
      doc_revision: chunk.metadata.doc_revision ?? "1",
      ordinal: chunk.metadata.ordinal,
      text: chunk.pageContent,
      text_sha: textSha(chunk.pageContent),
    })),
  };
  writeFileSync(path, `${JSON.stringify(corpus, null, 2)}\n`, "utf8");
}

/** Integration point 2: what retrieval returned, in rank order, per query. */
export async function writeRun(store, queries, k = 5, path = "hits.jsonl") {
  const lines = [];
  for (const [queryId, query] of Object.entries(queries)) {
    const hits = await store.similaritySearch(query, k);
    lines.push(
      JSON.stringify({ query_id: queryId, ranking: hits.map((hit) => hit.metadata.chunk_id) }),
    );
  }
  writeFileSync(path, `${lines.join("\n")}\n`, "utf8");
}

const documents = [
  new Document({
    pageContent: "Annual plans may be refunded within 30 days of renewal.",
    metadata: { doc_uri: "help://billing/refunds", doc_revision: "2026-08-04" },
  }),
];

const { store, chunks } = await index(documents);
writeCorpus(chunks);
await writeRun(store, { q01: "can I get a refund on an annual plan?" });
console.log("wrote corpus.json and hits.jsonl");
