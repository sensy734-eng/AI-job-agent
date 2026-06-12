from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass


SKILL_ALIASES: dict[str, set[str]] = {
    "Python": {"python", "py"},
    "Java": {"java", "spring", "spring boot"},
    "JavaScript": {"javascript", "js", "typescript", "ts", "node", "node.js"},
    "React": {"react", "next.js", "nextjs"},
    "FastAPI": {"fastapi"},
    "SQL": {"sql", "mysql", "postgresql", "postgres", "sqlite"},
    "RAG": {"rag", "retrieval augmented generation", "检索增强"},
    "LLM": {"llm", "大模型", "prompt", "提示词", "openai", "langchain", "langgraph"},
    "NLP": {"nlp", "自然语言处理", "文本分类", "信息抽取"},
    "Machine Learning": {"machine learning", "机器学习", "sklearn", "scikit-learn"},
    "Deep Learning": {"deep learning", "深度学习", "pytorch", "tensorflow"},
    "Vector DB": {"vector", "embedding", "向量", "pgvector", "milvus", "faiss"},
    "Docker": {"docker", "容器"},
    "Git": {"git", "github"},
    "Data Analysis": {"pandas", "numpy", "数据分析", "可视化"},
    "API": {"api", "restful", "接口"},
}

STOP_WORDS = {
    "and",
    "or",
    "the",
    "with",
    "for",
    "to",
    "of",
    "in",
    "on",
    "a",
    "an",
    "is",
    "are",
    "岗位",
    "负责",
    "熟悉",
    "掌握",
    "使用",
    "具备",
    "能力",
    "相关",
    "项目",
    "经验",
}


@dataclass(frozen=True)
class TextChunk:
    source: str
    title: str
    text: str


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def split_lines(text: str) -> list[str]:
    lines = [normalize_text(line) for line in re.split(r"[\n\r]+", text)]
    return [line for line in lines if line]


def sentence_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？.!?])\s+|[；;]\s*", normalize_text(text))
    return [part.strip(" -•\t") for part in parts if part.strip(" -•\t")]


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for canonical, aliases in SKILL_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            found.append(canonical)
    return found


def tokenize(text: str) -> list[str]:
    english = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]{1,}", text.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    tokens = english + chinese
    return [token for token in tokens if token not in STOP_WORDS and len(token) > 1]


def top_keywords(text: str, limit: int = 16) -> list[str]:
    skills = extract_skills(text)
    counts = Counter(tokenize(text))
    ranked = [word for word, _ in counts.most_common(limit * 2)]
    merged: list[str] = []
    for item in skills + ranked:
        display = item.strip()
        if display and display.lower() not in {x.lower() for x in merged}:
            merged.append(display)
        if len(merged) >= limit:
            break
    return merged


def jaccard_similarity(left: list[str], right: list[str]) -> float:
    left_set = {item.lower() for item in left}
    right_set = {item.lower() for item in right}
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def cosine_similarity(left: str, right: str) -> float:
    left_counts = Counter(tokenize(left))
    right_counts = Counter(tokenize(right))
    if not left_counts or not right_counts:
        return 0.0
    overlap = set(left_counts) & set(right_counts)
    numerator = sum(left_counts[token] * right_counts[token] for token in overlap)
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


def make_chunks(source: str, title: str, text: str) -> list[TextChunk]:
    lines = split_lines(text)
    chunks: list[TextChunk] = []
    current_title = title
    for line in lines:
        if len(line) <= 18 and re.search(r"(教育|技能|项目|经历|经验|职责|要求|资格|亮点|获奖)", line):
            current_title = line.strip("：:")
            continue
        if len(line) > 8:
            chunks.append(TextChunk(source=source, title=current_title, text=line))
    if not chunks:
        chunks = [TextChunk(source=source, title=title, text=item) for item in sentence_split(text)[:12]]
    return chunks


def section_items(text: str, labels: tuple[str, ...]) -> list[str]:
    lines = split_lines(text)
    items: list[str] = []
    capture = False
    for line in lines:
        lower = line.lower()
        if any(label.lower() in lower for label in labels):
            capture = True
            tail = re.sub(r"^.*?[：:]", "", line).strip()
            if tail and tail != line:
                items.append(tail)
            continue
        if capture:
            if re.search(r"(教育|技能|项目|经历|经验|获奖|自我评价|职责|要求|资格)", line) and len(line) < 24:
                break
            items.append(line.strip("-• "))
    return [item for item in items if len(item) > 3][:8]
