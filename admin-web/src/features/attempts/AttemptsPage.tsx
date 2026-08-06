import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  formatWhen,
  riskLabel,
  type AttemptSummary,
} from "@/shared/api/client";

export function AttemptsPage() {
  const [attempts, setAttempts] = useState<AttemptSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "flagged">("flagged");

  useEffect(() => {
    const ac = new AbortController();
    void api
      .listAttempts(ac.signal)
      .then((list) => {
        setAttempts(list);
        if (!list.some((a) => a.flagged)) setFilter("all");
      })
      .catch((err: unknown) => {
        if ((err as Error).name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Could not load attempts.");
      });
    return () => ac.abort();
  }, []);

  const flaggedCount = useMemo(() => attempts.filter((a) => a.flagged).length, [attempts]);
  const visible = useMemo(
    () => (filter === "flagged" ? attempts.filter((a) => a.flagged) : attempts),
    [attempts, filter],
  );

  return (
    <>
      <p className="section-lead">
        <strong>What to do:</strong> open any flagged student → Review evidence → decide if the attempt is valid.
        Flagged means high risk or auto-captured photos.
      </p>

      <div className="toolbar">
        <div className="seg">
          <button
            type="button"
            className={filter === "all" ? "seg-on" : ""}
            onClick={() => setFilter("all")}
          >
            All attempts ({attempts.length})
          </button>
          <button
            type="button"
            className={filter === "flagged" ? "seg-on" : ""}
            onClick={() => setFilter("flagged")}
          >
            Needs review ({flaggedCount})
          </button>
        </div>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      <div className="attempt-grid">
        {visible.map((a) => {
          const risk = a.last_risk_score;
          return (
            <article key={a.session_id} className={`attempt-card ${a.flagged ? "is-flagged" : ""}`}>
              <div className="attempt-top">
                <div>
                  <h3>{a.student_name}</h3>
                  <p className="status">{a.student_email}</p>
                </div>
                <span className={`pill risk-${risk >= 0.65 ? "high" : risk >= 0.4 ? "mid" : "ok"}`}>
                  {riskLabel(risk)} · {Math.round(risk * 100)}%
                </span>
              </div>
              <p className="attempt-exam">{a.exam_title}</p>
              {a.flagged ? (
                <p className="flag-banner">
                  {a.evidence_count > 0
                    ? `${a.evidence_count} photo(s) captured when rules were broken`
                    : "Elevated integrity risk — open the report"}
                </p>
              ) : null}
              <dl className="attempt-meta">
                <div>
                  <dt>Started</dt>
                  <dd>{formatWhen(a.started_at)}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{a.status}</dd>
                </div>
                <div>
                  <dt>Phone camera</dt>
                  <dd>{a.android_paired ? "Paired" : "Not paired"}</dd>
                </div>
                <div>
                  <dt>Auto photos</dt>
                  <dd>{a.evidence_count} saved</dd>
                </div>
              </dl>
              <Link className="primary-btn block" to={`/reports?session=${a.session_id}`}>
                Review evidence
              </Link>
            </article>
          );
        })}
        {!visible.length && !error ? (
          <p className="empty-state">
            No attempts yet. When a student finishes (or is mid-exam), their session appears here.
            A demo attempt with sample face photos is seeded on first API start.
          </p>
        ) : null}
      </div>
    </>
  );
}
