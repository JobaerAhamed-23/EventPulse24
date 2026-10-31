import { beforeEach, describe, expect, it, vi } from "vitest";

import { readTimeline } from "@/lib/timeline-read";

/**
 * The Timeline's server-side read.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous — and a signed-in user's own Timeline telling them they have nothing is
 * exactly the bug `lib/session.ts` documents. This is the first thing to break and the
 * hardest to notice, so it is pinned here.
 *
 * **Two answers, not one.** `week` is a week; `unavailable` is a failure to answer.
 * They are deliberately not folded together: telling a user their week is quiet
 * because a request failed would be a lie about the world.
 */

const GET = vi.fn();
const apiBaseUrl = vi.fn();
const cookies = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { GET: (...args: unknown[]) => GET(...args) },
}));

vi.mock("@/lib/api-base-url", () => ({
  apiBaseUrl: (...args: unknown[]) => apiBaseUrl(...args),
}));

vi.mock("next/headers", () => ({
  cookies: () => cookies(),
}));

const WEEK = {
  days: [
    { blocks: [], date: "2026-11-02" },
    { blocks: [], date: "2026-11-03" },
    { blocks: [], date: "2026-11-04" },
    { blocks: [], date: "2026-11-05" },
    { blocks: [], date: "2026-11-06" },
    { blocks: [], date: "2026-11-07" },
    { blocks: [], date: "2026-11-08" },
  ],
  timezone: "America/New_York",
  week_end: "2026-11-08",
  week_start: "2026-11-02",
};

beforeEach(() => {
  GET.mockReset();
  apiBaseUrl.mockReset();
  cookies.mockReset();
  apiBaseUrl.mockReturnValue("http://127.0.0.1:8000");
  cookies.mockResolvedValue({ toString: () => "sessionid=abc; csrftoken=tok" });
});

describe("readTimeline", () => {
  it("reads the week with the visitor's cookies", async () => {
    GET.mockResolvedValue({ data: WEEK, error: undefined, response: new Response(null) });

    const read = await readTimeline();

    expect(read).toEqual({ kind: "week", week: WEEK });
    const [, options] = GET.mock.calls[0] as [string, { headers: { cookie: string } }];
    expect(options.headers.cookie).toBe("sessionid=abc; csrftoken=tok");
  });

  it("sends the week it was given", async () => {
    GET.mockResolvedValue({ data: WEEK, error: undefined, response: new Response(null) });

    await readTimeline("2026-11-02");

    const [, options] = GET.mock.calls[0] as [
      string,
      { params: { query: { week: string | undefined } } },
    ];
    expect(options.params.query.week).toBe("2026-11-02");
  });

  it("sends no week when the caller named none", async () => {
    GET.mockResolvedValue({ data: WEEK, error: undefined, response: new Response(null) });

    await readTimeline();

    const [, options] = GET.mock.calls[0] as [
      string,
      { params: { query: { week: string | undefined } } },
    ];
    expect(options.params.query.week).toBeUndefined();
  });

  it("answers 'unavailable' when there is no API to ask", async () => {
    apiBaseUrl.mockReturnValue(null);

    expect(await readTimeline()).toEqual({ kind: "unavailable" });
    expect(GET).not.toHaveBeenCalled();
  });

  it("answers 'unavailable' when the request fails", async () => {
    GET.mockRejectedValue(new Error("connection refused"));

    expect(await readTimeline()).toEqual({ kind: "unavailable" });
  });

  it("answers 'unavailable' when the API answers with an error", async () => {
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_authenticated", message: "Please sign in to continue." },
      response: new Response(null, { status: 401 }),
    });

    expect(await readTimeline()).toEqual({ kind: "unavailable" });
  });
});
