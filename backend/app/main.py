from __future__ import annotations

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.session import active_vector_backend
from app.schemas import (
    BatchMatchRequest,
    BatchMatchResponse,
    EvaluationSummary,
    FeedbackEvent,
    FeedbackRequest,
    HealthResponse,
    InterviewAnswerRequest,
    InterviewFeedback,
    InterviewSession,
    InterviewSessionRequest,
    JobAnalyzeRequest,
    MatchReport,
    MatchRequest,
    ParsedJobDescription,
    ParsedResume,
    ReportSummary,
    ResumeExport,
    ResumeVersion,
    ResumeVersionRequest,
    ResumeTextRequest,
    ReindexResponse,
    RewriteResponse,
)
from app.db.repository import get_repository
from app.db.session import init_db
from app.services.agent import JobAgent, get_agent
from app.services.embeddings import embedding_status, warmup_embedding_provider
from app.services.parser import parse_document_bytes, parse_jd, parse_resume

settings = get_settings()

app = FastAPI(
    title="AI 求职助手 Agent API",
    description="岗位 JD + 个人简历驱动的匹配、简历优化与面试准备 API。",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    status = embedding_status()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        mode=settings.llm_provider,
        vector_backend=active_vector_backend(),
        embedding_provider=str(status["embedding_provider"]),
        embedding_fallback_count=int(status["embedding_fallback_count"]),
        embedding_configured_provider=str(status["embedding_configured_provider"]),
        embedding_model=str(status["embedding_model"]),
        embedding_dimension=int(status["embedding_dimension"]),
        embedding_real_enabled=bool(status["embedding_real_enabled"]),
        embedding_last_error=str(status["embedding_last_error"]),
        embedding_device=str(status["embedding_device"]),
        embedding_load_status=str(status["embedding_load_status"]),
        embedding_latency_ms=int(status["embedding_latency_ms"]),
    )


@app.post("/resumes/parse", response_model=ParsedResume)
def parse_resume_text(request: ResumeTextRequest) -> ParsedResume:
    return parse_resume(request.text)


@app.post("/resumes/upload", response_model=ParsedResume)
async def upload_resume(file: UploadFile = File(...)) -> ParsedResume:
    content = await file.read()
    try:
        text = parse_document_bytes(file.filename or "resume.txt", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if len(text.strip()) < 20:
        raise HTTPException(status_code=400, detail="简历内容过短，无法解析。")
    return parse_resume(text)


@app.post("/jobs/analyze", response_model=ParsedJobDescription)
def analyze_job(request: JobAnalyzeRequest) -> ParsedJobDescription:
    return parse_jd(request.jd_text)


@app.post("/matches", response_model=MatchReport)
def create_match_report(request: MatchRequest, agent: JobAgent = Depends(get_agent)) -> MatchReport:
    return agent.run_match(request)


@app.post("/matches/batch", response_model=BatchMatchResponse)
def create_batch_match_report(request: BatchMatchRequest, agent: JobAgent = Depends(get_agent)) -> BatchMatchResponse:
    return agent.run_batch_match(request)


@app.post("/resumes/{resume_id}/rewrite", response_model=RewriteResponse)
def rewrite_resume(
    resume_id: str,
    request: MatchRequest,
    agent: JobAgent = Depends(get_agent),
) -> RewriteResponse:
    del resume_id
    return agent.rewrite(request)


@app.post("/interviews/sessions", response_model=InterviewSession)
def create_interview_session(
    request: InterviewSessionRequest,
    agent: JobAgent = Depends(get_agent),
) -> InterviewSession:
    return agent.start_interview(request)


@app.post("/interviews/{session_id}/answer", response_model=InterviewFeedback)
def answer_interview_question(
    session_id: str,
    request: InterviewAnswerRequest,
    agent: JobAgent = Depends(get_agent),
) -> InterviewFeedback:
    del session_id
    return agent.grade_interview_answer(request.question, request.answer)


@app.post("/feedback", response_model=FeedbackEvent)
def record_feedback(request: FeedbackRequest, agent: JobAgent = Depends(get_agent)) -> FeedbackEvent:
    return agent.record_feedback(request)


@app.get("/reports/{report_id}", response_model=MatchReport)
def get_report(report_id: str, agent: JobAgent = Depends(get_agent)) -> MatchReport:
    report = agent.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在或已过期。")
    return report


@app.get("/reports", response_model=list[ReportSummary])
def list_reports(limit: int = 20, agent: JobAgent = Depends(get_agent)) -> list[ReportSummary]:
    return agent.list_reports(limit)


@app.post("/resume-versions", response_model=ResumeVersion)
def create_resume_version(request: ResumeVersionRequest, agent: JobAgent = Depends(get_agent)) -> ResumeVersion:
    try:
        return agent.create_resume_version(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/resume-versions/{resume_id}", response_model=list[ResumeVersion])
def list_resume_versions(resume_id: str, agent: JobAgent = Depends(get_agent)) -> list[ResumeVersion]:
    return agent.list_resume_versions(resume_id)


@app.get("/resume-versions/export/{version_id}", response_model=ResumeExport)
def export_resume_version(version_id: str, agent: JobAgent = Depends(get_agent)) -> ResumeExport:
    try:
        return agent.export_resume_version(version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/evaluation/summary", response_model=EvaluationSummary)
def evaluation_summary(agent: JobAgent = Depends(get_agent)) -> EvaluationSummary:
    return agent.evaluation_summary()


@app.post("/rag/reindex", response_model=ReindexResponse)
def reindex_rag_chunks() -> ReindexResponse:
    result = get_repository().reindex_rag_chunks()
    status = embedding_status()
    return ReindexResponse(
        status="ok",
        updated_chunks=int(result["updated_chunks"]),
        source_counts=result["source_counts"],
        embedding_provider=str(result["embedding_provider"]),
        embedding_model=str(result["embedding_model"]),
        embedding_dimension=int(status["embedding_dimension"]),
        duration_ms=int(result["duration_ms"]),
        failed_chunks=int(result["failed_chunks"]),
    )


@app.post("/embeddings/warmup", response_model=HealthResponse)
def warmup_embeddings() -> HealthResponse:
    warmup_embedding_provider()
    return health()


@app.get("/showcase")
def project_showcase() -> dict:
    return {
        "title": "AI 求职助手 Agent v2",
        "positioning": "面向 AI 实习投递的简历/JD 匹配、简历优化和面试准备 Agent。",
        "architecture": [
            "Next.js 工作台负责输入、报告展示、证据侧栏和反馈交互。",
            "FastAPI 提供结构化 API，并通过 Pydantic 约束输入输出。",
            "Agent workflow 记录 ResumeParser、JDParser、RAGRetriever、MatchScorer、ResumeRewriter、InterviewCoach 等节点 trace。",
            "RAG 使用关键词召回 + 向量召回 + 简单重排，真实 embedding 不可用时回退 hashing，生产部署预留 pgvector。",
        ],
        "metrics": [
            "报告生成 P95 < 20s",
            "结构化输出解析失败可降级",
            "改写建议必须引用证据",
            "20 组样例评测统计匹配准确率、短板命中率、证据覆盖和幻觉风险",
        ],
        "v2_features": [
            "多 JD 横向对比",
            "简历版本生成与历史",
            "评测摘要 API",
            "证据召回方式标注",
        ],
    }
