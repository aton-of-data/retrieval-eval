# The market gap

_Registry and repository data pulled from the npm registry and the GitHub API on 2026-09-22.
Every number is a reading from that date and should be rechecked before it is repeated._

## 1. What the registries say

Three queries, run against the live registries rather than against comparison articles.

**npm has no information retrieval metrics library.** The package names a developer would reach
for first, `ir-measures`, `trec-eval`, `ndcg`, `ranking-metrics` and `retrieval-metrics`, are
unpublished. Searching npm for `qrels` returns two results, both unrelated. What does exist is
thin or coupled:

| Package | State on 2026-09-22 |
|---|---|
| `node-dcg` | DCG only, last published 2023 |
| `trec-eval-wrapper` | shells out to the `trec_eval` C binary, last published 2022 |
| recent entries | bundled inside an MCP server or a recommender engine's core package |

Thirty years of evaluation science has no maintained, standalone, dependency-free presence in
JavaScript.

**In Python the rigorous tools exist but are an academic backwater.** `trec_eval` (NIST, C) has
282 stars, `pytrec_eval` 353 with its last push on 2023-10-10, `ir_measures` 102, `ir_datasets`
392. DeepEval has 18,397 and RAGAS holds the mindshare. The tools with the strongest
methodology are the least visible to the people who need them.

**The RAG evaluation space is fragmenting quickly.** Ten or more tools, zero interchange. Each
defines its own dataset shape and its own result shape, so a team's labels are locked to
whichever tool it adopted first, and none of them can read the IR community's test collections.

## 2. What already covers part of this, and covers it well

Naming this precisely matters more than the gap itself. An adoption argument that misrepresents
the incumbents does not survive its first reader.

| Covered by | What it owns | Why this project does not compete |
|---|---|---|
| RAGAS | the vocabulary of judged RAG metrics | adopted and bridged, not renamed |
| DeepEval, Python and TypeScript | judged metrics inside a test runner | complementary layer; it needs durable labels |
| promptfoo | assertion-style prompt and RAG testing | gains a ranking-metric companion |
| `trec_eval`, `ir_measures`, `pytrec_eval` | reference IR metric implementations in Python | conversion target, not a rival |
| BEIR, `ir_datasets` | public test collections | reachable from this format in one conversion |
| Pathway | streaming freshness for constantly changing corpora | different problem, different runtime |
| RAGFlow, Onyx, Dify | deployable RAG applications and platforms | not importable into a product request path |
| Vespa | serving and ranking at scale | a possible backend, never a competitor |

A claim retired during this research: "Node has no evaluation tooling" is false. `deepeval` on
npm is the official DeepEval for TypeScript, created 2026-02-22, 21 releases, running as Vitest.
A second claim retired: `ragbench` on npm, created 2026-09-08, already ships deterministic
metrics with a build gate and zero dependencies. A deterministic RAG evaluation CLI for
TypeScript is therefore not an empty space.

## 3. The gap that is still empty

What survives both corrections is narrower and better defined:

> No tool in any language, at any price, reports which of your relevance judgments are still true
> after the corpus or the chunker changed, and no format lets two evaluation tools exchange those
> judgments.

Two things follow from that sentence, and they are the entire scope of this project:

1. **A portable judgment format.** A strict superset of TREC qrels, adding content-addressed
   chunk identity, a corpus fingerprint, label provenance, and a stratum. Four fields, each
   carrying a specific capability the base format cannot express.
2. **Drift detection over that format.** Roughly two hundred lines of algorithm that exist
   nowhere else, and that make every other evaluation tool in the ecosystem more trustworthy
   without asking anyone to switch.

## 4. Gap claims, with their evidence grade

| Claim | Grade | Basis |
|---|---|---|
| npm has no maintained standalone IR metrics library | VERIFIED | registry queries, 2026-09-22 |
| No format expresses corpus-revision validity of a judgment | VERIFIED | schema review of the shipped evaluation frameworks |
| No tool reports label drift after a re-chunk | VERIFIED | feature review across the tools in section 2 |
| Evaluation tools have no interchange format | VERIFIED | dataset shapes compared across ten npm and Python tools |
| Averaged metrics mask category failure | CORROBORATED | stratification literature, plus the behaviour of a mean gate |
| Judge non-determinism at temperature 0 | CORROBORATED | reproduced in published reports; see [01-problem](01-problem.md) |
| Judging is 60 to 80 percent of RAG system cost | CORROBORATED | practitioner reporting, not independently audited here |
| "Node has no evaluation tooling" | FALSIFIED | official DeepEval for TypeScript, 2026-02-22 |
| "Nobody ships a deterministic RAG eval CLI" | FALSIFIED | `ragbench`, 2026-09-08 |

