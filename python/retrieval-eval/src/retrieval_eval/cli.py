"""Command line interface.

The same verbs, flags, output and exit codes as the TypeScript CLI, so a polyglot team writes
one CI step and a tutorial works in either language. `scripts/check_parity.py` runs both over
the shared fixtures and diffs the result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from .drift import drift, fix
from .gate import evaluate_gates, parse_gate, worse_status
from .help_text import COMMAND_HELP, COMMANDS, ROOT_HELP
from .judgments import parse_corpus, parse_judgments, parse_run, serialize_judgments, validate
from .metrics import StratumScore
from .models import DriftResult
from .qrels import from_qrels, to_qrels, to_trec_run
from .report import TOOL_VERSION, Report, build_report
from .ui import bar, heading, num, paint, pct, set_color

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


class CliError(Exception):
    """An input or invocation the user can fix. Never a traceback: see `main`."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        """Record the message and, where there is one, the command that fixes it."""
        super().__init__(message)
        self.hint = hint


class _Parser(argparse.ArgumentParser):
    """An argparse parser whose failures travel the same path as every other CLI error."""

    def error(self, message: str) -> NoReturn:
        missing = message.split(": expected one argument")
        if len(missing) == 2 and missing[0].startswith("argument "):
            flag = missing[0].removeprefix("argument ").split("/")[-1]
            raise CliError(f"{flag} expects a value")
        raise CliError(message)


def _build_parser() -> _Parser:
    parser = _Parser(prog="retrieval-eval", add_help=False)
    parser.add_argument("positionals", nargs="*")
    for flag in ("judgments", "run", "corpus", "qrels", "baseline", "out", "to", "color"):
        parser.add_argument(f"--{flag}")
    parser.add_argument("-k", "--k", dest="k")
    parser.add_argument("--threshold")
    parser.add_argument("--gate", action="append", default=[])
    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--as-chunk-ids", dest="as_chunk_ids", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-h", "--help", dest="help", action="store_true")
    parser.add_argument("-v", "--version", dest="version", action="store_true")
    return parser


def _report(error: Exception) -> int:
    """Turn any failure into one readable line plus, where there is one, the way out of it."""
    sys.stderr.write(f"{paint('red', 'error')}  {error}\n")
    hint = getattr(error, "hint", None)
    if hint is not None:
        sys.stderr.write(f"{paint('dim', '        try')} {hint}\n")
    return EXIT_USAGE


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as error:
        reason = (error.strerror or str(error)).lower()
        raise CliError(f"cannot read {path}: {reason}") from error


def _required(args: argparse.Namespace, command: str, flags: list[str]) -> None:
    if any(getattr(args, flag.replace("-", "_")) is None for flag in flags):
        joined = " and ".join(f"--{flag}" for flag in flags)
        raise CliError(f"{command} needs {joined}", f"retrieval-eval {command} --help")


def _integer(raw: str | None, flag: str, fallback: int) -> int:
    if raw is None:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        raise CliError(f"{flag} expects a positive integer, got '{raw}'") from None
    if value < 1:
        raise CliError(f"{flag} expects a positive integer, got '{raw}'")
    return value


def _resolve_color(value: str | None) -> str:
    if value is None:
        return "auto"
    if value in ("auto", "always", "never"):
        return value
    raise CliError(f"--color expects auto, always or never, got '{value}'")


def _closest(typo: str) -> str | None:
    """The command a typo most likely meant, by edit distance, or None if none is close."""
    best, best_distance = None, len(typo) + 1
    for candidate in COMMANDS:
        distance = _edit_distance(typo, candidate)
        if distance < best_distance:
            best, best_distance = candidate, distance
    return best if best_distance <= 3 else None


def _edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, start=1):
        current = [i]
        for j, right in enumerate(b, start=1):
            cost = 0 if left == right else 1
            current.append(min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost))
        previous = current
    return previous[len(b)]


def _print_drift(result: DriftResult, total: int, *, fixing: bool) -> None:
    summary = result.summary
    out = ["\n"]
    out.append(
        f"  {total} judgments · labeled @ fingerprint "
        f"{paint('cyan', result.judgments_fingerprint or 'unknown')}\n"
    )
    out.append(
        f"  live corpus    @ fingerprint "
        f"{paint('cyan', result.corpus_fingerprint or 'unknown')}\n\n"
    )

    # Marks are padded before colouring: escape codes have width in the string, not on screen.
    rows = [
        ("ok", "green", summary.valid, "VALID", "chunk_id still present"),
        ("!", "yellow", summary.re_anchorable, "RE-ANCHORABLE", "text moved to a new chunk_id"),
        ("!", "yellow", summary.merged, "MERGED", "text absorbed into a coarser chunk"),
        ("!", "yellow", summary.split, "SPLIT", "labeled text now spans 2+ chunks"),
        ("x", "red", summary.orphaned, "ORPHANED", "source text or document is gone"),
    ]
    for mark, color, count, label, note in rows:
        out.append(
            f"  {paint(color, mark.ljust(2))} {str(count).rjust(3)}  "
            f"{label.ljust(14)} {paint('dim', note)}\n"
        )

    if summary.invalid_ratio > 0:
        recoverable = summary.re_anchorable + summary.merged
        needs_human = summary.split + summary.orphaned
        headline = (
            f"{pct(summary.invalid_ratio)} of your judgment set no longer matches the live corpus."
        )
        detail = "Any metric computed against it is measuring two changes at once."
        out.append(f"\n  {paint('bold', headline)}\n")
        out.append(f"  {paint('dim', detail)}\n")
        # Split the number so it is actionable rather than merely alarming.
        breakdown = f"{recoverable} recoverable automatically · {needs_human} need a human"
        out.append(f"  {paint('dim', breakdown)}\n")
        if recoverable > 0 and not fixing:
            nxt = "retrieval-eval drift --fix, to re-anchor the recoverable labels"
            out.append(f"\n  {paint('dim', 'next')}    {nxt}\n")
    else:
        clean = "Every label still points at the text it was written for."
        out.append(f"\n  {paint('green', clean)}\n")

    sys.stdout.write("".join(out))


def _cmd_drift(args: argparse.Namespace) -> int:
    _required(args, "drift", ["judgments", "corpus"])
    judgments = parse_judgments(_read(args.judgments))
    corpus = parse_corpus(_read(args.corpus))
    result = drift(judgments, corpus)

    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        _print_drift(result, len(judgments), fixing=args.fix)

    if args.fix:
        fixed = fix(judgments, result)
        Path(args.judgments).write_text(serialize_judgments(fixed.judgments), encoding="utf-8")
        sys.stdout.write(
            f"\n  {paint('green', 'fixed')}   re-anchored {fixed.reanchored} label(s) "
            f"in {args.judgments}\n"
            f"  {paint('yellow', 'review')}  {len(fixed.needs_review)} label(s) "
            "still need a human\n"
        )

    # Non-zero when labels have decayed, so `drift` stands alone as a CI check.
    return EXIT_FAILED if result.summary.invalid_ratio > 0 else EXIT_OK


def _print_score(report: Report) -> None:
    out = [f"\n  {report.judgments['queries']} queries · {report.judgments['labels']} labels"]
    if report.judgments.get("human_labels") is not None:
        out.append(
            paint(
                "dim",
                f" ({report.judgments['human_labels']} human, "
                f"{report.judgments.get('synthetic_labels', 0)} synthetic)",
            )
        )
    out.append("\n\n")

    if not report.metrics:
        out.append(f"  {paint('dim', 'no metric was computed')}\n")

    for name, measurement in report.metrics.items():
        ci = ""
        if measurement.ci is not None:
            ci = paint("dim", f"  [{num(measurement.ci[0])}, {num(measurement.ci[1])}]")
        out.append(f"  {name.ljust(16)} {num(measurement.value)}{ci}\n")

    if report.per_stratum:
        names = list(report.metrics)
        primary = next(
            (name for name in names if name.startswith("recall@")), names[0] if names else ""
        )

        def stratum_value(stratum: StratumScore) -> float:
            measurement = stratum.metrics.get(primary)
            return measurement.value if measurement is not None else 0.0

        entries = [
            (name, stratum.n, stratum_value(stratum))
            for name, stratum in report.per_stratum.items()
        ]
        # A stratum with no scored query has no number to compare, so it is listed after the
        # ones that do and never marked worst.
        ranked = sorted((row for row in entries if row[1] > 0), key=lambda row: (row[2], row[0]))
        unscored = sorted(row for row in entries if row[1] == 0)

        out.append(heading(f"{primary} by stratum" if primary else "strata"))
        for index, (name, n, value) in enumerate(ranked):
            flag = paint("yellow", "  worst") if index == 0 and len(ranked) > 1 else ""
            out.append(
                f"  {paint('dim', '·')} {name.ljust(20)} {num(value)}  "
                f"{paint('dim', bar(value))}  {paint('dim', f'n={n}')}{flag}\n"
            )
        for name, _n, _value in unscored:
            note = "not scored, no label at the relevance threshold"
            out.append(f"  {paint('dim', '·')} {name.ljust(20)} {paint('dim', note)}\n")

    drift_info = report.judgments.get("drift")
    if drift_info and drift_info.get("invalid_ratio", 0) > 0:
        out.append(
            f"\n  {paint('yellow', 'warning')} "
            f"{pct(drift_info['invalid_ratio'])} of judgments no longer match the corpus\n"
        )

    if report.verdict.gates:
        out.append(heading("gates"))
        for gate in report.verdict.gates:
            mark = {
                "PASS": paint("green", "ok"),
                "FAIL": paint("red", "x "),
                "INDETERMINATE": paint("yellow", "? "),
            }[gate.status]
            out.append(f"  {mark} {gate.expression}\n")

    for reason in report.verdict.reasons:
        out.append(f"  {paint('dim', f'→ {reason}')}\n")

    color = {"PASS": "green", "FAIL": "red", "INDETERMINATE": "yellow"}[report.verdict.status]
    out.append(f"\n  {paint(color, paint('bold', report.verdict.status))}\n")
    sys.stdout.write("".join(out))


def _cmd_score(args: argparse.Namespace) -> int:
    _required(args, "score", ["judgments", "run"])
    judgments = parse_judgments(_read(args.judgments))
    run = parse_run(_read(args.run))
    k = _integer(args.k, "-k", 10)
    threshold = _integer(args.threshold, "--threshold", 1)

    corpus = parse_corpus(_read(args.corpus)) if args.corpus else None
    drift_result = drift(judgments, corpus) if corpus else None

    report = build_report(
        judgments,
        run,
        k=k,
        threshold=threshold,
        corpus=corpus,
        drift_result=drift_result,
    )

    if args.gate:
        gates = [parse_gate(expression) for expression in args.gate]
        baseline = Report.from_dict(json.loads(_read(args.baseline))) if args.baseline else None
        evaluated = evaluate_gates(report, gates, baseline)
        # The base verdict already carries findings no gate looked at, such as a judgment set
        # `validate` rejects, so a passing gate does not clear them.
        report.verdict.status = worse_status(report.verdict.status, evaluated.status)
        report.verdict.gates = evaluated.results
        report.verdict.reasons = [*report.verdict.reasons, *evaluated.reasons]

    if args.out:
        Path(args.out).write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")

    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    else:
        _print_score(report)

    return EXIT_OK if report.verdict.status == "PASS" else EXIT_FAILED


def _cmd_validate(args: argparse.Namespace) -> int:
    _required(args, "validate", ["judgments"])
    result = validate(parse_judgments(_read(args.judgments)))

    if args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
        return EXIT_OK if result.ok else EXIT_FAILED

    out = [
        f"\n  {result.labels} labels · {result.queries} queries · {len(result.strata)} strata\n\n"
    ]
    if not result.issues:
        out.append(f"  {paint('green', 'ok')}      no issues\n")
    else:
        for issue in result.issues:
            mark = (
                paint("red", "error  ") if issue.severity == "error" else paint("yellow", "warning")
            )
            out.append(f"  {mark} {paint('dim', f'[{issue.code}]')} {issue.message}\n")
    sys.stdout.write("".join(out))
    return EXIT_OK if result.ok else EXIT_FAILED


def _cmd_convert(args: argparse.Namespace) -> int:
    if args.to is None:
        raise CliError(
            "convert needs --to qrels, trec-run or judgments",
            "retrieval-eval convert --help",
        )

    if args.to == "judgments":
        _required(args, "convert", ["qrels"])
        judgments = from_qrels(_read(args.qrels), as_chunk_ids=args.as_chunk_ids)
        sys.stdout.write(serialize_judgments(judgments))
        return EXIT_OK

    if args.to == "qrels":
        _required(args, "convert", ["judgments"])
        sys.stdout.write(to_qrels(parse_judgments(_read(args.judgments))))
        return EXIT_OK

    if args.to == "trec-run":
        _required(args, "convert", ["run"])
        sys.stdout.write(to_trec_run(parse_run(_read(args.run))))
        return EXIT_OK

    raise CliError(
        f"unknown --to '{args.to}', expected qrels, trec-run or judgments",
        "retrieval-eval convert --help",
    )


_HANDLERS = {
    "drift": _cmd_drift,
    "score": _cmd_score,
    "validate": _cmd_validate,
    "convert": _cmd_convert,
}


def main(argv: list[str] | None = None) -> int:
    """Run one command and return its exit code.

    A parse or validation failure becomes one readable line, not a traceback: a measurement
    tool that answers a malformed file with a stack trace teaches people not to trust its
    other output either.
    """
    try:
        args, extras = _build_parser().parse_known_args(argv)
    except CliError as error:
        set_color("auto")
        return _report(error)

    try:
        set_color(_resolve_color(args.color))
        unknown = next((token for token in extras if token.startswith("-")), None)
        if unknown is not None:
            raise CliError(f"unknown option '{unknown}'", "retrieval-eval --help")

        if args.version:
            sys.stdout.write(f"{TOOL_VERSION}\n")
            return EXIT_OK

        first = args.positionals[0] if args.positionals else None
        command = (
            args.positionals[1]
            if first == "help" and len(args.positionals) > 1
            else (None if first == "help" else first)
        )

        if command is None:
            sys.stdout.write(f"{ROOT_HELP}\n")
            # `help` and `--help` were asked for; a bare invocation was not.
            return EXIT_OK if args.help or first == "help" else EXIT_USAGE
        if command not in COMMANDS:
            near = _closest(command)
            raise CliError(
                f"unknown command '{command}'",
                f"retrieval-eval {near}" if near else "retrieval-eval --help",
            )
        if args.help or first == "help":
            sys.stdout.write(f"{COMMAND_HELP[command]}\n")
            return EXIT_OK

        return _HANDLERS[command](args)
    except (CliError, ValueError, json.JSONDecodeError) as error:
        return _report(error)


if __name__ == "__main__":
    raise SystemExit(main())
