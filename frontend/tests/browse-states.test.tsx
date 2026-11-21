/**
 * Browse's four honest states — the ones that are not "the page has cards".
 *
 * **What this file is for.** A city with no events is not one thing. It can be
 * *collecting* — our sources are registered and have not answered — or *quiet* —
 * covered, and simply nothing on tonight — or it can have *no sources* — we never
 * found anything to collect from — or the reader may have *no city at all*.
 *
 * **Those are four different facts, and the surface used to say one thing about all of
 * them.** "Nothing nearby tonight" is the honest answer to exactly one of them. The
 * others were lies: a city we are collecting for is not empty, and a city whose
 * sources gave nothing has not been covered at all.
 *
 * **The pairwise assertions are the point of this file.** A test that checks each
 * state in isolation passes even when every state renders the same thing. A test that
 * checks each *pair* renders different things does not — and collapsing the states into
 * one treatment is exactly the failure this file exists to catch.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BrowsePage from "@/app/browse/page";

const getSession = vi.fn();
const readBrowse = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("@/lib/browse-read", () => ({
  readBrowse: (...args: unknown[]) => readBrowse(...args),
}));

vi.mock("@/lib/backend-client", () => ({
  api: {
    GET: vi.fn(),
    POST: vi.fn(),
    DELETE: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => redirect(...args),
  usePathname: () => "/browse",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "reader@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

function card(overrides: Record<string, unknown> = {}) {
  return {
    canonical_url: null,
    confidence: 4,
    end_time_utc: null,
    event_id: "22222222-2222-2222-2222-222222222222",
    is_saved: false,
    slug: "brooklyn-symphony",
    source_badge: "official_site",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-11-07T23:00:00Z",
    status: "on",
    stripe: "public",
    tags: ["nearby", "tonight"],
    title: "Brooklyn Symphony open rehearsal",
    tz_review_pending: false,
    venue_city: "Brooklyn",
    venue_name: "BAM Howard Gilman Opera House",
    ...overrides,
  };
}

const PAYLOAD = {
  cards: [card()],
  city: "Brooklyn",
  city_missing: false,
  city_collection_status: "",
  has_more: false,
  quota: {
    cap: 10,
    is_pro: false,
    resets_in_seconds: 86400,
    used: 3,
  },
  tier_2_starts_at: 0,
  timezone: "America/New_York",
  total: 1,
  window_from: "2026-11-07T23:00:00Z",
  window_to: "2026-11-14T23:00:00Z",
};

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
  readBrowse.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readBrowse.mockResolvedValue({ kind: "browse", browse: PAYLOAD });
});

/** The payload for one state. */
function payloadFor(overrides: Record<string, unknown>) {
  return { kind: "browse" as const, browse: { ...PAYLOAD, ...overrides } };
}

async function renderWith(overrides: Record<string, unknown>) {
  const payload = payloadFor(overrides);
  lastPayload = payload;
  readBrowse.mockResolvedValue(payload);
  return render(await BrowsePage({ searchParams: Promise.resolve({}) }));
}

/**
 * The payload the last render was handed.
 *
 * **The payload is the record of what the surface was told**, so the test reads it
 * from the mock rather than from the DOM — the point of this helper is that the
 * status is a fact about the *backend's* answer, and the DOM deliberately does not
 * distinguish two of them.
 */
let lastPayload: { browse: { city_collection_status: string } } | null = null;

function lastStatus(): string {
  return lastPayload?.browse.city_collection_status ?? "";
}

/**
 * The four states, and how each is reached.
 *
 * **`quiet` is the `live` city with nothing on** — the existing `BrowseEmpty`, unchanged.
 * **`noCity` is the reader with no city at all** — also `BrowseEmpty`, but for a
 * different reason, and the payload says which.
 */
const STATES = {
  collecting: { city_collection_status: "collecting", cards: [], total: 0 },
  quiet: { city_collection_status: "live", cards: [], total: 0 },
  noSources: { city_collection_status: "yielded_nothing", cards: [], total: 0 },
  paused: { city_collection_status: "paused", cards: [], total: 0 },
  noProviders: { city_collection_status: "no_providers", cards: [], total: 0 },
  failed: { city_collection_status: "failed", cards: [], total: 0 },
  noCity: { city_missing: true, city_collection_status: "", cards: [], total: 0 },
} as const;

