<div align="center">

# retrieval-eval

**Every re-chunk quietly invalidates part of your RAG test suite.<br>
`retrieval-eval` tells you which labels are still true, and repairs the ones it can.**

Label drift detection · deterministic retrieval metrics · a portable, qrels-compatible judgment format<br>
Zero dependencies · no API key · TypeScript and Python

[![CI](https://github.com/aton-of-data/retrieval-eval/actions/workflows/ci.yml/badge.svg)](https://github.com/aton-of-data/retrieval-eval/actions/workflows/ci.yml)
[![npm version](https://img.shields.io/npm/v/retrieval-eval?logo=npm&label=npm&color=cb3837)](https://www.npmjs.com/package/retrieval-eval)
[![PyPI version](https://img.shields.io/pypi/v/retrieval-eval?logo=pypi&logoColor=white&label=pypi&color=3775a9)](https://pypi.org/project/retrieval-eval/)
[![node](https://img.shields.io/node/v/retrieval-eval?logo=nodedotjs&logoColor=white&color=5fa04e)](https://www.npmjs.com/package/retrieval-eval)
[![python](https://img.shields.io/pypi/pyversions/retrieval-eval?logo=python&logoColor=white&color=3775a9)](https://pypi.org/project/retrieval-eval/)
[![zero dependencies](https://img.shields.io/badge/runtime%20deps-0-brightgreen)](#why-zero-dependencies)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![docs](https://img.shields.io/badge/docs-aton--of--data.github.io-0d1117?logo=github)](https://aton-of-data.github.io/retrieval-eval/)

</div>

---

A retrieval test suite rests on one assumption nobody writes down: that every label still points
at the passage a human actually read. Labels are stored as chunk IDs, and chunk IDs are an
artifact of your chunker. Change the chunk size, the splitter or the overlap, and the IDs move
while the labels stay where they were. Nothing errors. The metrics keep computing, against ground
truth that is partly no longer there.

One command shows you how much:

<!--:npm-->
```bash
npx retrieval-eval drift --judgments judgments.jsonl --corpus corpus.json
```
<!--:end-->
<!--:pypi-->
```bash
retrieval-eval drift --judgments judgments.jsonl --corpus corpus.json
```
<!--:end-->

```
  312 judgments · labeled @ fingerprint recursive/512
  live corpus    @ fingerprint recursive/384

  ok  188  VALID          chunk_id still present
  !    47  RE-ANCHORABLE  text moved to a new chunk_id
  !    24  MERGED         text absorbed into a coarser chunk
  !    34  SPLIT          labeled text now spans 2+ chunks
  x    19  ORPHANED       source text or document is gone

  40% of your judgment set no longer matches the live corpus.
  Any metric computed against it is measuring two changes at once.
  71 recoverable automatically · 53 need a human

  next    retrieval-eval drift --fix, to re-anchor the recoverable labels
```

You changed your chunker. Your `recall@5` moved 0.06. You credited the change.

But 40% of your labels no longer point at the text a human actually read. Part of that movement
was your test suite decaying, not your retriever improving, and no other evaluation tool will
tell you which part.

`retrieval-eval` separates them, then recovers the labels it can:

<!--:npm-->
```bash
npx retrieval-eval drift --judgments judgments.jsonl --corpus corpus.json --fix
#   fixed   re-anchored 71 label(s) in judgments.jsonl
#   review  53 label(s) still need a human
```
<!--:end-->
<!--:pypi-->
```bash
retrieval-eval drift --judgments judgments.jsonl --corpus corpus.json --fix
#   fixed   re-anchored 71 label(s) in judgments.jsonl
#   review  53 label(s) still need a human
```
<!--:end-->

`RE_ANCHORABLE` and `MERGED` are recoverable: the text a human judged is still there, either as
its own chunk or inside a bigger one. `SPLIT` and `ORPHANED` are left alone on purpose, because
guessing at them would fabricate ground truth, which is the exact failure this tool exists to
expose.

> **See it happen in 30 seconds.** [`examples/quickstart`](examples/quickstart) runs a corpus
> whose text never changes, re-chunks it, and watches `recall@3` fall from 1.00 to 0.00 while
> retrieval stays perfect, then brings it back with `--fix`. Six more runnable scenarios, the
> integration for eight stacks, and complete CI jobs are in [`examples/`](examples).

## Why this matters

A golden set is the most expensive thing in a RAG project. Every label is a person reading a
passage and deciding whether it answers a question. Yet it is the one artifact nothing checks.
Retrievers get versioned, prompts get diffed, embedding models get benchmarked, and the labels
underneath all of them are treated as permanent. They are coordinates into one particular
chunking, and every chunking change moves the map.

The damage is quiet, and it points the wrong way. A chunker that genuinely retrieves better can
score worse, because its correct answers now live under IDs the labels have never seen. A real
improvement and the decay it caused can cancel out and read as no change at all. Either way, the
number you gate releases on is measuring two things at once, and nothing tells you how much of
each.

Teams that notice end up with three bad options: relabel from scratch, stop trusting the suite,
or stop changing the chunker. `drift` is a fourth. It names exactly which labels moved, recovers
every one whose text is provably still there, and sends only the rest to a human. After that,
your metrics are measuring your retriever again.

## Install

<!--:npm-->
```bash
npm install retrieval-eval        # or: npx retrieval-eval --help
```
<!--:end-->
<!--:pypi-->
```bash
pip install retrieval-eval        # or: uvx retrieval-eval --help
```
<!--:end-->
<!--:root-->
```bash
npm install retrieval-eval        # or: npx retrieval-eval --help
pip install retrieval-eval        # or: uvx retrieval-eval --help
```
<!--:end-->

Same name, same commands, same flags, same rendered output, same exit codes in both, so one CI
step works for a polyglot team. Node 20.11 or newer, Python 3.10 or newer.

## What it does

**1. Keeps your labels true when the corpus changes.** Every chunk gets an identity derived from
its content, not its position ([the one idea](#the-one-idea)), so a label remembers what a human
read rather than where it used to sit. `drift` classifies every label as `VALID`,
`RE_ANCHORABLE`, `MERGED`, `SPLIT` or `ORPHANED`, `--fix` repairs the two recoverable classes in
place, and the command exits non-zero on decay, so a re-chunk cannot ship with a stale suite
behind it. Run it before `score`, in CI, on every chunking change.

**2. Measures retrieval, deterministically.** `precision@k`, `recall@k`, `ndcg@k`, `mrr@k`, `map@k`,
`hit_rate@k`. Every metric carries its cutoff in its name, because a number that means
something other than its name is how a report stops being trustworthy. No model call, no API key, no per-run cost, milliseconds per run.

These are the metrics that localize a failure. High `recall@20` with low `recall@5` means
retrieval found the answer and ranking buried it, so the reranker is the problem rather than the
chunker. A single end-to-end score cannot make that distinction.

```bash
retrieval-eval score --judgments judgments.jsonl --run hits.jsonl -k 5 \
  --baseline .retrieval-eval/baseline.json \
  --gate recall@5:-0.02 \
  --gate worst-stratum:recall@5:0.7
```

**3. Refuses to let an average hide a broken query class.**

```
  recall@3 by stratum
  · legal                0.0000  ░░░░░░░░  n=2  worst
  · billing              1.0000  ████████  n=3

  gates
  ok recall@3:0.5
  x  worst-stratum:recall@3:0.7
```

Overall recall is 0.60 and passes an average gate. Legal queries retrieve nothing. That is why
`stratum` is a field in the format, `per_stratum` is mandatory in the report, and worst-stratum
gating is a first-class gate.

**4. Speaks TREC qrels, so thirty years of tooling just works.**

```bash
retrieval-eval convert --judgments judgments.jsonl --to qrels | trec_eval -m all_trec - run.txt
retrieval-eval convert --qrels beir/scifact/qrels/test.tsv --to judgments > judgments.jsonl
```

A judgments file is a strict superset of qrels, so `trec_eval`, `ir_measures`, `pytrec_eval`,
BEIR and `ir_datasets` are all one conversion away in either direction.

**5. Tells you when a judgment set is unsound**, not merely malformed:

```
  warning [no-human-labels] every label is synthetic. Without human labels you cannot measure
          judge calibration, and synthetic labels quietly become ground truth
  warning [mixed-fingerprints] judgments span 2 corpus fingerprints; run 'drift' first
  warning [thin-stratum] stratum 'legal' has only 2 labels, too few to gate on
  error   [no-positives] no judgment has relevance >= 1, so recall is undefined
```

## The one idea

Give every chunk an identity derived from its **content**, not its position:

```
chunk_id = "c1:" + sha256(doc_uri ␟ doc_revision ␟ ordinal ␟ normalize(text) ␟ chunker_fingerprint)[0..16]
#                    128 bits, written as 32 lowercase hex characters
```

A label then points at text a human read, so after a re-chunk the tool can say exactly which
labels survived.

The [spec](spec/) is two JSON Schemas and one hash definition, small enough to implement in an
afternoon in any language. If it ever needs a framework, it has failed. It ships inside both
packages, so a port never has to start from the GitHub UI.

## What this removes

Each row is a situation teams are already in.

| Situation | What breaks today | What changes |
|---|---|---|
| Chunker changed and a metric moved | the whole movement is credited to the retriever | drift separates label decay from retrieval change |
| Chunk size tuned, labels now point at stale IDs | the golden set is relabeled by hand, or quietly trusted anyway | `--fix` re-anchors every label whose text survived; only the rest need a human |
| Golden set built in one evaluation tool, team adopts another | labels are rebuilt by hand or abandoned | one conversion, labels outlive the tool |
| Public collection in TREC qrels, product written in TypeScript | no path into the ecosystem | one conversion, then scored locally |
| Gate on an aggregate metric | a whole query class can fail silently | worst-stratum gate fails the build |
| Judged metric gated on a single sample | a non-deterministic instrument reported as a point estimate | confidence interval, plus an `INDETERMINATE` verdict |
| Synthetic labels accumulating over time | they become ground truth without anyone deciding that | `labeled_by` is required, and `validate` warns |
| Evaluation platform priced per run | build gates get rationed to stay inside a tier | no model call, no API key, no per-run cost |
| Evaluation tooling added to a CI image | a dependency tree makes the step slow or fragile | standard library only, in both languages |

## Use it as a library

```ts
import { drift, score, chunkId, toQrels } from "retrieval-eval";

const result = drift(judgments, corpus);
if (result.summary.invalid_ratio > 0.1) throw new Error("golden set has decayed");

const { metrics } = score(judgments, run, { k: 5 });
metrics["recall@5"].value;
```

```python
from retrieval_eval import drift, score, chunk_id, to_qrels

result = drift(judgments, corpus)
if result.summary.invalid_ratio > 0.1:
    raise RuntimeError("golden set has decayed")

scored = score(judgments, run, k=5)
scored.metrics["recall@5"].value
```

## In CI

<!--:npm-->
```yaml
- run: npx retrieval-eval drift --judgments eval/judgments.jsonl --corpus eval/corpus.json
- run: |
    npx retrieval-eval score \
      --judgments eval/judgments.jsonl --run eval/hits.jsonl -k 5 \
      --baseline eval/baseline.json \
      --gate recall@5:-0.02 --gate worst-stratum:recall@5:0.7 \
      --out report.json
```
<!--:end-->
<!--:pypi-->
```yaml
- run: pip install retrieval-eval
- run: retrieval-eval drift --judgments eval/judgments.jsonl --corpus eval/corpus.json
- run: |
    retrieval-eval score \
      --judgments eval/judgments.jsonl --run eval/hits.jsonl -k 5 \
      --baseline eval/baseline.json \
      --gate recall@5:-0.02 --gate worst-stratum:recall@5:0.7 \
      --out report.json
```
<!--:end-->

Exit `0` passed, exit `1` a gate failed or labels decayed, exit `2` bad invocation or unreadable
input. `drift` exits non-zero on its own, so it works as a standalone check.

GitLab, CircleCI, Jenkins, Azure Pipelines and pre-commit recipes are in [docs/ci.md](docs/ci.md).

## Why this does not already exist

Every evaluation tool scores against a golden set. None of them checks whether the golden set
still describes the corpus. RAGAS, DeepEval, promptfoo and the IR toolkits all store a label as
a pointer and trust it forever, because no shared format records which corpus revision or which
chunker a label was made against. Without that, drift is not merely unreported, it is
unmeasurable. The judgment format here adds exactly the fields that make it measurable, and
`drift` is the algorithm that uses them.

The metrics had a smaller gap of their own. Python has `pytrec_eval`, `ir_measures` and BEIR. On npm the package names you would reach for
first, `ndcg`, `ir-measures`, `trec-eval` and `qrels`, are unpublished, and what does exist is
thin: [`node-dcg`](https://www.npmjs.com/package/node-dcg) computes DCG alone and was last
published in 2023, [`trec-eval-wrapper`](https://www.npmjs.com/package/trec-eval-wrapper) shells
out to the `trec_eval` C binary rather than implementing anything and was last published in 2022,
and the recent entries are coupled to something else, an MCP server or a recommender engine's own
core package.

So there are two gaps, in order of importance: **nothing in either ecosystem treats judgment
drift as a measurable condition**, and **no maintained, standalone, dependency-free IR
evaluation library exists for JavaScript**. The evidence, including the
two claims this research falsified against its own earlier draft, is in
[research/](research/).

*(Registry state checked 2026-09-22. If this has changed, the claim is wrong and belongs in an
issue. Accuracy about our own positioning is part of the point.)*

## It is not a replacement for judged evaluation

Retrieval quality is a large share of end-to-end RAG quality, not all of it. The rest is how well
the model uses what it retrieved. This covers the retrieval half rigorously and deliberately does
not claim to certify a RAG system.

Use it alongside RAGAS, DeepEval, promptfoo, Phoenix or Braintrust rather than instead of them. It
makes their golden sets portable and durable, which is why interoperability is the strategy rather
than a feature.

For the judged half, the report format carries the honesty those metrics need, and `summarize()`
computes it: `n`, `stdev` and a confidence interval from repeated samples of the same judge, plus
a third verdict, `INDETERMINATE`. LLM judges are non-deterministic even at temperature 0, so a
`ci-lower` gate on a single sample says "I do not know" rather than guessing.

```python
report.metrics["faithfulness"] = summarize([0.8, 1.0, 0.6, 0.9, 0.7])
#  value 0.8000, stdev 0.1581, 95% interval [0.6037, 0.9963]
#  the mean clears a 0.8 floor; the interval says you cannot tell yet
```

[`examples/judged-metrics`](examples/judged-metrics) runs that end to end in both languages.

## Why zero dependencies

Both packages use only their standard library: `sha256` and JSON. A measurement tool that drags in
a dependency tree becomes a thing you skip installing in CI. It also keeps the spec implementable
anywhere, which is the point of a spec.

## Status

**0.1.0, alpha.** The formats and the metric mathematics are what we intend to keep. The CLI
surface may still move. The `c1:` and `t1:` hash prefixes exist so identity can be versioned
without breaking existing judgment files.

What is already load-bearing, and enforced on every commit:

- **Parity.** Both implementations run the same `spec/fixtures` through both CLIs and must agree
  on the numbers, the rendered output, the help text and the exit codes. Not two test suites that
  each pass, one job that runs both and diffs the result.
- **Determinism.** Same inputs, same output, every run. No network, no model, no clock in the
  numbers. Across the two implementations: rendered output and judgments files are byte-identical,
  and `--json` agrees as data rather than as bytes, because JSON writes a whole number as `1` in
  JavaScript and `1.0` in Python. Compare reports by parsing them, not by checksum.
- **A quickstart that is executed, not described.** CI runs the README's own first-run path on a
  clean checkout on Linux and macOS, and asserts the demo still demonstrates its claim.

## Repo layout

```
spec/                        the contract: 2 schemas, 1 hash definition, shared fixtures
  fixtures/                  conformance cases BOTH implementations must pass
packages/retrieval-eval/     TypeScript (tsup · vitest · biome)
python/retrieval-eval/       Python     (hatchling · pytest · ruff · mypy --strict)
docs/                        CLI reference, CI recipes, interop, troubleshooting
examples/                    runnable scenarios, stack integrations, pipeline jobs
  frameworks/                LangChain, LlamaIndex, Haystack, Chroma, Qdrant, pgvector, RAGAS, DeepEval
  pipelines/                 Jenkins, GitHub Actions, GitLab, Azure, CircleCI, pre-commit
research/                    the evidence behind the design
```

Python and TypeScript are peers, not ports. Both read the same `spec/fixtures` and must agree to
the twelfth decimal, which is what makes "parity by spec" a claim rather than a slogan.

## Docs

| | |
|---|---|
| [docs/cli.md](docs/cli.md) | every command, flag, exit code and output mode |
| [docs/ci.md](docs/ci.md) | pipeline recipes and how to keep a baseline |
| [docs/interop.md](docs/interop.md) | qrels, BEIR, `ir_datasets`, and the tools you already run |
| [docs/troubleshooting.md](docs/troubleshooting.md) | every error and warning, and what to do about it |
| [spec/](spec/) | the formats, the hash, the fixtures |
| [examples/](examples) | seven runnable scenarios, eight stack integrations, seven pipeline jobs |
| [research/](research/) | the problem, the market gap, and the impact argument |
| [CONTRIBUTING.md](CONTRIBUTING.md) | add a metric, add an adapter, port the spec |

## License

Apache-2.0
