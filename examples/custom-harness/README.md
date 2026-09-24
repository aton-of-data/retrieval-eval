# Your own harness: the library without the CLI

Evaluation often belongs inside something you already run: a pytest suite, a vitest file, a
nightly job, a service endpoint. The CLI is a thin layer over exported functions, so none of that
needs a subprocess.

```bash
python3 harness.py      # or: node harness.mjs, they print the same thing
```

It reads the [support-bot](../support-bot) data, so every number matches what
`retrieval-eval score` prints for the same files.

## What it shows that the CLI cannot

**Per-query detail.** `relevance_by_query` and `query_metrics` give you the numbers behind the
mean, so a failing build can name the three queries that caused it:

```
     q07  recall=0.00  how are disputes handled?
     q08  recall=0.00  how long do you keep my data after I leave?
     q09  recall=0.00  can I ask for a copy of my data?
```

That list is what a developer needs and what a mean cannot provide. Put it in your test output,
your PR comment, or your dashboard.

**A canonical writer.** `serialize_judgments` writes the format the way both implementations
write it, so tooling that generates or repairs labels produces files that diff cleanly against
files written anywhere else.

## The rest is the CLI's own path

| Step | Functions |
|---|---|
| refuse to measure an unchecked set | `validate` |
| per-stratum, and the class to gate on | `score_by_stratum`, `worst_stratum` |
| a report, with a judged metric beside the deterministic ones | `build_report`, `summarize` |
| gates and a verdict | `parse_gate`, `evaluate_gates` |
| hand the labels to `trec_eval`, and read its run back | `to_qrels`, `to_trec_run`, `from_trec_run` |
| drift, so the numbers mean something | `drift`, `fix` |

Both packages export the same surface under each language's naming convention:
`score_by_stratum` in Python, `scoreByStratum` in TypeScript.

## Using it in a test suite

```python
def test_retrieval_did_not_regress():
    report = build_report(judgments, run, k=5)
    verdict = evaluate_gates(report, [parse_gate("worst-stratum:recall@5:0.7")])
    assert verdict.status == "PASS", verdict.reasons
```

```ts
it("retrieval did not regress", () => {
  const report = buildReport({ judgments, run, k: 5 });
  const verdict = evaluateGates({ report, gates: [parseGate("worst-stratum:recall@5:0.7")] });
  expect(verdict.status, verdict.reasons.join("; ")).toBe("PASS");
});
```

A failing assertion prints the reason the gate gives, which is the same sentence the CLI prints,
because it is the same code.
