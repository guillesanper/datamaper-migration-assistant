import React, { useState, useEffect, useRef } from 'react';
import { X, Loader2, Eye, EyeOff, Lock, AlertCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { encryptionService } from '../../services/encryption.service';
import { useEncryption } from '../../providers/EncryptionProvider';
import { secureCleanupState } from '../../utils/secureMemory';

interface EncryptionUnlockModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUnlock: () => void;
  projectId: string;
  projectName: string;
}

/**
 * Modal for unlocking encrypted projects
 *
 * Features:
 * - Password input with show/hide toggle
 * - Submit on Enter key
 * - ESC key to cancel (unless loading)
 * - Auto-focus on password field
 * - Loading states with spinner
 * - Error display for invalid passphrase
 * - Network error handling
 */
export const EncryptionUnlockModal: React.FC<EncryptionUnlockModalProps> = ({
  isOpen,
  onClose,
  onUnlock,
  projectId,
  projectName
}) => {
  const [passphrase, setPassphrase] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const inputRef = useRef<HTMLInputElement>(null);
  const { setSession } = useEncryption();

  // Auto-focus input when modal opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      // Small delay to ensure modal is rendered
      const timeoutId = setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timeoutId);
    }
  }, [isOpen]);

  // Clear form when modal closes
  // FASE 2.3: Secure memory cleanup
  useEffect(() => {
    if (!isOpen) {
      secureCleanupState(setPassphrase); // Limpiar passphrase de memoria
      setError('');
      setShowPassword(false);
    }
  }, [isOpen]);

  // FASE 2.3: Auto-cleanup al desmontar componente
  useEffect(() => {
    return () => {
      secureCleanupState(setPassphrase);
    };
  }, []);

  // ESC key handling
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !isLoading) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, isLoading, onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!passphrase.trim()) {
      setError('Por favor introduce la passphrase');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const response = await encryptionService.verifyPassphrase(projectId, passphrase);

      if (response.valid && response.expires_in_seconds) {
        // Store session (token está en httpOnly cookie, solo guardamos metadatos de expiración)
        setSession(projectId, response.expires_in_seconds);

        console.log(
          `[EncryptionUnlockModal] Session created successfully, expires in ${response.expires_in_seconds}s`
        );

        // FASE 2.3: Limpiar passphrase INMEDIATAMENTE después de uso exitoso
        secureCleanupState(setPassphrase);

        // Success - call onUnlock and close
        onUnlock();
      } else {
        setError('Passphrase incorrecta');
        secureCleanupState(setPassphrase); // Limpiar passphrase incorrecta
        inputRef.current?.focus();
      }
    } catch (err: unknown) {
      console.error('[EncryptionUnlockModal] Error verifying passphrase:', err);

      const errObj = err as Record<string, unknown>;
      if (errObj.error === 'network_error') {
        setError('Error de conexión. Verifica tu internet e intenta de nuevo.');
      } else if (errObj.error === 'timeout') {
        setError('La verificación tardó demasiado. Intenta de nuevo.');
      } else if (errObj.status === 401 || errObj.status === 403) {
        setError('Passphrase incorrecta');
        secureCleanupState(setPassphrase); // Limpiar passphrase incorrecta
        inputRef.current?.focus();
      } else {
        setError(err instanceof Error ? err.message : 'Error al verificar la passphrase');
      }
    } finally {
      setIsLoading(false);
      // FASE 2.3: Garantizar limpieza incluso si hubo error
      secureCleanupState(setPassphrase);
    }
  };

  const handleCancel = () => {
    if (!isLoading) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="relative w-full max-w-md bg-card border rounded-lg shadow-lg p-6 m-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Lock className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h2 className="text-xl font-semibold">Proyecto Cifrado</h2>
              <p className="text-sm text-muted-foreground mt-1">
                {projectName}
              </p>
            </div>
          </div>
          <button
            onClick={handleCancel}
            disabled={isLoading}
            className="text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Cerrar modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Info Box */}
        <div className="mb-6 p-4 bg-primary/5 border border-primary/20 rounded-lg">
          <p className="text-sm text-muted-foreground">
            Este proyecto está cifrado. Introduce la passphrase para desbloquear
            y acceder a los datos. La sesión permanecerá activa durante 3 horas.
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label htmlFor="passphrase" className="block text-sm font-medium mb-2">
              Passphrase
            </label>
            <div className="relative">
              <input
                ref={inputRef}
                id="passphrase"
                type={showPassword ? 'text' : 'password'}
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
                disabled={isLoading}
                className="w-full px-4 py-2 pr-10 border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed bg-background"
                placeholder="Introduce tu passphrase"
                autoComplete="off"
                aria-describedby={error ? 'passphrase-error' : undefined}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                disabled={isLoading}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                tabIndex={-1}
                aria-label={showPassword ? 'Ocultar passphrase' : 'Mostrar passphrase'}
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>

          {/* Error Display */}
          {error && (
            <div
              id="passphrase-error"
              className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-2"
              role="alert"
            >
              <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={handleCancel}
              disabled={isLoading}
              className="flex-1"
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={isLoading || !passphrase.trim()}
              className="flex-1"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Verificando...
                </>
              ) : (
                'Desbloquear'
              )}
            </Button>
          </div>
        </form>

        {/* Help Text */}
        <div className="mt-4 text-center">
          <p className="text-xs text-muted-foreground">
            ¿Olvidaste tu passphrase? Contacta al administrador del proyecto.
          </p>
        </div>
      </div>
    </div>
  );
};
