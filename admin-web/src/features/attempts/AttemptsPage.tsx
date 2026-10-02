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
        Open a flagged student → review photos → decide.
      </p>

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
            Needs review ({flaggedCount})
          </button>
        </div>
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
                  <h3>{a.student_name}</h3>
                  <p className="status">{a.student_email}</p>
                </div>
                <span className={`pill risk-${riskTier}`}>
                  {riskLabel(risk)} · {Math.round(risk * 100)}%
                </span>
              </div>
              <p className="attempt-exam">{a.exam_title}</p>

              <div className="chip-row">
                {a.flagged ? (
                  <span className="chip chip-danger">Review needed</span>
                ) : (
                  <span className="chip chip-ok">Clear</span>
                )}
                <span className="chip">
                  {a.evidence_count > 0 ? `${a.evidence_count} photo(s)` : "No photos"}
                </span>
                <span className={`chip ${a.android_paired ? "chip-ok" : "chip-muted"}`}>
                  Phone {a.android_paired ? "paired" : "off"}
                </span>
                {a.quiz_max_score ? (
                  <span className="chip">
                    Score {a.quiz_score ?? 0}/{a.quiz_max_score}
                  </span>
                ) : null}
              </div>

              <p className="status" style={{ margin: 0 }}>
                {formatWhen(a.started_at)}
              </p>

              <Link className="primary-btn block" to={`/reports?session=${a.session_id}`}>
                Review evidence
              </Link>
            </article>
          );
        })}
        {!visible.length && !error ? (
          <p className="empty-state">No attempts yet.</p>
        ) : null}
      </div>
    </>
  );
}
