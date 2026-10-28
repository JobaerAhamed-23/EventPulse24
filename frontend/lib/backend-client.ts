import createClient from "openapi-fetch";

import type { paths } from "@/lib/api/schema";
import { apiBaseUrl } from "@/lib/api-base-url";

/**
 * The only way frontend code reaches the backend (AD-19): typed from the generated schema.
 * In the browser requests stay on this site (/api/…), which proxy.ts forwards to Django;
 * on the Next.js server they go straight to API_BASE_URL.
 */
export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? (apiBaseUrl() ?? "") : "",
});
