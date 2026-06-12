from __future__ import annotations

from app.schemas import Evidence, ParsedJobDescription, ParsedResume, RewriteSuggestion


def build_rewrite_suggestions(
    resume: ParsedResume,
    jd: ParsedJobDescription,
    evidence: list[Evidence],
    limit: int = 5,
) -> list[RewriteSuggestion]:
    evidence_ids = [item.id for item in evidence[:3]]
    suggestions: list[RewriteSuggestion] = []
    target_skills = jd.required_skills[:4] or jd.keywords[:4]

    if resume.projects:
        project = resume.projects[0]
        after = _project_after(project, target_skills)
        suggestions.append(
            RewriteSuggestion(
                section="项目经历",
                before=project,
                after=after,
                rationale="把项目描述改成 STAR 结构，并显式对应 JD 技能词；只重写表达，不新增不存在的经历。",
                evidence_ids=evidence_ids,
            )
        )

    skill_before = "、".join(resume.skills) if resume.skills else "技能描述较分散，未形成岗位关键词区。"
    skill_after = "技术栈：" + "、".join(dict.fromkeys(resume.skills + target_skills).keys())
    suggestions.append(
        RewriteSuggestion(
            section="技能摘要",
            before=skill_before,
            after=skill_after,
            rationale="把简历已有技能和 JD 高频技能放在顶部，提高筛选阶段可读性。",
            evidence_ids=evidence_ids,
        )
    )

    headline = resume.target_role or "软件工程专业大三学生"
    suggestions.append(
        RewriteSuggestion(
            section="个人摘要",
            before=headline,
            after=f"{headline}，关注 AI 应用开发、RAG 检索与后端工程，能够基于岗位 JD 快速拆解需求并交付可演示原型。",
            rationale="用一句话说明求职方向、技术主题和工程交付能力，适合 AI 实习岗位开头摘要。",
            evidence_ids=evidence_ids,
        )
    )

    if jd.responsibilities:
        responsibility = jd.responsibilities[0]
        suggestions.append(
            RewriteSuggestion(
                section="岗位定制",
                before="未针对该 JD 单独突出职责匹配点。",
                after=f"针对 JD 中“{responsibility[:60]}”的要求，可在项目描述中补充对应模块、接口、评测指标或迭代结果。",
                rationale="把 JD 职责转成简历中的证据点，提升定制化程度。",
                evidence_ids=evidence_ids,
            )
        )

    return suggestions[:limit]


def _project_after(project: str, target_skills: list[str]) -> str:
    skill_phrase = "、".join(target_skills[:3]) if target_skills else "项目相关技术"
    clean = project.strip(" -•")
    return (
        f"{clean}；围绕业务目标拆解需求，使用 {skill_phrase} 完成核心模块，"
        "并通过测试用例、用户反馈或已有项目结果验证效果。"
    )
