import { describe, expect, it } from "vitest";

import { isDetailEvent, isEventUuid, isMintedSlug } from "@/lib/event-identifier";

/**
 * The route's discriminator — the rule that decides whether `/events/{id}` is the
 * signed-in Detail Screen or the public event page.
 *
 * **This file exists because the rule is load-bearing and shared.** The route asks the
 * question in two places (the page and the metadata), and a regex written at a call site
 * would be two copies of a rule that decides *which of two surfaces a stranger sees*.
 * So the rule lives once, here, and is tested once, here.
 *
 * **The direction of the mistake matters.** A parameter that is wrongly taken for a UUID
 * reaches the signed-in Detail Screen, which reads the personal endpoint with the
 * visitor's cookies. A parameter that is wrongly taken for a slug reaches the public
 * endpoint, which has no session at all and 404s anything that is not a public event.
 * So the failures are asymmetric: the first is a privacy question and the second is a
 * wrong status code. **Every near-miss below is checked for the safe direction.**
 */

/**
 * A real UUIDv7 from this system's minting.
 *
 * **The shape is the backend's**: 48-bit millisecond timestamp, 12-bit counter, 62
 * random bits, RFC 9562 §6.2 (`backend/shared/ids.py`). The version nibble is `7` and
 * the variant nibble is one of `8`/`9`/`a`/`b`.
 */
const UUID_V7 = "0196c3a4-5b6d-7e8f-9a0b-1c2d3e4f5061";
const UUID_V7_UPPER = "0196C3A4-5B6D-7E8F-9A0B-1C2D3E4F5061";

describe("isEventUuid", () => {
  it("accepts a UUIDv7", () => {
    expect(isEventUuid(UUID_V7)).toBe(true);
  });

  it("accepts a UUIDv7 in upper case", () => {
    // The canonical form is lower case, but a UUID's hex digits are case-insensitive
    // and the backend's parser accepts either. A parameter typed in upper case is
    // still the id it was.
    expect(isEventUuid(UUID_V7_UPPER)).toBe(true);
  });

  it("rejects a UUIDv4", () => {
    // **The version nibble is the reason this check exists.** A v4 uuid is a perfectly
    // good uuid and it is *not* one of this system's event ids — the backend mints v7
    // and only v7. A v4 must take the public branch, where the read 404s it, rather
    // than the detail branch, where it would read as "an event that is not public" —
    // a different fact, and a misleading one.
    expect(isEventUuid("3f2504e0-4f89-41d3-9a0c-0305e82c3301")).toBe(false);
  });

  it("rejects a UUIDv1", () => {
    expect(isEventUuid("6ba7b810-9dad-11d1-80b4-00c04fd430c8")).toBe(false);
  });

  it("rejects a uuid whose variant nibble is wrong", () => {
    // The version nibble says 7 and the form is canonical, but the variant nibble is
    // `c` — not one of `8`/`9`/`a`/`b`. RFC 9562 §6.10 fixes the variant at `10`, so
    // this is not a uuid this system minted, whatever its version claims.
    expect(isEventUuid("0196c3a4-5b6d-7e8f-ca0b-1c2d3e4f5061")).toBe(false);
  });

  it("rejects a truncated uuid", () => {
    expect(isEventUuid("0196c3a4-5b6d-7e8f-9a0b-1c2d3e4f506")).toBe(false);
  });

  it("rejects a uuid with no hyphens", () => {
    // The canonical form has them. The backend renders ids with `str(uuid.UUID)`, so
    // the id in a URL always does.
    expect(isEventUuid("0196c3a45b6d7e8f9a0b1c2d3e4f5061")).toBe(false);
  });

  it("rejects a slug", () => {
    expect(isEventUuid("designing-for-calm-2026-08-28-a1b2c3")).toBe(false);
  });

  it("rejects an empty string", () => {
    expect(isEventUuid("")).toBe(false);
  });

  it("rejects a non-uuid string that happens to be the right length", () => {
    expect(isEventUuid("zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz")).toBe(false);
  });

  it("rejects a minted slug", () => {
    // The minted form is `<title-slug>-<local-date>-<hex-tail>`
    // (`apps/ingestion/services/slugs.py`) — and it is *hyphen-separated lowercase hex*,
    // which is exactly the shape of a uuid. The version nibble is what tells them
    // apart, and this is the case where getting it wrong would send a slug to the
    // signed-in Detail Screen.
    expect(isEventUuid("designing-for-calm-2026-08-28-a1b2c3")).toBe(false);
  });
});

/**
 * The minted slug's own shape — `<title-slug>-<YYYY-MM-DD>-<hex-tail>`.
 *
 * **This is the format the backend mints** (`apps/ingestion/services/slugs.py`):
 *
 * ```
 * mint_slug(title, start_time_local, event_id) →
 *     f"{slugify(title)[:80]}-{start_time_local[:10]}-{event_id.hex[-6:]}"
 * ```
 *
 * **The date is what makes a slug distinguishable from a UUID.** Both are lower-case
 * hyphen-separated hex, so a bare "is it hex-and-hyphens" test cannot tell them apart.
 * But a slug's third group is exactly **two digits** (the month) and its fourth is
 * exactly **two digits** (the day), while a UUID's groups are 8-4-4-4-12. The two
 * shapes cannot both match.
 */
