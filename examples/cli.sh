# Resolve a `retrieval-eval` to run, in this order:
#
#   1. an installed one on PATH, which is what a reader following the README will have
#   2. the TypeScript build in this checkout
#   3. the Python source in this checkout, which needs nothing installed at all
#
# Sourced by every example's run.sh so the examples work from a fresh clone, from an installed
# package, and in CI, without each one reimplementing the lookup.

set -euo pipefail

EXAMPLES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$EXAMPLES_DIR/.." && pwd)"

if command -v retrieval-eval >/dev/null 2>&1; then
  cli() { retrieval-eval "$@"; }
elif [ -f "$REPO_ROOT/packages/retrieval-eval/dist/cli.js" ] && command -v node >/dev/null 2>&1; then
  cli() { node "$REPO_ROOT/packages/retrieval-eval/dist/cli.js" "$@"; }
elif command -v python3 >/dev/null 2>&1; then
  cli() {
    PYTHONPATH="$REPO_ROOT/python/retrieval-eval/src${PYTHONPATH:+:$PYTHONPATH}" \
      python3 -m retrieval_eval.cli "$@"
  }
else
  echo "error  no retrieval-eval found: install the package, run 'pnpm build', or install python3" >&2
  exit 2
fi

# Print the command before running it, so the transcript reads like a session rather than a log.
# Dimmed only when the terminal wants colour, matching what the tool itself does.
# The banner goes to stderr, so a step whose stdout is redirected into a file still writes only
# what the tool produced.
if [ -t 2 ] && [ -z "${NO_COLOR:-}" ]; then
  step() { printf '\n\033[2m$ retrieval-eval %s\033[0m\n' "$*" >&2; cli "$@" || return $?; }
else
  step() { printf '\n$ retrieval-eval %s\n' "$*" >&2; cli "$@" || return $?; }
fi
