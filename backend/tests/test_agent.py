import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.models import JobDescriptionChunk, RagChunk, ResumeChunk
from app.db.repository import session_scope
from app.main import app
from app.schemas import BatchJobInput, BatchMatchRequest, Evidence, EvidenceSource, InterviewAnswerRequest, MatchRequest, ResumeVersionRequest, RewriteSuggestion
from app.services.embeddings import EmbeddingProvider, embedding_status
from app.services.agent import JobAgent, get_agent
from app.services.llm import OfflineProvider
from app.services.parser import parse_jd, parse_resume
from app.services.scoring import score_match
from app.services.validator import validate_rewrite_suggestions


RESUME = """
张三
软件工程本科大三，求职意向：AI 应用开发实习生
技能：Python、FastAPI、React、SQL、Git、RAG、LLM、Pandas
项目经历：
AI 求职助手 Agent：使用 FastAPI 和 React 实现简历解析、JD 匹配、RAG 检索和面试题生成，负责后端 API、评分策略和交互原型。
校园问答系统：基于向量检索和大模型回答实现课程资料问答，设计文档切分、召回和答案引用。
"""

JD = """
岗位：AI 应用开发实习生
职责：
- 参与大模型应用、RAG 检索和 Agent 工作流开发
- 使用 Python/FastAPI 设计后端 API，并和前端联调
要求：
- 计算机、软件工程相关专业本科及以上
- 熟悉 Python、SQL、RAG、LLM，有 React 或 Next.js 经验加分
"""


