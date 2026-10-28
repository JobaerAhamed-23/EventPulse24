/** Where the Django API lives: an origin such as "http://127.0.0.1:8000" (any path is ignored). */
export const DEV_API_BASE_URL = "http://127.0.0.1:8000";

/**
 * API_BASE_URL, read when called (per request in proxy.ts), never baked in at build time.
 * Outside production it falls back to the local API; in production it must be set.
 */
export function apiBaseUrl(): string | undefined {
  const configured = process.env.API_BASE_URL;
  if (configured) return configured;
  return process.env.NODE_ENV === "production" ? undefined : DEV_API_BASE_URL;
}
