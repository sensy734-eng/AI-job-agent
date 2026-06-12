from __future__ import annotations

import re

from app.schemas import ParsedJobDescription, ParsedResume
from app.services.nlp import extract_skills, normalize_text, section_items, sentence_split, split_lines, top_keywords


def parse_resume(text: str) -> ParsedResume:
    cleaned = normalize_text(text)
    lines = split_lines(text)
    name = _guess_name(lines)
    education = _matching_lines(lines, ("大学", "本科", "硕士", "软件工程", "计算机", "GPA", "绩点"))
    skills = extract_skills(cleaned)
    projects = section_items(text, ("项目", "Project", "Projects"))
    experiences = section_items(text, ("实习", "经历", "Experience", "Work"))
    awards = section_items(text, ("获奖", "荣誉", "Award"))
    target_role = _guess_role(cleaned)
    return ParsedResume(
        name=name,
        target_role=target_role,
        education=education[:5],
        skills=skills,
        projects=projects or _project_like_sentences(text),
        experiences=experiences,
        awards=awards,
        raw_text=text,
    )


def parse_jd(text: str) -> ParsedJobDescription:
    cleaned = normalize_text(text)
    lines = split_lines(text)
    title = _guess_job_title(lines)
    company = _guess_company(lines)
    required_skills = extract_skills(cleaned)
    preferred_skills = _preferred_skills(text)
    responsibilities = section_items(text, ("职责", "工作内容", "Responsibilities", "What you will do"))
    requirements = section_items(text, ("要求", "任职资格", "Qualifications", "Requirements"))
    education = _matching_lines(lines, ("本科", "硕士", "博士", "计算机", "软件工程", "年级", "实习"))
    keywords = top_keywords(cleaned, 18)
    return ParsedJobDescription(
        title=title,
        company=company,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        responsibilities=responsibilities or sentence_split(text)[:5],
        education_requirements=education[:5],
        keywords=keywords,
        raw_text=text,
    )


def parse_document_bytes(filename: str, content: bytes) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "pdf":
        return _parse_pdf(content)
    if suffix in {"docx", "doc"}:
        return _parse_docx(content)
    return content.decode("utf-8", errors="ignore")


def _parse_pdf(content: bytes) -> str:
    try:
        import fitz

        doc = fitz.open(stream=content, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    except Exception as exc:
        raise ValueError("PDF parsing requires PyMuPDF and a valid PDF file") from exc


def _parse_docx(content: bytes) -> str:
    try:
        from docx import Document
        from io import BytesIO

        document = Document(BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception as exc:
        raise ValueError("DOCX parsing requires python-docx and a valid DOCX file") from exc


def _guess_name(lines: list[str]) -> str | None:
    for line in lines[:4]:
        if len(line) <= 12 and not re.search(r"(简历|电话|邮箱|求职|resume)", line, re.I):
            return line
    return None


def _guess_role(text: str) -> str | None:
    patterns = [
        r"(AI\s?应用开发|大模型应用开发|算法实习生|后端开发实习生|软件开发实习生|Python开发实习生)",
        r"求职意向[：:\s]+([^，。\n]{2,24})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1 if match.lastindex else 0)
    return None


def _guess_job_title(lines: list[str]) -> str:
    for line in lines[:8]:
        if re.search(r"(实习|工程师|开发|算法|AI|Agent|大模型|LLM)", line, re.I) and len(line) <= 40:
            return re.sub(r"岗位|职位|招聘|[:：]", "", line).strip() or "AI 应用开发实习生"
    return "AI 应用开发实习生"


def _guess_company(lines: list[str]) -> str | None:
    for line in lines[:5]:
        match = re.search(r"(公司|Company)[：:\s]+(.{2,30})", line, re.I)
        if match:
            return match.group(2).strip()
    return None


def _matching_lines(lines: list[str], hints: tuple[str, ...]) -> list[str]:
    return [line for line in lines if any(hint.lower() in line.lower() for hint in hints)][:8]


def _project_like_sentences(text: str) -> list[str]:
    return [item for item in sentence_split(text) if re.search(r"(项目|系统|平台|实现|开发|构建)", item)][:6]


def _preferred_skills(text: str) -> list[str]:
    preferred_lines = section_items(text, ("加分", "优先", "Preferred", "Nice to have"))
    return extract_skills("\n".join(preferred_lines))