describe("isMintedSlug", () => {
  it("accepts a minted slug", () => {
    expect(isMintedSlug("designing-for-calm-2026-08-28-a1b2c3")).toBe(true);
  });

  it("accepts a slug whose short tail was retried to the long tail", () => {
    // The mint retries with the last 12 hex characters when the 6-character tail
    // collides, so a valid minted slug may end in twelve hex digits rather than six.
    expect(isMintedSlug("designing-for-calm-2026-08-28-a1b2c3d4e5f6")).toBe(true);
  });

  it("accepts a slug whose title is only alphanumerics", () => {
    // `slugify` produces a title part with no hyphens of its own when the title has
    // one word — the date and tail still separate it.
    expect(isMintedSlug("concert-2026-08-28-a1b2c3")).toBe(true);
  });

  it("accepts a slug whose title part carries an underscore", () => {
    // **Django's `slugify` keeps an underscore.** It removes everything that is not
    // alphanumeric, a hyphen or an underscore — so `"AI_ML Night"` mints
    // `ai_ml-night-2026-08-28-a1b2c3`.
    //
    // **Why this test exists.** A pattern that accepted only `[a-z0-9]` would call that
    // slug a *detail* parameter, and `isDetailEvent` would route it to the signed-in
    // Detail Screen — a public event's page would be served as somebody's personal
    // surface. That is the exact failure this rule exists to prevent, and it would
    // have been silent: the shared URL would work for anyone who opened it directly.
    expect(isMintedSlug("ai_ml-night-2026-08-28-a1b2c3")).toBe(true);
  });

  it("accepts a slug whose title is only an underscore and digits", () => {
    // `slugify("_404_")` keeps the underscores, so the title part can be almost
    // nothing but them.
    expect(isMintedSlug("_404_-2026-08-28-a1b2c3")).toBe(true);
  });

  it("rejects a UUIDv7", () => {
    // **The two shapes are disjoint.** A uuid's third group is four characters, not
    // the slug's two-digit month.
    expect(isMintedSlug(UUID_V7)).toBe(false);
  });

  it("rejects a UUIDv7 in upper case", () => {
    // A minted slug is lower case by construction; an upper-case uuid is not one.
    expect(isMintedSlug(UUID_V7_UPPER)).toBe(false);
  });

  it("rejects a slug with a one-digit month", () => {
    expect(isMintedSlug("designing-for-calm-2026-8-28-a1b2c3")).toBe(false);
  });

  it("rejects a slug with a five-digit tail", () => {
    expect(isMintedSlug("designing-for-calm-2026-08-28-a1b2c")).toBe(false);
  });

  it("rejects a slug with a seven-digit tail", () => {
    // The tail is six hex characters, or twelve on a retry — never seven.
    expect(isMintedSlug("designing-for-calm-2026-08-28-a1b2c3d")).toBe(false);
  });

  it("rejects a slug with a non-hex tail", () => {
    expect(isMintedSlug("designing-for-calm-2026-08-28-zzzzzz")).toBe(false);
  });

  it("rejects a slug with an upper-case title", () => {
    // `slugify` lower-cases, so an upper-case title is not a minted slug.
    expect(isMintedSlug("Designing-for-Calm-2026-08-28-a1b2c3")).toBe(false);
  });

  it("rejects a bare id-like string", () => {
    expect(isMintedSlug("event-1")).toBe(false);
  });

  it("rejects an empty string", () => {
    expect(isMintedSlug("")).toBe(false);
  });
});

/**
 * The branch's actual predicate: which of the two surfaces a parameter names.
 *
 * **The rule is "a minted slug is the public page; everything else is the detail
 * screen"** — and the direction matters, because the two surfaces differ in kind.
 *
 * A parameter that is wrongly taken for a slug reaches the public endpoint, which has
 * no session at all and 404s anything that is not a public event. A parameter that is
 * wrongly taken for an id reaches the personal endpoint — whose parameter the backend
 * types as `UUID`, so a parameter that is not a uuid is refused with a **422** rather
 * than rendering somebody's personal page. **The safe direction is the detail
 * branch's**, and that is where everything that is not a minted slug goes.
 */
describe("isDetailEvent", () => {
  it("sends a minted slug to the public page", () => {
    expect(isDetailEvent("designing-for-calm-2026-08-28-a1b2c3")).toBe(false);
  });

  it("sends a slug with an underscore in its title to the public page", () => {
    // **The consequence of the underscore rule**, and the reason it is load-bearing:
    // an underscored slug is a *public* event's address, so it must reach the public
    // page and not the signed-in Detail Screen.
    expect(isDetailEvent("ai_ml-night-2026-08-28-a1b2c3")).toBe(false);
  });

  it("sends a UUIDv7 to the detail screen", () => {
    expect(isDetailEvent(UUID_V7)).toBe(true);
  });

  it("sends an id-shaped token that is not a minted slug to the detail screen", () => {
    // **The "everything else" half of the rule.** This is what keeps the existing
    // detail-route tests meaningful: an id the route has always rendered stays on
    // the detail screen.
    expect(isDetailEvent("event-1")).toBe(true);
  });

  it("sends a UUIDv4 to the detail screen", () => {
    // A v4 uuid is not one of this system's minted ids, but it is not a slug
    // either — and the detail endpoint accepts any uuid.
    expect(isDetailEvent("3f2504e0-4f89-41d3-9a0c-0305e82c3301")).toBe(true);
  });

  it("sends an empty string to the detail screen", () => {
    expect(isDetailEvent("")).toBe(true);
  });

  it("never sends both a slug and a uuid to the same surface", () => {
    // **The shapes are disjoint**, so the two tests can never disagree about one
    // parameter — which is the property that makes a shared rule possible at all.
    for (const value of [
      UUID_V7,
      UUID_V7_UPPER,
      "event-1",
      "",
      "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
    ]) {
      expect(isEventUuid(value) && isMintedSlug(value)).toBe(false);
    }
    for (const value of [
      "designing-for-calm-2026-08-28-a1b2c3",
      "designing-for-calm-2026-08-28-a1b2c3d4e5f6",
    ]) {
      expect(isEventUuid(value) && isMintedSlug(value)).toBe(false);
    }
  });
});
