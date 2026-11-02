import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  displayStudentName,
  formatWhen,
  riskLabel,
  type AttemptSummary,
  type StudentAccount,
} from "@/shared/api/client";

export function AttemptsPage() {
  const [attempts, setAttempts] = useState<AttemptSummary[]>([]);
  const [students, setStudents] = useState<StudentAccount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "flagged">("flagged");
  const [clearing, setClearing] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [createdMsg, setCreatedMsg] = useState<string | null>(null);

  async function refresh(signal?: AbortSignal) {
    const [list, accounts] = await Promise.all([
      api.listAttempts(signal),
      api.listStudents(signal),
    ]);
    setAttempts(list);
    setStudents(accounts);
    if (!list.some((a) => a.flagged)) setFilter("all");
  }

  useEffect(() => {
    const ac = new AbortController();
    void refresh(ac.signal).catch((err: unknown) => {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Could not load students.");
    });
    return () => ac.abort();
  }, []);

  async function onCreateStudent(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setCreatedMsg(null);
    try {
      const created = await api.createStudent({
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      });
      setFullName("");
      setEmail("");
      setPassword("");
      setCreatedMsg(`Added ${created.full_name} (${created.email}). They can sign in on the Desktop app.`);
      setStudents(await api.listStudents());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add student.");
    } finally {
      setSaving(false);
    }
  }

  async function removeStudent(id: string, name: string) {
    if (!window.confirm(`Remove login for ${name}? Past exam reports stay until you clear them.`)) {
      return;
    }
    setError(null);
    try {
      await api.deleteStudent(id);
      setStudents((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove student.");
    }
  }

  async function clearAllReports() {
    if (
      !window.confirm(
        "Delete ALL student attempts and photo reports? Exams and logins stay. This cannot be undone.",
      )
    ) {
      return;
    }
    setClearing(true);
    setError(null);
    try {
      await api.clearAllAttempts();
      setAttempts([]);
      setFilter("all");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not clear reports.");
    } finally {
      setClearing(false);
    }
  }

  async function clearOne(sessionId: string, name: string) {
    if (!window.confirm(`Delete report for ${name}?`)) return;
    setError(null);
    try {
      await api.clearAttempt(sessionId);
      setAttempts((prev) => prev.filter((a) => a.session_id !== sessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete this report.");
    }
  }

  const flaggedCount = useMemo(() => attempts.filter((a) => a.flagged).length, [attempts]);
  const visible = useMemo(
    () => (filter === "flagged" ? attempts.filter((a) => a.flagged) : attempts),
    [attempts, filter],
  );

  return (
    <>
      <section className="panel" style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ marginTop: 0 }}>Add student</h2>
        <p className="status" style={{ marginTop: 0 }}>
          Create a login for the Desktop exam app. Students do not use this admin website for quizzes.
        </p>
        <form className="stack-form" onSubmit={(e) => void onCreateStudent(e)}>
          <label className="field">
            <span>Full name</span>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Ali Khan"
              required
            />
          </label>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ali@school.edu"
              required
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="text"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 6 characters"
              minLength={6}
              required
            />
          </label>
          <button type="submit" className="primary-btn" disabled={saving}>
            {saving ? "Adding…" : "Add student"}
          </button>
        </form>
        {createdMsg ? <p className="status" style={{ color: "var(--ok)" }}>{createdMsg}</p> : null}

        <h3 style={{ marginTop: "1.25rem" }}>Student logins ({students.length})</h3>
        {students.length ? (
          <ul className="plain-list stacked">
            {students.map((s) => (
              <li key={s.id}>
                <strong>{s.full_name}</strong>
                <p>
                  {s.email}
                  <button
                    type="button"
                    className="ghost-btn compact"
                    style={{ marginLeft: "0.75rem" }}
                    onClick={() => void removeStudent(s.id, s.full_name)}
                  >
                    Remove
                  </button>
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty-state">No student accounts yet — add one above.</p>
        )}
      </section>

      <div className="toolbar">
        <div className="seg">
          <button
            type="button"
            className={filter === "all" ? "seg-on" : ""}
            onClick={() => setFilter("all")}
          >
            Attempts ({attempts.length})
          </button>
          <button
            type="button"
            className={filter === "flagged" ? "seg-on" : ""}
            onClick={() => setFilter("flagged")}
          >
            Review ({flaggedCount})
          </button>
        </div>
        <button
          type="button"
          className="ghost-btn compact"
          onClick={() => void clearAllReports()}
          disabled={clearing || !attempts.length}
        >
          {clearing ? "Clearing…" : "Clear all reports"}
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      <div className="attempt-grid">
        {visible.map((a) => {
          const risk = a.last_risk_score;
          const riskTier = risk >= 0.65 ? "high" : risk >= 0.4 ? "mid" : "ok";
          return (
            <article key={a.session_id} className={`attempt-card ${a.flagged ? "is-flagged" : ""}`}>
              <div className="attempt-top">
                <div>
                  <h3>{displayStudentName(a.student_name)}</h3>
                  <p className="status">{a.exam_title}</p>
                </div>
                <span className={`pill risk-${riskTier}`}>
                  {riskLabel(risk)} · {Math.round(risk * 100)}%
                </span>
              </div>

              <div className="chip-row">
                {a.flagged ? (
                  <span className="chip chip-danger">Needs review</span>
                ) : (
                  <span className="chip chip-ok">OK</span>
                )}
                <span className="chip vis-chip">
                  <span className="mini-cam" aria-hidden />
                  {a.evidence_count} photos
                </span>
                <span className={`chip ${a.android_paired ? "chip-ok" : "chip-muted"}`}>
                  <span className={`mini-phone ${a.android_paired ? "on" : ""}`} aria-hidden />
                  Phone {a.android_paired ? "on" : "off"}
                </span>
                {a.quiz_max_score ? (
                  <span className="chip">
                    {a.quiz_score ?? 0}/{a.quiz_max_score}
                  </span>
                ) : null}
              </div>

              <p className="status" style={{ margin: 0 }}>
                {formatWhen(a.started_at)}
              </p>

              <div className="attempt-actions">
                <Link className="primary-btn block" to={`/reports?session=${a.session_id}`}>
                  Open photos
                </Link>
                <button
                  type="button"
                  className="ghost-btn compact"
                  onClick={() => void clearOne(a.session_id, displayStudentName(a.student_name))}
                >
                  Delete
                </button>
              </div>
            </article>
          );
        })}
        {!visible.length && !error ? (
          <p className="empty-state">No attempts yet. Students take exams on the Desktop app.</p>
        ) : null}
      </div>
    </>
  );
}
