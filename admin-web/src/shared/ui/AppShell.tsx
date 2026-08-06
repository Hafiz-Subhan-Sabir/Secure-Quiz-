import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";

const TITLES: Record<string, { eyebrow: string; title: string; hint: string }> = {
  "/overview": {
    eyebrow: "Control center",
    title: "Exam integrity at a glance",
    hint: "Publish exams, watch attempts, and open photo evidence when a student breaks the rules.",
  },
  "/exams": {
    eyebrow: "Catalog",
    title: "Create & publish exams",
    hint: "Students only see exams you mark as Published.",
  },
  "/attempts": {
    eyebrow: "Students",
    title: "Attempts & flags",
    hint: "Step 1: open a flagged student. Step 2: review their evidence photos.",
  },
  "/proctoring": {
    eyebrow: "Rules",
    title: "Face & camera rules",
    hint: "Plain-language guidance for when photos are captured during a quiz.",
  },
  "/reports": {
    eyebrow: "Evidence",
    title: "Photo reports",
    hint: "Step 2: review webcam, phone, and screen photos for this student.",
  },
};

export function AppShell() {
  const { role, logout } = useAuth();
  const { pathname } = useLocation();
  const meta = TITLES[pathname] ?? TITLES["/overview"];

  return (
    <div className="app-shell">
      <aside className="side-nav">
        <div className="brand-block">
          <p className="wordmark">IntelliQuiz</p>
          <p className="tag">Admin · AI exam security</p>
        </div>
        <nav className="nav-links" aria-label="Primary">
          <NavLink to="/overview" className={({ isActive }) => (isActive ? "active" : undefined)}>
            Home
          </NavLink>
          <NavLink to="/exams" className={({ isActive }) => (isActive ? "active" : undefined)}>
            Exams
          </NavLink>
          <NavLink to="/attempts" className={({ isActive }) => (isActive ? "active" : undefined)}>
            Attempts &amp; flags
          </NavLink>
          <NavLink to="/proctoring" className={({ isActive }) => (isActive ? "active" : undefined)}>
            Face &amp; camera rules
          </NavLink>
          <NavLink to="/reports" className={({ isActive }) => (isActive ? "active" : undefined)}>
            Photo reports
          </NavLink>
        </nav>
        <div className="nav-footer">
          <span className="role-chip">{role ?? "user"}</span>
          <button type="button" className="ghost-btn" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>

      <div className="main-pane">
        <header className="topbar">
          <div>
            <p className="eyebrow">{meta.eyebrow}</p>
            <h1>{meta.title}</h1>
            <p className="top-hint">{meta.hint}</p>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
