// src/types/admin_types.ts

export interface AdminUserStats {
  total_users: number;
  verified_users: number;
  new_last_7_days: number;
  currently_locked: number;
  active_last_30_days: number;
}

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  is_verified: boolean;
  is_deleted: boolean;
  created_at: string | null;
  last_login_at: string | null;
  failed_login_attempts: number;
  locked_until: string | null;
}

export interface AdminUsersResponse {
  users: AdminUser[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminUserFilters {
  search?: string;
  verified?: boolean;
  locked?: boolean;
  page?: number;
  page_size?: number;
}

export interface SecurityStats {
  period_days: number;
  total_events: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  top_ips: Array<{ ip_address: string; count: number }>;
  by_day: Array<{ date: string; count: number }>;
}

export interface SecurityEvent {
  id: string;
  event_type: string;
  severity: string;
  ip_address: string | null;
  username: string | null;
  user_id: string | null;
  endpoint: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface SecurityEventsFilters {
  event_type?: string;
  severity?: string;
  limit?: number;
  offset?: number;
}

export interface DayCount {
  date: string;
  count: number;
}

export interface BusinessMetrics {
  total_projects: number;
  projects_by_status: Record<string, number>;
  total_users: number;
  new_users_by_day: DayCount[];
  projects_by_day: DayCount[];
  subscription_breakdown: Record<string, number>;
  total_active_subscriptions: number;
}

export interface ActivityTypeCount {
  type: string;
  count: number;
}

export interface ActiveUser {
  user_id: string;
  username: string;
  count: number;
}

export interface PlatformActivity {
  activity_by_day: DayCount[];
  activity_by_type: ActivityTypeCount[];
  most_active_users: ActiveUser[];
}

export interface EndpointStat {
  endpoint: string;
  method: string;
  count: number;
  avg_ms: number;
  p95_ms: number;
  error_count: number;
}

export interface ErrorStat {
  endpoint: string;
  method: string;
  status_code: number;
  count: number;
}

export interface HealthStatus {
  db_status: "healthy" | "error";
  redis_status: "healthy" | "error";
  memory_percent: number;
  cpu_percent: number;
  process_memory_mb: number;
  environment: string;
  timestamp: string;
}
