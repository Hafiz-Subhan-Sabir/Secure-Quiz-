import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api,
  displayStudentName,
  formatTime,
  formatWhen,
  riskLabel,
  shortEventText,
  shortSummary,
  sourceLabel,
  type IntegrityReport,
} from "@/shared/api/client";

function flagChip(flag: string): string {
  const f = flag.toLowerCase();
  if (f.includes("phone") || f.includes("android")) return "Phone";
  if (f.includes("app") || f.includes("browser")) return "Blocked app";
  if (f.includes("face") || f.includes("gaze") || f.includes("gesture")) return "Face";
  if (f.includes("screen")) return "Screen";
  return "Alert";
}

type TimelineGroup = {
  key: string;
  label: string;
  count: number;
  severity: number;
  ts: string;
};

function isNoiseEvent(item: Record<string, unknown>): boolean {
  const typ = String(item.type || "").toLowerCase();
  if (typ === "heartbeat" || typ === "submit") return true;
  const plain = String(item.plain_language || item.gesture_label || "").toLowerCase();
  const sev = Number(item.severity) || 0;
  // Routine phone room frames — photos already cover these.
  if (plain.includes("room view photo") || plain.includes("room camera captured")) {
    return sev < 0.75;
  }
  if (plain.includes("exam lockdown") || plain.includes("other apps blocked")) {
    return sev < 0.5;
  }
  return false;
}

function groupTimeline(items: Array<Record<string, unknown>>): TimelineGroup[] {
  const map = new Map<string, TimelineGroup>();
  for (const item of items) {
    if (isNoiseEvent(item)) continue;
    const raw = String(item.plain_language || item.gesture_label || item.type || "Alert");
    const label = shortEventText(raw);
    const ts = String(item.ts || "");
    let minuteKey = ts;
    try {
      const d = new Date(ts);
      if (!Number.isNaN(d.getTime())) {
        minuteKey = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}-${d.getHours()}-${d.getMinutes()}`;
      }
    } catch {
      /* keep ts */
    }
    const key = `${label}|${minuteKey}`;
    const sev = Number(item.severity) || 0;
    const prev = map.get(key);
    if (prev) {
      prev.count += 1;
      prev.severity = Math.max(prev.severity, sev);
    } else {
      map.set(key, { key, label, count: 1, severity: sev, ts });
    }
  }
  return [...map.values()].sort(
    (a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime(),
  );
}

export function ReportsPage() {
  const [params] = useSearchParams();
  const fromUrl = params.get("session") ?? "";
  const [sessionId, setSessionId] = useState(fromUrl);
  const [report, setReport] = useState<IntegrityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activePhoto, setActivePhoto] = useState<string | null>(null);
  const [showIdBox, setShowIdBox] = useState(!fromUrl);

  const pct = useMemo(
    () => (report ? Math.round(report.cheating_probability * 1000) / 10 : 0),
    [report],
  );

  const timeline = useMemo(
    () => (report ? groupTimeline(report.timeline) : []),
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
    const id = params.get("session");
    if (id) {
      setSessionId(id);
      setShowIdBox(false);
      void load(id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  async function onLoad(e: FormEvent) {
    e.preventDefault();
    await load(sessionId);
  }

  const active = report?.evidence.find((e) => e.event_id === activePhoto) ?? null;
  const needsReview = pct >= 40 || (report?.flags.length ?? 0) > 0;

  return (
    <>
      <div className="report-toolbar">
        <Link className="ghost-btn compact" to="/attempts">
          ← Students
        </Link>
        {!showIdBox ? (
          <button type="button" className="ghost-btn compact" onClick={() => setShowIdBox(true)}>
            Paste ID
          </button>
        ) : null}
      </div>

      {showIdBox ? (
        <section className="panel" style={{ marginBottom: "1rem" }}>
          <form className="report-form" onSubmit={onLoad}>
            <label className="field">
              <span>Session ID</span>
              <input
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
                placeholder="Paste ID from Students list"
                required
              />
            </label>
            <button className="primary-btn" type="submit" disabled={loading}>
              {loading ? "Loading…" : "Open"}
            </button>
          </form>
        </section>
      ) : null}

      {error ? <p className="error-text">{error}</p> : null}
      {loading && !report ? <p className="status">Loading photos…</p> : null}

      {report ? (
        <>
          <section
            className={`panel report-summary ${needsReview ? "is-warn" : "is-ok"}`}
            style={{ marginBottom: "1rem" }}
          >
            <div className="report-summary-top">
              <div>
                <p className="report-kicker">{needsReview ? "Needs your review" : "Looks fine"}</p>
                <h2 className="report-student">{displayStudentName(report.student_name)}</h2>
                <p className="status" style={{ margin: "0.2rem 0 0" }}>
                  {report.exam_title}
                  {report.quiz_max_score
                    ? ` · Score ${report.quiz_score}/${report.quiz_max_score}`
                    : ""}
                </p>
              </div>
              <div className={`risk-bubble risk-${pct >= 65 ? "high" : pct >= 40 ? "mid" : "ok"}`}>
                <strong>{pct}%</strong>
                <span>{riskLabel(report.cheating_probability)}</span>
              </div>
            </div>
            <p className="summary-plain">
              {shortSummary(report.summary_plain, {
                pct,
                photoCount: report.evidence.length,
                flags: report.flags,
              })}
            </p>
            <div className="chip-row">
              {report.flags.length ? (
                [...new Set(report.flags.map(flagChip))].map((f) => (
                  <span key={f} className="chip chip-danger">
                    {f}
                  </span>
                ))
              ) : (
                <span className="chip chip-ok">No warnings</span>
              )}
              <span className="chip">{report.evidence.length} photos</span>
              <span className="chip">{timeline.length} alerts</span>
            </div>
          </section>

          <div className="split-2 report-split">
            <section className="panel">
              <h2>Photos</h2>
              {!report.evidence.length ? (
                <p className="status">No photos for this attempt.</p>
              ) : (
                <>
                  {active ? (
                    <figure className="evidence-stage">
                      <img src={active.image_data_uri} alt="" />
                      <figcaption>
                        <span className="chip">{sourceLabel(active.source)}</span>{" "}
                        {shortEventText(active.plain_language)}
                        <span className="status"> · {formatWhen(active.captured_at)}</span>
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
                        title={shortEventText(frame.plain_language)}
                      >
                        <img src={frame.image_data_uri} alt="" />
                        <span>{sourceLabel(frame.source)}</span>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </section>

            <section className="panel">
              <h2>Alerts</h2>
              {!timeline.length ? (
                <p className="status">No important alerts.</p>
              ) : (
                <div className="timeline timeline-compact">
                  {timeline.map((item) => (
                    <div className="timeline-row" key={item.key}>
                      <time>{formatTime(item.ts)}</time>
                      <span className="timeline-label">
                        {item.label}
                        {item.count > 1 ? ` ×${item.count}` : ""}
                      </span>
                      <span className="timeline-sev">{Math.round(item.severity * 100)}%</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        </>
      ) : null}
    </>
  );
}
