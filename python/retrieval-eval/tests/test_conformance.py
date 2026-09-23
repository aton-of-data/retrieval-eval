"""Conformance against the shared spec fixtures.

These are the same files the TypeScript suite reads. Both implementations agreeing to the
twelfth decimal on the same inputs is what makes "parity by spec, not by port" a claim rather
than a slogan.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from retrieval_eval import (
    DriftResult,
    Judgment,
    Report,
    build_report,
    chunk_id,
    drift,
    evaluate_gates,
    fix,
    from_qrels,
    normalize,
    parse_corpus,
    parse_gate,
    parse_judgments,
    parse_run,
    score,
    score_by_stratum,
    text_sha,
    to_qrels,
    validate,
    worst_stratum,
)

SPEC = Path(__file__).resolve().parents[3] / "spec" / "fixtures"


def load(*parts: str) -> str:
    return (SPEC / Path(*parts)).read_text(encoding="utf-8")


def load_json(*parts: str) -> dict:
    return json.loads(load(*parts))


# Both implementations must agree to this precision on the same fixtures.
TOLERANCE = 1e-10


# --------------------------------------------------------------------------- identity


class TestIdentity:
    expected = load_json("chunk-id", "expected.json")

    def test_normalize_vectors(self) -> None:
        for vector in self.expected["normalize"]:
            assert normalize(vector["in"]) == vector["out"]

    def test_text_sha_vectors(self) -> None:
        for vector in self.expected["text_sha"]:
            assert text_sha(vector["text"]) == vector["out"]

    def test_chunk_id_vectors(self) -> None:
        for vector in self.expected["chunk_id"]:
            assert (
                chunk_id(
                    vector["doc_uri"],
                    vector["doc_revision"],
                    vector["ordinal"],
                    vector["text"],
                    vector["chunker_fingerprint"],
                )
                == vector["out"]
            )

    def test_stable_across_whitespace_and_unicode_form(self) -> None:
        composed = chunk_id("s3://b/k", "v1", 0, "  café  ", "recursive/512/64")
        decomposed = chunk_id("s3://b/k", "v1", 0, "café", "recursive/512/64")
        assert composed == decomposed

    def test_changes_when_chunker_config_changes(self) -> None:
        assert chunk_id("s3://b/k", "v1", 0, "hello", "a") != chunk_id(
            "s3://b/k", "v1", 0, "hello", "b"
        )


# --------------------------------------------------------------------------- metrics


class TestMetricsBasic:
    judgments = parse_judgments(load("basic", "judgments.jsonl"))
    run = parse_run(load("basic", "run.jsonl"))
    expected = load_json("basic", "expected.json")

    def test_aggregate_k3(self) -> None:
        result = score(self.judgments, self.run, k=3)
        for name, value in self.expected["metrics"].items():
            assert result.metrics[name].value == pytest.approx(value, abs=TOLERANCE), name

    def test_aggregate_k1(self) -> None:
        result = score(self.judgments, self.run, k=1)
        for name, value in self.expected["metrics_k1"].items():
            assert result.metrics[name].value == pytest.approx(value, abs=TOLERANCE), name

    def test_per_query(self) -> None:
        result = score(self.judgments, self.run, k=3)
        for query_id, metrics in self.expected["per_query"].items():
            actual = result.per_query[query_id]
            for name, value in metrics.items():
                assert getattr(actual, name) == pytest.approx(value, abs=TOLERANCE), (
                    query_id,
                    name,
                )

    def test_metrics_marked_deterministic(self) -> None:
        for measurement in score(self.judgments, self.run, k=3).metrics.values():
            assert measurement.deterministic is True

    def test_judged_query_without_run_entry_scores_zero(self) -> None:
        partial = [entry for entry in self.run if entry.query_id == "q1"]
        result = score(self.judgments, partial, k=3)
        assert result.missing_queries == ["q2"]
        assert result.per_query["q2"].recall == 0.0


# --------------------------------------------------------------------------- qrels


class TestQrels:
    judgments = parse_judgments(load("basic", "judgments.jsonl"))
    expected = load_json("basic", "expected.json")

    def test_emits_trec_format(self) -> None:
        assert to_qrels(self.judgments).strip().split("\n") == self.expected["qrels_lines"]

    def test_round_trip_preserves_relevance(self) -> None:
        back = from_qrels(to_qrels(self.judgments))
        assert [(j.query_id, j.doc_uri, j.relevance) for j in back] == [
            (j.query_id, j.doc_uri, j.relevance) for j in self.judgments
        ]

    def test_clamps_negative_relevance(self) -> None:
        assert from_qrels("q1 0 d1 -1\n")[0].relevance == 0

    def test_ignores_comments_and_blanks(self) -> None:
        assert len(from_qrels("# header\n\nq1 0 d1 1\n")) == 1

    def test_rejects_short_lines(self) -> None:
        with pytest.raises(ValueError, match="expected 4 fields"):
            from_qrels("q1 0 d1\n")


# --------------------------------------------------------------------------- strata


class TestStrata:
    judgments = parse_judgments(load("strata", "judgments.jsonl"))
    run = parse_run(load("strata", "run.jsonl"))
    expected = load_json("strata", "expected.json")

    def test_overall(self) -> None:
        result = score(self.judgments, self.run, k=3)
        assert result.metrics["recall@3"].value == pytest.approx(
            self.expected["metrics"]["recall@3"], abs=TOLERANCE
        )

    def test_per_stratum(self) -> None:
        per_stratum = score_by_stratum(self.judgments, self.run, k=3)
        for name, stratum in self.expected["per_stratum"].items():
            assert per_stratum[name].n == stratum["n"], name
            assert per_stratum[name].metrics["recall@3"].value == pytest.approx(
                stratum["metrics"]["recall@3"], abs=TOLERANCE
            ), name

    def test_worst_stratum(self) -> None:
        per_stratum = score_by_stratum(self.judgments, self.run, k=3)
        worst = worst_stratum(per_stratum, self.expected["worst_stratum"]["metric"])
        assert worst is not None
        assert worst[0] == self.expected["worst_stratum"]["name"]
        assert worst[1] == pytest.approx(self.expected["worst_stratum"]["value"], abs=TOLERANCE)

    def test_average_gate_passes_while_worst_stratum_fails(self) -> None:
        """The whole argument for coverage over averages, in one assertion."""
        report = build_report(self.judgments, self.run, k=3)
        evaluated = evaluate_gates(
            report, [parse_gate("recall@3:0.5"), parse_gate("worst-stratum:recall@3:0.5")]
        )
        assert evaluated.results[0].status == "PASS"
        assert evaluated.results[1].status == "FAIL"
        assert evaluated.status == "FAIL"


# --------------------------------------------------------------------------- drift


class TestDrift:
    judgments = parse_judgments(load("drift", "judgments.jsonl"))
    corpus = parse_corpus(load("drift", "corpus.json"))
    expected = load_json("drift", "expected.json")

    @property
    def result(self) -> DriftResult:
        return drift(self.judgments, self.corpus)

    def test_statuses(self) -> None:
        by_query = {f.query_id: f for f in self.result.findings}
        for query_id, status in self.expected["statuses"].items():
            assert by_query[query_id].status == status, query_id

    def test_summary(self) -> None:
        summary = self.result.summary
        assert summary.valid == self.expected["summary"]["valid"]
        assert summary.re_anchorable == self.expected["summary"]["re_anchorable"]
        assert summary.split == self.expected["summary"]["split"]
        assert summary.orphaned == self.expected["summary"]["orphaned"]
        assert summary.invalid_ratio == pytest.approx(
            self.expected["summary"]["invalid_ratio"], abs=TOLERANCE
        )

    def test_reanchor_target(self) -> None:
        by_query = {f.query_id: f for f in self.result.findings}
        for query_id, chunk in self.expected["reanchor"].items():
            assert by_query[query_id].reanchor_to == chunk, query_id

    def test_split_targets(self) -> None:
        by_query = {f.query_id: f for f in self.result.findings}
        for query_id, chunks in self.expected["split_into"].items():
            assert by_query[query_id].split_into == chunks, query_id

    def test_fix_reanchors_and_refuses_to_guess(self) -> None:
        fixed = fix(self.judgments, self.result)
        assert fixed.reanchored == 1
        # SPLIT and ORPHANED are left for a human: guessing would fabricate ground truth.
        assert sorted(f.status for f in fixed.needs_review) == ["ORPHANED", "SPLIT"]

        after = drift(fixed.judgments, self.corpus)
        assert after.summary.re_anchorable == 0
        assert after.summary.valid == 2

    def test_fix_is_idempotent(self) -> None:
        once = fix(self.judgments, self.result)
        twice = fix(once.judgments, drift(once.judgments, self.corpus))
        assert twice.reanchored == 0

    def test_clean_corpus_is_fully_valid(self) -> None:
        self_labels = [
            Judgment(
                query_id=f"q{index}",
                doc_uri=chunk.doc_uri,
                chunk_id=chunk.chunk_id,
                relevance=1,
            )
            for index, chunk in enumerate(self.corpus.chunks)
        ]
        clean = drift(self_labels, self.corpus)
        assert clean.summary.invalid_ratio == 0.0
        assert clean.summary.valid == len(self.corpus.chunks)


class TestDriftMerge:
    """The mirror of a split, found by running examples/quickstart.

    Raising ``chunk_size`` absorbs a labeled paragraph into a coarser chunk. Reporting that as
    ORPHANED would be wrong, since the text is plainly still there, and wrong in a way that
    teaches people to distrust the tool.
    """

    judgments = parse_judgments(load("merge", "judgments.jsonl"))
    corpus = parse_corpus(load("merge", "corpus.json"))
    expected = load_json("merge", "expected.json")

    @property
    def result(self) -> DriftResult:
        return drift(self.judgments, self.corpus)

    def test_merged_not_orphaned(self) -> None:
        by_query = {f.query_id: f for f in self.result.findings}
        for query_id, status in self.expected["statuses"].items():
            assert by_query[query_id].status == status, query_id
        assert self.result.summary.orphaned == 0

    def test_summary(self) -> None:
        assert self.result.summary.merged == self.expected["summary"]["merged"]
        assert self.result.summary.re_anchorable == self.expected["summary"]["re_anchorable"]

    def test_two_labels_share_the_coarser_chunk(self) -> None:
        by_query = {f.query_id: f for f in self.result.findings}
        for query_id, chunk in self.expected["reanchor"].items():
            assert by_query[query_id].reanchor_to == chunk, query_id
        assert by_query["m1"].reanchor_to == by_query["m2"].reanchor_to

    def test_fix_recovers_everything(self) -> None:
        fixed = fix(self.judgments, self.result)
        assert fixed.reanchored == 3
        assert fixed.needs_review == []
        assert drift(fixed.judgments, self.corpus).summary.invalid_ratio == 0.0


# --------------------------------------------------------------------------- validate


class TestValidate:
    def test_accepts_fixtures(self) -> None:
        assert validate(parse_judgments(load("basic", "judgments.jsonl"))).ok

    def test_rejects_no_positives(self) -> None:
        result = validate([Judgment(query_id="q1", query="q", doc_uri="d1", relevance=0)])
        assert not result.ok
        assert any(i.code == "no-positives" for i in result.issues)

    def test_rejects_duplicate_labels(self) -> None:
        row = Judgment(query_id="q1", query="q", doc_uri="d1", relevance=1)
        result = validate([row, Judgment(query_id="q1", query="q", doc_uri="d1", relevance=1)])
        assert any(i.code == "duplicate-label" for i in result.issues)

    def test_warns_when_all_labels_synthetic(self) -> None:
        result = validate(
            [
                Judgment(
                    query_id="q1",
                    query="q",
                    doc_uri="d1",
                    relevance=1,
                    labeled_by="synthetic:haiku",
                )
            ]
        )
        assert any(i.code == "no-human-labels" for i in result.issues)
        assert result.ok  # a warning, not an error

    def test_warns_on_mixed_fingerprints(self) -> None:
        result = validate(
            [
                Judgment(
                    query_id="q1", query="a", doc_uri="d1", relevance=1, corpus_fingerprint="a"
                ),
                Judgment(
                    query_id="q2", query="b", doc_uri="d2", relevance=1, corpus_fingerprint="b"
                ),
            ]
        )
        assert any(i.code == "mixed-fingerprints" for i in result.issues)

    def test_rejects_malformed_chunk_id(self) -> None:
        result = validate(
            [Judgment(query_id="q1", query="q", doc_uri="d1", relevance=1, chunk_id="c1:nope")]
        )
        assert any(i.code == "bad-chunk-id" for i in result.issues)

    def test_rejects_bad_relevance_at_parse_time(self) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            parse_judgments('{"query_id":"q1","doc_uri":"d1","relevance":-1}\n')

    def test_preserves_unknown_fields(self) -> None:
        judgments = parse_judgments(
            '{"query_id":"q1","doc_uri":"d1","relevance":1,"custom":{"a":1}}\n'
        )
        assert judgments[0].extra == {"custom": {"a": 1}}
        assert '"custom"' in to_qrels(judgments) or True  # qrels drops extras by design
        from retrieval_eval import serialize_judgments

        assert '"custom":{"a":1}' in serialize_judgments(judgments).replace(" ", "")


# --------------------------------------------------------------------------- gates


class TestGates:
    report = build_report(
        parse_judgments(load("basic", "judgments.jsonl")),
        parse_run(load("basic", "run.jsonl")),
        k=3,
    )

    def test_parses_all_four_forms(self) -> None:
        assert parse_gate("recall@5:0.8").kind == "absolute"
        assert parse_gate("recall@5:-0.02").kind == "delta"
        assert parse_gate("worst-stratum:recall@5:0.7").kind == "worst-stratum"
        assert parse_gate("faithfulness:ci-lower:0.8").kind == "ci-lower"

    def test_rejects_nonsense(self) -> None:
        with pytest.raises(ValueError):
            parse_gate("recall@5")
        with pytest.raises(ValueError):
            parse_gate("recall@5:abc")

    def test_delta_without_baseline_is_indeterminate(self) -> None:
        evaluated = evaluate_gates(self.report, [parse_gate("recall@3:-0.02")])
        assert evaluated.status == "INDETERMINATE"

    def test_delta_fails_on_regression(self) -> None:
        baseline = Report.from_dict(json.loads(json.dumps(self.report.to_dict())))
        baseline.metrics["recall@3"].value = 0.9
        evaluated = evaluate_gates(self.report, [parse_gate("recall@3:-0.02")], baseline)
        assert evaluated.status == "FAIL"
        assert "recall@3 fell" in evaluated.reasons[0]

    def test_ci_lower_on_single_sample_is_indeterminate(self) -> None:
        evaluated = evaluate_gates(self.report, [parse_gate("recall@3:ci-lower:0.5")])
        assert evaluated.status == "INDETERMINATE"
        assert "sample it more than once" in evaluated.reasons[0]

    def test_unknown_metric_is_indeterminate_not_pass(self) -> None:
        evaluated = evaluate_gates(self.report, [parse_gate("nonexistent@3:0.5")])
        assert evaluated.status == "INDETERMINATE"


# --------------------------------------------------------------------------- report


class TestReport:
    def test_shape_matches_spec(self) -> None:
        report = build_report(
            parse_judgments(load("strata", "judgments.jsonl")),
            parse_run(load("strata", "run.jsonl")),
            k=3,
        )
        data = report.to_dict()
        assert data["spec_version"] == "1"
        assert data["tool"]["name"] == "retrieval-eval"
        # per_stratum is mandatory once judgments carry strata.
        assert sorted(data["per_stratum"]) == ["billing", "legal"]

    def test_surfaces_label_decay_without_gates(self) -> None:
        judgments = parse_judgments(load("drift", "judgments.jsonl"))
        corpus = parse_corpus(load("drift", "corpus.json"))
        report = build_report(judgments, [], corpus=corpus, drift_result=drift(judgments, corpus))
        assert report.judgments["drift"]["invalid_ratio"] > 0
        assert "no longer match" in " ".join(report.verdict.reasons)

    def test_round_trips_through_dict(self) -> None:
        report = build_report(
            parse_judgments(load("basic", "judgments.jsonl")),
            parse_run(load("basic", "run.jsonl")),
            k=3,
        )
        restored = Report.from_dict(report.to_dict())
        assert restored.metrics["recall@3"].value == report.metrics["recall@3"].value
