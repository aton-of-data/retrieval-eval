#!/usr/bin/env python3
"""Assert the two implementations answer identically on the shared fixtures.

This is the load-bearing test of the whole project. "Parity by spec, not by port" is a claim
about behaviour, so it is checked by running both CLIs and comparing, not by trusting that two
test suites which each pass are therefore equivalent.

Three kinds of case, each compared the way that kind should be compared:

- ``json``  numbers semantically, since JSON ``1`` and ``1.0`` denote the same value; keys,
            order and strings exactly.
- ``text``  human-readable stdout, byte for byte. The rendered report is part of the contract.
- ``error`` exit code and the message on stderr, byte for byte.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "spec" / "fixtures"
TS_CLI = ROOT / "packages" / "retrieval-eval" / "dist" / "cli.js"

Compare = Literal["json", "text", "error"]


@dataclass(frozen=True)
class Case:
    """One invocation both implementations must agree on."""

    name: str
    argv: list[str]
    compare: Compare = "json"
    codes: tuple[int, ...] = field(default=())


BASIC = ["--judgments", "basic/judgments.jsonl", "--run", "basic/run.jsonl"]
DUPLICATE = [
    "--judgments", "duplicate-ranking/judgments.jsonl",
    "--run", "duplicate-ranking/run.jsonl",
]

CASES: list[Case] = [
    # Reports, compared as data.
    Case("drift", ["drift", "--judgments", "drift/judgments.jsonl", "--corpus", "drift/corpus.json", "--json"]),
    Case("drift-merge", ["drift", "--judgments", "merge/judgments.jsonl", "--corpus", "merge/corpus.json", "--json"]),
    Case("score-basic", ["score", *BASIC, "-k", "3", "--json"]),
    Case("score-k10", ["score", *BASIC, "--json"]),
    Case(
        "score-strata-gates",
        [
            "score",
            "--judgments", "strata/judgments.jsonl",
            "--run", "strata/run.jsonl",
            "-k", "3",
            "--gate", "recall@3:0.5",
            "--gate", "worst-stratum:recall@3:0.7",
            "--json",
        ],
    ),
    Case(
        "score-with-corpus",
        ["score", "--judgments", "drift/judgments.jsonl", "--run", "basic/run.jsonl", "--corpus", "drift/corpus.json", "--json"],
    ),
    Case("validate", ["validate", "--judgments", "strata/judgments.jsonl", "--json"]),
    # A ranking that repeats a key. Counted naively these metrics leave their range, so both
    # implementations must drop the repeat and both must say that they did.
    Case("score-duplicate-ranking", ["score", *DUPLICATE, "-k", "5", "--json"]),
    Case(
        "score-duplicate-ranking-gated",
        ["score", *DUPLICATE, "-k", "5", "--gate", "recall@5:0.9", "--json"],
        codes=(1,),
    ),
    # A judgment set `validate` rejects. `score` must not report PASS over it, and a gate that
    # passes must not clear the finding it never looked at.
    Case(
        "score-unsound-judgments",
        [
            "score",
            "--judgments", "unsound-judgments/judgments.jsonl",
            "--run", "unsound-judgments/run.jsonl",
            "-k", "2",
            "--gate", "recall@2:0.1",
            "--json",
        ],
        codes=(1,),
    ),
    # Query ids and strata arriving out of order. Insertion order in one implementation and
    # sorted order in the other is a parity break no already-sorted fixture can catch.
    Case(
        "validate-unsorted-queries",
        ["validate", "--judgments", "unsorted-queries/judgments.jsonl", "--json"],
    ),
    Case(
        "score-no-positives",
        ["score", "--judgments", "no-positives/judgments.jsonl", "--run", "no-positives/run.jsonl", "-k", "3", "--json"],
    ),
    Case(
        "score-threshold",
        ["score", *BASIC, "-k", "3", "--threshold", "2", "--json"],
    ),
    Case(
        "render-score-no-positives",
        ["score", "--judgments", "no-positives/judgments.jsonl", "--run", "no-positives/run.jsonl", "-k", "3"],
        "text",
    ),
    # Conversions and rendered output, compared as text.
    Case("convert-qrels", ["convert", "--judgments", "basic/judgments.jsonl", "--to", "qrels"], "text"),
    Case("convert-trec-run", ["convert", "--run", "basic/run.jsonl", "--to", "trec-run"], "text"),
    Case("convert-from-beir-qrels", ["convert", "--qrels", "qrels/beir.tsv", "--to", "judgments"], "text"),
    Case("convert-from-trec-qrels", ["convert", "--qrels", "qrels/trec.qrels", "--to", "judgments", "--as-chunk-ids"], "text"),
    Case("render-drift", ["drift", "--judgments", "drift/judgments.jsonl", "--corpus", "drift/corpus.json"], "text"),
    Case("render-drift-doc-level", ["drift", "--judgments", "basic/judgments.jsonl", "--corpus", "merge/corpus.json"], "text"),
    Case("render-score", ["score", *BASIC, "-k", "3"], "text"),
    Case(
        "render-score-strata",
        ["score", "--judgments", "strata/judgments.jsonl", "--run", "strata/run.jsonl", "-k", "3", "--gate", "recall@3:0.5", "--gate", "worst-stratum:recall@3:0.7"],
        "text",
    ),
    Case("render-validate", ["validate", "--judgments", "strata/judgments.jsonl"], "text"),
    Case("render-score-duplicate-ranking", ["score", *DUPLICATE, "-k", "5"], "text"),
    Case(
        "render-score-unsound-judgments",
        [
            "score",
            "--judgments", "unsound-judgments/judgments.jsonl",
            "--run", "unsound-judgments/run.jsonl",
            "-k", "2",
        ],
        "text",
        codes=(1,),
    ),
    Case(
        "render-validate-unsorted-queries",
        ["validate", "--judgments", "unsorted-queries/judgments.jsonl"],
        "text",
    ),
    # The stratum table. `localeCompare` ordered these by locale, which disagreed with Python
    # and with another machine running the same build.
    Case(
        "render-score-stratum-order",
        [
            "score",
            "--judgments", "stratum-order/judgments.jsonl",
            "--run", "stratum-order/run.jsonl",
            "-k", "3",
            "--threshold", "2",
        ],
        "text",
    ),
    Case(
        "score-stratum-order",
        [
            "score",
            "--judgments", "stratum-order/judgments.jsonl",
            "--run", "stratum-order/run.jsonl",
            "-k", "3",
            "--threshold", "2",
            "--json",
        ],
    ),
    Case(
        "render-score-threshold",
        ["score", "--judgments", "strata/judgments.jsonl", "--run", "strata/run.jsonl", "-k", "3", "--threshold", "2"],
        "text",
    ),
    Case(
        "score-nothing-scored",
        [
            "score",
            "--judgments", "nothing-scored/judgments.jsonl",
            "--run", "nothing-scored/run.jsonl",
            "-k", "3",
            "--threshold", "2",
            "--json",
        ],
        codes=(1,),
    ),
    Case(
        "render-score-nothing-scored",
        [
            "score",
            "--judgments", "nothing-scored/judgments.jsonl",
            "--run", "nothing-scored/run.jsonl",
            "-k", "3",
            "--threshold", "2",
            "--gate", "recall@3:0.5",
        ],
        "text",
        codes=(1,),
    ),
    # Help is part of the interface. Two CLIs that document themselves differently are two CLIs.
    Case("help-root", ["--help"], "text"),
    Case("help-bare", [], "text", codes=(2,)),
    Case("help-drift", ["drift", "--help"], "text"),
    Case("help-score", ["score", "--help"], "text"),
    Case("help-validate", ["validate", "--help"], "text"),
    Case("help-convert", ["convert", "--help"], "text"),
    Case("help-verb", ["help", "score"], "text"),
    Case("version", ["--version"], "text"),
    # Failures, where wording and exit code both matter.
    Case("missing-file", ["drift", "--judgments", "nope.jsonl", "--corpus", "nope.json"], "error", codes=(2,)),
    Case("bad-gate", ["score", *BASIC, "--gate", "recall@3"], "error", codes=(2,)),
    # `parseFloat` read '0.5abc' as 0.5 while `float` rejected it; `float` read 'nan' and
    # 'infinity' while `parseFloat` rejected them. A threshold the two cannot agree on is
    # worse than no threshold, so all three are refused by both.
    Case("bad-gate-trailing", ["score", *BASIC, "--gate", "recall@3:0.5abc"], "error", codes=(2,)),
    Case("bad-gate-nan", ["score", *BASIC, "--gate", "recall@3:nan"], "error", codes=(2,)),
    Case("bad-gate-infinity", ["score", *BASIC, "--gate", "recall@3:infinity"], "error", codes=(2,)),
    # A run file that no longer says what it means.
    Case(
        "bad-run-duplicate-query",
        [
            "score",
            "--judgments", "duplicate-ranking/judgments.jsonl",
            "--run", "duplicate-ranking/run-duplicate-query.jsonl",
        ],
        "error",
        codes=(2,),
    ),
    Case(
        "bad-run-non-string-key",
        [
            "score",
            "--judgments", "duplicate-ranking/judgments.jsonl",
            "--run", "duplicate-ranking/run-non-string-key.jsonl",
        ],
        "error",
        codes=(2,),
    ),
    Case("unknown-command", ["frobnicate"], "error", codes=(2,)),
    Case("near-miss-command", ["drif"], "error", codes=(2,)),
    Case("unknown-option", ["drift", "--nope"], "error", codes=(2,)),
    Case("missing-required", ["score", "--judgments", "basic/judgments.jsonl"], "error", codes=(2,)),
    Case("bad-k", ["score", *BASIC, "-k", "0"], "error", codes=(2,)),
    Case("bad-color", ["validate", "--judgments", "basic/judgments.jsonl", "--color", "mauve"], "error", codes=(2,)),
    Case("bad-convert-target", ["convert", "--judgments", "basic/judgments.jsonl", "--to", "csv"], "error", codes=(2,)),
]


def resolve(argv: list[str]) -> list[str]:
    """Turn fixture-relative paths into absolute ones."""
    return [
        str(FIXTURES / arg)
        if "/" in arg and arg.endswith((".jsonl", ".json", ".tsv", ".qrels"))
        else arg
        for arg in argv
    ]


def run(cmd: list[str], argv: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(  # noqa: S603
        [*cmd, *resolve(argv)],
        capture_output=True,
        text=True,
        env={**os.environ, "NO_COLOR": "1"},
        cwd=ROOT,
    )
    return result.returncode, result.stdout, result.stderr


def normalize(value: Any) -> Any:
    """Drop the timestamp and collapse integral floats, so 1 and 1.0 compare equal."""
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items() if k != "generated_at"}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def compare(case: Case, ts: tuple[int, str, str], py: tuple[int, str, str]) -> list[str]:
    """Every way this case's two answers disagree."""
    problems: list[str] = []
    ts_code, ts_out, ts_err = ts
    py_code, py_out, py_err = py

    if ts_code != py_code:
        problems.append(f"exit codes differ: ts={ts_code} py={py_code}")
    if case.codes and ts_code not in case.codes:
        problems.append(f"expected exit code in {case.codes}, got {ts_code}")

    if case.compare == "json":
        try:
            if normalize(json.loads(ts_out)) != normalize(json.loads(py_out)):
                problems.append("JSON payloads differ")
        except json.JSONDecodeError as error:
            problems.append(f"output is not valid JSON: {error}")
    elif case.compare == "text":
        if ts_out != py_out:
            problems.append("stdout differs")
    elif ts_err != py_err:
        problems.append("stderr differs")

    return problems