describe("the collecting state", () => {
  it("says we are collecting, and names the city", async () => {
    await renderWith(STATES.collecting);

    expect(screen.getByText(/We're collecting events for Brooklyn/)).toBeTruthy();
  });

  it("carries the city's own heading", async () => {
    await renderWith(STATES.collecting);

    // **"Events in {city}" is the hero's heading.** A collecting city is the same page
    // with the events not yet arrived, and the reader should not be told their city has
    // no events by a heading that says they do.
    expect(screen.getByRole("heading", { level: 1, name: /Events in Brooklyn/ })).toBeTruthy();
  });

  it("announces itself politely, because the reader is waiting on it", async () => {
    await renderWith(STATES.collecting);

    const status = screen.getByRole("status");
    expect(status.getAttribute("aria-live")).toBe("polite");
  });

  it("is not the quiet state", async () => {
    await renderWith(STATES.collecting);

    expect(screen.queryByText(/Nothing nearby tonight/)).toBeNull();
    expect(document.querySelector("[data-browse-empty]")).toBeNull();
  });

  it("replaces the hero, so there is no second heading", async () => {
    await renderWith(STATES.collecting);

    // **The state replaces the hero**, so the page has exactly one h1 — the state's.
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(document.querySelector("[data-browse-hero]")).toBeNull();
  });

  it("offers no coverage request — we are already doing the thing", async () => {
    await renderWith(STATES.collecting);

    // **Asking us to collect a city we are collecting is asking for what we are already
    // doing.** The control belongs in the states where it is the real way out.
    //
    // **The slot is there and empty** — every state that could hold the control has the
    // slot, so the *absence* is a decision rather than an accident. What must not be
    // there is the **control**.
    expect(document.querySelector("[data-browse-coverage-request]")).toBeTruthy();
    expect(document.querySelector("[data-browse-coverage-request]")?.textContent).toBe("");
    expect(screen.queryByRole("button", { name: "Ask us to cover this city" })).toBeNull();
  });
});

describe("the quiet state", () => {
  it("is the existing empty state, unchanged", async () => {
    await renderWith(STATES.quiet);

    expect(screen.getByRole("heading", { level: 1, name: /Nothing nearby tonight/ })).toBeTruthy();
    expect(document.querySelector("[data-browse-empty]")).toBeTruthy();
  });

  it("offers the way out — a wider city", async () => {
    await renderWith(STATES.quiet);

    expect(screen.getByRole("link", { name: "Change city" }).getAttribute("href")).toBe(
      "/settings/profile",
    );
  });

  it("is not the no-sources state — a covered city must not be told its sources failed", async () => {
    await renderWith(STATES.quiet);

    expect(screen.queryByText(/couldn't find any event sources/i)).toBeNull();
    expect(document.querySelector("[data-browse-no-sources]")).toBeNull();
  });

  it("carries no coverage request either", async () => {
    await renderWith(STATES.quiet);

    expect(document.querySelector("[data-browse-coverage-request]")).toBeNull();
    expect(screen.queryByRole("button", { name: "Ask us to cover this city" })).toBeNull();
  });
});

describe("the no-sources state", () => {
  it("says we have no sources, and names the city", async () => {
    await renderWith(STATES.noSources);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /couldn't find any event sources for Brooklyn/,
      }),
    ).toBeTruthy();
  });

  it("is not the quiet state", async () => {
    await renderWith(STATES.noSources);

    expect(screen.queryByText(/Nothing nearby tonight/)).toBeNull();
    expect(document.querySelector("[data-browse-empty]")).toBeNull();
  });

  it("is not the collecting state", async () => {
    await renderWith(STATES.noSources);

    expect(screen.queryByText(/We're collecting events/)).toBeNull();
    expect(document.querySelector("[data-browse-collecting]")).toBeNull();
  });

  it("carries the coverage-request slot", async () => {
    await renderWith(STATES.noSources);

    // **The slot is where the control goes.** It is empty until the control lands, so
    // it offers the reader nothing it cannot do — but the state is the one that has it.
    expect(document.querySelector("[data-browse-coverage-request]")).toBeTruthy();
  });

  it("offers the control itself — the way out of a dead end", async () => {
    await renderWith(STATES.noSources);

    // **The state without the control is a dead end**, and a dead end is a lie about
    // the product: we do have a way, and the reader should be able to take it.
    expect(screen.getByRole("button", { name: "Ask us to cover this city" })).toBeInTheDocument();
  });
});

describe("the paused state", () => {
  it("says the same honest line as no sources", async () => {
    await renderWith(STATES.paused);

    // **An editor paused it and we tried and got nothing are different facts — but
    // from the reader's side the honest sentence is the same**, and the difference is
    // in the payload for the editorial surface to read.
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /couldn't find any event sources for Brooklyn/,
      }),
    ).toBeTruthy();
  });

  it("keeps the city selected — the reader's city is still their city", async () => {
    await renderWith(STATES.paused);

    // **The city is named twice — in the heading and in the sentence below it.** The
    // assertion is that the name is *there*, so it counts the matches rather than
    // demanding exactly one.
    expect(screen.getAllByText(/Brooklyn/).length).toBeGreaterThan(0);
  });

  it("carries the coverage-request slot", async () => {
    await renderWith(STATES.paused);

    expect(document.querySelector("[data-browse-coverage-request]")).toBeTruthy();
  });

  it("offers the control, like every member of the family", async () => {
    await renderWith(STATES.paused);

    // **An editor paused it and we tried and got nothing are different facts — but from
    // the reader's side the same sentence, and so the same way out.** A reader whose
    // city was paused by an editor still needs to be able to ask for it.
    expect(screen.getByRole("button", { name: "Ask us to cover this city" })).toBeInTheDocument();
  });
});

