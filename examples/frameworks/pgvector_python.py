"""pgvector: one extra column, and a run file that falls out of the query you already run.

Written against psycopg 3.x and pgvector 0.3.x.

    pip install "psycopg[binary]" pgvector retrieval-eval
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from retrieval_eval import chunk_id, text_sha

FINGERPRINT = "paragraph/1/0"

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id      text PRIMARY KEY,   -- the content-addressed id, not a serial
    doc_uri       text NOT NULL,
    doc_revision  text NOT NULL,
    ordinal       int  NOT NULL,
    body          text NOT NULL,
    embedding     vector(1536)
);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
"""


def index(conn: psycopg.Connection, chunks: list[dict], vectors: list[list[float]]) -> None:
    """Upsert by content-addressed id.

    Making the id the primary key is the whole trick: re-running ingestion over unchanged text
    is a no-op, and a re-chunk writes new rows whose ids differ, which is exactly the signal
    `drift` reads.
    """
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
        for chunk, vector in zip(chunks, vectors, strict=True):
            cid = chunk_id(
                chunk["doc_uri"],
                chunk["doc_revision"],
                chunk["ordinal"],
                chunk["text"],
                FINGERPRINT,
            )
            cur.execute(
                """
                INSERT INTO chunks (chunk_id, doc_uri, doc_revision, ordinal, body, embedding)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (chunk_id) DO NOTHING
                """,
                (
                    cid,
                    chunk["doc_uri"],
                    chunk["doc_revision"],
                    chunk["ordinal"],
                    chunk["text"],
                    vector,
                ),
            )
    conn.commit()


def write_corpus(conn: psycopg.Connection, path: str = "corpus.json") -> None:
    """Integration point 1: the live table, as the corpus snapshot."""
    with conn.cursor() as cur:
        cur.execute("SELECT chunk_id, doc_uri, doc_revision, ordinal, body FROM chunks")
        rows = cur.fetchall()

    Path(path).write_text(
        json.dumps(
            {
                "corpus_fingerprint": FINGERPRINT,
                "chunker_fingerprint": FINGERPRINT,
                "chunks": [
                    {
                        "chunk_id": cid,
                        "doc_uri": uri,
                        "doc_revision": revision,
                        "ordinal": ordinal,
                        "text": body,
                        "text_sha": text_sha(body),
                    }
                    for cid, uri, revision, ordinal, body in rows
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def write_run(
    conn: psycopg.Connection,
    queries: dict[str, list[float]],
    k: int = 5,
    path: str = "hits.jsonl",
) -> None:
    """Integration point 2: the same nearest-neighbour query your application runs."""
    with Path(path).open("w", encoding="utf-8") as out, conn.cursor() as cur:
        for query_id, vector in queries.items():
            cur.execute(
                "SELECT chunk_id FROM chunks ORDER BY embedding <=> %s LIMIT %s", (vector, k)
            )
            ranking = [row[0] for row in cur.fetchall()]
            out.write(json.dumps({"query_id": query_id, "ranking": ranking}) + "\n")


if __name__ == "__main__":
    with psycopg.connect("postgresql://localhost/rag") as conn:
        register_vector(conn)
        write_corpus(conn)
        print("wrote corpus.json")
