"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { PersonalEventsPanel } from "@/components/personal-events-panel";
import { AccountMenu } from "@/components/shell/account-menu";
import { BrandMark } from "@/components/brand-mark";
import {
  AddGlyph,
  BrowseGlyph,
  ConflictsGlyph,
  DigestGlyph,
  SearchGlyph,
  SettingsGlyph,
  TimelineGlyph,
} from "@/components/shell/nav-glyphs";
import { isSettingsPath } from "@/lib/settings-sections";

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
 * **An inert route is a `<span>`, not an `<a>`.** An anchor with `aria-disabled="true"`
 * is still focusable and still navigates — the attribute is a hint, not a mechanism — and
 * a link to a 404 is a lie about where the label goes. A `<span>` says what is true:
 * there is nothing there yet.
 *
 * **All six routes exist now.** Browse shipped with the Browse surface, and Settings
 * shipped with the first `/settings/*` screens, so the rail has no inert row left. The
 * rule above still stands for whatever route is deferred next, and the branch that
 * implements it is kept — but nothing in the rail uses it today, and a rule that is
 * never exercised is a rule that rots. **The branch is therefore not deleted; it is
 * pinned by a test**, so that the next inert route inherits the rule rather than
 * reinventing it.
 *
 * **The account row is a control, and it stays one.** It used to link to `/settings`,
 * which did not exist — the one place in the rail that broke the rule above — and it was
 * made a button onto the account sheet (`AccountMenu`), which is where Sign out lives.
 * `/settings` exists now, but the row is **not** turned back into a link: that would
 * evict Sign out from the only surface that mounts it at both breakpoints, to duplicate
 * a destination the Settings row above already carries. The sheet links to `/settings`
 * instead.
 */
export type SidenavProps = {
  /** The user's name, for the account row. */
  name: string;
  /** The user's email, shown in the account sheet. */
  email: string;
  /** The user's picture — `""` when the account has none. The seed for the disc. */
  avatarUrl: string;
};

