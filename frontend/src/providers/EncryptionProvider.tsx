import React, { createContext, useContext, useState, useRef, useEffect, useCallback } from 'react';

/**
 * Represents an active encryption session for a project
 *
 * SEGURIDAD HARDENED:
 * - Session token NUNCA almacenado en memoria (solo en httpOnly cookie)
 * - Solo guardamos metadatos de expiración para UX
 * - Inmune a XSS - JavaScript no puede acceder al token
 */
interface EncryptionSession {
  expiresAt: number;  // Timestamp de expiración (solo para UI)
  hasSession: boolean; // Flag booleano
}

/**
 * Context type for encryption operations
 */
interface EncryptionContextType {
  setSession: (projectId: string, expiresIn: number) => void;
  clearSession: (projectId: string) => void;
  isSessionValid: (projectId: string) => boolean;
  getRemainingTime: (projectId: string) => number;
  checkSessionStatus: (projectId: string) => Promise<boolean>;
  refreshSession: (projectId: string) => Promise<boolean>;
}

const EncryptionContext = createContext<EncryptionContextType | undefined>(undefined);

const ENCRYPTION_CHANNEL = 'datamap_encryption_sessions';

/**
 * Provider component for managing encryption sessions across the application
 *
 * SEGURIDAD HARDENED:
 * - Session tokens en httpOnly cookies (inmunes a XSS)
 * - Solo metadatos de expiración en memoria (para UX)
 * - NUNCA localStorage (vulnerable a XSS)
 * - Cross-tab synchronization vía BroadcastChannel
 * - Automatic session expiry handling
 *
 * VULNERABILIDAD CORREGIDA: CRÍTICA
 * - Antes: Session tokens en localStorage (vulnerable a XSS)
 * - Ahora: Session tokens en httpOnly cookies (inmunes a XSS)
 * - Referencia: Auditoría de Seguridad 2025-01-03, Fase 1.1
 */
