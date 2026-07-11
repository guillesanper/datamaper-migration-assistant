// src/providers/AuthProvider.tsx
import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { type User, type AuthContextType } from "../types/auth_types";
import { authService } from "../services/auth_service";

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function extractErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "object" && err !== null && "message" in err)
    return String((err as { message: unknown }).message);
  return fallback;
}

const AUTH_CHANNEL = "auth_channel";
const AUTH_STORAGE_KEY = "auth_sync_event";

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initialCheckDone, setInitialCheckDone] = useState(false);
  
  const channelRef = useRef<BroadcastChannel | null>(null);
  const isInitializedRef = useRef(false);
  const expiryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // BroadcastChannel + localStorage como fallback
  useEffect(() => {
    // Inicializar BroadcastChannel si está disponible
    if (typeof BroadcastChannel !== "undefined") {
      try {
        channelRef.current = new BroadcastChannel(AUTH_CHANNEL);
        
        channelRef.current.onmessage = (event) => {
          console.log("[AuthProvider] Mensaje recibido:", event.data);
          const { type, user: newUser } = event.data;
          
          switch (type) {
            case "LOGIN":
              setUser(newUser);
              console.log("[AuthProvider] Usuario actualizado por broadcast (LOGIN):", newUser);
              break;
            case "LOGOUT":
              setUser(null);
              console.log("[AuthProvider] Usuario eliminado por broadcast (LOGOUT)");
              break;
            case "UPDATE_USER":
              setUser(newUser);
              console.log("[AuthProvider] Usuario actualizado por broadcast (UPDATE):", newUser);
              break;
          }
        };

        console.log("[AuthProvider] BroadcastChannel inicializado");
      } catch (error) {
        console.error("[AuthProvider] Error al crear BroadcastChannel:", error);
      }
    } else {
      console.warn("[AuthProvider] BroadcastChannel no disponible, usando solo localStorage");
    }

    // Listener de localStorage como fallback
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === AUTH_STORAGE_KEY && e.newValue) {
        try {
          const { type, user: newUser } = JSON.parse(e.newValue);
          console.log("[AuthProvider] Evento de storage recibido:", { type, newUser });
          
          switch (type) {
            case "LOGIN":
              setUser(newUser);
              break;
            case "LOGOUT":
              setUser(null);
              break;
            case "UPDATE_USER":
              setUser(newUser);
              break;
          }
        } catch (error) {
          console.error("[AuthProvider] Error al parsear storage event:", error);
        }
      }
    };

    window.addEventListener("storage", handleStorageChange);

    return () => {
      if (channelRef.current) {
        channelRef.current.close();
        console.log("[AuthProvider] BroadcastChannel cerrado");
      }
      window.removeEventListener("storage", handleStorageChange);
    };
  }, []);

  const broadcastAuthChange = useCallback((type: "LOGIN" | "LOGOUT" | "UPDATE_USER", user?: User | null) => {
    const message = { type, user };
    console.log("[AuthProvider] Broadcasting:", message);

    // BroadcastChannel (para tabs en el mismo contexto de navegación)
    if (channelRef.current) {
      try {
        channelRef.current.postMessage(message);
        console.log("[AuthProvider] Mensaje enviado por BroadcastChannel");
      } catch (error) {
        console.error("[AuthProvider] Error al enviar por BroadcastChannel:", error);
      }
    }

    // localStorage (para compatibilidad y como fallback)
    try {
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(message));
      // Limpiar inmediatamente para que el evento se dispare en cada cambio
      setTimeout(() => {
        localStorage.removeItem(AUTH_STORAGE_KEY);
      }, 100);
      console.log("[AuthProvider] Mensaje enviado por localStorage");
    } catch (error) {
      console.error("[AuthProvider] Error al enviar por localStorage:", error);
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const scheduleExpiryCheck = useCallback((expiresAt: string | undefined) => {
    if (expiryTimerRef.current) clearTimeout(expiryTimerRef.current);
    if (!expiresAt) return;

    const msUntilExpiry = new Date(expiresAt).getTime() - Date.now();
    if (msUntilExpiry <= 0) {
      setUser(null);
      return;
    }

    expiryTimerRef.current = setTimeout(() => {
      setUser(null);
      broadcastAuthChange("LOGOUT");
    }, msUntilExpiry);
  }, [broadcastAuthChange]);

  useEffect(() => {
    const handleSessionExpired = () => {
      if (expiryTimerRef.current) clearTimeout(expiryTimerRef.current);
      setUser(null);
      broadcastAuthChange("LOGOUT");
    };

    window.addEventListener('auth-session-expired', handleSessionExpired);
    return () => {
      window.removeEventListener('auth-session-expired', handleSessionExpired);
      if (expiryTimerRef.current) clearTimeout(expiryTimerRef.current);
    };
  }, [broadcastAuthChange]);

  // Verificar sesión al cargar
  const checkSession = useCallback(async () => {
    if (isInitializedRef.current) return;
    
    try {
      setLoading(true);
      console.log("[AuthProvider] Verificando sesión...");
      const currentUser = await authService.getCurrentUser();
      
      if (currentUser) {
        setUser(currentUser);
        scheduleExpiryCheck(currentUser.expires_at);
        console.log("[AuthProvider] Sesión verificada:", currentUser.email);
      } else {
        setUser(null);
        console.log("[AuthProvider] No hay sesión activa");
      }
    } catch (err) {
      setUser(null);
      console.error("[AuthProvider] Error al verificar sesión:", err);
    } finally {
      setLoading(false);
      setInitialCheckDone(true);
      isInitializedRef.current = true;
    }
  }, [scheduleExpiryCheck]);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  const login = useCallback(
    async (identifier: string, password: string): Promise<void> => {
      try {
        setLoading(true);
        clearError();
        
        console.log("[AuthProvider] Iniciando login...");
        const userData = await authService.login({ identifier, password });
        
        setUser(userData);
        scheduleExpiryCheck(userData.expires_at);
        // Pequeño delay para asegurar que el estado se actualiza antes de broadcast
        setTimeout(() => {
          broadcastAuthChange("LOGIN", userData);
        }, 50);
        console.log("[AuthProvider] Login exitoso:", userData.email);
      } catch (err: unknown) {
        const errorMessage = extractErrorMessage(err, "Error al iniciar sesión");
        setError(errorMessage);
        console.error("[AuthProvider] Error en login:", errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [broadcastAuthChange, clearError, scheduleExpiryCheck]
  );

  const register = useCallback(
    async (username: string, email: string, password: string, confirmPassword: string) => {
      try {
        setLoading(true);
        clearError();
        
        console.log("[AuthProvider] Iniciando registro...");
        await authService.register({
          username,
          email,
          password,
          confirm_password: confirmPassword,
        });
        console.log("[AuthProvider] Registro exitoso");
      } catch (err: unknown) {
        const errorMessage = extractErrorMessage(err, "Error al registrar");
        setError(errorMessage);
        console.error("[AuthProvider] Error en registro:", errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [clearError]
  );

  const logout = useCallback(async () => {
    try {
      setLoading(true);
      console.log("[AuthProvider] Cerrando sesión...");
      await authService.logout();
      if (expiryTimerRef.current) clearTimeout(expiryTimerRef.current);
      setUser(null);
      setTimeout(() => {
        broadcastAuthChange("LOGOUT");
      }, 50);
      console.log("[AuthProvider] Logout exitoso");
    } catch (err: unknown) {
      console.error("[AuthProvider] Error en logout:", err);
      // Hacer logout local aunque falle el servidor
      setUser(null);
      setTimeout(() => {
        broadcastAuthChange("LOGOUT");
      }, 50);
    } finally {
      setLoading(false);
    }
  }, [broadcastAuthChange]);

  const verifyCode = useCallback(
    async (email: string, code: string) => {
      try {
        setLoading(true);
        clearError();
        
        console.log("[AuthProvider] Verificando código...");
        await authService.verifyCode({ email, code });
        
        // Después de verificar, obtener el usuario actual
        const currentUser = await authService.getCurrentUser();
        if (currentUser) {
          setUser(currentUser);
          scheduleExpiryCheck(currentUser.expires_at);
          setTimeout(() => {
            broadcastAuthChange("LOGIN", currentUser);
          }, 50);
          console.log("[AuthProvider] Código verificado:", currentUser.email);
        }
      } catch (err: unknown) {
        const errorMessage = extractErrorMessage(err, "Error al verificar código");
        setError(errorMessage);
        console.error("[AuthProvider] Error al verificar código:", errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [broadcastAuthChange, clearError, scheduleExpiryCheck]
  );

  const resendCode = useCallback(
    async (email: string) => {
      try {
        setLoading(true);
        clearError();
        console.log("[AuthProvider] Reenviando código...");
        await authService.resendCode({ email });
        console.log("[AuthProvider] Código reenviado");
      } catch (err: unknown) {
        const errorMessage = extractErrorMessage(err, "Error al reenviar código");
        setError(errorMessage);
        console.error("[AuthProvider] Error al reenviar código:", errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [clearError]
  );

  const forgotPassword = useCallback(
    async (email: string) => {
      try {
        setLoading(true);
        clearError();
        console.log("[AuthProvider] Solicitando recuperación...");
        await authService.forgotPassword({ email });
        console.log("[AuthProvider] Recuperación solicitada");
      } catch (err: unknown) {
        const errorMessage = extractErrorMessage(err, "Error al solicitar recuperación");
        setError(errorMessage);
        console.error("[AuthProvider] Error en forgot password:", errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [clearError]
  );

  const resetPassword = useCallback(
    async (email: string, code: string, newPassword: string) => {
      try {
        setLoading(true);
        clearError();
        console.log("[AuthProvider] Reseteando contraseña...");
        await authService.resetPassword({ email, code, new_password: newPassword });
        console.log("[AuthProvider] Contraseña reseteada");
      } catch (err: unknown) {
        const errorMessage = extractErrorMessage(err, "Error al resetear contraseña");
        setError(errorMessage);
        console.error("[AuthProvider] Error al resetear contraseña:", errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [clearError]
  );

  const value: AuthContextType = {
    user,
    loading: loading || !initialCheckDone,
    error,
    login,
    register,
    logout,
    verifyCode,
    resendCode,
    forgotPassword,
    resetPassword,
    clearError,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth debe usarse dentro de AuthProvider");
  }
  return context;
};
