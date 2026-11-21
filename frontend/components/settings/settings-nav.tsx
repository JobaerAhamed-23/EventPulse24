"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { SETTINGS_DEFAULT_HREF, SETTINGS_SECTIONS } from "@/lib/settings-sections";

/**
 * `Component.Subnav.Settings` — the row of section links every `/settings/*` screen
 * carries.
 *
 * **It is the sub-nav the settings routes shipped without.** Each route used to be
 * reachable only from whichever page happened to link to it, and four of the six were
 * linked from nowhere. This renders `SETTINGS_SECTIONS`, so every settings screen is one
 * tap from every other, and adding a route to that list is the whole of making it
 * reachable.
 *
 * ## It is a client component, and only because of the pathname
 *
 * Marking the current section is the one thing this needs that a server component cannot
 * do, so it takes `usePathname` and nothing else. **It reads no session and no API** —
 * the pages stay server components, and this leaf does not drag their data into the
 * browser.
 *
 * **Every section is listed for every user, including Collections.** Gating the row on
 * entitlement would need the tier here, which would make this a second place the tier is
 * read and a second place it can be read wrongly. `/settings/collections` already
 * renders a Free user an upgrade prompt rather than a refusal, so the honest row is the
 * one that goes there.
 *
 * ## The active section is an ink pill, never a terracotta fill
 *
 * The same rule and the same classes as `Component.Sidenav.App`: *"terracotta on a
 * small-control toggle burns the accent on a control used many times per day"*. This is
 * such a control, once per settings section.
 *
 * ## The shape is a wrapping row, not a second rail
 *
 * `AppShell` already puts a vertical rail on the left at `md`. A second vertical rail
 * inside the content would be two navigations competing for the same edge, and at phone
 * width there is no room for either. A wrapping row sits above the page's own header,
 * reads as a table of contents for the screen below it, and needs no breakpoint of its
 * own.
 */
export function SettingsNav() {
  const pathname = usePathname();

  return (
    <nav aria-label="Settings sections" className="mb-8">
      <ul className="flex flex-wrap gap-2">
        {SETTINGS_SECTIONS.map((section) => {
          /**
           * **An equality, not a prefix** — with one exception, and the exception is
           * the index.
           *
           * No settings section has children, so a prefix rule would be a claim about
           * routes that do not exist.
           *
           * **The exception is `/settings`, which is where the redirect starts.**
           * `/settings` is not a section; it forwards to `SETTINGS_DEFAULT_HREF`, and
           * during that forward the browser's own pathname is still `/settings` while
           * the server has already rendered the *default* section's markup. So the
           * server marks the default section and the client — reading `/settings` —
           * marks nothing, and the two disagree.
           *
           * **That disagreement is a hydration mismatch**, and it is visible: React
           * reports the differing `aria-current` and the differing `className` on the
           * row. It was found by a browser probe that simulated the Dark Reader
           * extension, because the extension's DOM rewrite shifts the hydration
           * timing enough to surface the race — but nothing about it is about the
           * extension, and it would surface for any reader whose hydration is
           * disturbed.
           *
           * **So the index marks the section it is forwarding to.** The row the reader
           * sees as current is the row they are about to arrive at, and the server and
           * the client agree.
           */
          const active =
            pathname === section.href ||
            (pathname === "/settings" && section.href === SETTINGS_DEFAULT_HREF);

          return (
            <li key={section.href}>
              <Link
                href={section.href}
                aria-current={active ? "page" : undefined}
                className={[
                  "inline-block rounded-subtle px-3 py-2 [font:var(--type-scale-meta-md)]",
                  active
                    ? "border border-border-subtle bg-surface-subtle text-ink-primary"
                    : "border border-transparent text-ink-secondary hover:bg-surface-subtle hover:text-ink-primary",
                ].join(" ")}
              >
                {section.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
