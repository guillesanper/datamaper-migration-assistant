// src/hooks/useCancellableRequest.ts
import { useEffect, useRef, useCallback } from "react";

/**
 * Hook para manejar requests cancelables
 * Útil para evitar memory leaks cuando componentes se desmontan
 */
export const useCancellableRequest = () => {
  const abortControllersRef = useRef<Set<AbortController>>(new Set());

  /**
   * Crea un nuevo AbortController y lo registra
   */
  const createController = useCallback((): AbortController => {
    const controller = new AbortController();
    abortControllersRef.current.add(controller);
    return controller;
  }, []);

  /**
   * Remueve un controller del registro
   */
  const removeController = useCallback((controller: AbortController) => {
    abortControllersRef.current.delete(controller);
  }, []);

  /**
   * Cancela todos los requests pendientes
   */
  const cancelAll = useCallback(() => {
    abortControllersRef.current.forEach((controller) => {
      controller.abort();
    });
    abortControllersRef.current.clear();
  }, []);

  /**
   * Wrapper para fetch con auto-cleanup
   */
  const cancellableFetch = useCallback(
    async <T = unknown>(
      url: string,
      options?: RequestInit
    ): Promise<T> => {
      const controller = createController();

      try {
        const response = await fetch(url, {
          ...options,
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        return data;
      } finally {
        removeController(controller);
      }
    },
    [createController, removeController]
  );

  //  Cleanup: Cancelar todos los requests al desmontar
  useEffect(() => {
    return () => {
      cancelAll();
    };
  }, [cancelAll]);

  return {
    createController,
    removeController,
    cancelAll,
    cancellableFetch,
  };
};

/**
 *  Hook simplificado para un único request cancelable
 */
export const useSingleCancellableRequest = () => {
  const abortControllerRef = useRef<AbortController | null>(null);

  /**
   * Cancela el request actual y retorna un nuevo controller
   */
  const getController = useCallback((): AbortController => {
    // Cancelar request anterior si existe
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Crear nuevo controller
    const controller = new AbortController();
    abortControllerRef.current = controller;
    return controller;
  }, []);

  /**
   * Cancela el request actual
   */
  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  //  Cleanup
  useEffect(() => {
    return () => {
      cancel();
    };
  }, [cancel]);

  return { getController, cancel };
};

export default useCancellableRequest;
