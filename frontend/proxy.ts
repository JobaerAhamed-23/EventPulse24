import { NextResponse, type NextRequest } from "next/server";

import { apiBaseUrl } from "@/lib/api-base-url";

// The browser only ever calls /api/* on this site; Next forwards it to Django. Same origin, so
// no CORS, and cookies stay first-party. Runs per request, so API_BASE_URL can change without a
// rebuild (next.config rewrites would be fixed at build time).
// Note: Next adds an x-middleware-rewrite response header naming the backend URL.

let reportedMissing = false;

export function proxy(request: NextRequest) {
  const base = apiBaseUrl();
  if (!base) {
    if (!reportedMissing) {
      console.error("API_BASE_URL is not set: /api requests answer 503 until it is.");
      reportedMissing = true;
    }
    return NextResponse.json(
      { code: "api_not_configured", message: "The service isn't available right now." },
      { status: 503 },
    );
  }
  const { pathname, search } = request.nextUrl;
  return NextResponse.rewrite(new URL(`${pathname}${search}`, base));
}

export const config = { matcher: "/api/:path*" };
