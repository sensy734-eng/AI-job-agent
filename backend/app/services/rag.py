from __future__ import annotations

from app.schemas import Evidence, EvidenceSource
from app.db.repository import JobRepository
from app.services.embeddings import EmbeddingProvider, cosine_vector, get_embedding_provider
from app.services.nlp import TextChunk, cosine_similarity, make_chunks


INTERVIEW_BANK = [
    "请介绍一个你做过的 AI 或 NLP 项目，说明目标、数据、模型/检索方案、评估指标和你的贡献。",
    "如果岗位要求 RAG，你会如何设计文档切分、向量检索、重排和回答引用机制？",
    "当大模型生成了与简历不一致的经历时，你会如何做输入约束和输出校验？",
    "请解释 FastAPI 服务如何组织路由、Pydantic schema、异常处理和接口文档。",
    "如果 JD 要求 Python、SQL 和向量数据库，你的项目经历如何证明这些能力？",
    "讲一次你根据反馈迭代产品或模型效果的经历。",
]


class SimpleRetriever:
    def __init__(
        self,
        resume_text: str,
        jd_text: str,
        feedback_texts: list[str] | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        chunks: list[TextChunk] = []
        chunks.extend(make_chunks("resume", "简历证据", resume_text))
        chunks.extend(make_chunks("jd", "JD 证据", jd_text))
        chunks.extend(TextChunk("interview_bank", "面试题库", item) for item in INTERVIEW_BANK)
        for feedback in feedback_texts or []:
            chunks.extend(make_chunks("feedback", "用户反馈", feedback))
        self.chunks = chunks
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.chunk_embeddings = self.embedding_provider.embed_texts([chunk.text for chunk in self.chunks])
        self.mode = f"hybrid-memory:{self.embedding_provider.name}"

    def search(self, query: str, limit: int = 8) -> list[Evidence]:
        query_embedding = self.embedding_provider.embed_texts([query])[0]
        scored = sorted(
            (
                self._score_chunk(query, query_embedding, chunk, index)
                for index, chunk in enumerate(self.chunks)
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        results: list[Evidence] = []
        for score, chunk, method in scored[:limit]:
            if score <= 0:
                continue
            results.append(
                Evidence(
                    source=EvidenceSource(chunk.source),
                    title=chunk.title,
                    text=chunk.text,
                    score=round(min(score, 1.0), 3),
                    retrieval_method=method,
                )
            )
        if not results:
            for chunk in self.chunks[:limit]:
                results.append(
                    Evidence(
                        source=EvidenceSource(chunk.source),
                        title=chunk.title,
                        text=chunk.text,
                        score=0.1,
                        retrieval_method="fallback",
                    )
                )
        return results

    def _score_chunk(self, query: str, query_embedding: list[float], chunk: TextChunk, index: int) -> tuple[float, TextChunk, str]:
        keyword_score = cosine_similarity(query, chunk.text)
        vector_score = max(0.0, cosine_vector(query_embedding, self.chunk_embeddings[index]))
        score = keyword_score * 0.45 + vector_score * 0.55
        if keyword_score > vector_score + 0.1:
            method = "keyword"
        elif vector_score > keyword_score + 0.1:
            method = "vector"
        else:
            method = "hybrid"
        return score, chunk, method


class RepositoryRetriever:
    def __init__(
        self,
        repository: JobRepository,
        owner_ids: list[str],
        fallback: SimpleRetriever,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.repository = repository
        self.owner_ids = owner_ids
        self.fallback = fallback
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.mode = f"repository:{self.embedding_provider.name}"

    def search(self, query: str, limit: int = 10) -> list[Evidence]:
        query_embedding = self.embedding_provider.embed_texts([query])[0]
        results = self.repository.search_rag_chunks(query, query_embedding, self.owner_ids, limit=limit)
        if results:
            methods = {item.retrieval_method for item in results}
            if any("pgvector" in method for method in methods):
                self.mode = f"hybrid-pgvector:{self.embedding_provider.name}"
            else:
                self.mode = f"hybrid-sqlite:{self.embedding_provider.name}"
            return results
        fallback_results = self.fallback.search(query, limit=limit)
        self.mode = f"{self.fallback.mode}:fallback"
        return fallback_results