Two falsified claims are the reason the scope narrowed from a library to a format plus one
algorithm. Finding them in an afternoon of registry queries was cheaper than finding them three
months into implementation.

## 5. What the ecosystem's failures imply about shape

Four comparable projects died or stalled within roughly ten months, measured on 2026-09-22:

| Project | Stars | State |
|---|---:|---|
| run-llama/LlamaIndexTS | 3,079 | archived, 149 open issues |
| weaviate/Verba | 7,703 | archived, 78 open issues |
| truefoundry/cognita | 4,420 | archived |
| SciPhi-AI/R2R | 8,001 | no push in about 10 months, README still claims production readiness |

Meanwhile the narrow components are healthy. Docling holds 67,631 stars doing one job, more than
LlamaIndex at 52,284, with Unstructured at 15,469 and RAGAS and DeepEval alive beside them.

The pattern is not random. Applications and orchestration frameworks carry unbounded surface
area, every connector and every provider, which grows faster than any maintainer. Vendor-owned
open source stops when the funnel that paid for it changes: Cognita belonged to TrueFoundry,
Verba to Weaviate. Focused components with a small readable core survive.

Three constraints follow, and they are design rules here rather than preferences:

- **No orchestration, ever.** No agents, chains, prompt DSL, graph runtime or UI.
- **No provider SDKs in the core.** Both packages are standard library only. A measurement tool
  that drags in a dependency tree becomes the tool people skip installing in CI.
- **A core small enough to read in an afternoon.** Unreadable abstraction is what drives the
  documented backlash against RAG frameworks. Fewer abstractions, not more documentation.

## 6. Who this is for

Not enterprises building internal knowledge search. MIT's 2025 GenAI Divide report found that 95
percent of enterprise GenAI pilots fail to reach measurable P&L impact, with in-house builds
succeeding about a third of the time against about two thirds for vendor partnerships. A bank
building employee search should deploy Onyx, buy a platform, or use a managed knowledge base.

The same research names the exception: teams building a product where the retrieval layer is the
differentiation. Concretely, that is vertical SaaS shipping search over its customers' documents,
AI-native products whose value is retrieval quality over a proprietary corpus, polyglot teams
running Python ingestion behind a TypeScript product, and agent builders who need a correct
`search()` rather than a framework. Those teams cannot buy their way out, and they are the ones
for whom proving that quality did not regress is a recurring cost.

## Sources

- npm registry and GitHub API queries, 2026-09-22, covering `deepeval`, `ragbench`, `promptfoo`,
  `pytrec_eval`, `ir_measures`, `trec_eval`, `ir_datasets`, `beir`, `node-dcg`,
  `trec-eval-wrapper`
- [usnistgov/trec_eval](https://github.com/usnistgov/trec_eval), [cvangysel/pytrec_eval](https://github.com/cvangysel/pytrec_eval), [terrierteam/ir_measures](https://github.com/terrierteam/ir_measures)
- [run-llama/LlamaIndexTS](https://github.com/run-llama/LlamaIndexTS), [weaviate/Verba](https://github.com/weaviate/Verba), [truefoundry/cognita](https://github.com/truefoundry/cognita), [SciPhi-AI/R2R](https://github.com/SciPhi-AI/r2r)
- [docling-project/docling](https://github.com/docling-project/docling), [pathwaycom/pathway](https://github.com/pathwaycom/pathway), [vespa-engine/vespa](https://github.com/vespa-engine/vespa)
- [mastra-ai/mastra#16985, evaluation metrics for multi-step RAG](https://github.com/mastra-ai/mastra/issues/16985)
- [Build vs buy RAG in 2026](https://www.chitika.com/build-vs-buy-rag-in-2026-when-enterprises-should-use-a-managed-rag-platform-instead-of-building-from-scratch/)
- [Best enterprise RAG platforms for 2026](https://onyx.app/insights/enterprise-rag-platforms-2026)
- [Why we no longer use LangChain for building our AI agents](https://news.ycombinator.com/item?id=40739982)
