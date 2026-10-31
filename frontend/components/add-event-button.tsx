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
 */
import { useState } from "react";

import { PersonalEventsPanel } from "@/components/personal-events-panel";
import { AddGlyph } from "@/components/shell/nav-glyphs";

export function AddEventButton() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label="Add personal event"
        className="inline-flex min-h-[44px] items-center gap-2 rounded-control border border-accent-terracotta/45 px-4 py-2 font-semibold text-accent-terracotta hover:border-accent-terracotta hover:bg-accent-terracotta/10 [font:var(--type-scale-meta-md)]"
      >
        <AddGlyph />
        <span>Add personal event</span>
      </button>
      <PersonalEventsPanel sheetsOnly createOpen={open} onCreateOpenChange={setOpen} />
    </>
  );
}
