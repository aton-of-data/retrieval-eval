"""Haystack: emit a corpus snapshot and a run file from an existing pipeline.

Written against haystack-ai 2.x, which also matches the 3.x component API for these two
components. Uses the in-memory store and BM25 so the example needs no model and no keys.

    pip install haystack-ai retrieval-eval
    python haystack_python.py
"""

from __future__ import annotations

import json
from pathlib import Path

from haystack import Document
from haystack.components.preprocessors import DocumentSplitter
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from haystack.document_stores.in_memory import InMemoryDocumentStore
from retrieval_eval import chunk_id, text_sha

SPLIT_BY, SPLIT_LENGTH, SPLIT_OVERLAP = "word", 120, 20
FINGERPRINT = f"{SPLIT_BY}/{SPLIT_LENGTH}/{SPLIT_OVERLAP}"

splitter = DocumentSplitter(
    split_by=SPLIT_BY, split_length=SPLIT_LENGTH, split_overlap=SPLIT_OVERLAP
)


def index(documents: list[Document]) -> tuple[InMemoryDocumentStore, list[Document]]:
    """Split, stamp each chunk with a content-addressed id, then write to the store.

    Haystack's own `Document.id` is a hash of content *and* metadata, so adding a field changes
    it. That is fine for a store key and wrong for a label anchor, which is why the spec's id is
    computed separately and kept in `meta`.
    """
    splitter.warm_up()
    chunks: list[Document] = splitter.run(documents=documents)["documents"]

    ordinals: dict[str, int] = {}
    for chunk in chunks:
        uri = chunk.meta["doc_uri"]
        revision = chunk.meta.get("doc_revision", "1")
        ordinal = ordinals[uri] = ordinals.get(uri, -1) + 1
        chunk.meta["ordinal"] = ordinal
        chunk.meta["chunk_id"] = chunk_id(uri, revision, ordinal, chunk.content or "", FINGERPRINT)

    store = InMemoryDocumentStore()
    store.write_documents(chunks)
    return store, chunks


def write_corpus(chunks: list[Document], path: str = "corpus.json") -> None:
    """Integration point 1: what the index currently contains."""
    Path(path).write_text(
        json.dumps(
            {
                "corpus_fingerprint": FINGERPRINT,
                "chunker_fingerprint": FINGERPRINT,
                "chunks": [
                    {
                        "chunk_id": chunk.meta["chunk_id"],
                        "doc_uri": chunk.meta["doc_uri"],
                        "doc_revision": chunk.meta.get("doc_revision", "1"),
                        "ordinal": chunk.meta["ordinal"],
                        "text": chunk.content,
                        "text_sha": text_sha(chunk.content or ""),
                    }
                    for chunk in chunks
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def write_run(
    store: InMemoryDocumentStore,
    queries: dict[str, str],
    k: int = 5,
    path: str = "hits.jsonl",
) -> None:
    """Integration point 2: what retrieval returned, in rank order, per query."""
    retriever = InMemoryBM25Retriever(document_store=store, top_k=k)
    with Path(path).open("w", encoding="utf-8") as out:
        for query_id, query in queries.items():
            hits = retriever.run(query=query)["documents"]
            ranking = [hit.meta["chunk_id"] for hit in hits]
            out.write(json.dumps({"query_id": query_id, "ranking": ranking}) + "\n")


if __name__ == "__main__":
    documents = [
        Document(
            content="Annual plans may be refunded within 30 days of renewal.",
            meta={"doc_uri": "help://billing/refunds", "doc_revision": "2026-08-04"},
        )
    ]
    store, chunks = index(documents)
    write_corpus(chunks)
    write_run(store, {"q01": "can I get a refund on an annual plan?"})
    print("wrote corpus.json and hits.jsonl")
