# Examples

Four scenarios you can run right now, integrations for the stacks people actually build on, and
complete pipeline jobs for the systems people actually run.

## Run these

No dependencies, no API key, no network. Each one is a `./run.sh` that prints a session you can
follow, and each is executed by CI on Linux and macOS so it cannot quietly stop being true.

| Example | The question it answers | Two minutes of your time buys |
|---|---|---|
| [quickstart](quickstart) | what does judgment drift even look like? | `recall@3` falling 1.00 to 0.00 while retrieval stays perfect, then recovering |
| [support-bot](support-bot) | my mean looks fine, is it? | an entire query class returning nothing behind a passing average |
| [reranker-vs-chunker](reranker-vs-chunker) | should I change the chunker or the ranking? | two numbers that decide it before anyone touches the pipeline |
| [graded-relevance](graded-relevance) | what counts as relevant here? | the same run scored two ways, and why `mrr@3` falls from 1.00 to 0.57 |
| [judged-metrics](judged-metrics) | can I gate on an LLM judge? | error bars, and a verdict that says "I do not know" instead of guessing |
| [beir-qrels](beir-qrels) | can I use public IR collections, and keep my options open? | a BEIR collection in, `trec_eval` out, nothing lost either way |
| [custom-harness](custom-harness) | can I skip the CLI and call this from my tests? | the whole surface used programmatically, per-query detail included |

```bash
examples/quickstart/demo.py          # or demo.mjs, they print the same thing
examples/support-bot/run.sh
examples/reranker-vs-chunker/run.sh
examples/graded-relevance/run.sh
examples/judged-metrics/demo.py      # or demo.mjs
examples/beir-qrels/run.sh
examples/custom-harness/harness.py   # or harness.mjs
```

## Wire it into your stack

[frameworks/](frameworks) has the integration for LangChain (Python and JavaScript), LlamaIndex,
Haystack, Chroma, Qdrant, pgvector, RAGAS and DeepEval. Every one of them comes down to the same
two files, `corpus.json` and `hits.jsonl`, and to computing `chunk_id` where chunks are created
so it comes back on every hit.

These files are linted and syntax-checked on every commit but not executed by CI, because running
them would mean installing nine frameworks and a database into a pipeline whose point is that it
needs none of that. Instead,
[`frameworks/verify_integrations.py`](frameworks/verify_integrations.py) runs the real code path
for every framework **you** have installed and skips the rest, so the claims stay checkable on
your machine in one command.

## Put it in a pipeline

[pipelines/](pipelines) has complete jobs for Jenkins, GitHub Actions, GitLab CI, Azure
Pipelines, CircleCI and pre-commit, plus a scheduled job that re-anchors decayed labels nightly
and opens a pull request for review rather than repairing the set behind your back.

The concepts behind those files, which gates to choose and how to keep a baseline, are in
[../docs/ci.md](../docs/ci.md).

## Reading order

New to the idea, run [quickstart](quickstart) and read nothing. Deciding whether this is worth a
pipeline slot, read [support-bot](support-bot). Wiring it in, go straight to
[frameworks/](frameworks) and [pipelines/](pipelines).

## Not shipped

None of this is in the published npm package or Python wheel. Both ship the library, the CLI and
the spec, which keeps the install small and keeps the examples where they are useful: in the
repository, beside the code they integrate with, versioned with the tool they demonstrate.
