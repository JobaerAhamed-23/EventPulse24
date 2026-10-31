"use client";

/**
 * The digest header's quick action: **+ Add personal event** (`pulse-digest-desktop.html`
 * `.pagehead .quickadd`).
 *
 * The spine's Add affordance **opens `Sheet.PersonalEventCreate` in place** — it does not
 * route to an `/events/new` page. So this button opens the create sheet rather than
 * navigating, and there is deliberately **no `/add` route**: a route would be a second
 * entry point for one surface. The sidenav's and the bottom-tab's Add rows open the same
 * sheet; this is the one the page head carries, where the user is already looking.
 *
 * **No terracotta fill.** Primary fill is reserved for actions *inside* a decision moment,
 * and a tap-anytime control is not one. The mockup draws it as a terracotta **outline**
 * with terracotta text, and the sheet's own primary action keeps the fill.
 *
 * **Only the sheets are mounted** (`sheetsOnly`): the button belongs to the page head, and
 * the personal-events list is not part of the head.
 *
 * **The confirmation is inline, next to the button.** The digest does not show personal
 * events any more — the Timeline does — so an add from here would otherwise look like
 * nothing happened. `EXPERIENCE.md` §3's rule is "inline notice only": no toast, no
 * modal, no separate banner. So the line sits under the button, in `Text.Meta`, and
 * carries a link to the week the event landed on.
 */
import Link from "next/link";
import { useState } from "react";

import { PersonalEventsPanel } from "@/components/personal-events-panel";
import { AddGlyph } from "@/components/shell/nav-glyphs";

/** What the panel reports when an event was created. */
type Added = { name: string; localDate: string };

export function AddEventButton() {
  const [open, setOpen] = useState(false);
  const [added, setAdded] = useState<Added | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  /**
   * A new add clears whatever the last one said.
   *
   * **The notice is about the last attempt.** A line that says "couldn't save that"
   * next to the button that opens the sheet again would be a claim about an attempt
   * the user has not made yet.
   */
  const openCreate = (): void => {
    setAdded(null);
    setFailed(null);
    setOpen(true);
  };

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={openCreate}
        aria-haspopup="dialog"
        aria-label="Add personal event"
        className="inline-flex min-h-[44px] items-center gap-2 rounded-control border border-accent-terracotta/45 px-4 py-2 font-semibold text-accent-terracotta hover:border-accent-terracotta hover:bg-accent-terracotta/10 [font:var(--type-scale-meta-md)]"
      >
        <AddGlyph />
        <span>Add personal event</span>
      </button>

      {/*
        The inline notice. It is a **live region**, so the confirmation is announced as
        well as shown — a sheet closing is not otherwise a thing a screen reader says.

        **A live region without `role="status"`.** The digest's own "ready" line is the
        page's `role="status"`, and it stays the only one there is — two status regions
        on a page would make "which one is the page talking?" a question the DOM cannot
        answer. This is the same rule `PersonalEventsPanel` follows for the same reason.
      */}
      <p aria-live="polite" className="text-ink-secondary [font:var(--type-scale-meta-md)]">
        {added ? (
          <>
            &quot;{added.name}&quot; was added.{" "}
            <Link
              href={`/timeline?week=${added.localDate}`}
              className="text-ink-primary underline underline-offset-4"
            >
              See it on your Timeline
            </Link>
          </>
        ) : (
          failed
        )}
      </p>

      <PersonalEventsPanel
        sheetsOnly
        createOpen={open}
        onCreateOpenChange={setOpen}
        onCreated={(event) => {
          setFailed(null);
          setAdded(event);
        }}
        onFailed={(message) => {
          setAdded(null);
          setFailed(message);
        }}
        // The line above is the announcement. Without this the panel would announce
        // the same add through its own hidden region, and a screen reader would say it
        // twice.
        messageShownByCaller
      />
    </div>
  );
}
