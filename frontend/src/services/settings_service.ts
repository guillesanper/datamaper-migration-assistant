// src/services/settings_service.ts
import { apiService } from "./api.service";
import type {
  UserProfile,
  NotificationPrefs,
  UserPreferences,
  ActiveSession,
  AccessHistoryEntry,
  TwoFASetup,
  ApiKey,
  NewApiKey,
} from "../types/settings_types";

class SettingsService {
  private readonly BASE_PATH = "/api/settings";
  private readonly BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

  // --- Profile ---

  async getProfile(): Promise<UserProfile> {
    return apiService.get<UserProfile>(`${this.BASE_PATH}/profile`);
  }

  async updateProfile(data: Partial<{ username: string }>): Promise<UserProfile> {
    const response = await apiService.put<{ success: boolean; user: UserProfile }>(
      `${this.BASE_PATH}/profile`,
      data
    );
    if (!response.success || !response.user) {
      throw new Error("Error al actualizar el perfil");
    }
    return response.user;
  }

  async changePassword(data: {
    current_password: string;
    new_password: string;
    confirm_password: string;
  }): Promise<void> {
    const response = await apiService.put<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/password`,
      data
    );
    if (!response.success) {
      throw new Error(response.message || "Error al cambiar la contraseña");
    }
  }

  async uploadAvatar(file: File): Promise<{ avatar_url: string }> {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${this.BASE_URL}${this.BASE_PATH}/avatar`, {
      method: "POST",
      body: formData,
      credentials: "include",
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.detail || data.message || "Error al subir el avatar");
    }
    return { avatar_url: data.avatar_url };
  }

  async deleteAvatar(): Promise<void> {
    const response = await apiService.delete<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/avatar`
    );
    if (!response.success) {
      throw new Error(response.message || "Error al eliminar el avatar");
    }
  }

  // --- Notifications ---

  async getNotificationPrefs(): Promise<NotificationPrefs> {
    return apiService.get<NotificationPrefs>(`${this.BASE_PATH}/notifications`);
  }

  async updateNotificationPrefs(data: Partial<NotificationPrefs>): Promise<NotificationPrefs> {
    const response = await apiService.put<{ success: boolean; preferences: NotificationPrefs }>(
      `${this.BASE_PATH}/notifications`,
      data
    );
    if (!response.success || !response.preferences) {
      throw new Error("Error al actualizar preferencias de notificaciones");
    }
    return response.preferences;
  }

  // --- Preferences ---

  async getPreferences(): Promise<UserPreferences> {
    return apiService.get<UserPreferences>(`${this.BASE_PATH}/preferences`);
  }

  async updatePreferences(data: Partial<UserPreferences>): Promise<UserPreferences> {
    const response = await apiService.put<{ success: boolean; preferences: UserPreferences }>(
      `${this.BASE_PATH}/preferences`,
      data
    );
    if (!response.success || !response.preferences) {
      throw new Error("Error al actualizar preferencias");
    }
    return response.preferences;
  }

  // --- Security ---

  async getSessions(): Promise<ActiveSession[]> {
    return apiService.get<ActiveSession[]>(`${this.BASE_PATH}/sessions`);
  }

  async revokeSession(sessionId: string): Promise<void> {
    const response = await apiService.delete<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/sessions/${sessionId}`
    );
    if (!response.success) {
      throw new Error(response.message || "Error al revocar la sesión");
    }
  }

  async getAccessHistory(limit = 20, offset = 0): Promise<AccessHistoryEntry[]> {
    return apiService.get<AccessHistoryEntry[]>(
      `${this.BASE_PATH}/access-history?limit=${limit}&offset=${offset}`
    );
  }

  // --- 2FA ---

  async setup2FA(): Promise<TwoFASetup> {
    return apiService.post<TwoFASetup>(`${this.BASE_PATH}/2fa/setup`);
  }

  async verify2FA(code: string): Promise<void> {
    const response = await apiService.post<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/2fa/verify`,
      { code }
    );
    if (!response.success) {
      throw new Error(response.message || "Error al verificar el código 2FA");
    }
  }

  async disable2FA(code: string, password: string): Promise<void> {
    const response = await apiService.delete<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/2fa`,
      {
        body: JSON.stringify({ code, password }),
        headers: { "Content-Type": "application/json" },
      }
    );
    if (!response.success) {
      throw new Error(response.message || "Error al desactivar 2FA");
    }
  }

  // --- API Keys ---

  async getApiKeys(): Promise<ApiKey[]> {
    return apiService.get<ApiKey[]>(`${this.BASE_PATH}/api-keys`);
  }

  async createApiKey(name: string, expiresInDays?: number): Promise<NewApiKey> {
    const response = await apiService.post<{
      key_id: string;
      name: string;
      raw_key: string;
      key_prefix: string;
      created_at: string;
      last_used_at: string | null;
      expires_at: string | null;
      is_active: boolean;
    }>(`${this.BASE_PATH}/api-keys`, { name, expires_in_days: expiresInDays });
    return {
      id: response.key_id,
      name: response.name,
      key_prefix: response.key_prefix,
      created_at: response.created_at,
      last_used_at: response.last_used_at ?? null,
      expires_at: response.expires_at ?? null,
      is_active: response.is_active ?? true,
      raw_key: response.raw_key,
    };
  }

  async revokeApiKey(keyId: string): Promise<void> {
    const response = await apiService.delete<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/api-keys/${keyId}`
    );
    if (!response.success) {
      throw new Error(response.message || "Error al revocar la API key");
    }
  }
}

export const settingsService = new SettingsService();
export default SettingsService;
