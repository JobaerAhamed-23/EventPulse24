/**
 * The cap payload on a refusal, read for the inline upgrade prompt.
 *
 * Two endpoints refuse on a tier ceiling, and both answer **409** with the same
 * `details` shape (`backend/domain/errors.py`):
 *
 * | Cap | Endpoint | `code` | `details` |
 * |---|---|---|---|
 * | The save cap (FR-49) | `POST /api/personal/saved-events/{id}` | `save_cap_reached` | `{cap, upgrade_hint}` |
 * | The calendar cap (FR-50) | `POST /api/personal/calendars` | `calendar_cap_reached` | `{cap, upgrade_hint}` |
 *
 * **This is a sibling of `readApiError`, not a change to it.** `readApiError` is used in
 * nine places and returns `{code, message, fieldErrors}` — the shape a *form* renders. A
 * cap is not a form error, and widening `ApiError` with an `upgrade_hint` would put an
 * always-null field on every error in the app for the benefit of two of them. So this
 * module reads the same body for a different question, and the nine other call sites are
 * untouched.
 *
 * **It reads `upgrade_hint` and nothing else as the sentence.** The server owns the copy
 * (`frontend-upgrade-prompts`, acceptance criterion 4): a backend wording change must not
 * require a frontend change, so no sentence is written here, assembled here, or chosen
 * between here.
 *
 * **It cannot see a modal.** `modal`, `title`, `actions` and `dismissable` are absent from
 * both payloads *by design* — `calendar_connections.py` and `save_cap.py` both say so in
 * as many words. This module does not read them, so a future payload that grew one could
 * not turn this prompt into an interruption without someone editing this file on purpose.
 */

/** What a cap refusal said: the ceiling the user hit, and one sentence about it. */
export type CapDetails = {
  /** The tier's limit — 1 free save a day, 1 calendar provider. */
  cap: number;
  /** The server's own sentence. Rendered verbatim. */
  upgradeHint: string;
};

/** The two refusal codes that carry a cap. Nothing else is a cap. */
const CAP_CODES = new Set(["save_cap_reached", "calendar_cap_reached"]);

/**
 * Read a cap out of an API refusal, or `null` if it is not one.
 *
 * `error` is the `error` member of an openapi-fetch response — the parsed body of a
 * non-2xx answer — or anything thrown while making the request.
 *
 * **The `code` decides, not the presence of the fields.** Both cap endpoints already
 * answer 409 for a second, unrelated reason (`scheduling_conflict` on the save path), and
 * narrowing on "does it have an `upgrade_hint`" would make the client's reading depend on
 * a payload's accidents rather than on the fact the server stated.
 */
export function readCapDetails(error: unknown): CapDetails | null {
  if (typeof error !== "object" || error === null) return null;
  const body = error as Record<string, unknown>;
  if (typeof body.code !== "string" || !CAP_CODES.has(body.code)) return null;

  const details = body.details;
  if (typeof details !== "object" || details === null) return null;
  const { cap, upgrade_hint: upgradeHint } = details as Record<string, unknown>;

  // A cap with no sentence has nothing to render, and a prompt with no words would be a
  // bare "Upgrade" link appearing for no stated reason. Treated as not-a-cap, which
  // falls back to the surface's ordinary refusal line.
  if (typeof cap !== "number" || typeof upgradeHint !== "string" || upgradeHint === "") {
    return null;
  }
  return { cap, upgradeHint };
}
