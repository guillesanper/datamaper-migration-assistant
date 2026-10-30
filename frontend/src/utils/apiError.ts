import type { TFunction } from 'i18next';
import type { ApiErrorResponse } from '@/services/api.service';

export function getApiError(error: unknown, t: TFunction): string {
  const err = error as Partial<ApiErrorResponse>;

  const code = err?.code;
  if (code) {
    const key = `errors.${code}`;
    // El código llega del backend: clave dinámica, con defaultValue para que una clave sin
    // traducción devuelva la propia clave (y caiga a los mensajes genéricos de abajo)
    const msg = t(key, { ...err?.params, defaultValue: key });
    if (msg !== key) return msg;
  }

  const errType = err?.error;
  if (errType === 'timeout' || errType === 'network_error') {
    return t('errors.network');
  }

  return t('errors.generic');
}
