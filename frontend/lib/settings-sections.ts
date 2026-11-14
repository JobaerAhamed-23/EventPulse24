/**
 * The settings sections — **the one list**, read by the index and by the sub-nav.
 *
 * ## Why this file exists
 *
 * Seven `/settings/*` routes shipped one at a time, each from its own work item, and the
 * convention each of them inherited was *"there is no `/settings` index page and no
 * settings sub-navigation"*. So every route that needed to be reachable was made
 * reachable by hand-written links from whichever page happened to ship before it: the
 * nav pointed at `/settings/reminders`, `/settings/quiet-hours` carried the only links
 * to `/settings/digest` and `/settings/calendars`, and `/settings/collections` was
 * linked from nowhere at all. Four of the six screens were working routes that no
 * sequence of clicks could reach.
 *
 * **A list of routes is not a navigation.** The fix is not another hand-written link; it
 * is one list that both the index and the sub-nav render, so a new settings route is
 * reachable from everywhere the moment it is added here, and unreachable from nowhere.
 *
 * ## It is data, not markup
 *
 * The list is a plain module constant rather than a component, because two different
 * surfaces render it in two different shapes — the index as a stack of described rows,
 * the sub-nav as a compact rail — and a component that could do both would be a
 * component with a `variant` prop deciding which half of itself to be.
 *
 * ## The order is the mockup's
 *
 * `settings-desktop.html` runs Notifications → Quiet hours → Calendar sync → Account.
 * The built routes map onto that order with two insertions: the default Reminder Plan is
 * this product's "Notifications" section, and the digest's two screens sit together
 * because they answer the two halves of one question — when the brief arrives, and what
 * is in it. **Profile sits after Account**, because it is the account-adjacent section
 * and the mockup's order ends there.
 *
 * **Appearance, Privacy and Danger zone are not here**, because they are not built. A
 * row for a route that does not exist is the 404 link this whole file exists to prevent;
 * `tests/settings-routes.test.ts` asserts that every `href` below resolves to a real
 * `page.tsx`. **Profile is here because its route does exist** — the rule is about
 * reachability, not about which sections are interesting.
 */

export type SettingsSection = {
  /** The route. Always an absolute `/settings/*` path. */
  href: string;
  /**
   * The nav label, and the index row's title.
   *
   * It matches the `<h1>` of the page it points at. A label that renamed the screen on
   * the way to it would make the user wonder whether they had arrived.
   */
  label: string;
  /**
   * One line on what the section is for — the index renders it under the label.
   *
   * It is the same sentence as the destination page's own subheading, for the same
   * reason the label is: the index is a table of contents, not a second description of
   * the product.
   */
  description: string;
};

export const SETTINGS_SECTIONS: readonly SettingsSection[] = [
  {
    href: "/settings/reminders",
    label: "Default reminders",
    description: "What we suggest when you save an event.",
  },
  {
    href: "/settings/quiet-hours",
    label: "Quiet hours",
    description: "When we stay quiet, and when your daily brief arrives.",
  },
  {
    href: "/settings/digest",
    label: "Pulse Digest",
    description: "What travels in your daily brief.",
  },
  {
    href: "/settings/calendars",
    label: "Calendars",
    description: "Connect a calendar to see personal events alongside public ones.",
  },
  {
    href: "/settings/collections",
    label: "Collections",
    description: "Named groups of the events you kept.",
  },
  {
    href: "/settings/sources",
    label: "Sources",
    description: "Where your events come from, and how much of each you see.",
  },
  {
    href: "/settings/taste",
    label: "Taste",
    description: "Categories you've asked us to show less of.",
  },
  {
    href: "/settings/account",
    label: "Account",
    description: "Your plan, and your data.",
  },
  {
    href: "/settings/profile",
    label: "Profile",
    description: "Your name, and how we address you.",
  },
];

/**
 * Is `pathname` inside the settings surface?
 *
 * **The index is included**, which is why this is not a bare `startsWith("/settings/")`
 * — that test is false for `/settings` itself, and a rail that goes quiet on the
 * settings index reads as "you have left Settings" at the exact moment the user arrived.
 */
export function isSettingsPath(pathname: string): boolean {
  return pathname === "/settings" || pathname.startsWith("/settings/");
}

/**
 * Where `/settings` sends you — **the first section, by construction.**
 *
 * `/settings` used to render an index: one described row per section, and a click on one
 * of them to reach a screen that then showed the same sections again in its sub-nav. The
 * index was a step between the nav and the setting, and `SettingsNav` had already made it
 * redundant. `/settings` now redirects here.
 *
 * **It is derived, not declared.** A hard-coded `"/settings/reminders"` would be a second
 * place the default lives, free to drift from the list and free to name a route that no
 * longer exists. Reordering `SETTINGS_SECTIONS` moves the default with it, which is the
 * behaviour the order already implies: the first section is the one you see first.
 */
export const SETTINGS_DEFAULT_HREF: string = SETTINGS_SECTIONS[0].href;
