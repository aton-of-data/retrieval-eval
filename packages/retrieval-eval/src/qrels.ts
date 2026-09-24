import type { Judgment, RunEntry } from "./types.js";

/**
 * TREC qrels: `query_id iteration doc_id relevance`, whitespace separated. Thirty years of
 * tooling reads this (trec_eval, ir_measures, BEIR, ir_datasets), which is why judgments are
 * a strict superset of it rather than a new idea.
 */
export function toQrels(judgments: Judgment[]): string {
  const lines = judgments.map((j) => `${j.query_id} 0 ${j.chunk_id ?? j.doc_uri} ${j.relevance}`);
  return `${lines.join("\n")}\n`;
}

export interface FromQrelsOptions {
  /** Treat the qrels doc_id as a chunk_id rather than a doc_uri. */
  asChunkIds?: boolean;
  corpusFingerprint?: string;
  labeledBy?: string;
}

/**
 * Read qrels in either shape that exists in the wild:
 *
 *   `query_id iteration doc_id relevance`  the TREC form, 4 columns
 *   `query-id  corpus-id  score`           the BEIR form, 3 columns with a header row
 *
 * Accepting only the first means not being able to read BEIR or `ir_datasets` exports, which
 * is most of the reason to speak qrels at all.
 */
export function fromQrels(content: string, options: FromQrelsOptions = {}): Judgment[] {
  const out: Judgment[] = [];
  const lines = content.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = (lines[i] as string).trim();
    if (line === "" || line.startsWith("#")) continue;
    const parts = line.split(/\s+/);
    if (parts.length < 3)
      throw new Error(`qrels:${i + 1}: expected 3 or 4 fields, got ${parts.length}`);

    const [queryId, second, third, fourth] = parts as [string, string, string, string?];
    const docId = parts.length >= 4 ? third : second;
    const relevance = parts.length >= 4 ? (fourth as string) : third;
    const parsed = Number.parseInt(relevance, 10);
    if (Number.isNaN(parsed)) {
      // The BEIR header, `query-id corpus-id score`, is a row only by accident of format.
      if (out.length === 0 && /^query[-_ ]?id$/i.test(queryId)) continue;
      throw new Error(`qrels:${i + 1}: relevance '${relevance}' is not an integer`);
    }

    const judgment: Judgment = {
      query_id: queryId,
      doc_uri: docId,
      // Negative relevance appears in some TREC collections; clamp to the schema's minimum.
      relevance: Math.max(0, parsed),
    };
    if (options.asChunkIds) judgment.chunk_id = docId;
    if (options.corpusFingerprint) judgment.corpus_fingerprint = options.corpusFingerprint;
    if (options.labeledBy) judgment.labeled_by = options.labeledBy;
    out.push(judgment);
  }
  return out;
}

/** TREC run format: `query_id iteration doc_id rank score run_name`. */
export function toTrecRun(run: RunEntry[], runName = "retrieval-eval"): string {
  const lines: string[] = [];
  for (const entry of run) {
    entry.ranking.forEach((docId, index) => {
      const score = (entry.ranking.length - index).toFixed(4);
      lines.push(`${entry.query_id} Q0 ${docId} ${index + 1} ${score} ${runName}`);
    });
  }
  return `${lines.join("\n")}\n`;
}

export function fromTrecRun(content: string): RunEntry[] {
  const byQuery = new Map<string, { docId: string; rank: number }[]>();
  for (const raw of content.split("\n")) {
    const line = raw.trim();
    if (line === "" || line.startsWith("#")) continue;
    const parts = line.split(/\s+/);
    if (parts.length < 4) continue;
    const [queryId, , docId, rank] = parts as [string, string, string, string];
    const list = byQuery.get(queryId) ?? [];
    list.push({ docId, rank: Number.parseInt(rank, 10) });
    byQuery.set(queryId, list);
  }
  return [...byQuery.entries()].map(([queryId, rows]) => ({
    query_id: queryId,
    ranking: rows.sort((a, b) => a.rank - b.rank).map((r) => r.docId),
  }));
}
