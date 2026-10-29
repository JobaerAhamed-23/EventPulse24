"use client";

/**
 * The **Add** nav affordance (EXPERIENCE.md `Component.Sidenav.App` / `Component.BottomTab`).
 *
 * The spine's "Add" slot **opens `Sheet.PersonalEventCreate` in place** — it does not
 * route to an `/events/new` page. So this button opens the create sheet rather than
 * navigating, and there is deliberately **no `/add` route**: a route would be a second
 * entry point for one surface.
 *
 * The sidenav itself does not exist in the frontend yet (the six-route shell is later
 * work). This button is the affordance the shell will carry, so the surface is reachable
 * and the shell can adopt the component without changing the flow.
 *
 * **No terracotta fill.** The spine is explicit: the Add slot does not carry the
 * terracotta fill — primary fill is reserved for actions *inside* a decision moment, and
 * terracotta on a tap-anytime nav control would burn the accent. The sheet's own
 * primary action keeps it.
 */
import { useState } from "react";

import { PersonalEventsPanel } from "@/components/personal-events-panel";

export type AddEventButtonProps = {
  /** The user's personal events, read by the server component that renders this. */
  events?: Parameters<typeof PersonalEventsPanel>[0]["events"];
};

export function AddEventButton({ events = [] }: AddEventButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label="Add personal event"
        className="rounded-control border border-border-subtle px-3 py-1.5 [font:var(--type-scale-meta-md)] text-ink-secondary"
      >
        + Add
      </button>
      {/* The panel owns the create sheet's open state, so the sheet opens when the panel
          is told to. The panel is the one place that knows the round trip. */}
      <PersonalEventsPanel events={events} createOpen={open} onCreateOpenChange={setOpen} />
    </>
  );
}
