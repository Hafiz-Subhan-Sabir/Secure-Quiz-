import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  api,
  type ExamSummary,
  type ProctoringProfile,
  type QuestionAdmin,
} from "@/shared/api/client";

const EMPTY_CHOICES = ["", "", "", ""];

export function ExamsPage() {
  const [exams, setExams] = useState<ExamSummary[]>([]);
  const [profiles, setProfiles] = useState<ProctoringProfile[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [questions, setQuestions] = useState<QuestionAdmin[]>([]);
  const [title, setTitle] = useState("");
  const [minutes, setMinutes] = useState(60);
  const [instructions, setInstructions] = useState(
    "Keep your face visible. Pair the Android camera before starting.",
  );
  const [profileId, setProfileId] = useState<string>("");
  const [qPrompt, setQPrompt] = useState("");
  const [qChoices, setQChoices] = useState<string[]>([...EMPTY_CHOICES]);
  const [qCorrect, setQCorrect] = useState(0);
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

  const selected = sorted.find((e) => e.id === selectedId) ?? null;

  async function refresh(signal?: AbortSignal) {
    const [examList, profileList] = await Promise.all([
      api.listExams(signal),
      api.listProctoringProfiles(signal),
    ]);
    setExams(examList);
    setProfiles(profileList);
    if (!profileId && profileList[0]) setProfileId(profileList[0].id);
  }

  async function loadQuestions(examId: string) {
    setQuestions(await api.listQuestions(examId));
  }

  useEffect(() => {
    const ac = new AbortController();
    void refresh(ac.signal).catch((err: unknown) => {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Failed to load exams");
    });
    return () => ac.abort();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setQuestions([]);
      return;
    }
    void loadQuestions(selectedId).catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load questions"),
    );
  }, [selectedId]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const created = await api.createExam({
        title,
        duration_minutes: minutes,
        instructions,
        proctoring_profile_id: profileId || null,
      });
      setTitle("");
      await refresh();
      setSelectedId(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setSaving(false);
    }
  }

  async function onAddQuestion(e: FormEvent) {
    e.preventDefault();
    if (!selectedId) return;
    const choices = qChoices.map((c) => c.trim()).filter(Boolean);
    if (choices.length < 2) {
      setError("Add at least two answer choices.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createQuestion(selectedId, {
        prompt: qPrompt.trim(),
        choices,
        correct_index: Math.min(qCorrect, choices.length - 1),
      });
      setQPrompt("");
      setQChoices([...EMPTY_CHOICES]);
      setQCorrect(0);
      await loadQuestions(selectedId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Add question failed");
    } finally {
      setSaving(false);
    }
  }

  async function onDeleteQuestion(questionId: string) {
    if (!selectedId) return;
    setError(null);
    try {
      await api.deleteQuestion(selectedId, questionId);
      await loadQuestions(selectedId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
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
        Create exams, add MCQ questions, then publish. Students pick a published quiz on the Desktop
        app. Add at least one question before publishing.
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
              <span>Proctoring profile</span>
              <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                <option value="">Default (none)</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.strictness})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Instructions</span>
              <textarea
                rows={3}
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
                  <button
                    type="button"
                    className="ghost-btn compact"
                    style={{ fontWeight: selectedId === exam.id ? 700 : 400 }}
                    onClick={() => setSelectedId(exam.id)}
                  >
                    {exam.title}
                  </button>
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

      {selected ? (
        <section className="panel" style={{ marginTop: "1rem" }}>
          <h2>Questions — {selected.title}</h2>
          {questions.length ? (
            <ul className="plain-list stacked">
              {questions.map((q, idx) => (
                <li key={q.id}>
                  <strong>
                    {idx + 1}. {q.prompt}
                  </strong>
                  <ul>
                    {q.choices.map((c, i) => (
                      <li key={i}>
                        {i === q.correct_index ? "✓ " : ""}
                        {c}
                      </li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    className="ghost-btn compact"
                    onClick={() => void onDeleteQuestion(q.id)}
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="section-lead">No questions yet — add at least one before publishing.</p>
          )}

          <form onSubmit={onAddQuestion} className="stack-form" style={{ marginTop: "1rem" }}>
            <label className="field">
              <span>Question prompt</span>
              <textarea
                rows={2}
                value={qPrompt}
                onChange={(e) => setQPrompt(e.target.value)}
                required
              />
            </label>
            {qChoices.map((choice, i) => (
              <label className="field" key={i}>
                <span>Choice {String.fromCharCode(65 + i)}</span>
                <input
                  value={choice}
                  onChange={(e) => {
                    const next = [...qChoices];
                    next[i] = e.target.value;
                    setQChoices(next);
                  }}
                />
              </label>
            ))}
            <label className="field">
              <span>Correct answer</span>
              <select value={qCorrect} onChange={(e) => setQCorrect(Number(e.target.value))}>
                {qChoices.map((c, i) =>
                  c.trim() ? (
                    <option key={i} value={i}>
                      {String.fromCharCode(65 + i)} — {c}
                    </option>
                  ) : null,
                )}
              </select>
            </label>
            <button className="primary-btn" type="submit" disabled={saving || !selectedId}>
              Add question
            </button>
          </form>
        </section>
      ) : null}
    </>
  );
}
