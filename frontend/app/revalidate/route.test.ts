// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const revalidatePath = vi.fn();
const revalidateTag = vi.fn();
vi.mock("next/cache", () => ({ revalidatePath, revalidateTag }));

const { GET, POST } = await import("./route");

const SECRET = "a-shared-secret";

function request(body: unknown, { token = SECRET }: { token?: string | null } = {}): Request {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token !== null) {
    headers.authorization = `Bearer ${token}`;
  }
  return new Request("http://127.0.0.1:3000/revalidate", {
    method: "POST",
    headers,
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

describe("POST /revalidate", () => {
  beforeEach(() => {
    vi.stubEnv("REVALIDATION_SECRET", SECRET);
    revalidatePath.mockClear();
    revalidateTag.mockClear();
  });

  afterEach(() => vi.unstubAllEnvs());

  it("revalidates every path it is given", async () => {
    const response = await POST(
      request({ paths: ["/events/jazz-night", "/events-in-brooklyn"], event_version: 7 }),
    );

    expect(response.status).toBe(200);
    expect(revalidatePath).toHaveBeenCalledTimes(2);
    expect(revalidatePath).toHaveBeenNthCalledWith(1, "/events/jazz-night");
    expect(revalidatePath).toHaveBeenNthCalledWith(2, "/events-in-brooklyn");
  });

  it("invalidates the data cache under the same path", async () => {
    // **The page and the facts are two different caches, and a signal must clear
    // both.** `revalidatePath` drops the *page* from the Full Route Cache — where a
    // statically generated public page lives. `revalidateTag` drops the *facts* from
    // the data cache — where a public event's payload lives, because the segment that
    // serves it is dynamic (it also serves the personal Detail Screen, and one segment
    // has one rendering mode).
    //
    // **The tag is the path itself.** `lib/public-event-read.ts` tags its cached read
    // with the event's own path, so a tag that was not the path would leave the
    // cache uncleared — and the stale page would stay live.
    const response = await POST(
      request({ paths: ["/events/jazz-night", "/events-in-brooklyn"], event_version: 7 }),
    );

    expect(response.status).toBe(200);
    expect(revalidateTag).toHaveBeenCalledTimes(2);
    expect(revalidateTag).toHaveBeenNthCalledWith(1, "/events/jazz-night", { expire: 0 });
    expect(revalidateTag).toHaveBeenNthCalledWith(2, "/events-in-brooklyn", { expire: 0 });
  });

  it("expires the cached facts now, not at the end of their own life", async () => {
    // **`expire: 0` means "expire now".** The signal means *this page is stale now*,
    // and a profile with no expiry would leave the entry alive until its own TTL — a
    // day of serving a page the backend has already corrected.
    await POST(request({ paths: ["/events/jazz-night"], event_version: 7 }));

    const [, profile] = revalidateTag.mock.calls[0] as [string, { expire?: number }];
    expect(profile.expire).toBe(0);
  });

  it("refuses a wrong secret and revalidates nothing", async () => {
    const response = await POST(
      request({ paths: ["/events/jazz-night"], event_version: 2 }, { token: "wrong" }),
    );

    expect(response.status).toBe(401);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("refuses a request with no secret at all", async () => {
    const response = await POST(
      request({ paths: ["/events/jazz-night"], event_version: 2 }, { token: null }),
    );

    expect(response.status).toBe(401);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("fails closed when the deployment has no secret configured", async () => {
    vi.stubEnv("REVALIDATION_SECRET", "");

    const response = await POST(request({ paths: ["/events/jazz-night"], event_version: 2 }));

    expect(response.status).toBe(503);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("answers 400 for a body that is not JSON", async () => {
    const response = await POST(request("not json at all"));

    expect(response.status).toBe(400);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("answers 400 for a body with no paths", async () => {
    const response = await POST(request({ paths: [], event_version: 2 }));

    expect(response.status).toBe(400);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("answers 400 for a path that is not a path on this site", async () => {
    const response = await POST(
      request({ paths: ["https://elsewhere.example/events"], event_version: 2 }),
    );

    expect(response.status).toBe(400);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("answers 400 for a version that is not a positive integer", async () => {
    const response = await POST(request({ paths: ["/events/jazz-night"], event_version: 0 }));

    expect(response.status).toBe(400);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("is harmless to repeat", async () => {
    const body = { paths: ["/events/jazz-night"], event_version: 2 };

    const first = await POST(request(body));
    const second = await POST(request(body));

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    // Rebuilding twice is idempotent by construction: the second invalidation finds
    // nothing to invalidate.
    expect(revalidatePath).toHaveBeenCalledTimes(2);
  });

  it("reads no cookie", async () => {
    const withCookie = new Request("http://127.0.0.1:3000/revalidate", {
      method: "POST",
      headers: { authorization: `Bearer ${SECRET}`, cookie: "session=whatever" },
      body: JSON.stringify({ paths: ["/events/jazz-night"], event_version: 2 }),
    });

    await POST(withCookie);

    // A session cookie is irrelevant here: the backend authenticates with the shared
    // secret. Reading one would widen the endpoint's trust boundary for no reason.
    expect(withCookie.headers.get("cookie")).toBe("session=whatever");
    expect(revalidatePath).toHaveBeenCalledTimes(1);
  });
});

describe("GET /revalidate", () => {
  it("is refused, so the endpoint cannot be triggered by a link", async () => {
    const response = await GET();

    expect(response.status).toBe(405);
    expect(response.headers.get("allow")).toBe("POST");
  });
});
