import { beforeEach, describe, expect, it, vi } from "vitest";

import { readConflicts } from "@/lib/conflict-list-read";

/**
 * The Conflict Review's server-side read.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous — and an anonymous read of somebody's conflicts answers with an empty list,
 * which reads exactly like "you have no overlaps". That is a lie about the world, so
 * the cookies are pinned here.
 *
 * **Two answers, not one.** `pairs` is the server's answer; `unavailable` is a failure
 * to answer. They are deliberately not folded together: a failed read must not render
 * "No overlaps."
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

const PAIRS = {
  active: [
    {
      actions: ["keep_both", "edit_new", "skip_public"],
      kind: "time",
      left: {
        available: true,
        id: "11111111-1111-1111-1111-111111111111",
        kind: "personal_event",
        name: "Work standup",
        start_time_tz: "America/New_York",
        start_time_utc: "2026-09-08T13:00:00Z",
      },
      pair_id: "44444444-4444-4444-4444-444444444444",
      right: {
        available: true,
        id: "22222222-2222-2222-2222-222222222222",
        kind: "saved_event",
        name: "Designers coffee chat",
        start_time_tz: "America/New_York",
        start_time_utc: "2026-09-08T13:15:00Z",
      },
      status: "active",
    },
  ],
  resolved: [],
};

beforeEach(() => {
  GET.mockReset();
  apiBaseUrl.mockReset();
  cookies.mockReset();
  apiBaseUrl.mockReturnValue("http://127.0.0.1:8000");
  cookies.mockResolvedValue({ toString: () => "sessionid=abc; csrftoken=tok" });
});

describe("readConflicts", () => {
  it("reads the pairs with the visitor's cookies", async () => {
    GET.mockResolvedValue({ data: PAIRS, error: undefined, response: new Response(null) });

    const read = await readConflicts();

    expect(read).toEqual({ kind: "pairs", pairs: PAIRS });
    const [path, options] = GET.mock.calls[0] as [string, { headers: { cookie: string } }];
    expect(path).toBe("/api/personal/conflicts");
    expect(options.headers.cookie).toBe("sessionid=abc; csrftoken=tok");
  });

  it("answers 'unavailable' when there is no API to ask", async () => {
    apiBaseUrl.mockReturnValue(null);

    expect(await readConflicts()).toEqual({ kind: "unavailable" });
    expect(GET).not.toHaveBeenCalled();
  });

  it("answers 'unavailable' when the request fails", async () => {
    GET.mockRejectedValue(new Error("connection refused"));

    expect(await readConflicts()).toEqual({ kind: "unavailable" });
  });

  it("answers 'unavailable' when the API answers with an error", async () => {
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_authenticated", message: "Please sign in to continue." },
      response: new Response(null, { status: 401 }),
    });

    expect(await readConflicts()).toEqual({ kind: "unavailable" });
  });

  it("never answers 'unavailable' as if the user had no conflicts", async () => {
    // A failed read must not be indistinguishable from an empty list.
    GET.mockRejectedValue(new Error("connection refused"));

    const read = await readConflicts();

    expect(read.kind).not.toBe("pairs");
  });
});
