import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AttemptSummary, type ExamSummary } from "@/shared/api/client";

type AiMetrics = {
  lab_accuracy_pct: number;
  meets_90_target: boolean;
  dataset_samples: number;
  note: string;
};

export function OverviewPage() {
  const [exams, setExams] = useState<ExamSummary[]>([]);
  const [attempts, setAttempts] = useState<AttemptSummary[]>([]);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ai, setAi] = useState<AiMetrics | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    (async () => {
      try {
        const [health, list, atts] = await Promise.all([
          api.health(ac.signal),
          api.listExams(ac.signal),
          api.listAttempts(ac.signal),
        ]);
        setApiOk(health.status === "ok");
        setExams(list);
        setAttempts(atts);
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setApiOk(false);
        setError(err instanceof Error ? err.message : "Could not load home.");
      }
    })();
    void fetch("/ai-metrics.json", { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: AiMetrics | null) => {
        if (data) setAi(data);
      })
      .catch(() => undefined);
    return () => ac.abort();
  }, []);

  const published = exams.filter((e) => e.status === "published").length;
  const flagged = attempts.filter((a) => a.flagged).length;

  return (
    <>
      <div className="metric-row visual-metrics">
        <article className={`metric ${apiOk ? "tone-ok" : apiOk === false ? "tone-bad" : ""}`}>
          <div className="metric-icon" aria-hidden>
            <span className={`dot ${apiOk ? "on" : ""}`} />
          </div>
          <p className="label">Server</p>
          <p className="value">{apiOk == null ? "…" : apiOk ? "Online" : "Down"}</p>
        </article>
        <article className="metric">
          <div className="metric-icon" aria-hidden>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M8 4h8a2 2 0 0 1 2 2v14l-6-3-6 3V6a2 2 0 0 1 2-2z" />
            </svg>
          </div>
          <p className="label">Live exams</p>
          <p className="value">{published}</p>
        </article>
        <article className={`metric ${flagged ? "tone-warn" : "tone-ok"}`}>
          <div className="metric-icon" aria-hidden>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="8" />
              <path d="M12 8v5M12 16h.01" />
            </svg>
          </div>
          <p className="label">Need review</p>
          <p className="value">{flagged}</p>
        </article>
        <article className={`metric ${ai?.meets_90_target ? "tone-ok" : ""}`}>
          <div className="metric-icon" aria-hidden>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="9" r="3.5" />
              <path d="M6 19c1.2-3 3.5-4.5 6-4.5S16.8 16 18 19" />
            </svg>
          </div>
          <p className="label">Face AI (lab)</p>
          <p className="value">{ai ? `${ai.lab_accuracy_pct}%` : "—"}</p>
        </article>
      </div>

      {ai ? <p className="status ai-note">{ai.note}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}

      <section className="action-grid">
        <Link className="action-card" to="/exams">
          <span className="action-glyph">1</span>
          <strong>Make exam</strong>
          <span>Add questions · Publish</span>
        </Link>
        <Link className="action-card" to="/attempts">
          <span className="action-glyph">2</span>
          <strong>Check students</strong>
          <span>Flags · photos · scores</span>
        </Link>
        <Link className="action-card" to="/reports">
          <span className="action-glyph">3</span>
          <strong>Open photos</strong>
          <span>Webcam · phone · screen</span>
        </Link>
        <Link className="action-card" to="/proctoring">
          <span className="action-glyph">?</span>
          <strong>Rules</strong>
          <span>When photos save</span>
        </Link>
      </section>

      <section className="panel" style={{ marginTop: "1rem" }}>
        <h2>During a quiz</h2>
        <div className="icon-row">
          <div className="icon-pill">
            <span className="ip-dot ok" /> PC face
          </div>
          <div className="icon-pill">
            <span className="ip-dot ok" /> Phone room
          </div>
          <div className="icon-pill">
            <span className="ip-dot warn" /> Blocked apps
          </div>
          <div className="icon-pill">
            <span className="ip-dot bad" /> Auto photo
          </div>
        </div>
        <p className="status" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
          Phone pairing is required. If the phone leaves, the quiz pauses and a photo can be saved.
        </p>
      </section>
    </>
  );
}
