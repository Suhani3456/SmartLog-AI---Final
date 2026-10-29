/**
 * App shell: fixed left sidebar (232px) + top bar + content outlet.
 * Design per SmartLog design brief.
 */

import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Gauge,
  Info,
  Radar,
  Search,
  Table2,
  UploadCloud,
  Moon,
  Sun,
} from "lucide-react";
import { cn } from "../lib/utils";
import { useEffect, useState } from "react";

const NAV = [
  { to: "/", label: "Dashboard", icon: BarChart3 },
  { to: "/live", label: "Live Monitor", icon: Activity },
  { to: "/classify", label: "Classify log", icon: Search },
  { to: "/incidents", label: "Incidents", icon: Table2 },
  { to: "/anomalies", label: "Anomaly explorer", icon: Radar },
  { to: "/model", label: "Model performance", icon: Gauge },
  { to: "/upload", label: "Upload logs", icon: UploadCloud },
  { to: "/about", label: "About", icon: Info },
];

export function Layout() {
  const { pathname } = useLocation();
  const title = NAV.find((n) => n.to === pathname)?.label ?? "SmartLog AI";
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    if (dark) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }, [dark]);

  return (
    <div className="flex min-h-screen bg-bg text-text">
      <nav className="fixed left-0 top-0 h-screen w-[232px] shrink-0 border-r border-border bg-surface flex flex-col">
        <div className="px-4 py-4">
          <div className="flex items-baseline gap-1">
            <span className="text-[14px] font-semibold">SmartLog</span>
            <span className="font-mono text-[11px] text-muted">AI</span>
          </div>
        </div>
        <ul className="mt-2 flex-1 space-y-0.5 px-2">
          {NAV.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2.5 rounded-sm px-2 py-1.5 text-[13px] transition-colors",
                    isActive
                      ? "bg-subtle text-accent"
                      : "text-text hover:bg-subtle/60"
                  )
                }
              >
                <Icon size={16} strokeWidth={1.5} />
                <span>{label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="px-4 py-3 text-[11px] text-muted border-t border-border">
          RV College of Engineering · EL Phase I
        </div>
      </nav>
      <div className="flex-1 ml-[232px] flex flex-col min-h-screen">
        <header className="flex items-center justify-between border-b border-border bg-surface px-6 py-2.5">
          <h1 className="text-[14px] font-medium">{title}</h1>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-[12px] text-muted">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
              <span>Streaming</span>
            </div>
            <button
              onClick={() => setDark(!dark)}
              className="inline-flex items-center justify-center h-7 w-7 rounded-sm hover:bg-subtle"
              aria-label="Toggle theme"
            >
              {dark ? <Sun size={15} strokeWidth={1.5} /> : <Moon size={15} strokeWidth={1.5} />}
            </button>
          </div>
        </header>
        <main className="flex-1">
          <div className="mx-auto max-w-content p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
