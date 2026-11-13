"use client";

/**
 * The name the shell is showing **right now** — and the way to change it.
 *
 * ## Why this exists
 *
 * **The rail is rendered on the server, and a server render is a photograph.**
 *
 * Every page reads the session on the server, derives the display name from it, and
 * hands that name to `AppShell`, which hands it to the sidenav, the bottom bar and the
 * account sheet. That name is fixed for the life of the render. **So a person who types
 * their name on `/settings/profile`, sees "Saved.", and looks up at the rail sees the
 * old one** — and the rail is on every page, so the wrong name is on every page.
 *
 * **A save that does not show up is a save that did not happen.** The account sheet's
 * whole point is that the name in it is the name you are called by, and the sheet is
 * opened from the rail. If the rail disagrees with the sheet, one of them is lying, and
 * the reader has no way to tell which.
 *
 * **This is the same shape as the live save allowance** (`browse-quota-provider`): the
 * server states the fact, and the client shows the fact it was given — but a client
 * that is given the fact *once*, at page load, and never hears about it again is a
 * client showing a stale fact. The allowance was worth a provider; so is the name.
 *
 * ## Why a store and not a provider
 *
 * **The reader is the shell; the writer is a page's island.** They are in different
 * subtrees, and the writer is *below* the reader — `ProfileName` sits inside the
 * content, and the rail sits beside it. A prop cannot cross that boundary (the content
 * is server-rendered and the rail is not), and threading a callback down through the
 * page, the settings nav and the island would be plumbing for one string.
 *
 * **A React context cannot do it either, without moving the shell.** The context
 * provider would have to sit *above* the rail — and the rail is rendered by `AppShell`,
 * which every page mounts by hand. So a provider means fifteen pages each wrapping
 * their own `<AppShell>`, and the fifteen pages are exactly the thing the display-name
 * work just finished consolidating.
 *
 * **So the store is a module, and the shell reads it directly.** The module is a
 * client module, so it is safe to read from the client components that need it — and
 * `useSyncExternalStore` is React's own answer to "a value outside React that React
 * must re-render for".
 *
 * ## What the store holds, and what it does not
 *
 * **It holds the display name — the name to call somebody by — not the stored name.**
 * The two are different questions, and the display question is the one the shell asks.
 * The stored name is `""` when no name is set; the display name is the email-derived
 * fallback. **The store holds the answer the shell wants**, so the shell does not have
 * to know the fallback rule exists.
 *
 * **It holds `null` when nothing has been published**, and `null` means *"ask the
 * server-rendered name"*. That is the seed: every page passes the name it was rendered
 * with, and the store's value — once published — wins over it.
 *
 * ## Why the seed is a fallback and not the truth
 *
 * **The published name is newer than the render.** It was published *after* the page
 * was rendered, by a save the server has already accepted. The server-rendered name is
 * older by construction. So when the two disagree, the published one is the one the
 * account holds.
 *
 * **And when they agree, nothing changes.** The overwhelmingly common case is that
 * the store is empty, because nobody has changed anything this session — and then the
 * seed is the only answer there is.
 *
 * ## The stale case, and why it is acceptable
 *
 * **The store outlives a navigation.** A soft navigation to `/timeline` re-renders the
 * server components, and the server reads the name the account now holds — the same
 * name the store holds, because the save went through the API before the store was
 * written. **So the two agree, and nothing is stale.**
 *
 * **The store does outlive a *hard* reload in one direction**: the module registry is
 * wiped by a reload, so the store empties and the seed takes over. That is the
 * correct direction — the server is the source of truth, and a reload asks it.
 *
 * **The genuinely stale case is another tab.** If a second tab changes the name, this
 * tab's store still holds the old one until a reload. **That is the same bargain the
 * live save allowance makes**, and the right one: re-reading the name on every
 * navigation would be a second answer to a question the page already answered.
 */
import { useSyncExternalStore } from "react";

/**
 * The published display name, or `null` when nothing has been published.
 *
 * **It is `null` and not `""` on purpose.** An empty display name is not a thing the
 * product shows — the shell always shows *something* — so `null` can mean "no
 * published name, ask the seed" without also meaning "the name is empty".
 */
let published: string | null = null;

/** The listeners, told whenever the published name changes. */
const listeners = new Set<() => void>();

/**
 * The current published name.
 *
 * **It returns the module-level value directly**, which is what `useSyncExternalStore`
 * requires: the snapshot must be the *same* value for as long as nothing has changed,
 * or React re-renders in a loop.
 */
function getSnapshot(): string | null {
  return published;
}

/** The listeners' unsubscribe function. */
function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Publish the name the shell should show from now on.
 *
 * **This is the write.** It is called by the one place that knows the account's name
 * has changed — the profile island, and only after the server has accepted the write.
 *
 * **Publishing before the server answers would be publishing a guess.** The server
 * trims, collapses and caps the name, so the account's name is not always the one that
 * was typed — and the shell would then show a name the account does not hold.
 */
export function publishName(name: string): void {
  published = name;
  for (const listener of listeners) listener();
}

/**
 * The live display name, or the seed when nothing has been published.
 *
 * **The seed is what the caller was rendered with** — the server-rendered name, which
 * is the fallback-derived display name on every page.
 */
export function useLiveName(seed: string): string {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot) ?? seed;
}
