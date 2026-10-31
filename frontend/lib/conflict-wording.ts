import type { components } from "@/lib/api/schema";

/**
 * The conflict wording, in one place.
 *
 * **Two surfaces, one vocabulary.** The forced prompt (`Sheet.ConflictResolution`, FR-58)
 * and the review screen (`/conflicts`, FR-33) both talk about the same five resolutions.
 * The work item's Technical Note says so outright: *"Reuse the conflict wording and
 * action set from `components/sheets/conflict-resolution.tsx` rather than writing a
 * second copy of the strings; if the inline layout needs them outside the sheet, extract
 * them once."*
 *
 * **So the strings live here, and both surfaces read them.** What differs between the
 * surfaces is not the vocabulary but the **point of view**:
 *
 *   - The **prompt** is relative. It has a side the user just created ("the new one")
 *     and a side that was already saved ("the existing one"), so its labels say
 *     "Edit the new one" and "Update the existing one".
 *   - The **review screen** is symmetric. It shows two sides and there is no "new" one —
 *     the pair row is sorted by id, so neither side is the recent one. Its labels name
 *     the event instead: "Move Work standup", "Skip Designers coffee chat".
 *
 * **The action set is shared; the label wording is contextual, and both are built here.**
 * A copy of the table in two files would drift, and a drift between a prompt's button
 * and the review screen's button would be a bug the user finds by clicking.
 */

/** The resolutions the API accepts. The prompt never offers one outside this set. */
export type Resolution = components["schemas"]["ConflictResolutionIn"]["resolution"];

/** One side of a conflict pair, as the list hands it over. */
export type ConflictSide = components["schemas"]["ConflictListSideOut"];

/** The kind of record a side names. */
export type SideKind = ConflictSide["kind"];

/**
 * **The minimum a side has to carry** for the rules in this module to work.
 *
 * `actionSide()` and `movableSide()` read a side's **kind** and its **id** — nothing
 * else. The list's side carries a display zone and an availability flag; the Detail
 * Screen's side carries neither, because the prompt needs the instants and the kind.
 *
 * **So the rules take the minimum**, and each surface hands over its own richer side.
 * Forcing the Detail Screen's side to invent an `available` flag or a zone it was never
 * given would be inventing facts — and `available: true` for a personal event whose
 * record has gone is a lie the prompt would then render.
 */
export type SideRef = {
  kind: SideKind;
  id: string;
};

/**
 * Narrow a server-supplied action name to a resolution the API accepts.
 *
 * The contract types `actions` as the closed union the server owns. A name outside it is
 * one this module has no label for, so it is not offered — a surface renders the server's
 * choices, and a choice it cannot explain is not a choice it offers.
 */
export function asResolution(value: string): Resolution | null {
  return value === "keep_both" ||
    value === "edit_new" ||
    value === "update_existing" ||
    value === "delete_new" ||
    value === "skip_public"
    ? value
    : null;
}

/**
 * The prompt's hint sentences — one per resolution.
 *
 * These are the sentences that say what choosing the action *does*, and they are the same
 * on both surfaces: "Both events stay on your timeline" is true whether the question was
 * asked by a sheet or by a list.
 */
export const RESOLUTION_HINTS: Record<Resolution, string> = {
  keep_both:
    "Both events stay on your timeline. A small amber dot on each reminds you they're close. We won't ask again.",
  edit_new:
    "Open the event in edit mode with the time pre-highlighted so you can shift it. Conflict re-checks automatically.",
  update_existing:
    "Open the event you already saved in edit mode so you can change it. Conflict re-checks automatically.",
  delete_new: "Removes the new event. You'll be asked to confirm before it's gone for good.",
  skip_public:
    "Releases your saved copy of the public event. Your own event stays exactly as it is.",
};

/** The glyph each action carries. Decorative — the label carries the meaning. */
export const RESOLUTION_GLYPHS: Record<Resolution, string> = {
  keep_both: "✓",
  edit_new: "✎",
  update_existing: "✎",
  delete_new: "✕",
  skip_public: "↷",
};

/**
 * The prompt's labels — one per resolution.
 *
 * **These are relative to a prompt**, which has a new side and an existing side. The
 * review screen cannot use them: it has two symmetric sides and no "new" one, so "Edit
 * the new one" there would name an event that does not exist. The review surface's
 * labels come from `reviewActionLabel` below, and both are built from this one module.
 */
export const RESOLUTION_LABELS: Record<Resolution, string> = {
  keep_both: "Keep both — I'll manage",
  edit_new: "Edit the new one",
  update_existing: "Update the existing one",
  delete_new: "Delete the new one",
  skip_public: "Skip the public event",
};

