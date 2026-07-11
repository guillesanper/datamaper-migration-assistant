/**
 * Utilidades para manejo seguro de datos sensibles en memoria (FASE 2.3)
 *
 * SEGURIDAD:
 * - Limpieza de passphrases después de uso
 * - Reducción de ventana de exposición en memoria
 * - Prevención de memory dumps con datos sensibles
 *
 * LIMITACIONES:
 * - JavaScript no permite true memory scrubbing (GC es no-determinístico)
 * - Estas funciones reducen ventana de exposición pero no garantizan eliminación total
 * - Para seguridad completa, las passphrases nunca deberían estar en memoria del navegador
 *
 * Autor: DataMap Security Team
 * Fecha: 2025-01-04
 */

/**
 * Limpia una variable de estado de React que contiene datos sensibles
 *
 * Esta función hace lo mejor posible para eliminar datos sensibles de la memoria,
 * pero debido a limitaciones de JavaScript/GC, no puede garantizar eliminación total.
 *
 * Estrategia:
 * 1. Sobrescribir string con vacío (libera referencia)
 * 2. Sobrescribir con caracteres aleatorios (dificulta recuperación)
 * 3. Limpiar final (intentar forzar GC)
 *
 * @param setValue - Función setState de React
 *
 * @example
 * ```typescript
 * const [passphrase, setPassphrase] = useState('');
 *
 * // Después de usar passphrase
 * secureCleanupState(setPassphrase);
 * ```
 */
export function secureCleanupState(setValue: (value: string) => void): void {
  try {
    // Sobrescribir con string vacío
    setValue('');

    // Sobrescribir con caracteres aleatorios (hace más difícil recuperación)
    const randomLength = 32 + Math.floor(Math.random() * 32); // 32-64 chars
    const randomChars = Array.from({ length: randomLength }, () =>
      String.fromCharCode(Math.floor(Math.random() * 94) + 33)
    ).join('');

    setValue(randomChars);

    // Limpiar final
    setValue('');

    // Intentar sugerir GC (no garantizado)
    // En navegadores, gc() no está disponible, solo en Node.js con --expose-gc
    const globalWithGc = globalThis as Record<string, unknown>;
    if (typeof globalThis !== 'undefined' && typeof globalWithGc.gc === 'function') {
      (globalWithGc.gc as () => void)();
    }
  } catch (error) {
    // Fallback silencioso: al menos intentar limpiar
    setValue('');
    console.error('[secureMemory] Error during cleanup:', error);
  }
}

/**
 * Limpia una variable local/const que contiene datos sensibles
 *
 * Nota: Esta función tiene limitaciones severas en JavaScript ya que
 * las strings son inmutables. Solo puede limpiar la referencia, no la memoria.
 *
 * @param value - String a limpiar
 * @returns String vacío (para reasignación)
 *
 * @example
 * ```typescript
 * let passphrase = 'my-secret-password';
 * // ... usar passphrase ...
 * passphrase = secureCleanupString(passphrase);
 * ```
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function secureCleanupString(_value: string): string {
  // En JavaScript, strings son inmutables
  // Lo mejor que podemos hacer es retornar vacío y dejar que GC limpie
  return '';
}

/**
 * Hook personalizado para manejo seguro de passphrases en React
 *
 * Limpia automáticamente la passphrase cuando el componente se desmonta
 *
 * @param initialValue - Valor inicial (default: '')
 * @returns [value, setValue, secureCleanup]
 *
 * @example
 * ```typescript
 * function MyComponent() {
 *   const [passphrase, setPassphrase, cleanupPassphrase] = useSecureState('');
 *
 *   const handleSubmit = async () => {
 *     try {
 *       await submitPassphrase(passphrase);
 *     } finally {
 *       // CRÍTICO: Limpiar después de uso
 *       cleanupPassphrase();
 *     }
 *   };
 *
 *   // Auto-cleanup al desmontar
 *   return <form onSubmit={handleSubmit}>...</form>;
 * }
 * ```
 */
export function useSecureState(
  initialValue: string = ''
): [string, React.Dispatch<React.SetStateAction<string>>, () => void] {
  const [value, setValue] = React.useState(initialValue);

  // Cleanup function
  const secureCleanup = React.useCallback(() => {
    secureCleanupState(setValue);
  }, []);

  // Auto-cleanup al desmontar componente
  React.useEffect(() => {
    return () => {
      secureCleanupState(setValue);
    };
  }, []);

  return [value, setValue, secureCleanup];
}

/**
 * Limpia un array de strings sensibles
 *
 * @param values - Array de strings a limpiar
 *
 * @example
 * ```typescript
 * const sensitiveData = ['password1', 'password2', 'api-key'];
 * secureCleanupArray(sensitiveData);
 * // sensitiveData ahora está vacío
 * ```
 */
export function secureCleanupArray(values: string[]): void {
  // Sobrescribir cada elemento
  for (let i = 0; i < values.length; i++) {
    values[i] = '';
  }

  // Vaciar array
  values.length = 0;
}

/**
 * Limpia un objeto que contiene campos sensibles
 *
 * @param obj - Objeto a limpiar
 * @param sensitiveKeys - Array de claves a limpiar
 *
 * @example
 * ```typescript
 * const formData = {
 *   username: 'john',
 *   passphrase: 'secret123',
 *   email: 'john@example.com'
 * };
 *
 * secureCleanupObject(formData, ['passphrase']);
 * // formData.passphrase ahora está vacío
 * ```
 */
export function secureCleanupObject<T extends Record<string, unknown>>(
  obj: T,
  sensitiveKeys: (keyof T)[]
): void {
  for (const key of sensitiveKeys) {
    if (typeof obj[key] === 'string') {
      obj[key] = '' as T[keyof T];
    }
  }
}

/**
 * Valida que un campo sensible fue limpiado correctamente
 *
 * Útil en tests y debugging
 *
 * @param value - Valor a verificar
 * @returns true si el valor está vacío
 *
 * @example
 * ```typescript
 * if (__DEV__) {
 *   console.assert(isCleanedUp(passphrase), 'Passphrase no fue limpiada!');
 * }
 * ```
 */
export function isCleanedUp(value: string): boolean {
  return value === '' || value === null || value === undefined;
}

/**
 * Wrapper para funciones async que manejan datos sensibles
 *
 * Garantiza limpieza incluso si la función falla
 *
 * @param fn - Función async a ejecutar
 * @param cleanup - Función de limpieza a llamar al final
 *
 * @example
 * ```typescript
 * await withSecureCleanup(
 *   async () => {
 *     await submitPassphrase(passphrase);
 *   },
 *   () => secureCleanupState(setPassphrase)
 * );
 * ```
 */
export async function withSecureCleanup<T>(
  fn: () => Promise<T>,
  cleanup: () => void
): Promise<T> {
  try {
    return await fn();
  } finally {
    cleanup();
  }
}

// Re-export React para el hook
import * as React from 'react';
