import { createHash } from "node:crypto";

/** U+001F unit separator: joins canonical fields without colliding with real content. */
const SEP = "";

/**
 * Normalize chunk text. Exactly three steps, in this order. Any deviation breaks
 * cross-language agreement with the Python implementation. See `spec/chunk-id.md`.
 */
export function normalize(text: string): string {
  return text.normalize("NFC").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
}

function h128(input: string): string {
  return createHash("sha256").update(input, "utf8").digest("hex").slice(0, 32);
}

/** Hash of the normalized text, so a judgment can describe itself without storing the text. */
export function textSha(text: string): string {
  return `t1:${h128(normalize(text))}`;
}

export interface ChunkIdInput {
  docUri: string;
  docRevision: string;
  ordinal: number;
  text: string;
  chunkerFingerprint: string;
}

/** Content-addressed chunk id: a label points at text, not at a position in a list. */
export function chunkId(input: ChunkIdInput): string {
  const canonical = [
    input.docUri,
    input.docRevision,
    String(input.ordinal),
    normalize(input.text),
    input.chunkerFingerprint,
  ].join(SEP);
  return `c1:${h128(canonical)}`;
}
