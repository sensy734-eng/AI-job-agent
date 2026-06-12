from __future__ import annotations

from app.schemas import InterviewFeedback, InterviewQuestion, ParsedJobDescription, ParsedResume


def build_interview_questions(
    resume: ParsedResume,
    jd: ParsedJobDescription,
    evidence_ids: list[str],
    count: int = 6,
) -> list[InterviewQuestion]:
    skills = jd.required_skills[:4] or resume.skills[:4] or ["Python", "RAG", "API"]
    questions = [
        InterviewQuestion(
            category="resume",
            question="请用 1 分钟介绍你的简历，并说明为什么适合这个岗位。",
            expected_points=["求职方向", "项目证据", "与 JD 的技能交集"],
            evidence_ids=evidence_ids,
        ),
        InterviewQuestion(
            category="project",
            question="选择一个最贴近 JD 的项目，讲清楚背景、你的职责、技术方案和结果。",
            expected_points=["项目目标", "个人贡献", "技术取舍", "量化结果"],
            evidence_ids=evidence_ids,
        ),
        InterviewQuestion(
            category="technical",
            question=f"如果让你为该岗位设计一个 RAG 功能，你会如何做文档切分、检索和回答引用？",
            expected_points=["chunk 策略", "向量检索", "证据引用", "幻觉控制"],
            evidence_ids=evidence_ids,
        ),
        InterviewQuestion(
            category="technical",
            question=f"请说明你对 {skills[0]} 的掌握程度，并举一个项目中的实际使用场景。",
            expected_points=["技术原理", "项目场景", "遇到的问题", "解决方式"],
            evidence_ids=evidence_ids,
        ),
        InterviewQuestion(
            category="behavioral",
            question="讲一次你根据反馈迭代项目或产品方案的经历。",
            expected_points=["反馈来源", "迭代动作", "前后效果", "复盘"],
            evidence_ids=evidence_ids,
        ),
        InterviewQuestion(
            category="project",
            question="如果面试官质疑你的项目不够真实或不够深入，你会如何补充证据？",
            expected_points=["代码/文档", "测试结果", "指标", "个人负责范围"],
            evidence_ids=evidence_ids,
        ),
    ]
    return questions[:count]


def grade_answer(question: str, answer: str) -> InterviewFeedback:
    answer_len = len(answer.strip())
    has_structure = any(marker in answer for marker in ("首先", "其次", "最后", "背景", "目标", "结果", "STAR"))
    has_metrics = any(char.isdigit() for char in answer)
    has_self_role = any(word in answer for word in ("我负责", "我实现", "我的贡献", "我设计"))

    score = 45
    if answer_len >= 80:
        score += 20
    elif answer_len >= 30:
        score += 10
    if has_structure:
        score += 15
    if has_metrics:
        score += 10
    if has_self_role:
        score += 10

    strengths = []
    if answer_len >= 30:
        strengths.append("回答已经覆盖基本信息。")
    if has_structure:
        strengths.append("表达有一定结构，便于面试官理解。")
    if has_self_role:
        strengths.append("能够说明个人贡献。")
    if not strengths:
        strengths.append("回答提供了起点，可以继续补充项目背景和个人贡献。")

    improvements = []
    if answer_len < 80:
        improvements.append("建议补充背景、任务、行动、结果，避免只给结论。")
    if not has_metrics:
        improvements.append("建议加入可验证指标，例如准确率、响应时间、覆盖率、用户反馈数量。")
    if not has_self_role:
        improvements.append("建议明确“我负责/我实现”的部分，避免像团队介绍。")
    if "RAG" in question.upper() and "引用" not in answer and "检索" not in answer:
        improvements.append("RAG 类问题需要讲清楚检索、证据引用和幻觉控制。")

    outline = [
        "先用一句话回答问题核心结论。",
        "补充项目背景、目标用户或业务约束。",
        "说明自己的具体动作、技术方案和取舍。",
        "给出结果指标，并复盘可以继续优化的方向。",
    ]

    return InterviewFeedback(
        score=max(0, min(100, score)),
        strengths=strengths,
        improvements=improvements,
        revised_answer_outline=outline,
    )
