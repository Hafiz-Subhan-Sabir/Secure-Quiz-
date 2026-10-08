import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";

const TITLES: Record<string, { title: string; hint: string }> = {
  "/overview": {
    title: "Home",
    hint: "Quick status and shortcuts.",
  },
  "/exams": {
    title: "Exams",
    hint: "Create questions and publish.",
  },
  "/attempts": {
    title: "Students",
    hint: "Open a student → check photos → decide.",
  },
  "/proctoring": {
    title: "Rules",
    hint: "When photos are saved.",
  },
  "/reports": {
    title: "Photos",
    hint: "Risk score + photo proof.",
  },
};

function NavIcon({ kind }: { kind: string }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  switch (kind) {
    case "home":
      return (
        <svg {...common}>
          <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5z" />
        </svg>
      );
    case "exams":
      return (
        <svg {...common}>
          <path d="M8 4h8a2 2 0 0 1 2 2v14l-6-3-6 3V6a2 2 0 0 1 2-2z" />
        </svg>
      );
    case "students":
      return (
        <svg {...common}>
          <circle cx="9" cy="8" r="3" />
          <circle cx="17" cy="9" r="2.5" />
          <path d="M3 19c1.5-3 4-4.5 6-4.5S14.5 16 16 19" />
          <path d="M15 19c.6-1.6 1.8-2.6 3.5-2.6" />
        </svg>
      );
    case "rules":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8" />
          <path d="M12 8v5" />
          <path d="M12 16h.01" />
        </svg>
      );
    case "photos":
      return (
        <svg {...common}>
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <circle cx="9" cy="12" r="2.5" />
          <path d="m13 16 2.5-3 3.5 4" />
        </svg>
      );
    default:
      return null;
  }
}

export function AppShell() {
  const { role, logout } = useAuth();
  const { pathname } = useLocation();
  const meta = TITLES[pathname] ?? TITLES["/overview"];

  return (
    <div className="app-shell">
      <aside className="side-nav">
        <div className="brand-block">
          <p className="wordmark">IntelliQuiz</p>
          <p className="tag">Admin</p>
        </div>
        <nav className="nav-links" aria-label="Primary">
          <NavLink to="/overview" className={({ isActive }) => (isActive ? "active" : undefined)}>
            <NavIcon kind="home" />
            <span>Home</span>
          </NavLink>
          <NavLink to="/exams" className={({ isActive }) => (isActive ? "active" : undefined)}>
            <NavIcon kind="exams" />
            <span>Exams</span>
          </NavLink>
          <NavLink to="/attempts" className={({ isActive }) => (isActive ? "active" : undefined)}>
            <NavIcon kind="students" />
            <span>Students</span>
          </NavLink>
          <NavLink to="/proctoring" className={({ isActive }) => (isActive ? "active" : undefined)}>
            <NavIcon kind="rules" />
            <span>Rules</span>
          </NavLink>
          <NavLink to="/reports" className={({ isActive }) => (isActive ? "active" : undefined)}>
            <NavIcon kind="photos" />
            <span>Photos</span>
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
