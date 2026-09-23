# Impact

_Written 2026-09-22. This document states what adoption would look like, how it is supposed to
happen, and the conditions under which the argument is wrong._

## 1. What impact means here, and what it does not

The RAG market runs at roughly 3.3 billion dollars in 2026 and is forecast at about 9.86 billion
by 2030. Almost all of that spend goes to platforms and managed services, which this project is
deliberately not competing with. Market share is therefore the wrong measure.

The right comparables are Docling, 67,631 stars for one job and no revenue, and OpenTelemetry, a
vendor-neutral specification with a conformance suite and foundation governance. In both cases
influence is measured in how many systems assume the thing exists.

Impact for this project means three observable outcomes:

1. `judgments.jsonl` becomes how teams exchange retrieval labels, including between tools that do
   not depend on this package.
2. Reporting retrieval quality without a worst-stratum number starts to look incomplete, the way
   reporting a mean without an `n` does.
3. Content-addressed chunk identity becomes an assumption rather than a feature, so the question
   "which of my labels survived the re-chunk" has an answer by default.

The third outcome is the one that ends the need for this tool, which is the correct ambition for
a measurement standard.

## 2. How adoption is supposed to happen

The strategy is the inverse of building a framework: ship adapters into the incumbents and let
them keep their users.

```
RAGAS  DeepEval (py)  DeepEval (ts)  promptfoo  ragbench  Langfuse  Braintrust
                              |
                       judgments.jsonl
                              |
      TREC qrels  BEIR  ir_datasets  trec_eval  ir_measures
```

Nobody has to switch tools. `ragbench` becomes more useful with a durable judgment file.
promptfoo's assertion tests gain a ranking-metric companion. RAGAS users get their golden set out
of RAGAS. BEIR's test collections become usable from TypeScript. A team that changes evaluation
tools keeps its labels, which is the expensive asset.

This is the path EditorConfig, SARIF and OpenAPI took. Roughly 70 percent of developers use
OpenAPI, not because the specification is clever but because adoption compounds into tooling and
tooling compounds into adoption. Standards win by being cheap to emit and valuable to consume.
The Croissant project reached the same conclusion: keeping the standard as simple as possible is
what gained it adoption.

Two design consequences follow:

- The specification stays small enough to implement in an afternoon in any language. Two JSON
  Schemas and one hash definition. If it ever needs a framework, it has failed.
- `drift` must be independently valuable on day one, because a standard nobody emits yet is just
  a text file. Drift detection works against tools that never adopt the format, by falling back
  to text matching when chunk ids are absent.

## 3. Problems in other projects this addresses

Adoption arguments are easier to check when they name the specific failure they remove. The
table of situations, and what changes in each, is in the
[README](../README.md#what-this-removes). Every row is a state a team is already in with tooling
they already run, which is what makes the argument checkable rather than aspirational.

## 4. The falsifiable bet

Stated so it can be checked rather than believed:

> A team that adopts this format should be able to change its chunker and get an evaluation
> report that says exactly which of its labels survived, re-anchor the recoverable ones without
> human review, and gate a build on the weakest query class rather than the mean, without writing
> any of that themselves.

The conditions under which that is false, and the project should stop:

- Teams re-label from scratch after a re-chunk and find it cheap enough not to care. Drift
  detection then solves a problem nobody is paying for.
- Chunk identity requires cooperation from whatever produced the chunks. If producers do not
  compute ids the specified way and the text-matching fallback proves too weak in practice, the
  format degrades to qrels with extra fields.
- Fragmentation resolves without a neutral format. If DeepEval's TypeScript push becomes the de
  facto shape, the format is redundant. The counter-argument is that vendors with monthly-tier
  pricing have poor incentives to make golden sets portable, and portability is the thing users
  want most from them.

## 5. What this project is not first at

- RAGAS defined the vocabulary of judged RAG metrics. This project adopts it and bridges to it.
- DeepEval and RAGAS are healthy and rigorous in their layer. This one covers the layer below
  them, deterministically.
- `trec_eval` and `ir_measures` implemented these metrics long ago and correctly. The
  contribution is portability and drift, not new ranking mathematics.
- Pathway owns streaming freshness for indexes. Test-set freshness is a different problem that
  happens to use the same word.
- The IR community has maintained this methodology for thirty years. Most of what this project
  does is carry it across to the tooling that currently reinvents a worse version of it.

## 6. The longer path

There is a credible standards route. OWASP has named the security category for retrieval, TREC
RAG is renegotiating what correctness means for these systems, and commentary through 2026 asks
for protocol-level standards that unify knowledge grounding. A neutral, conformance-backed
judgment format with two independent implementations is a plausible donation to a foundation in
two to three years.

That only works if the project is not a vendor's funnel, which is why governance is neutral from
the start, why there will never be a paywalled part of the format, and why the conformance
fixtures are the actual deliverable.

## Sources

- [RAG market forecast to 2030](https://www.marketsandmarkets.com/PressReleases/retrieval-augmented-generation-rag.asp)
- [Benefits of OpenAPI-driven API development](https://swagger.io/blog/benefits-of-openapi-api-development/)
- [EditorConfig specification](https://spec.editorconfig.org/)
- [SARIF home](https://sarifweb.azurewebsites.net/)
- [OpenML: insights from 10 years and more than a thousand papers](https://www.sciencedirect.com/science/article/pii/S2666389925001655)
- [docling-project/docling](https://github.com/docling-project/docling), star count via GitHub API 2026-09-22
- OWASP Top 10 for LLM Applications, 2026 revision
