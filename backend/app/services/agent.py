from __future__ import annotations

from app.schemas import (
    BatchMatchItem,
    BatchMatchRequest,
    BatchMatchResponse,
    FeedbackEvent,
    FeedbackRequest,
    EvaluationSummary,
    InterviewFeedback,
    InterviewSession,
    InterviewSessionRequest,
    MatchReport,
    MatchRequest,
    ResumeExport,
    ResumeVersion,
    ResumeVersionRequest,
    RewriteResponse,
)
from app.db.repository import JobRepository, get_repository
from app.services.interview import build_interview_questions, grade_answer
from app.services.llm import LLMProvider, OfflineProvider, get_llm_provider
from app.services.parser import parse_jd, parse_resume
from app.services.embeddings import get_embedding_provider
from app.services.rag import INTERVIEW_BANK, RepositoryRetriever, SimpleRetriever
from app.services.rewriter import build_rewrite_suggestions
from app.services.scoring import build_gaps, score_match, summarize_strengths
from app.services.validator import safe_suggestions, validate_rewrite_suggestions
from app.services.workflow import TraceRecorder, WorkflowRunner
from app.evaluation.metrics import run_evaluation


REPORT_STORE: dict[str, MatchReport] = {}
FEEDBACK_STORE: list[FeedbackEvent] = []
EVALUATION_CACHE: EvaluationSummary | None = None


