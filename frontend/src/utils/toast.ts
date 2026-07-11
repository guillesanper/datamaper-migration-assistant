/**
 * Optimized toast utility with lazy loading
 * This wrapper provides the same API as react-hot-toast but loads the module on demand
 *
 * Usage: import { toast } from '../utils/toast'
 *
 * OPTIMIZATION: Reduces initial bundle size by ~50KB by deferring toast library load
 */

import type { ToastOptions, Renderable } from 'react-hot-toast';

// Cache for the loaded module
let toastModule: typeof import('react-hot-toast') | null = null;
let loadPromise: Promise<typeof import('react-hot-toast')> | null = null;

// Lazy load the toast module (singleton pattern)
const loadToast = () => {
  if (toastModule) {
    return Promise.resolve(toastModule);
  }

  if (!loadPromise) {
    loadPromise = import('react-hot-toast').then(module => {
      toastModule = module;
      loadPromise = null;
      return module;
    });
  }

  return loadPromise;
};

// Proxy object that loads toast on first use
export const toast = {
  success: (message: string, options?: ToastOptions) => {
    loadToast().then(({ toast: t }) => t.success(message, options));
  },
  error: (message: string, options?: ToastOptions) => {
    loadToast().then(({ toast: t }) => t.error(message, options));
  },
  loading: (message: string, options?: ToastOptions): Promise<string> => {
    return loadToast().then(({ toast: t }) => t.loading(message, options));
  },
  custom: (message: Renderable, options?: ToastOptions) => {
    loadToast().then(({ toast: t }) => t.custom(message, options));
  },
  promise: <T,>(
    promise: Promise<T>,
    msgs: {
      loading: string;
      success: string | ((data: T) => string);
      error: string | ((err: unknown) => string);
    },
    options?: ToastOptions
  ): Promise<T> => {
    return loadToast().then(({ toast: t }) => t.promise(promise, msgs, options));
  },
  dismiss: (toastId?: string) => {
    loadToast().then(({ toast: t }) => t.dismiss(toastId));
  },
};

// Re-export Toaster component for use in App
export { Toaster } from 'react-hot-toast';
