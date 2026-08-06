import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AttemptSummary, type ExamSummary } from "@/shared/api/client";

export function OverviewPage() {
  const [exams, setExams] = useState<ExamSummary[]>([]);
  const [attempts, setAttempts] = useState<AttemptSummary[]>([]);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

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
        setError(err instanceof Error ? err.message : "Could not load the home screen.");
      }
    })();
    return () => ac.abort();
  }, []);

  const published = exams.filter((e) => e.status === "published").length;
  const flagged = attempts.filter((a) => a.flagged).length;

  return (
    <>
      <section className="hero-banner">
        <div>
          <p className="hero-kicker">Built for clarity</p>
          <h2>Watch every quiz with confidence</h2>
          <p>
            IntelliQuiz watches the student’s face on the laptop camera, pairs a phone camera for
            room coverage, and <strong>automatically saves a photo</strong> when an abnormal face
            gesture is detected (looking away, head shake, second person, and more).
          </p>
        </div>
        <Link className="primary-btn" to="/attempts">
          Check student attempts
        </Link>
      </section>

      <div className="metric-row">
        <article className="metric">
          <p className="label">System</p>
          <p className="value">{apiOk == null ? "…" : apiOk ? "Ready" : "Offline"}</p>
        </article>
        <article className="metric">
          <p className="label">Published exams</p>
          <p className="value">{published}</p>
        </article>
        <article className="metric">
          <p className="label">Attempts needing review</p>
          <p className="value">{flagged}</p>
        </article>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      <section className="panel guide-panel">
        <h2>How to run a secure quiz (simple steps)</h2>
        <ol className="guide-steps">
          <li>
            <strong>Create an exam</strong> on the Exams page, then click <em>Publish</em> so
            students can see it.
          </li>
          <li>
            <strong>Student opens the Desktop app</strong>, signs in, and must pass a camera check
            (PC webcam with one face, or phone camera via QR if there is no webcam).
          </li>
          <li>
            <strong>During the quiz</strong>, AI watches face gestures. Rule breaks capture a webcam
            photo and screen snapshot, synced for your review.
          </li>
          <li>
            <strong>You review here</strong>: open Attempts &amp; flags → pick a student → see risk,
            timeline, and the photo gallery.
          </li>
        </ol>
      </section>

      <div className="split-2">
        <section className="panel">
          <h2>What gets photographed automatically?</h2>
          <ul className="plain-list">
            <li>Head shaking or looking around the room</li>
            <li>Wink + head tilt (strong “looking away” signal)</li>
            <li>Mouth open for a long time (possible talking)</li>
            <li>Second face appearing in the webcam</li>
            <li>Unusual movement in the phone’s room camera</li>
          </ul>
          <Link className="text-link" to="/proctoring">
            Read the face & camera rules →
          </Link>
        </section>

        <section className="panel">
          <h2>Quick links</h2>
          <ul className="list-plain">
            <li>
              <span>Publish an exam for students</span>
              <Link className="ghost-btn compact" to="/exams">
                Exams
              </Link>
            </li>
            <li>
              <span>Review flagged students &amp; photos</span>
              <Link className="ghost-btn compact" to="/attempts">
                Attempts &amp; flags
              </Link>
            </li>
            <li>
              <span>Open a full photo report</span>
              <Link className="ghost-btn compact" to="/reports">
                Reports
              </Link>
            </li>
          </ul>
        </section>
      </div>
    </>
  );
}
