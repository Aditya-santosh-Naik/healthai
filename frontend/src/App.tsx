import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/lib/auth";
import Login from "@/pages/Login";
import Onboarding from "@/pages/Onboarding";
import Dashboard from "@/pages/Dashboard";
import Profile from "@/pages/Profile";
import Consultation from "@/pages/Consultation";
import Documents from "@/pages/Documents";
import { HistoryDetailPage, HistoryList } from "@/pages/History";

function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
      Loading...
    </div>
  );
}

/** Signed in and onboarded, or bounced to wherever the user needs to be. */
function Protected({ children }: { children: React.ReactNode }) {
  const { ready, authenticated, profile } = useAuth();
  if (!ready) return <Loading />;
  if (!authenticated) return <Navigate to="/login" replace />;
  if (!profile) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  const { ready, authenticated, profile } = useAuth();
  if (!ready) return <Loading />;

  return (
    <Routes>
      <Route
        path="/login"
        element={authenticated ? <Navigate to="/" replace /> : <Login />}
      />
      <Route
        path="/onboarding"
        element={
          !authenticated ? (
            <Navigate to="/login" replace />
          ) : profile ? (
            <Navigate to="/" replace />
          ) : (
            <Onboarding />
          )
        }
      />
      <Route
        path="/"
        element={
          <Protected>
            <Dashboard />
          </Protected>
        }
      />
      <Route
        path="/consultation"
        element={
          <Protected>
            <Consultation />
          </Protected>
        }
      />
      <Route
        path="/history"
        element={
          <Protected>
            <HistoryList />
          </Protected>
        }
      />
      <Route
        path="/history/:id"
        element={
          <Protected>
            <HistoryDetailPage />
          </Protected>
        }
      />
      <Route
        path="/documents"
        element={
          <Protected>
            <Documents />
          </Protected>
        }
      />
      <Route
        path="/profile"
        element={
          <Protected>
            <Profile />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
