"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Check,
  ClipboardList,
  Database,
  Download,
  Eye,
  FileText,
  GitCompare,
  History,
  Layers,
  MessageSquare,
  PlayCircle,
  RefreshCw,
  RotateCcw,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Upload,
} from "lucide-react";
import { Button } from "@/components/button";
import {
  createBatchMatchReport,
  createMatchReport,
  createResumeVersion,
  exportResumeVersion,
  getEvaluationSummary,
  getHealthStatus,
  getReport,
  gradeInterviewAnswer,
  listReports,
  listResumeVersions,
  sendFeedback,
  warmupEmbeddings,
} from "@/lib/api";
import type {
  BatchMatchItem,
  Evidence,
  EvaluationSummary,
  GapItem,
  HealthStatus,
  InterviewFeedback,
  InterviewQuestion,
  MatchReport,
  ReportSummary,
  ResumeVersion,
  RewriteSuggestion,
} from "@/lib/types";
import { cn, scoreLabel } from "@/lib/utils";

const SAMPLE_RESUME = `张三
软件工程本科大三，求职意向：AI 应用开发实习生
技能：Python、FastAPI、React、SQL、Git、RAG、LLM、Pandas
项目经历：
AI 求职助手 Agent：使用 FastAPI 和 React 实现简历解析、JD 匹配、RAG 检索和面试题生成，负责后端 API、评分策略和交互原型。
校园问答系统：基于向量检索和大模型回答实现课程资料问答，设计文档切分、召回和答案引用。
`;

const SAMPLE_JD = `岗位：AI 应用开发实习生
职责：
- 参与大模型应用、RAG 检索和 Agent 工作流开发
- 使用 Python/FastAPI 设计后端 API，并和前端联调
要求：
- 计算机、软件工程相关专业本科及以上
- 熟悉 Python、SQL、RAG、LLM，有 React 或 Next.js 经验加分
`;

const SAMPLE_BATCH_JDS = `${SAMPLE_JD}

---JD---
岗位：AI 后端开发实习生
职责：参与 AI 应用 API、数据存储、检索服务建设。
要求：熟悉 Python、FastAPI、SQL，了解 RAG、Embedding、向量数据库。

---JD---
岗位：产品运营实习生
职责：用户调研、活动策划、社群运营和数据复盘。
要求：Excel、PPT、沟通能力、活动执行经验。`;

const scoreItems = [
  ["技能匹配", "skill_match"],
  ["项目经验", "project_experience"],
  ["关键词覆盖", "keyword_coverage"],
  ["学历要求", "education_fit"],
  ["风险控制", "risk_control"],
] as const;

type ActiveTab = "match" | "compare" | "rewrite" | "versions" | "interview" | "trace" | "showcase";
type SuggestionDecision = "accept" | "reject" | "edit";

