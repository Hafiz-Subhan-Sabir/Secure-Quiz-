import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, type ExamSummary } from "@/shared/api/client";

export function ExamsPage() {
  const [exams, setExams] = useState<ExamSummary[]>([]);
  const [title, setTitle] = useState("");
  const [minutes, setMinutes] = useState(60);
  const [instructions, setInstructions] = useState(
    "Keep your face visible. Pair the Android camera before starting.",
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [publishingId, setPublishingId] = useState<string | null>(null);

  const sorted = useMemo(
    () =>
      [...exams].sort((a, b) => {
        if (a.status === b.status) return a.title.localeCompare(b.title);
        return a.status === "published" ? -1 : 1;
      }),
    [exams],
  );

  async function refresh(signal?: AbortSignal) {
    setExams(await api.listExams(signal));
  }

  useEffect(() => {
    const ac = new AbortController();
    void refresh(ac.signal).catch((err: unknown) => {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Failed to load exams");
    });
    return () => ac.abort();
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.createExam({ title, duration_minutes: minutes, instructions });
      setTitle("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setSaving(false);
    }
  }

  async function onPublish(id: string) {
    setPublishingId(id);
    setError(null);
    try {
      await api.publishExam(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Publish failed");
    } finally {
      setPublishingId(null);
    }
  }

  return (
    <>
      <p className="section-lead">
        Create a quiz, then click Publish. Only published exams appear for students on the Desktop
        app. After they finish, check Student attempts for face photos and risk.
      </p>

      <div className="split-2">
        <section className="panel">
          <h2>Create exam</h2>
          <form onSubmit={onCreate} className="stack-form">
            <label className="field">
              <span>Title</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Midterm — Secure Systems"
                required
              />
            </label>
            <label className="field">
              <span>Duration (minutes)</span>
              <input
                type="number"
                min={1}
                max={600}
                value={minutes}
                onChange={(e) => setMinutes(Number(e.target.value))}
                required
              />
            </label>
            <label className="field">
              <span>Instructions</span>
              <textarea
                rows={4}
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
              />
            </label>
            {error ? <p className="error-text">{error}</p> : null}
            <button className="primary-btn" type="submit" disabled={saving}>
              {saving ? "Creating…" : "Create exam"}
            </button>
          </form>
        </section>

        <section className="panel">
          <h2>Inventory</h2>
          <ul className="list-plain">
            {sorted.map((exam) => (
              <li key={exam.id}>
                <div>
                  <strong>{exam.title}</strong>
                  <div className="status">{exam.duration_minutes} minutes</div>
                </div>
                <div className="row-actions">
                  <span className={`status ${exam.status}`}>{exam.status}</span>
                  {exam.status !== "published" ? (
                    <button
                      type="button"
                      className="ghost-btn compact"
                      disabled={publishingId === exam.id}
                      onClick={() => void onPublish(exam.id)}
                    >
                      {publishingId === exam.id ? "…" : "Publish"}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
            {!sorted.length ? <li>No exams yet.</li> : null}
          </ul>
        </section>
      </div>
    </>
  );
}
