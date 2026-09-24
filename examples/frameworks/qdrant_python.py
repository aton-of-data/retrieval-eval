"""Qdrant: keep the content-addressed id in the payload, because point ids must be UUID or int.

Written against qdrant-client 1.12+, using the `query_points` API.

    pip install qdrant-client retrieval-eval
    python qdrant_python.py
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from retrieval_eval import chunk_id, text_sha

FINGERPRINT = "paragraph/1/0"
COLLECTION = "help-center"


def index(client: QdrantClient, chunks: list[dict], vectors: list[list[float]]) -> None:
    """Upsert, carrying the spec's id in the payload.

    Qdrant point ids are unsigned integers or UUIDs, so the content-addressed id cannot be the
    point id. A deterministic UUID derived from it keeps upserts idempotent, and the payload
    carries the real id back on every hit.
    """
    client.recreate_collection(
        COLLECTION,
        vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE),
    )
    points = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        cid = chunk_id(
            chunk["doc_uri"], chunk["doc_revision"], chunk["ordinal"], chunk["text"], FINGERPRINT
        )
        points.append(
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, cid)),
                vector=vector,
                payload={
                    "chunk_id": cid,
                    "doc_uri": chunk["doc_uri"],
                    "doc_revision": chunk["doc_revision"],
                    "ordinal": chunk["ordinal"],
                    "text": chunk["text"],
                },
            )
        )
    client.upsert(COLLECTION, points=points)


def write_corpus(client: QdrantClient, path: str = "corpus.json") -> None:
    """Integration point 1: scroll the collection and write what is in it."""
    chunks, offset = [], None
    while True:
        batch, offset = client.scroll(
            COLLECTION, limit=256, offset=offset, with_payload=True, with_vectors=False
        )
        for point in batch:
            payload = point.payload or {}
            chunks.append(
                {
                    "chunk_id": payload["chunk_id"],
                    "doc_uri": payload["doc_uri"],
                    "doc_revision": payload["doc_revision"],
                    "ordinal": payload["ordinal"],
                    "text": payload["text"],
                    "text_sha": text_sha(payload["text"]),
                }
            )
        if offset is None:
            break

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
    client: QdrantClient,
    queries: dict[str, list[float]],
    k: int = 5,
    path: str = "hits.jsonl",
) -> None:
    """Integration point 2: the ranked chunk ids per query."""
    with Path(path).open("w", encoding="utf-8") as out:
        for query_id, vector in queries.items():
            hits = client.query_points(COLLECTION, query=vector, limit=k, with_payload=True).points
            ranking = [(hit.payload or {})["chunk_id"] for hit in hits]
            out.write(json.dumps({"query_id": query_id, "ranking": ranking}) + "\n")
