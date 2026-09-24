"""Conformance against the shared spec fixtures.

These are the same files the TypeScript suite reads. Both implementations agreeing to the
twelfth decimal on the same inputs is what makes "parity by spec, not by port" a claim rather
than a slogan.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from retrieval_eval import (
    DriftResult,
    Judgment,
    Report,
    build_report,
    chunk_id,
    dedupe,
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
    serialize_judgments,
    summarize,
    text_sha,
    to_qrels,
    validate,
    worse_status,
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

    def test_rejects_lines_that_are_neither_shape(self) -> None:
        with pytest.raises(ValueError, match="expected 3 or 4 fields"):
            from_qrels("q1 d1\n")
        with pytest.raises(ValueError, match="not an integer"):
            from_qrels("q1 0 d1 high\n")


class TestQueriesWithoutPositives:
    judgments = parse_judgments(load("no-positives", "judgments.jsonl"))
    run = parse_run(load("no-positives", "run.jsonl"))
    expected = load_json("no-positives", "expected.json")

    def test_excluded_from_the_averages(self) -> None:
        result = score(self.judgments, self.run, k=3)
        for name, value in self.expected["metrics"].items():
            assert result.metrics[name].value == pytest.approx(value, abs=TOLERANCE)

    def test_named_so_the_exclusion_is_visible(self) -> None:
        result = score(self.judgments, self.run, k=3)
        assert result.queries_without_positives == self.expected["queries_without_positives"]

    def test_report_counts_the_queries_actually_scored(self) -> None:
        report = build_report(self.judgments, self.run, k=3)
        assert report.judgments["queries"] == 2
        assert report.judgments["queries_scored"] == self.expected["queries_scored"]
        assert "excluded from the averages" in " ".join(report.verdict.reasons)

    def test_follows_the_threshold(self) -> None:
        graded = parse_judgments('{"query_id":"q1","doc_uri":"d1","relevance":1}\n')
        ranking = parse_run('{"query_id":"q1","ranking":["d1"]}\n')
        assert score(graded, ranking, k=3).queries_without_positives == []
        assert score(graded, ranking, k=3, threshold=2).queries_without_positives == ["q1"]


class TestStratumWithNothingToScore:
    judgments = parse_judgments(
        '{"query_id":"q1","doc_uri":"d1","relevance":2,"stratum":"answerable"}\n'
        '{"query_id":"q2","doc_uri":"d2","relevance":1,"stratum":"context-only"}\n'
    )
    run = parse_run('{"query_id":"q1","ranking":["d1"]}\n{"query_id":"q2","ranking":["d2"]}\n')

    def test_reports_n_zero_rather_than_a_zero_score(self) -> None:
        per_stratum = score_by_stratum(self.judgments, self.run, k=3, threshold=2)
        assert per_stratum["context-only"].n == 0
        assert per_stratum["answerable"].n == 1

    def test_is_never_the_worst_stratum(self) -> None:
        per_stratum = score_by_stratum(self.judgments, self.run, k=3, threshold=2)
        worst = worst_stratum(per_stratum, "recall@3")
        assert worst is not None
        assert worst.name == "answerable"

    def test_cannot_fail_a_worst_stratum_gate_on_its_own(self) -> None:
        report = build_report(self.judgments, self.run, k=3, threshold=2)
        evaluated = evaluate_gates(report, [parse_gate("worst-stratum:recall@3:0.9")])
        assert evaluated.status == "PASS"


class TestSummarize:
    """Error bars on a metric whose instrument is not deterministic."""

    fixture = load_json("summarize", "expected.json")

    @pytest.mark.parametrize("name", list(load_json("summarize", "expected.json")["cases"]))
    def test_matches_the_fixture(self, name: str) -> None:
        case = self.fixture["cases"][name]
        measurement = summarize(case["samples"])
        expected = case["expected"]

        assert measurement.value == pytest.approx(expected["value"], abs=TOLERANCE)
        assert measurement.n == expected["n"]
        assert measurement.deterministic is False

        if "stdev" in expected:
            assert measurement.stdev == pytest.approx(expected["stdev"], abs=TOLERANCE)
        else:
            assert measurement.stdev is None

        if "ci" in expected:
            assert measurement.ci is not None
            assert measurement.ci[0] == pytest.approx(expected["ci"][0], abs=TOLERANCE)
            assert measurement.ci[1] == pytest.approx(expected["ci"][1], abs=TOLERANCE)
        else:
            assert measurement.ci is None

    def test_refuses_an_empty_sample_set(self) -> None:
        with pytest.raises(ValueError, match="at least one sample"):
            summarize([])

    def test_makes_a_ci_lower_gate_decidable(self) -> None:
        report = build_report([], [], k=5)
        report.metrics["faithfulness"] = summarize([0.8, 1.0, 0.6, 0.9, 0.7])
        assert evaluate_gates(report, [parse_gate("faithfulness:ci-lower:0.8")]).status == "FAIL"

        report.metrics["faithfulness"] = summarize([0.82])
        evaluated = evaluate_gates(report, [parse_gate("faithfulness:ci-lower:0.8")])
        assert evaluated.status == "INDETERMINATE"

    def test_does_not_raise_a_negative_lower_bound(self) -> None:
        report = build_report([], [], k=5)
        report.metrics["faithfulness"] = summarize([0.0, 0.0, 1.0])
        evaluated = evaluate_gates(report, [parse_gate("faithfulness:ci-lower:0")])
        assert evaluated.status == "FAIL"
        assert report.metrics["faithfulness"].ci is not None
        assert report.metrics["faithfulness"].ci[0] < 0


class TestNothingScored:
    """An empty average is undefined, not zero."""

    expected = load_json("nothing-scored", "expected.json")
    judgments = parse_judgments(load("nothing-scored", "judgments.jsonl"))
    run = parse_run(load("nothing-scored", "run.jsonl"))

    def test_omits_the_metrics_instead_of_emitting_zero(self) -> None:
        result = score(self.judgments, self.run, k=3, threshold=self.expected["threshold"])
        assert result.metrics == {}
        assert result.queries_without_positives == ["q1"]

    def test_does_not_say_an_excluded_query_scored_zero_when_the_run_is_missing(self) -> None:
        report = build_report(
            parse_judgments('{"query_id":"q1","doc_uri":"d1","relevance":0}\n'), []
        )
        assert "scored zero" not in " ".join(report.verdict.reasons)

    def test_is_indeterminate_and_an_absolute_gate_cannot_fail_at_zero(self) -> None:
        report = build_report(self.judgments, self.run, k=3, threshold=self.expected["threshold"])
        assert report.judgments["queries"] == self.expected["queries"]
        assert report.judgments["queries_scored"] == self.expected["queries_scored"]
        assert report.verdict.status == self.expected["status"]
        assert self.expected["reason"] in report.verdict.reasons
        assert report.per_stratum is not None
        assert report.per_stratum["billing"].n == 0
        assert report.per_stratum["billing"].metrics == {}

        evaluated = evaluate_gates(report, [parse_gate("recall@3:0.5")])
        assert evaluated.status == "INDETERMINATE"
        assert self.expected["gate_reason"] in evaluated.reasons

        worst = evaluate_gates(report, [parse_gate("worst-stratum:recall@3:0.5")])
        assert worst.status == "INDETERMINATE"
        assert worst.reasons == ["worst-stratum:recall@3:0.5: no stratum was scored for 'recall@3'"]


class TestCanonicalSerialization:
    line = '{"stratum":"legal","relevance":2,"doc_uri":"d1","query_id":"q1","house":{"a":1}}'
    canonical = '{"query_id":"q1","doc_uri":"d1","relevance":2,"stratum":"legal","house":{"a":1}}'

    def test_schema_order_then_unknown_fields_compactly(self) -> None:
        assert serialize_judgments(parse_judgments(self.line)).strip() == self.canonical

    def test_is_idempotent(self) -> None:
        once = serialize_judgments(parse_judgments(self.line))
        assert serialize_judgments(parse_judgments(once)) == once


class TestQrelsShapes:
    """The two shapes that exist in the wild: TREC's four columns and BEIR's three."""

    expected = load_json("qrels", "expected.json")

    @staticmethod
    def shape(judgments: list) -> list[dict]:
        return [
            {"query_id": j.query_id, "doc_uri": j.doc_uri, "relevance": j.relevance}
            for j in judgments
        ]

    def test_reads_the_beir_form(self) -> None:
        assert self.shape(from_qrels(load("qrels", "beir.tsv"))) == self.expected["beir"]

    def test_reads_the_trec_form(self) -> None:
        assert self.shape(from_qrels(load("qrels", "trec.qrels"))) == self.expected["trec"]

    def test_emits_the_trec_form_from_either(self) -> None:
        converted = to_qrels(from_qrels(load("qrels", "beir.tsv")))
        assert converted.strip().split("\n") == self.expected["qrels_lines"]


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
        # qrels has nowhere to put an unknown field, so conversion drops it by design.
        assert '"custom"' not in to_qrels(judgments)
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


class TestDuplicateRanking:
    """A retriever that returns the same key twice must not be paid twice for it."""

    fixture = load_json("duplicate-ranking", "expected.json")
    judgments = parse_judgments(load("duplicate-ranking", "judgments.jsonl"))
    run = parse_run(load("duplicate-ranking", "run.jsonl"))

    def test_counts_a_repeated_key_once(self):
        result = score(self.judgments, self.run, k=5)
        for name, value in self.fixture["metrics"].items():
            assert result.metrics[name].value == pytest.approx(value, abs=1e-10)
        # The bug this fixture exists for: naively q1 returning d1 five times scores recall 2.5.
        assert result.metrics["recall@5"].value <= 1

    def test_keeps_the_first_occurrence(self):
        by_query = {entry.query_id: entry.ranking for entry in self.run}
        for query_id, ranking in self.fixture["deduped_rankings"].items():
            assert dedupe(by_query[query_id]) == ranking

    def test_names_the_queries_it_corrected(self):
        result = score(self.judgments, self.run, k=5)
        assert result.queries_with_duplicates == self.fixture["queries_with_duplicates"]
        report = build_report(self.judgments, self.run, k=5)
        assert self.fixture["reason"] in report.verdict.reasons

    def test_cannot_carry_a_failing_run_past_a_gate(self):
        report = build_report(self.judgments, self.run, k=5)
        # Truthful recall is 0.75. Counted with the repeats it was 2.5, which cleared this floor.
        assert evaluate_gates(report, [parse_gate("recall@5:0.9")]).status == "FAIL"

    def test_rejects_a_run_that_is_malformed(self):
        for case in self.fixture["rejected"]["cases"]:
            with pytest.raises(ValueError, match=re.escape(case["message"])):
                parse_run(load("duplicate-ranking", case["file"]))


class TestUnsoundJudgments:
    """Scoring a set `validate` rejects and reporting PASS is the lie this tool exposes."""

    fixture = load_json("unsound-judgments", "expected.json")
    judgments = parse_judgments(load("unsound-judgments", "judgments.jsonl"))
    run = parse_run(load("unsound-judgments", "run.jsonl"))

    def test_is_an_error_not_a_warning(self):
        result = validate(self.judgments)
        assert result.ok is self.fixture["validate"]["ok"]
        codes = sorted({i.code for i in result.issues if i.severity == "error"})
        assert codes == self.fixture["validate"]["error_codes"]

    def test_cannot_be_scored_to_a_pass(self):
        report = build_report(self.judgments, self.run, k=2)
        assert report.verdict.status == self.fixture["verdict"]
        assert self.fixture["reason"] in report.verdict.reasons

    def test_is_not_cleared_by_a_gate_that_passes(self):
        report = build_report(self.judgments, self.run, k=2)
        evaluated = evaluate_gates(report, [parse_gate(self.fixture["gate"]["expression"])])
        assert evaluated.status == self.fixture["gate"]["gate_status"]
        assert (
            worse_status(report.verdict.status, evaluated.status) == self.fixture["gate"]["verdict"]
        )


class TestOrderingsThatReachTheOutput:
    """Insertion order here and sorted order there is a parity break sorted ids cannot catch."""

    fixture = load_json("unsorted-queries", "expected.json")
    judgments = parse_judgments(load("unsorted-queries", "judgments.jsonl"))

    def test_missing_query_text_is_sorted_not_file_order(self):
        issues = [i for i in validate(self.judgments).issues if i.code == "missing-query-text"]
        order = [i.message.split()[1] for i in issues]
        assert order == self.fixture["missing_query_text_order"]

    def test_thin_strata_are_sorted_not_insertion_order(self):
        issues = [i for i in validate(self.judgments).issues if i.code == "thin-stratum"]
        order = [i.message.split("'")[1] for i in issues]
        assert order == self.fixture["thin_stratum_order"]


class TestGateThresholds:
    """`float` took 'nan' and 'infinity'; `parseFloat` took '0.5abc'. Three silent splits."""

    @pytest.mark.parametrize("bad", ["0.5abc", "nan", "infinity", "inf", "1d0", ""])
    def test_rejects(self, bad):
        with pytest.raises(ValueError, match="is not a number"):
            parse_gate(f"recall@5:{bad}")

    @pytest.mark.parametrize(
        ("good", "value"),
        [("0.8", 0.8), ("-0.02", -0.02), ("1e-1", 0.1), (".5", 0.5), ("+1", 1.0)],
    )
    def test_accepts(self, good, value):
        assert parse_gate(f"recall@5:{good}").threshold == pytest.approx(value, abs=1e-12)


class TestStratumOrdering:
    """Code-point order and locale collation disagree about every one of these names."""

    fixture = load_json("stratum-order", "expected.json")
    judgments = parse_judgments(load("stratum-order", "judgments.jsonl"))
    run = parse_run(load("stratum-order", "run.jsonl"))

    def test_breaks_ties_by_code_point(self):
        per_stratum = score_by_stratum(self.judgments, self.run, k=3, threshold=2)
        scored = sorted(name for name, s in per_stratum.items() if s.n > 0)
        unscored = sorted(name for name, s in per_stratum.items() if s.n == 0)
        assert scored == self.fixture["scored_order"]
        assert unscored == self.fixture["unscored_order"]

    def test_counts_each_stratums_scored_queries(self):
        per_stratum = score_by_stratum(self.judgments, self.run, k=3, threshold=2)
        for name, n in self.fixture["per_stratum_n"].items():
            assert per_stratum[name].n == n
