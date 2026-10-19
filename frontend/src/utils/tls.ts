// src/utils/tls.ts
// Reglas de TLS de las conexiones a BD externas que la UI comprueba antes de llamar a la API.
// Son solo ayuda de UX: el backend repite todas las validaciones (confirm_hostname incluida).

/** Longitud máxima del PEM de la CA propia (el backend rechaza más de 65 536 caracteres) */
export const MAX_CA_PEM_LENGTH = 65_536;

/**
 * Normaliza un hostname para compararlo: sin espacios, en minúsculas y sin el punto final.
 * Debe coincidir con normalize_hostname del backend (validators.py).
 */
export function normalizeHostname(value: string): string {
  const normalized = value.trim().toLowerCase();
  return normalized.endsWith('.') ? normalized.slice(0, -1) : normalized;
}

/** True si el texto escrito confirma el host de la conexión */
export function confirmsHostname(typed: string, host: string): boolean {
  const expected = normalizeHostname(host);
  return expected !== '' && normalizeHostname(typed) === expected;
}

/**
 * Comprobación previa de una CA propia: solo certificados PEM, nunca claves privadas.
 * El backend la valida y normaliza de verdad; esto evita subir un archivo equivocado.
 */
export function isPlausibleCaPem(text: string): boolean {
  if (text.length === 0 || text.length > MAX_CA_PEM_LENGTH) return false;
  if (text.includes('PRIVATE KEY')) return false;
  return text.includes('-----BEGIN CERTIFICATE-----') && text.includes('-----END CERTIFICATE-----');
}
