# Interoperability

Labels are the expensive asset in evaluation. Tools are cheap and get replaced. This format
exists so the asset outlives the tool, which means every path in this page is meant to be
travelled in both directions.

A `judgments.jsonl` file is a strict superset of TREC qrels. Everything qrels can express, it can
express; four added fields carry what qrels cannot.

| Field | What it buys |
|---|---|
| `chunk_id` | a label points at text a human read, not at a position a chunker produced |
| `corpus_fingerprint` | the corpus state the judgment was made against, which is what makes drift decidable |
| `labeled_by` | human, synthetic, or which model, so judge calibration is measurable and synthetic labels cannot quietly become ground truth |
| `stratum` | coverage reporting instead of averages |

## TREC qrels, `trec_eval`, `ir_measures`, `pytrec_eval`

```bash
retrieval-eval convert --judgments judgments.jsonl --to qrels > qrels.txt
retrieval-eval convert --run hits.jsonl --to trec-run > run.txt
trec_eval -m all_trec qrels.txt run.txt
```

The reverse direction imports thirty years of test collections:

```bash
retrieval-eval convert --qrels qrels.txt --to judgments > judgments.jsonl
```

Negative relevance grades, which some TREC collections use, are clamped to 0. Comments and blank
lines are ignored. Round-tripping preserves the relevance grade.

## BEIR and `ir_datasets`

Both ship qrels TSV files, so both import through the same command.

```bash
retrieval-eval convert --qrels beir/scifact/qrels/test.tsv --to judgments > judgments.jsonl
```

Use `--as-chunk-ids` when the collection's document ids are already chunk-level; without it they
are treated as document uris, which is right for collections of whole documents.

This is the first path from these collections into a JavaScript toolchain, and it is the cheapest
way to get a realistic judgment set before you have labeled your own corpus.

## RAGAS, DeepEval, promptfoo, and other judged-evaluation tools

These answer a different question: whether the model used the context it was given. This tool
answers whether the right context was retrieved at all. Run both.

The integration point is the judgment set. Export your labels here, keep them under version
control, run `drift` when the corpus changes, and feed the surviving labels back into whichever
judged evaluation you run. That keeps the golden set portable while you keep using the tool you
already have.

An adapter is a small script: read the other tool's dataset, emit one JSON object per line with
`query_id`, `doc_uri`, `relevance`, and as many of the four added fields as the source can
supply. Adapters live under `spec/fixtures/adapters/<name>/` so both implementations test them.
[CONTRIBUTING.md](../CONTRIBUTING.md) has the requirements.

## Problems this removes

The table of situations this changes, from a golden set locked inside one tool to a metric that
moved for two reasons at once, is in the [README](../README.md#what-this-removes).

## Implementing the format elsewhere

The whole contract is two JSON Schemas and one hash definition, small enough to implement in an
afternoon. A port is correct when `spec/fixtures/chunk-id` passes byte for byte and every other
fixture agrees. See [CONTRIBUTING.md](../CONTRIBUTING.md).

Ambiguity in the spec is a spec bug. Two honest implementations that disagree mean the text is
wrong, and those reports are the most useful contribution this project can receive.
