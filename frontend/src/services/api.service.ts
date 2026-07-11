// src/services/api_service.ts

interface ApiResponse<T = unknown> {
  success?: boolean;
  message?: string;
  error?: string;
  data?: T;
  [key: string]: unknown;
}

interface ApiErrorResponse {
  success: false;
  code: string;                         // "project.not_found" or legacy "request_failed"
  error: string;                        // kept for backward compatibility
  message: string;
  params?: Record<string, unknown>;     // i18next interpolation
  status?: number;
}

interface RequestConfig extends RequestInit {
  retries?: number;
  retryDelay?: number;
  timeout?: number;
  url?: string;
}

type RequestInterceptor = (config: RequestInit & { url?: string }) => RequestInit & { url?: string } | Promise<RequestInit & { url?: string }>;
type ResponseInterceptor = <T>(response: T) => T | Promise<T>;
type ErrorInterceptor = (error: ApiErrorResponse) => Promise<never>;

class ApiService {
  private baseURL: string;
  private defaultHeaders: HeadersInit;
  private requestInterceptors: RequestInterceptor[] = [];
  private responseInterceptors: ResponseInterceptor[] = [];
  private errorInterceptors: ErrorInterceptor[] = [];

  constructor() {
    this.baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";
    this.defaultHeaders = {
      "Content-Type": "application/json",
    };
  }

  /**
   * Agregar interceptor de request
   */
  addRequestInterceptor(interceptor: RequestInterceptor): void {
    this.requestInterceptors.push(interceptor);
  }

  /**
   * Agregar interceptor de response
   */
  addResponseInterceptor(interceptor: ResponseInterceptor): void {
    this.responseInterceptors.push(interceptor);
  }

  /**
   * Agregar interceptor de error
   */
  addErrorInterceptor(interceptor: ErrorInterceptor): void {
    this.errorInterceptors.push(interceptor);
  }

  /**
   * Aplicar todos los interceptores de request
   */
  private async applyRequestInterceptors(config: RequestInit & { url?: string }): Promise<RequestInit & { url?: string }> {
    let modifiedConfig = config;
    for (const interceptor of this.requestInterceptors) {
      modifiedConfig = await interceptor(modifiedConfig);
    }
    return modifiedConfig;
  }

  /**
   * Aplicar todos los interceptores de response
   */
  private async applyResponseInterceptors<T>(response: T): Promise<T> {
    let modifiedResponse = response;
    for (const interceptor of this.responseInterceptors) {
      modifiedResponse = await interceptor(modifiedResponse);
    }
    return modifiedResponse;
  }

  /**
   * Aplicar todos los interceptores de error
   */
  private async applyErrorInterceptors(error: ApiErrorResponse): Promise<never> {
    for (const interceptor of this.errorInterceptors) {
      await interceptor(error);
    }
    throw error;
  }

  /**
   * Sleep utility para retry logic
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Método genérico para hacer peticiones HTTP con retry logic
   */
  private async request<T = unknown>(
    endpoint: string,
    options: RequestConfig = {}
  ): Promise<T> {
    const {
      retries = 0,
      retryDelay = 1000,
      timeout = 30000,
      ...fetchOptions
    } = options;

    const url = `${this.baseURL}${endpoint}`;

    // Aplicar interceptores de request
    let config: RequestInit & { url?: string } = {
      ...fetchOptions,
      headers: {
        ...this.defaultHeaders,
        ...fetchOptions.headers,
      },
      credentials: "include",
      url: endpoint, // Include URL for interceptors
    };

    config = await this.applyRequestInterceptors(config);

    // Controller para timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    let lastError: ApiErrorResponse | null = null;

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const response = await fetch(url, {
          ...config,
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        const data = await response.json();

        if (!response.ok) {
          let errorCode: string;
          let errorParams: Record<string, unknown> | undefined;

          if (data.detail && typeof data.detail === 'object' && 'code' in (data.detail as object)) {
            errorCode = (data.detail as Record<string, unknown>).code as string;
            errorParams = (data.detail as Record<string, unknown>).params as Record<string, unknown> | undefined;
          } else {
            errorCode = (typeof data.detail === 'string' ? data.detail : null)
              ?? (data.error as string | undefined)
              ?? 'request_failed';
          }

          const error: ApiErrorResponse = {
            success: false,
            code: errorCode,
            error: errorCode,
            params: errorParams,
            message: typeof data.detail === 'string'
              ? data.detail
              : (data.message as string | undefined) || `Error ${response.status}: ${response.statusText}`,
            status: response.status,
          };

          // Si es error 5xx, reintentamos
          if (response.status >= 500 && attempt < retries) {
            lastError = error;
            await this.sleep(retryDelay * Math.pow(2, attempt)); // Exponential backoff
            continue;
          }

          await this.applyErrorInterceptors(error);
        }

        // Aplicar interceptores de response
        const processedData = await this.applyResponseInterceptors(data);

        return processedData as T;
      } catch (error: unknown) {
        clearTimeout(timeoutId);

        const err = error as { name?: string; success?: boolean; message?: string };

        // Si es un abort por timeout
        if (err.name === "AbortError") {
          const timeoutError: ApiErrorResponse = {
            success: false,
            error: "timeout",
            message: "La petición ha excedido el tiempo límite",
          };
          await this.applyErrorInterceptors(timeoutError);
        }

        // Si ya es un error formateado
        if (err.success === false) {
          throw error;
        }

        // Error de red - reintentamos
        if (attempt < retries) {
          lastError = {
            success: false,
            error: "network_error",
            message: err.message || "Error de conexión con el servidor",
          };
          await this.sleep(retryDelay * Math.pow(2, attempt));
          continue;
        }

        // Último intento fallido
        const networkError: ApiErrorResponse = {
          success: false,
          error: "network_error",
          message: err.message || "Error de conexión con el servidor",
        };
        await this.applyErrorInterceptors(networkError);
      }
    }

    // Si llegamos aquí, todos los reintentos fallaron
    if (lastError) {
      throw lastError;
    }

    throw {
      success: false,
      error: "unknown_error",
      message: "Error desconocido",
    };
  }

