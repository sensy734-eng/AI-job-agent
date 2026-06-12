from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Protocol

from app.schemas import EvaluationCaseResult, EvaluationSummary, MatchRequest
from app.db.session import active_vector_backend
from app.services.embeddings import embedding_status


class MatchAgent(Protocol):
    def run_match(self, request: MatchRequest): ...


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "fixtures.json"


def band(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def run_evaluation(agent: MatchAgent) -> EvaluationSummary:
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    rows: list[EvaluationCaseResult] = []
    hallucination_risks = 0
    cited_suggestions = 0
    total_suggestions = 0
    passed_suggestions = 0
    total_gap_hits = 0
    total_expected_gaps = 0
    latencies: list[int] = []

    for fixture in fixtures:
        start = perf_counter()
        report = agent.run_match(MatchRequest(resume_text=fixture["resume_text"], jd_text=fixture["jd_text"]))
        latencies.append(round((perf_counter() - start) * 1000))
        expected = fixture["expected_band"]
        actual = band(report.scores.overall)

        total_suggestions += len(report.rewrite_suggestions)
        cited_suggestions += sum(1 for item in report.rewrite_suggestions if item.evidence_ids)
        passed_suggestions += sum(1 for item in report.rewrite_suggestions if item.validation_status == "passed")

        forbidden = fixture.get("forbidden_terms", [])
        for item in report.rewrite_suggestions:
            if any(term in item.after for term in forbidden):
                hallucination_risks += 1

        expected_gaps = fixture.get("expected_gaps", [])
        gap_text = " ".join([gap.title + " " + gap.detail for gap in report.gaps])
        gap_hits = sum(1 for expected_gap in expected_gaps if expected_gap.lower() in gap_text.lower())
        total_gap_hits += gap_hits
        total_expected_gaps += len(expected_gaps)

        rows.append(
            EvaluationCaseResult(
                id=fixture["id"],
                expected=expected,
                actual=actual,
                score=report.scores.overall,
                evidence=len(report.evidence),
                trace_steps=len(report.trace),
                expected_gap_hits=gap_hits,
                expected_gap_total=len(expected_gaps),
            )
        )

    exact_band_accuracy = sum(1 for row in rows if row.expected == row.actual) / max(1, len(rows))
    status = embedding_status()
    return EvaluationSummary(
        case_count=len(rows),
        exact_band_accuracy=round(exact_band_accuracy, 3),
        gap_hit_rate=round(total_gap_hits / max(1, total_expected_gaps), 3),
        suggestion_evidence_coverage=round(cited_suggestions / max(1, total_suggestions), 3),
        hallucination_risk_count=hallucination_risks,
        average_latency_ms=round(sum(latencies) / max(1, len(latencies))),
        validation_pass_rate=round(passed_suggestions / max(1, total_suggestions), 3),
        embedding_fallback_count=int(status["embedding_fallback_count"]),
        rag_backend=active_vector_backend(),
        embedding_provider=str(status["embedding_provider"]),
        embedding_model=str(status["embedding_model"]),
        embedding_dimension=int(status["embedding_dimension"]),
        embedding_real_enabled=bool(status["embedding_real_enabled"]),
        cases=rows,
    )
