import { normalize, textSha } from "./identity.js";
import type {
  Corpus,
  CorpusChunk,
  DriftFinding,
  DriftResult,
  DriftStatus,
  Judgment,
} from "./types.js";

interface Index {
  byChunkId: Map<string, CorpusChunk>;
  byTextSha: Map<string, CorpusChunk[]>;
  byDoc: Map<string, CorpusChunk[]>;
}

function buildIndex(corpus: Corpus): Index {
  const byChunkId = new Map<string, CorpusChunk>();
  const byTextSha = new Map<string, CorpusChunk[]>();
  const byDoc = new Map<string, CorpusChunk[]>();

  for (const chunk of corpus.chunks) {
    byChunkId.set(chunk.chunk_id, chunk);

    const sha = chunk.text_sha ?? (chunk.text !== undefined ? textSha(chunk.text) : undefined);
    if (sha) {
      const list = byTextSha.get(sha);
      if (list) list.push(chunk);
      else byTextSha.set(sha, [chunk]);
    }

    const docList = byDoc.get(chunk.doc_uri);
    if (docList) docList.push(chunk);
    else byDoc.set(chunk.doc_uri, [chunk]);
  }

  for (const list of byDoc.values()) {
    list.sort((a, b) => (a.ordinal ?? 0) - (b.ordinal ?? 0));
  }
  return { byChunkId, byTextSha, byDoc };
}

/**
 * Live chunks whose text the labeled text now spans: a coarse label broken into finer chunks.
 *
 * Returned in document order when at least two live chunks are substrings of the labeled text.
 * A single match is left to exact re-anchoring or to {@link findMerged}.
 */
function findSplit(labeledText: string, docChunks: CorpusChunk[]): CorpusChunk[] | null {
  const haystack = normalize(labeledText);
  if (haystack === "") return null;

  const covering = docChunks.filter((chunk) => {
    if (chunk.text === undefined) return false;
    const needle = normalize(chunk.text);
    return needle !== "" && haystack.includes(needle);
  });

  return covering.length >= 2 ? covering : null;
}

/**
 * The live chunk that now contains the labeled text: a fine label absorbed into a coarser chunk.
 *
 * This is the mirror image of a split, and at least as common: raising `chunk_size` merges
 * paragraphs. The label is still sound, because a chunk containing text a human judged relevant
 * still contains the answer, so it re-anchors rather than needing re-judgment. Reported
 * separately from an exact match because the new chunk carries extra material, which dilutes
 * precision-style metrics and is worth knowing about.
 *
 * When several live chunks contain the text, the shortest wins: it is the tightest evidence.
 */
function findMerged(labeledText: string, docChunks: CorpusChunk[]): CorpusChunk | null {
  const needle = normalize(labeledText);
  if (needle === "") return null;

  const containing = docChunks.filter(
    (chunk) => chunk.text !== undefined && normalize(chunk.text).includes(needle),
  );
  if (containing.length === 0) return null;

  return containing.reduce((best, chunk) =>
    normalize(chunk.text as string).length < normalize(best.text as string).length ? chunk : best,
  );
}

export interface DriftOptions {
  /** Corpus fingerprint to record when judgments carry none. */
  corpusFingerprint?: string;
}

/**
 * Classify every judgment against a live corpus.
 *
 * This is the question no other evaluation tool can answer: after you changed your chunker,
 * which of your labels still mean what they meant when a human wrote them?
 *
 * - `VALID`          the labeled chunk_id is still present
 * - `RE_ANCHORABLE`  the id is stale, but the exact text is still a live chunk
 * - `MERGED`         the text was absorbed into a coarser chunk; re-anchors safely
 * - `SPLIT`          the labeled text now spans two or more live chunks, so it needs re-judging
 * - `ORPHANED`       the text or its document is gone
 */
