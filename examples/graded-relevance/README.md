# Graded labels: deciding what "relevant" means, and measuring it

An API documentation search with three-grade labels, the way a docs team actually judges:

| Grade | Meaning |
|---|---|
| `2` | this chunk answers the question |
| `1` | useful context, but it does not answer the question |
| `0` | judged and rejected |

```bash
./run.sh
```

Most evaluation setups collapse this to relevant or not, because their format has nowhere to put
the middle. Then a retriever that is very good at surfacing *related* text scores as though it
were answering questions.

## Everything useful counts

```
retrieval-eval score --judgments judgments.jsonl --run hits.jsonl -k 3
```

```
  precision@3      0.5556
  recall@3         0.9167
  ndcg@3           0.8050
  mrr@3            1.0000
  map@3            0.9167
  hit_rate@3       1.0000
```

`mrr@3` is a perfect 1.00: every query gets *something* relevant at rank 1. A dashboard showing
this is showing a system that looks solved.

## Only answers count

```
retrieval-eval score --judgments judgments.jsonl --run hits.jsonl -k 3 --threshold 2
```

```
  precision@3      0.2667
  recall@3         0.8000
  ndcg@3           0.7660
  mrr@3            0.5667
  map@3            0.5667
  hit_rate@3       0.8000

  recall@3 by stratum
  · payments             0.6667  █████░░░  n=3  worst
  · errors               1.0000  ████████  n=2
  · billing              not scored, no label at the relevance threshold
  → 1 judged queries have no label at relevance >= 2 and were excluded from the averages
```

Same labels, same retrieval, different question. `mrr@3` falls from 1.00 to 0.57: the top result
is frequently context rather than the answer. For a support bot that summarizes, the first
reading may be the one you care about. For a docs assistant that quotes, the second is the only
one that matters.

`--threshold` is where you state which it is, and it is a product decision rather than a
statistical one.

## Two behaviours worth knowing

**A query with no label at the threshold is excluded, not scored zero.** One query here has only
grade-1 context in the corpus: nothing answers it directly. At `--threshold 2` there is nothing
for retrieval to have found, so scoring it zero would report a corpus gap as a retrieval failure.
It is excluded, counted, and the count is printed. The report carries both numbers as
`judgments.queries` and `judgments.queries_scored`.

**A stratum with nothing to score is never the worst stratum.** `billing` disappears from the
ranking rather than sitting at 0.0000 and failing a worst-stratum gate over an empty set. It is
still listed, because silently dropping a query class is how coverage gaps hide.

## Grades and nDCG

`ndcg@k` is the metric that uses the full grade rather than the threshold: a grade-2 chunk at
rank 1 is worth more than a grade-1 chunk at rank 1, with gains of `2^grade - 1`. It is the
reason to write graded labels at all, and the reason it moves less than `mrr@3` between the two
readings above.

Both readings are computed from one judgment file. The grades are recorded once by a human, and
what counts as relevant is decided at scoring time, per gate, per team.
