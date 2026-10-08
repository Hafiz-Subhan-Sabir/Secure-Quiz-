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

export type ExamDetail = ExamSummary & {
  instructions: string;
  question_count: number;
};

export type QuestionAdmin = {
  id: string;
  prompt: string;
  choices: string[];
  correct_index: number;
  order_index: number;
  points: number;
};

export type ProctoringProfile = {
  id: string;
  name: string;
  strictness: "low" | "medium" | "high" | "lockdown";
  warn_threshold: number;
  flag_threshold: number;
  terminate_threshold: number;
  require_android_camera: boolean;
  blacklist_apps_csv: string;
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
    body: {
      title: string;
      duration_minutes: number;
      instructions?: string;
      proctoring_profile_id?: string | null;
    },
    signal?: AbortSignal,
  ) =>
    request<ExamSummary>("/exams", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),
  getExam: (examId: string, signal?: AbortSignal) =>
    request<ExamDetail>(`/exams/${examId}`, { signal }),
  updateExam: (
    examId: string,
    body: Partial<{
      title: string;
      duration_minutes: number;
      instructions: string;
      proctoring_profile_id: string | null;
    }>,
    signal?: AbortSignal,
  ) =>
    request<ExamDetail>(`/exams/${examId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
      signal,
    }),
  listQuestions: (examId: string, signal?: AbortSignal) =>
    request<QuestionAdmin[]>(`/exams/${examId}/questions`, { signal }),
  createQuestion: (
    examId: string,
    body: {
      prompt: string;
      choices: string[];
      correct_index: number;
      points?: number;
    },
    signal?: AbortSignal,
  ) =>
    request<QuestionAdmin>(`/exams/${examId}/questions`, {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),
  deleteQuestion: (examId: string, questionId: string, signal?: AbortSignal) =>
    request<void>(`/exams/${examId}/questions/${questionId}`, { method: "DELETE", signal }),
  updateQuestion: (
    examId: string,
    questionId: string,
    body: {
      prompt: string;
      choices: string[];
      correct_index: number;
      points?: number;
    },
    signal?: AbortSignal,
  ) =>
    request<QuestionAdmin>(`/exams/${examId}/questions/${questionId}`, {
      method: "PUT",
      body: JSON.stringify(body),
      signal,
    }),
  publishExam: (examId: string, signal?: AbortSignal) =>
    request<ExamSummary>(`/exams/${examId}/publish`, { method: "POST", signal }),
  listProctoringProfiles: (signal?: AbortSignal) =>
    request<ProctoringProfile[]>("/proctoring-profiles", { signal }),
  createProctoringProfile: (body: Omit<ProctoringProfile, "id">, signal?: AbortSignal) =>
    request<ProctoringProfile>("/proctoring-profiles", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),
  updateProctoringProfile: (
    profileId: string,
    body: Omit<ProctoringProfile, "id">,
    signal?: AbortSignal,
  ) =>
    request<ProctoringProfile>(`/proctoring-profiles/${profileId}`, {
      method: "PUT",
      body: JSON.stringify(body),
      signal,
    }),
  listAttempts: (signal?: AbortSignal) =>
    request<AttemptSummary[]>("/sessions/attempts", { signal }),
  getReport: (sessionId: string, signal?: AbortSignal) =>
    request<IntegrityReport>(`/reports/sessions/${sessionId}`, { signal }),
};

export function riskLabel(score: number): string {
  if (score >= 0.65) return "High";
  if (score >= 0.4) return "Review";
  return "OK";
}

export function sourceLabel(source: string): string {
  if (source === "android_camera") return "Phone";
  if (source === "screen") return "Screen";
  return "Webcam";
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

/** Short, simple admin summary even if the API still returns old long text. */
export function shortSummary(
  text: string,
  opts: { pct: number; photoCount: number; flags: string[] },
): string {
  const photos = opts.photoCount;
  const flagBits: string[] = [];
  for (const f of opts.flags) {
    const fl = f.toLowerCase();
    if (fl.includes("phone") || fl.includes("android") || fl.includes("no_face")) {
      flagBits.push("phone / camera");
    } else if (fl.includes("app")) {
      flagBits.push("blocked app");
    } else if (fl.includes("face") || fl.includes("gaze") || fl.includes("gesture")) {
      flagBits.push("face");
    }
  }
  const warnings = [...new Set(flagBits)].join(", ") || "none";
  if (opts.pct < 35 && opts.flags.length === 0 && photos === 0) {
    return "Looks fine. No strong cheating signs. You can accept the score.";
  }
  if (opts.pct < 65) {
    return `Please check. Saved ${photos} photo(s). Warnings: ${warnings}. Open photos, then decide.`;
  }
  return `High concern (${Math.round(opts.pct)}% risk). Saved ${photos} photo(s). Warnings: ${warnings}. Review photos before accepting.`;
}

export function shortEventText(text: string): string {
  const t = (text || "").trim();
  const low = t.toLowerCase();
  if (low.includes("left the") && low.includes("app")) return "Left the phone camera app.";
  if (low.includes("phone") && (low.includes("moved") || low.includes("cover"))) {
    return "Phone moved or covered.";
  }
  if (low.includes("phone") && (low.includes("disconnect") || low.includes("lost"))) {
    return "Phone camera lost.";
  }
  if (low.includes("blocked") || low.includes("prohibited") || low.includes("flagged app")) {
    return "Opened a blocked app.";
  }
  if (low.includes("looked away")) return "Looked away from the screen.";
  if (low.includes("more than one") || low.includes("second face")) {
    return "More than one face on camera.";
  }
  if (low.includes("no face")) return "No face on camera.";
  if (t.length > 90) return `${t.slice(0, 87)}…`;
  return t || "Event";
}

export function displayStudentName(name: string): string {
  const n = (name || "").trim();
  if (!n || n.toLowerCase() === "demo student" || n.toLowerCase() === "student") {
    return "Student (name not typed)";
  }
  return n;
}
