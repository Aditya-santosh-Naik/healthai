import { Link, NavLink, useNavigate } from "react-router-dom";
import { Activity, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

/** Invariant 11: the disclaimer is always on screen, never dismissible. */
export function DisclaimerBar() {
  return (
    <div className="border-t bg-muted/60 px-6 py-3 text-center text-xs leading-relaxed text-muted-foreground">
      HealthAI is an educational project, not a medical device. It does not diagnose,
      prescribe, or replace professional medical care. Always consult a qualified doctor
      or pharmacist about your health.
    </div>
  );
}

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/consultation", label: "Consultation" },
  { to: "/history", label: "History" },
  { to: "/documents", label: "Documents" },
  { to: "/profile", label: "Profile" },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const { profile, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-screen flex-col bg-muted/30">
      <header className="border-b bg-background">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center gap-6 px-6">
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <Activity className="h-5 w-5 text-primary" />
            HealthAI
          </Link>

          <nav className="flex items-center gap-1 text-sm">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 transition-colors",
                    isActive
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {profile && (
              <span className="text-sm text-muted-foreground">{profile.name}</span>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">{children}</main>

      <DisclaimerBar />
    </div>
  );
}
