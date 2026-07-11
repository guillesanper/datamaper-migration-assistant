// src/pages/admin/AdminMetrics.tsx
import React, { useState, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { adminService } from "../../services/admin_service";
import type { EndpointStat, ErrorStat } from "../../types/admin_types";

function useColumnResize(initialWidths: number[]) {
  const [widths, setWidths] = useState<number[]>(initialWidths);
  const resizingRef = useRef<{
    colIndex: number;
    startX: number;
    startWidth: number;
  } | null>(null);

  const onMouseDown = useCallback(
    (colIndex: number) => (e: React.MouseEvent) => {
      e.preventDefault();
      resizingRef.current = {
        colIndex,
        startX: e.clientX,
        startWidth: widths[colIndex],
      };

      const onMouseMove = (ev: MouseEvent) => {
        if (!resizingRef.current) return;
        const delta = ev.clientX - resizingRef.current.startX;
        const newWidth = Math.max(48, resizingRef.current.startWidth + delta);
        setWidths((prev) => {
          const next = [...prev];
          next[resizingRef.current!.colIndex] = newWidth;
          return next;
        });
      };

      const onMouseUp = () => {
        resizingRef.current = null;
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [widths]
  );

  return { widths, onMouseDown };
}

const HOUR_OPTIONS = [
  { label: "1h", value: 1 },
  { label: "6h", value: 6 },
  { label: "24h", value: 24 },
  { label: "7d", value: 168 },
];

const SkeletonRow: React.FC<{ cols: number }> = ({ cols }) => (
  <tr>
    {Array.from({ length: cols }).map((_, i) => (
      <td key={i} className="px-4 py-2">
        <div className="h-4 animate-pulse bg-muted rounded w-full" />
      </td>
    ))}
  </tr>
);

export const AdminMetrics: React.FC = () => {
  const [hours, setHours] = useState(24);

  const perfCols = useColumnResize([280, 80, 90, 80, 80, 80]);
  const errCols = useColumnResize([280, 80, 80, 80]);

  const {
    data: perfData,
    isLoading: perfLoading,
    refetch: refetchPerf,
    isFetching: perfFetching,
  } = useQuery({
    queryKey: ["admin", "api-performance", hours],
    queryFn: () => adminService.getApiPerformance(hours),
  });

  const {
    data: errData,
    isLoading: errLoading,
    refetch: refetchErr,
  } = useQuery({
    queryKey: ["admin", "api-errors", hours],
    queryFn: () => adminService.getApiErrors(hours),
  });

  const handleRefresh = () => {
    void refetchPerf();
    void refetchErr();
  };

  const stats: EndpointStat[] = perfData?.stats ?? [];
  const errors: ErrorStat[] = errData?.errors ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Performance</h1>
          <p className="text-sm text-muted-foreground">
            Métricas de rendimiento por endpoint
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Hours selector */}
          <div className="flex rounded-md border border-border overflow-hidden">
            {HOUR_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setHours(opt.value)}
                className={`px-3 py-1.5 text-sm transition-colors ${
                  hours === opt.value
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button
            onClick={handleRefresh}
            disabled={perfFetching}
            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-md border border-border text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={perfFetching ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Endpoint Performance Table */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Endpoint Performance
        </h2>
        <div className="rounded-lg border border-border overflow-x-auto">
          <table className="text-sm" style={{ tableLayout: "fixed", width: perfCols.widths.reduce((a, b) => a + b, 0) }}>
            <colgroup>
              {perfCols.widths.map((w, i) => (
                <col key={i} style={{ width: w }} />
              ))}
            </colgroup>
            <thead className="bg-muted/50">
              <tr>
                {(["Endpoint", "Método", "Requests", "Avg ms", "P95 ms", "Errores"] as const).map(
                  (label, i) => (
                    <th
                      key={label}
                      className={`px-4 py-2 font-medium text-muted-foreground select-none relative ${
                        i >= 2 ? "text-right" : "text-left"
                      }`}
                      style={{ width: perfCols.widths[i], overflow: "hidden" }}
                    >
                      {label}
                      <span
                        onMouseDown={perfCols.onMouseDown(i)}
                        className="absolute right-0 top-1/4 h-1/2 w-px bg-border cursor-col-resize hover:w-1 hover:bg-muted-foreground/50 transition-all"
                        style={{ touchAction: "none" }}
                      />
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {perfLoading ? (
                Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={6} />)
              ) : stats.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-8 text-center text-sm text-muted-foreground"
                  >
                    Sin datos para este período.
                  </td>
                </tr>
              ) : (
                stats.map((row) => (
                  <tr
                    key={`${row.method}-${row.endpoint}`}
                    className="hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-2 font-mono text-xs overflow-hidden text-ellipsis whitespace-nowrap" title={row.endpoint}>
                      {row.endpoint}
                    </td>
                    <td className="px-4 py-2 overflow-hidden">
                      <span className="inline-block px-1.5 py-0.5 rounded text-xs font-medium bg-muted text-muted-foreground">
                        {row.method}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{row.count}</td>
                    <td
                      className={`px-4 py-2 text-right tabular-nums ${
                        row.avg_ms >= 1000
                          ? "text-red-600"
                          : row.avg_ms >= 500
                          ? "text-yellow-600"
                          : ""
                      }`}
                    >
                      {row.avg_ms}
                    </td>
                    <td
                      className={`px-4 py-2 text-right tabular-nums ${
                        row.p95_ms >= 2000
                          ? "text-red-600"
                          : row.p95_ms >= 1000
                          ? "text-yellow-600"
                          : ""
                      }`}
                    >
                      {row.p95_ms}
                    </td>
                    <td
                      className={`px-4 py-2 text-right tabular-nums ${
                        row.error_count > 0 ? "text-red-600 font-medium" : "text-muted-foreground"
                      }`}
                    >
                      {row.error_count}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Top Errors Table */}
      <section>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Top Errors
        </h2>
        <div className="rounded-lg border border-border overflow-x-auto">
          <table className="text-sm" style={{ tableLayout: "fixed", width: errCols.widths.reduce((a, b) => a + b, 0) }}>
            <colgroup>
              {errCols.widths.map((w, i) => (
                <col key={i} style={{ width: w }} />
              ))}
            </colgroup>
            <thead className="bg-muted/50">
              <tr>
                {(["Endpoint", "Método", "Status", "Count"] as const).map((label, i) => (
                  <th
                    key={label}
                    className={`px-4 py-2 font-medium text-muted-foreground select-none relative ${
                      i >= 2 ? "text-right" : "text-left"
                    }`}
                    style={{ width: errCols.widths[i], overflow: "hidden" }}
                  >
                    {label}
                    <span
                      onMouseDown={errCols.onMouseDown(i)}
                      className="absolute right-0 top-1/4 h-1/2 w-px bg-border cursor-col-resize hover:w-1 hover:bg-muted-foreground/50 transition-all"
                      style={{ touchAction: "none" }}
                    />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {errLoading ? (
                Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={4} />)
              ) : errors.length === 0 ? (
                <tr>
                  <td
                    colSpan={4}
                    className="px-4 py-8 text-center text-sm text-muted-foreground"
                  >
                    Sin errores en este período.
                  </td>
                </tr>
              ) : (
                errors.map((row, idx) => (
                  <tr
                    key={idx}
                    className="hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-2 font-mono text-xs overflow-hidden text-ellipsis whitespace-nowrap" title={row.endpoint}>
                      {row.endpoint}
                    </td>
                    <td className="px-4 py-2 overflow-hidden">
                      <span className="inline-block px-1.5 py-0.5 rounded text-xs font-medium bg-muted text-muted-foreground">
                        {row.method}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span
                        className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
                          row.status_code >= 500
                            ? "bg-red-100 text-red-800"
                            : "bg-yellow-100 text-yellow-800"
                        }`}
                      >
                        {row.status_code}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums font-medium text-red-600">
                      {row.count}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