export function drift(
  judgments: Judgment[],
  corpus: Corpus,
  options: DriftOptions = {},
): DriftResult {
  const index = buildIndex(corpus);
  const findings: DriftFinding[] = [];
  const fingerprints = new Set<string>();

  for (const j of judgments) {
    if (j.corpus_fingerprint) fingerprints.add(j.corpus_fingerprint);

    const finding: DriftFinding = {
      query_id: j.query_id,
      doc_uri: j.doc_uri,
      status: "ORPHANED",
    };
    if (j.chunk_id !== undefined) finding.chunk_id = j.chunk_id;

    const sha = j.text_sha ?? (j.chunk_text !== undefined ? textSha(j.chunk_text) : undefined);
    const docChunks = index.byDoc.get(j.doc_uri) ?? [];

    // Document-level labels have no chunk to track; they are valid while the document exists.
    if (j.chunk_id === undefined) {
      finding.status = docChunks.length > 0 ? "VALID" : "ORPHANED";
      findings.push(finding);
      continue;
    }

    if (index.byChunkId.has(j.chunk_id)) {
      finding.status = "VALID";
      findings.push(finding);
      continue;
    }

    // Exact text match first: cheapest and most precise.
    if (sha) {
      const matches = index.byTextSha.get(sha) ?? [];
      const sameDoc = matches.filter((chunk) => chunk.doc_uri === j.doc_uri);
      const target = sameDoc[0] ?? matches[0];
      if (target) {
        finding.status = "RE_ANCHORABLE";
        finding.reanchor_to = target.chunk_id;
        findings.push(finding);
        continue;
      }
    }

    // Then the two re-chunk shapes. Without these, a label whose text plainly still exists
    // would be reported ORPHANED, which is both wrong and the kind of wrong that erodes trust.
    if (j.chunk_text !== undefined) {
      const split = findSplit(j.chunk_text, docChunks);
      if (split) {
        finding.status = "SPLIT";
        finding.split_into = split.map((chunk) => chunk.chunk_id);
        findings.push(finding);
        continue;
      }

      const merged = findMerged(j.chunk_text, docChunks);
      if (merged) {
        finding.status = "MERGED";
        finding.reanchor_to = merged.chunk_id;
        findings.push(finding);
        continue;
      }
    }

    findings.push(finding);
  }

  const count = (status: DriftStatus): number => findings.filter((f) => f.status === status).length;
  const valid = count("VALID");
  const total = findings.length;

  return {
    findings,
    summary: {
      valid,
      re_anchorable: count("RE_ANCHORABLE"),
      merged: count("MERGED"),
      split: count("SPLIT"),
      orphaned: count("ORPHANED"),
      invalid_ratio: total === 0 ? 0 : Math.round(((total - valid) / total) * 1e12) / 1e12,
    },
    judgments_fingerprint: fingerprints.size === 1 ? ([...fingerprints][0] as string) : null,
    corpus_fingerprint: corpus.corpus_fingerprint ?? options.corpusFingerprint ?? null,
  };
}

export interface FixResult {
  judgments: Judgment[];
  reanchored: number;
  /** Labels left untouched because they need a human: SPLIT and ORPHANED. */
  needsReview: DriftFinding[];
}

/**
 * Re-anchor the recoverable labels onto their new chunk_ids and stamp the new fingerprint.
 *
 * RE_ANCHORABLE and MERGED are recoverable: in both cases the text a human judged is still
 * there. SPLIT and ORPHANED are deliberately left alone, because guessing at them would
 * silently fabricate ground truth, the exact failure this tool exists to expose.
 */
export function fix(judgments: Judgment[], result: DriftResult): FixResult {
  const byQueryAndChunk = new Map<string, DriftFinding>();
  for (const finding of result.findings) {
    byQueryAndChunk.set(`${finding.query_id}\u0000${finding.chunk_id ?? ""}`, finding);
  }

  let reanchored = 0;
  const needsReview: DriftFinding[] = [];
  const out = judgments.map((j) => {
    const finding = byQueryAndChunk.get(`${j.query_id}\u0000${j.chunk_id ?? ""}`);
    if (!finding) return j;

    if (
      (finding.status === "RE_ANCHORABLE" || finding.status === "MERGED") &&
      finding.reanchor_to
    ) {
      reanchored++;
      const next: Judgment = { ...j, chunk_id: finding.reanchor_to };
      if (result.corpus_fingerprint) next.corpus_fingerprint = result.corpus_fingerprint;
      return next;
    }
    if (finding.status === "SPLIT" || finding.status === "ORPHANED") needsReview.push(finding);
    if (finding.status === "VALID" && result.corpus_fingerprint) {
      return { ...j, corpus_fingerprint: result.corpus_fingerprint };
    }
    return j;
  });

  return { judgments: out, reanchored, needsReview };
}
