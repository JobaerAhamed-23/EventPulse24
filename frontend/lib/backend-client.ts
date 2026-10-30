import createClient from "openapi-fetch";

import type { paths } from "@/lib/api/schema";
import { apiBaseUrl } from "@/lib/api-base-url";
import { csrfOnRequest } from "@/lib/csrf";

/**
 * The only way frontend code reaches the backend (AD-19): typed from the generated schema.
 * In the browser requests stay on this site (/api/…), which proxy.ts forwards to Django;
 * on the Next.js server they go straight to API_BASE_URL.
 */
export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? (apiBaseUrl() ?? "") : "",
});

/**
 * **In the browser, every state-changing request carries the CSRF token** (D13).
 *
 * The backend checks the token itself on every unsafe request — Django Ninja exempts its
 * own views from Django's middleware, so `apps/identity/api_auth.py` does the check — and
 * this is the half that satisfies it. Registering it here, on the one client, means every
 * write in the app is covered: the auth forms, and the personal-event writes that existed
 * before this item and were never changed.
 *
 * It is not registered on the server. There is no `document` to read the cookie from, and
 * the server only ever reads.
 *
 * `requestToken` asks `GET /api/auth/csrf`, which issues the cookie. It goes through this
 * same client, which is deliberate — it is the one way to the backend — and it cannot
 * recurse, because the middleware ignores safe methods.
 */
if (typeof window !== "undefined") {
  api.use({
    onRequest: csrfOnRequest({
      requestToken: () => api.GET("/api/auth/csrf"),
    }),
  });
}
