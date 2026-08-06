import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/shared/api/client";
import { useAuth } from "./AuthContext";

export function LoginPage() {
  const { setSession } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("admin@intelliquiz.dev");
  const [password, setPassword] = useState("Admin123!");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.login(email, password);
      setSession(res.access_token, res.role);
      if (res.role === "student") {
        navigate("/student-portal");
      } else {
        navigate("/overview");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-shell">
      <section className="auth-visual" aria-label="Brand">
        <p className="wordmark">IntelliQuiz</p>
        <p className="caption">
          See which students broke exam rules — webcam, phone, and screen evidence in one place.
        </p>
        <ul className="auth-bullets">
          <li>Attempts &amp; flags for every desktop quiz</li>
          <li>Auto photos when face or room looks wrong</li>
          <li>Publish exams in minutes</li>
        </ul>
      </section>

      <section className="auth-form-pane">
        <form className="auth-form" onSubmit={onSubmit}>
          <h1>Admin sign in</h1>
          <p className="lead">
            Teachers and admins only. Students use the Desktop exam client — not this site.
          </p>

          <label className="field">
            <span>Email</span>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              autoComplete="username"
              required
            />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="current-password"
              required
            />
          </label>

          {error ? <p className="error-text">{error}</p> : null}

          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? "Signing in…" : "Enter control center"}
          </button>
        </form>
      </section>
    </div>
  );
}
