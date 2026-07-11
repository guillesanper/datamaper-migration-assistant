// src/services/auth_service.ts
import { apiService } from "./api.service";
import type { User, AuthResponse, CheckAuthResponse } from "../types/auth_types";

interface LoginCredentials {
  identifier: string;
  password: string;
}

interface RegisterData {
  username: string;
  email: string;
  password: string;
  confirm_password: string;
}

interface VerifyCodeData {
  email: string;
  code: string;
}

interface ResendCodeData {
  email: string;
}

interface ForgotPasswordData {
  email: string;
}

interface ResetPasswordData {
  email: string;
  code: string;
  new_password: string;
}

class AuthService {
  /**
   * Login de usuario
   */
  async login(credentials: LoginCredentials): Promise<User> {
    const response = await apiService.post<AuthResponse>("/api/auth/login", credentials);
    
    if (!response.success || !response.data?.user) {
      throw new Error(response.message || "Error al iniciar sesión");
    }
    
    return response.data.user;
  }

  /**
   * Registro de usuario
   */
  async register(data: RegisterData): Promise<{ email: string; user_id: string }> {
    const response = await apiService.post<AuthResponse>("/api/auth/register", data);
    
    if (!response.success || !response.data) {
      throw new Error(response.message || "Error al registrar usuario");
    }
    
    return {
      email: response.data.email!,
      user_id: response.data.user_id!
    };
  }

  /**
   * Verificar código OTP
   */
  async verifyCode(data: VerifyCodeData): Promise<void> {
    const response = await apiService.post<AuthResponse>("/api/auth/verify-code", data);
    
    if (!response.success) {
      throw new Error(response.message || "Error al verificar código");
    }
  }

  /**
   * Reenviar código de verificación
   */
  async resendCode(data: ResendCodeData): Promise<void> {
    const response = await apiService.post<AuthResponse>("/api/auth/resend-code", data);
    
    if (!response.success) {
      throw new Error(response.message || "Error al reenviar código");
    }
  }

  /**
   * Solicitar recuperación de contraseña
   */
  async forgotPassword(data: ForgotPasswordData): Promise<void> {
    const response = await apiService.post<AuthResponse>("/api/auth/forgot", data);
    
    if (!response.success) {
      throw new Error(response.message || "Error al solicitar recuperación");
    }
  }

  /**
   * Resetear contraseña
   */
  async resetPassword(data: ResetPasswordData): Promise<void> {
    const response = await apiService.post<AuthResponse>("/api/auth/reset", data);
    
    if (!response.success) {
      throw new Error(response.message || "Error al resetear contraseña");
    }
  }

  /**
   * Cerrar sesión
   */
  async logout(): Promise<void> {
    const response = await apiService.post<AuthResponse>("/api/auth/logout");
    
    if (!response.success) {
      throw new Error(response.message || "Error al cerrar sesión");
    }
  }

  /**
   * Obtener usuario actual
   */
  async getCurrentUser(): Promise<User | null> {
    try {
      const response = await apiService.get<AuthResponse>("/api/auth/me");
      
      if (!response.success || !response.data?.user) {
        return null;
      }
      
      return response.data.user;
    } catch (error: unknown) {
      // Si no está autenticado, retornamos null en lugar de lanzar error
      const e = error as { status?: number; error?: string };
      if (e.status === 401 || e.error === "unauthorized") {
        return null;
      }
      throw error;
    }
  }

  /**
   * Verificar si el usuario está autenticado
   */
  async checkAuth(): Promise<boolean> {
    try {
      const response = await apiService.get<CheckAuthResponse>("/api/auth/check");
      return response.authenticated || false;
    } catch {
      return false;
    }
  }
}

// Exportar instancia singleton
export const authService = new AuthService();

export default AuthService;
