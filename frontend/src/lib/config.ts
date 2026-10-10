/** Public runtime configuration. Never put secrets in VITE_* variables: they ship to the browser. */
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
