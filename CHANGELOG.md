# Changelog

Both packages release together under the same version: a spec version that means two different
things in two registries defeats the point.

## Unreleased

### Fixed

- **`bin` is written as `dist/cli.js`**, the form npm normalizes to. npm 12 rewrote
  `./dist/cli.js` on every publish and warned that the entry was invalid. Nothing was wrong with
  the published command; the warning was.

## 0.1.1, 2026-09-24

No change to the spec, the metrics or either CLI. This release exists to put both packages
through the release pipeline end to end, which 0.1.0 did not manage for npm.

### Changed

- **npm publishes through trusted publishing.** The release workflow authenticates to npm with
  GitHub's OIDC token instead of a long-lived `NPM_TOKEN`, and every tarball carries a
  provenance attestation linking it to the commit and workflow run that built it. PyPI already
  worked this way.
- **A release tag must match the version.** The workflow refuses to publish when `vX.Y.Z` does
  not equal the version in all four places `scripts/check-version.mjs` checks.
- **A tagged release creates the GitHub release**, with this changelog's entry as its notes.

### Added

- **A docs site**, https://aton-of-data.github.io/retrieval-eval/, rendered from the root README
  by `scripts/build-site.mjs`. The README stays the single source; the site is derived from it.
- **Version badges** for npm, PyPI and the supported Node and Python versions.

### Dependencies

Development and CI only: both packages still have zero runtime dependencies.

- Biome 1.9 → 2.5, Vitest 2.1 → 4.1 (with Vite 8), TypeScript 5.6 → 5.9.
- `actions/checkout`, `actions/setup-node` and `actions/setup-python` 4/5 → 7, and
  `pnpm/action-setup` 4 → 6, `actions/upload-pages-artifact` 3 → 5 and `actions/deploy-pages`
  4 → 5, all of which move the actions onto the Node 24 runtime.
- **Held back:** TypeScript 7, Vitest 5, Changesets 3 and `@types/node` 26. Each either drops
  Node 20, which is still supported and tested, or breaks the declaration build. The reasons are
  recorded beside the ignore rules in `.github/dependabot.yml`.

## 0.1.0, 2026-09-24

First release. The spec, and two reference implementations that prove it.

### Added

- **`spec/`**: `judgments.schema.json`, `report.schema.json`, `chunk-id.md`, and the shared
  `fixtures/` both implementations are tested against.
- **`drift`**: classify every relevance label against a live corpus as `VALID`,
  `RE_ANCHORABLE`, `MERGED`, `SPLIT` or `ORPHANED`, and `--fix` to re-anchor the recoverable
  ones. `SPLIT` and `ORPHANED` are never guessed.
- **`score`**: `precision@k`, `recall@k`, `ndcg@k`, `mrr`, `map`, `hit_rate@k`; per-stratum
  breakdown; per-query detail. Deterministic, no LLM, no API key.
- **Gates**: absolute, delta-against-baseline, `worst-stratum`, and `ci-lower`, with a third
  verdict `INDETERMINATE` for when the data cannot answer the question asked of it.
- **`validate`**: structural errors plus statistical warnings: `no-positives`,
  `no-human-labels`, `mixed-fingerprints`, `thin-stratum`, `no-chunk-ids`, `mixed-granularity`.
- **`convert`**: lossless TREC qrels and TREC run interoperability in both directions.
- **`scripts/check_parity.py`**: runs both CLIs over the fixtures and fails if they disagree.
- **The spec ships inside both packages.** `spec/` (schemas, hash definition and fixtures) is
  copied into each package at build time, so a port never has to start from the GitHub UI.
- **Generated READMEs.** The npm and PyPI READMEs are derived from the root one by
  `scripts/build-readme.mjs`; CI fails if a copy drifts.
- **`scripts/check-version.mjs`**: the version is written in four places (two manifests, two
  `TOOL_VERSION` constants). CI asserts they agree.

### Added during pre-release hardening

- **A documented CLI surface.** Sectioned help for the tool and for each command, `--color
  auto|always|never` beside `NO_COLOR`, one-line errors with a suggested next command, a
  nearest-command suggestion for typos, and documented exit codes: `0` passed, `1` a gate failed
  or labels decayed, `2` bad invocation or unreadable input.