/**
 * The accessible name for a resolution, on the prompt.
 *
 * **The name says the action and its consequence** — the AC for the review screen asks
 * for exactly this, and the prompt's own names already do it. The consequence is the
 * point: "Keep both" alone would not tell a screen-reader user that the conflict
 * indicator stays.
 */
export const RESOLUTION_ARIA: Record<Resolution, string> = {
  keep_both: "Keep both events. The conflict indicator remains on both.",
  edit_new: "Edit the new event. Its start time is highlighted so you can move it.",
  update_existing:
    "Update the existing event. Its details open in edit mode so you can change them.",
  delete_new: "Delete the new event. You will be asked to confirm before it is removed.",
  skip_public: "Skip the public event. Your saved copy of it is released and your own event stays.",
};

/**
 * What a side is called, in a label.
 *
 * **"Personal" and "Public event"** are the two words the Timeline's blocks already use,
 * and the pair's sides carry the same distinction. The review screen's action labels
 * name an event with them ("Move Work standup", "Skip Designers coffee chat"), so the
 * nouns have to be the same nouns the cards use.
 */
export function sideNoun(kind: SideKind): string {
  return kind === "personal_event" ? "personal event" : "public event";
}

/**
 * The review screen's visible label for a resolution.
 *
 * **The label names the event the action is about**, because on the review screen the
 * pair is symmetric: "Skip the public event" says *which* public event only if there is
 * one, and the user is looking at two of them side by side.
 *
 * `subject` is the event's own name — "Work standup", "Designers coffee chat" — and
 * `kind` is that side's kind, which decides the verb:
 *
 *   - `edit_new` / `update_existing` → **"Move {name}"** — the personal event moves.
 *   - `skip_public` → **"Skip {name}"** — the public event is released.
 *   - `delete_new` → **"Delete {name}"** — the personal event is removed.
 *   - `keep_both` → **"Keep both — I'll manage"** — it is about neither side, so it says
 *     neither.
 *
 * **The two moves cannot collide.** The backend's resolution maps are keyed by the
 * pair's *kind* — a time pair offers `edit_new`, a duplicate pair offers
 * `update_existing` — so a pair never carries both, and the review screen never shows
 * two buttons with the same label.
 *
 * **A name that is missing falls back to the kind's noun**, so the label never reads
 * "Move " with nothing after it.
 */
export function reviewActionLabel(
  resolution: Resolution,
  subject: string | null | undefined,
): string {
  const name = subject?.trim() ? subject.trim() : null;
  switch (resolution) {
    case "edit_new":
    case "update_existing":
      return name ? `Move ${name}` : "Move the personal event";
    case "skip_public":
      return name ? `Skip ${name}` : "Skip the public event";
    case "delete_new":
      return name ? `Delete ${name}` : "Delete the personal event";
    case "keep_both":
      return RESOLUTION_LABELS.keep_both;
  }
}

/**
 * The review screen's accessible name for a resolution.
 *
 * **The name says the action and its consequence** — the AC is explicit about this, and
 * it is the reason a visible label alone is not enough: "Move Work standup" does not
 * tell a screen-reader user that the event opens in edit mode with its time
 * highlighted.
 *
 * The consequence comes from `RESOLUTION_ARIA`, so the prompt and the review screen
 * cannot describe the same action differently.
 */
export function reviewActionAria(
  resolution: Resolution,
  subject: string | null | undefined,
): string {
  const name = subject?.trim() ? subject.trim() : null;
  switch (resolution) {
    case "edit_new":
    case "update_existing":
      return name
        ? `Move ${name} to a different time. Its start time is highlighted so you can shift it.`
        : "Move the personal event to a different time. Its start time is highlighted so you can shift it.";
    case "skip_public":
      return name
        ? `Skip ${name}. Your saved copy of it is released and your own event stays.`
        : "Skip the public event. Your saved copy of it is released and your own event stays.";
    case "delete_new":
      return name
        ? `Delete ${name}. You will be asked to confirm before it is removed.`
        : "Delete the personal event. You will be asked to confirm before it is removed.";
    case "keep_both":
      return RESOLUTION_ARIA.keep_both;
  }
}

