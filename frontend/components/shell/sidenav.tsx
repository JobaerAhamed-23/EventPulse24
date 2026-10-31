"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { AddEventButton } from "@/components/add-event-button";
import { PersonalEventsPanel } from "@/components/personal-events-panel";
import {
  AddGlyph,
  BrowseGlyph,
  ConflictsGlyph,
  DigestGlyph,
  SearchGlyph,
  SettingsGlyph,
  TimelineGlyph,
} from "@/components/shell/nav-glyphs";

/**
 * `Component.Sidenav.App` — the desktop left rail (`EXPERIENCE.md` §4).
 *
 * **Six routes, in the locked order.** Digest / Timeline / Add / Browse / Conflicts /
 * Settings. The five-route variant is the onboarding batch's, and the six-route variant
 * is canonical on every authed surface going forward.
 *
 * **The active route is an ink pill, never a terracotta fill.** Both documents say so,
 * twice: "no terracotta fill on the active route", and "terracotta on a small-control
 * toggle burns the accent on a control used many times per day". The pill mirrors the
 * `Control.Segmented` ink-inversion pattern in miniature.
 *
 * **An inert route is a `<span>`, not an `<a>`.** Four of the six routes do not exist
 * yet. An anchor with `aria-disabled="true"` is still focusable and still navigates —
 * the attribute is a hint, not a mechanism — and a link to a 404 is a lie about where
 * the label goes. A `<span>` says what is true: there is nothing there yet.
 */
export type SidenavProps = {
  /** The user's name, for the account row. */
  name: string;
};

export function Sidenav({ name }: SidenavProps) {
  const pathname = usePathname();
  const [addOpen, setAddOpen] = useState(false);

  return (
    <aside
      aria-label="Primary"
      className="hidden w-(--layout-sidenav-app-width-tablet) shrink-0 flex-col self-start bg-surface-paper p-6 md:flex lg:w-(--layout-sidenav-app-width-desktop)"
    >
      <div className="flex items-center gap-2 text-ink-primary [font:var(--type-scale-body-md)] font-semibold">
        <span aria-hidden="true" className="text-accent-terracotta">
          ◉
        </span>
        EventPulse24
      </div>
      <div className="my-4 h-px bg-border-subtle" />

      <nav aria-label="Main">
        <ul className="flex flex-col gap-1">
          <SidenavItem href="/" label="Digest" active={pathname === "/"} glyph={<DigestGlyph />} />
          <SidenavItem label="Timeline" glyph={<TimelineGlyph />} />
          <SidenavItem
            label="Add"
            glyph={<AddGlyph />}
            control={<AddEventButton compact withoutPanel onOpen={() => setAddOpen(true)} />}
          />
          <SidenavItem label="Browse" glyph={<BrowseGlyph />} />
          <SidenavItem label="Conflicts" glyph={<ConflictsGlyph />} />
          <SidenavItem label="Settings" glyph={<SettingsGlyph />} />
        </ul>
      </nav>

      {/*
        The create sheet is mounted *outside* the route list. It is a whole panel of
        markup, and inside the `<li>` it would be a form nested in a navigation list.
      */}
      <PersonalEventsPanel createOpen={addOpen} onCreateOpenChange={setAddOpen} />

      {/*
        The footer is pinned to the bottom of the rail (`margin-top: auto`) and carries
        the two affordances that fit nowhere else: Search and the account row. It is
        structural, not situational — it renders in the empty, skeleton and error states
        too.
      */}
      <div className="mt-auto border-t border-border-subtle pt-4">
        <button
          type="button"
          aria-label="Search events"
          className="flex w-full items-center gap-3 rounded-subtle px-2 py-2 text-left text-ink-secondary hover:bg-surface-subtle hover:text-ink-primary [font:var(--type-scale-body-md)]"
        >
          <SearchGlyph />
          Search
        </button>
        <Link
          href="/settings"
          aria-label={`Account: ${name} — opens Settings`}
          className="mt-1 flex items-center gap-3 rounded-subtle px-2 py-2 hover:bg-surface-subtle"
        >
          <span
            aria-hidden="true"
            className="flex h-7 w-7 items-center justify-center rounded-full bg-surface-inset text-ink-secondary [font:var(--type-scale-meta-sm)]"
          >
            {name.slice(0, 2).toUpperCase()}
          </span>
          <span className="flex flex-col">
            <span className="text-ink-primary [font:var(--type-scale-body-md)]">{name}</span>
            <span className="text-ink-muted [font:var(--type-scale-meta-sm)]">Account</span>
          </span>
        </Link>
      </div>
    </aside>
  );
}

/**
 * One route row.
 *
 * `control` is for a row that opens a surface in place rather than routing — the Add
 * item, which the spec says mounts the creation panel instead of navigating.
 */
function SidenavItem({
  href,
  label,
  glyph,
  active,
  control,
}: {
  href?: string;
  label: string;
  glyph: React.ReactNode;
  active?: boolean;
  control?: React.ReactNode;
}) {
  const className = [
    "flex items-center gap-3 rounded-subtle px-2 py-2 [font:var(--type-scale-body-md)]",
    active
      ? "border border-border-subtle bg-surface-subtle text-ink-primary"
      : "text-ink-secondary",
  ].join(" ");

  if (control) {
    return (
      <li>
        <span className={className}>
          {glyph}
          {control}
          <span>{label}</span>
        </span>
      </li>
    );
  }

  if (!href) {
    // The inert route. It is a `<span>` with `aria-disabled`, and it says "Coming soon"
    // in muted meta ink — present, so the route order is honest, and honest about what
    // it is.
    return (
      <li>
        <span className={className} aria-disabled="true">
          {glyph}
          <span>{label}</span>
          <span className="ml-auto text-ink-muted [font:var(--type-scale-meta-sm)]">
            Coming soon
          </span>
        </span>
      </li>
    );
  }

  return (
    <li>
      <Link href={href} className={className} aria-current={active ? "page" : undefined}>
        {glyph}
        <span>{label}</span>
      </Link>
    </li>
  );
}
