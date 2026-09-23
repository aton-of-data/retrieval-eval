# Chunk identity

A relevance label must point at *text*, not at "position 7 of whatever the chunker produced that
day." Everything `drift` can do follows from that.

## Definition

```
chunk_id = "c1:" + lowercase_hex( SHA256( canonical )[0..16] )     # 128 bits, 32 hex chars
```

`canonical` is the UTF-8 encoding of these five fields joined by `U+001F` (unit separator):

```
doc_uri ␟ doc_revision ␟ ordinal ␟ normalize(text) ␟ chunker_fingerprint
```

| Field | Notes |
|---|---|
| `doc_uri` | canonical and stable (`notion://page/abc`, `s3://bucket/key`). Not a local path. |
| `doc_revision` | source etag/version, or `normalize(text)`'s own hash when the source has none |
| `ordinal` | 0-based chunk index within the document, base-10, no padding |
| `text` | the chunk body, normalized as below |
| `chunker_fingerprint` | opaque, stable string identifying chunker + settings (e.g. `recursive/512/64`) |

## `normalize(text)`

Exactly three steps, in order. Any deviation breaks cross-language agreement:

1. Unicode **NFC** normalization.
2. Line endings `\r\n` and `\r` → `\n`.
3. Strip leading and trailing whitespace from the **whole string** (not per line).

Deliberately *not* done: case folding, punctuation stripping, internal whitespace collapsing.
Those lose information a retrieval system legitimately depends on.

## `text_sha`

```
text_sha = "t1:" + lowercase_hex( SHA256( normalize(text) )[0..16] )
```

Recorded on a judgment so a label is **self-describing**: `drift` can re-anchor it after a
re-chunk without storing the text itself. Store `chunk_text` too when you want `SPLIT` detection
and can accept the size; use `text_sha` alone when the corpus is sensitive.

## Why SHA-256 and not BLAKE3

BLAKE3 is faster and would be the better hash. SHA-256 is in the standard library of every
language that matters, which keeps implementations dependency-free, worth more than throughput
for files this size. The `c1:`/`t1:` prefixes exist so a future `c2:` can switch.
