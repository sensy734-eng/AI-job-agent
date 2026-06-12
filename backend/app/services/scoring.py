from __future__ import annotations

from app.schemas import GapItem, ParsedJobDescription, ParsedResume, ScoreBreakdown
from app.services.nlp import clamp_score, cosine_similarity, jaccard_similarity


WEIGHTS = {
    "skill_match": 0.35,
    "project_experience": 0.30,
    "keyword_coverage": 0.15,
    "education_fit": 0.10,
    "risk_control": 0.10,
}


def score_match(resume: ParsedResume, jd: ParsedJobDescription) -> ScoreBreakdown:
    skill_score = _skill_score(resume.skills, jd.required_skills + jd.preferred_skills)
    project_score = _project_score(resume, jd)
    keyword_score = clamp_score(jaccard_similarity(jd.keywords, resume.skills + resume.projects + resume.experiences) * 140)
    education_score = _education_score(resume, jd)
    risk_score = _risk_score(resume, jd)
    calibrated = _calibrate_mid_match(resume, jd, skill_score, project_score, keyword_score)
    overall = clamp_score(
        skill_score * WEIGHTS["skill_match"]
        + project_score * WEIGHTS["project_experience"]
        + keyword_score * WEIGHTS["keyword_coverage"]
        + education_score * WEIGHTS["education_fit"]
        + risk_score * WEIGHTS["risk_control"]
        + calibrated
    )
    return ScoreBreakdown(
        skill_match=skill_score,
        project_experience=project_score,
        keyword_coverage=keyword_score,
        education_fit=education_score,
        risk_control=risk_score,
        overall=overall,
    )


def build_gaps(resume: ParsedResume, jd: ParsedJobDescription) -> list[GapItem]:
    resume_skill_set = {skill.lower() for skill in resume.skills}
    missing = [skill for skill in jd.required_skills if skill.lower() not in resume_skill_set]
    gaps: list[GapItem] = []
    for skill in missing[:4]:
        gaps.append(
            GapItem(
                type="skill",
                title=f"补强 {skill} 证据",
                detail=f"JD 明确出现 {skill}，但简历中没有稳定证据。建议补充课程、项目模块或实践结果。",
                priority="high",
            )
        )
    if _project_score(resume, jd) < 60:
        gaps.append(
            GapItem(
                type="project",
                title="项目经历与岗位职责关联不足",
                detail="简历项目需要更清楚说明场景、技术方案、个人贡献和可量化结果。",
                priority="high",
            )
        )
    if _education_score(resume, jd) < 70:
        gaps.append(
            GapItem(
                type="education",
                title="学历/年级要求表达不够明显",
                detail="建议在简历顶部明确年级、专业、可实习周期和到岗时间。",
                priority="medium",
            )
        )
    if not gaps:
        gaps.append(
            GapItem(
                type="risk",
                title="避免泛泛描述",
                detail="当前匹配度较好，主要风险是项目描述过于宽泛。建议把技术选择和效果指标写得更具体。",
                priority="low",
            )
        )
    return gaps


def summarize_strengths(resume: ParsedResume, jd: ParsedJobDescription) -> list[str]:
    overlaps = sorted({skill for skill in resume.skills if skill in jd.required_skills + jd.preferred_skills})
    strengths: list[str] = []
    if overlaps:
        strengths.append(f"技能关键词有交集：{', '.join(overlaps[:5])}。")
    if resume.projects:
        strengths.append("具备可包装为岗位相关证据的项目经历。")
    if any("软件工程" in item or "计算机" in item for item in resume.education):
        strengths.append("专业背景与 AI/软件开发实习岗位方向一致。")
    if not strengths:
        strengths.append("简历已有基础经历，可通过结构化表达提升与 JD 的关联度。")
    return strengths[:4]


def _skill_score(resume_skills: list[str], jd_skills: list[str]) -> int:
    if not jd_skills:
        return 70 if resume_skills else 40
    resume_set = {skill.lower() for skill in resume_skills}
    required_set = {skill.lower() for skill in jd_skills}
    coverage = len(resume_set & required_set) / len(required_set)
    partial = _partial_skill_overlap(resume_set, required_set)
    return clamp_score(coverage * 100 + partial * 12)


def _project_score(resume: ParsedResume, jd: ParsedJobDescription) -> int:
    project_text = "\n".join(resume.projects + resume.experiences + resume.raw_text.splitlines()[:20])
    jd_text = "\n".join(jd.responsibilities + jd.required_skills + jd.keywords)
    base = cosine_similarity(project_text, jd_text)
    bonus = 0.1 if resume.projects else 0
    return clamp_score((base + bonus) * 100)


def _education_score(resume: ParsedResume, jd: ParsedJobDescription) -> int:
    if not jd.education_requirements:
        return 80
    resume_text = " ".join(resume.education + [resume.raw_text])
    jd_text = " ".join(jd.education_requirements)
    if any(keyword in resume_text for keyword in ("本科", "硕士", "博士", "软件工程", "计算机", "大三", "大四")):
        return 85
    if cosine_similarity(resume_text, jd_text) > 0.1:
        return 75
    return 45


def _risk_score(resume: ParsedResume, jd: ParsedJobDescription) -> int:
    missing_skills = {skill.lower() for skill in jd.required_skills} - {skill.lower() for skill in resume.skills}
    risk = len(missing_skills) * 12
    if len(resume.raw_text) < 300:
        risk += 15
    if not resume.projects:
        risk += 20
    return clamp_score(100 - risk)


def _partial_skill_overlap(resume_set: set[str], required_set: set[str]) -> int:
    related_groups = [
        {"python", "java", "javascript", "react", "fastapi", "api"},
        {"sql", "postgresql", "mysql", "sqlite", "vector db"},
        {"rag", "llm", "nlp", "machine learning", "deep learning"},
        {"docker", "git", "api"},
    ]
    partial = 0
    for group in related_groups:
        if resume_set & group and required_set & group:
            partial += 1
    return partial


def _calibrate_mid_match(
    resume: ParsedResume,
    jd: ParsedJobDescription,
    skill_score: int,
    project_score: int,
    keyword_score: int,
) -> int:
    has_major = any(keyword in resume.raw_text for keyword in ("软件工程", "计算机", "人工智能", "本科", "大三"))
    has_project = bool(resume.projects)
    jd_ai = any(keyword in jd.raw_text.lower() for keyword in ("ai", "rag", "llm", "大模型", "agent", "embedding"))
    resume_engineering = any(keyword in resume.raw_text.lower() for keyword in ("api", "后端", "接口", "项目", "系统", "python", "java", "react", "sql"))
    if jd_ai and has_major and has_project and resume_engineering and max(skill_score, project_score, keyword_score) >= 25:
        return 12
    if has_major and has_project and max(skill_score, project_score, keyword_score) >= 40:
        return 8
    return 0
