"""Command line behaviour.

The TypeScript suite carries the same cases. Where both assert on wording, the wording is part
of the contract: `scripts/check_parity.py` diffs the two CLIs byte for byte.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from retrieval_eval.cli import main
from retrieval_eval.report import TOOL_VERSION

SPEC = Path(__file__).resolve().parents[3] / "spec" / "fixtures"


def fixture(*parts: str) -> str:
    return str(SPEC.joinpath(*parts))


@pytest.fixture(autouse=True)
def _plain_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Capture is not a terminal, but make the colour decision explicit rather than incidental."""
    monkeypatch.setenv("NO_COLOR", "1")


def run(*argv: str) -> tuple[int, str, str]:
    """Run the CLI and return everything a shell would observe."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestInvocation:
    def test_version_prints_alone(self) -> None:
        code, out, _ = run("--version")
        assert out == f"{TOOL_VERSION}\n"
        assert code == 0

    def test_help_is_zero_and_a_bare_call_is_two(self) -> None:
        assert run("--help")[0] == 0
        assert run("help")[0] == 0
        code, out, _ = run()
        assert code == 2
        assert "Usage" in out

    def test_every_command_documents_itself(self) -> None:
        for command in ("drift", "score", "validate", "convert"):
            code, out, _ = run(command, "--help")
            assert code == 0
            assert f"retrieval-eval {command}" in out
            assert "Exit codes" in out

    def test_suggests_the_command_a_typo_meant(self) -> None:
        code, _, err = run("drif")
        assert code == 2
        assert "unknown command 'drif'" in err
        assert "try retrieval-eval drift" in err

    def test_names_the_offending_option(self) -> None:
        code, _, err = run("drift", "--nope")
        assert code == 2
        assert err == "error  unknown option '--nope'\n        try retrieval-eval --help\n"

    def test_names_missing_flags_with_the_command_that_documents_them(self) -> None:
        code, _, err = run("score", "--judgments", fixture("basic", "judgments.jsonl"))
        assert code == 2
        assert "score needs --judgments and --run" in err
        assert "try retrieval-eval score --help" in err

    def test_missing_file_is_one_line_never_a_traceback(self) -> None:
        code, _, err = run("drift", "--judgments", "nope.jsonl", "--corpus", "nope.json")
        assert code == 2
        assert err == "error  cannot read nope.jsonl: no such file or directory\n"

    def test_rejects_a_k_that_cannot_be_a_cutoff(self) -> None:
        code, _, err = run(
            "score",
            "--judgments",
            fixture("basic", "judgments.jsonl"),
            "--run",
            fixture("basic", "run.jsonl"),
            "-k",
            "0",
        )
        assert code == 2
        assert "-k expects a positive integer, got '0'" in err


class TestColor:
    args = ("validate", "--judgments", fixture("basic", "judgments.jsonl"))

    def test_no_color_is_honoured(self) -> None:
        assert "\033[" not in run(*self.args)[1]

    def test_color_always_overrides(self) -> None:
        assert "\033[" in run(*self.args, "--color", "always")[1]

    def test_rejects_a_mode_it_does_not_have(self) -> None:
        code, _, err = run(*self.args, "--color", "mauve")
        assert code == 2
        assert "--color expects auto, always or never" in err


class TestDrift:
    args = (
        "drift",
        "--judgments",
        fixture("drift", "judgments.jsonl"),
        "--corpus",
        fixture("drift", "corpus.json"),
    )

    def test_exits_one_on_decay(self) -> None:
        code, out, _ = run(*self.args)
        assert code == 1
        assert "RE-ANCHORABLE" in out
        assert "1 recoverable automatically · 2 need a human" in out

    def test_points_at_fix_only_when_there_is_something_to_fix(self, tmp_path: Path) -> None:
        assert "retrieval-eval drift --fix" in run(*self.args)[1]

        judgments = tmp_path / "clean.jsonl"
        judgments.write_text(
            json.dumps(
                {
                    "query_id": "c1",
                    "doc_uri": "wiki://refunds",
                    "chunk_id": "c1:d577264d22f91060a5abc8d3df2b1cea",
                    "relevance": 2,
                    "labeled_by": "human:ana",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        code, out, _ = run(
            "drift", "--judgments", str(judgments), "--corpus", fixture("merge", "corpus.json")
        )
        assert code == 0
        assert "Every label still points at the text it was written for." in out
        assert "--fix" not in out

    def test_rewrites_recoverable_labels_in_place(self, tmp_path: Path) -> None:
        source = SPEC / "drift" / "judgments.jsonl"
        path = tmp_path / "judgments.jsonl"
        path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

        args = ("drift", "--judgments", str(path), "--corpus", fixture("drift", "corpus.json"))
        _, out, _ = run(*args, "--fix")
        assert "re-anchored 1 label(s)" in out
        assert "2 label(s) still need a human" in out

        after = path.read_text(encoding="utf-8")
        assert after != source.read_text(encoding="utf-8")

        # A second pass must change nothing: fixing is not a ratchet that drifts on its own.
        _, again, _ = run(*args, "--fix")
        assert "re-anchored 0 label(s)" in again
        assert path.read_text(encoding="utf-8") == after

    def test_json_carries_every_finding(self) -> None:
        _, out, _ = run(*self.args, "--json")
        assert len(json.loads(out)["findings"]) == 4


class TestScore:
    args = (
        "score",
        "--judgments",
        fixture("strata", "judgments.jsonl"),
        "--run",
        fixture("strata", "run.jsonl"),
        "-k",
        "3",
    )

    def test_average_gate_passes_while_the_worst_stratum_fails(self) -> None:
        code, out, _ = run(
            *self.args, "--gate", "recall@3:0.5", "--gate", "worst-stratum:recall@3:0.7"
        )
        assert code == 1
        assert "ok recall@3:0.5" in out
        assert "x  worst-stratum:recall@3:0.7" in out
        assert "FAIL" in out

    def test_marks_the_weakest_query_class(self) -> None:
        code, out, _ = run(*self.args)
        assert code == 0
        assert "legal" in out
        assert "worst" in out

    def test_writes_the_report_while_printing_for_a_human(self, tmp_path: Path) -> None:
        out_path = tmp_path / "report.json"
        _, out, _ = run(*self.args, "--out", str(out_path))
        assert "recall@3" in out
        assert json.loads(out_path.read_text(encoding="utf-8"))["spec_version"] == "1"


class TestValidateAndConvert:
    def test_warnings_exit_zero_and_errors_exit_one(self, tmp_path: Path) -> None:
        code, out, _ = run("validate", "--judgments", fixture("strata", "judgments.jsonl"))
        assert code == 0
        assert "warning" in out

        broken = tmp_path / "no-positives.jsonl"
        broken.write_text('{"query_id":"q1","doc_uri":"d1","relevance":0}\n', encoding="utf-8")
        code, out, _ = run("validate", "--judgments", str(broken))
        assert code == 1
        assert "[no-positives]" in out

    def test_qrels_goes_to_stdout_and_nothing_else(self) -> None:
        code, out, err = run(
            "convert", "--judgments", fixture("basic", "judgments.jsonl"), "--to", "qrels"
        )
        assert code == 0
        assert err == ""
        assert all(len(line.split(" ")) == 4 for line in out.strip().split("\n"))

    def test_refuses_a_format_it_cannot_produce(self) -> None:
        code, _, err = run(
            "convert", "--judgments", fixture("basic", "judgments.jsonl"), "--to", "csv"
        )
        assert code == 2
        assert "unknown --to 'csv'" in err
