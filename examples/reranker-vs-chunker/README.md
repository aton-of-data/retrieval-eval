# Reranker or chunker: reading two numbers before changing anything

An API documentation corpus, twelve questions a developer would actually ask, one labeled answer
each. `recall@5` is 0.33 and somebody is about to rewrite the chunker.

```bash
./run.sh
```

## The number that starts the argument

```
retrieval-eval score --judgments judgments.jsonl --run hits.jsonl -k 5
```

```
  precision@5      0.0667
  recall@5         0.3333
  ndcg@5           0.2135
  mrr@5            0.1736
  map@5            0.1736
  hit_rate@5       0.3333
```

Two thirds of questions get no correct chunk in the top 5. The usual next move is to change
chunk size, add overlap, switch the embedding model, or all three at once over a week.

## The number that ends it

The same run and the same labels, read at a wider cutoff:

```
retrieval-eval score --judgments judgments.jsonl --run hits.jsonl -k 20
```

```
  precision@20     0.0500
  recall@20        1.0000
  ndcg@20          0.4135
  mrr@20           0.2479
  map@20           0.2479
  hit_rate@20      1.0000
```

`recall@20` is 1.00. **Every** answer is already in the candidate set. The retriever is finding
the right text and the ordering is burying it. Chunking differently cannot improve a recall that
is already perfect; it can only move the problem around.

## The fix, measured

Same candidates, reordered by a cross-encoder. No new chunks, no new embeddings, no reindex:

```
retrieval-eval score --judgments judgments.jsonl --run hits-reranked.jsonl -k 5
```

```
  precision@5      0.2000
  recall@5         1.0000
  ndcg@5           0.8186
  mrr@5            0.7569
  map@5            0.7569
  hit_rate@5       1.0000
```

`recall@5` goes 0.33 to 1.00 and `mrr@5` 0.17 to 0.76, from a change that touches only the last
step of the pipeline.

## How to read the pair

| `recall@k` small | `recall@20` large | Diagnosis |
|---|---|---|
| low | high | ranking problem: rerank, tune fusion weights, revisit the query rewriter |
| low | low | retrieval problem: chunking, the embedding model, or the corpus does not contain the answer |
| high | high | retrieval is fine, look downstream at how the model uses the context |

This is the reason to keep deterministic ranking metrics next to a judged evaluation. A single
end-to-end quality score moves when this pipeline is bad, but it cannot tell you which of the
three rows above you are in, and the three have nothing in common except the symptom.

`ndcg@20` at 0.41 next to `recall@20` at 1.00 says the same thing a second way: everything is
present, positioned badly. A gap between a recall and an nDCG at the same cutoff is always a
ranking gap.

## The files

| File | What it is |
|---|---|
| `corpus.json` | 22 chunks across 8 documentation pages |
| `judgments.jsonl` | one labeled answer per question, stratified `reference` and `guide` |
| `hits.jsonl` | the current retriever, top 20 per query |
| `hits-reranked.jsonl` | the same candidates after a cross-encoder reorders them |

The reranked run is not an oracle: two queries still land at rank 3 and 4. A reranker is an
improvement, not a guarantee, and an example that pretends otherwise sets the wrong expectation
for what your own numbers should look like.
