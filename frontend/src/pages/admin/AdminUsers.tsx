// src/pages/admin/AdminUsers.tsx
import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminService } from "../../services/admin_service";
import type { AdminUser } from "../../types/admin_types";
import { Search, Unlock } from "lucide-react";

const PAGE_SIZE = 20;

export const AdminUsers: React.FC = () => {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [verified, setVerified] = useState<boolean | undefined>(undefined);
  const [locked, setLocked] = useState<boolean | undefined>(undefined);
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["admin", "users", { search, verified, locked, page }],
    queryFn: () =>
      adminService.getUsers({ search: search || undefined, verified, locked, page, page_size: PAGE_SIZE }),
  });

  const unlockMutation = useMutation({
    mutationFn: (userId: string) => adminService.unlockUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "user-stats"] });
    },
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  const handleSearch = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setPage(1);
  };

  const isLocked = (user: AdminUser): boolean => {
    if (!user.locked_until) return false;
    return new Date(user.locked_until) > new Date();
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Usuarios</h1>
        <p className="text-sm text-muted-foreground">
          {data ? `${data.total} usuarios en total` : "Cargando..."}
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <input
              type="text"
              placeholder="Buscar usuario o email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-3 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <button
            type="submit"
            className="px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
          >
            Buscar
          </button>
        </form>

        <select
          value={verified === undefined ? "" : String(verified)}
          onChange={(e) => {
            setVerified(e.target.value === "" ? undefined : e.target.value === "true");
            setPage(1);
          }}
          className="px-2 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none"
        >
          <option value="">Todos</option>
          <option value="true">Verificados</option>
          <option value="false">Sin verificar</option>
        </select>

        <select
          value={locked === undefined ? "" : String(locked)}
          onChange={(e) => {
            setLocked(e.target.value === "" ? undefined : e.target.value === "true");
            setPage(1);
          }}
          className="px-2 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none"
        >
          <option value="">Bloqueados: todos</option>
          <option value="true">Solo bloqueados</option>
          <option value="false">No bloqueados</option>
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-10 rounded border border-border bg-card animate-pulse" />
          ))}
        </div>
      ) : !data?.users.length ? (
        <p className="text-sm text-muted-foreground py-8 text-center">
          No se encontraron usuarios con los filtros aplicados.
        </p>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Usuario</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Email</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Estado</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Registro</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Último login</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.users.map((user) => {
                const locked = isLocked(user);
                return (
                  <tr key={user.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-2 font-medium">{user.username}</td>
                    <td className="px-4 py-2 text-muted-foreground">{user.email}</td>
                    <td className="px-4 py-2">
                      <div className="flex flex-wrap gap-1">
                        {user.is_verified ? (
                          <span className="inline-block px-2 py-0.5 rounded text-xs bg-green-100 text-green-800">
                            verificado
                          </span>
                        ) : (
                          <span className="inline-block px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-600">
                            sin verificar
                          </span>
                        )}
                        {locked && (
                          <span className="inline-block px-2 py-0.5 rounded text-xs bg-red-100 text-red-800">
                            bloqueado
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-muted-foreground text-xs">
                      {user.created_at
                        ? new Date(user.created_at).toLocaleDateString("es-ES")
                        : "—"}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground text-xs">
                      {user.last_login_at
                        ? new Date(user.last_login_at).toLocaleString("es-ES")
                        : "Nunca"}
                    </td>
                    <td className="px-4 py-2">
                      {locked && (
                        <button
                          onClick={() => unlockMutation.mutate(user.id)}
                          disabled={unlockMutation.isPending}
                          className="flex items-center gap-1 px-2 py-1 text-xs border border-border rounded hover:bg-accent transition-colors disabled:opacity-50"
                          title="Desbloquear usuario"
                        >
                          <Unlock size={12} />
                          Desbloquear
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 border border-border rounded hover:bg-accent transition-colors disabled:opacity-40"
          >
            Anterior
          </button>
          <span className="text-muted-foreground">
            Página {page} de {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1 border border-border rounded hover:bg-accent transition-colors disabled:opacity-40"
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
};
