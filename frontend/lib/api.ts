import type { BatchMatchItem, EvaluationSummary, HealthStatus, InterviewFeedback, MatchReport, ReportSummary, ResumeExport, ResumeVersion } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function createMatchReport(resumeText: string, jdText: string): Promise<MatchReport> {
  const response = await fetch(`${API_BASE}/matches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_text: resumeText, jd_text: jdText })
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function getHealthStatus(): Promise<HealthStatus> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function warmupEmbeddings(): Promise<HealthStatus> {
  const response = await fetch(`${API_BASE}/embeddings/warmup`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function createBatchMatchReport(resumeText: string, jdTexts: string[]): Promise<BatchMatchItem[]> {
  const response = await fetch(`${API_BASE}/matches/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      resume_text: resumeText,
      jobs: jdTexts.map((jdText, index) => ({ id: `job_${index + 1}`, jd_text: jdText }))
    })
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const data = await response.json();
  return data.items;
}

export async function sendFeedback(targetId: string, action: "accept" | "reject" | "revise", comment?: string) {
  const response = await fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_id: targetId, action, comment })
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function listReports(): Promise<ReportSummary[]> {
  const response = await fetch(`${API_BASE}/reports?limit=10`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function getReport(reportId: string): Promise<MatchReport> {
  const response = await fetch(`${API_BASE}/reports/${reportId}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function createResumeVersion(resumeId: string, reportId: string, acceptedSuggestionIds: string[]): Promise<ResumeVersion> {
  const response = await fetch(`${API_BASE}/resume-versions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      resume_id: resumeId,
      report_id: reportId,
      accepted_suggestion_ids: acceptedSuggestionIds
    })
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function listResumeVersions(resumeId: string): Promise<ResumeVersion[]> {
  const response = await fetch(`${API_BASE}/resume-versions/${resumeId}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function exportResumeVersion(versionId: string): Promise<ResumeExport> {
  const response = await fetch(`${API_BASE}/resume-versions/export/${versionId}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function getEvaluationSummary(): Promise<EvaluationSummary> {
  const response = await fetch(`${API_BASE}/evaluation/summary`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function gradeInterviewAnswer(question: string, answer: string): Promise<InterviewFeedback> {
  const response = await fetch(`${API_BASE}/interviews/demo/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, answer })
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}
