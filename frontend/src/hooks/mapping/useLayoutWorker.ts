/**
 * Hook for using the layout Web Worker
 *
 * OPTIMIZATION: Offloads heavy layout calculations to a Web Worker
 * to keep the UI responsive during large project rendering
 */

import { useRef, useCallback } from 'react';
import type { Node, Edge } from 'reactflow';

interface UseLayoutWorkerResult {
  calculateLayout: (nodes: Node[], edges: Edge[]) => Promise<{ nodes: Node[]; edges: Edge[] }>;
  terminateWorker: () => void;
}

export function useLayoutWorker(): UseLayoutWorkerResult {
  const workerRef = useRef<Worker | null>(null);
  const pendingRequestsRef = useRef<Map<number, {
    resolve: (result: { nodes: Node[]; edges: Edge[] }) => void;
    reject: (error: Error) => void;
  }>>(new Map());
  const requestIdRef = useRef(0);

  // Initialize worker on first use
  const getWorker = useCallback(() => {
    if (!workerRef.current) {
      // Create worker using Vite's special syntax for Web Workers
      workerRef.current = new Worker(
        new URL('../../workers/layout.worker.ts', import.meta.url),
        { type: 'module' }
      );

      // Setup message handler
      workerRef.current.onmessage = (event) => {
        const { type, payload, requestId } = event.data;

        if (type === 'LAYOUT_CALCULATED' && requestId !== undefined) {
          const pending = pendingRequestsRef.current.get(requestId);
          if (pending) {
            pending.resolve(payload);
            pendingRequestsRef.current.delete(requestId);
          }
        }
      };

      // Setup error handler
      workerRef.current.onerror = (error) => {
        console.error('[useLayoutWorker] Worker error:', error);
        // Reject all pending requests
        pendingRequestsRef.current.forEach(({ reject }) => {
          reject(new Error('Worker failed'));
        });
        pendingRequestsRef.current.clear();
      };
    }

    return workerRef.current;
  }, []);

  const calculateLayout = useCallback(
    (nodes: Node[], edges: Edge[]): Promise<{ nodes: Node[]; edges: Edge[] }> => {
      return new Promise((resolve, reject) => {
        try {
          const worker = getWorker();
          const requestId = requestIdRef.current++;

          // Store promise handlers
          pendingRequestsRef.current.set(requestId, { resolve, reject });

          // Send message to worker
          worker.postMessage({
            type: 'CALCULATE_LAYOUT',
            payload: { nodes, edges },
            requestId,
          });
        } catch (error) {
          reject(error);
        }
      });
    },
    [getWorker]
  );

  const terminateWorker = useCallback(() => {
    if (workerRef.current) {
      workerRef.current.terminate();
      workerRef.current = null;
      pendingRequestsRef.current.clear();
    }
  }, []);

  return {
    calculateLayout,
    terminateWorker,
  };
}
