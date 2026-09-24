"""LlamaIndex: emit a corpus snapshot and a run file from an existing index.

Written against llama-index-core 0.12.x.

LlamaIndex already gives every node an id, so the temptation is to use `node.node_id` as the
chunk id and stop. Do not: that id is assigned at parse time and changes when you re-parse, which
is precisely the property that makes a golden set rot silently. Compute the content-addressed id
alongside it and keep both.

    pip install llama-index-core llama-index-embeddings-openai retrieval-eval
    python llamaindex_python.py
"""

from __future__ import annotations

import json
from pathlib import Path

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode
from retrieval_eval import chunk_id, text_sha

CHUNK_SIZE, CHUNK_OVERLAP = 512, 64
FINGERPRINT = f"sentence/{CHUNK_SIZE}/{CHUNK_OVERLAP}"

splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


def index(documents: list[Document]) -> tuple[VectorStoreIndex, list[BaseNode]]:
    """Parse into nodes, stamp each with a content-addressed id, then index."""
    nodes = splitter.get_nodes_from_documents(documents)

    ordinals: dict[str, int] = {}
    for node in nodes:
        uri = node.metadata["doc_uri"]
        revision = node.metadata.get("doc_revision", "1")
        ordinal = ordinals[uri] = ordinals.get(uri, -1) + 1
        node.metadata["ordinal"] = ordinal
        node.metadata["chunk_id"] = chunk_id(uri, revision, ordinal, node.text, FINGERPRINT)
        # Keep the id out of the embedded text and out of the LLM's context: it is plumbing,
        # not content, and embedding it would change what the vector means.
        node.excluded_embed_metadata_keys.extend(["chunk_id", "ordinal"])
        node.excluded_llm_metadata_keys.extend(["chunk_id", "ordinal"])

    return VectorStoreIndex(nodes), nodes


def write_corpus(nodes: list[BaseNode], path: str = "corpus.json") -> None:
    """Integration point 1: what the index currently contains."""
    Path(path).write_text(
        json.dumps(
            {
                "corpus_fingerprint": FINGERPRINT,
                "chunker_fingerprint": FINGERPRINT,
                "chunks": [
                    {
                        "chunk_id": node.metadata["chunk_id"],
                        "doc_uri": node.metadata["doc_uri"],
                        "doc_revision": node.metadata.get("doc_revision", "1"),
                        "ordinal": node.metadata["ordinal"],
                        "text": node.text,
                        "text_sha": text_sha(node.text),
                    }
                    for node in nodes
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def write_run(
    index: VectorStoreIndex, queries: dict[str, str], k: int = 5, path: str = "hits.jsonl"
) -> None:
    """Integration point 2: what retrieval returned, in rank order, per query."""
    retriever = index.as_retriever(similarity_top_k=k)
    with Path(path).open("w", encoding="utf-8") as out:
        for query_id, query in queries.items():
            ranking = [hit.node.metadata["chunk_id"] for hit in retriever.retrieve(query)]
            out.write(json.dumps({"query_id": query_id, "ranking": ranking}) + "\n")


if __name__ == "__main__":
    documents = [
        Document(
            text="Annual plans may be refunded within 30 days of renewal.",
            metadata={"doc_uri": "help://billing/refunds", "doc_revision": "2026-08-04"},
        )
    ]
    built, nodes = index(documents)
    write_corpus(nodes)
    write_run(built, {"q01": "can I get a refund on an annual plan?"})
    print("wrote corpus.json and hits.jsonl")
