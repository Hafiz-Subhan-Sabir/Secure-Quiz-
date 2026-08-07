const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export type TokenResponse = {
  access_token: string;
  token_type: string;
  role: "admin" | "instructor" | "student";
  expires_in: number;
};

export type ExamSummary = {
  id: string;
  title: string;
  status: string;
  duration_minutes: number;
  proctoring_profile_id: string | null;
};

export type EvidenceFrame = {
  event_id: string;
  captured_at: string;
  source: "primary_webcam" | "android_camera" | "screen";
  gesture_label: string;
  plain_language: string;
  severity: number;
  image_data_uri: string;
};

export type IntegrityReport = {
  session_id: string;
  student_name: string;
  student_email: string;
  exam_title: string;
  status: string;
  cheating_probability: number;
  flags: string[];
  event_count: number;
  timeline: Array<Record<string, unknown>>;
  evidence: EvidenceFrame[];
  summary_plain: string;
  quiz_score?: number;
  quiz_max_score?: number;
  quiz_percent?: number;
};

export type AttemptSummary = {
  session_id: string;
  student_name: string;
  student_email: string;
  exam_title: string;
  status: string;
  started_at: string;
  last_risk_score: number;
  android_paired: boolean;
  event_count: number;
  evidence_count: number;
  flagged: boolean;
  quiz_score?: number;
  quiz_max_score?: number;
  quiz_percent?: number;
};

type RequestOpts = RequestInit & { signal?: AbortSignal };

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("iq_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function friendlyError(status: number, body: string): string {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail) && parsed.detail[0]?.msg) {
      return String(parsed.detail[0].msg);
    }
  } catch {
    /* raw */
  }
  if (status === 401) return "Wrong email/password, or your session expired. Please sign in again.";
  if (status === 403) return "You do not have permission for this action.";
  if (status === 404) return "We could not find that item.";
  return body || `Something went wrong (${status}).`;
}

async function request<T>(path: string, init?: RequestOpts): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new Error(friendlyError(res.status, await res.text()));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: (signal?: AbortSignal) =>
    request<{ status: string; service: string; version: string }>("/health", { signal }),
  login: (email: string, password: string, signal?: AbortSignal) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      signal,
    }),
  listExams: (signal?: AbortSignal) => request<ExamSummary[]>("/exams", { signal }),
  createExam: (
    body: { title: string; duration_minutes: number; instructions?: string },
    signal?: AbortSignal,
  ) =>
    request<ExamSummary>("/exams", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),
  publishExam: (examId: string, signal?: AbortSignal) =>
    request<ExamSummary>(`/exams/${examId}/publish`, { method: "POST", signal }),
  listAttempts: (signal?: AbortSignal) =>
    request<AttemptSummary[]>("/sessions/attempts", { signal }),
  getReport: (sessionId: string, signal?: AbortSignal) =>
    request<IntegrityReport>(`/reports/sessions/${sessionId}`, { signal }),
};

export function riskLabel(score: number): string {
  if (score >= 0.65) return "High concern";
  if (score >= 0.4) return "Needs review";
  return "Looks fine";
}

export function sourceLabel(source: string): string {
  if (source === "android_camera") return "Phone camera (side / rear view)";
  if (source === "screen") return "Screen capture";
  return "Laptop webcam";
}

export function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}
