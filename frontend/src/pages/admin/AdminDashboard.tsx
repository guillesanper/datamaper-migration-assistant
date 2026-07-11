// src/pages/admin/AdminDashboard.tsx
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { adminService } from "../../services/admin_service";
import { Users, ShieldAlert, UserCheck, Lock, Activity, FolderOpen, TrendingUp } from "lucide-react";
import type { DayCount, ActivityTypeCount, ActiveUser } from "../../types/admin_types";

interface StatCardProps {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  description?: string;
}

const StatCard: React.FC<StatCardProps> = ({ label, value, icon, description }) => (
  <div className="rounded-lg border border-border bg-card p-4 flex flex-col gap-2">
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-muted-foreground">{icon}</span>
    </div>
    <span className="text-2xl font-bold text-foreground">{value}</span>
    {description && (
      <span className="text-xs text-muted-foreground">{description}</span>
    )}
  </div>
);

const SeverityBadge: React.FC<{ severity: string }> = ({ severity }) => {
  const colors: Record<string, string> = {
    info: "bg-blue-100 text-blue-800",
    warning: "bg-yellow-100 text-yellow-800",
    error: "bg-red-100 text-red-800",
    critical: "bg-red-200 text-red-900 font-semibold",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs ${
        colors[severity] ?? "bg-gray-100 text-gray-800"
      }`}
    >
      {severity}
    </span>
  );
};

const BarChart: React.FC<{ data: DayCount[]; label: string }> = ({ data, label }) => {
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <div>
      <p className="text-xs text-muted-foreground mb-2">{label}</p>
      {data.length === 0 ? (
        <p className="text-xs text-muted-foreground">Sin datos en este período.</p>
      ) : (
        <div className="flex items-end gap-1 h-24">
          {data.map((d) => (
            <div key={d.date} className="flex-1 flex flex-col items-center gap-0.5 group relative">
              <div
                className="w-full bg-primary/60 rounded-t hover:bg-primary transition-colors"
                style={{ height: `${Math.max((d.count / max) * 88, 2)}px` }}
              />
              <span className="text-[9px] text-muted-foreground hidden group-hover:block absolute -top-5 bg-card border border-border px-1 rounded whitespace-nowrap">
                {d.date.slice(5)}: {d.count}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const HorizontalBarChart: React.FC<{ data: ActivityTypeCount[] }> = ({ data }) => {
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <div className="space-y-1.5">
      {data.length === 0 ? (
        <p className="text-xs text-muted-foreground">Sin actividad en este período.</p>
      ) : (
        data.map((d) => (
          <div key={d.type} className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground font-mono w-36 truncate shrink-0">
              {d.type}
            </span>
            <div className="flex-1 bg-muted rounded-full h-2">
              <div
                className="bg-primary/70 h-2 rounded-full"
                style={{ width: `${(d.count / max) * 100}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground w-8 text-right">{d.count}</span>
          </div>
        ))
      )}
    </div>
  );
};

