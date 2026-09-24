# Documentation

| | |
|---|---|
| [cli.md](cli.md) | every command, flag, exit code and output mode |
| [ci.md](ci.md) | running this in GitHub Actions, GitLab, CircleCI, Jenkins, Azure Pipelines and pre-commit |
| [interop.md](interop.md) | moving labels in and out: TREC qrels, BEIR, `ir_datasets`, RAGAS, DeepEval, promptfoo |
| [troubleshooting.md](troubleshooting.md) | what each error and warning means, and what to do about it |
| [../spec/](../spec/) | the formats themselves: two JSON Schemas and one hash definition |
| [../examples/](../examples) | runnable scenarios, stack integrations and complete pipeline jobs |
| [../research/](../research/) | the evidence behind the design |

## Where to start

New to the tool, run the [quickstart](../examples/quickstart).

Adding it to a pipeline, read [ci.md](ci.md) for the concepts and
[examples/pipelines](../examples/pipelines) for a file to copy. Wiring it into LangChain,
LlamaIndex, Haystack or a vector store, see [examples/frameworks](../examples/frameworks).
Bringing existing labels with you, read [interop.md](interop.md).

Implementing the format in another language, read the [spec](../spec/) and nothing else: it is
the contract, and everything in this directory is downstream of it.
