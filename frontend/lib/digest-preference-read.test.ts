import { beforeEach, describe, expect, it, vi } from "vitest";

import { readDigestPreference } from "@/lib/digest-preference-read";

/**
 * The Pulse Digest preference's server-side read.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous — and an anonymous read of somebody's digest preference answers with
 * *somebody else's* default, which would render the opt-out toggle in the wrong state
 * and send the wrong value back on the next save. That is why the cookie is pinned here
 * rather than assumed.
 *
 * **Two answers, not one.** `found` is the server's answer; `unavailable` is a failure
 * to answer. They are deliberately not folded together: a failed read must never render
 * as "the opt-out is off", because that is a setting the user never changed.
 *
 * **The returned shape is narrower than the API's.** The city is not one of the three
 * fields, and the assertion below that it is absent is a real claim — a caller that
 * found a city here would be tempted to send it back, and the endpoint cannot clear it.
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

/** The onboarding state the API returns, with the digest block filled in. */
function state(overrides: Record<string, unknown> = {}) {
  return {
    completed: true,
    current_step: null,
    step_name: null,
    interests: [],
    last_advanced_at: null,
    completed_at: null,
    digest: {
      city: "Brooklyn",
      city_source: "geo",
      delivery_time: "08:00:00",
      timezone: "America/New_York",
      include_personal_events: true,
    },
    ...overrides,
  };
}

beforeEach(() => {
  GET.mockReset();
  apiBaseUrl.mockReset();
  cookies.mockReset();
  apiBaseUrl.mockReturnValue("http://127.0.0.1:8000");
  cookies.mockResolvedValue({ toString: () => "sessionid=abc; csrftoken=tok" });
});

describe("readDigestPreference", () => {
  it("reads the preference with the visitor's cookies", async () => {
    GET.mockResolvedValue({ data: state(), error: undefined, response: new Response(null) });

    const read = await readDigestPreference();

    expect(read).toEqual({
      kind: "found",
      preference: {
        delivery_time: "08:00:00",
        timezone: "America/New_York",
        include_personal_events: true,
      },
    });
    const [path, options] = GET.mock.calls[0] as [string, { headers: { cookie: string } }];
    expect(path).toBe("/api/personal/onboarding");
    expect(options.headers.cookie).toBe("sessionid=abc; csrftoken=tok");
  });

  it("reads the onboarding endpoint, not a digest-specific one", async () => {
    // **There is no digest-preference GET.** The read has to go to the onboarding state
    // endpoint, which is where the digest block lives — and the path is pinned so a
    // rename cannot silently send it somewhere that answers 404.
    GET.mockResolvedValue({ data: state(), response: new Response(null) });

    await readDigestPreference();

    expect(GET.mock.calls[0]?.[0]).toBe("/api/personal/onboarding");
  });

  it("returns the opt-out as the server stated it", async () => {
    GET.mockResolvedValue({
      data: state({
        digest: {
          city: null,
          city_source: null,
          delivery_time: "08:00:00",
          timezone: "America/New_York",
          include_personal_events: false,
        },
      }),
      response: new Response(null),
    });

    const read = await readDigestPreference();

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    expect(read.preference.include_personal_events).toBe(false);
  });

  it("returns only the three fields the screen needs", async () => {
    GET.mockResolvedValue({ data: state(), response: new Response(null) });

    const read = await readDigestPreference();

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    // **The city is not returned.** The endpoint cannot clear a city, so a client that
    // found one here and sent it back would be relying on a field the screen does not
    // own. The assertion is that the shape has exactly three keys.
    expect(Object.keys(read.preference).sort()).toEqual([
      "delivery_time",
      "include_personal_events",
      "timezone",
    ]);
  });

  it("keeps a null delivery time and timezone null", async () => {
    // **A user who has not finished onboarding has no schedule yet.** That is a real
    // state, and it must survive the read unchanged — normalising it here would change
    // the user's delivery time the next time the screen saved the opt-out.
    GET.mockResolvedValue({
      data: state({
        digest: {
          city: null,
          city_source: null,
          delivery_time: null,
          timezone: null,
          include_personal_events: true,
        },
      }),
      response: new Response(null),
    });

    const read = await readDigestPreference();

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    expect(read.preference.delivery_time).toBeNull();
    expect(read.preference.timezone).toBeNull();
  });

  it("reads an absent delivery time and timezone as null, not undefined", async () => {
    // **The schema permits the key to be missing, not just null.** `delivery_time` and
    // `timezone` are `delivery_time?: string | null` — an *optional* key, so the API may
    // omit them entirely. The read's declared type is `string | null`, and `undefined` is
    // not in it, so an absent key must become `null`.
    //
    // **Why this matters, concretely.** A caller that changes the opt-out has to send
    // the schedule back unchanged, because the endpoint refuses to half-apply the pair.
    // An `undefined` in that body is a different thing from a `null` — one is "no value
    // in this field", the other is "the field is absent" — and the two are not
    // interchangeable to a serializer. A screen that read `undefined` and sent it back
    // would be sending a body the endpoint treats differently from one carrying `null`.
    GET.mockResolvedValue({
      data: {
        completed: true,
        current_step: null,
        step_name: null,
        interests: [],
        last_advanced_at: null,
        completed_at: null,
        // **The digest block with no delivery_time and no timezone keys at all.**
        digest: {
          city: null,
          city_source: null,
          include_personal_events: true,
        },
      },
      response: new Response(null),
    });

    const read = await readDigestPreference();

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    expect(read.preference.delivery_time).toBeNull();
    expect(read.preference.timezone).toBeNull();
    // **Explicitly not `undefined`.** `toBeNull` alone would not catch a value that was
    // `undefined`, and `toBeUndefined` alone would not catch one that was `null` — the
    // pair is the claim.
    expect(read.preference.delivery_time).not.toBeUndefined();
    expect(read.preference.timezone).not.toBeUndefined();
  });

  it("answers 'unavailable' when there is no API to ask", async () => {
    apiBaseUrl.mockReturnValue(null);

    expect(await readDigestPreference()).toEqual({ kind: "unavailable" });
    expect(GET).not.toHaveBeenCalled();
  });

  it("answers 'unavailable' when the request fails", async () => {
    GET.mockRejectedValue(new Error("connection refused"));

    expect(await readDigestPreference()).toEqual({ kind: "unavailable" });
  });

  it("answers 'unavailable' when the API answers with an error", async () => {
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_authenticated", message: "Please sign in to continue." },
      response: new Response(null, { status: 401 }),
    });

    expect(await readDigestPreference()).toEqual({ kind: "unavailable" });
  });

  it("answers 'unavailable' when a 200 carries no payload", async () => {
    GET.mockResolvedValue({ data: undefined, response: new Response(null, { status: 200 }) });

    expect(await readDigestPreference()).toEqual({ kind: "unavailable" });
  });

  it("never answers 'unavailable' as if the user had opted out", async () => {
    // **The whole point of the two answers.** A failed read must not be
    // indistinguishable from "the opt-out is off" — that would show a user a setting
    // they never changed, and the next save would write that fiction to the server.
    GET.mockRejectedValue(new Error("connection refused"));

    const read = await readDigestPreference();

    expect(read.kind).not.toBe("found");
    expect(read).not.toHaveProperty("preference");
  });
});
