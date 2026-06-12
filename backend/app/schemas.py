from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class EvidenceSource(str, Enum):
    resume = "resume"
    jd = "jd"
    interview_bank = "interview_bank"
    feedback = "feedback"


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ev"))
    source: EvidenceSource
    title: str
    text: str
    score: float = Field(ge=0, le=1)
    retrieval_method: str = "hybrid"


class ParsedResume(BaseModel):
    id: str = Field(default_factory=lambda: new_id("resume"))
    name: str | None = None
    target_role: str | None = None
    education: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    raw_text: str


class ParsedJobDescription(BaseModel):
    id: str = Field(default_factory=lambda: new_id("jd"))
    title: str
    company: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    raw_text: str


class ResumeTextRequest(BaseModel):
    text: str = Field(min_length=20)


class JobAnalyzeRequest(BaseModel):
    jd_text: str = Field(min_length=20)


class MatchRequest(BaseModel):
    resume_text: str = Field(min_length=20)
    jd_text: str = Field(min_length=20)


class BatchJobInput(BaseModel):
    id: str | None = None
    jd_text: str = Field(min_length=20)


class BatchMatchRequest(BaseModel):
    resume_text: str = Field(min_length=20)
    jobs: list[BatchJobInput] = Field(min_length=1, max_length=8)


class ScoreBreakdown(BaseModel):
    skill_match: int = Field(ge=0, le=100)
    project_experience: int = Field(ge=0, le=100)
    keyword_coverage: int = Field(ge=0, le=100)
    education_fit: int = Field(ge=0, le=100)
    risk_control: int = Field(ge=0, le=100)
    overall: int = Field(ge=0, le=100)


class GapItem(BaseModel):
    type: Literal["skill", "project", "keyword", "education", "risk"]
    title: str
    detail: str
    priority: Literal["high", "medium", "low"]
    evidence_ids: list[str] = Field(default_factory=list)


class RewriteSuggestion(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rw"))
    section: str
    before: str
    after: str
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    validation_status: Literal["passed", "warning", "failed"] = "passed"
    validation_notes: list[str] = Field(default_factory=list)


class InterviewQuestion(BaseModel):
    id: str = Field(default_factory=lambda: new_id("q"))
    category: Literal["project", "technical", "behavioral", "resume"]
    question: str
    expected_points: list[str]
    evidence_ids: list[str] = Field(default_factory=list)


class AgentTraceStep(BaseModel):
    name: str
    status: Literal["success", "error", "skipped"]
    started_at: datetime
    duration_ms: int
    input_summary: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    output_summary: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    error: str | None = None


class MatchReport(BaseModel):
    id: str = Field(default_factory=lambda: new_id("report"))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resume: ParsedResume
    jd: ParsedJobDescription
    scores: ScoreBreakdown
    summary: str
    strengths: list[str]
    gaps: list[GapItem]
    evidence: list[Evidence]
    rewrite_suggestions: list[RewriteSuggestion]
    interview_questions: list[InterviewQuestion]
    trace: list[AgentTraceStep] = Field(default_factory=list)
    model_provider: str = "offline"
    rag_mode: str = "hybrid-memory"


class ReportSummary(BaseModel):
    id: str
    created_at: datetime
    jd_title: str
    overall_score: int
    top_gap: str | None = None
    model_provider: str = "offline"
    rag_mode: str = "hybrid-memory"


class BatchMatchItem(BaseModel):
    job_id: str
    report_id: str
    jd_title: str
    overall_score: int
    skill_match: int
    project_experience: int
    keyword_coverage: int
    gap_count: int
    top_gap: str | None = None
    priority: Literal["high", "medium", "low"]
    recommendation_reason: str
    model_provider: str
    rag_mode: str


class BatchMatchResponse(BaseModel):
    items: list[BatchMatchItem]


class ResumeVersionRequest(BaseModel):
    resume_id: str
    report_id: str | None = None
    accepted_suggestion_ids: list[str] = Field(default_factory=list)
    title: str | None = None


class ResumeVersion(BaseModel):
    id: str = Field(default_factory=lambda: new_id("version"))
    resume_id: str
    title: str
    content: str
    suggestions: list[RewriteSuggestion] = Field(default_factory=list)
    diff: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResumeExport(BaseModel):
    filename: str
    content: str


class EvaluationCaseResult(BaseModel):
    id: str
    expected: str
    actual: str
    score: int
    evidence: int
    trace_steps: int
    expected_gap_hits: int = 0
    expected_gap_total: int = 0


class EvaluationSummary(BaseModel):
    case_count: int
    exact_band_accuracy: float
    gap_hit_rate: float
    suggestion_evidence_coverage: float
    hallucination_risk_count: int
    average_latency_ms: int
    validation_pass_rate: float = 0
    embedding_fallback_count: int = 0
    rag_backend: str = "sqlite"
    embedding_provider: str = "offline-hashing"
    embedding_model: str = "hashing"
    embedding_dimension: int = 64
    embedding_real_enabled: bool = False
    cases: list[EvaluationCaseResult]


class RewriteRequest(BaseModel):
    resume_text: str = Field(min_length=20)
    jd_text: str = Field(min_length=20)
    focus: str | None = "AI 实习岗位"


class RewriteResponse(BaseModel):
    report_id: str
    suggestions: list[RewriteSuggestion]


class InterviewSessionRequest(BaseModel):
    resume_text: str = Field(min_length=20)
    jd_text: str = Field(min_length=20)
    question_count: int = Field(default=6, ge=1, le=10)


class InterviewSession(BaseModel):
    id: str = Field(default_factory=lambda: new_id("session"))
    report_id: str
    questions: list[InterviewQuestion]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InterviewAnswerRequest(BaseModel):
    question: str = Field(min_length=5)
    answer: str = Field(min_length=1)
    resume_text: str | None = None
    jd_text: str | None = None


class InterviewFeedback(BaseModel):
    score: int = Field(ge=0, le=100)
    strengths: list[str]
    improvements: list[str]
    revised_answer_outline: list[str]


class FeedbackRequest(BaseModel):
    target_id: str
    action: Literal["accept", "reject", "revise"]
    comment: str | None = None


class FeedbackEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("feedback"))
    target_id: str
    action: Literal["accept", "reject", "revise"]
    comment: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    mode: str
    vector_backend: str = "sqlite"
    embedding_provider: str = "offline-hashing"
    embedding_fallback_count: int = 0
    embedding_configured_provider: str = "offline"
    embedding_model: str = "hashing"
    embedding_dimension: int = 64
    embedding_real_enabled: bool = False
    embedding_last_error: str = ""
    embedding_device: str = "auto"
    embedding_load_status: Literal["not_loaded", "loading", "ready", "fallback", "error"] = "not_loaded"
    embedding_latency_ms: int = 0


class ReindexResponse(BaseModel):
    status: Literal["ok"]
    updated_chunks: int = 0
    source_counts: dict[str, int] = Field(default_factory=dict)
    embedding_provider: str = "offline-hashing"
    embedding_model: str = "hashing"
    embedding_dimension: int = 64
    duration_ms: int = 0
    failed_chunks: int = 0