- **`summarize(samples)`** in both implementations: mean, `n`, sample standard deviation and a
  95% Student-t interval, from repeated samples of a non-deterministic metric. The interval is
  not clamped. A normal approximation is too narrow at the sample sizes a judge is actually run
  (five draws is df=4, where t is 2.776), and raising a negative lower bound to 0 lets a
  `ci-lower` gate pass. One sample returns no interval at all, so a `ci-lower` gate over it is
  `INDETERMINATE` rather than a quiet pass. The report format always carried `ci`; nothing
  computed it until now, which left the project's own statistical-honesty argument as advice.
- **Parity over rendered output, not just JSON.** `scripts/check_parity.py` diffs human-readable
  stdout, every help screen and the stderr of failing invocations, byte for byte, across 39
  cases. Two implementations that document themselves differently are two tools.
- **CLI test suites in both languages**, covering exit codes, error wording, colour policy,
  `--fix` idempotence and gate outcomes, plus coverage floors in `vitest.config.ts` and a
  `--cov-fail-under` gate for pytest.
- **`docs/`.** CLI reference, CI concepts, interoperability and migration paths, and a
  troubleshooting page covering every error and validation code.
- **`examples/` covers real stacks, real pipelines and the full surface.** Six runnable
  scenarios, each executed and asserted by CI: `quickstart`, `support-bot` (an average hiding a
  broken query class, then a re-chunk), `reranker-vs-chunker` (two numbers that localize a
  failure), `graded-relevance` (one run scored at two thresholds), `judged-metrics` (gating on a
  confidence interval, in both languages) and `beir-qrels` (a public collection in and back out).
  `examples/frameworks/` carries the integration for LangChain in Python and JavaScript,
  LlamaIndex, Haystack, Chroma, Qdrant, pgvector, RAGAS and DeepEval, plus
  `verify_integrations.py`, which runs the real code path for every framework the reader has
  installed and skips the rest. `examples/pipelines/` carries complete jobs for Jenkins, GitHub
  Actions, GitLab CI, Azure Pipelines, CircleCI and pre-commit, plus a scheduled re-anchor that
  opens a pull request instead of repairing a golden set unreviewed.

### Changed during pre-release hardening

- **Metric names carry their cutoff.** `mrr` and `map` are now `mrr@k` and `map@k`, because both
  were already computed within the cutoff. A number that means something other than its name is
  how a report stops being trustworthy, and a `trec_eval` user reading `map` would have assumed
  an unbounded run.
- **Queries with nothing relevant to find are excluded from the averages**, not scored zero.
  Recall, nDCG, MRR and AP are undefined when a query has no label at the threshold, so scoring
  them zero reported a corpus gap as a retrieval failure. The count is surfaced as
  `judgments.queries_scored` and printed under the metrics.
- **A stratum with no scored query is never the worst stratum.** It appears in the table as
  "not scored" rather than sitting at 0.0000 and failing a worst-stratum gate over an empty set.
- **A run where every query is below the threshold does not score zero.** The averages are
  omitted, the verdict is `INDETERMINATE`, and an absolute gate says the metric was not
  computed. Reporting 0 there failed a build over an empty set.
- **`convert --qrels` reads both qrels shapes**, the TREC four-column form and BEIR's three
  columns behind a `query-id corpus-id score` header. Accepting only the first meant not being
  able to read the collections the README says are one conversion away, which the `beir-qrels`
  example found on its first run.
- **One canonical way to write a judgments file:** schema field order, unknown fields last,
  compact JSON. A file written by one implementation is byte-identical to the same file written
  by the other, so `drift --fix` produces a diff of the labels that changed rather than of the
  whole file.
- **Parse errors name the line in the file**, not the index of the row, which diverged as soon as
  a file had a blank or commented line.
- **Literal control characters are gone from the sources.** A U+001F separator and two NUL
  separators made `grep`, `rg` and diff treat the files as binary.
- Error messages are phrased identically in both implementations, including filesystem failures,
  so the parity check can compare them.
- `research/` reduced to the three documents the positioning actually rests on: the problem, the
  market gap with an evidence grade per claim, and the impact argument. The broader `open-rag`
  architecture and connector drafts were out of scope and were removed rather than kept as noise.

