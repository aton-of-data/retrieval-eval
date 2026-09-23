# The problem

_Evidence pass, 2026-09-22. Figures are readings from that date._

Four failures show up repeatedly in teams that evaluate retrieval, and in the issue trackers of
the tools they use to do it. Each one is measurable, none of them requires a model to detect,
and none of the widely used evaluation stacks reports on them today.

## 1. A judgment set decays without saying so

A relevance judgment is a statement about a piece of text that a person read. Every mainstream
evaluation format stores it as a reference to a document id or to a chunk index, so the
statement survives only as long as the chunking that produced it.

Change the chunker, the embedding model, or the source document, and the reference still
resolves. It simply points somewhere else. Metrics computed afterwards are measuring two
changes at once: the retriever you meant to change, and the labels you did not.

Research on golden datasets states the requirement directly. A usable golden set must record
which question was asked, what answer is acceptable, which chunks support it, and which corpus
revision made those judgments meaningful. The last clause is the one no shipped evaluation
framework can express, because none of them carry a stable chunk identity or a corpus
fingerprint.

The consequence is not a wrong number, it is an unattributable one. Index staleness is well
covered in the literature and in product roadmaps. Test-set staleness is not, and it is worse,
because the number keeps being reported with confidence.

**What this project does about it:** `drift` classifies every label against the live corpus as
`VALID`, `RE_ANCHORABLE`, `MERGED`, `SPLIT` or `ORPHANED`, and `drift --fix` re-anchors the two
recoverable classes. `SPLIT` and `ORPHANED` are never guessed, because inventing ground truth is
the failure this tool exists to expose.

## 2. Averages hide a broken query class

Aggregate retrieval metrics are the default unit of reporting, and a single mean can sit
comfortably above a threshold while an entire category of queries returns nothing. Semantic
stratification exists in the literature precisely because a system can succeed in narrow niches
and struggle elsewhere while posting a respectable overall score.

A gate on the mean will pass that system. A team that ships it finds out from its users.

**What this project does about it:** `stratum` is a first-class field in the judgment format,
`per_stratum` is mandatory in the report schema, and `worst-stratum:<metric>:<floor>` is a
first-class gate rather than an optional extra.

## 3. LLM judges are treated as if they were deterministic

LLM-as-judge answers questions that ranking metrics cannot: whether the model used the retrieved
context, and whether the answer is supported. Those questions matter. The instrument has three
documented problems that current reporting practice ignores.

- **Agreement with humans is weak.** Correlation between RAGAS metrics and human evaluation
  reaches a harmonic mean of about 0.55, far below what automated evaluation would need to stand
  alone.
- **Judgments are not reproducible.** Judges vary even at temperature 0 through tokenization,
  batching and backend routing. The same triple scored three times can return 0.8, 1.0 and 0.6.
  Known bias directions compound this: position, verbosity, and self-enhancement.
- **Judging dominates cost.** The choice of evaluator model commonly accounts for 60 to 80
  percent of total RAG system cost, plus latency and, for hosted judges, data exposure.

A point estimate from a single sample of a non-deterministic instrument is a measurement claim
the instrument cannot support.

**What this project does about it:** the report schema carries `n`, `stdev` and a confidence
interval per metric, a `ci-lower` gate compares intervals rather than point estimates, and the
verdict has a third state, `INDETERMINATE`, for the case where the interval straddles the
threshold. The deterministic metrics this tool computes are marked as deterministic, so the two
kinds of number are never confused. No LLM is called anywhere in this repository.

## 4. Golden sets are locked to whichever tool was adopted first

Labels are the expensive asset in evaluation. Tools are cheap and get replaced. The current
ecosystem inverts that: every evaluation tool defines its own dataset shape and its own result
shape, so the asset is trapped inside the disposable thing.

In npm alone the evaluation space now includes `deepeval`, `ragbench`, two independent RAGAS
ports, an MCP scoring server, `@hazeljs/eval` and `node-dcg`, alongside promptfoo. In Python it
includes RAGAS, DeepEval, TruLens, Phoenix, Langfuse, Braintrust and Maxim. There is no
interchange format between any of them, and none of them read the test collections the
information retrieval community has maintained for three decades.

Static analysis had the same shape of problem, dozens of scanners with incompatible outputs,
until SARIF standardized the results format. SARIF spread because it was a format rather than a
product, so adopting it cost no vendor their users. The machine learning ecosystem has
acknowledged the same gap: Croissant standardized dataset description, and extending it to tasks
and model evaluation is named as unfinished work.

**What this project does about it:** `judgments.jsonl` is a strict superset of TREC qrels, so one
conversion reaches `trec_eval`, `ir_measures`, `pytrec_eval`, BEIR and `ir_datasets`. The report
is a documented JSON Schema any tool may emit and any dashboard may read. Portability is the
strategy, not a feature.

## Why these are identity problems, not AI problems

Problems 1 and 4 both reduce to the absence of a stable name for a piece of retrieved text. Give
a chunk an identity derived from its content rather than its position, and a label points at text
a human read, a re-chunk becomes a set difference, and two tools can exchange labels without
agreeing on anything else.

That primitive is plumbing, which is why it has been skipped while the field worked on retrieval
strategies, and why a small library can supply it without waiting on a model release.

## Claims deliberately not made

Credibility in this area is easy to lose in one sentence.

- Retrieval quality is a large share of end-to-end RAG quality, not all of it. The rest is how
  well the model uses what it retrieved. This project covers the retrieval half and does not
  certify a RAG system.
- A widely recirculated set of figures attributed to a NIST analysis of July 2026, including a
  73 percent audit failure rate, traces to a single aggregator blog with no primary publication
  behind it. It is not used here. The real documents are NIST AI 600-1, the Generative AI Profile
  of the AI Risk Management Framework, which names confabulation as a primary risk category, and
  the OWASP Top 10 for LLM Applications.
- The format makes labels durable and portable. It does not create them. Labeling remains
  synthetic generation plus sampled production traffic plus human calibration.

## Sources

- [Coverage, Not Averages: Semantic Stratification](https://arxiv.org/pdf/2604.20763)
- [Evaluating RAG Metrics in Applied Contexts](https://arxiv.org/pdf/2607.07302)
- [FreshStack: Realistic Benchmarks for Retrieval on Technical Documents](https://arxiv.org/pdf/2504.13128)
- [Pytrec_eval: An Extremely Fast Python Interface to trec_eval](https://arxiv.org/pdf/1805.01597)
- [The complete guide to SARIF](https://www.sonarsource.com/resources/library/sarif/) and [SARIF home](https://sarifweb.azurewebsites.net/)
- [OpenML: insights from 10 years and more than a thousand papers](https://www.sciencedirect.com/science/article/pii/S2666389925001655)
- [Evaluation metrics for search and recommendation systems](https://weaviate.io/blog/retrieval-evaluation-metrics)
- [Evaluating RAG pipelines](https://www.promptfoo.dev/docs/guides/evaluate-rag/)
- NIST AI 600-1, Generative AI Profile of the AI Risk Management Framework
- OWASP Top 10 for LLM Applications, 2026 revision