export default function HomePage() {
  const [resumeText, setResumeText] = useState(SAMPLE_RESUME);
  const [jdText, setJdText] = useState(SAMPLE_JD);
  const [batchJdText, setBatchJdText] = useState(SAMPLE_BATCH_JDS);
  const [report, setReport] = useState<MatchReport | null>(null);
  const [history, setHistory] = useState<ReportSummary[]>([]);
  const [batchItems, setBatchItems] = useState<BatchMatchItem[]>([]);
  const [versions, setVersions] = useState<ResumeVersion[]>([]);
  const [evaluation, setEvaluation] = useState<EvaluationSummary | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [healthLoading, setHealthLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<ActiveTab>("match");
  const [answer, setAnswer] = useState("");
  const [feedback, setInterviewFeedback] = useState<InterviewFeedback | null>(null);
  const [exportStatus, setExportStatus] = useState("");
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(null);
  const [suggestionDecisions, setSuggestionDecisions] = useState<Record<string, SuggestionDecision>>({});
  const [editedSuggestions, setEditedSuggestions] = useState<Record<string, string>>({});

  async function handleAnalyze() {
    setLoading(true);
    setError("");
    setInterviewFeedback(null);
    try {
      const result = await createMatchReport(resumeText, jdText);
      setReport(result);
      setHistory(await listReports());
      setVersions(await listResumeVersions(result.resume.id));
      setSelectedEvidenceId(result.evidence[0]?.id ?? null);
      setActiveQuestionId(result.interview_questions[0]?.id ?? null);
      setActiveTab("match");
    } catch (err) {
      setError(err instanceof Error ? err.message : "分析失败，请确认后端服务已启动。");
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadHistory(item: ReportSummary) {
    const loaded = await getReport(item.id);
    setReport(loaded);
    setVersions(await listResumeVersions(loaded.resume.id));
    setSelectedEvidenceId(loaded.evidence[0]?.id ?? null);
    setActiveQuestionId(loaded.interview_questions[0]?.id ?? null);
    setActiveTab("match");
  }

  async function handleBatchAnalyze() {
    setBatchLoading(true);
    setError("");
    try {
      const jdTexts = batchJdText.split("---JD---").map((item) => item.trim()).filter((item) => item.length >= 20);
      const items = await createBatchMatchReport(resumeText, jdTexts);
      setBatchItems(items);
      setHistory(await listReports());
      setActiveTab("compare");
    } catch (err) {
      setError(err instanceof Error ? err.message : "批量匹配失败，请确认后端服务已启动。");
    } finally {
      setBatchLoading(false);
    }
  }

  async function handleSuggestionFeedback(suggestion: RewriteSuggestion, action: "accept" | "reject" | "revise") {
    await sendFeedback(suggestion.id, action, `${suggestion.section}: ${suggestion.rationale}`);
  }

  async function handleCreateVersion() {
    if (!report) return;
    const acceptedIds = Object.entries(suggestionDecisions)
      .filter(([, decision]) => decision === "accept" || decision === "edit")
      .map(([id]) => id);
    const ids = acceptedIds.length > 0 ? acceptedIds : report.rewrite_suggestions.map((item) => item.id);
    const version = await createResumeVersion(report.resume.id, report.id, ids);
    setVersions([version, ...(await listResumeVersions(report.resume.id))]);
    setActiveTab("versions");
  }

  async function handleExportVersion(version: ResumeVersion) {
    setExportStatus("");
    const exported = await exportResumeVersion(version.id);
    const blob = new Blob([exported.content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = exported.filename;
    anchor.click();
    URL.revokeObjectURL(url);
    setExportStatus(`已生成 ${exported.filename}`);
  }

  async function handleLoadEvaluation() {
    setActiveTab("showcase");
    setError("");
    try {
      setHealth(await getHealthStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 RAG 状态失败，请确认后端服务已启动。");
    }
    try {
      setEvaluation(await getEvaluationSummary());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载评测摘要失败，请确认后端服务已启动。");
    }
  }

  async function handleWarmup() {
    setHealthLoading(true);
    setError("");
    try {
      setHealth(await warmupEmbeddings());
    } catch (err) {
      setError(err instanceof Error ? err.message : "本地 Embedding 预热失败，已保留 fallback。");
    } finally {
      setHealthLoading(false);
    }
  }

  async function handleGrade(question?: InterviewQuestion) {
    const targetQuestion = question ?? report?.interview_questions[0];
    if (!targetQuestion || !answer.trim()) return;
    const result = await gradeInterviewAnswer(targetQuestion.question, answer);
    setInterviewFeedback(result);
  }

  function markSuggestion(suggestion: RewriteSuggestion, decision: SuggestionDecision) {
    setSuggestionDecisions((current) => ({ ...current, [suggestion.id]: decision }));
    if (decision === "edit" && !editedSuggestions[suggestion.id]) {
      setEditedSuggestions((current) => ({ ...current, [suggestion.id]: suggestion.after }));
    }
  }

  const radarPolygon = useMemo(() => {
    if (!report) return "";
    const values = scoreItems.map(([, key]) => report.scores[key]);
    return values
      .map((value, index) => {
        const angle = (Math.PI * 2 * index) / values.length - Math.PI / 2;
        const radius = 20 + value * 0.72;
        const x = 100 + Math.cos(angle) * radius;
        const y = 100 + Math.sin(angle) * radius;
        return `${x},${y}`;
      })
      .join(" ");
  }, [report]);

  const selectedEvidence = report?.evidence.find((item) => item.id === selectedEvidenceId) ?? report?.evidence[0] ?? null;
  const deliveryAdvice = report ? getDeliveryAdvice(report.scores.overall, report.gaps.length) : null;
  const finalPreview = useMemo(() => buildFinalPreview(report, suggestionDecisions, editedSuggestions), [report, suggestionDecisions, editedSuggestions]);
  const priorityQuestions = report?.interview_questions.slice(0, 3) ?? [];
  const activeQuestion = priorityQuestions.find((item) => item.id === activeQuestionId) ?? priorityQuestions[0];

  return (
    <main className="min-h-screen">
      <header className="border-b border-ink/10 bg-paper/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-md bg-ink text-white">
              <Sparkles size={20} />
            </div>
            <div>
              <h1 className="text-xl font-bold">AI 求职助手 Agent</h1>
              <p className="text-sm text-ink/60">岗位匹配 · 简历优化 · 面试准备</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <EmbeddingStatus health={health} onWarmup={handleWarmup} loading={healthLoading} />
            <Button onClick={handleAnalyze} disabled={loading}>
              {loading ? <RefreshCw className="animate-spin" size={16} /> : <Send size={16} />}
              {loading ? "分析中" : "生成报告"}
            </Button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-5 px-5 py-6 lg:grid-cols-[400px_1fr]">
        <aside className="space-y-4">
          <Panel title="输入工作流" icon={<FileText size={18} />}>
            <InputStep index={1} title="简历" meta={`${resumeText.length} 字`}>
              <div className="mb-2 flex flex-wrap gap-2">
                <Button variant="ghost" onClick={() => setResumeText(SAMPLE_RESUME)}>
                  <Sparkles size={14} />
                  示例
                </Button>
                <Button variant="ghost" onClick={() => setResumeText("")}>
                  <RotateCcw size={14} />
                  清空
                </Button>
                <Button variant="ghost" disabled>
                  <Upload size={14} />
                  上传
                </Button>
              </div>
              <textarea
                className="h-48 w-full rounded-md border border-ink/15 bg-white p-3 text-sm leading-6 outline-none focus:border-aqua"
                value={resumeText}
                onChange={(event) => setResumeText(event.target.value)}
              />
              <ParsedPreview label="解析预览" items={previewResume(resumeText)} />
            </InputStep>

            <InputStep index={2} title="岗位 JD" meta={`${jdText.length} 字`}>
              <div className="mb-2 flex flex-wrap gap-2">
                <Button variant="ghost" onClick={() => setJdText(SAMPLE_JD)}>
                  <Sparkles size={14} />
                  示例
                </Button>
                <Button variant="ghost" onClick={() => setJdText("")}>
                  <RotateCcw size={14} />
                  清空
                </Button>
              </div>
              <textarea
                className="h-40 w-full rounded-md border border-ink/15 bg-white p-3 text-sm leading-6 outline-none focus:border-aqua"
                value={jdText}
                onChange={(event) => setJdText(event.target.value)}
              />
              <ParsedPreview label="岗位预览" items={previewJd(jdText)} />
            </InputStep>

            <InputStep index={3} title="分析设置" meta="本地优先">
              <div className="grid gap-2 text-sm text-ink/70">
                <p className="rounded-md bg-white p-3">默认单 JD 分析，生成报告后可继续做简历优化和面试准备。</p>
                <p className="rounded-md bg-white p-3">多 JD 对比已移到“岗位对比”视图，避免干扰主流程。</p>
                <p className="rounded-md bg-white p-3">所有改写建议必须引用证据，证据不足会提示人工复核。</p>
              </div>
              <Button className="mt-3 w-full" onClick={handleAnalyze} disabled={loading || resumeText.length < 20 || jdText.length < 20}>
                {loading ? <RefreshCw className="animate-spin" size={16} /> : <Send size={16} />}
                {loading ? "分析中" : "生成岗位匹配报告"}
              </Button>
            </InputStep>
          </Panel>

          {report && (
            <>
              <Panel title="证据侧栏" icon={<ClipboardList size={18} />}>
                <div className="space-y-3">
                  {report.evidence.slice(0, 7).map((item) => (
                    <EvidenceCard
                      key={item.id}
                      item={item}
                      active={selectedEvidenceId === item.id}
                      onClick={() => setSelectedEvidenceId(item.id)}
                    />
                  ))}
                </div>
              </Panel>
              <Panel title="历史报告" icon={<History size={18} />}>
                <div className="space-y-2">
                  {history.length === 0 && <p className="text-sm text-ink/55">生成报告后会在这里保存历史记录。</p>}
                  {history.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => handleLoadHistory(item)}
                      className="w-full rounded-md border border-ink/10 bg-white p-3 text-left text-sm transition hover:border-aqua"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <strong>{item.jd_title}</strong>
                        <span>{item.overall_score}</span>
                      </div>
                      <p className="mt-1 truncate text-xs text-ink/55">{item.top_gap}</p>
                    </button>
                  ))}
                </div>
              </Panel>
            </>
          )}
        </aside>

        <section className="space-y-4">
          {error && <div className="rounded-md border border-coral/30 bg-coral/10 p-3 text-sm text-coral">{error}</div>}

          {!report ? (
            <EmptyState onAnalyze={handleAnalyze} loading={loading} />
          ) : (
            <>
              <Panel title={report.jd.title} icon={<Sparkles size={18} />}>
                <div className="grid gap-4 xl:grid-cols-[250px_1fr]">
                  <div className="rounded-md bg-white p-4">
                    <div className="flex items-end gap-2">
                      <strong className="text-5xl">{report.scores.overall}</strong>
                      <span className="pb-2 text-sm text-ink/55">/100</span>
                    </div>
                    <p className="mt-2 font-semibold text-moss">{scoreLabel(report.scores.overall)}</p>
                    <div className="mt-3 space-y-2 text-xs text-ink/60">
                      <p className="flex items-center gap-2"><Sparkles size={14} />模型：{report.model_provider}</p>
                      <p className="flex items-center gap-2"><Database size={14} />RAG：{report.rag_mode}</p>
                    </div>
                    <svg viewBox="0 0 200 200" className="mt-4 aspect-square w-full">
                      {[40, 70, 100].map((radius) => (
                        <circle key={radius} cx="100" cy="100" r={radius} fill="none" stroke="#d8ded5" strokeWidth="1" />
                      ))}
                      {scoreItems.map(([label], index) => {
                        const angle = (Math.PI * 2 * index) / scoreItems.length - Math.PI / 2;
                        const x = 100 + Math.cos(angle) * 92;
                        const y = 100 + Math.sin(angle) * 92;
                        return (
                          <text key={label} x={x} y={y} textAnchor="middle" dominantBaseline="middle" className="fill-ink text-[9px]">
                            {label}
                          </text>
                        );
                      })}
                      <polygon points={radarPolygon} fill="rgba(62, 141, 150, 0.28)" stroke="#3e8d96" strokeWidth="2" />
                    </svg>
                  </div>
                  <div className="space-y-4">
                    {deliveryAdvice && <DeliveryCard advice={deliveryAdvice} />}
                    <p className="text-base leading-7">{report.summary}</p>
                    <div className="grid gap-3 md:grid-cols-3">
                      <Button variant="secondary" onClick={() => setActiveTab("rewrite")}>
                        <FileText size={16} />
                        优化简历
                      </Button>
                      <Button variant="secondary" onClick={() => setActiveTab("interview")}>
                        <MessageSquare size={16} />
                        练习面试
                      </Button>
                      <Button variant="secondary" onClick={() => setActiveTab("compare")}>
                        <GitCompare size={16} />
                        对比其他 JD
                      </Button>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      {scoreItems.map(([label, key]) => (
                        <div key={key} className="rounded-md border border-ink/10 bg-white p-3">
                          <div className="flex items-center justify-between text-sm">
                            <span>{label}</span>
                            <strong>{report.scores[key]}</strong>
                          </div>
                          <div className="mt-2 h-2 rounded-full bg-ink/10">
                            <div className="h-full rounded-full bg-aqua" style={{ width: `${report.scores[key]}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </Panel>

              <div className="flex flex-wrap gap-2">
                <Tab active={activeTab === "match"} onClick={() => setActiveTab("match")}>匹配报告</Tab>
                <Tab active={activeTab === "compare"} onClick={() => setActiveTab("compare")}>岗位对比</Tab>
                <Tab active={activeTab === "rewrite"} onClick={() => setActiveTab("rewrite")}>简历优化</Tab>
                <Tab active={activeTab === "versions"} onClick={() => setActiveTab("versions")}>简历版本</Tab>
                <Tab active={activeTab === "interview"} onClick={() => setActiveTab("interview")}>面试准备</Tab>
                <Tab active={activeTab === "trace"} onClick={() => setActiveTab("trace")}>Agent 链路</Tab>
                <Tab active={activeTab === "showcase"} onClick={() => setActiveTab("showcase")}>项目展示</Tab>
              </div>

              {activeTab === "match" && (
                <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
                  <Panel title="短板与行动建议" icon={<ClipboardList size={18} />}>
                    <div className="space-y-3">
                      {sortGaps(report.gaps).map((gap) => (
                        <GapCard key={gap.title} gap={gap} selectedEvidenceId={selectedEvidenceId} onEvidenceClick={setSelectedEvidenceId} />
                      ))}
                    </div>
                  </Panel>
                  <div className="space-y-4">
                    <Panel title="优势" icon={<Check size={18} />}>
                      <div className="space-y-2">
                        {report.strengths.map((item) => (
                          <p key={item} className="rounded-md bg-white p-3 text-sm leading-6">{item}</p>
                        ))}
                      </div>
                    </Panel>
                    <Panel title="当前选中证据" icon={<Eye size={18} />}>
                      {selectedEvidence ? <EvidenceDetail item={selectedEvidence} /> : <p className="text-sm text-ink/60">点击左侧证据查看详情。</p>}
                    </Panel>
                  </div>
                </div>
              )}

              {activeTab === "compare" && (
                <Panel title="多 JD 横向对比" icon={<BarChart3 size={18} />}>
                  <div className="mb-4 grid gap-3 lg:grid-cols-[1fr_180px]">
                    <textarea
                      className="h-36 rounded-md border border-ink/15 bg-white p-3 text-sm leading-6 outline-none focus:border-aqua"
                      value={batchJdText}
                      onChange={(event) => setBatchJdText(event.target.value)}
                    />
                    <div className="space-y-2">
                      <Button className="w-full" variant="secondary" onClick={handleBatchAnalyze} disabled={batchLoading}>
                        {batchLoading ? <RefreshCw className="animate-spin" size={16} /> : <GitCompare size={16} />}
                        {batchLoading ? "对比中" : "批量对比"}
                      </Button>
                      <p className="text-xs leading-5 text-ink/55">用 ---JD--- 分隔多个岗位，最多 8 个。</p>
                    </div>
                  </div>
                  {batchItems.length === 0 ? (
                    <p className="rounded-md bg-white p-4 text-sm text-ink/60">粘贴多个 JD 后查看排序结果和投递策略。</p>
                  ) : (
                    <CompareTable items={batchItems} onOpen={async (item) => {
                      const loaded = await getReport(item.report_id);
                      setReport(loaded);
                      setVersions(await listResumeVersions(loaded.resume.id));
                      setSelectedEvidenceId(loaded.evidence[0]?.id ?? null);
                      setActiveQuestionId(loaded.interview_questions[0]?.id ?? null);
                      setActiveTab("match");
                    }} />
                  )}
                </Panel>
              )}

              {activeTab === "rewrite" && (
                <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
                  <Panel title="简历优化建议" icon={<FileText size={18} />}>
                    <div className="mb-4 flex flex-wrap justify-end gap-2">
                      <Button variant="secondary" onClick={handleCreateVersion}>
                        <Download size={16} />
                        生成简历版本
                      </Button>
                    </div>
                    <div className="space-y-4">
                      {groupSuggestions(report.rewrite_suggestions).map(([group, suggestions]) => (
                        <section key={group} className="space-y-3">
                          <h3 className="text-sm font-bold text-ink/70">{group}</h3>
                          {suggestions.map((suggestion) => (
                            <SuggestionCard
                              key={suggestion.id}
                              suggestion={suggestion}
                              decision={suggestionDecisions[suggestion.id]}
                              editedText={editedSuggestions[suggestion.id]}
                              selectedEvidenceId={selectedEvidenceId}
                              onDecision={(decision) => markSuggestion(suggestion, decision)}
                              onEdit={(value) => setEditedSuggestions((current) => ({ ...current, [suggestion.id]: value }))}
                              onEvidenceClick={setSelectedEvidenceId}
                              onFeedback={handleSuggestionFeedback}
                            />
                          ))}
                        </section>
                      ))}
                    </div>
                  </Panel>
                  <Panel title="最终简历预览" icon={<Eye size={18} />}>
                    <pre className="max-h-[620px] overflow-auto whitespace-pre-wrap rounded-md bg-white p-3 text-sm leading-6">{finalPreview}</pre>
                  </Panel>
                </div>
              )}

              {activeTab === "versions" && (
                <Panel title="简历版本历史" icon={<Layers size={18} />}>
                  {versions.length === 0 ? (
                    <p className="rounded-md bg-white p-4 text-sm text-ink/60">在简历优化页点击“生成简历版本”后会出现在这里。</p>
                  ) : (
                    <div className="space-y-4">
                      {exportStatus && <p className="rounded-md bg-aqua/10 p-3 text-sm text-aqua">{exportStatus}</p>}
                      {versions.map((version) => (
                        <article key={version.id} className="rounded-md border border-ink/10 bg-white p-4">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <strong>{version.title}</strong>
                            <div className="flex items-center gap-3">
                              <span className="text-xs text-ink/50">{new Date(version.created_at).toLocaleString()}</span>
                              <Button variant="ghost" onClick={() => handleExportVersion(version)}>
                                <Download size={14} />
                                导出
                              </Button>
                            </div>
                          </div>
                          {version.diff.length > 0 && (
                            <pre className="mt-3 max-h-44 overflow-auto whitespace-pre-wrap rounded border border-ink/10 bg-ink/5 p-3 text-xs leading-5">
                              {version.diff.join("\n")}
                            </pre>
                          )}
                          <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-ink/5 p-3 text-sm leading-6">{version.content}</pre>
                        </article>
                      ))}
                    </div>
                  )}
                </Panel>
              )}

              {activeTab === "interview" && (
                <Panel title="面试准备" icon={<MessageSquare size={18} />}>
                  <div className="mb-4 rounded-md bg-white p-4 text-sm leading-6 text-ink/70">
                    先练 3 道优先题：项目深挖、技术短板、行为表达。回答后会给出重答提纲。
                  </div>
                  <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
                    <div className="space-y-3">
                      {priorityQuestions.map((item, index) => (
                        <InterviewQuestionCard
                          key={item.id}
                          question={item}
                          index={index}
                          active={activeQuestion?.id === item.id}
                          onPractice={() => {
                            setActiveQuestionId(item.id);
                            setAnswer("");
                            setInterviewFeedback(null);
                          }}
                        />
                      ))}
                    </div>
                    <div className="rounded-md border border-ink/10 bg-white p-4">
                      <label className="text-sm font-semibold">回答当前题目</label>
                      <p className="mt-2 rounded-md bg-ink/5 p-3 text-sm leading-6 text-ink/70">
                        {activeQuestion?.question ?? "请选择一道题开始练习。"}
                      </p>
                      <textarea
                        className="mt-2 h-44 w-full rounded-md border border-ink/15 p-3 text-sm leading-6 outline-none focus:border-aqua"
                        value={answer}
                        onChange={(event) => setAnswer(event.target.value)}
                        placeholder="用 STAR 结构回答：背景、任务、行动、结果..."
                      />
                      <Button className="mt-3 w-full" onClick={() => handleGrade(activeQuestion)} disabled={!answer.trim() || !activeQuestion}>
                        <MessageSquare size={16} />
                        获取反馈
                      </Button>
                      {feedback && (
                        <div className="mt-4 space-y-3 text-sm">
                          <div className="rounded-md bg-aqua/10 p-3">
                            <strong>反馈得分：{feedback.score}</strong>
                          </div>
                          <FeedbackList title="优点" items={feedback.strengths} />
                          <FeedbackList title="改进" items={feedback.improvements} />
                          <FeedbackList title="重答提纲" items={feedback.revised_answer_outline} />
                        </div>
                      )}
                    </div>
                  </div>
                </Panel>
              )}

              {activeTab === "trace" && (
                <Panel title="Agent 执行链路" icon={<Activity size={18} />}>
                  <div className="space-y-3">
                    {report.trace.map((step, index) => (
                      <details key={`${step.name}-${index}`} className="rounded-md border border-ink/10 bg-white p-4">
                        <summary className="cursor-pointer">
                          <span className="font-semibold">{index + 1}. {step.name}</span>
                          <span className="ml-3 rounded bg-aqua/10 px-2 py-1 text-xs font-semibold text-aqua">
                            {step.status} · {step.duration_ms}ms
                          </span>
                          <span className="ml-3 text-xs text-ink/50">{summarizeTrace(step.output_summary)}</span>
                        </summary>
                        <div className="mt-3 grid gap-3 text-xs md:grid-cols-2">
                          <pre className="overflow-auto rounded bg-ink/5 p-3">{JSON.stringify(step.input_summary, null, 2)}</pre>
                          <pre className="overflow-auto rounded bg-ink/5 p-3">{JSON.stringify(step.output_summary, null, 2)}</pre>
                        </div>
                        {step.error && <p className="mt-2 text-sm text-coral">{step.error}</p>}
                      </details>
                    ))}
                  </div>
                </Panel>
              )}

              {activeTab === "showcase" && (
                <Panel title="项目展示" icon={<Sparkles size={18} />}>
                  <div className="mb-4 flex flex-wrap justify-end gap-2">
                    <Button variant="secondary" onClick={handleWarmup} disabled={healthLoading}>
                      {healthLoading ? <RefreshCw className="animate-spin" size={16} /> : <PlayCircle size={16} />}
                      预热本地 Embedding
                    </Button>
                    <Button variant="secondary" onClick={handleLoadEvaluation}>
                      <Activity size={16} />
                      加载评测摘要
                    </Button>
                  </div>
                  <div className="grid gap-4 lg:grid-cols-2">
                    <ShowcaseBlock title="产品流程" items={["输入简历与 JD", "生成匹配报告", "采纳简历建议", "模拟面试反馈"]} />
                    <ShowcaseBlock title="Agent 流程" items={["InputGuard", "ResumeParser / JDParser", "RAGRetriever", "MatchScorer / Rewriter / Coach"]} />
                    <ShowcaseBlock title="RAG 链路" items={health ? [
                      `后端 ${health.vector_backend}`,
                      `模型 ${health.embedding_model}`,
                      `状态 ${health.embedding_load_status}`,
                      `设备 ${health.embedding_device}`,
                      `延迟 ${health.embedding_latency_ms}ms`,
                      `fallback ${health.embedding_fallback_count} 次`,
                    ] : ["本地 BGE-M3 优先", "失败自动 fallback", "证据可追溯", "支持 reindex"]} />
                    <ShowcaseBlock title="评测指标" items={evaluation ? [
                      `样例数 ${evaluation.case_count}`,
                      `档位准确率 ${Math.round(evaluation.exact_band_accuracy * 100)}%`,
                      `证据覆盖 ${Math.round(evaluation.suggestion_evidence_coverage * 100)}%`,
                      `校验通过 ${Math.round(evaluation.validation_pass_rate * 100)}%`,
                      `幻觉风险 ${evaluation.hallucination_risk_count}`,
                    ] : ["匹配档位准确率", "短板命中率", "证据覆盖率", "幻觉风险数"]} />
                  </div>
                </Panel>
              )}
            </>
          )}
        </section>
      </section>
    </main>
  );
}

function EmbeddingStatus({ health, onWarmup, loading }: { health: HealthStatus | null; onWarmup: () => void; loading: boolean }) {
  const ready = health?.embedding_real_enabled;
  return (
    <button
      onClick={onWarmup}
      className={cn(
        "flex items-center gap-2 rounded-md border px-3 py-2 text-xs font-semibold",
        ready ? "border-aqua/30 bg-aqua/10 text-aqua" : "border-amber/30 bg-amber/10 text-amber"
      )}
    >
      {loading ? <RefreshCw className="animate-spin" size={14} /> : <Database size={14} />}
      {health ? `${health.embedding_load_status} · ${health.embedding_model}` : "Embedding 状态"}
    </button>
  );
}

function InputStep({ index, title, meta, children }: { index: number; title: string; meta: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-ink/10 py-4 last:border-b-0 last:pb-0 first:pt-0">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="flex size-6 items-center justify-center rounded bg-ink text-xs font-bold text-white">{index}</span>
          <strong>{title}</strong>
        </div>
        <span className="text-xs text-ink/50">{meta}</span>
      </div>
      {children}
    </section>
  );
}

function ParsedPreview({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="mt-2 rounded-md bg-white p-3 text-xs text-ink/60">
      <strong className="text-ink/70">{label}</strong>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.map((item) => (
          <span key={item} className="rounded bg-ink/5 px-2 py-1">{item}</span>
        ))}
      </div>
    </div>
  );
}

function DeliveryCard({ advice }: { advice: { title: string; detail: string; tone: "high" | "medium" | "low" } }) {
  return (
    <div className={cn(
      "rounded-md border p-4",
      advice.tone === "high" && "border-aqua/25 bg-aqua/10",
      advice.tone === "medium" && "border-amber/25 bg-amber/10",
      advice.tone === "low" && "border-coral/25 bg-coral/10",
    )}>
      <div className="flex items-center gap-2 font-bold">
        {advice.tone === "low" ? <AlertTriangle size={18} /> : <Check size={18} />}
        {advice.title}
      </div>
      <p className="mt-2 text-sm leading-6 text-ink/70">{advice.detail}</p>
    </div>
  );
}

function EvidenceCard({ item, active, onClick }: { item: Evidence; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full rounded-md border bg-white p-3 text-left transition",
        active ? "border-aqua shadow-panel" : "border-ink/10 hover:border-aqua/60"
      )}
    >
      <div className="flex items-center justify-between text-xs font-semibold text-ink/55">
        <span>{item.source}</span>
        <span>{item.retrieval_method} · {Math.round(item.score * 100)}%</span>
      </div>
      <p className="mt-2 line-clamp-3 text-sm leading-6">{item.text}</p>
    </button>
  );
}

function EvidenceDetail({ item }: { item: Evidence }) {
  return (
    <article className="rounded-md bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-semibold text-ink/55">
        <span>{item.id}</span>
        <span>{item.source} · {item.retrieval_method}</span>
      </div>
      <p className="mt-3 text-sm leading-6">{item.text}</p>
    </article>
  );
}

function GapCard({ gap, selectedEvidenceId, onEvidenceClick }: { gap: GapItem; selectedEvidenceId: string | null; onEvidenceClick: (id: string) => void }) {
  return (
    <article className={cn(
      "rounded-md border bg-white p-4",
      gap.evidence_ids.includes(selectedEvidenceId ?? "") ? "border-aqua" : "border-ink/10"
    )}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <strong>{gap.title}</strong>
        <span className={cn("rounded px-2 py-1 text-xs font-semibold", gap.priority === "high" ? "bg-coral/15 text-coral" : "bg-amber/15 text-amber")}>
          {gap.priority} · {gap.evidence_ids.length} 条证据
        </span>
      </div>
      <p className="mt-2 text-sm leading-6 text-ink/70">{gap.detail}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {gap.evidence_ids.map((id) => (
          <button key={id} onClick={() => onEvidenceClick(id)} className="rounded bg-ink/5 px-2 py-1 text-xs text-ink/60 hover:bg-aqua/10">
            {id}
          </button>
        ))}
      </div>
    </article>
  );
}

function SuggestionCard({
  suggestion,
  decision,
  editedText,
  selectedEvidenceId,
  onDecision,
  onEdit,
  onEvidenceClick,
  onFeedback,
}: {
  suggestion: RewriteSuggestion;
  decision?: SuggestionDecision;
  editedText?: string;
  selectedEvidenceId: string | null;
  onDecision: (decision: SuggestionDecision) => void;
  onEdit: (value: string) => void;
  onEvidenceClick: (id: string) => void;
  onFeedback: (suggestion: RewriteSuggestion, action: "accept" | "reject" | "revise") => void;
}) {
  const unsafe = suggestion.validation_status !== "passed";
  return (
    <article className={cn(
      "rounded-md border bg-white p-4",
      suggestion.evidence_ids.includes(selectedEvidenceId ?? "") ? "border-aqua" : "border-ink/10"
    )}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <strong>{suggestion.section}</strong>
          <ValidationBadge status={suggestion.validation_status} />
          {decision && <span className="rounded bg-ink/5 px-2 py-1 text-xs text-ink/55">{decision}</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => { onDecision("accept"); onFeedback(suggestion, "accept"); }}>
            <ThumbsUp size={14} />
            采纳
          </Button>
          <Button variant="ghost" onClick={() => { onDecision("reject"); onFeedback(suggestion, "reject"); }}>
            <ThumbsDown size={14} />
            忽略
          </Button>
          <Button variant="ghost" onClick={() => { onDecision("edit"); onFeedback(suggestion, "revise"); }}>
            <FileText size={14} />
            编辑
          </Button>
        </div>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <DiffBlock title="Before" text={suggestion.before} tone="before" />
        <DiffBlock title="After" text={suggestion.after} tone="after" />
      </div>
      {decision === "edit" && (
        <textarea
          className="mt-3 h-28 w-full rounded-md border border-ink/15 p-3 text-sm leading-6 outline-none focus:border-aqua"
          value={editedText ?? suggestion.after}
          onChange={(event) => onEdit(event.target.value)}
        />
      )}
      <p className="mt-3 text-sm leading-6 text-ink/65">{suggestion.rationale}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        {suggestion.evidence_ids.map((id) => (
          <button key={id} onClick={() => onEvidenceClick(id)} className="rounded bg-ink/5 px-2 py-1 text-ink/55 hover:bg-aqua/10">{id}</button>
        ))}
      </div>
      {unsafe && (
        <div className="mt-3 rounded-md border border-amber/25 bg-amber/10 p-3 text-xs leading-5 text-ink/70">
          <strong>证据不足，不建议直接写入简历。</strong>
          {(suggestion.validation_notes.length > 0 ? suggestion.validation_notes : ["需要人工复核后再使用。"]).map((note) => (
            <p key={note}>{note}</p>
          ))}
        </div>
      )}
    </article>
  );
}

function CompareTable({ items, onOpen }: { items: BatchMatchItem[]; onOpen: (item: BatchMatchItem) => void }) {
  return (
    <div className="overflow-auto rounded-md border border-ink/10 bg-white">
      <table className="w-full min-w-[780px] border-collapse text-sm">
        <thead className="bg-ink/5 text-left">
          <tr>
            <th className="p-3">岗位</th>
            <th className="p-3">总分</th>
            <th className="p-3">技能</th>
            <th className="p-3">项目</th>
            <th className="p-3">关键词</th>
            <th className="p-3">短板</th>
            <th className="p-3">优先级</th>
            <th className="p-3">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.report_id} className="border-t border-ink/10">
              <td className="p-3">
                <div className="font-semibold">{item.jd_title}</div>
                <p className="mt-1 max-w-[320px] text-xs leading-5 text-ink/60">{item.recommendation_reason}</p>
              </td>
              <td className="p-3">{item.overall_score}</td>
              <td className="p-3">{item.skill_match}</td>
              <td className="p-3">{item.project_experience}</td>
              <td className="p-3">{item.keyword_coverage}</td>
              <td className="p-3">{item.gap_count}</td>
              <td className="p-3"><PriorityBadge priority={item.priority} /></td>
              <td className="p-3"><Button variant="ghost" onClick={() => onOpen(item)}>查看</Button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function InterviewQuestionCard({ question, index, active, onPractice }: { question: InterviewQuestion; index: number; active: boolean; onPractice: () => void }) {
  return (
    <article className={cn("rounded-md border bg-white p-4", active ? "border-aqua shadow-panel" : "border-ink/10")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs font-semibold uppercase text-aqua">Q{index + 1} · {question.category}</div>
        <Button variant="ghost" onClick={onPractice}>
          <PlayCircle size={14} />
          重练
        </Button>
      </div>
      <p className="mt-2 font-semibold leading-7">{question.question}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {question.expected_points.map((point) => (
          <span key={point} className="rounded bg-ink/5 px-2 py-1 text-xs">{point}</span>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-ink/55">
        {question.evidence_ids.map((id) => <span key={id}>证据 {id}</span>)}
      </div>
    </article>
  );
}

function PriorityBadge({ priority }: { priority: "high" | "medium" | "low" }) {
  return (
    <span className={cn(
      "rounded px-2 py-1 text-xs font-semibold",
      priority === "high" && "bg-aqua/15 text-aqua",
      priority === "medium" && "bg-amber/15 text-amber",
      priority === "low" && "bg-coral/15 text-coral"
    )}>
      {priority}
    </span>
  );
}

function ValidationBadge({ status }: { status: "passed" | "warning" | "failed" }) {
  return (
    <span className={cn(
      "rounded px-2 py-1 text-xs font-semibold",
      status === "passed" && "bg-aqua/15 text-aqua",
      status === "warning" && "bg-amber/15 text-amber",
      status === "failed" && "bg-coral/15 text-coral"
    )}>
      {status}
    </span>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-ink/10 bg-paper p-4 shadow-panel">
      <div className="mb-4 flex items-center gap-2">
        <span className="text-aqua">{icon}</span>
        <h2 className="text-base font-bold">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function EmptyState({ onAnalyze, loading }: { onAnalyze: () => void; loading: boolean }) {
  return (
    <section className="flex min-h-[560px] items-center justify-center rounded-md border border-dashed border-ink/20 bg-white p-8 text-center">
      <div className="max-w-md">
        <Sparkles className="mx-auto text-aqua" size={44} />
        <h2 className="mt-4 text-2xl font-bold">生成第一份岗位匹配报告</h2>
        <p className="mt-3 leading-7 text-ink/65">左侧按 3 步填入简历和 JD，可直接使用示例，也可以替换成自己的材料。</p>
        <Button className="mt-5" onClick={onAnalyze} disabled={loading}>
          {loading ? <RefreshCw className="animate-spin" size={16} /> : <Send size={16} />}
          开始分析
        </Button>
      </div>
    </section>
  );
}

function Tab({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-md border px-4 py-2 text-sm font-semibold transition",
        active ? "border-ink bg-ink text-white" : "border-ink/10 bg-white text-ink hover:border-aqua"
      )}
    >
      {children}
    </button>
  );
}

function DiffBlock({ title, text, tone }: { title: string; text: string; tone: "before" | "after" }) {
  return (
    <div className={cn("rounded-md border p-3", tone === "before" ? "border-coral/20 bg-coral/5" : "border-aqua/20 bg-aqua/5")}>
      <div className="text-xs font-bold uppercase text-ink/50">{title}</div>
      <p className="mt-2 text-sm leading-6">{text}</p>
    </div>
  );
}

function FeedbackList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <strong>{title}</strong>
      <ul className="mt-2 space-y-1 text-ink/70">
        {items.map((item) => (
          <li key={item}>· {item}</li>
        ))}
      </ul>
    </div>
  );
}

function ShowcaseBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <article className="rounded-md border border-ink/10 bg-white p-4">
      <strong>{title}</strong>
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <p key={item} className="rounded bg-ink/5 px-3 py-2 text-sm">{item}</p>
        ))}
      </div>
    </article>
  );
}

function previewResume(text: string) {
  const skills = ["Python", "FastAPI", "React", "RAG", "LLM", "SQL"].filter((item) => text.toLowerCase().includes(item.toLowerCase()));
  return [`技能 ${skills.length}`, `项目 ${text.includes("项目") ? "已识别" : "待补充"}`, `长度 ${text.length >= 120 ? "充足" : "偏短"}`];
}

function previewJd(text: string) {
  const title = text.match(/岗位[:：]\s*([^\n]+)/)?.[1] ?? "待识别岗位";
  const skills = ["Python", "FastAPI", "React", "RAG", "LLM", "SQL", "Embedding"].filter((item) => text.toLowerCase().includes(item.toLowerCase()));
  return [title, `要求 ${skills.length} 项`, `长度 ${text.length >= 80 ? "充足" : "偏短"}`];
}

function getDeliveryAdvice(score: number, gapCount: number) {
  if (score >= 75 && gapCount <= 3) {
    return { title: "优先投递", detail: "匹配度较高，建议先采纳高证据改写，再准备项目深挖题。", tone: "high" as const };
  }
  if (score >= 50) {
    return { title: "可投但需优化", detail: "岗位方向匹配，但需要补强短板表达和项目证据。", tone: "medium" as const };
  }
  return { title: "谨慎投递", detail: "当前短板较多，建议优先选择更匹配岗位，或先补充相关项目经历。", tone: "low" as const };
}

function sortGaps(gaps: GapItem[]) {
  const order = { high: 0, medium: 1, low: 2 };
  return [...gaps].sort((left, right) => order[left.priority] - order[right.priority]);
}

function groupSuggestions(suggestions: RewriteSuggestion[]): Array<[string, RewriteSuggestion[]]> {
  const groups: Record<string, RewriteSuggestion[]> = {};
  for (const suggestion of suggestions) {
    const key = suggestion.section.includes("项目") ? "项目经历" : suggestion.section.includes("技能") ? "技能摘要" : suggestion.section.includes("目标") ? "求职目标" : "补充说明";
    groups[key] = [...(groups[key] ?? []), suggestion];
  }
  return Object.entries(groups);
}

function buildFinalPreview(report: MatchReport | null, decisions: Record<string, SuggestionDecision>, edits: Record<string, string>) {
  if (!report) return "";
  const accepted = report.rewrite_suggestions.filter((item) => decisions[item.id] === "accept" || decisions[item.id] === "edit");
  const items = accepted.length > 0 ? accepted : report.rewrite_suggestions.filter((item) => item.validation_status === "passed");
  return [
    report.resume.skills.length ? `技能：${report.resume.skills.join("、")}` : "技能：请补充技能摘要",
    "",
    "## 针对岗位的优化版本",
    ...items.flatMap((item) => [`### ${item.section}`, edits[item.id] ?? item.after, ""]),
  ].join("\n").trim();
}

function summarizeTrace(output: Record<string, string | number | boolean | null>) {
  const first = Object.entries(output)[0];
  if (!first) return "暂无摘要";
  return `${first[0]}: ${String(first[1])}`;
}
