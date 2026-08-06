import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";

/** Must be signed in. */
export function ProtectedRoute() {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}

/** Admin console only — students are redirected away. */
export function AdminOnlyRoute() {
  const { token, role } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  if (role === "student") return <Navigate to="/student-portal" replace />;
  if (role !== "admin" && role !== "instructor") {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
