# Conformance fixtures

Every implementation must pass these. That is what makes "parity by spec, not by port" a claim
rather than a slogan, so the fixtures are normative and this file describes their shape.

Each directory is one case. Inputs use the wire formats the spec already defines; `expected.json`
holds the answers, and **its shape is per-case rather than fixed**, because the cases check
different things: some check numbers, some check a classification, some check a refusal.

| File | Meaning |
|---|---|
| `judgments.jsonl` | input, per [`judgments.schema.json`](../judgments.schema.json) |
| `run.jsonl` | input, one `{"query_id", "ranking"}` object per line |
| `corpus.json` | input, a corpus snapshot: `{"corpus_fingerprint", "chunker_fingerprint", "chunks"}` |
| `*.tsv`, `*.qrels` | input, TREC or BEIR qrels |
| `expected.json` | the answers, in the shape the table below gives |

`expected.json` may carry a `note` in any case. It is prose for a human reader, never asserted.

## What each case asserts

| Case | Asserts |
|---|---|
| `basic` | `metrics` at `k`, `metrics_k1` at k=1, `per_query` detail, `qrels_lines` |
| `chunk-id` | vectors for `normalize`, `text_sha` and `chunk_id` |
| `drift` | per-label `statuses`, `summary` counts, `reanchor` and `split_into` targets |
| `merge` | `statuses` and `summary` for a re-chunk that merges paragraphs |
| `qrels` | the judgments a `beir` and a `trec` file convert to, and the `qrels_lines` back out |
| `strata` | `metrics`, `per_stratum` scores, and `worst_stratum` |
| `summarize` | `cases`, each with `samples` and the expected measurement |
| `no-positives` | `queries_without_positives`, and the metrics over what remains |
| `nothing-scored` | that no metric is emitted and the verdict is `INDETERMINATE` |
| `duplicate-ranking` | that a repeated key counts once, plus the runs that are refused outright |
| `unsound-judgments` | that a set `validate` rejects cannot be scored to a `PASS` |
| `unsorted-queries` | the order validation issues are emitted in |

## Rules a fixture follows

1. **Numbers are given to twelve decimal places.** Both implementations round to 1e-12, so a
   fixture that agrees to fewer digits is not testing agreement.
2. **Inputs are the published formats.** A fixture never invents a file type an implementation
   would not otherwise read.
3. **A refusal is an answer.** Where the right behaviour is to reject the input, the fixture
   carries the input file and the exact message, because two implementations that reject the
   same file with different words are still two tools.
4. **A case earns its place by catching something.** `unsorted-queries` exists because every
   other fixture happened to have sorted query ids, which hid a real divergence between the two
   implementations.
