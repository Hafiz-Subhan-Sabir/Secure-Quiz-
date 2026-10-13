import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  displayStudentName,
  formatWhen,
  riskLabel,
  type AttemptSummary,
} from "@/shared/api/client";

export function AttemptsPage() {
  const [attempts, setAttempts] = useState<AttemptSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "flagged">("flagged");
  const [clearing, setClearing] = useState(false);

  async function refresh(signal?: AbortSignal) {
    const list = await api.listAttempts(signal);
    setAttempts(list);
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
      <div className="toolbar">
        <div className="seg">
          <button
            type="button"
            className={filter === "all" ? "seg-on" : ""}
            onClick={() => setFilter("all")}
          >
            All ({attempts.length})
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
          <p className="empty-state">No students yet.</p>
        ) : null}
      </div>
    </>
  );
}
