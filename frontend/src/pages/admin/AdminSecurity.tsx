// src/pages/admin/AdminSecurity.tsx
import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminService } from "../../services/admin_service";

const SEVERITY_OPTIONS = ["", "info", "warning", "error", "critical"];

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

export const AdminSecurity: React.FC = () => {
  const [days, setDays] = useState(7);
  const [eventType, setEventType] = useState("");
  const [severity, setSeverity] = useState("");

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["admin", "security-stats", days],
    queryFn: () => adminService.getSecurityStats(days),
  });

  const { data: events, isLoading: eventsLoading } = useQuery({
    queryKey: ["admin", "security-events", { eventType, severity }],
    queryFn: () =>
      adminService.getSecurityEvents({
        event_type: eventType || undefined,
        severity: severity || undefined,
        limit: 50,
      }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Seguridad</h1>
        <p className="text-sm text-muted-foreground">
          Eventos de seguridad y estadísticas
        </p>
      </div>

      {/* Stats section */}
      <section>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
            Resumen
          </h2>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="px-2 py-1 text-xs border border-border rounded bg-background"
          >
            {[1, 7, 14, 30].map((d) => (
              <option key={d} value={d}>
                {d} {d === 1 ? "día" : "días"}
              </option>
            ))}
          </select>
        </div>

        {statsLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-20 rounded border border-border bg-card animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="rounded-lg border border-border bg-card p-4">
              <p className="text-xs text-muted-foreground">Total eventos</p>
              <p className="text-2xl font-bold">{stats?.total_events ?? 0}</p>
            </div>
            {(["info", "warning", "error", "critical"] as const).map((sev) => (
              <div key={sev} className="rounded-lg border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground capitalize">{sev}</p>
                <p className="text-2xl font-bold">{stats?.by_severity?.[sev] ?? 0}</p>
              </div>
            ))}
          </div>
        )}

        {/* By type */}
        {stats && Object.keys(stats.by_type).length > 0 && (
          <div className="mt-4 rounded-lg border border-border bg-card p-4">
            <p className="text-xs font-medium text-muted-foreground uppercase mb-3">
              Por tipo de evento
            </p>
            <div className="space-y-2">
              {Object.entries(stats.by_type)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 10)
                .map(([type, count]) => {
                  const max = Math.max(...Object.values(stats.by_type));
                  const pct = max > 0 ? (count / max) * 100 : 0;
                  return (
                    <div key={type} className="flex items-center gap-3">
                      <span className="text-xs font-mono w-48 truncate text-muted-foreground">
                        {type}
                      </span>
                      <div className="flex-1 bg-muted rounded-full h-1.5">
                        <div
                          className="bg-primary h-1.5 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground w-8 text-right">
                        {count}
                      </span>
                    </div>
                  );
                })}
            </div>
          </div>
        )}
      </section>

      {/* Events table */}
      <section>
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
            Eventos
          </h2>
          <input
            type="text"
            placeholder="Tipo de evento..."
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            className="px-2 py-1 text-xs border border-border rounded bg-background focus:outline-none"
          />
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="px-2 py-1 text-xs border border-border rounded bg-background"
          >
            {SEVERITY_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s || "Todas severidades"}
              </option>
            ))}
          </select>
        </div>

        {eventsLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-10 rounded border border-border bg-card animate-pulse" />
            ))}
          </div>
        ) : !events?.length ? (
          <p className="text-sm text-muted-foreground py-8 text-center">
            No hay eventos con los filtros aplicados.
          </p>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">Tipo</th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">Severidad</th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">Usuario</th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">IP</th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">Fecha</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {events.map((ev) => (
                  <tr key={ev.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-2 font-mono text-xs">{ev.event_type}</td>
                    <td className="px-4 py-2">
                      <SeverityBadge severity={ev.severity} />
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">{ev.username ?? "—"}</td>
                    <td className="px-4 py-2 text-muted-foreground text-xs font-mono">
                      {ev.ip_address ?? "—"}
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
    </div>
  );
};