  /**
   * GET request
   */
  async get<T = unknown>(endpoint: string, options: RequestConfig = {}): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "GET",
    });
  }

  /**
   * POST request
   */
  async post<T = unknown>(
    endpoint: string,
    body?: unknown,
    options: RequestConfig = {}
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /**
   * PUT request
   */
  async put<T = unknown>(
    endpoint: string,
    body?: unknown,
    options: RequestConfig = {}
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /**
   * DELETE request
   */
  async delete<T = unknown>(endpoint: string, options: RequestConfig = {}): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "DELETE",
    });
  }

  /**
   * PATCH request
   */
  async patch<T = unknown>(
    endpoint: string,
    body?: unknown,
    options: RequestConfig = {}
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    });
  }
}

// Exportar instancia singleton
export const apiService = new ApiService();

// Configurar interceptores globales
apiService.addRequestInterceptor((config) => {
  // Ejemplo: Agregar timestamp a todas las peticiones
  console.log(`[API] ${config.method} request at ${new Date().toISOString()}`);
  return config;
});

apiService.addResponseInterceptor((response) => {
  // Ejemplo: Log de respuestas
  console.log(`[API] Response received at ${new Date().toISOString()}`);
  return response;
});

apiService.addErrorInterceptor(async (error) => {
  // Ejemplo: Log de errores
  console.error(`[API] Error: ${error.error} - ${error.message}`);
  throw error;
});

// ============================================================================
// ENCRYPTION SESSION HANDLING
// ============================================================================

/**
 * SEGURIDAD HARDENED: httpOnly Cookies
 *
 * VULNERABILIDAD CORREGIDA: CRÍTICA
 * - Antes: Session tokens en localStorage + header manual
 * - Ahora: Session tokens en httpOnly cookies (enviadas automáticamente)
 * - Referencia: Auditoría de Seguridad 2025-01-03, Fase 1.1
 *
 * VENTAJAS:
 * - httpOnly cookies son inmunes a XSS (JavaScript no puede accederlas)
 * - Se envían automáticamente con credentials: "include"
 * - No requieren interceptors manuales
 * - Manejo de expiración automático por el navegador
 * - SameSite=Strict previene CSRF
 *
 * Las cookies de sesión se establecen por el backend en:
 * - POST /api/projects/{id}/encryption/verify
 *
 * Las cookies se leen automáticamente en el middleware del backend:
 * - backend/app/middleware/encryption_session.py
 *
 * NOTA: Ya no necesitamos interceptors para inyectar headers.
 * Las cookies van automáticamente con cada request.
 */

/**
 * Error interceptor: Handle encryption session expiration
 * Dispatches custom event when encryption-related errors occur
 */
apiService.addErrorInterceptor(async (error) => {
  const isAuthSessionError = error.status === 401 &&
    (error.error === 'session_expired' || error.error === 'session_invalid' || error.error === 'session_revoked');

  if (isAuthSessionError) {
    window.dispatchEvent(new CustomEvent('auth-session-expired', {
      detail: { error, timestamp: Date.now() }
    }));
  }
  throw error;
});

apiService.addErrorInterceptor(async (error) => {
  if ((error.status === 401 || error.status === 403) &&
      (error.message?.toLowerCase().includes('encryption') ||
       error.message?.toLowerCase().includes('decrypt') ||
       error.error === 'encryption_session_expired')) {

    if (import.meta.env.DEV) {
      console.error('[API] Encryption session error:', error.message);
    }

    window.dispatchEvent(new CustomEvent('encryption-session-error', {
      detail: {
        error,
        timestamp: Date.now()
      }
    }));
  }

  throw error;
});

export default ApiService;
export type { ApiResponse, ApiErrorResponse, RequestConfig };
