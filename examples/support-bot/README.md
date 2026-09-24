# Support bot: the failure an average hides, and the one nothing else reports

A customer support assistant retrieving over a help center: billing, shipping, legal and account
pages. Eleven queries, thirteen human labels, four strata. Small enough to read, shaped like the
real thing.

```bash
./run.sh          # the whole story, about two seconds, no dependencies
```

## The situation

Someone swapped the embedding model on Monday. The mean barely moved, the dashboard stayed green,
and support started getting angry tickets about arbitration and data retention.

## 1. Is the judgment set sound?

```
retrieval-eval validate --judgments judgments.jsonl
```

```
  13 labels · 11 queries · 4 strata

  warning [thin-stratum] stratum 'billing' has only 4 labels, too few to gate on
  warning [thin-stratum] stratum 'shipping' has only 4 labels, too few to gate on
  warning [thin-stratum] stratum 'legal' has only 3 labels, too few to gate on
  warning [thin-stratum] stratum 'account' has only 2 labels, too few to gate on
```

Exit `0`, because none of that is an error. It is a warning that this set is too small to gate
on with confidence, which is true here and worth saying out loud: a real set wants tens of labels
per stratum, not three. The example keeps them small so you can read the files.

## 2. Score it

```
retrieval-eval score --judgments judgments.jsonl --run hits.jsonl -k 3 \
  --gate recall@3:0.7 \
  --gate worst-stratum:recall@3:0.6
```

```
  11 queries · 13 labels (13 human, 0 synthetic)

  precision@3      0.3030
  recall@3         0.7273
  ndcg@3           0.7273
  mrr@3            0.7273
  map@3            0.7273
  hit_rate@3       0.7273

  recall@3 by stratum
  · legal                0.0000  ░░░░░░░░  n=3  worst
  · account              1.0000  ████████  n=2
  · billing              1.0000  ████████  n=3
  · shipping             1.0000  ████████  n=3

  gates
  ok recall@3:0.7
  x  worst-stratum:recall@3:0.6
  → worst stratum recall@3 is 0.0000, below 0.6

  FAIL
```

`recall@3` is 0.73 and clears its floor. Legal retrieves **nothing**, for every legal query. With
an average gate alone, this ships. The stratum table is what makes the failure visible, and the
worst-stratum gate is what makes it stop the build.

This is the common case, not an exotic one. A model change moves one semantic neighbourhood and
leaves the rest alone, and legal language is the neighbourhood most likely to sit far away from
everything else in a product-trained embedding space.

## 3. Compare against last week

```
retrieval-eval score --judgments judgments.jsonl --run hits.jsonl -k 3 \
  --baseline baseline.json --gate recall@3:-0.02
```

```
  x  recall@3:-0.02
  → recall@3 fell 0.2727, from 1.0000 to 0.7273

  FAIL
```

The delta gate tells you something broke. The stratum table tells you what. You want both: a
baseline catches slow erosion that a floor allows, and the worst-stratum gate catches this even
on the first run, before any baseline exists.

`baseline.json` here is the report from `hits-before.jsonl`, the same queries before the model
changed. That is exactly how you would produce one in CI.

## 4. Then someone raises the chunk size

Unrelated work, a week later: the chunker's target size goes up and the short help-center pages
now fit in one chunk each.

```
retrieval-eval drift --judgments judgments.jsonl --corpus corpus-after-rechunk.json
```

```
  13 judgments · labeled @ fingerprint recursive/512/64
  live corpus    @ fingerprint recursive/1024/64

  ok   0  VALID          chunk_id still present
  !    0  RE-ANCHORABLE  text moved to a new chunk_id
  !   13  MERGED         text absorbed into a coarser chunk
  !    0  SPLIT          labeled text now spans 2+ chunks
  x    0  ORPHANED       source text or document is gone

  100% of your judgment set no longer matches the live corpus.
  Any metric computed against it is measuring two changes at once.
  13 recoverable automatically · 0 need a human
```

Every label still describes text that exists. Not one of them still points at a chunk that
exists. Any metric computed now is measuring the chunker change and the retrieval change
together, and the report would look like a retrieval regression.

`drift --fix` re-anchors all thirteen, because merged text is recoverable. Had the chunk size gone
*down* instead, some labels would come back `SPLIT` and stay untouched: the labeled text would
span several chunks, and only a human can say which one carries the answer.

## Machine-readable, for everything that is not a terminal

Every command takes `--json` and writes the report or the finding list to stdout, with nothing
else on stdout:

```bash
retrieval-eval drift --judgments judgments.jsonl --corpus corpus-after-rechunk.json --json \
  | jq '.summary'
```

```json
{
  "valid": 0,
  "re_anchorable": 0,
  "merged": 13,
  "split": 0,
  "orphaned": 0,
  "invalid_ratio": 1
}
```

`score --json` emits the full report against
[`spec/report.schema.json`](../../spec/report.schema.json), which is what
[`examples/pipelines/nightly-drift-pr.yml`](../pipelines/nightly-drift-pr.yml) reads to decide
whether to open a pull request.

## 5. What the files are

| File | What it is |
|---|---|
| `corpus.json` | the live corpus, one chunk per help-center paragraph |
| `corpus-after-rechunk.json` | the same text at a larger chunk size |
| `judgments.jsonl` | 13 human labels with `chunk_id`, `chunk_text`, `stratum` and provenance |
| `hits.jsonl` | this week's retrieval, top 3 per query |
| `hits-before.jsonl` | last week's retrieval, before the embedding model changed |
| `baseline.json` | the report generated from `hits-before.jsonl` |

Labels carry `chunk_text` on purpose. Without it a label can only come back `VALID` or
`ORPHANED`, because there is nothing to match the live corpus against. It is the cheapest field
in the format and the one that makes recovery possible.

## Where these files come from in your system

`corpus.json` is a dump of your live chunks, `hits.jsonl` is your retriever's output. Both are a
few lines of code in whatever framework you use: see
[../frameworks](../frameworks) for LangChain, LlamaIndex, Haystack, Chroma, Qdrant and pgvector.
