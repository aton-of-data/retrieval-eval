# Judged metrics: error bars, and a verdict that can say "I do not know"

Retrieval metrics are deterministic. Judged metrics are not, and reporting them as if they were
is the most common measurement error in RAG evaluation.

```bash
node demo.mjs      # or: python3 demo.py, they print the same thing
```

## The instrument

An LLM judge scoring the same `(question, context, answer)` triple five times, same model, same
prompt, same temperature 0:

```
     samples        0.80, 1.00, 0.60, 0.90, 0.70
```

That spread is ordinary. Tokenization, batching and backend routing all leak into the score.
Whatever your evaluation platform shows you, one of those five numbers is what it sampled.

## One sample

```
     faithfulness   0.8000   n=1, no interval

     INDETERMINATE
     -> faithfulness:ci-lower:0.8: no confidence interval on 'faithfulness', sample it more than once
```

`summarize([0.8])` returns a measurement with `n=1` and **no interval at all**, rather than a
zero-width one. A `ci-lower` gate over it is `INDETERMINATE`, not a pass. One draw from a
non-deterministic instrument is not evidence about the next draw, and a gate that pretends
otherwise is worse than no gate, because it produces green builds you believe.

## Five samples

```
     faithfulness   0.8000   n=5  stdev=0.1581
     95% interval   [0.6037, 0.9963]

     FAIL
     -> faithfulness lower bound is 0.6037, below 0.8
```

The mean is the same 0.80 that passed a moment ago. The interval says the true value is
plausibly anywhere from 0.60 to 1.00, and the 0.8 floor sits inside it. The honest verdict is
that this build cannot be judged on this metric yet: sample more, or widen the tolerance
deliberately, but do not read a coin flip as a measurement.

## What the library gives you

```python
from retrieval_eval import summarize

measurement = summarize([0.8, 1.0, 0.6, 0.9, 0.7])
measurement.value   # 0.8
measurement.stdev   # 0.158113883008
measurement.ci      # (0.603675683852, 0.996324316148)
```

```ts
import { summarize } from "retrieval-eval";

const measurement = summarize([0.8, 1.0, 0.6, 0.9, 0.7]);
```

A 95% Student-t interval on the sample mean, with the sample standard deviation. It is not
clamped to the metric's range. One sample yields no interval. Both implementations agree to the
twelfth decimal against `spec/fixtures/summarize`.

Put the result straight into a report next to the deterministic metrics, and gate on both:

```python
report = build_report(judgments, run, k=5)
report.metrics["faithfulness"] = summarize(judge_samples)
verdict = evaluate_gates(report, [parse_gate("recall@5:0.8"), parse_gate("faithfulness:ci-lower:0.8")])
```

## Why this belongs in a retrieval tool

It does not compute judged metrics, and it never will: no model is called anywhere in this
repository. What it provides is the reporting discipline those metrics need, so the two halves
of a RAG evaluation can sit in one report with one verdict.

Run RAGAS, DeepEval, promptfoo or your own judge for the scores. Bring the samples here for the
error bars, the gate and the verdict. See
[../frameworks/deepeval_python.py](../frameworks/deepeval_python.py) for that split in a script.

## The three verdicts

| Verdict | Meaning | Exit |
|---|---|---|
| `PASS` | every gate was decided and cleared | `0` |
| `FAIL` | a gate was decided and did not clear | `1` |
| `INDETERMINATE` | a gate could not be decided from the data given | `1` |

`INDETERMINATE` exits non-zero on purpose. A build gate that cannot tell you whether quality
held is not a passing build gate.
