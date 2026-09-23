## What and why

<!-- One or two sentences. -->

## Checklist

- [ ] Behaviour changes start in `spec/`: a fixture was added or changed first
- [ ] **Both** implementations updated (a change in one language only is a bug)
- [ ] `pnpm -r test` passes
- [ ] `pytest` passes
- [ ] `python scripts/check_parity.py` is green
- [ ] `pnpm lint` / `ruff check .` / `mypy` clean
- [ ] Still zero runtime dependencies
- [ ] No new ground truth is invented (nothing guesses at a label)
