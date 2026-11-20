"use client";

/**
 * The picture the shell is showing **right now** — and the way to change it.
 *
 * ## Why this exists, and why it is separate from `lib/avatar.ts`
 *
 * **The rail is rendered on the server, and a server render is a photograph.** Every
 * page reads the session on the server, takes the picture URL from it, and hands that
 * URL to `AppShell`, which hands it to the sidenav, the bottom bar and the account
 * sheet. That URL is fixed for the life of the render. **So a person who uploads a
 * picture, sees "Saved.", and looks up at the rail sees the old one** — and the rail is
 * on every page, so the wrong picture is on every page.
 *
 * **A save that does not show up is a save that did not happen.** The account sheet's
 * whole point is that the picture in it is the one you are represented by, and the
 * sheet is opened from the rail.
 *
 * **The rule and the store are two modules because they are two things.** The rule —
 * *the initials for a display name* — is a pure function that a server component may
 * want; the store is React plumbing that only the client has. `lib/avatar.ts` holds the
 * rule and imports nothing; this module holds the store.
 *
 * ## Why a store and not a provider
 *
 * **The reader is the shell; the writer is a page's island.** They are in different
 * subtrees, and the writer is *below* the reader — the upload island sits inside the
 * content, and the rail sits beside it. A prop cannot cross that boundary (the content
 * is server-rendered and the rail is not), and threading a callback down through the
 * page, the settings nav and the island would be plumbing for one string.
 *
 * **A React context cannot do it either, without moving the shell.** The context
 * provider would have to sit *above* the rail — and the rail is rendered by `AppShell`,
 * which every page mounts by hand. So a provider means fifteen pages each wrapping
 * their own `<AppShell>`.
 *
 * **So the store is a module, and the shell reads it directly** — exactly as
 * `lib/session-name.ts` does for the name.
 *
 * ## Why the picture does not share the name's store
 *
 * **The name publishes a string; the picture publishes a URL, and a URL is a different
 * kind of value.** It becomes `""` when the picture is removed — the account's state is
 * *no picture*, not *a picture of nothing* — and it changes when the picture is
 * replaced, because the URL's `{version}` segment is derived from the stored key.
 *
 * **One store per value, one rule each.** Both stores hold `null` for "nothing has been
 * published", and both fall back to a seed. But they are two stores because they answer
 * two questions, and a store that answered both would have to carry a union type and
 * a rule for which field to read.
 *
 * ## The stale case, and why it is acceptable
 *
 * **The store outlives a navigation.** A soft navigation re-renders the server
 * components, and the server reads the picture the account now holds — the same picture
 * the store holds, because the save went through the API before the store was written.
 *
 * **The genuinely stale case is another tab.** If a second tab changes the picture, this
 * tab's store still holds the old one until a reload. **That is the same bargain the
 * name makes**, and the right one.
 */
import { useSyncExternalStore } from "react";

/**
 * The published picture URL, or `null` when nothing has been published.
 *
 * **It is `null` and not `""` on purpose**, for the same reason `session-name.ts` uses
 * `null`: an empty URL is not a thing the shell shows — the shell shows the initials —
 * so `null` can mean "no published picture, ask the seed" without also meaning "the
 * picture is empty".
 */
let published: string | null = null;

/** The listeners, told whenever the published picture changes. */
const listeners = new Set<() => void>();

/**
 * The current published picture URL.
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
 * Publish the picture the shell should show from now on.
 *
 * **This is the write.** It is called by the one place that knows the account's picture
 * has changed — the upload island, and only after the server has accepted the write.
 *
 * **Publishing before the server answers would be publishing a guess.** The server
 * validates the bytes, re-encodes them and may refuse the file outright — so a URL
 * published early would name a picture that may not exist.
 */
export function publishAvatar(avatarUrl: string): void {
  published = avatarUrl;
  for (const listener of listeners) listener();
}

/**
 * The live picture URL, or the seed when nothing has been published.
 *
 * **The seed is what the caller was rendered with** — the server-rendered URL, which is
 * `""` when the account has no picture.
 */
export function useLiveAvatar(seed: string): string {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot) ?? seed;
}