class AgentTest(unittest.TestCase):
    def test_parse_resume(self) -> None:
        resume = parse_resume(RESUME)
        self.assertIn("Python", resume.skills)
        self.assertTrue(resume.projects)

    def test_parse_jd(self) -> None:
        jd = parse_jd(JD)
        self.assertIn("RAG", jd.required_skills)
        self.assertEqual(jd.title, "AI 应用开发实习生")

    def test_match_report_contains_evidence(self) -> None:
        report = get_agent().run_match(MatchRequest(resume_text=RESUME, jd_text=JD))
        self.assertGreaterEqual(report.scores.overall, 50)
        self.assertTrue(report.evidence)
        self.assertTrue(report.evidence[0].retrieval_method)
        self.assertTrue(report.rewrite_suggestions)
        self.assertTrue(report.interview_questions)

    def test_batch_match_returns_sorted_items(self) -> None:
        agent = JobAgent(llm_provider=OfflineProvider())
        response = agent.run_batch_match(
            BatchMatchRequest(
                resume_text=RESUME,
                jobs=[
                    BatchJobInput(id="good", jd_text=JD),
                    BatchJobInput(
                        id="weak",
                        jd_text="岗位：市场运营实习生\n职责：活动策划、用户访谈、社群运营。\n要求：Excel、PPT、沟通能力。",
                    ),
                ],
            )
        )
        self.assertEqual(len(response.items), 2)
        self.assertGreaterEqual(response.items[0].overall_score, response.items[1].overall_score)
        self.assertTrue(response.items[0].recommendation_reason)

    def test_resume_version_can_be_created(self) -> None:
        agent = JobAgent(llm_provider=OfflineProvider())
        report = agent.run_match(MatchRequest(resume_text=RESUME, jd_text=JD))
        version = agent.create_resume_version(
            ResumeVersionRequest(
                resume_id=report.resume.id,
                report_id=report.id,
                accepted_suggestion_ids=[report.rewrite_suggestions[0].id],
            )
        )
        self.assertEqual(version.resume_id, report.resume.id)
        self.assertIn("优化建议采纳版", version.content)
        self.assertTrue(version.diff)
        exported = agent.export_resume_version(version.id)
        self.assertTrue(exported.filename.endswith(".md"))
        self.assertIn("## 版本差异", exported.content)

    def test_rewrite_validator_marks_unsafe_claims(self) -> None:
        resume = parse_resume(RESUME)
        evidence = [
            Evidence(source=EvidenceSource.resume, title="项目经历", text=resume.projects[0], score=0.9),
        ]
        suggestion = RewriteSuggestion(
            section="项目经历",
            before=resume.projects[0],
            after="曾在腾讯负责 RAG 系统，核心指标提升 35%。",
            rationale="测试幻觉校验",
            evidence_ids=["missing"],
        )
        validated = validate_rewrite_suggestions([suggestion], resume, evidence)[0]
        self.assertEqual(validated.validation_status, "failed")
        self.assertEqual(validated.evidence_ids, [evidence[0].id])

    def test_medium_ai_match_is_not_scored_too_low(self) -> None:
        resume = parse_resume(
            """
            李四
            软件工程本科大三，做过课程管理系统和后端接口开发。
            技能：Python、SQL、Git
            项目经历：课程管理系统，负责 API 设计、数据库建模和前后端联调。
            """
        )
        jd = parse_jd(
            """
            岗位：AI 工程实习生
            职责：参与大模型应用、RAG 检索和业务系统后端开发。
            要求：熟悉 Python、SQL，了解 LLM、RAG、Embedding。
            """
        )
        scores = score_match(resume, jd)
        self.assertGreaterEqual(scores.overall, 50)

    def test_report_persists_resume_and_jd_chunks(self) -> None:
        agent = JobAgent(llm_provider=OfflineProvider())
        report = agent.run_match(MatchRequest(resume_text=RESUME, jd_text=JD))
        with session_scope() as session:
            resume_count = session.query(ResumeChunk).filter(ResumeChunk.resume_id == report.resume.id).count()
            jd_count = session.query(JobDescriptionChunk).filter(JobDescriptionChunk.jd_id == report.jd.id).count()
        self.assertGreater(resume_count, 0)
        self.assertGreater(jd_count, 0)

    def test_rag_chunks_are_upserted_without_duplicate_growth(self) -> None:
        agent = JobAgent(llm_provider=OfflineProvider())
        first = agent.run_match(MatchRequest(resume_text=RESUME, jd_text=JD))
        second = agent.run_match(MatchRequest(resume_text=RESUME, jd_text=JD))
        with session_scope() as session:
            first_count = session.query(RagChunk).filter(RagChunk.owner_id == first.resume.id, RagChunk.source == "resume").count()
            second_count = session.query(RagChunk).filter(RagChunk.owner_id == second.resume.id, RagChunk.source == "resume").count()
            interview_count = session.query(RagChunk).filter(RagChunk.owner_id == "interview_bank_default").count()
        self.assertGreater(first_count, 0)
        self.assertEqual(first_count, second_count)
        self.assertGreaterEqual(interview_count, 6)

    def test_sqlite_repository_retriever_returns_traceable_evidence(self) -> None:
        agent = JobAgent(llm_provider=OfflineProvider())
        report = agent.run_match(MatchRequest(resume_text=RESUME, jd_text=JD))
        self.assertTrue(report.evidence)
        self.assertTrue(any(item.retrieval_method in {"hybrid-sqlite", "keyword"} for item in report.evidence))
        for item in report.evidence:
            self.assertTrue(item.source)
            self.assertTrue(item.text)
            self.assertGreaterEqual(item.score, 0)

    def test_embedding_fallback_count_is_reported(self) -> None:
        class BrokenProvider(EmbeddingProvider):
            name = "broken"

            def embed_texts(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("boom")

        from app.services.embeddings import FallbackEmbeddingProvider, OfflineEmbeddingProvider

        before = int(embedding_status()["embedding_fallback_count"])
        provider = FallbackEmbeddingProvider(BrokenProvider(), OfflineEmbeddingProvider())
        provider.embed_texts(["hello"])
        after = int(embedding_status()["embedding_fallback_count"])
        self.assertEqual(after, before + 1)

    def test_reindex_rag_chunks_updates_existing_embeddings(self) -> None:
        agent = JobAgent(llm_provider=OfflineProvider())
        report = agent.run_match(MatchRequest(resume_text=RESUME, jd_text=JD))
        result = agent.repository.reindex_rag_chunks()
        self.assertGreater(result["updated_chunks"], 0)
        self.assertIn("resume", result["source_counts"])
        with session_scope() as session:
            chunk = session.query(RagChunk).filter(RagChunk.owner_id == report.resume.id).first()
            self.assertIsNotNone(chunk)
            self.assertTrue(chunk.embedding)
            self.assertIn("embedding_provider", chunk.metadata_json)

    def test_embedding_status_reports_real_provider_success(self) -> None:
        from app.services.embeddings import OpenAICompatibleEmbeddingProvider

        with patch.object(OpenAICompatibleEmbeddingProvider, "embed_texts", return_value=[[1.0] * 64]):
            from app.config import get_settings
            from app.services.embeddings import get_embedding_provider

            get_settings.cache_clear()
            with patch.dict(
                os.environ,
                {
                    "EMBEDDING_PROVIDER": "openai_compatible",
                    "EMBEDDING_BASE_URL": "https://example.test/v1",
                    "EMBEDDING_API_KEY": "test-key",
                    "EMBEDDING_MODEL": "text-embedding-3-small",
                    "EMBEDDING_DIMENSION": "64",
                },
                clear=False,
            ):
                get_settings.cache_clear()
                provider = get_embedding_provider()
                provider.embed_texts(["hello"])
                status = embedding_status()
                self.assertEqual(status["embedding_provider"], "openai_compatible-embedding")
                self.assertEqual(status["embedding_model"], "text-embedding-3-small")
                self.assertEqual(status["embedding_dimension"], 64)
                self.assertEqual(status["embedding_real_enabled"], 1)
            get_settings.cache_clear()

    def test_health_response_does_not_expose_sensitive_values(self) -> None:
        response = TestClient(app).get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("vector_backend", payload)
        self.assertIn("embedding_provider", payload)
        self.assertIn("embedding_fallback_count", payload)
        self.assertIn("embedding_model", payload)
        self.assertIn("embedding_dimension", payload)
        self.assertIn("embedding_real_enabled", payload)
        self.assertIn("embedding_device", payload)
        self.assertIn("embedding_load_status", payload)
        self.assertIn("embedding_latency_ms", payload)
        serialized = str(payload)
        self.assertNotIn("OPENAI_API_KEY", serialized)
        self.assertNotIn("sk-", serialized)
        self.assertNotIn("DATABASE_URL", serialized)

    def test_evaluation_summary_shape(self) -> None:
        summary = JobAgent(llm_provider=OfflineProvider()).evaluation_summary()
        self.assertGreaterEqual(summary.case_count, 20)
        self.assertGreaterEqual(summary.suggestion_evidence_coverage, 0)
        self.assertGreaterEqual(summary.validation_pass_rate, 0)
        self.assertIn(summary.rag_backend, {"sqlite", "pgvector"})
        self.assertTrue(summary.embedding_provider)
        self.assertGreater(summary.embedding_dimension, 0)

    def test_warmup_embeddings_endpoint_keeps_fallback_safe(self) -> None:
        response = TestClient(app).post("/embeddings/warmup")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("embedding_load_status", payload)
        self.assertIn(payload["embedding_load_status"], {"not_loaded", "loading", "ready", "fallback", "error"})

    def test_interview_feedback(self) -> None:
        request = InterviewAnswerRequest(
            question="请介绍你的 RAG 项目",
            answer="背景是课程资料查询，我负责文档切分、向量检索和答案引用，最终提升了回答可追溯性。",
        )
        feedback = JobAgent(llm_provider=OfflineProvider()).grade_interview_answer(request.question, request.answer)
        self.assertGreaterEqual(feedback.score, 60)
        self.assertTrue(feedback.improvements)

    @unittest.skipUnless(os.getenv("PGVECTOR_TEST_DATABASE_URL"), "PGVECTOR_TEST_DATABASE_URL is not set")
    def test_pgvector_integration_placeholder(self) -> None:
        self.assertTrue(os.getenv("PGVECTOR_TEST_DATABASE_URL"))


if __name__ == "__main__":
    unittest.main()
