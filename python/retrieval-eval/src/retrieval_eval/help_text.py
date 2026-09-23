"""Every help screen the CLI prints.

The TypeScript implementation carries the same text and CI diffs the two, because a tool that
reports drift should not ship documentation that has drifted from its twin.
"""

from __future__ import annotations

from .report import TOOL_VERSION

COMMANDS = ("drift", "score", "validate", "convert")

_ROOT = """\
retrieval-eval {version}
Does your retrieval find the right things, and are your labels still true?

Usage
  retrieval-eval <command> [options]

Commands
  drift      report which relevance labels survived a re-chunk, and re-anchor them
  score      compute deterministic retrieval metrics and gate a build on them
  validate   check a judgment set for problems before you trust its numbers
  convert    move labels and runs between this format and TREC qrels

Global options
  -h, --help          show this help, or 'retrieval-eval <command> --help'
  -v, --version       print the version and exit
      --json          emit machine-readable JSON on stdout
      --color <when>  auto, always or never (default auto; NO_COLOR is honored)

Exit codes
  0  success, every gate passed
  1  a gate failed, a label decayed, or validation found an error
  2  usage error, unreadable file, or malformed input

Examples
  retrieval-eval drift    --judgments judgments.jsonl --corpus corpus.json --fix
  retrieval-eval score    --judgments judgments.jsonl --run hits.jsonl -k 5
  retrieval-eval validate --judgments judgments.jsonl
  retrieval-eval convert  --judgments judgments.jsonl --to qrels

Docs  https://github.com/aton-of-data/retrieval-eval
"""

ROOT_HELP = _ROOT.format(version=TOOL_VERSION).rstrip("\n")

COMMAND_HELP = {
    "drift": """\
retrieval-eval drift
Report which relevance labels are still true against the live corpus.

Usage
  retrieval-eval drift --judgments <file> --corpus <file> [options]

Options
      --judgments <file>  the labels to check, JSONL
      --corpus <file>     the live corpus, JSON
      --fix               re-anchor recoverable labels in place, rewriting --judgments
      --json              emit every finding as JSON
      --color <when>      auto, always or never
  -h, --help              show this help

Label classes
  VALID          the labeled chunk_id is still in the corpus
  RE_ANCHORABLE  the labeled text moved to a new chunk_id, --fix recovers it
  MERGED         the labeled text was absorbed into a coarser chunk, --fix recovers it
  SPLIT          the labeled text now spans several chunks, a human must re-judge
  ORPHANED       the labeled text or its document is gone

--fix never touches SPLIT or ORPHANED labels. Guessing at them would fabricate ground truth,
which is the failure this command exists to expose.

Exit codes
  0  every label still points at the text it was written for
  1  at least one label has decayed
  2  usage error, unreadable file, or malformed input

Docs  https://github.com/aton-of-data/retrieval-eval/blob/main/spec/drift.md
""".rstrip("\n"),
    "score": """\
retrieval-eval score
Compute deterministic retrieval metrics and gate a build on them.

Usage
  retrieval-eval score --judgments <file> --run <file> [options]

Options
      --judgments <file>  relevance labels, JSONL
      --run <file>        ranked results per query, JSONL
      --corpus <file>     also report judgment drift alongside the metrics
  -k, --k <n>             rank cutoff for the @k metrics (default 10)
      --threshold <n>     lowest relevance counted as relevant (default 1)
      --gate <expr>       add a gate, repeatable; see below
      --baseline <file>   a previous report, required by delta gates
      --out <file>        write the JSON report to this file
      --json              print the JSON report on stdout
      --color <when>      auto, always or never
  -h, --help              show this help

Metrics
  precision@k  recall@k  ndcg@k  mrr  map  hit_rate@k

Gate expressions, repeatable
  recall@5:0.8                 absolute floor
  recall@5:-0.02               regression tolerance against --baseline
  worst-stratum:recall@5:0.7   floor on the weakest query class, so averages cannot hide it
  faithfulness:ci-lower:0.8    floor on the lower confidence bound

Exit codes
  0  every gate passed
  1  a gate failed or could not be decided
  2  usage error, unreadable file, or malformed input

Docs  https://github.com/aton-of-data/retrieval-eval
""".rstrip("\n"),
    "validate": """\
retrieval-eval validate
Check a judgment set for problems before you trust its numbers.

Usage
  retrieval-eval validate --judgments <file> [options]

Options
      --judgments <file>  the labels to check, JSONL
      --json              emit every issue as JSON
      --color <when>      auto, always or never
  -h, --help              show this help

This reports more than schema conformance. A judgment set can parse cleanly and still be
unsound: every label synthetic, labels spanning several corpus fingerprints, a stratum too thin
to gate on, or no positive label at all, which leaves recall undefined.

Exit codes
  0  no errors, warnings may still be printed
  1  at least one error
  2  usage error, unreadable file, or malformed input

Docs  https://github.com/aton-of-data/retrieval-eval/blob/main/spec/README.md
""".rstrip("\n"),
    "convert": """\
retrieval-eval convert
Move labels and runs between this format and TREC qrels.

Usage
  retrieval-eval convert --judgments <file> --to qrels
  retrieval-eval convert --run <file> --to trec-run
  retrieval-eval convert --qrels <file> --to judgments [--as-chunk-ids]

Options
      --to <format>       qrels, trec-run or judgments
      --judgments <file>  source labels, for --to qrels
      --run <file>        source run, for --to trec-run
      --qrels <file>      source qrels, for --to judgments
      --as-chunk-ids      treat the qrels doc_id as a chunk_id rather than a doc_uri
      --color <when>      auto, always or never
  -h, --help              show this help

A judgments file is a strict superset of qrels, so one conversion reaches trec_eval,
ir_measures, pytrec_eval, BEIR and ir_datasets. Converted output goes to stdout.

Exit codes
  0  converted
  2  usage error, unreadable file, or malformed input

Docs  https://github.com/aton-of-data/retrieval-eval
""".rstrip("\n"),
}
