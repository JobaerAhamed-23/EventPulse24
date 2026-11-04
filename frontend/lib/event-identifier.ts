/**
 * Which of the two surfaces a `/events/{id}` parameter names.
 *
 * **One route, two pages.** `app/events/[id]/page.tsx` serves the signed-in Detail Screen
 * *and* the public event page. Next.js allows exactly one `page.tsx` per URL, and two
 * different dynamic names at one level (`[id]` and `[slug]`) is a build error — so the
 * route **branches on its parameter** instead of having two routes.
 *
 * **The discriminator is shared, not inline.** A regex written at the call site is a rule
 * that exists in two places the moment a second caller needs it, and the two copies
 * would eventually disagree about which surface a stranger is looking at. So the rule
 * lives here, once, and is tested here.
 */

/**
 * The canonical UUID form: 32 hex digits in 8-4-4-4-12 groups.
 *
 * **The hyphens are part of the canonical form, not decoration.** The backend renders
 * ids with `str(uuid.UUID)`, so the id in a URL always has them. A uuid without hyphens
 * is the same value written differently, and the backend's `UUID` parser accepts it —
 * but it is not what this system's links contain, and the branch does not need to guess.
 */
const CANONICAL_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The version nibble: the first character of the third group.
 *
 * **Version 7 is the only version this system mints** (`shared.ids.uuid7`). The version
 * nibble is a *feature*, not decoration: a UUIDv4 id is a different kind of thing, and
 * the branch has to be able to say so.
 */
const VERSION_7 = "7";

/**
 * The variant nibble: the first character of the fourth group.
 *
 * **RFC 9562 §6.10 fixes the variant at `10`** in binary — the two high bits — so the
 * nibble is one of `8`, `9`, `a`, `b`. A uuid whose variant is anything else is not a
 * uuid this system minted, whatever its version nibble claims.
 */
const VARIANT_NIBBLES = new Set(["8", "9", "a", "b"]);

/**
 * The minted slug's shape: `<title-slug>-<YYYY-MM-DD>-<hex-tail>`.
 *
 * **This is the backend's own format, read off `apps/ingestion/services/slugs.py`:**
 *
 * ```
 * mint_slug(title, start_time_local, event_id) →
 *     f"{slugify(title)[:80]}-{start_time_local[:10]}-{event_id.hex[-6:]}"
 * ```
 *
 * The title part is a `django.utils.text.slugify` result — lower case, hyphen-separated
 * alphanumerics, at most 80 characters. The middle part is the event's local date,
 * `YYYY-MM-DD`. The tail is the last 6 hex characters of the event's UUIDv7 — or 12 when
 * the short tail collided and the mint was retried.
 *
 * **The date is what makes a slug distinguishable from a UUID.** Both are lower-case
 * hyphen-separated hex, so a bare "is it hex-and-hyphens" test cannot tell them apart.
 * But a slug's third group is exactly **two digits** (the month) and its fourth is
 * exactly **two digits** (the day), while a UUID's groups are 8-4-4-4-12. The two
 * shapes cannot both match.
 *
 * **The title part may carry an underscore, and it must.** Django's `slugify` keeps
 * `_` — it removes everything that is not alphanumeric, a hyphen or an underscore — so
 * a title like `"AI_ML Night"` mints `ai_ml-night-2026-11-05-a1b2c3`. A pattern that
 * accepted only `[a-z0-9]` would call that a *detail* parameter, and the route would
 * send it to the signed-in Detail Screen instead of the public page. **That is the
 * exact failure this rule exists to prevent**, so the underscore is in the pattern
 * because the backend's `slugify` puts it there.
 */
const MINTED_SLUG = /^[a-z0-9_]+(?:-[a-z0-9_]+)*-\d{4}-\d{2}-\d{2}-[0-9a-f]{6}([0-9a-f]{6})?$/;

/**
 * Whether `value` is one of this system's event ids — a UUIDv7.
 *
 * **The three checks are the three that make a uuid a uuidv7**: the canonical form, the
 * version nibble, and the variant nibble. Checking the form alone would accept a v4
 * uuid; checking the version alone would accept a hand-typed `7` in a v1 uuid's slot.
 */
export function isEventUuid(value: string): boolean {
  if (!CANONICAL_UUID.test(value)) return false;

  const version = value[14];
  if (version !== VERSION_7) return false;

  const variant = value[19]?.toLowerCase();
  return variant !== undefined && VARIANT_NIBBLES.has(variant);
}

/**
 * Whether `value` is a minted public slug.
 *
 * **A slug is a precise, identifiable shape** — the format above — and the branch uses
 * that precision rather than guessing.
 */
export function isMintedSlug(value: string): boolean {
  return MINTED_SLUG.test(value);
}

/**
 * Whether the parameter names the **signed-in Detail Screen**.
 *
 * **The rule is: a minted slug is the public page; everything else is the detail
 * screen.**
 *
 * **Why it is stated that way round.** The rule has to answer two questions at once —
 * "is this a public slug?" and "is this an event id?" — and only the first can be
 * answered with certainty. A slug's shape is *knowable* (the backend mints one format
 * and never changes it). An id's shape is *guessable*: the real ids are UUIDv7s, but
 * the detail endpoint accepts any UUID, and the route has to keep working for the ids
 * that are actually linked into it.
 *
 * So the discriminator identifies the thing it can identify, and routes **everything
 * else** to the detail screen. That is the safe direction:
 *
 * - A parameter that is not a minted slug reaches `GET /api/events/{event_id}`, whose
 *   parameter is typed `UUID` on the backend. **A parameter that is not a UUID is
 *   refused with a 422**, so a stray token can never render a personal page — it
 *   renders the "no longer available" state, which is a fact about a non-existent id
 *   rather than a leak of somebody else's.
 * - A parameter that *is* a minted slug reaches the public endpoint, which has no
 *   session at all.
 *
 * **And `isEventUuid` is still the primary test**, because it names the ids this
 * system actually mints and is what the route checks first. A UUIDv7 is never a minted
 * slug — the shapes are disjoint — so the two tests cannot disagree about one.
 */
export function isDetailEvent(value: string): boolean {
  return isEventUuid(value) || !isMintedSlug(value);
}