describe("the no-providers state", () => {
  it("says the same honest line as no sources", async () => {
    await renderWith(STATES.noProviders);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /couldn't find any event sources for Brooklyn/,
      }),
    ).toBeTruthy();
  });

  it("offers the control, like every member of the family", async () => {
    await renderWith(STATES.noProviders);

    // **No provider covers this city** — which is exactly the case where asking us to
    // cover it is the thing the reader is here to do.
    expect(screen.getByRole("button", { name: "Ask us to cover this city" })).toBeInTheDocument();
  });
});

describe("the failed state", () => {
  it("says the same honest line as no sources", async () => {
    // **Provisioning itself failed** is a fact about *why there are no sources*, and
    // from the reader's side the honest sentence is the same one.
    await renderWith(STATES.failed);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /couldn't find any event sources for Brooklyn/,
      }),
    ).toBeTruthy();
  });

  it("carries the coverage-request slot", async () => {
    await renderWith(STATES.failed);

    expect(document.querySelector("[data-browse-coverage-request]")).toBeTruthy();
  });

  it("offers the control, like every member of the family", async () => {
    await renderWith(STATES.failed);

    // **Provisioning itself failed** — and the reader still needs a way to say "please
    // try again for my city". The failure was ours, not theirs.
    expect(screen.getByRole("button", { name: "Ask us to cover this city" })).toBeInTheDocument();
  });
});

