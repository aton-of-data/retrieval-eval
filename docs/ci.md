# Running this in CI

Two checks belong in a pipeline, in this order:

1. **`drift`**, to establish that the labels still describe the live corpus. A metric computed
   against decayed labels is measuring two changes at once, so this runs first and fails fast.
2. **`score`**, with gates, to establish that retrieval did not regress.

Both are deterministic, call no model, need no API key and finish in milliseconds, so there is no
reason to sample them or run them nightly instead of per commit.

## Choosing gates

Start with two, and add more only when you have the labels to support them.

```
--gate recall@5:-0.02                 regression tolerance against the last accepted report
--gate worst-stratum:recall@5:0.7     a floor no query class may fall below
```

The delta gate catches slow erosion that an absolute floor allows. The worst-stratum gate catches
the failure an average hides. An absolute floor alone catches neither, which is why it is the
weakest gate and a poor default.

`--threshold` sets the lowest relevance grade that counts as relevant. Graded collections
sometimes need `--threshold 2` to mean what you think `recall` means.

## Keeping a baseline

A delta gate needs a previous report. The three workable strategies, and their trade-offs, are in
[examples/pipelines](../examples/pipelines#keeping-a-baseline). Whichever you pick, treat a
baseline change as a reviewable event: a gate whose baseline updates itself on failure is not a
gate.

## Complete jobs, ready to copy

Each system has a whole working file in [examples/pipelines](../examples/pipelines) rather than a
fragment here:

| File | System |
|---|---|
| [`Jenkinsfile`](../examples/pipelines/Jenkinsfile) | Jenkins, with exit `1` and exit `2` handled separately |
| [`github-actions.yml`](../examples/pipelines/github-actions.yml) | GitHub Actions, commenting the numbers on the pull request |
| [`gitlab-ci.yml`](../examples/pipelines/gitlab-ci.yml) | GitLab CI |
| [`azure-pipelines.yml`](../examples/pipelines/azure-pipelines.yml) | Azure Pipelines |
| [`circleci-config.yml`](../examples/pipelines/circleci-config.yml) | CircleCI |
| [`pre-commit-config.yaml`](../examples/pipelines/pre-commit-config.yaml) | pre-commit |
| [`nightly-drift-pr.yml`](../examples/pipelines/nightly-drift-pr.yml) | a scheduled re-anchor that opens a pull request |

The shortest useful version, for orientation:

```yaml
- run: npx retrieval-eval drift --judgments eval/judgments.jsonl --corpus eval/corpus.json
- run: |
    npx retrieval-eval score \
      --judgments eval/judgments.jsonl --run eval/hits.jsonl -k 5 \
      --baseline eval/baseline.json \
      --gate "recall@5:-0.02" --gate "worst-stratum:recall@5:0.7" \
      --out report.json
```

## Reading the exit code

| Code | Meaning | What a pipeline should do |
|---|---|---|
| `0` | passed | continue |
| `1` | a gate failed, or labels decayed | fail the job, publish the report |
| `2` | bad invocation or unreadable input | fail the job, this is a pipeline bug rather than a quality signal |

Distinguishing `1` from `2` is worth the extra line in a script. Treating every non-zero exit as
"quality regressed" turns a typo in a path into a false alarm about your retriever, and teams
that get those stop believing the gate.

## Where the inputs come from

`judgments.jsonl` is yours to maintain. `hits.jsonl` is produced by your retrieval code: one JSON
object per query with `query_id` and a `ranking` array of chunk ids or document uris. `corpus.json`
is a dump of the live chunks. Both shapes are in the [spec](../spec/).

Emitting `corpus.json` from your indexing pipeline is what makes `drift` possible, and it is the
one integration step this tool asks of you. If computing `chunk_id` the specified way is not
practical yet, ship the corpus anyway: drift degrades to text matching and document granularity
rather than to nothing.
