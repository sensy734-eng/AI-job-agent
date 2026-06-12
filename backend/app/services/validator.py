from __future__ import annotations

import re

from app.schemas import Evidence, ParsedResume, RewriteSuggestion
from app.services.nlp import extract_skills


COMPANY_HINTS = ("腾讯", "阿里", "字节", "百度", "美团", "京东", "华为", "微软", "Google", "Amazon")


def validate_rewrite_suggestions(
    suggestions: list[RewriteSuggestion],
    resume: ParsedResume,
    evidence: list[Evidence],
) -> list[RewriteSuggestion]:
    evidence_ids = {item.id for item in evidence}
    resume_text = resume.raw_text
    resume_skills = {item.lower() for item in extract_skills(resume_text)}
    validated: list[RewriteSuggestion] = []
    for suggestion in suggestions:
        notes: list[str] = []
        status = "passed"
        if not suggestion.evidence_ids:
            notes.append("缺少证据引用，已标记为需要复核。")
            status = "warning"
            suggestion.evidence_ids = [item.id for item in evidence[:2]]
        elif any(item not in evidence_ids for item in suggestion.evidence_ids):
            notes.append("包含不存在的 evidence_id，已替换为最高相关证据。")
            status = "warning"
            suggestion.evidence_ids = [item.id for item in evidence[:2]]

        for company in COMPANY_HINTS:
            if company in suggestion.after and company not in resume_text:
                notes.append(f"疑似引入简历未提供的公司/组织：{company}。")
                status = "failed"

        for number in re.findall(r"\d+(?:\.\d+)?%", suggestion.after):
            if number not in resume_text:
                notes.append(f"疑似引入简历未提供的百分比指标：{number}。")
                status = "failed"

        for number in re.findall(r"\b\d{4,}\b", suggestion.after):
            if number not in resume_text:
                notes.append(f"疑似引入简历未提供的大数值指标：{number}。")
                status = "warning" if status == "passed" else status

        after_skills = {item.lower() for item in extract_skills(suggestion.after)}
        new_skills = sorted(after_skills - resume_skills)
        if new_skills and suggestion.section in {"技能摘要", "个人摘要"}:
            notes.append(f"包含 JD 相关但简历证据较弱的技能词：{', '.join(new_skills[:4])}。")
            status = "warning" if status == "passed" else status

        suggestion.validation_status = status
        suggestion.validation_notes = notes
        validated.append(suggestion)
    return validated


def safe_suggestions(suggestions: list[RewriteSuggestion]) -> list[RewriteSuggestion]:
    return [item for item in suggestions if item.validation_status != "failed"] or suggestions
