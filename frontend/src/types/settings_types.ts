// src/types/settings_types.ts

export interface UserProfile {
  username: string;
  email: string;
  avatar_url: string | null;
  created_at: string;
  is_verified: boolean;
  totp_enabled: boolean;
}

export interface NotificationPrefs {
  email_notifications: {
    invitations: boolean;
    comments: boolean;
    version_updates: boolean;
    security_alerts: boolean;
  };
  in_app_notifications: {
    invitations: boolean;
    comments: boolean;
    version_updates: boolean;
    security_alerts: boolean;
  };
}

export interface UserPreferences {
  language: string;
  timezone: string;
  default_db_type: string | null;
  default_export_format: string;
}

export interface ActiveSession {
  id: string;
  ip_address: string;
  user_agent: string;
  created_at: string;
  last_activity: string;
  expires_at: string;
  is_current: boolean;
}

export interface AccessHistoryEntry {
  event_type: string;
  ip_address: string;
  endpoint: string;
  severity: 'info' | 'warning' | 'error' | 'critical';
  created_at: string;
  details: Record<string, unknown>;
}

export interface TwoFASetup {
  secret: string;
  otpauth_url: string;
  qr_code_base64: string;
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  is_active: boolean;
}

export interface NewApiKey extends ApiKey {
  raw_key: string; // Solo devuelto en la creación
}
