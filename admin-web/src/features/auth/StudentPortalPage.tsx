import { Navigate } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";

/**
 * Students do not use this website for exams.
 * They must use the Desktop app + paired Android phone camera.
 */
export function StudentPortalPage() {
  const { token, logout, role } = useAuth();

  if (!token) return <Navigate to="/login" replace />;
  if (role !== "student") return <Navigate to="/overview" replace />;

  return (
    <div className="auth-shell student-gate">
      <section className="auth-visual" aria-label="Brand">
        <p className="wordmark">IntelliQuiz</p>
        <p className="caption">
          You’re signed in as a student. Exams are taken on the Desktop app — not in this browser.
        </p>
      </section>

      <section className="auth-form-pane">
        <div className="auth-form student-gate-card">
          <h1>Use the Desktop app</h1>
          <p className="lead">
            This website is only for teachers and admins (create exams, review face photos, check
            integrity).
          </p>

          <ol className="guide-steps">
            <li>
              Open the <strong>IntelliQuiz Desktop</strong> app on your exam computer.
            </li>
            <li>
              Sign in with your student account (
              <code>student@intelliquiz.dev</code> for the demo).
            </li>
            <li>Start the published quiz and complete face verification.</li>
            <li>
              Scan the QR code with the <strong>Android</strong> app to link the phone camera.
            </li>
            <li>Answer the questions. Abnormal face gestures auto-save photos for review.</li>
          </ol>

          <p className="status" style={{ marginTop: "0.75rem" }}>
            Current role: <strong>{role}</strong>
          </p>

          <div className="gate-actions">
            <button type="button" className="primary-btn" onClick={logout}>
              Sign out
            </button>
            <button
              type="button"
              className="ghost-btn"
              onClick={() => {
                logout();
                window.location.href = "/login";
              }}
            >
              Sign in as admin instead
            </button>
          </div>

          <p className="section-lead" style={{ marginBottom: 0, marginTop: "0.5rem" }}>
            Demo desktop check:{" "}
            <code>cd desktop && python -m intelliQuiz_desktop.cli smoke</code>
          </p>
        </div>
      </section>
    </div>
  );
}
