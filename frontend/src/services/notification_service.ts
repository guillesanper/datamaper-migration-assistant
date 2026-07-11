import { apiService } from "./api.service";

export interface Notification {
  id: string;
  recipient_id: string;
  notification_kind: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
  metadata?: Record<string, unknown>;
}

class NotificationService {
  private readonly BASE_PATH = "/notifications";

  async getNotifications(params?: { limit?: number }): Promise<Notification[]> {
    const query = new URLSearchParams();
    if (params?.limit) query.append("limit", params.limit.toString());
    const qs = query.toString();
    return apiService.get<Notification[]>(`${this.BASE_PATH}${qs ? "?" + qs : ""}`);
  }

  async getUnreadCount(): Promise<number> {
    const data = await apiService.get<{ unread: number }>(`${this.BASE_PATH}/unread_count`);
    return data.unread;
  }

  async markAsRead(id: string): Promise<void> {
    await apiService.patch(`${this.BASE_PATH}/${id}/read`);
  }

  async markAllAsRead(): Promise<void> {
    await apiService.post(`${this.BASE_PATH}/mark_all_read`);
  }
}

export const notificationService = new NotificationService();
