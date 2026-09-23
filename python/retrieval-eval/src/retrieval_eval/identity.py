"""Content-addressed chunk identity.

A relevance label must point at *text*, not at "position 7 of whatever the chunker produced
that day". Everything :mod:`retrieval_eval.drift` can do follows from that.

The three normalization steps and the field order below must match the TypeScript
implementation exactly; ``spec/fixtures/chunk-id`` holds the vectors that prove they do.
"""

from __future__ import annotations

import hashlib
import unicodedata

#: U+001F unit separator: joins canonical fields without colliding with real content.
SEP = "\x1f"


def normalize(text: str) -> str:
    """Normalize chunk text: NFC, then newline endings, then strip the whole string."""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.strip()


def _h128(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def text_sha(text: str) -> str:
    """Hash the normalized text, so a judgment can describe itself without storing the text."""
    return f"t1:{_h128(normalize(text))}"


def chunk_id(
    doc_uri: str,
    doc_revision: str,
    ordinal: int,
    text: str,
    chunker_fingerprint: str,
) -> str:
    """Compute a content-addressed chunk id.

    Args:
        doc_uri: Canonical, stable document uri. Not a local path.
        doc_revision: Source etag or version; the text hash when the source has none.
        ordinal: Zero-based chunk index within the document.
        text: The chunk body, normalized by :func:`normalize`.
        chunker_fingerprint: Opaque stable string identifying chunker plus settings.

    Returns:
        A ``c1:``-prefixed 128-bit hex digest.
    """
    canonical = SEP.join(
        [doc_uri, doc_revision, str(ordinal), normalize(text), chunker_fingerprint]
    )
    return f"c1:{_h128(canonical)}"