/**
 * The side a resolution acts on, in a pair.
 *
 * **The pair row is symmetric, so the row cannot say which side the user is acting on**
 * — the request has to (`ConflictResolutionIn.side`). This is where that choice is made,
 * and it is made from the pair's **kinds**, never from `left`/`right`: those are sorted
 * by id, not by role.
 *
 * **The rules are the server's rules.** The backend's `_target_side_kind` decides what
 * each action may act on, and it enforces it — a request naming the other kind of side
 * is refused with `IllegalResolutionError`, and the pair stays active. So the client has
 * to name the same side the server would accept:
 *
 *   - `edit_new` — the **personal** side. "Move" means moving your own event.
 *   - `update_existing` — the **personal** side. It is the duplicate's middle action,
 *     and it opens the personal event in edit mode — not the saved one.
 *   - `delete_new` — the **personal** side. Deleting a save is `skip_public`'s job.
 *   - `skip_public` — the **saved** side. Releasing somebody else's event is not the
 *     same act as deleting your own.
 *   - `keep_both` — **neither side**. It acts on neither, and the server accepts
 *     *either* of the pair's sides for it. So this returns `null`, and the caller names
 *     one of the pair's own sides — a side the server will accept.
 *
 * **A pair with two personal sides** is ambiguous for `edit_new` and `update_existing`:
 * both sides are the same kind, so "the personal side" and "the other side" are the
 * same claim. The rule picks the **left** side for `edit_new` and the **right** side
 * for `update_existing` — a deterministic answer, and the one the server's own
 * duplicate handling mirrors.
 *
 * **A pair with no personal side** (a saved-vs-saved pair) cannot answer `edit_new`,
 * `update_existing` or `delete_new` at all — the server refuses them. The rule still
 * names a side, so the request is well-formed and the server's refusal is the honest
 * answer rather than a client-side guess.
 *
 * **A mixed pair offers four actions.** The backend's `resolutions_for_pair` is the
 * **union** of the two sides' sets, so a personal-vs-saved pair carries `delete_new`
 * *and* `skip_public` alongside the two they share. Both destructive actions are real
 * choices about that pair, and each names its own side — which is exactly why this
 * function exists.
 */
export function actionSide(
  resolution: Resolution,
  left: SideRef,
  right: SideRef,
): { kind: SideKind; id: string } | null {
  const personal = [left, right].find((side) => side.kind === "personal_event") ?? null;
  const saved = [left, right].find((side) => side.kind === "saved_event") ?? null;

  switch (resolution) {
    case "edit_new":
      if (personal) return { kind: personal.kind, id: personal.id };
      return { kind: left.kind, id: left.id };
    case "update_existing":
      // The **personal** side, like `edit_new`. When there are two of them, the right
      // one is the "existing" event the duplicate action updates.
      if (personal) {
        if (personal.id === left.id && right.kind === "personal_event") {
          return { kind: right.kind, id: right.id };
        }
        return { kind: personal.kind, id: personal.id };
      }
      return { kind: left.kind, id: left.id };
    case "delete_new":
      return personal ? { kind: personal.kind, id: personal.id } : { kind: left.kind, id: left.id };
    case "skip_public":
      return saved ? { kind: saved.kind, id: saved.id } : { kind: left.kind, id: left.id };
    case "keep_both":
      return null;
  }
}

/**
 * The resolution a "move" action posts, and the side it opens in the edit sheet.
 *
 * **Two resolutions move an event, and they are not the same request.** `edit_new` moves
 * the event the user just created; `update_existing` moves the one they already had.
 * The review screen offers whichever the server allows, and this says which side the
 * edit sheet should open.
 */
export function moveResolution(resolution: Resolution): Resolution | null {
  return resolution === "edit_new" || resolution === "update_existing" ? resolution : null;
}

/**
 * The side a move opens in the edit sheet.
 *
 * **The side the move acts on, and it must be a personal event** — the edit sheet
 * edits personal events. `actionSide` says which side the request names; this says
 * whether that side can be opened for editing.
 */
export function movableSide<T extends SideRef>(
  resolution: Resolution,
  left: T,
  right: T,
): T | null {
  if (moveResolution(resolution) === null) return null;
  const target = actionSide(resolution, left, right);
  if (!target) return null;
  const side = target.id === left.id ? left : right;
  return side.kind === "personal_event" ? side : null;
}

/**
 * The resolution, in words, for a resolved pair's history line.
 *
 * **"Skipped public · Poetry reading · Fri Sep 11"** — the mockup's line, and the AC's
 * example. Three parts: what was decided, which event it was about, and when.
 *
 * The wording is the past tense of the decision, and it is the **same decision** the
 * active row offers — so a user reading the history sees the words they would have
 * chosen.
 */
export function resolutionPhrase(resolution: Resolution | null | undefined): string {
  switch (resolution) {
    case "keep_both":
      return "Kept both";
    case "edit_new":
    case "update_existing":
      return "Moved personal";
    case "delete_new":
      return "Deleted personal";
    case "skip_public":
      return "Skipped public";
    default:
      return "Decided";
  }
}
