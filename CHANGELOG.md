# Changelog

Both packages release together under the same version: a spec version that means two different
things in two registries defeats the point.

## 0.1.0, unreleased

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
- **Parity over the rendered output, not just the JSON.** `scripts/check_parity.py` now diffs
  human-readable stdout, every help screen and the stderr of failing invocations, byte for byte,
  across 31 cases. Two implementations that document themselves differently are two tools.
- **CLI test suites in both languages**, covering exit codes, error wording, colour policy,
  `--fix` idempotence and gate outcomes.
- **Coverage floors.** Thresholds in `vitest.config.ts` and a `--cov-fail-under` gate for pytest.
- **`docs/`.** CLI reference, CI recipes for five pipeline systems plus pre-commit,
  interoperability and migration paths, and a troubleshooting page covering every error and
  validation code.

### Changed during pre-release hardening

- `research/` reduced to the three documents the positioning actually rests on: the problem, the
  market gap with an evidence grade per claim, and the impact argument. The broader `open-rag`
  architecture and connector drafts were out of scope and were removed rather than kept as noise.
- Error messages are phrased identically in both implementations, including filesystem failures,
  so the parity check can compare them.
- Two literal NUL characters used as map-key separators in the TypeScript source were replaced
  with `\u0000` escapes; they made the files read as binary to `grep`, `rg` and diff tools.

### Fixed before first release

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

### Notes

- Zero runtime dependencies in both packages.
- `MERGED` was added after `examples/quickstart` showed that raising `chunk_size` reported labels
  as `ORPHANED` when their text was plainly still present, a wrong answer and the kind of wrong
  that erodes trust in a measurement tool.