def excerpt(label: str, text: str) -> str:
    return f"     {label}: {text[:400]!r}"


def main() -> int:
    if not TS_CLI.exists():
        sys.stderr.write(f"error  {TS_CLI} is missing. Run `pnpm build` first.\n")
        return 2

    ts_cmd = ["node", str(TS_CLI)]
    py_cmd = [sys.executable, "-m", "retrieval_eval.cli"]

    # Fail loudly on the one mistake everybody makes: running this with an interpreter that
    # cannot import the package. Without this, every case "fails" with a JSON decode error and
    # the report reads like a parity break rather than a missing install.
    probe = subprocess.run([*py_cmd, "--version"], capture_output=True, text=True, cwd=ROOT)  # noqa: S603
    if probe.returncode != 0:
        detail = probe.stderr.strip().splitlines()[-1] if probe.stderr.strip() else ""
        sys.stderr.write(
            f"error  retrieval_eval is not importable by {sys.executable}\n"
            f"       {detail}\n\n"
            "       pip install -e ./python/retrieval-eval\n"
            "       then run this with that same interpreter.\n"
        )
        return 2

    failures = 0
    for case in CASES:
        ts = run(ts_cmd, case.argv)
        py = run(py_cmd, case.argv)
        problems = compare(case, ts, py)

        if not problems:
            print(f"ok   {case.name}")
            continue

        failures += 1
        print(f"FAIL {case.name}")
        for problem in problems:
            print(f"     {problem}")
        if "stderr differs" in problems:
            print(excerpt("ts", ts[2]))
            print(excerpt("py", py[2]))
        elif any(p.startswith(("JSON", "stdout")) for p in problems):
            print(excerpt("ts", ts[1]))
            print(excerpt("py", py[1]))

    print(f"\n{len(CASES) - failures}/{len(CASES)} cases agree")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
