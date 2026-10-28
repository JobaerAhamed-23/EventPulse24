// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEV_API_BASE_URL } from "@/lib/api-base-url";
import { config, proxy } from "@/proxy";

// NextResponse.rewrite records its target in this header; Next acts on it.
const REWRITE_HEADER = "x-middleware-rewrite";

function call(path: string) {
  return proxy(new NextRequest(new URL(path, "http://127.0.0.1:3000")));
}

describe("proxy", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("only runs for /api/*", () => {
    expect(config.matcher).toBe("/api/:path*");
  });

  it("forwards to API_BASE_URL read at request time, keeping path and query", () => {
    vi.stubEnv("API_BASE_URL", "http://api.internal:9000");
    expect(call("/api/health?verbose=1").headers.get(REWRITE_HEADER)).toBe(
      "http://api.internal:9000/api/health?verbose=1",
    );

    vi.stubEnv("API_BASE_URL", "http://elsewhere:8001");
    expect(call("/api/health").headers.get(REWRITE_HEADER)).toBe(
      "http://elsewhere:8001/api/health",
    );
  });

  it("falls back to the local API outside production", () => {
    vi.stubEnv("API_BASE_URL", "");
    vi.stubEnv("NODE_ENV", "development");

    expect(call("/api/health").headers.get(REWRITE_HEADER)).toBe(`${DEV_API_BASE_URL}/api/health`);
  });

  it("answers 503 in the shared error shape in production without API_BASE_URL", async () => {
    vi.stubEnv("API_BASE_URL", "");
    vi.stubEnv("NODE_ENV", "production");
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});

    const response = call("/api/health");

    expect(response.status).toBe(503);
    expect(response.headers.get(REWRITE_HEADER)).toBeNull();
    expect(await response.json()).toEqual({
      code: "api_not_configured",
      message: "The service isn't available right now.",
    });
    expect(logged).toHaveBeenCalledTimes(1);
    logged.mockRestore();
  });
});
