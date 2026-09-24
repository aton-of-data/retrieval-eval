# A public collection, in and back out

Thirty years of information retrieval evaluation is distributed as qrels files. BEIR ships them,
`ir_datasets` exports them, `trec_eval` reads them, and until now none of it was reachable from a
JavaScript toolchain.

```bash
./run.sh
```

`collection/` is a small collection in exactly the BEIR layout: `corpus.jsonl`, `queries.jsonl`
and `qrels/test.tsv`. Point the same commands at a real one and nothing changes.

## In

```
retrieval-eval convert --qrels collection/qrels/test.tsv --to judgments > judgments.jsonl
```

```
{"query_id":"qa1","doc_uri":"d2","relevance":1}
{"query_id":"qa1","doc_uri":"d3","relevance":2}
{"query_id":"qa2","doc_uri":"d4","relevance":2}
```

Both qrels shapes are read: BEIR's three columns behind a `query-id corpus-id score` header, and
the classic TREC four columns. Negative grades, which some TREC collections use, are clamped to
0. Comments and blank lines are ignored.

Use `--as-chunk-ids` when the collection's document ids are already chunk-level. Without it they
become `doc_uri`, which is right for collections of whole documents like this one.

## What the format says about an imported set

```
retrieval-eval validate --judgments judgments.jsonl
```

```
  7 labels · 4 queries · 1 strata

  warning [no-chunk-ids] no label has a chunk_id, so drift can only work at document
          granularity. See spec/chunk-id.md
```

Correct, and worth reading rather than silencing. A qrels file cannot carry chunk identity,
provenance or strata, because the format has nowhere to put them. Conversion does not invent
them. What you get is a judgment set that is exactly as strong as its source, and a warning
naming the one capability it cannot have until you add chunk ids.

That is the upgrade path, not a limitation: import the collection, score against it today, and
when your own pipeline starts emitting content-addressed ids, drift detection turns on for the
labels that have them.

## Score

```
retrieval-eval score --judgments judgments.jsonl --run hits.jsonl -k 3
```

```
  4 queries · 7 labels (0 human, 0 synthetic)

  precision@3      0.5000
  recall@3         0.7500
  ndcg@3           0.6648
  mrr@3            0.6250
  map@3            0.6458
  hit_rate@3       0.7500

  PASS
```

`0 human, 0 synthetic` is the provenance the source file could not express. Every metric here is
the textbook definition, computed deterministically, and cross-checked against a second
implementation on every commit.

## Out

```
retrieval-eval convert --judgments judgments.jsonl --to qrels  > qrels.txt
retrieval-eval convert --run hits.jsonl --to trec-run          > run.txt
trec_eval -m all_trec qrels.txt run.txt
```

```
qa1 0 d2 1          qa1 Q0 d1 1 5.0000 retrieval-eval
qa1 0 d3 2          qa1 Q0 d3 2 4.0000 retrieval-eval
qa2 0 d4 2          qa1 Q0 d2 3 3.0000 retrieval-eval
```

Round-tripping preserves the relevance grades. Fields qrels has no room for, such as `stratum`
or `labeled_by`, are dropped on the way out, which is why the judgments file stays the source of
truth and qrels is the interchange.

## The same conversion from code

```python
from retrieval_eval import from_qrels, serialize_judgments

judgments = from_qrels(
    open("collection/qrels/test.tsv").read(),
    corpus_fingerprint="bm25/v1",       # optional, stamps the corpus state on every label
    labeled_by="human:beir",            # optional, records where the labels came from
)
open("judgments.jsonl", "w").write(serialize_judgments(judgments))
```

`from_qrels` takes the two fields the source file cannot carry, so an import can start recording
provenance and corpus state immediately rather than after the next re-label.

## Why bother, if `trec_eval` already exists

Because `trec_eval` cannot tell you that your labels stopped describing your corpus, and because
it is a C binary that does not exist in a Node image. Use both: this for the labels, the gates
and the CI story, `trec_eval` when you want the reference implementation's number on the same
data.