export const AdminDashboard: React.FC = () => {
  const { data: statsData, isLoading: statsLoading } = useQuery({
    queryKey: ["admin", "user-stats"],
    queryFn: () => adminService.getUserStats(),
  });

  const { data: secStats, isLoading: secLoading } = useQuery({
    queryKey: ["admin", "security-stats"],
    queryFn: () => adminService.getSecurityStats(7),
  });

  const { data: recentEvents, isLoading: eventsLoading } = useQuery({
    queryKey: ["admin", "security-events-recent"],
    queryFn: () => adminService.getSecurityEvents({ limit: 10 }),
  });

  const { data: bizMetrics, isLoading: bizLoading } = useQuery({
    queryKey: ["admin", "business-metrics"],
    queryFn: () => adminService.getBusinessMetrics(30),
  });

  const { data: platformActivity, isLoading: platformLoading } = useQuery({
    queryKey: ["admin", "platform-activity"],
    queryFn: () => adminService.getPlatformActivity(7),
  });

  const loading = statsLoading || secLoading || eventsLoading || bizLoading || platformLoading;

  // new_last_7_days from business metrics (sum last 7 entries)
  const weeklyNewUsers = statsData?.new_last_7_days ?? 0;
  const weeklyNewProjects =
    bizMetrics?.projects_by_day
      .slice(-7)
      .reduce((acc, d) => acc + d.count, 0) ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Overview</h1>
        <p className="text-sm text-muted-foreground">
          Resumen del sistema en tiempo real
        </p>
      </div>

      {/* User KPIs */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Usuarios
        </h2>
        {statsLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-24 rounded-lg border border-border bg-card animate-pulse"
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <StatCard
              label="Total usuarios"
              value={statsData?.total_users ?? 0}
              icon={<Users size={16} />}
            />
            <StatCard
              label="Verificados"
              value={statsData?.verified_users ?? 0}
              icon={<UserCheck size={16} />}
            />
            <StatCard
              label="Nuevos (7d)"
              value={statsData?.new_last_7_days ?? 0}
              icon={<Users size={16} />}
              description="últimos 7 días"
            />
            <StatCard
              label="Bloqueados"
              value={statsData?.currently_locked ?? 0}
              icon={<Lock size={16} />}
            />
            <StatCard
              label="Activos (30d)"
              value={statsData?.active_last_30_days ?? 0}
              icon={<Activity size={16} />}
              description="últimos 30 días"
            />
          </div>
        )}
      </section>

      {/* Business KPIs */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Negocio
        </h2>
        {bizLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-24 rounded-lg border border-border bg-card animate-pulse"
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label="Total proyectos"
              value={bizMetrics?.total_projects ?? 0}
              icon={<FolderOpen size={16} />}
            />
            <StatCard
              label="Suscripciones activas"
              value={bizMetrics?.total_active_subscriptions ?? 0}
              icon={<TrendingUp size={16} />}
              description="beta — sin suscripciones aún"
            />
            <StatCard
              label="Nuevos usuarios (7d)"
              value={weeklyNewUsers}
              icon={<Users size={16} />}
              description="últimos 7 días"
            />
            <StatCard
              label="Nuevos proyectos (7d)"
              value={weeklyNewProjects}
              icon={<FolderOpen size={16} />}
              description="últimos 7 días"
            />
          </div>
        )}
      </section>

      {/* Charts */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* New users chart */}
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="text-sm font-medium text-foreground mb-3">
            Nuevos usuarios — últimos 30 días
          </h3>
          {bizLoading ? (
            <div className="h-24 animate-pulse bg-muted rounded" />
          ) : (
            <BarChart
              data={bizMetrics?.new_users_by_day ?? []}
              label="Registros por día"
            />
          )}
        </div>

        {/* Activity type breakdown */}
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="text-sm font-medium text-foreground mb-3">
            Actividad por tipo — últimos 7 días
          </h3>
          {platformLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-4 animate-pulse bg-muted rounded" />
              ))}
            </div>
          ) : (
            <HorizontalBarChart data={platformActivity?.activity_by_type ?? []} />
          )}
        </div>
      </section>

      {/* Most active users */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Usuarios más activos — últimos 7 días
        </h2>
        {platformLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-8 animate-pulse bg-muted rounded" />
            ))}
          </div>
        ) : !platformActivity?.most_active_users?.length ? (
          <p className="text-sm text-muted-foreground">Sin actividad en este período.</p>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">#</th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">Usuario</th>
                  <th className="text-right px-4 py-2 font-medium text-muted-foreground">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(platformActivity.most_active_users as ActiveUser[]).map((u, idx) => (
                  <tr key={u.user_id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-2 text-muted-foreground">{idx + 1}</td>
                    <td className="px-4 py-2 font-medium">{u.username}</td>
                    <td className="px-4 py-2 text-right text-muted-foreground">{u.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Security KPIs */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Seguridad — últimos 7 días
        </h2>
        {secLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-24 rounded-lg border border-border bg-card animate-pulse"
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label="Total eventos"
              value={secStats?.total_events ?? 0}
              icon={<ShieldAlert size={16} />}
            />
            <StatCard
              label="Warnings"
              value={secStats?.by_severity?.warning ?? 0}
              icon={<ShieldAlert size={16} />}
            />
            <StatCard
              label="Errors"
              value={secStats?.by_severity?.error ?? 0}
              icon={<ShieldAlert size={16} />}
            />
            <StatCard
              label="Critical"
              value={secStats?.by_severity?.critical ?? 0}
              icon={<ShieldAlert size={16} />}
            />
          </div>
        )}
      </section>

      {/* Recent security events */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Eventos recientes
        </h2>
        {eventsLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-10 rounded border border-border bg-card animate-pulse"
              />
            ))}
          </div>
        ) : !recentEvents?.length ? (
          <p className="text-sm text-muted-foreground">
            No hay eventos recientes.
          </p>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    Tipo
                  </th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    Severidad
                  </th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    Usuario
                  </th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    Fecha
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {recentEvents.map((ev) => (
                  <tr key={ev.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-2 font-mono text-xs">
                      {ev.event_type}
                    </td>
                    <td className="px-4 py-2">
                      <SeverityBadge severity={ev.severity} />
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {ev.username ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground text-xs">
                      {new Date(ev.created_at).toLocaleString("es-ES")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {loading && (
        <p className="text-xs text-muted-foreground text-center">
          Cargando datos...
        </p>
      )}
    </div>
  );
};
