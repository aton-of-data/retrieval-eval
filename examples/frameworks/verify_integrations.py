"""Prove the integrations in this directory still match the frameworks they integrate with.

Framework APIs move. An example that was correct when it was written is a liability once it is
not, so this script runs the real code path for every framework you have installed, skips the
ones you do not, and reports what it checked.

    pip install retrieval-eval
    pip install langchain-text-splitters llama-index-core haystack-ai chromadb   # any subset
    python verify_integrations.py

No API key, no network, no model download: where a stack needs an embedder, a deterministic
stand-in is used, because what is being checked is the plumbing that carries a chunk id, not
the quality of anyone's vectors.

Last run green against: langchain-text-splitters 1.1.2, llama-index-core 0.14.25,
haystack-ai 3.1.1, chromadb 1.5.9, on 2026-09-23.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from retrieval_eval import (
    chunk_id,
    drift,
    parse_corpus,
    parse_judgments,
    parse_run,
    score,
    text_sha,
)

FINGERPRINT = "example/512/64"


def corpus_from(chunks: list[dict]) -> str:
    """The corpus snapshot every example writes, as JSON."""
    return json.dumps(
        {
            "corpus_fingerprint": FINGERPRINT,
            "chunker_fingerprint": FINGERPRINT,
            "chunks": chunks,
        }
    )


def label_for(chunk: dict) -> str:
    """One judgment anchored to a chunk, as JSONL."""
    return (
        json.dumps(
            {
                "query_id": "q1",
                "doc_uri": chunk["doc_uri"],
                "chunk_id": chunk["chunk_id"],
                "text_sha": chunk["text_sha"],
                "chunk_text": chunk["text"],
                "relevance": 2,
                "labeled_by": "human:verify",
            }
        )
        + "\n"
    )


def check_langchain() -> list[str]:
    """LangChain: ids in Document.metadata survive chunking, and a re-chunk is detected."""
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    documents = [
        Document(
            page_content="Annual plans may be refunded within 30 days of renewal.\n\n" * 6,
            metadata={"doc_uri": "help://billing/refunds", "doc_revision": "2026-08-04"},
        )
    ]

    def chunks_at(size: int, overlap: int, fingerprint: str) -> list[dict]:
        splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
        out: list[dict] = []
        for ordinal, chunk in enumerate(splitter.split_documents(documents)):
            uri = chunk.metadata["doc_uri"]
            revision = chunk.metadata["doc_revision"]
            out.append(
                {
                    "chunk_id": chunk_id(uri, revision, ordinal, chunk.page_content, fingerprint),
                    "doc_uri": uri,
                    "doc_revision": revision,
                    "ordinal": ordinal,
                    "text": chunk.page_content,
                    "text_sha": text_sha(chunk.page_content),
                }
            )
        return out

    live = chunks_at(512, 64, FINGERPRINT)
    labels = parse_judgments(label_for(live[0]))

    before = drift(labels, parse_corpus(corpus_from(live))).findings[0].status
    after = drift(labels, parse_corpus(corpus_from(chunks_at(128, 16, "example/128/16"))))
    assert before == "VALID", f"label should be VALID against its own corpus, got {before}"
    assert after.summary.invalid_ratio == 1.0, "a smaller re-chunk should decay the label"

    return [
        f"{len(live)} chunks at 512, label {before} against them",
        f"after re-chunking at 128: {after.findings[0].status}",
    ]


def check_llamaindex() -> list[str]:
    """LlamaIndex: node_id is not stable across a re-parse, the content-addressed id is."""
    from llama_index.core import Document
    from llama_index.core.node_parser import SentenceSplitter

    documents = [
        Document(
            text="Annual plans may be refunded within 30 days of renewal. " * 40,
            metadata={"doc_uri": "help://billing/refunds", "doc_revision": "2026-08-04"},
        )
    ]

    def parse() -> list:
        return SentenceSplitter(chunk_size=512, chunk_overlap=64).get_nodes_from_documents(
            documents
        )

    first, again = parse()[0], parse()[0]
    stable_node_id = first.node_id == again.node_id
    ids = [
        chunk_id("help://billing/refunds", "2026-08-04", 0, node.text, FINGERPRINT)
        for node in (first, again)
    ]

    # The claim the README makes about this framework, checked rather than asserted.
    assert not stable_node_id, "node_id unexpectedly stable: the README's reasoning needs updating"
    assert ids[0] == ids[1], "content-addressed id must not change across a re-parse"

    first.metadata["chunk_id"] = ids[0]
    first.excluded_embed_metadata_keys.append("chunk_id")
    assert "chunk_id" in first.excluded_embed_metadata_keys

    return [
        f"node_id across two parses: {'stable' if stable_node_id else 'different'}",
        "chunk_id across two parses: identical",
        "chunk_id excluded from the embedded metadata",
    ]


def check_haystack() -> list[str]:
    """Haystack: Document.id includes metadata, so it cannot anchor a label."""
    from haystack import Document
    from haystack.components.preprocessors import DocumentSplitter
    from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
    from haystack.document_stores.in_memory import InMemoryDocumentStore

    documents = [
        Document(
            content="Annual plans may be refunded within 30 days of renewal. " * 30,
            meta={"doc_uri": "help://billing/refunds", "doc_revision": "2026-08-04"},
        ),
        Document(
            content="Standard delivery takes three to five business days. " * 30,
            meta={"doc_uri": "help://shipping/delivery", "doc_revision": "2026-07-19"},
        ),
    ]

    splitter = DocumentSplitter(split_by="word", split_length=120, split_overlap=20)
    splitter.warm_up()
    chunks = splitter.run(documents=documents)["documents"]

    snapshot: list[dict] = []
    ordinals: dict[str, int] = {}
    for chunk in chunks:
        uri = chunk.meta["doc_uri"]
        revision = chunk.meta["doc_revision"]
        ordinal = ordinals[uri] = ordinals.get(uri, -1) + 1
        chunk.meta["chunk_id"] = chunk_id(uri, revision, ordinal, chunk.content or "", FINGERPRINT)
        snapshot.append(
            {
                "chunk_id": chunk.meta["chunk_id"],
                "doc_uri": uri,
                "doc_revision": revision,
                "ordinal": ordinal,
                "text": chunk.content,
                "text_sha": text_sha(chunk.content or ""),
            }
        )

    store = InMemoryDocumentStore()
    store.write_documents(chunks)
    hits = InMemoryBM25Retriever(document_store=store, top_k=3).run(
        query="can I get a refund on an annual plan?"
    )["documents"]
    ranking = [hit.meta["chunk_id"] for hit in hits]

    labels = parse_judgments(label_for(snapshot[0]))
    run = parse_run(json.dumps({"query_id": "q1", "ranking": ranking}) + "\n")
    recall = score(labels, run, k=3).metrics["recall@3"].value

    with_meta = Document(content="same text", meta={"doc_uri": "d"}).id
    with_more = Document(content="same text", meta={"doc_uri": "d", "extra": 1}).id
    assert with_meta != with_more, "Haystack's id no longer depends on metadata"
    assert drift(labels, parse_corpus(corpus_from(snapshot))).findings[0].status == "VALID"

    return [
        f"{len(chunks)} chunks, BM25 returned {len(ranking)} ids, recall@3 = {recall}",
        "Document.id changes when metadata changes, so the spec's id is kept separately",
    ]


def check_chroma() -> list[str]:
    """Chroma: the content-addressed id is the collection id and comes back from a query."""
    import chromadb
    from chromadb.api.types import EmbeddingFunction

    class WordCount(EmbeddingFunction):
        """A deterministic stand-in for a model, so this needs no download and no key."""

        def __init__(self) -> None:
            self.terms = ("refund", "delivery", "invoice", "annual")

        def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
            return [[float(text.lower().count(term)) for term in self.terms] for text in input]

        @staticmethod
        def name() -> str:
            return "wordcount"

    rows = [
        {
            "doc_uri": "help://billing/refunds",
            "doc_revision": "2026-08-04",
            "ordinal": 0,
            "text": "Annual plans may be refunded within 30 days of renewal.",
        },
        {
            "doc_uri": "help://shipping/delivery",
            "doc_revision": "2026-07-19",
            "ordinal": 0,
            "text": "Standard delivery takes three to five business days.",
        },
    ]
    ids = [
        chunk_id(r["doc_uri"], r["doc_revision"], r["ordinal"], r["text"], FINGERPRINT)
        for r in rows
    ]

    collection = chromadb.Client().get_or_create_collection(
        "verify-integrations", embedding_function=WordCount()
    )
    collection.upsert(
        ids=ids,
        documents=[r["text"] for r in rows],
        metadatas=[
            {"doc_uri": r["doc_uri"], "doc_revision": r["doc_revision"], "ordinal": r["ordinal"]}
            for r in rows
        ],
    )

    stored = collection.get(include=["documents", "metadatas"])
    snapshot = [
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
    ranking = collection.query(query_texts=["annual plan refund"], n_results=2)["ids"][0]

    labels = parse_judgments(label_for(next(c for c in snapshot if c["chunk_id"] == ids[0])))
    run = parse_run(json.dumps({"query_id": "q1", "ranking": ranking}) + "\n")

    assert set(ranking) <= set(ids), "query returned ids the collection was not given"
    assert drift(labels, parse_corpus(corpus_from(snapshot))).findings[0].status == "VALID"

    return [
        f"{len(snapshot)} chunks stored and read back with their ids",
        f"recall@2 = {score(labels, run, k=2).metrics['recall@2'].value}",
    ]


CHECKS: dict[str, Callable[[], list[str]]] = {
    "langchain": check_langchain,
    "llamaindex": check_llamaindex,
    "haystack": check_haystack,
    "chroma": check_chroma,
}


def main() -> int:
    """Run every check whose framework is installed. Missing frameworks are skipped, not failed."""
    failures = 0
    skipped = 0

    for name, check in CHECKS.items():
        try:
            notes = check()
        except ImportError:
            skipped += 1
            print(f"skip {name}  not installed")
            continue
        except AssertionError as error:
            failures += 1
            print(f"FAIL {name}  {error}")
            continue
        except Exception as error:  # noqa: BLE001
            # An API that moved shows up here, which is the whole reason this script exists.
            failures += 1
            print(f"FAIL {name}  {type(error).__name__}: {error}")
            continue

        print(f"ok   {name}")
        for note in notes:
            print(f"     {note}")

    checked = len(CHECKS) - skipped
    print(f"\n{checked - failures}/{checked} installed frameworks verified, {skipped} skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
