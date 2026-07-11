// src/pages/admin/AdminHealth.tsx
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Database, Server, Cpu, MemoryStick, HardDrive } from "lucide-react";
import { adminService } from "../../services/admin_service";
import type { HealthStatus } from "../../types/admin_types";

type StatusLevel = "green" | "yellow" | "red";

function percentLevel(value: number): StatusLevel {
  if (value >= 90) return "red";
  if (value >= 70) return "yellow";
  return "green";
}

function serviceLevel(status: "healthy" | "error"): StatusLevel {
  return status === "healthy" ? "green" : "red";
}

const LEVEL_CLASSES: Record<StatusLevel, { card: string; dot: string; text: string }> = {
  green: {
    card: "border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950/30",
    dot: "bg-green-500",
    text: "text-green-700 dark:text-green-400",
  },
  yellow: {
    card: "border-yellow-200 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-950/30",
    dot: "bg-yellow-500",
    text: "text-yellow-700 dark:text-yellow-400",
  },
  red: {
    card: "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30",
    dot: "bg-red-500",
    text: "text-red-700 dark:text-red-400",
  },
};

interface StatusCardProps {
  label: string;
  value: string;
  description?: string;
  level: StatusLevel;
  icon: React.ReactNode;
}

const StatusCard: React.FC<StatusCardProps> = ({ label, value, description, level, icon }) => {
  const cls = LEVEL_CLASSES[level];
  return (
    <div className={`rounded-lg border p-4 flex flex-col gap-2 ${cls.card}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="text-muted-foreground">{icon}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${cls.dot}`} />
        <span className={`text-2xl font-bold ${cls.text}`}>{value}</span>
      </div>
      {description && (
        <span className="text-xs text-muted-foreground">{description}</span>
      )}
    </div>
  );
};

const SkeletonCard: React.FC = () => (
  <div className="rounded-lg border border-border bg-card p-4 flex flex-col gap-2 animate-pulse">
    <div className="h-4 bg-muted rounded w-1/2" />
    <div className="h-8 bg-muted rounded w-3/4" />
    <div className="h-3 bg-muted rounded w-1/3" />
  </div>
);

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString("es-ES", {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

export const AdminHealth: React.FC = () => {
  const { data, isLoading, dataUpdatedAt } = useQuery<HealthStatus>({
    queryKey: ["admin", "health"],
    queryFn: () => adminService.getHealth(),
    refetchInterval: 30000,
  });

  const lastChecked = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleString("es-ES", { timeStyle: "medium" })
    : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">System Health</h1>
          <p className="text-sm text-muted-foreground">
            Estado del sistema — actualización automática cada 30s
          </p>
        </div>
        {lastChecked && (
          <span className="text-xs text-muted-foreground">
            Última comprobación: {lastChecked}
          </span>
        )}
      </div>

      {/* Services */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Servicios
        </h2>
        {isLoading ? (
          <div className="grid grid-cols-2 gap-3">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <StatusCard
              label="Base de datos"
              value={data?.db_status === "healthy" ? "Healthy" : "Error"}
              level={serviceLevel(data?.db_status ?? "error")}
              icon={<Database size={16} />}
            />
            <StatusCard
              label="Redis"
              value={data?.redis_status === "healthy" ? "Healthy" : "Error"}
              level={serviceLevel(data?.redis_status ?? "error")}
              icon={<Server size={16} />}
            />
          </div>
        )}
      </section>

      {/* Resources */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Recursos del sistema
        </h2>
        {isLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            <StatusCard
              label="Memoria del sistema"
              value={`${data?.memory_percent?.toFixed(1) ?? "—"}%`}
              level={percentLevel(data?.memory_percent ?? 0)}
              icon={<MemoryStick size={16} />}
              description={
                data?.memory_percent !== undefined
                  ? data.memory_percent >= 90
                    ? "Crítico — por encima del 90%"
                    : data.memory_percent >= 70
                    ? "Advertencia — por encima del 70%"
                    : "Normal"
                  : undefined
              }
            />
            <StatusCard
              label="CPU"
              value={`${data?.cpu_percent?.toFixed(1) ?? "—"}%`}
              level={percentLevel(data?.cpu_percent ?? 0)}
              icon={<Cpu size={16} />}
              description={
                data?.cpu_percent !== undefined
                  ? data.cpu_percent >= 90
                    ? "Crítico — por encima del 90%"
                    : data.cpu_percent >= 70
                    ? "Advertencia — por encima del 70%"
                    : "Normal"
                  : undefined
              }
            />
            <StatusCard
              label="Memoria del proceso"
              value={`${data?.process_memory_mb?.toFixed(1) ?? "—"} MB`}
              level="green"
              icon={<HardDrive size={16} />}
              description="Uso RSS del proceso FastAPI"
            />
          </div>
        )}
      </section>

      {/* Meta */}
      {data && (
        <section className="rounded-lg border border-border bg-card p-4 text-sm space-y-1">
          <div className="flex gap-4 text-muted-foreground">
            <span>
              Entorno:{" "}
              <span className="font-medium text-foreground">{data.environment}</span>
            </span>
            <span>
              Timestamp servidor:{" "}
              <span className="font-medium text-foreground font-mono text-xs">
                {formatTimestamp(data.timestamp)}
              </span>
            </span>
          </div>
        </section>
      )}
    </div>
  );
};