export function Sidenav({ name, email, avatarUrl }: SidenavProps) {
  const pathname = usePathname();
  const [addOpen, setAddOpen] = useState(false);

  return (
    <aside
      aria-label="Primary"
      className="sticky top-0 hidden h-screen w-(--layout-sidenav-app-width-tablet) shrink-0 flex-col self-start overflow-y-auto border-r border-border-subtle bg-surface-paper p-6 md:flex lg:w-(--layout-sidenav-app-width-desktop)"
    >
      <div className="flex items-center gap-2 text-ink-primary [font:var(--type-scale-body-md)] font-semibold">
        <BrandMark size={28} />
        EventPulse24
      </div>
      <div className="my-4 h-px bg-border-subtle" />

      <nav aria-label="Main">
        <ul className="flex flex-col gap-1">
          {/*
            **Digest is active on every path under `/events/`.**

            The Detail Screen is reached by tapping a Digest card, and the Reminder
            Picker hangs off the Detail Screen — so both hang off Digest in the IA. The
            mockup says the same thing: *"Parent surface in IA is Digest (Detail is
            reached by tapping a Digest card; Reminder Picker hangs off Detail). So
            6-route sidenav uses Digest as the active nav-item, mirroring
            event-detail-desktop.html."*

            **The rule is a prefix, not an equality.** An equality would mark Digest
            active on the digest home and nowhere else, and every screen the user
            reaches *from* the digest would show no active route at all — which reads as
            "you have left the digest" rather than "you are still in it".
          */}
          <SidenavItem
            href="/"
            label="Digest"
            active={pathname === "/" || pathname.startsWith("/events/")}
            glyph={<DigestGlyph />}
          />
          <SidenavItem
            href="/timeline"
            label="Timeline"
            // **Timeline covers the personal-event reminder screen too.**
            // `personal-event-reminders-desktop.html` is explicit: *"a Personal Event is
            // reached from the Timeline / Add surfaces, where personal events live,
            // rather than from the public Pulse Digest"* — so that route marks Timeline
            // active, the way `/events/` marks Digest active.
            active={pathname === "/timeline" || pathname.startsWith("/personal-events/")}
            glyph={<TimelineGlyph />}
          />
          <SidenavItem label="Add" glyph={<AddGlyph />} onActivate={() => setAddOpen(true)} />
          {/*
            **Browse is a real route now.** The Browse surface shipped, so this row is a
            link and not a "Coming soon" label.

            **The active rule is an equality, not a prefix.** Browse has no children —
            there is no `/browse/*` screen — so a prefix rule would be a claim about
            routes that do not exist. Digest uses a prefix because `/events/*` hangs off
            it, and Settings uses one because `/settings/*` does; Browse has neither,
            so it takes the same rule as Timeline and Conflicts.
          */}
          <SidenavItem
            href="/browse"
            label="Browse"
            active={pathname === "/browse"}
            glyph={<BrowseGlyph />}
          />
          <SidenavItem
            href="/conflicts"
            label="Conflicts"
            active={pathname === "/conflicts"}
            glyph={<ConflictsGlyph />}
          />
          {/*
            **Settings points at `/settings`, the index.**

            It used to point at `/settings/reminders`, because there was no index — and
            that one screen has no links out, so the rail landed the user on a dead end
            with five sibling routes they could not reach. The index exists now, and it
            and `SettingsNav` both render `SETTINGS_SECTIONS`, so every settings screen
            is reachable from the rail in two taps and from every other in one.

            **`isSettingsPath` is the active rule, not `startsWith("/settings/")`.** The
            trailing slash is load-bearing: `"/settings".startsWith("/settings/")` is
            `false`, so the plain prefix would go quiet on the index — the rail dropping
            its highlight on the very screen the rail just navigated to. Digest's
            `/events/` rule has the same shape and avoids it the same way, with an
            equality beside the prefix.
          */}
          <SidenavItem
            href="/settings"
            label="Settings"
            active={isSettingsPath(pathname)}
            glyph={<SettingsGlyph />}
          />
        </ul>
      </nav>

      {/*
        The create and conflict sheets are mounted *outside* the route list, and only the
        sheets: inside the `<li>` a list would be a form nested in a
        navigation list, and the whole panel would wedge a heading into the rail.
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
        <AccountMenu name={name} email={email} avatarUrl={avatarUrl} />
      </div>
    </aside>
  );
}

/**
 * One route row.
 *
 * `onActivate` is for a row that opens a surface in place rather than routing — the Add
 * item, which the spec says mounts the creation panel instead of navigating. The whole
 * row is the button, so the target is the row the user sees, not a glyph inside it.
 */
function SidenavItem({
  href,
  label,
  glyph,
  active,
  onActivate,
}: {
  href?: string;
  label: string;
  glyph: React.ReactNode;
  active?: boolean;
  onActivate?: () => void;
}) {
  const className = [
    // `[&>svg]:shrink-0`: a row with "Coming soon" is tight at 220px, and the glyph is
    // the one thing in it that must keep its 16px.
    "flex items-center gap-3 rounded-subtle px-2 py-2 [font:var(--type-scale-body-md)] [&>svg]:shrink-0",
    active
      ? "border border-border-subtle bg-surface-subtle text-ink-primary"
      : "text-ink-secondary",
  ].join(" ");

  if (onActivate) {
    return (
      <li>
        <button
          type="button"
          onClick={onActivate}
          aria-haspopup="dialog"
          aria-label="Add personal event"
          className={`${className} w-full text-left hover:bg-surface-subtle hover:text-ink-primary`}
        >
          {glyph}
          <span>{label}</span>
        </button>
      </li>
    );
  }

  if (!href) {
    // The inert route. It is a `<span>` with `aria-disabled`, and it says "Coming soon"
    // in muted meta ink — present, so the route order is honest, and honest about what
    // it is.
    //
    // **No row uses this today.** Browse was the last one, and it shipped. The branch
    // stays anyway, because the rule it implements — *an inert route is a `<span>`, not
    // an anchor* — is the rule the next deferred route has to inherit. Deleting the
    // only implementation of a rule the product still states would weaken it exactly
    // when someone needs it.
    //
    // `tests/digest-home-boundary.test.ts` pins this branch by name, so it cannot rot
    // silently into an anchor while it waits.
    return (
      <li>
        <span className={className} aria-disabled="true">
          {glyph}
          <span>{label}</span>
          <span className="ml-auto whitespace-nowrap text-ink-muted [font:var(--type-scale-meta-sm)]">
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