export const EncryptionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Solo guardamos metadatos de expiración en memoria
  // El session token real está en httpOnly cookie (inaccesible para JS)
  const [sessions, setSessions] = useState<Map<string, EncryptionSession>>(new Map());
  const channelRef = useRef<BroadcastChannel | null>(null);

  // Initialize BroadcastChannel for cross-tab communication
  useEffect(() => {
    if (typeof BroadcastChannel !== 'undefined') {
      try {
        channelRef.current = new BroadcastChannel(ENCRYPTION_CHANNEL);

        channelRef.current.onmessage = (event) => {
          const { type, projectId, expiresIn } = event.data;

          if (type === 'SESSION_CREATED') {
            setSessions(prev => new Map(prev).set(projectId, {
              hasSession: true,
              expiresAt: Date.now() + expiresIn * 1000
            }));
            if (import.meta.env.DEV) {
              console.log(`[EncryptionProvider] Session synced from another tab for project ${projectId.substring(0, 8)}...`);
            }
          } else if (type === 'SESSION_CLEARED') {
            setSessions(prev => {
              const newMap = new Map(prev);
              newMap.delete(projectId);
              return newMap;
            });
            if (import.meta.env.DEV) {
              console.log(`[EncryptionProvider] Session cleared from another tab for project ${projectId.substring(0, 8)}...`);
            }
          }
        };

        if (import.meta.env.DEV) {
          console.log('[EncryptionProvider] BroadcastChannel initialized');
        }
      } catch (error) {
        console.error('[EncryptionProvider] Error creating BroadcastChannel:', error);
      }
    }

    return () => {
      if (channelRef.current) {
        channelRef.current.close();
        if (import.meta.env.DEV) {
          console.log('[EncryptionProvider] BroadcastChannel closed');
        }
      }
    };
  }, []);

  /**
   * Check session status with the backend
   * @param projectId - UUID of the project
   * @returns Promise<boolean> - True if session is valid
   */
  const checkSessionStatus = useCallback(async (projectId: string): Promise<boolean> => {
    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/projects/${projectId}/encryption/session-status`,
        {
          credentials: 'include', // CRÍTICO: Enviar cookies httpOnly
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        return false;
      }

      const data = await response.json();

      if (data.has_session) {
        // Actualizar estado local con info de expiración
        setSessions(prev => new Map(prev).set(projectId, {
          hasSession: true,
          expiresAt: Date.now() + (data.expires_in_seconds * 1000)
        }));
        return true;
      }

      return false;
    } catch (error) {
      console.error('[EncryptionProvider] Error checking session status:', error);
      return false;
    }
  }, []);

  /**
   * Refresh encryption session (rotate token) - FASE 2.2
   *
   * SEGURIDAD:
   * - Rota el session token en el backend
   * - Previene session fixation attacks
   * - httpOnly cookie actualizada automáticamente
   * - Grace period de 30s para race conditions
   *
   * @param projectId - UUID of the project
   * @returns Promise<boolean> - True if rotation was successful
   */
  const refreshSession = useCallback(async (projectId: string): Promise<boolean> => {
    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/projects/${projectId}/encryption/refresh-session`,
        {
          method: 'POST',
          credentials: 'include', // CRÍTICO: Enviar cookies httpOnly
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        console.error('[EncryptionProvider] Failed to refresh session:', response.status);
        return false;
      }

      const data = await response.json();

      if (data.success) {
        // Actualizar estado local con nueva expiración
        const expiresIn = data.expires_in_seconds;
        setSessions(prev => new Map(prev).set(projectId, {
          hasSession: true,
          expiresAt: Date.now() + (expiresIn * 1000)
        }));

        if (import.meta.env.DEV) {
          console.log(
            `[EncryptionProvider] Session token rotated for project ${projectId.substring(0, 8)}..., ` +
            `expires in ${expiresIn}s, grace period: ${data.grace_period_seconds}s`
          );
        }

        // Broadcast to other tabs
        if (channelRef.current) {
          try {
            channelRef.current.postMessage({
              type: 'SESSION_CREATED', // Reusar evento existente
              projectId,
              expiresIn
            });
          } catch (error) {
            console.error('[EncryptionProvider] Error broadcasting session rotation:', error);
          }
        }

        return true;
      }

      return false;
    } catch (error) {
      console.error('[EncryptionProvider] Error refreshing session:', error);
      return false;
    }
  }, []);

  /**
   * Create or update a session for a project
   * SEGURIDAD: El token se guarda automáticamente en httpOnly cookie por el backend
   * Solo guardamos metadatos de expiración en memoria para UX
   *
   * @param projectId - UUID of the project
   * @param expiresIn - Expiration time in seconds
   */
  const setSession = useCallback((projectId: string, expiresIn: number) => {
    const expiresAt = Date.now() + expiresIn * 1000;

    // Update in-memory state (solo metadatos)
    setSessions(prev => new Map(prev).set(projectId, {
      hasSession: true,
      expiresAt
    }));

    if (import.meta.env.DEV) {
      console.log(`[EncryptionProvider] Session metadata updated for project ${projectId.substring(0, 8)}..., expires in ${expiresIn}s`);
    }

    // Broadcast to other tabs
    if (channelRef.current) {
      try {
        channelRef.current.postMessage({
          type: 'SESSION_CREATED',
          projectId,
          expiresIn
        });
      } catch (error) {
        console.error('[EncryptionProvider] Error broadcasting session creation:', error);
      }
    }
  }, []);

  /**
   * Clear a session for a project
   * SEGURIDAD: La cookie httpOnly se limpia automáticamente al expirar
   * Aquí solo limpiamos el estado local
   *
   * @param projectId - UUID of the project
   */
  const clearSession = useCallback((projectId: string) => {
    // Update in-memory state
    setSessions(prev => {
      const newMap = new Map(prev);
      newMap.delete(projectId);
      return newMap;
    });

    if (import.meta.env.DEV) {
      console.log(`[EncryptionProvider] Session metadata cleared for project ${projectId.substring(0, 8)}...`);
    }

    // Broadcast to other tabs
    if (channelRef.current) {
      try {
        channelRef.current.postMessage({
          type: 'SESSION_CLEARED',
          projectId
        });
      } catch (error) {
        console.error('[EncryptionProvider] Error broadcasting session clear:', error);
      }
    }
  }, []);

  /**
   * Check if a session is valid (exists and not expired)
   *
   * IMPORTANTE: Esto solo verifica el estado local en memoria
   *
   * PATRÓN CORRECTO para restaurar sesiones después de refresh:
   *
   * INCORRECTO:
   * ```ts
   * const hasSession = isSessionValid(projectId);  // Solo memoria, se pierde en refresh
   * ```
   *
   * CORRECTO:
   * ```ts
   * const hasSession = await checkSessionStatus(projectId);  // Verifica cookie httpOnly
   * ```
   *
   * Para verificación definitiva que restaure sesiones desde cookies, usar checkSessionStatus()
   *
   * @param projectId - UUID of the project
   * @returns True if session appears valid locally
   */
  const isSessionValid = useCallback((projectId: string): boolean => {
    const session = sessions.get(projectId);
    return session ? (session.hasSession && Date.now() < session.expiresAt) : false;
  }, [sessions]);

  /**
   * Get remaining time in seconds for a session
   * @param projectId - UUID of the project
   * @returns Remaining seconds or 0 if expired/not found
   */
  const getRemainingTime = useCallback((projectId: string): number => {
    const session = sessions.get(projectId);
    if (session && session.hasSession && Date.now() < session.expiresAt) {
      return Math.floor((session.expiresAt - Date.now()) / 1000);
    }
    return 0;
  }, [sessions]);

  const value: EncryptionContextType = {
    setSession,
    clearSession,
    isSessionValid,
    getRemainingTime,
    checkSessionStatus,
    refreshSession
  };

  return <EncryptionContext.Provider value={value}>{children}</EncryptionContext.Provider>;
};

/**
 * Hook to access encryption context
 * @throws Error if used outside EncryptionProvider
 */
// eslint-disable-next-line react-refresh/only-export-components
export const useEncryption = (): EncryptionContextType => {
  const context = useContext(EncryptionContext);
  if (!context) {
    throw new Error('useEncryption must be used within EncryptionProvider');
  }
  return context;
};
