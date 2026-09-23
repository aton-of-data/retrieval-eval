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

A delta gate needs a previous report. Three workable strategies:

| Strategy | How | Trade-off |
|---|---|---|
| Commit it | `eval/baseline.json` in the repo, updated in the PR that moves it | visible in review, one more file to rebase |
| Build artifact | publish `report.json` from the default branch, download it in the PR job | no repo noise, needs an artifact retention window longer than your slowest PR |
| Package registry | store reports alongside releases | durable, more moving parts |

Whichever you pick, treat a baseline change as a reviewable event. A gate whose baseline is
updated automatically on failure is not a gate.

## GitHub Actions

```yaml
name: Retrieval quality
on: [pull_request]

jobs:
  retrieval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Labels still describe the corpus
        run: npx retrieval-eval drift --judgments eval/judgments.jsonl --corpus eval/corpus.json

      - name: Retrieval did not regress
        run: |
          npx retrieval-eval score \
            --judgments eval/judgments.jsonl --run eval/hits.jsonl -k 5 \
            --baseline eval/baseline.json \
            --gate recall@5:-0.02 \
            --gate worst-stratum:recall@5:0.7 \
            --out report.json

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: retrieval-report
          path: report.json
```

`if: always()` matters: the report is most useful on the run that failed.

## GitLab CI

```yaml
retrieval:
  image: python:3.12-slim
  before_script:
    - pip install retrieval-eval
  script:
    - retrieval-eval drift --judgments eval/judgments.jsonl --corpus eval/corpus.json
    - >
      retrieval-eval score
      --judgments eval/judgments.jsonl --run eval/hits.jsonl -k 5
      --baseline eval/baseline.json
      --gate recall@5:-0.02 --gate worst-stratum:recall@5:0.7
      --out report.json
  artifacts:
    when: always
    paths: [report.json]
```

## CircleCI

```yaml
jobs:
  retrieval:
    docker: [{ image: cimg/python:3.12 }]
    steps:
      - checkout
      - run: pip install retrieval-eval
      - run: retrieval-eval drift --judgments eval/judgments.jsonl --corpus eval/corpus.json
      - run: |
          retrieval-eval score \
            --judgments eval/judgments.jsonl --run eval/hits.jsonl -k 5 \
            --gate worst-stratum:recall@5:0.7 --out report.json
      - store_artifacts: { path: report.json }
```

## Jenkins

```groovy
stage('Retrieval quality') {
  steps {
    sh 'pip install --quiet retrieval-eval'
    sh 'retrieval-eval drift --judgments eval/judgments.jsonl --corpus eval/corpus.json'
    sh '''retrieval-eval score \
      --judgments eval/judgments.jsonl --run eval/hits.jsonl -k 5 \
      --gate worst-stratum:recall@5:0.7 --out report.json'''
  }
  post { always { archiveArtifacts artifacts: 'report.json' } }
}
```

## Azure Pipelines

```yaml
- script: pip install retrieval-eval
  displayName: Install
- script: retrieval-eval drift --judgments eval/judgments.jsonl --corpus eval/corpus.json
  displayName: Judgment drift
- script: >
    retrieval-eval score
    --judgments eval/judgments.jsonl --run eval/hits.jsonl -k 5
    --gate worst-stratum:recall@5:0.7 --out report.json
  displayName: Retrieval gates
```

## pre-commit

Cheap enough to run on every commit that touches the judgment set.

```yaml
repos:
  - repo: local
    hooks:
      - id: retrieval-eval-validate
        name: validate relevance judgments
        entry: retrieval-eval validate --judgments
        language: system
        files: ^eval/judgments\.jsonl$
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
