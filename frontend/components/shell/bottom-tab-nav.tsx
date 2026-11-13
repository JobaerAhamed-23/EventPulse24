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
import { isSettingsPath } from "@/lib/settings-sections";

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
 * **All five slots are real now.** Browse lives behind the More sheet and the sheet's
 * row is a link; Settings points at `/settings/reminders`. **A slot that navigates to a
 * 404 is a lie**, and there is no such slot left in the bar.
 *
 * **An inert slot is inert.** The branch for one is kept, because the rule it implements
 * — *a route that does not exist is a `<span>`, never a link* — is the rule the next
 * deferred route has to inherit. No slot uses it today.
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
        {/*
          **Digest is a real route, and it was never a link.** This slot has had no
          `href` since the digest home shipped, so on a phone the *first* tab rendered
          the inert branch — a disabled `<span>` carrying a visually-hidden "Coming soon"
          — while also carrying `active={pathname === "/"}`. The home route's own tab did
          nothing and said it was not coming soon.

          **It is now a link to `/`.** The route exists; the inert branch was never the
          right treatment for it, and it is the same defect the sidenav's Browse row
          had, one route over.

          **The active rule is a prefix, like the sidenav's.** The Detail Screen hangs
          off Digest in the IA — it is reached by tapping a Digest card — so a reader on
          `/events/...` has not left the Digest. The sidenav already applies this rule
          to its Digest row, and the bottom bar must agree with it, or the same screen
          would mark Digest active in the rail and nothing active in the bar.
        */}
        <TabSlot
          href="/"
          label="Digest"
          active={pathname === "/" || pathname.startsWith("/events/")}
          glyph={<DigestGlyph />}
        />
        <TabSlot
          label="Timeline"
          href="/timeline"
          active={pathname === "/timeline"}
          glyph={<TimelineGlyph />}
        />
        <TabSlot label="Add" glyph={<AddGlyph />} onActivate={() => setAddOpen(true)} />
        <TabSlot
          label="Conflicts"
          href="/conflicts"
          active={pathname === "/conflicts"}
          glyph={<ConflictsGlyph />}
        />
        {/*
          **Settings points at `/settings`, the index** — the same destination and the
          same active rule as the desktop rail's row, from the same module constant.

          **The mobile rail gets the same treatment as the desktop one.** It used to
          land on `/settings/reminders`, a screen with no links out, which on a phone
          meant the product said *"You can change these later in Settings"* and then
          Settings was one of six screens with no way to the other five. A route that
          only exists on desktop is not a route, and neither is one you cannot navigate
          to.
        */}
        <TabSlot
          href="/settings"
          label="Settings"
          active={isSettingsPath(pathname)}
          glyph={<SettingsGlyph />}
        />

        {/*
          The More slot is a control, not a route: it opens the overflow sheet, where
          Browse lives. It is mounted as its own component because it carries a dialog
          — and a dialog inside a nav slot would be a form nested in a navigation list.
        */}
        <MoreMenu name={name} email={email} />
      </nav>

      {/*
        The create and conflict sheets are mounted outside the bar, and only the sheets
        inside a nav slot a list would be a form nested in a navigation list,
        and the whole panel here would be a third column of the shell's flex row.
      */}
      <PersonalEventsPanel createOpen={addOpen} onCreateOpenChange={setAddOpen} />
    </>
  );
}

/**
 * One slot.
 *
 * `onActivate` is for a slot that opens a surface in place rather than routing — the Add
 * slot, which the spec says mounts the creation panel instead of navigating. The whole
 * slot is the button, so the tap target is the full fifth of the bar.
 *
 * `href` is for a slot that routes. **A slot with no `href` and no `onActivate` is
 * inert** — it is a `<span>` with `aria-disabled`, because a link to a 404 is a lie
 * about where the label goes. No slot is inert today, and the branch stays for the next
 * deferred route.
 */
function TabSlot({
  label,
  glyph,
  href,
  active,
  onActivate,
}: {
  label: string;
  glyph: React.ReactNode;
  href?: string;
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

  if (!href) {
    // The inert slot. Nothing to navigate to, so there is nothing to focus.
    //
    // **No slot uses this today.** Digest was the last one, and it was a link by now —
    // but the branch stays, because the rule it implements is the rule the next deferred
    // route has to inherit. A route that does not exist is a `<span>`, never a link to
    // a 404.
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
      href={href}
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
