import type { TFunction } from 'i18next';
import type { ApiErrorResponse } from '@/services/api.service';

export function getApiError(error: unknown, t: TFunction): string {
  const err = error as Partial<ApiErrorResponse>;

  const code = err?.code;
  if (code) {
    const params = (err?.params ?? {}) as Record<string, unknown>;
    const key = `errors.${code}`;
    const msg = t(key as any, params);
    if (msg !== key) return msg;
  }

  const errType = err?.error;
  if (errType === 'timeout' || errType === 'network_error') {
    return t('errors.network');
  }

  return t('errors.generic');
}