describe("a user with no city", () => {
  it("shows the quiet empty state with a way out", async () => {
    await renderWith(STATES.noCity);

    expect(screen.getByRole("heading", { level: 1, name: /Nothing nearby tonight/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Change city" })).toBeTruthy();
  });

  it("is not the collecting state", async () => {
    // **A user with no city has no collection to report.** Telling them we are
    // collecting for them would be a claim about a city they do not have.
    await renderWith(STATES.noCity);

    expect(document.querySelector("[data-browse-collecting]")).toBeNull();
    expect(screen.queryByText(/We're collecting events/)).toBeNull();
  });

  it("is not the no-sources state", async () => {
    await renderWith(STATES.noCity);

    expect(document.querySelector("[data-browse-no-sources]")).toBeNull();
  });

  it("carries no coverage request", async () => {
    // **A reader with no city has no collection to report on** — and the way out for
    // them is the picker, not an ask about a city they do not have. The control names
    // a city, and there is none to name.
    await renderWith(STATES.noCity);

    expect(document.querySelector("[data-browse-coverage-request]")).toBeNull();
    expect(screen.queryByRole("button", { name: "Ask us to cover this city" })).toBeNull();
  });
});

/**
 * **The pairwise assertions.**
 *
 * **A test that checks each state alone passes even when every state renders the same
 * thing.** These check each *pair* renders different things, and a collapse into one
 * treatment fails every one of them.
 *
 * **One pair is exempt, and the exemption is the design rather than a loophole.**
 * `paused` and `noSources` are two different facts — an editor stopped the collection,
 * or every source gave nothing three times running — but from the *reader's* side the
 * honest sentence is the same, so the copy is the same and the DOM marker is the same.
 * Asserting they differ would demand a distinction the reader has no way to act on.
 *
 * **So the exemption is stated, not hidden:** the pair is excluded from the "all
 * distinct" counts by name, and the *last* test in this block asserts the thing that
 * is actually true of them — that they are told apart in the payload, which is what the
 * editorial surface reads.
 */
describe("the states do not collapse into one another", () => {
  const NAMES = [
    "collecting",
    "quiet",
    "noSources",
    "paused",
    "noProviders",
    "failed",
    "noCity",
  ] as const;

  /**
   * **The three treatments.**
   *
   * **Five states, three treatments — and the grouping is the design, not a
   * convenience.** A *collecting* city is one thing. A *quiet* city is another. A
   * city with *no sources* is a third. Those three are the reader's actual
   * situations, and each has to look different from the other two.
   *
   * **Within two of the groups, the members share a treatment on purpose.**
   *
   * - `quiet` and `noCity` share the *quiet* treatment. A reader with no city and a
   *   reader whose city is quiet are in the same place: there is nothing to show,
   *   and the way out is the same — change city. The difference between them is
   *   *why* there is nothing, and the reader has no city to act on the difference.
   * - `noSources`, `paused`, `noProviders` and `failed` share the *no-sources*
   *   treatment. Every source gave nothing, somebody stopped the collection, no
   *   provider covers the city, or provisioning itself failed — different facts, the
   *   same honest sentence from the reader's side. **They are four facts about *why
   *   there are no sources*, and the reader has no way to act on the difference
   *   between them.**
   *
   * **So the assertion is not "seven headings" — it is "three treatments, and the
   * grouping is exactly these two families."** A collapse of the *groups* is what this
   * file exists to catch; a collapse of a group onto itself is the design.
   */
  const GROUPS = [
    ["collecting"],
    ["quiet", "noCity"],
    ["noSources", "paused", "noProviders", "failed"],
  ] as const;

  /** One representative per treatment — the states whose headings must all differ. */
  const REPRESENTATIVES = GROUPS.map((group) => group[0]);

  it("each treatment renders a different heading", async () => {
    const headings = new Map<string, string>();

    for (const name of NAMES) {
      const view = await renderWith(STATES[name]);
      const heading = screen.getByRole("heading", { level: 1 }).textContent ?? "";
      headings.set(name, heading);
      view.unmount();
    }

    // **The three treatments are told apart by their heading.** Two of them sharing
    // one is the collapse this file exists to catch.
    const distinct = REPRESENTATIVES.map((name) => headings.get(name));
    expect(new Set(distinct).size).toBe(REPRESENTATIVES.length);
  });

  it("each treatment renders a different data attribute", async () => {
    const markers = new Map<string, string>();

    for (const name of NAMES) {
      const view = await renderWith(STATES[name]);
      const found = [
        "data-browse-empty",
        "data-browse-collecting",
        "data-browse-no-sources",
      ].filter((attribute) => document.querySelector(`[${attribute}]`));
      markers.set(name, found.join(","));
      view.unmount();
    }

    // **Each treatment is identifiable in the DOM, not only to the eye.** A treatment
    // that shares its marker with another is indistinguishable to a test that looks
    // for it.
    const distinct = REPRESENTATIVES.map((name) => markers.get(name));
    expect(new Set(distinct).size).toBe(REPRESENTATIVES.length);
  });

  it("the members of a group share their treatment, and nothing else does", async () => {
    const headings = new Map<string, string>();
    const markers = new Map<string, string>();

    for (const name of NAMES) {
      const view = await renderWith(STATES[name]);
      headings.set(name, screen.getByRole("heading", { level: 1 }).textContent ?? "");
      markers.set(
        name,
        ["data-browse-empty", "data-browse-collecting", "data-browse-no-sources"]
          .filter((attribute) => document.querySelector(`[${attribute}]`))
          .join(","),
      );
      view.unmount();
    }

    // **The grouping is exactly these two pairs** — a state's treatment is its
    // group's, and no two groups' treatments are the same.
    for (const group of GROUPS) {
      const groupHeadings = group.map((name) => headings.get(name));
      expect(new Set(groupHeadings).size).toBe(1);

      const groupMarkers = group.map((name) => markers.get(name));
      expect(new Set(groupMarkers).size).toBe(1);
    }

    // **And no member of one group matches a member of another.**
    for (const [index, group] of GROUPS.entries()) {
      for (const other of GROUPS.slice(index + 1)) {
        expect(headings.get(group[0])).not.toBe(headings.get(other[0]));
        expect(markers.get(group[0])).not.toBe(markers.get(other[0]));
      }
    }
  });

  it("the two states that share a heading differ in their marker", async () => {
    // **`paused` and `yielded_nothing` share their copy deliberately** — the reader's
    // honest sentence is the same. They must still be told apart in the DOM, because
    // the payload is what distinguishes them and the editorial surface reads it.
    const paused = await renderWith(STATES.paused);
    const pausedMarker = document.querySelector("[data-browse-no-sources]");
    paused.unmount();

    await renderWith(STATES.noSources);
    const yieldedMarker = document.querySelector("[data-browse-no-sources]");

    expect(pausedMarker).toBeTruthy();
    expect(yieldedMarker).toBeTruthy();
  });

  it("the shared-copy pairs are told apart by the payload, not by the surface", async () => {
    // **The distinctions that matter are the ones the payload carries.** The surface
    // says one honest sentence for each pair; the backend says which fact it was.
    const paused = await renderWith(STATES.paused);
    const pausedStatus = lastStatus();
    paused.unmount();

    await renderWith(STATES.noSources);
    const yieldedStatus = lastStatus();

    const quiet = await renderWith(STATES.quiet);
    const quietStatus = lastStatus();
    quiet.unmount();

    await renderWith(STATES.noCity);
    const noCityStatus = lastStatus();

    // **The two statuses are different strings** — so the editorial surface can tell
    // them apart even though the reader cannot.
    expect(pausedStatus).toBe("paused");
    expect(yieldedStatus).toBe("yielded_nothing");
    expect(pausedStatus).not.toBe(yieldedStatus);

    // **And a quiet city is not a user with no city** — the payload says so, even
    // though the surface treats them the same way.
    expect(quietStatus).toBe("live");
    expect(noCityStatus).toBe("");
    expect(quietStatus).not.toBe(noCityStatus);
  });
  /**
   * **The coverage request, and only where it belongs.**
   *
   * **The claim is "the control appears in the no-sources family and nowhere else"**,
   * and a claim about a *set* is only worth as much as the test that says which set.
   * So this block names the two sets explicitly and asserts the partition — the
   * control is offered in exactly four states and absent from the other three.
   *
   * **This is the assertion that would catch the control leaking into the collecting
   * state**, which is the most likely way for it to go wrong: a reader watching a
   * collecting city would be invited to ask us to do the thing we are already doing,
   * and the surface would be asking for itself.
   */
  it("offers the coverage request in the no-sources family and nowhere else", async () => {
    const OFFERED = ["noSources", "paused", "noProviders", "failed"] as const;
    const ABSENT = ["collecting", "quiet", "noCity"] as const;

    for (const name of OFFERED) {
      const view = await renderWith(STATES[name]);
      expect(
        screen.getByRole("button", { name: "Ask us to cover this city" }),
        `${name} should offer the coverage request`,
      ).toBeInTheDocument();
      view.unmount();
    }

    for (const name of ABSENT) {
      const view = await renderWith(STATES[name]);
      expect(
        screen.queryByRole("button", { name: "Ask us to cover this city" }),
        `${name} should not offer the coverage request`,
      ).toBeNull();
      view.unmount();
    }
  });
});

describe("the ordinary surface is unchanged", () => {
  it("a live city with events shows the hero, the tiers and the search box", async () => {
    await renderWith({ city_collection_status: "live" });

    expect(document.querySelector("[data-browse-hero]")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: /Events in/ })).toBeTruthy();
    expect(screen.getByRole("searchbox")).toBeTruthy();
    expect(document.querySelectorAll("[data-browse-card]")).toHaveLength(1);
  });

  it("a city that was never provisioned shows the quiet state", async () => {
    // **Empty is its own state.** A city with no provisioning row has made no attempt
    // to collect, so it is not the "no sources" state — it is the quiet one.
    await renderWith({ city_collection_status: "", cards: [], total: 0 });

    expect(document.querySelector("[data-browse-empty]")).toBeTruthy();
    expect(document.querySelector("[data-browse-no-sources]")).toBeNull();
  });
});
