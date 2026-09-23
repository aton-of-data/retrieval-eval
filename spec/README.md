# The retrieval-eval spec

Two file formats and one hash definition. Small on purpose: if implementing this takes more than
an afternoon in any language, the spec has failed.

| File | Purpose |
|---|---|
| [`judgments.schema.json`](judgments.schema.json) | relevance labels that survive a re-chunk |
| [`report.schema.json`](report.schema.json) | results any CI or dashboard can ingest |
| [`chunk-id.md`](chunk-id.md) | the content-addressed chunk identity |
| [`drift.md`](drift.md) | the five label statuses and how they are resolved |
| [`fixtures/`](fixtures/) | conformance cases every implementation must pass |

## Design rules

1. **JSONL for data, JSON for reports.** Streamable, greppable, diffable in code review.
2. **A strict superset of TREC qrels.** Any judgments file converts losslessly to
   `query_id 0 doc_id relevance`, so `trec_eval`, `ir_measures`, BEIR and `ir_datasets` all work.
3. **Zero required dependencies.** SHA-256 and JSON only, both in every standard library.
4. **Unknown fields are preserved, never rejected.** Tools must round-trip fields they don't know.
5. **Every implementation passes `fixtures/`.** That is what makes a conformance claim mean
   something: machine-readable, runnable black-box, stable over time.
