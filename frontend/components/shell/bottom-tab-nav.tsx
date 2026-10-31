"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";

import { PersonalEventsPanel } from "@/components/personal-events-panel";
import { type AccountProps } from "@/components/shell/account-menu";
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
 * navigates to a 404 is a lie. An inert slot is a `<span>` with `aria-disabled="true"`,
 * and it carries the same "Coming soon" the sidenav's inert rows carry — visually hidden
 * here, because a slot is a fifth of the bar and there is no room to print it, but said
 * aloud, because `aria-disabled` alone does not explain *why* the slot does nothing.
 *
 * **Sign out reaches mobile through the More sheet.** The sidenav is `hidden md:flex`, so
 * the account row in its footer is desktop-only; `MoreMenu` carries the same account
 * panel here.
 */
export function BottomTabNav({ name, email }: AccountProps) {
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
        <TabSlot label="Add" glyph={<AddGlyph />} onActivate={() => setAddOpen(true)} />
        <TabSlot label="Conflicts" glyph={<ConflictsGlyph />} />
        <TabSlot label="Settings" glyph={<SettingsGlyph />} />

        {/*
          The More slot is a control, not a route: it opens the overflow sheet, where
          Browse lives. It is mounted as its own component because it carries a dialog
          — and a dialog inside a nav slot would be a form nested in a navigation list.
        */}
        <MoreMenu name={name} email={email} />
      </nav>

      {/*
        The create and conflict sheets are mounted outside the bar, and only the sheets
        (`sheetsOnly`): inside a nav slot they would be a form nested in a navigation list,
        and the whole panel here would be a third column of the shell's flex row.
      */}
      <PersonalEventsPanel sheetsOnly createOpen={addOpen} onCreateOpenChange={setAddOpen} />
    </>
  );
}

/**
 * One slot.
 *
 * `onActivate` is for a slot that opens a surface in place rather than routing — the Add
 * slot, which the spec says mounts the creation panel instead of navigating. The whole
 * slot is the button, so the tap target is the full fifth of the bar.
 */
function TabSlot({
  label,
  glyph,
  active,
  onActivate,
}: {
  label: string;
  glyph: React.ReactNode;
  active?: boolean;
  onActivate?: () => void;
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

  if (onActivate) {
    return (
      <button
        type="button"
        onClick={onActivate}
        aria-haspopup="dialog"
        aria-label="Add personal event"
        className={className}
      >
        {content}
      </button>
    );
  }

  if (!active && label !== "Digest") {
    // The inert slot. Nothing to navigate to, so there is nothing to focus.
    //
    // "Coming soon" is visually hidden rather than printed: the sidenav's inert rows show
    // it in muted meta ink, but a slot here is a fifth of the bar and the words do not
    // fit. Hiding them visually keeps the bar's geometry and still tells a screen reader
    // what `aria-disabled` alone leaves unsaid — that the route is on the way, not broken.
    return (
      <div className={className} aria-disabled="true">
        {content}
        <span className="sr-only">Coming soon</span>
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
