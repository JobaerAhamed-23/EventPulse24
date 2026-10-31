"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";

import { AddEventButton } from "@/components/add-event-button";
import { PersonalEventsPanel } from "@/components/personal-events-panel";
import { MoreMenu } from "@/components/shell/more-menu";
import {
  AddGlyph,
  ConflictsGlyph,
  DigestGlyph,
  SettingsGlyph,
  TimelineGlyph,
} from "@/components/shell/nav-glyphs";

/**
 * `Component.BottomTab` — the mobile navigation (`EXPERIENCE.md` §4).
 *
 * **Five slots, twenty percent each.** Digest / Timeline / Add / Conflicts / Settings.
 * Browse is the sixth route and lives behind the **More** affordance on the trailing
 * edge (`Component.BottomTab.MoreMenu`), so the five-slot geometry is preserved exactly.
 *
 * **The active slot is ink-inverted, with a 2px terracotta underline above it.** The
 * ink inversion mirrors the `Control.Segmented` pattern; the underline is the *only*
 * chromatic use in the bar. **Never a full-bar terracotta fill** — the spec says that
 * twice, and the reason is that terracotta on a control used many times per day burns
 * the accent.
 *
 * **The More slot is a control, not a route.** It opens the overflow sheet, and it
 * carries no `aria-current="page"` — the row *inside* the sheet carries that when the
 * overflow route is the current one.
 *
 * **An inert slot is inert.** Four of the five routes do not exist yet, and a slot that
 * navigates to a 404 is a lie. An inert slot is a `<span>` with `aria-disabled="true"`.
 */
export function BottomTabNav() {
  const pathname = usePathname();
  const [addOpen, setAddOpen] = useState(false);

  return (
    <>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-20 flex border-t border-border-subtle bg-surface-elevated md:hidden"
        style={{ height: "var(--layout-bottom-tab-height)" }}
      >
        <TabSlot label="Digest" active={pathname === "/"} glyph={<DigestGlyph />} />
        <TabSlot label="Timeline" glyph={<TimelineGlyph />} />
        <TabSlot
          label="Add"
          glyph={<AddGlyph />}
          control={<AddEventButton compact withoutPanel onOpen={() => setAddOpen(true)} />}
        />
        <TabSlot label="Conflicts" glyph={<ConflictsGlyph />} />
        <TabSlot label="Settings" glyph={<SettingsGlyph />} />

        {/*
          The More slot is a control, not a route: it opens the overflow sheet, where
          Browse lives. It is mounted as its own component because it carries a dialog
          — and a dialog inside a nav slot would be a form nested in a navigation list.
        */}
        <MoreMenu />
      </nav>

      {/*
        The create sheet is mounted outside the bar. It is a whole panel of markup, and
        inside a nav slot it would be a form nested in a navigation list.
      */}
      <PersonalEventsPanel createOpen={addOpen} onCreateOpenChange={setAddOpen} />
    </>
  );
}

/**
 * One slot.
 *
 * `control` is for a slot that opens a surface in place rather than routing — the Add
 * slot, which the spec says mounts the creation panel instead of navigating.
 */
function TabSlot({
  label,
  glyph,
  active,
  control,
}: {
  label: string;
  glyph: React.ReactNode;
  active?: boolean;
  control?: React.ReactNode;
}) {
  const className = [
    "flex flex-1 flex-col items-center justify-center gap-1",
    // The active slot is ink-inverted, and the terracotta underline sits above it.
    active ? "bg-ink-primary text-ink-inverse" : "text-ink-muted",
    "[font:var(--type-scale-meta-sm)]",
  ].join(" ");

  const content = (
    <>
      {glyph}
      <span>{label}</span>
    </>
  );

  if (control) {
    return (
      <div className={className}>
        {glyph}
        {control}
        <span>{label}</span>
      </div>
    );
  }

  if (!active && label !== "Digest") {
    // The inert slot. Nothing to navigate to, so there is nothing to focus.
    return (
      <div className={className} aria-disabled="true">
        {content}
      </div>
    );
  }

  return (
    <a
      href={label === "Digest" ? "/" : undefined}
      aria-current={active ? "page" : undefined}
      className={[
        className,
        // The 2px terracotta underline: the only chromatic use in the bar.
        active ? "border-t-2 border-accent-terracotta" : "",
      ].join(" ")}
    >
      {content}
    </a>
  );
}
