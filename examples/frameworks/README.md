# Wiring this into the stack you already have

Whatever you built your retrieval on, the integration is the same two files. Nothing here asks
you to change frameworks, move your index, or adopt an abstraction.

| File | What it is | Produced by |
|---|---|---|
| `corpus.json` | every chunk currently in your index, with its content-addressed id and text | your indexing job, once per index build |
| `hits.jsonl` | one line per query: `query_id` and the ranked ids that came back | your retrieval code, once per evaluation run |

`judgments.jsonl`, the third file, is yours. It is the labels, and it outlives all of the above.

## The one thing to get right

Compute `chunk_id` where chunks are created, and carry it through the store so it comes back on
every hit.

```python
from retrieval_eval import chunk_id

cid = chunk_id(doc_uri, doc_revision, ordinal, chunk_text, chunker_fingerprint)
```

Every framework in this directory already gives chunks an id of its own. None of those ids are
usable as label anchors, for the same reason in each case:

| Stack | Its own id | Why it cannot anchor a label |
|---|---|---|
| LangChain | store-assigned uuid | new on every re-index, even for unchanged text |
| LlamaIndex | `node.node_id` | assigned at parse time, changes when you re-parse |
| Haystack | `Document.id` | hashes content **and** metadata, so adding a field changes it |
| Chroma | caller-supplied id | usable, which is why the example passes the spec's id straight in |
| Qdrant | uuid or integer | the format forbids a string id, so the real id lives in the payload |
| pgvector | whatever you chose | usually a serial, which says nothing about content |

A label anchored to any of those still resolves after a re-chunk. It simply points somewhere
else, silently, and that is the failure this tool exists to make visible.

LangChain, LlamaIndex, Haystack and Chroma were checked by running them.
[`verify_integrations.py`](verify_integrations.py) executes those four paths for whichever of
them you have installed, and skips the rest. The Qdrant and pgvector rows describe the id types
those stores accept; the examples follow them, and the script does not execute them.

```
$ python verify_integrations.py
ok   langchain
     1 chunks at 512, label VALID against them
     after re-chunking at 128: SPLIT
ok   llamaindex
     node_id across two parses: different
     chunk_id across two parses: identical
     chunk_id excluded from the embedded metadata
ok   haystack
     6 chunks, BM25 returned 3 ids, recall@3 = 1.0
     Document.id changes when metadata changes, so the spec's id is kept separately
ok   chroma
     2 chunks stored and read back with their ids
     recall@2 = 1.0

4/4 installed frameworks verified, 0 skipped
```

Frameworks you do not have are skipped rather than failed, so the script is useful with any
subset installed. Last run green against langchain-text-splitters 1.1.2, llama-index-core
0.14.25, haystack-ai 3.1.1 and chromadb 1.5.9 on 2026-09-23.

## The examples

| File | Stack | Shows |
|---|---|---|
| [`langchain_python.py`](langchain_python.py) | LangChain + Chroma | ids in `Document.metadata`, carried through the store |
| [`langchain_js.mjs`](langchain_js.mjs) | LangChain.js | the same, in TypeScript-shaped JavaScript |
| [`llamaindex_python.py`](llamaindex_python.py) | LlamaIndex | ids excluded from embedding and LLM metadata, so they stay plumbing |
| [`haystack_python.py`](haystack_python.py) | Haystack | why `Document.id` is the wrong anchor, and what to use instead |
| [`chroma_python.py`](chroma_python.py) | Chroma | the id as the collection's own id, so a query returns it directly |
| [`qdrant_python.py`](qdrant_python.py) | Qdrant | a deterministic UUID point id, with the real id in the payload |
| [`pgvector_python.py`](pgvector_python.py) | Postgres + pgvector | the id as the primary key, which makes re-ingestion idempotent |
| [`ragas_export.py`](ragas_export.py) | RAGAS | turning a synthesized testset into labels that can be checked later |
| [`deepeval_python.py`](deepeval_python.py) | DeepEval | the deterministic layer gating the judged layer |
| [`verify_integrations.py`](verify_integrations.py) | all of the above | runs the real code path for whatever you have installed |

For promptfoo, `trec_eval`, BEIR and `ir_datasets`, no adapter is needed: convert and pipe. See
[../beir-qrels](../beir-qrels) and [../../docs/interop.md](../../docs/interop.md).

## What CI runs, and what it does not

CI executes every scenario example in [..](..) in full, on Linux and macOS, and asserts the
claims their READMEs make still hold.

The files in this directory are **not executed by CI**, because running them would mean
installing nine frameworks, a Postgres, a Qdrant and an OpenAI key into a pipeline whose entire
point is that it needs none of those. They are syntax-checked and linted on every commit, and
each one names the library versions it was written against at the top.

`verify_integrations.py` is how the gap gets closed on your side: one command, no key, no
network, and it tells you whether these integrations still match the versions you actually have.

If one of them has drifted from its framework's current API, that is a bug worth an issue.

## Not shipped

`examples/` is not part of the published npm package or the Python wheel. Both ship the library,
the CLI and the spec, and nothing else. The examples live in the repository, where they can be
read next to the code they integrate with.
