# Troubleshooting

## Errors, exit code 2

These mean the tool could not answer the question, not that the answer was bad.

| Message | Cause | Fix |
|---|---|---|
| `cannot read <path>: no such file or directory` | wrong path, or a CI step running in a different working directory | check the path relative to where the job runs |
| `<command> needs --x and --y` | a required flag is missing | `retrieval-eval <command> --help` lists them |
| `unknown option '--x'` | a typo, or a flag from another version | check `--help`; flags are identical in both packages |
| `unknown command 'x'` | a typo | the message suggests the nearest command |
| `-k expects a positive integer` | `-k 0` or a non-numeric cutoff | `@k` metrics need `k >= 1` |
| `--color expects auto, always or never` | an unsupported colour mode | use one of the three, or set `NO_COLOR` |
| `unknown --to 'x'` | an unsupported conversion target | `qrels`, `trec-run` or `judgments` |
| a parse failure naming a line | malformed JSONL | the line number is in the message; a trailing comma or a truncated write is the usual cause |

## Validation codes

`retrieval-eval validate --judgments judgments.jsonl`. Errors exit `1`, warnings exit `0`.

### Errors

| Code | Meaning | What to do |
|---|---|---|
| `empty` | no judgments in the file | check the writer actually flushed |
| `no-positives` | no label has relevance >= 1 | recall is undefined without a positive; label at least one relevant chunk per query |
| `duplicate-label` | two labels for the same query and target | keep one; duplicates silently weight a query twice |
| `inconsistent-query-text` | one `query_id` carries two different query strings | the ids collided, or a query was edited without a new id |
| `bad-chunk-id` | a `chunk_id` is not `c1:` plus 32 hex characters | the producer is not computing ids as the spec defines them |
| `bad-text-sha` | a `text_sha` is not `t1:` plus 32 hex characters | same cause |

### Warnings

| Code | Meaning | Why it matters |
|---|---|---|
| `no-human-labels` | every label is synthetic | without human labels you cannot measure judge calibration, and synthetic labels become ground truth by default rather than by decision |
| `mixed-fingerprints` | labels span several corpus fingerprints | the set was written against more than one corpus state; run `drift` before trusting any metric from it |
| `thin-stratum` | a stratum has fewer than five labels | too few to gate on; the worst-stratum gate will be noise |
| `mixed-granularity` | some labels have a `chunk_id`, others are document-level | metrics mix two granularities, which makes them hard to compare over time |
| `no-chunk-ids` | no label has a `chunk_id` | drift can only work at document granularity; see [spec/chunk-id.md](../spec/chunk-id.md) |
| `missing-query-text` | a `query_id` has no query text on any row | the labels are still usable, but nobody can review them |

Warnings exit `0` on purpose. They describe a judgment set that is unsound rather than invalid,
and that distinction is the point: a file can parse perfectly and still be unable to support the
claim you are about to make with it.

## Common situations

**`drift` reports everything `ORPHANED`.** The corpus and the judgments do not share document
uris, or the corpus was dumped from a different source than the one labeled. Compare a `doc_uri`
from each file before looking any further.

**Every label is `SPLIT` after a re-chunk.** Expected when the new chunk size is much smaller than
the labeled text. These need re-judgment and are never guessed. If most of a set lands here, it is
usually cheaper to re-label against the new chunking than to recover the old set.

**`drift` exits 1 and the build fails, but nothing is wrong.** That is the design: any decay is a
non-zero exit. If you want a tolerance instead, use the JSON output and gate on
`summary.invalid_ratio` yourself, or run `drift --fix` in a scheduled job that opens a pull
request with the re-anchored labels for review.

**A metric moved and drift is clean.** Then the movement is real, which is the whole point of
running drift first.

**`worst-stratum` fails while the mean passes.** Working as intended. One query class is failing
and the average was hiding it. Look at the stratum table above the gate line.

**A gate reports `INDETERMINATE`.** The gate could not be decided: a delta gate with no
`--baseline`, a `ci-lower` gate on a metric with a single sample, or a gate naming a metric the
report does not contain. It exits `1`, because a gate that cannot tell you whether quality held is
not a passing gate.

**Colour codes in a log file.** Output is plain unless stdout is a terminal. If something forces a
terminal, set `NO_COLOR=1` or pass `--color never`.

**The two packages disagree.** They should not: CI diffs their output byte for byte over the
shared fixtures. If you find a case where they differ, that is the most valuable bug report this
project can get. Include both outputs and the input files.
