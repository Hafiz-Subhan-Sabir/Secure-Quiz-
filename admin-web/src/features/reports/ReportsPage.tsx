import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api,
  formatWhen,
  riskLabel,
  sourceLabel,
  type IntegrityReport,
} from "@/shared/api/client";

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

  return (
    <>
      <p className="section-lead">
        <strong>What to do:</strong> check the integrity score, then browse photos left → right. Screen
        snapshots appear alongside webcam / phone frames.
      </p>

      <section className="panel" style={{ marginBottom: "1rem" }}>
        <form className="report-form" onSubmit={onLoad}>
          <label className="field">
            <span>Attempt / Session ID</span>
            <input
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="Paste an ID, or open one from Attempts & flags"
              required
            />
          </label>
          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? "Loading…" : "Show report"}
          </button>
          <Link className="ghost-btn compact" to="/attempts">
            Pick from attempts
          </Link>
        </form>
        {error ? <p className="error-text" style={{ marginTop: "0.75rem" }}>{error}</p> : null}
      </section>

      {report ? (
        <>
          <section className="panel report-hero">
            <div>
              <p className="eyebrow">Student</p>
              <h2>
                {report.student_name || "Unknown student"}{" "}
                <span className="soft">· {report.exam_title}</span>
              </h2>
              <p className="summary-plain">{report.summary_plain}</p>
              {report.student_email ? (
                <p className="status" style={{ marginTop: "0.5rem" }}>{report.student_email}</p>
              ) : null}
            </div>
            <div className="score-box">
              <p className="label">Integrity concern</p>
              <p className="value">{pct}%</p>
              <p className="status">{riskLabel(report.cheating_probability)}</p>
              <div className="risk-bar" aria-hidden>
                <span style={{ width: `${Math.min(100, pct)}%` }} />
              </div>
            </div>
          </section>

          <div className="split-2" style={{ marginTop: "1rem" }}>
            <section className="panel">
              <h2>Captured evidence ({report.evidence.length})</h2>
              {!report.evidence.length ? (
                <p className="status">No photos were saved for this attempt.</p>
              ) : (
                <>
                  {active ? (
                    <figure className="evidence-stage">
                      <img src={active.image_data_uri} alt={active.plain_language} />
                      <figcaption>
                        <strong>{active.gesture_label}</strong> · {sourceLabel(active.source)}
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
              <h2>What happened (timeline)</h2>
              <div className="timeline">
                {report.timeline.map((item) => (
                  <div className="timeline-item" key={String(item.event_id)}>
                    <span className="status">{formatWhen(String(item.ts))}</span>
                    <div>
                      <strong>{String(item.plain_language ?? item.type)}</strong>
                      <div className="status">{String(item.type)}</div>
                    </div>
                    <strong>{Math.round(Number(item.severity) * 100)}%</strong>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </>
      ) : null}
    </>
  );
}
