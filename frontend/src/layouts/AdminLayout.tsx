// src/layouts/AdminLayout.tsx
import React from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { ArrowLeft, LayoutDashboard, Users, Shield, Activity, HeartPulse } from "lucide-react";

const navItems = [
  { to: "/admin", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/admin/users", label: "Usuarios", icon: Users, end: false },
  { to: "/admin/security", label: "Seguridad", icon: Shield, end: false },
  { to: "/admin/metrics", label: "Performance", icon: Activity, end: false },
  { to: "/admin/health", label: "Health", icon: HeartPulse, end: false },
];

export const AdminLayout: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 border-r border-border flex flex-col">
        <div className="p-4 border-b border-border">
          <button
            onClick={() => navigate("/dashboard")}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft size={16} />
            Volver al dashboard
          </button>
          <p className="mt-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Panel Admin
          </p>
        </div>

        <nav className="flex-1 p-2 space-y-1">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  );
};
