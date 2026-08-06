import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/features/auth/AuthContext";
import { LoginPage } from "@/features/auth/LoginPage";
import { StudentPortalPage } from "@/features/auth/StudentPortalPage";
import { AttemptsPage } from "@/features/attempts/AttemptsPage";
import { ExamsPage } from "@/features/exams/ExamsPage";
import { OverviewPage } from "@/features/overview/OverviewPage";
import { ProctoringPage } from "@/features/proctoring/ProctoringPage";
import { ReportsPage } from "@/features/reports/ReportsPage";
import { AppShell } from "@/shared/ui/AppShell";
import { AdminOnlyRoute } from "./ProtectedRoute";

function HomeRedirect() {
  const { token, role } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  if (role === "student") return <Navigate to="/student-portal" replace />;
  return <Navigate to="/overview" replace />;
}

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/student-portal" element={<StudentPortalPage />} />
        <Route element={<AdminOnlyRoute />}>
          <Route element={<AppShell />}>
            <Route path="/overview" element={<OverviewPage />} />
            <Route path="/exams" element={<ExamsPage />} />
            <Route path="/attempts" element={<AttemptsPage />} />
            <Route path="/proctoring" element={<ProctoringPage />} />
            <Route path="/reports" element={<ReportsPage />} />
          </Route>
        </Route>
        <Route path="*" element={<HomeRedirect />} />
      </Routes>
    </AuthProvider>
  );
}
