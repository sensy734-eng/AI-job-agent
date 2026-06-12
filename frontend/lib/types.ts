export type ScoreBreakdown = {
  skill_match: number;
  project_experience: number;
  keyword_coverage: number;
  education_fit: number;
  risk_control: number;
  overall: number;
};

export type Evidence = {
  id: string;
  source: "resume" | "jd" | "interview_bank" | "feedback";
  title: string;
  text: string;
  score: number;
  retrieval_method: string;
};

export type GapItem = {
  type: "skill" | "project" | "keyword" | "education" | "risk";
  title: string;
  detail: string;
  priority: "high" | "medium" | "low";
  evidence_ids: string[];
};

export type RewriteSuggestion = {
  id: string;
  section: string;
  before: string;
  after: string;
  rationale: string;
  evidence_ids: string[];
  validation_status: "passed" | "warning" | "failed";
  validation_notes: string[];
};

export type InterviewQuestion = {
  id: string;
  category: "project" | "technical" | "behavioral" | "resume";
  question: string;
  expected_points: string[];
  evidence_ids: string[];
};

export type AgentTraceStep = {
  name: string;
  status: "success" | "error" | "skipped";
  started_at: string;
  duration_ms: number;
  input_summary: Record<string, string | number | boolean | null>;
  output_summary: Record<string, string | number | boolean | null>;
  error?: string | null;
};

export type MatchReport = {
  id: string;
  created_at: string;
  scores: ScoreBreakdown;
  summary: string;
  strengths: string[];
  gaps: GapItem[];
  evidence: Evidence[];
  rewrite_suggestions: RewriteSuggestion[];
  interview_questions: InterviewQuestion[];
  trace: AgentTraceStep[];
  model_provider: string;
  rag_mode: string;
  jd: {
    title: string;
    required_skills: string[];
    keywords: string[];
  };
  resume: {
    id: string;
    skills: string[];
    projects: string[];
  };
};

export type ReportSummary = {
  id: string;
  created_at: string;
  jd_title: string;
  overall_score: number;
  top_gap?: string | null;
  model_provider: string;
  rag_mode: string;
};

export type BatchMatchItem = {
  job_id: string;
  report_id: string;
  jd_title: string;
  overall_score: number;
  skill_match: number;
  project_experience: number;
  keyword_coverage: number;
  gap_count: number;
  top_gap?: string | null;
  priority: "high" | "medium" | "low";
  recommendation_reason: string;
  model_provider: string;
  rag_mode: string;
};

export type ResumeVersion = {
  id: string;
  resume_id: string;
  title: string;
  content: string;
  suggestions: RewriteSuggestion[];
  diff: string[];
  created_at: string;
};

export type ResumeExport = {
  filename: string;
  content: string;
};

export type EvaluationSummary = {
  case_count: number;
  exact_band_accuracy: number;
  gap_hit_rate: number;
  suggestion_evidence_coverage: number;
  hallucination_risk_count: number;
  average_latency_ms: number;
  validation_pass_rate: number;
  embedding_fallback_count: number;
  rag_backend: string;
  embedding_provider: string;
  embedding_model: string;
  embedding_dimension: number;
  embedding_real_enabled: boolean;
  cases: Array<{
    id: string;
    expected: string;
    actual: string;
    score: number;
    evidence: number;
    trace_steps: number;
    expected_gap_hits: number;
    expected_gap_total: number;
  }>;
};

export type HealthStatus = {
  status: "ok";
  service: string;
  mode: string;
  vector_backend: string;
  embedding_provider: string;
  embedding_fallback_count: number;
  embedding_configured_provider: string;
  embedding_model: string;
  embedding_dimension: number;
  embedding_real_enabled: boolean;
  embedding_last_error: string;
  embedding_device: string;
  embedding_load_status: "not_loaded" | "loading" | "ready" | "fallback" | "error";
  embedding_latency_ms: number;
};

export type InterviewFeedback = {
  score: number;
  strengths: string[];
  improvements: string[];
  revised_answer_outline: string[];
};
