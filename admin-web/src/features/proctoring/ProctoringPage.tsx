import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, type ProctoringProfile } from "@/shared/api/client";

type Strictness = ProctoringProfile["strictness"];

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
    body: "Reads face landmarks in real time (MediaPipe). Students enroll their face once per PC; each exam verifies identity match. Risky gestures trigger photo capture.",
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
  const [profiles, setProfiles] = useState<ProctoringProfile[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [strictness, setStrictness] = useState<Strictness>("medium");
  const [name, setName] = useState("Custom profile");
  const [blacklist, setBlacklist] = useState("chrome,discord,teamviewer,anydesk,edge,firefox");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const preset = useMemo(() => PRESETS[strictness], [strictness]);
  const selected = profiles.find((p) => p.id === selectedId) ?? null;

  async function refresh() {
    const list = await api.listProctoringProfiles();
    setProfiles(list);
    if (!selectedId && list[0]) {
      setSelectedId(list[0].id);
      applyProfile(list[0]);
    }
  }

  function applyProfile(p: ProctoringProfile) {
    setStrictness(p.strictness);
    setName(p.name);
    setBlacklist(p.blacklist_apps_csv);
  }

  useEffect(() => {
    void refresh().catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load profiles"),
    );
  }, []);

  useEffect(() => {
    if (selected) applyProfile(selected);
  }, [selectedId, profiles.length]);

  useEffect(() => {
    if (!selectedId) {
      setName(`${strictness.charAt(0).toUpperCase()}${strictness.slice(1)} profile`);
    }
  }, [strictness, selectedId]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const body = {
      name,
      strictness,
      warn_threshold: preset.warn,
      flag_threshold: preset.flag,
      terminate_threshold: preset.terminate,
      require_android_camera: preset.requireAndroid,
      blacklist_apps_csv: blacklist,
    };
    try {
      if (selectedId) {
        await api.updateProctoringProfile(selectedId, body);
      } else {
        const created = await api.createProctoringProfile(body);
        setSelectedId(created.id);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <p className="section-lead">
        Proctoring profiles are saved to the server and applied when students start an exam on
        Desktop. Assign a profile when creating an exam.
      </p>

      <div className="split-2">
        <section className="panel">
          <h2>Proctoring profiles</h2>
          <form onSubmit={onSave} className="stack-form">
            <label className="field">
              <span>Saved profile</span>
              <select
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
              >
                <option value="">— New profile —</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Profile name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} required />
            </label>
            <label className="field">
              <span>Strictness level</span>
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
            <label className="field">
              <span>Blocked apps (comma-separated)</span>
              <input value={blacklist} onChange={(e) => setBlacklist(e.target.value)} />
            </label>
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
              Phone camera required: <strong>{preset.requireAndroid ? "Yes" : "No"}</strong>
            </p>
            {error ? <p className="error-text">{error}</p> : null}
            <button className="primary-btn" type="submit" disabled={saving}>
              {saving ? "Saving…" : selectedId ? "Update profile" : "Create profile"}
            </button>
          </form>
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
    </>
  );
}
