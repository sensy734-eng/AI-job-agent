from __future__ import annotations

import hashlib
from contextlib import contextmanager
from time import perf_counter
from typing import Iterator

from sqlalchemy import bindparam, desc, text
from sqlalchemy.orm import Session

from app.db.models import (
    FeedbackEventRecord,
    JobDescription,
    JobDescriptionChunk,
    MatchReportRecord,
    RagChunk,
    Resume,
    ResumeChunk,
    ResumeVersion as ResumeVersionRecord,
)
from app.db.session import SessionLocal, active_vector_backend, init_db, is_pgvector_enabled
from app.schemas import Evidence, EvidenceSource, FeedbackEvent, MatchReport, ReportSummary, ResumeVersion, RewriteSuggestion, new_id
from app.services.embeddings import EmbeddingProvider, cosine_vector, get_embedding_provider
from app.services.nlp import TextChunk, cosine_similarity, make_chunks


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class JobRepository:
    def __init__(self) -> None:
        init_db()

    def save_report(self, report: MatchReport) -> None:
        payload = report.model_dump(mode="json")
        with session_scope() as session:
            session.merge(
                Resume(
                    id=report.resume.id,
                    raw_text=report.resume.raw_text,
                    parsed_json=report.resume.model_dump(mode="json"),
                )
            )
            session.merge(
                JobDescription(
                    id=report.jd.id,
                    raw_text=report.jd.raw_text,
                    parsed_json=report.jd.model_dump(mode="json"),
                )
            )
            session.merge(
                MatchReportRecord(
                    id=report.id,
                    resume_id=report.resume.id,
                    jd_id=report.jd.id,
                    scores_json=report.scores.model_dump(mode="json"),
                    report_json=payload,
                )
            )
            self._replace_chunks(session, report)
            if report.rewrite_suggestions:
                suggestions = report.rewrite_suggestions
                session.merge(
                    ResumeVersionRecord(
                        id=new_id("version"),
                        resume_id=report.resume.id,
                        title=f"{report.jd.title} 自动改写",
                        content="\n\n".join(item.after for item in suggestions),
                        suggestions_json=[item.model_dump(mode="json") for item in suggestions],
                    )
                )

    def get_report(self, report_id: str) -> MatchReport | None:
        with session_scope() as session:
            record = session.get(MatchReportRecord, report_id)
            if record is None:
                return None
            return MatchReport.model_validate(record.report_json)

    def list_reports(self, limit: int = 20) -> list[ReportSummary]:
        with session_scope() as session:
            records = (
                session.query(MatchReportRecord)
                .order_by(desc(MatchReportRecord.created_at))
                .limit(limit)
                .all()
            )
            summaries: list[ReportSummary] = []
            for record in records:
                report = MatchReport.model_validate(record.report_json)
                summaries.append(
                    ReportSummary(
                        id=report.id,
                        created_at=report.created_at,
                        jd_title=report.jd.title,
                        overall_score=report.scores.overall,
                        top_gap=report.gaps[0].title if report.gaps else None,
                        model_provider=report.model_provider,
                        rag_mode=report.rag_mode,
                    )
                )
            return summaries

    def save_feedback(self, event: FeedbackEvent) -> None:
        with session_scope() as session:
            session.merge(
                FeedbackEventRecord(
                    id=event.id,
                    target_id=event.target_id,
                    action=event.action,
                    comment=event.comment,
                    created_at=event.created_at,
                )
            )
            if event.comment:
                embedding_provider = get_embedding_provider()
                chunks = make_chunks("feedback", "用户反馈", event.comment)
                embeddings = embedding_provider.embed_texts([chunk.text for chunk in chunks])
                self._upsert_rag_chunks(session, event.id, chunks, embeddings)

    def create_resume_version(
        self,
        resume_id: str,
        title: str,
        content: str,
        suggestions: list[RewriteSuggestion],
    ) -> ResumeVersion:
        version = ResumeVersion(
            resume_id=resume_id,
            title=title,
            content=content,
            suggestions=suggestions,
            diff=build_suggestion_diff(suggestions),
        )
        with session_scope() as session:
            session.merge(
                ResumeVersionRecord(
                    id=version.id,
                    resume_id=version.resume_id,
                    title=version.title,
                    content=version.content,
                    suggestions_json=[item.model_dump(mode="json") for item in suggestions],
                    created_at=version.created_at,
                )
            )
        return version

    def list_resume_versions(self, resume_id: str) -> list[ResumeVersion]:
        with session_scope() as session:
            records = (
                session.query(ResumeVersionRecord)
                .filter(ResumeVersionRecord.resume_id == resume_id)
                .order_by(desc(ResumeVersionRecord.created_at))
                .all()
            )
            versions: list[ResumeVersion] = []
            for record in records:
                suggestions = [RewriteSuggestion.model_validate(item) for item in (record.suggestions_json or [])]
                versions.append(
                    ResumeVersion(
                        id=record.id,
                        resume_id=record.resume_id,
                        title=record.title,
                        content=record.content,
                        suggestions=suggestions,
                        diff=build_suggestion_diff(suggestions),
                        created_at=record.created_at,
                    )
                )
            return versions

    def get_resume_version(self, version_id: str) -> ResumeVersion | None:
        with session_scope() as session:
            record = session.get(ResumeVersionRecord, version_id)
            if record is None:
                return None
            suggestions = [RewriteSuggestion.model_validate(item) for item in (record.suggestions_json or [])]
            return ResumeVersion(
                id=record.id,
                resume_id=record.resume_id,
                title=record.title,
                content=record.content,
                suggestions=suggestions,
                diff=build_suggestion_diff(suggestions),
                created_at=record.created_at,
            )

    def feedback_texts(self, limit: int = 30) -> list[str]:
        with session_scope() as session:
            records = (
                session.query(FeedbackEventRecord)
                .filter(FeedbackEventRecord.comment.isnot(None))
                .order_by(desc(FeedbackEventRecord.created_at))
                .limit(limit)
                .all()
            )
            return [record.comment for record in records if record.comment]

    def upsert_text_chunks(
        self,
        owner_id: str,
        source: str,
        title: str,
        raw_text: str,
        embeddings: list[list[float]],
    ) -> int:
        chunks = make_chunks(source, title, raw_text)
        with session_scope() as session:
            self._upsert_rag_chunks(session, owner_id, chunks, embeddings[: len(chunks)])
        return len(chunks)

    def upsert_static_chunks(
        self,
        owner_id: str,
        source: str,
        title: str,
        texts: list[str],
        embedding_provider: EmbeddingProvider,
    ) -> int:
        chunks = [TextChunk(source=source, title=title, text=text) for text in texts if text.strip()]
        embeddings = embedding_provider.embed_texts([chunk.text for chunk in chunks]) if chunks else []
        with session_scope() as session:
            self._upsert_rag_chunks(session, owner_id, chunks, embeddings)
        return len(chunks)

    def upsert_feedback_contexts(
        self,
        feedback_texts: list[str],
        embedding_provider: EmbeddingProvider,
    ) -> list[str]:
        owner_ids: list[str] = []
        for feedback in feedback_texts:
            if not feedback.strip():
                continue
            owner_id = f"feedback_{hashlib.sha1(feedback.encode('utf-8')).hexdigest()[:12]}"
            chunks = make_chunks("feedback", "用户反馈", feedback)
            embeddings = embedding_provider.embed_texts([chunk.text for chunk in chunks]) if chunks else []
            with session_scope() as session:
                self._upsert_rag_chunks(session, owner_id, chunks, embeddings)
            owner_ids.append(owner_id)
        return owner_ids

    def search_rag_chunks(
        self,
        query: str,
        query_embedding: list[float],
        owner_ids: list[str],
        limit: int = 10,
    ) -> list[Evidence]:
        with session_scope() as session:
            vector_rows = self._vector_candidates(session, query_embedding, owner_ids, top_k=20)
            keyword_rows = self._keyword_candidates(session, query, owner_ids, top_k=20)
        merged: dict[str, dict] = {}
        for row in vector_rows + keyword_rows:
            existing = merged.get(row["id"])
            if existing is None or row["score"] > existing["score"]:
                merged[row["id"]] = row
            elif existing is not None and row["method"] not in existing["method"]:
                existing["method"] = "hybrid-pgvector" if active_vector_backend() == "pgvector" else "hybrid-sqlite"
                existing["score"] = max(existing["score"], row["score"])
        reranked = sorted(
            merged.values(),
            key=lambda item: (
                item["score"] * 0.7 + cosine_similarity(query, item["text"]) * 0.3,
                item["source"] in {"resume", "jd"},
            ),
            reverse=True,
        )
        evidence: list[Evidence] = []
        for row in reranked[:limit]:
            evidence.append(
                Evidence(
                    id=row["id"],
                    source=EvidenceSource(row["source"]),
                    title=row["title"],
                    text=row["text"],
                    score=round(max(0.0, min(row["score"], 1.0)), 3),
                    retrieval_method=row["method"],
                )
            )
        return evidence

    def rag_chunk_count(self, owner_id: str, source: str | None = None) -> int:
        with session_scope() as session:
            query = session.query(RagChunk).filter(RagChunk.owner_id == owner_id)
            if source:
                query = query.filter(RagChunk.source == source)
            return query.count()

    def reindex_rag_chunks(self, embedding_provider: EmbeddingProvider | None = None, batch_size: int = 32) -> dict:
        provider = embedding_provider or get_embedding_provider()
        start_time = perf_counter()
        updated = 0
        failed = 0
        source_counts: dict[str, int] = {}
        with session_scope() as session:
            records = session.query(RagChunk).order_by(RagChunk.created_at.asc()).all()
            for start in range(0, len(records), batch_size):
                batch = records[start : start + batch_size]
                try:
                    embeddings = provider.embed_texts([record.text for record in batch])
                except Exception:
                    failed += len(batch)
                    continue
                for record, embedding in zip(batch, embeddings):
                    record.embedding = embedding
                    metadata = dict(record.metadata_json or {})
                    metadata["embedding_provider"] = provider.name
                    metadata["embedding_model"] = getattr(provider, "model", "unknown")
                    record.metadata_json = metadata
                    updated += 1
                    source_counts[record.source] = source_counts.get(record.source, 0) + 1
        return {
            "updated_chunks": updated,
            "source_counts": source_counts,
            "embedding_provider": provider.name,
            "embedding_model": getattr(provider, "model", "unknown"),
            "duration_ms": round((perf_counter() - start_time) * 1000),
            "failed_chunks": failed,
        }

    def _replace_chunks(self, session: Session, report: MatchReport) -> None:
        embedding_provider = get_embedding_provider()
        resume_chunks = make_chunks("resume", "简历证据", report.resume.raw_text)
        jd_chunks = make_chunks("jd", "JD 证据", report.jd.raw_text)
        resume_embeddings = embedding_provider.embed_texts([chunk.text for chunk in resume_chunks])
        jd_embeddings = embedding_provider.embed_texts([chunk.text for chunk in jd_chunks])

        session.query(ResumeChunk).filter(ResumeChunk.resume_id == report.resume.id).delete()
        session.query(JobDescriptionChunk).filter(JobDescriptionChunk.jd_id == report.jd.id).delete()
        for chunk, embedding in zip(resume_chunks, resume_embeddings):
            session.add(ResumeChunk(resume_id=report.resume.id, text=chunk.text, embedding=embedding))
        for chunk, embedding in zip(jd_chunks, jd_embeddings):
            session.add(JobDescriptionChunk(jd_id=report.jd.id, text=chunk.text, embedding=embedding))
        self._upsert_rag_chunks(session, report.resume.id, resume_chunks, resume_embeddings)
        self._upsert_rag_chunks(session, report.jd.id, jd_chunks, jd_embeddings)

    def _upsert_rag_chunks(
        self,
        session: Session,
        owner_id: str,
        chunks: list[TextChunk],
        embeddings: list[list[float]],
    ) -> None:
        if not chunks:
            return
        source = chunks[0].source
        session.query(RagChunk).filter(RagChunk.owner_id == owner_id, RagChunk.source == source).delete()
        if is_pgvector_enabled():
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                session.execute(
                    text(
                        "INSERT INTO rag_chunks "
                        "(id, owner_id, source, title, text, embedding, metadata_json, created_at) "
                        "VALUES (:id, :owner_id, :source, :title, :text_value, :embedding, :metadata_json, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "id": new_id("chunk"),
                        "owner_id": owner_id,
                        "source": chunk.source,
                        "title": chunk.title,
                        "text_value": chunk.text,
                        "embedding": _vector_literal(embedding),
                        "metadata_json": {"chunk_index": index},
                    },
                )
            return
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            session.add(
                RagChunk(
                    id=new_id("chunk"),
                    owner_id=owner_id,
                    source=chunk.source,
                    title=chunk.title,
                    text=chunk.text,
                    embedding=embedding,
                    metadata_json={"chunk_index": index},
                )
            )

    def _vector_candidates(
        self,
        session: Session,
        query_embedding: list[float],
        owner_ids: list[str],
        top_k: int,
    ) -> list[dict]:
        if is_pgvector_enabled():
            statement = (
                text(
                    "SELECT id, source, title, text, "
                    "GREATEST(0, 1 - (embedding <=> :embedding)) AS score "
                    "FROM rag_chunks "
                    "WHERE owner_id IN :owner_ids AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> :embedding "
                    "LIMIT :limit"
                )
                .bindparams(bindparam("owner_ids", expanding=True))
            )
            rows = session.execute(
                statement,
                {"embedding": _vector_literal(query_embedding), "owner_ids": owner_ids, "limit": top_k},
            ).mappings()
            return [
                {
                    "id": row["id"],
                    "source": row["source"],
                    "title": row["title"],
                    "text": row["text"],
                    "score": float(row["score"] or 0),
                    "method": "vector-pgvector",
                }
                for row in rows
            ]
        records = (
            session.query(RagChunk)
            .filter(RagChunk.owner_id.in_(owner_ids), RagChunk.embedding.isnot(None))
            .all()
        )
        scored = sorted(
            (
                {
                    "id": record.id,
                    "source": record.source,
                    "title": record.title,
                    "text": record.text,
                    "score": max(0.0, cosine_vector(query_embedding, record.embedding or [])),
                    "method": "hybrid-sqlite",
                }
                for record in records
            ),
            key=lambda item: item["score"],
            reverse=True,
        )
        return scored[:top_k]

    def _keyword_candidates(self, session: Session, query: str, owner_ids: list[str], top_k: int) -> list[dict]:
        if is_pgvector_enabled():
            statement = (
                text("SELECT id, source, title, text FROM rag_chunks WHERE owner_id IN :owner_ids")
                .bindparams(bindparam("owner_ids", expanding=True))
            )
            rows = session.execute(statement, {"owner_ids": owner_ids}).mappings()
            scored = sorted(
                (
                    {
                        "id": row["id"],
                        "source": row["source"],
                        "title": row["title"],
                        "text": row["text"],
                        "score": cosine_similarity(query, row["text"]),
                        "method": "keyword",
                    }
                    for row in rows
                ),
                key=lambda item: item["score"],
                reverse=True,
            )
            return [item for item in scored if item["score"] > 0][:top_k]
        records = session.query(RagChunk).filter(RagChunk.owner_id.in_(owner_ids)).all()
        scored = sorted(
            (
                {
                    "id": record.id,
                    "source": record.source,
                    "title": record.title,
                    "text": record.text,
                    "score": cosine_similarity(query, record.text),
                    "method": "keyword",
                }
                for record in records
            ),
            key=lambda item: item["score"],
            reverse=True,
        )
        return [item for item in scored if item["score"] > 0][:top_k]


def build_suggestion_diff(suggestions: list[RewriteSuggestion]) -> list[str]:
    diff: list[str] = []
    for item in suggestions:
        diff.append(f"@@ {item.section}")
        if item.before:
            diff.append(f"- {item.before}")
        diff.append(f"+ {item.after}")
        if item.validation_status != "passed":
            diff.append(f"! {item.validation_status}: {'; '.join(item.validation_notes) or '需要人工复核'}")
    return diff


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in values) + "]"


def get_repository() -> JobRepository:
    return JobRepository()
