import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Camera,
  LayoutDashboard,
  LogOut,
  MapPin,
  PlayCircle,
  Settings as SettingsIcon,
  ShieldAlert,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useCurrentUser, useLogout } from "@/hooks/useAuth";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/live", label: "Live Monitoring", icon: Activity },
  { to: "/incidents", label: "Incidents", icon: AlertTriangle },
  { to: "/cameras", label: "Cameras", icon: Camera },
  { to: "/zones", label: "Zone Editor", icon: MapPin },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/demo", label: "Demo Mode", icon: PlayCircle },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export function AppShell() {
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  return (
    <div className="flex min-h-screen bg-bg">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-surface">
        <div className="flex items-center gap-2 border-b border-border px-4 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md border border-border-strong text-teal">
            <ShieldAlert className="h-4 w-4" />
          </div>
          <div>
            <p className="text-sm font-semibold text-text leading-none">SmartVision</p>
            <p className="text-[11px] text-text-faint leading-none mt-1">Ops Console</p>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 px-2 py-3">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-surface-raised text-text border border-border-strong"
                    : "text-text-muted hover:bg-surface-hover hover:text-text border border-transparent",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-border px-3 py-3">
          <div className="mb-2 px-1">
            <p className="truncate text-sm text-text">{user?.full_name}</p>
            <p className="truncate text-xs text-text-faint capitalize">{user?.role}</p>
          </div>
          <button
            onClick={() => logout.mutate()}
            className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-xs text-text-muted hover:bg-surface-hover hover:text-text"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex items-center justify-between border-b border-border bg-surface px-6 py-4">
      <div>
        <h1 className="text-base font-semibold text-text">{title}</h1>
        {description && <p className="mt-0.5 text-sm text-text-muted">{description}</p>}
      </div>
      {actions}
    </header>
  );
}
