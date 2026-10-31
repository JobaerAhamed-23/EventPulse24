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
  /**
   * **Render the glyph only, with no visible label.**
   *
   * The sidenav and the bottom-tab both draw the Add slot themselves — a 16×16
   * stroke-only `+` glyph beside the route label — so the button inside them must not
   * carry a second "+ Add" label. The button's `aria-label` stays, so the control is
   * still named.
   */
  compact?: boolean;
  /**
   * **Do not mount the create sheet here.**
   *
   * The sidenav's Add row is a `<li>` in the route list, and the sheet is a whole
   * panel of markup. Mounting it inside the list item would put a form inside a
   * navigation list — and the panel's own "Name" field would be a descendant of the
   * route list, which is nonsense structurally. So the caller mounts the sheet
   * separately and drives this button's open state.
   */
  withoutPanel?: boolean;
  /** Called when the button is pressed, instead of opening the sheet here. */
  onOpen?: () => void;
};

export function AddEventButton({
  events = [],
  compact = false,
  withoutPanel = false,
  onOpen,
}: AddEventButtonProps) {
  const [open, setOpen] = useState(false);

  const trigger = (
    <button
      type="button"
      onClick={() => (onOpen ? onOpen() : setOpen(true))}
      aria-haspopup="dialog"
      aria-label="Add personal event"
      className={
        compact
          ? "rounded-subtle p-1 text-ink-secondary hover:text-ink-primary"
          : "rounded-control border border-border-subtle px-3 py-1.5 [font:var(--type-scale-meta-md)] text-ink-secondary"
      }
    >
      {compact ? null : "+ Add"}
    </button>
  );

  if (withoutPanel) return trigger;

  return (
    <>
      {trigger}
      {/* The panel owns the create sheet's open state, so the sheet opens when the panel
          is told to. The panel is the one place that knows the round trip. */}
      <PersonalEventsPanel events={events} createOpen={open} onCreateOpenChange={setOpen} />
    </>
  );
}

/**
 * The compact button's mark.
 *
 * **Empty on purpose.** The sidenav and the bottom-tab both draw the Add *glyph*
 * themselves, beside the route label — a 16×16 stroke-only `+`. A compact button that
 * also rendered a `+` would put two plus signs in one row, and a plain-text `+` beside
 * a stroke-only SVG glyph is not the same mark twice; it is one mark drawn badly.
 *
 * The button is still a real, focusable, named control — it just carries no ink of its
 * own, because the glyph beside it is the ink.
 */
export function AddEventButtonCompact() {
  return <AddEventButton compact withoutPanel />;
}