### Fixed before first release

- **The installed npm binary did nothing.** `cli.ts` ran `main()` only when `argv[1]` matched
  `import.meta.url`, but npm and npx invoke a binary through a symlink in `node_modules/.bin`,
  and `import.meta.url` is always the real path. Every installed CLI, `npx retrieval-eval`
  included, exited 0 with no output, while every test passed because tests run the source tree.
  The link is now resolved first, and CI installs the packed tarball and the wheel and runs them
  as a user would.
- `files: ["spec"]` in `package.json` silently shipped nothing, because `spec/` lives at the
  repo root and npm cannot include paths outside the package directory. The spec is now copied
  in at build time, and CI inspects the actual tarball rather than trusting the manifest.
- The wheel declared `Typing :: Typed` without a `py.typed` marker, so PEP 561 consumers got no
  type information from a codebase that is `mypy --strict` clean. The marker now ships and CI
  checks for it.
- `OWNER` placeholders in `pyproject.toml`, `package.json`, `SECURITY.md` and the CLI help text
  would have published permanently-dead links to both registries.
- The README claimed there was "no IR metrics package on npm at all." There are a few, all
  narrow, unmaintained or coupled to something else. The claim is now the one that is actually
  true and still strong, with the registry state dated.
- `check_parity.py` reported eleven JSON decode errors when run with an interpreter that could
  not import the package, which reads like a parity break rather than a missing install. It now
  checks first and says what to run.

### Fixed after an adversarial audit

Four findings from deliberately hostile inputs rather than friendly ones. The rigour that had
been applied to judgments had never been applied to the *run*, which was the one input taken on
trust.

- **A repeated key in a ranking inflated every metric past its range.** A retriever returning
  the same chunk twice, routine when a hybrid search merges two indexes without deduplicating,
  scored the repeat as a fresh hit: `recall@5` came back `2.5` and cleared a `recall@5:0.9`
  gate. A repeat is not new evidence, so only the first occurrence counts, and the report now
  names the queries it corrected instead of correcting them quietly.
- **`parse_run` now rejects a run that is malformed rather than merely unsound.** A ranking
  holding a number, `null` or an object was accepted silently, and two entries claiming the same
  query were resolved last-wins, though the file no longer said what that query's ranking was.
- **`score` no longer reports `PASS` over a judgment set `validate` rejects.** Two labels
  disagreeing about the same query and target is a `duplicate-label` **error** that exits
  non-zero under `validate`; `score` read the same file, resolved the conflict last-wins and
  went green. The verdict is now `INDETERMINATE`, and a gate that happens to pass no longer
  clears a finding it never looked at.
- **Three orderings differed between the two implementations.** `missing-query-text` and
  `thin-stratum` were emitted in file order by TypeScript and sorted order by Python, and the
  stratum table used `localeCompare`, which is locale-dependent and so disagreed with Python
  *and* with the same build on another machine. All three now sort by Unicode code point.
  Every existing fixture happened to have sorted, ASCII names, which is why 39 parity cases
  passed over this; `unsorted-queries` and `stratum-order` exist so that cannot recur.
- **Gate thresholds are parsed identically.** `parseFloat` read `0.5abc` as `0.5` while Python's
  `float` rejected it, and `float` accepted `nan` and `infinity` while `parseFloat` rejected
  them. Both now take finite decimals only.

### Changed after that audit

- `spec/fixtures/README.md` documents the fixture format. The fixtures are normative — design
  rule 6 says every implementation must pass them — but their shape had to be reverse-engineered
  from the files, which is not a spec.
- The README no longer claims reports are byte-identical across the two implementations. They
  agree as *data*: JSON writes a whole number as `1` in JavaScript and `1.0` in Python, which
  `check_parity.py` has always known and normalized. Judgments files and rendered output are
  byte-identical, and that is now what is claimed.
- Example, integration and pipeline counts in the README match what is in `examples/`.

### Notes

- Zero runtime dependencies in both packages.
- `MERGED` was added after `examples/quickstart` showed that raising `chunk_size` reported labels
  as `ORPHANED` when their text was plainly still present, a wrong answer and the kind of wrong
  that erodes trust in a measurement tool.
