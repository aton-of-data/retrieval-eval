"""Chroma: store the content-addressed id so retrieval results can be joined to labels.

Written against chromadb 1.x.

    pip install chromadb retrieval-eval
    python chroma_python.py
"""

from __future__ import annotations

import json
from pathlib import Path

import chromadb
from retrieval_eval import chunk_id, text_sha

FINGERPRINT = "paragraph/1/0"


def index(chunks: list[dict], collection_name: str = "help-center") -> chromadb.Collection:
    """Upsert with the content-addressed id as Chroma's own id.

    Chroma requires unique ids and returns them on every query, so using the spec's id here
    means no extra lookup later. Identical text in two documents still yields two ids, because
    doc_uri and ordinal are part of the hash.
    """
    collection = chromadb.Client().get_or_create_collection(collection_name)
    ids = [
        chunk_id(c["doc_uri"], c["doc_revision"], c["ordinal"], c["text"], FINGERPRINT)
        for c in chunks
    ]
    collection.upsert(
        ids=ids,
        documents=[c["text"] for c in chunks],
        metadatas=[
            {"doc_uri": c["doc_uri"], "doc_revision": c["doc_revision"], "ordinal": c["ordinal"]}
            for c in chunks
        ],
    )
    return collection


def write_corpus(collection: chromadb.Collection, path: str = "corpus.json") -> None:
    """Integration point 1: dump what the collection currently holds."""
    stored = collection.get(include=["documents", "metadatas"])
    chunks = [
        {
            "chunk_id": cid,
            "doc_uri": meta["doc_uri"],
            "doc_revision": meta["doc_revision"],
            "ordinal": meta["ordinal"],
            "text": text,
            "text_sha": text_sha(text),
        }
        for cid, text, meta in zip(
            stored["ids"], stored["documents"], stored["metadatas"], strict=True
        )
    ]
    Path(path).write_text(
        json.dumps(
            {
                "corpus_fingerprint": FINGERPRINT,
                "chunker_fingerprint": FINGERPRINT,
                "chunks": chunks,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def write_run(
    collection: chromadb.Collection,
    queries: dict[str, str],
    k: int = 5,
    path: str = "hits.jsonl",
) -> None:
    """Integration point 2: the ranked ids per query, exactly as returned."""
    with Path(path).open("w", encoding="utf-8") as out:
        for query_id, query in queries.items():
            result = collection.query(query_texts=[query], n_results=k)
            out.write(json.dumps({"query_id": query_id, "ranking": result["ids"][0]}) + "\n")


if __name__ == "__main__":
    collection = index(
        [
            {
                "doc_uri": "help://billing/refunds",
                "doc_revision": "2026-08-04",
                "ordinal": 0,
                "text": "Annual plans may be refunded within 30 days of renewal.",
            }
        ]
    )
    write_corpus(collection)
    write_run(collection, {"q01": "can I get a refund on an annual plan?"})
    print("wrote corpus.json and hits.jsonl")
