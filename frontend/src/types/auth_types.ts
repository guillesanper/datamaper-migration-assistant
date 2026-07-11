// src/types/auth.ts
export type Role = 'admin' | 'editor' | 'viewer';

export interface User {
  id: string;
  username: string;
  email: string;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string;
  last_login_ip?: string;
  failed_login_attempts?: number;
  locked_until?: string;
  is_deleted: boolean;
  expires_at?: string;
  role?: Role; // Role for permission system
  is_admin?: boolean; // Computed from ADMIN_USER_IDS env var
}

export interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (identifier: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string, confirmPassword: string) => Promise<void>;
  logout: () => Promise<void>;
  verifyCode: (email: string, code: string) => Promise<void>;
  resendCode: (email: string) => Promise<void>;
  forgotPassword: (email: string) => Promise<void>;
  resetPassword: (email: string, code: string, newPassword: string) => Promise<void>;
  clearError: () => void;
}

export interface LoginFormData {
  identifier: string;
  password: string;
}

export interface RegisterFormData {
  username: string;
  email: string;
  password: string;
  confirmPassword: string;
}

export interface VerifyCodeFormData {
  email: string;
  code: string;
}

export interface ResetPasswordFormData {
  email: string;
  code: string;
  newPassword: string;
  confirmPassword: string;
}

// Estructura real del backend
export interface AuthResponse {
  success: boolean;
  message?: string;
  error?: string;
  data?: {
    user?: User;
    email?: string;
    user_id?: string;
    username?: string;
  };
}

// Para endpoint /me
export interface MeResponse {
  success: boolean;
  message?: string;
  data?: {
    user: User;
  };
}

// Para endpoint /check
export interface CheckAuthResponse {
  authenticated: boolean;
}