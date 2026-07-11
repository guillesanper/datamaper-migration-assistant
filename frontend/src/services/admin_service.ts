// src/services/admin_service.ts
import { apiService } from "./api.service";
import type {
  AdminUserStats,
  AdminUsersResponse,
  AdminUserFilters,
  SecurityStats,
  SecurityEvent,
  SecurityEventsFilters,
  BusinessMetrics,
  PlatformActivity,
  EndpointStat,
  ErrorStat,
  HealthStatus,
} from "../types/admin_types";

interface ApiDataResponse<T> {
  success: boolean;
  data: T;
}

export const adminService = {
  async getUserStats(): Promise<AdminUserStats> {
    const res = await apiService.get<ApiDataResponse<AdminUserStats>>(
      "/api/admin/users/stats"
    );
    return res.data;
  },

  async getUsers(filters: AdminUserFilters = {}): Promise<AdminUsersResponse> {
    const params = new URLSearchParams();
    if (filters.search) params.set("search", filters.search);
    if (filters.verified !== undefined)
      params.set("verified", String(filters.verified));
    if (filters.locked !== undefined)
      params.set("locked", String(filters.locked));
    if (filters.page) params.set("page", String(filters.page));
    if (filters.page_size) params.set("page_size", String(filters.page_size));

    const query = params.toString() ? `?${params.toString()}` : "";
    const res = await apiService.get<ApiDataResponse<AdminUsersResponse>>(
      `/api/admin/users${query}`
    );
    return res.data;
  },

  async unlockUser(userId: string): Promise<void> {
    await apiService.patch(`/api/admin/users/${userId}/unlock`);
  },

  async getSecurityStats(days = 7): Promise<SecurityStats> {
    const res = await apiService.get<ApiDataResponse<SecurityStats>>(
      `/api/admin/security/stats?days=${days}`
    );
    return res.data;
  },

  async getSecurityEvents(
    filters: SecurityEventsFilters = {}
  ): Promise<SecurityEvent[]> {
    const params = new URLSearchParams();
    if (filters.event_type) params.set("event_type", filters.event_type);
    if (filters.severity) params.set("severity", filters.severity);
    if (filters.limit !== undefined)
      params.set("limit", String(filters.limit));
    if (filters.offset !== undefined)
      params.set("offset", String(filters.offset));

    const query = params.toString() ? `?${params.toString()}` : "";
    const res = await apiService.get<ApiDataResponse<{ events: SecurityEvent[] }>>(
      `/api/admin/security/events${query}`
    );
    return res.data.events;
  },

  async getBusinessMetrics(days = 30): Promise<BusinessMetrics> {
    const res = await apiService.get<ApiDataResponse<BusinessMetrics>>(
      `/api/admin/metrics/business?days=${days}`
    );
    return res.data;
  },

  async getPlatformActivity(days = 7): Promise<PlatformActivity> {
    const res = await apiService.get<ApiDataResponse<PlatformActivity>>(
      `/api/admin/metrics/platform-activity?days=${days}`
    );
    return res.data;
  },

  async getApiPerformance(hours = 24): Promise<{ stats: EndpointStat[]; hours: number }> {
    const res = await apiService.get<ApiDataResponse<{ stats: EndpointStat[]; hours: number }>>(
      `/api/admin/metrics/api-performance?hours=${hours}`
    );
    return res.data;
  },

  async getApiErrors(hours = 24): Promise<{ errors: ErrorStat[]; hours: number }> {
    const res = await apiService.get<ApiDataResponse<{ errors: ErrorStat[]; hours: number }>>(
      `/api/admin/metrics/errors?hours=${hours}`
    );
    return res.data;
  },

  async getHealth(): Promise<HealthStatus> {
    return apiService.get<HealthStatus>("/api/admin/health/detailed");
  },
};
