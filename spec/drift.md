# Judgment drift

A relevance label is a statement about *text a human read*. When the corpus is re-chunked, the
chunk ids move but the text mostly does not, so most labels are still sound, and the ones that
are not need to be identified rather than silently kept.

`drift` classifies every label against a live corpus.

| Status | Meaning | Recoverable? |
|---|---|---|
| `VALID` | The labeled `chunk_id` is still present in the corpus. | already fine |
| `RE_ANCHORABLE` | The id is stale, but the exact labeled text is still a live chunk. | yes, `--fix` |
| `MERGED` | The labeled text was absorbed into a coarser chunk. | yes, `--fix` |
| `SPLIT` | The labeled text now spans two or more live chunks. | no, needs re-judgment |
| `ORPHANED` | The text, or its document, is gone. | no, needs re-judgment |

## Resolution order

1. `chunk_id` present in the corpus → `VALID`.
2. `text_sha` matches a live chunk exactly → `RE_ANCHORABLE`. Cheapest and most precise, so it
   is tried first. A match in the same `doc_uri` is preferred over one elsewhere.
3. Two or more live chunks are substrings of `chunk_text` → `SPLIT`, reporting every covering id.
4. `chunk_text` is a substring of exactly one live chunk → `MERGED`, re-anchoring to it. When
   several chunks contain it, the **shortest** wins: it is the tightest evidence.
5. Otherwise → `ORPHANED`.

Steps 3 and 4 need `chunk_text` on the judgment. With only `text_sha`, re-anchoring still works
but splits and merges are indistinguishable from orphans, which is the tradeoff for not storing
corpus text in your labels.

## Why MERGED re-anchors but SPLIT does not

`MERGED` is a sound inference: a chunk containing text a human judged relevant still contains
the answer, so the coarser chunk is relevant too. It is reported separately from an exact match
because the new chunk carries extra material, which dilutes precision-style metrics.

`SPLIT` is not sound. The labeled text broke into several chunks and there is no way to know
which of them carries the answer: possibly only one, possibly all. Assigning the label to all
of them would inflate recall; picking one would be a guess. So `drift --fix` leaves it, and says
so.

**`--fix` never invents ground truth.** That rule is worth more than the convenience of a fully
green report.

## invalid_ratio

The share of labels that are not `VALID`. It counts recoverable labels too, because a metric
computed before you re-anchor them *is* wrong. The CLI prints the recoverable/needs-a-human
split alongside it so the number is actionable rather than merely alarming.
