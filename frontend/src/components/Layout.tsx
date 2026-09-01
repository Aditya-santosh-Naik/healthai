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
        {/* min-w-0 lets the nav below shrink instead of forcing the row wider
            than the screen. Without it a flex child refuses to go below its
            content width and the whole page scrolls sideways: at 375px the
            document was 714px wide. */}
        <div className="mx-auto flex h-16 w-full max-w-5xl min-w-0 items-center gap-3 px-4 sm:gap-6 sm:px-6">
          <Link
            to="/"
            className="flex shrink-0 items-center gap-2 font-semibold tracking-tight"
          >
            <Activity className="h-5 w-5 text-primary" />
            <span className="hidden sm:inline">HealthAI</span>
          </Link>

          {/* Scrolls within itself on a phone rather than pushing the page
              wide. Every destination stays reachable, which a collapsed
              hamburger would also achieve but at the cost of a new component
              the spec says not to build. */}
          <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto text-sm [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "shrink-0 whitespace-nowrap rounded-md px-3 py-1.5 transition-colors",
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

          <div className="ml-auto flex shrink-0 items-center gap-3">
            {/* The name is the first thing worth losing on a narrow screen:
                the user knows who they are, and Sign out must stay reachable. */}
            {profile && (
              <span className="hidden text-sm text-muted-foreground sm:inline">
                {profile.name}
              </span>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <LogOut className="h-4 w-4 shrink-0" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">{children}</main>

      <DisclaimerBar />
    </div>
  );
}
