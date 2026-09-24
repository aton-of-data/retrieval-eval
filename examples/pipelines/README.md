# Pipelines

Complete, copyable jobs for the systems teams actually run. Each one does the same two things in
the same order, because the order is the point: establish that the labels still describe the
corpus, then measure retrieval against them.

| File | System | Notes |
|---|---|---|
| [`Jenkinsfile`](Jenkinsfile) | Jenkins | declarative pipeline, separates exit `1` from exit `2`, archives the reports |
| [`github-actions.yml`](github-actions.yml) | GitHub Actions | runs on pull requests and comments the numbers on the PR |
| [`gitlab-ci.yml`](gitlab-ci.yml) | GitLab CI | merge-request rule, report kept as an artifact |
| [`azure-pipelines.yml`](azure-pipelines.yml) | Azure Pipelines | publishes the report as a build artifact |
| [`circleci-config.yml`](circleci-config.yml) | CircleCI | stores the report as an artifact |
| [`pre-commit-config.yaml`](pre-commit-config.yaml) | pre-commit | catches an unsound judgment set before it reaches CI |
| [`nightly-drift-pr.yml`](nightly-drift-pr.yml) | GitHub Actions, scheduled | re-anchors decayed labels nightly and opens a pull request for review |

## The two files your pipeline has to produce

Everything here assumes your own code writes `eval/corpus.json` and `eval/hits.jsonl`, the way
[../frameworks](../frameworks) shows for each stack. `eval/judgments.jsonl` is committed, because
labels are an asset and belong in review.

## The three decisions each of these encodes

**Exit `1` and exit `2` mean different things.** A failed gate is a quality signal. A bad path or
a malformed file is a pipeline bug. The Jenkinsfile keeps them apart explicitly, and every other
file here is arranged so you can. A pipeline that treats every non-zero exit as "retrieval got
worse" will eventually cry wolf, and after that nobody reads the gate.

**Drift is checked before metrics, and it is not automatically fatal.** Decayed labels do not
mean quality dropped. They mean the numbers that follow are measuring two changes at once. The
Jenkins job marks the build unstable and keeps the report rather than failing outright, which is
usually what you want the first time a chunker changes.

**Nothing repairs itself unsupervised.** `drift --fix` is mechanical and safe, and it still opens
a pull request rather than pushing to the default branch. The nightly job exists so that the
repair is a small reviewed diff on a Tuesday instead of a 400-label archaeology project before a
release.

## Keeping a baseline

The delta gate needs a previous report. Pick one:

| Strategy | How | Trade-off |
|---|---|---|
| Commit it | `eval/baseline.json` in the repo, updated in the pull request that moves it | visible in review, one more file to rebase |
| Build artifact | publish `report.json` from the default branch, download it in the pull-request job | no repo noise, needs a retention window longer than your slowest review |
| Package registry | store reports next to releases | durable, more moving parts |

Whichever you choose, a baseline change is a reviewable event. A gate whose baseline updates
itself on failure is not a gate.
