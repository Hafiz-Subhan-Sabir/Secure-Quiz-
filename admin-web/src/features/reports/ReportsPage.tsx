import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api,
  formatWhen,
  riskLabel,
  sourceLabel,
  type IntegrityReport,
} from "@/shared/api/client";

function flagChip(flag: string): string {
  const f = flag.toLowerCase();
  if (f.includes("phone")) return "Phone";
  if (f.includes("app") || f.includes("browser")) return "App";
  if (f.includes("face") || f.includes("gaze")) return "Face";
  if (f.includes("screen")) return "Screen";
  return flag.replace(/_/g, " ").slice(0, 18);
}

export function ReportsPage() {
  const [params] = useSearchParams();
  const [sessionId, setSessionId] = useState(params.get("session") ?? "");
  const [report, setReport] = useState<IntegrityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activePhoto, setActivePhoto] = useState<string | null>(null);

  const pct = useMemo(
    () => (report ? Math.round(report.cheating_probability * 1000) / 10 : 0),
    [report],
  );

  async function load(id: string) {
    setLoading(true);
    setError(null);
    setReport(null);
    setActivePhoto(null);
    try {
      const data = await api.getReport(id.trim());
      setReport(data);
      if (data.evidence[0]) setActivePhoto(data.evidence[0].event_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this report.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const fromUrl = params.get("session");
    if (fromUrl) {
      setSessionId(fromUrl);
      void load(fromUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  async function onLoad(e: FormEvent) {
    e.preventDefault();
    await load(sessionId);
  }

  const active = report?.evidence.find((e) => e.event_id === activePhoto) ?? null;
  const needsReview = pct >= 40 || (report?.flags.length ?? 0) > 0 || (report?.evidence.length ?? 0) > 0;

  return (
    <>
      <p className="section-lead">Check score → browse photos → decide.</p>

      <section className="panel" style={{ marginBottom: "1rem" }}>
        <form className="report-form" onSubmit={onLoad}>
          <label className="field">
            <span>Session ID</span>
            <input
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="Paste ID or open from Attempts"
              required
            />
          </label>
          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? "Loading…" : "Show report"}
          </button>
          <Link className="ghost-btn compact" to="/attempts">
            Attempts
          </Link>
        </form>
        {error ? <p className="error-text" style={{ marginTop: "0.75rem" }}>{error}</p> : null}
      </section>

      {report ? (
        <>
          <section
            className="panel"
            style={{
              marginBottom: "1rem",
              borderColor: needsReview ? "rgba(180, 35, 24, 0.35)" : "rgba(31, 122, 77, 0.3)",
              background: needsReview ? "rgba(180, 35, 24, 0.06)" : "rgba(31, 122, 77, 0.06)",
            }}
          >
            <div className="attempt-top">
              <div>
                <h2 style={{ margin: 0, color: needsReview ? "var(--danger)" : "var(--ok)" }}>
                  {needsReview ? "Please review" : "Looks fine"}
                </h2>
                <p className="status" style={{ marginTop: "0.35rem" }}>
                  <strong>{report.student_name || "Student"}</strong> · {report.exam_title}
                </p>
              </div>
              <span className={`pill risk-${pct >= 65 ? "high" : pct >= 40 ? "mid" : "ok"}`}>
                {riskLabel(report.cheating_probability)} · {pct}%
              </span>
            </div>
            <div className="chip-row" style={{ marginTop: "0.75rem" }}>
              {report.flags.length
                ? report.flags.map((f) => (
                    <span key={f} className="chip chip-danger">
                      {flagChip(f)}
                    </span>
                  ))
                : (
                  <span className="chip chip-ok">No warnings</span>
                )}
              <span className="chip">{report.evidence.length} photo(s)</span>
              {report.quiz_max_score ? (
                <span className="chip">
                  Score {report.quiz_score}/{report.quiz_max_score}
                </span>
              ) : null}
            </div>
            <p className="summary-plain" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
              <strong>Summary: </strong>
              {report.summary_plain}
            </p>
          </section>

          <div className="split-2">
            <section className="panel">
              <h2>Evidence ({report.evidence.length})</h2>
              {!report.evidence.length ? (
                <p className="status">No photos saved.</p>
              ) : (
                <>
                  {active ? (
                    <figure className="evidence-stage">
                      <img src={active.image_data_uri} alt={active.plain_language} />
                      <figcaption>
                        <strong>{sourceLabel(active.source)}</strong>
                        <br />
                        {active.plain_language}
                        <br />
                        <span className="status">{formatWhen(active.captured_at)}</span>
                      </figcaption>
                    </figure>
                  ) : null}
                  <div className="evidence-thumbs">
                    {report.evidence.map((frame) => (
                      <button
                        key={frame.event_id}
                        type="button"
                        className={`thumb ${activePhoto === frame.event_id ? "on" : ""}`}
                        onClick={() => setActivePhoto(frame.event_id)}
                      >
                        <img src={frame.image_data_uri} alt="" />
                        <span>
                          {sourceLabel(frame.source).split(" ")[0]} · {Math.round(frame.severity * 100)}%
                        </span>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </section>

            <section className="panel">
              <h2>Timeline</h2>
              <div className="timeline">
                {report.timeline.map((item) => {
                  const plain = String(item.plain_language || item.gesture_label || item.type || "event");
                  const short = plain.length > 64 ? plain.slice(0, 61) + "…" : plain;
                  return (
                    <div className="timeline-item" key={String(item.event_id)}>
                      <span className="status">{formatWhen(String(item.ts))}</span>
                      <div>
                        <strong>{short}</strong>
                      </div>
                      <strong>{Math.round(Number(item.severity) * 100)}%</strong>
                    </div>
                  );
                })}
              </div>
            </section>
          </div>
        </>
      ) : null}
    </>
  );
}
