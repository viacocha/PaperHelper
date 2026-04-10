import type { ReviewResult, StandardOption } from "../types/review";

const API_BASE = "http://127.0.0.1:8000/api";

export async function fetchStandards(): Promise<StandardOption[]> {
  const response = await fetch(`${API_BASE}/standards`);
  if (!response.ok) {
    throw new Error("无法加载标准库。");
  }

  const payload = await response.json();
  return payload.standards;
}

export async function reviewEssay(file: File, standardId: string): Promise<ReviewResult> {
  const form = new FormData();
  form.append("file", file);
  if (standardId) {
    form.append("standard_id", standardId);
  }

  const response = await fetch(`${API_BASE}/review`, {
    method: "POST",
    body: form
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? "批改失败。");
  }

  return response.json();
}

export function reportDownloadUrl(reportName: string): string {
  return `${API_BASE}/reports/${encodeURIComponent(reportName)}`;
}
