# CLI reference

The npm and PyPI packages install the same executable, `retrieval-eval`, with the same verbs,
flags, output and exit codes. Anything in this page works in either, and CI diffs the two to keep
that true.

```bash
npx retrieval-eval --help     # Node 20.11 or newer
uvx retrieval-eval --help     # Python 3.10 or newer
```

## Conventions

| | |
|---|---|
| Exit `0` | the question was answered and the answer was good |
| Exit `1` | the question was answered and the answer was bad: a gate failed, a label decayed, validation found an error |
| Exit `2` | the question could not be answered: bad invocation, unreadable file, malformed input |
| `--json` | machine-readable output on stdout, nothing else on stdout |
| `--color auto\|always\|never` | default `auto`, which respects `NO_COLOR` and whether stdout is a terminal |
| errors | always on stderr, always one line, plus a `try` line when there is an obvious next command |

The split between `1` and `2` is what lets a CI step distinguish "your retrieval regressed" from
"your pipeline is broken". Do not treat non-zero as a single condition.

## `drift`

Report which relevance labels are still true against the live corpus.

```bash
retrieval-eval drift --judgments judgments.jsonl --corpus corpus.json [--fix] [--json]
```

| Label class | Meaning | Recoverable |
|---|---|---|
| `VALID` | the labeled `chunk_id` is still in the corpus | nothing to do |
| `RE_ANCHORABLE` | the labeled text moved to a new `chunk_id` | yes, `--fix` |
| `MERGED` | the labeled text was absorbed into a coarser chunk | yes, `--fix` |
| `SPLIT` | the labeled text now spans several chunks | no, a human must re-judge |
| `ORPHANED` | the labeled text or its document is gone | no |

`--fix` rewrites the judgments file in place, re-anchoring `RE_ANCHORABLE` and `MERGED` labels
onto their new chunk ids and stamping the new corpus fingerprint. It never touches `SPLIT` or
`ORPHANED`, because guessing at them would fabricate ground truth. Running it twice changes
nothing the second time.

Exit `1` whenever any label has decayed, so `drift` works as a standalone CI check with no gate
expression.

With no `chunk_id` on the labels, drift falls back to document granularity, which is weaker but
still useful against tools that never adopted the format. `validate` warns when that is happening.

## `score`

Compute deterministic retrieval metrics and gate a build on them.

```bash
retrieval-eval score --judgments judgments.jsonl --run hits.jsonl -k 5 \
  --baseline baseline.json \
  --gate recall@5:-0.02 \
  --gate worst-stratum:recall@5:0.7 \
  --out report.json
```

| Flag | Default | Meaning |
|---|---|---|
| `-k`, `--k` | `10` | rank cutoff for the `@k` metrics |
| `--threshold` | `1` | lowest relevance grade counted as relevant |
| `--corpus` | none | also report judgment drift beside the metrics |
| `--gate` | none | repeatable, see below |
| `--baseline` | none | a previous report, required by delta gates |
| `--out` | none | write the JSON report to a file while still printing for a human |

Metrics: `precision@k`, `recall@k`, `ndcg@k`, `mrr@k`, `map@k`, `hit_rate@k`. All deterministic,
no model call, milliseconds per run.

Every metric is computed over the top `k` results and named for it. `mrr@k` and `map@k` are
reciprocal rank and average precision **within that cutoff**, not over an unbounded run, which is
why they carry the cutoff that `trec_eval`'s `recip_rank` and `map` do not.

A query with no label at or above `--threshold` has nothing for retrieval to find, so it is
excluded from the averages rather than scored zero, and the count is reported as
`judgments.queries_scored` and printed under the metrics.

These are the metrics that localize a failure. High `recall@20` with low `recall@5` means
retrieval found the answer and ranking buried it, which points at the reranker rather than the
chunker. One end-to-end score cannot make that distinction.

### Gate expressions

| Form | Example | Meaning |
|---|---|---|
| absolute floor | `recall@5:0.8` | fail below 0.8 |
| delta | `recall@5:-0.02` | fail if more than 2 points below `--baseline` |
| worst stratum | `worst-stratum:recall@5:0.7` | fail if the weakest query class is below 0.7 |
| confidence bound | `faithfulness:ci-lower:0.8` | fail if the lower bound of the interval is below 0.8 |

A gate that cannot be decided returns `INDETERMINATE` rather than passing: a delta gate with no
baseline, a `ci-lower` gate on a single-sample metric, or a gate naming a metric the report does
not contain. `INDETERMINATE` exits `1`, because a build gate that cannot tell you whether quality
held is not a passing build gate.

The worst-stratum gate exists because an aggregate metric will sit above its threshold while a
whole query class returns nothing. Gate the mean and the mean is what you get.

## `validate`

Check a judgment set for problems before trusting its numbers.

```bash
retrieval-eval validate --judgments judgments.jsonl
```

Errors exit `1`, warnings exit `0`. Every code is listed in
[troubleshooting.md](troubleshooting.md). The warnings matter as much as the errors: a judgment
set can parse perfectly and still be unsound.

## `convert`

Move labels and runs between this format and TREC qrels.

```bash
retrieval-eval convert --judgments judgments.jsonl --to qrels > qrels.txt
retrieval-eval convert --run hits.jsonl --to trec-run > run.txt
retrieval-eval convert --qrels beir/scifact/qrels/test.tsv --to judgments > judgments.jsonl
```

`--as-chunk-ids` treats the qrels `doc_id` column as a `chunk_id` rather than a `doc_uri`, for
collections whose document ids are already chunk-level. Output goes to stdout, so it composes:

```bash
retrieval-eval convert --judgments judgments.jsonl --to qrels | trec_eval -m all_trec - run.txt
```

## Library use

The CLI is a thin layer over the exported functions. Both packages expose the same surface.

```ts
import { chunkId, drift, fix, score, summarize, toQrels, validate } from "retrieval-eval";

const result = drift(judgments, corpus);
if (result.summary.invalid_ratio > 0.1) throw new Error("golden set has decayed");

// Repeated samples of a non-deterministic judge, as a measurement with error bars.
report.metrics.faithfulness = summarize([0.8, 1.0, 0.6, 0.9, 0.7]);
```

```python
from retrieval_eval import chunk_id, drift, fix, score, summarize, to_qrels, validate

result = drift(judgments, corpus)
if result.summary.invalid_ratio > 0.1:
    raise RuntimeError("golden set has decayed")

report.metrics["faithfulness"] = summarize([0.8, 1.0, 0.6, 0.9, 0.7])
```

`summarize` returns a 95% Student-t interval on the sample mean. It is not clamped to the
metric's range: raising a negative lower bound to 0 would let a `ci-lower` gate pass. A single
sample returns `n=1` and **no** interval, so a `ci-lower` gate over it is `INDETERMINATE`
rather than a quiet pass. When no query has a label at the threshold, `score` omits the
averages and the verdict is `INDETERMINATE` instead of reporting 0.
