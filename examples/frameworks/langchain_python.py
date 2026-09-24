"""LangChain (Python): emit a corpus snapshot and a run file from an existing chain.

Written against langchain-core 1.x, langchain-text-splitters 1.x, langchain-chroma 0.2.x.

The integration is two functions. Everything else here is ordinary LangChain code that you
almost certainly already have.

    pip install langchain-text-splitters langchain-chroma langchain-openai retrieval-eval
    python langchain_python.py
    retrieval-eval drift --judgments judgments.jsonl --corpus corpus.json
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from retrieval_eval import chunk_id, text_sha

# The chunker's configuration, as one string. Any stable encoding works; what matters is that
# it changes when the chunking changes, because that is what makes a re-chunk detectable.
CHUNK_SIZE, CHUNK_OVERLAP = 512, 64
FINGERPRINT = f"recursive/{CHUNK_SIZE}/{CHUNK_OVERLAP}"

splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


def index(documents: list[Document]) -> tuple[Chroma, list[Document]]:
    """Chunk and index, stamping each chunk with its content-addressed id.

    The id goes in the metadata so it survives the round trip through the vector store and
    comes back on every retrieved document. Without that, a retrieval result cannot be joined
    to a label, and drift has nothing to compare.
    """
    chunks = splitter.split_documents(documents)

    ordinals: dict[str, int] = {}
    for chunk in chunks:
        uri = chunk.metadata["doc_uri"]
        revision = chunk.metadata.get("doc_revision", "1")
        ordinal = ordinals[uri] = ordinals.get(uri, -1) + 1
        chunk.metadata["chunk_id"] = chunk_id(
            uri, revision, ordinal, chunk.page_content, FINGERPRINT
        )
        chunk.metadata["ordinal"] = ordinal

    store = Chroma.from_documents(chunks, OpenAIEmbeddings(model="text-embedding-3-small"))
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
                        "chunk_id": c.metadata["chunk_id"],
                        "doc_uri": c.metadata["doc_uri"],
                        "doc_revision": c.metadata.get("doc_revision", "1"),
                        "ordinal": c.metadata["ordinal"],
                        "text": c.page_content,
                        "text_sha": text_sha(c.page_content),
                    }
                    for c in chunks
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def write_run(store: Chroma, queries: dict[str, str], k: int = 5, path: str = "hits.jsonl") -> None:
    """Integration point 2: what retrieval returned, in rank order, per query."""
    with Path(path).open("w", encoding="utf-8") as out:
        for query_id, query in queries.items():
            hits = store.similarity_search(query, k=k)
            ranking = [hit.metadata["chunk_id"] for hit in hits]
            out.write(json.dumps({"query_id": query_id, "ranking": ranking}) + "\n")


if __name__ == "__main__":
    docs = [
        Document(
            page_content=Path("help/refunds.md").read_text(encoding="utf-8"),
            metadata={"doc_uri": "help://billing/refunds", "doc_revision": "2026-08-04"},
        ),
    ]
    store, chunks = index(docs)
    write_corpus(chunks)
    write_run(store, {"q01": "can I get a refund on an annual plan?"})
    print("wrote corpus.json and hits.jsonl")