class JobAgent:
    def __init__(self, repository: JobRepository | None = None, llm_provider: LLMProvider | None = None) -> None:
        self.repository = repository or get_repository()
        self.llm_provider = llm_provider or get_llm_provider()
        self.workflow = WorkflowRunner()

    def run_match(self, request: MatchRequest) -> MatchReport:
        tracer = TraceRecorder()
        initial_state = {"request": request, "tracer": tracer}
        nodes = [
            ("InputGuard", self._input_guard),
            ("ResumeParser", self._parse_resume_node),
            ("JDParser", self._parse_jd_node),
            ("RAGRetriever", self._retrieve_node),
            ("MatchScorer", self._score_node),
            ("ResumeRewriter", self._rewrite_node),
            ("InterviewCoach", self._interview_node),
            ("ReportAssembler", self._assemble_node),
        ]
        state = self.workflow.run(initial_state, nodes)
        report: MatchReport = state["report"]
        REPORT_STORE[report.id] = report
        self.repository.save_report(report)
        return report

    def rewrite(self, request: MatchRequest) -> RewriteResponse:
        report = self.run_match(request)
        return RewriteResponse(report_id=report.id, suggestions=report.rewrite_suggestions)

    def run_batch_match(self, request: BatchMatchRequest) -> BatchMatchResponse:
        items: list[BatchMatchItem] = []
        for index, job in enumerate(request.jobs, start=1):
            report = self.run_match(MatchRequest(resume_text=request.resume_text, jd_text=job.jd_text))
            priority = self._priority(report)
            items.append(
                BatchMatchItem(
                    job_id=job.id or f"job_{index}",
                    report_id=report.id,
                    jd_title=report.jd.title,
                    overall_score=report.scores.overall,
                    skill_match=report.scores.skill_match,
                    project_experience=report.scores.project_experience,
                    keyword_coverage=report.scores.keyword_coverage,
                    gap_count=len(report.gaps),
                    top_gap=report.gaps[0].title if report.gaps else None,
                    priority=priority,
                    recommendation_reason=self._recommendation_reason(report),
                    model_provider=report.model_provider,
                    rag_mode=report.rag_mode,
                )
            )
        items.sort(key=lambda item: item.overall_score, reverse=True)
        return BatchMatchResponse(items=items)

    def start_interview(self, request: InterviewSessionRequest) -> InterviewSession:
        report = self.run_match(MatchRequest(resume_text=request.resume_text, jd_text=request.jd_text))
        return InterviewSession(
            report_id=report.id,
            questions=report.interview_questions[: request.question_count],
        )

    def grade_interview_answer(self, question: str, answer: str) -> InterviewFeedback:
        rule_feedback = grade_answer(question, answer)
        if self.llm_provider.name == "offline":
            return rule_feedback
        try:
            payload = self.llm_provider.complete_json_sync(
                "你是 AI 实习面试教练。只返回 JSON，字段为 score、strengths、improvements、revised_answer_outline。",
                f"问题：{question}\n回答：{answer}\n请基于回答本身给出结构化反馈，不要编造经历。",
            )
            return InterviewFeedback.model_validate(payload)
        except Exception:
            return rule_feedback

    def record_feedback(self, request: FeedbackRequest) -> FeedbackEvent:
        event = FeedbackEvent(target_id=request.target_id, action=request.action, comment=request.comment)
        FEEDBACK_STORE.append(event)
        self.repository.save_feedback(event)
        return event

    def get_report(self, report_id: str) -> MatchReport | None:
        return REPORT_STORE.get(report_id) or self.repository.get_report(report_id)

    def list_reports(self, limit: int = 20):
        return self.repository.list_reports(limit)

    def create_resume_version(self, request: ResumeVersionRequest) -> ResumeVersion:
        report = self.get_report(request.report_id) if request.report_id else None
        if report is None:
            raise ValueError("需要提供有效 report_id 来生成简历版本。")
        accepted = set(request.accepted_suggestion_ids)
        suggestions = [
            item
            for item in report.rewrite_suggestions
            if not accepted or item.id in accepted
        ]
        content = self._compose_resume_version(report.resume.raw_text, suggestions)
        title = request.title or f"{report.jd.title} 定制版本"
        return self.repository.create_resume_version(request.resume_id, title, content, suggestions)

    def list_resume_versions(self, resume_id: str) -> list[ResumeVersion]:
        return self.repository.list_resume_versions(resume_id)

    def export_resume_version(self, version_id: str) -> ResumeExport:
        version = self.repository.get_resume_version(version_id)
        if version is None:
            raise ValueError("简历版本不存在或已过期。")
        safe_title = "".join(char if char.isalnum() else "-" for char in version.title).strip("-") or "resume-version"
        lines = [
            f"# {version.title}",
            "",
            "## 版本差异",
            "",
            "```diff",
            *(version.diff or ["+ 当前版本暂无差异记录"]),
            "```",
            "",
            "## 优化后内容",
            "",
            version.content,
            "",
            "## 证据与校验",
        ]
        for suggestion in version.suggestions:
            evidence_ids = ", ".join(suggestion.evidence_ids) or "无"
            lines.extend(
                [
                    "",
                    f"### {suggestion.section}",
                    f"- 证据 ID：{evidence_ids}",
                    f"- 校验状态：{suggestion.validation_status}",
                    f"- 改写理由：{suggestion.rationale}",
                ]
            )
            if suggestion.validation_notes:
                lines.append(f"- 校验备注：{'; '.join(suggestion.validation_notes)}")
        return ResumeExport(filename=f"{safe_title}.md", content="\n".join(lines).strip() + "\n")

    def evaluation_summary(self) -> EvaluationSummary:
        global EVALUATION_CACHE
        if EVALUATION_CACHE is None:
            EVALUATION_CACHE = run_evaluation(JobAgent(repository=self.repository, llm_provider=OfflineProvider()))
        return EVALUATION_CACHE

    def _input_guard(self, state: dict) -> dict:
        request: MatchRequest = state["request"]
        tracer: TraceRecorder = state["tracer"]

        def action() -> dict:
            if len(request.resume_text.strip()) < 20 or len(request.jd_text.strip()) < 20:
                raise ValueError("简历和 JD 内容都需要至少 20 个字符。")
            return {"resume_chars": len(request.resume_text), "jd_chars": len(request.jd_text)}

        tracer.run("InputGuard", {"resume_chars": len(request.resume_text), "jd_chars": len(request.jd_text)}, action)
        return state

    def _parse_resume_node(self, state: dict) -> dict:
        request: MatchRequest = state["request"]
        tracer: TraceRecorder = state["tracer"]

        def action() -> dict:
            resume = parse_resume(request.resume_text)
            state["resume"] = resume
            return {"skills": len(resume.skills), "projects": len(resume.projects), "target_role": resume.target_role}

        tracer.run("ResumeParser", {"text_chars": len(request.resume_text)}, action)
        return state

    def _parse_jd_node(self, state: dict) -> dict:
        request: MatchRequest = state["request"]
        tracer: TraceRecorder = state["tracer"]

        def action() -> dict:
            jd = parse_jd(request.jd_text)
            state["jd"] = jd
            return {"title": jd.title, "required_skills": len(jd.required_skills), "keywords": len(jd.keywords)}

        tracer.run("JDParser", {"text_chars": len(request.jd_text)}, action)
        return state

    def _retrieve_node(self, state: dict) -> dict:
        request: MatchRequest = state["request"]
        tracer: TraceRecorder = state["tracer"]

        def action() -> dict:
            jd = state["jd"]
            resume = state["resume"]
            feedback_texts = [item.comment for item in FEEDBACK_STORE if item.comment] + self.repository.feedback_texts()
            embedding_provider = get_embedding_provider()
            resume_chunks = self.repository.upsert_text_chunks(
                resume.id,
                "resume",
                "简历证据",
                request.resume_text,
                embedding_provider.embed_texts([chunk.text for chunk in self._preview_chunks("resume", "简历证据", request.resume_text)]),
            )
            jd_chunks = self.repository.upsert_text_chunks(
                jd.id,
                "jd",
                "JD 证据",
                request.jd_text,
                embedding_provider.embed_texts([chunk.text for chunk in self._preview_chunks("jd", "JD 证据", request.jd_text)]),
            )
            interview_owner_id = "interview_bank_default"
            self.repository.upsert_static_chunks(
                interview_owner_id,
                "interview_bank",
                "面试题库",
                INTERVIEW_BANK,
                embedding_provider,
            )
            feedback_owner_ids = self.repository.upsert_feedback_contexts(feedback_texts, embedding_provider)
            fallback = SimpleRetriever(request.resume_text, request.jd_text, feedback_texts=feedback_texts, embedding_provider=embedding_provider)
            retriever = RepositoryRetriever(
                self.repository,
                [resume.id, jd.id, interview_owner_id, *feedback_owner_ids],
                fallback,
                embedding_provider=embedding_provider,
            )
            evidence = retriever.search(f"{jd.title} {' '.join(jd.required_skills + jd.keywords)}", limit=10)
            state["retriever"] = retriever
            state["evidence"] = evidence
            return {
                "evidence": len(evidence),
                "rag_mode": retriever.mode,
                "resume_chunks": resume_chunks,
                "jd_chunks": jd_chunks,
                "feedback_contexts": len(feedback_texts),
            }

        tracer.run("RAGRetriever", {"query": "jd title + required skills + keywords"}, action)
        return state

    def _score_node(self, state: dict) -> dict:
        tracer: TraceRecorder = state["tracer"]

        def action() -> dict:
            resume = state["resume"]
            jd = state["jd"]
            scores = score_match(resume, jd)
            gaps = build_gaps(resume, jd)
            strengths = summarize_strengths(resume, jd)
            state["scores"] = scores
            state["gaps"] = gaps
            state["strengths"] = strengths
            return {"overall": scores.overall, "gaps": len(gaps), "strengths": len(strengths)}

        tracer.run("MatchScorer", {"weights": "35/30/15/10/10"}, action)
        return state

    def _rewrite_node(self, state: dict) -> dict:
        tracer: TraceRecorder = state["tracer"]

        def action() -> dict:
            suggestions = build_rewrite_suggestions(state["resume"], state["jd"], state["evidence"])
            if self.llm_provider.name != "offline":
                suggestions = self._try_llm_rewrite(state, suggestions)
            suggestions = validate_rewrite_suggestions(suggestions, state["resume"], state["evidence"])
            suggestions = safe_suggestions(suggestions)
            state["rewrite_suggestions"] = suggestions
            return {"suggestions": len(suggestions), "provider": self.llm_provider.name}

        tracer.run("ResumeRewriter", {"provider": self.llm_provider.name}, action)
        return state

    def _interview_node(self, state: dict) -> dict:
        tracer: TraceRecorder = state["tracer"]

        def action() -> dict:
            evidence_ids = [item.id for item in state["evidence"][:4]]
            questions = build_interview_questions(state["resume"], state["jd"], evidence_ids)
            state["interview_questions"] = questions
            return {"questions": len(questions)}

        tracer.run("InterviewCoach", {"evidence": len(state["evidence"])}, action)
        return state

    def _assemble_node(self, state: dict) -> dict:
        tracer: TraceRecorder = state["tracer"]

        def action() -> dict:
            jd = state["jd"]
            scores = state["scores"]
            gaps = state["gaps"]
            report = MatchReport(
                resume=state["resume"],
                jd=jd,
                scores=scores,
                summary=(
                    f"该简历与“{jd.title}”整体匹配度为 {scores.overall}/100。"
                    f"优先补强 {gaps[0].title}，并把项目经历改写为可验证的岗位证据。"
                ),
                strengths=state["strengths"],
                gaps=gaps,
                evidence=state["evidence"],
                rewrite_suggestions=state["rewrite_suggestions"],
                interview_questions=state["interview_questions"],
                trace=tracer.steps,
                model_provider=self.llm_provider.name,
                rag_mode=state["retriever"].mode,
            )
            state["report"] = report
            return {"report_id": report.id, "trace_steps": len(report.trace)}

        tracer.run("ReportAssembler", {"provider": self.llm_provider.name}, action)
        return state

    def _try_llm_rewrite(self, state: dict, fallback):
        try:
            payload = self.llm_provider.complete_json_sync(
                "你是严谨的简历优化助手。只返回 JSON：suggestions 数组，每项包含 section、before、after、rationale、evidence_ids。禁止虚构经历。",
                (
                    f"简历：{state['resume'].raw_text}\n\n"
                    f"JD：{state['jd'].raw_text}\n\n"
                    f"证据ID：{[item.id for item in state['evidence']]}\n"
                    "请只基于简历和 JD 证据生成最多 5 条改写建议。"
                ),
            )
            items = payload.get("suggestions", payload if isinstance(payload, list) else [])
            if not items:
                return fallback
            from app.schemas import RewriteSuggestion

            return [RewriteSuggestion.model_validate(item) for item in items[:5]]
        except Exception:
            return fallback

    def _priority(self, report: MatchReport):
        if report.scores.overall >= 75 and len(report.gaps) <= 3:
            return "high"
        if report.scores.overall >= 50:
            return "medium"
        return "low"

    def _recommendation_reason(self, report: MatchReport) -> str:
        if report.scores.overall >= 75:
            return "优先投递：整体匹配较高，建议围绕首要短板做定制化改写。"
        if report.scores.overall >= 50:
            return "可投递但需优化：先补强技能证据和项目表达，再进入面试准备。"
        return "谨慎投递：当前短板较明显，除非岗位非常感兴趣，否则优先选择更匹配岗位。"

    def _compose_resume_version(self, raw_text: str, suggestions) -> str:
        lines = [raw_text.strip(), "", "## 针对岗位的优化建议采纳版"]
        for item in suggestions:
            lines.append(f"### {item.section}")
            lines.append(item.after)
        return "\n".join(lines).strip()

    def _preview_chunks(self, source: str, title: str, text: str):
        from app.services.nlp import make_chunks

        return make_chunks(source, title, text)


def get_agent() -> JobAgent:
    return JobAgent()
