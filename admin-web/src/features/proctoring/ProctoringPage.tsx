import { useMemo, useState } from "react";

type Strictness = "low" | "medium" | "high" | "lockdown";

const PRESETS: Record<
  Strictness,
  { warn: number; flag: number; terminate: number; requireAndroid: boolean; blurb: string }
> = {
  low: {
    warn: 0.55,
    flag: 0.8,
    terminate: 0.95,
    requireAndroid: false,
    blurb: "Gentle watch. Photos still save on strong alerts, but the quiz rarely stops early.",
  },
  medium: {
    warn: 0.4,
    flag: 0.65,
    terminate: 0.9,
    requireAndroid: true,
    blurb: "Recommended. Phone camera required. Unusual face gestures trigger photo capture.",
  },
  high: {
    warn: 0.3,
    flag: 0.55,
    terminate: 0.8,
    requireAndroid: true,
    blurb: "Strict. Smaller gestures can raise concern and more photos are kept for review.",
  },
  lockdown: {
    warn: 0.2,
    flag: 0.4,
    terminate: 0.7,
    requireAndroid: true,
    blurb: "Highest stakes. Very sensitive facial checks and room monitoring.",
  },
};

const CAPTURE_RULES = [
  {
    title: "Laptop webcam (primary)",
    body: "Reads face landmarks in real time (MediaPipe). When a risky FaceGest gesture appears — head shake, gaze away, wink+tilt, long mouth-open — a photo is saved with the attempt.",
  },
  {
    title: "Phone camera (secondary)",
    body: "After QR pairing, the Android app watches the side/rear of the room. Unusual room movement saves an environment photo so the webcam’s blind spots are covered.",
  },
  {
    title: "What you see in Admin",
    body: "Student attempts lists who took which quiz. Photo reports show the integrity % in plain words, plus a gallery of every auto-captured image.",
  },
];

export function ProctoringPage() {
  const [strictness, setStrictness] = useState<Strictness>("medium");
  const preset = useMemo(() => PRESETS[strictness], [strictness]);

  return (
    <>
      <p className="section-lead">
        These rules decide how sensitive facial recognition is, and when IntelliQuiz should save a
        camera photo for you to review later.
      </p>

      <div className="split-2">
        <section className="panel">
          <h2>How strict should monitoring be?</h2>
          <label className="field">
            <span>Choose a level (easy words)</span>
            <select
              value={strictness}
              onChange={(e) => setStrictness(e.target.value as Strictness)}
            >
              <option value="low">Low — practice quizzes</option>
              <option value="medium">Medium — normal exams (recommended)</option>
              <option value="high">High — important exams</option>
              <option value="lockdown">Lockdown — highest stakes</option>
            </select>
          </label>
          <p className="summary-plain">{preset.blurb}</p>

          <div className="metric-row" style={{ marginTop: "1rem", marginBottom: 0 }}>
            <article className="metric">
              <p className="label">Soft warning</p>
              <p className="value">{Math.round(preset.warn * 100)}%</p>
            </article>
            <article className="metric">
              <p className="label">Flag for review</p>
              <p className="value">{Math.round(preset.flag * 100)}%</p>
            </article>
            <article className="metric">
              <p className="label">Stop exam</p>
              <p className="value">{Math.round(preset.terminate * 100)}%</p>
            </article>
          </div>
          <p className="section-lead" style={{ marginTop: "1rem", marginBottom: 0 }}>
            Phone camera required:{" "}
            <strong>{preset.requireAndroid ? "Yes" : "No"}</strong>
          </p>
        </section>

        <section className="panel">
          <h2>Facial recognition & photo capture</h2>
          <ul className="plain-list stacked">
            {CAPTURE_RULES.map((rule) => (
              <li key={rule.title}>
                <strong>{rule.title}</strong>
                <p>{rule.body}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="panel" style={{ marginTop: "1rem" }}>
        <h2>Blocked apps during the quiz (Desktop)</h2>
        <p className="section-lead">
          The student computer tries to detect these apps so they cannot browse or remote-control
          during the exam:
        </p>
        <div className="chip-row">
          {["Chrome", "Edge", "Firefox", "Discord", "TeamViewer", "AnyDesk", "Zoom"].map((app) => (
            <span className="chip" key={app}>
              {app}
            </span>
          ))}
        </div>
      </section>
    </>
  );
}
