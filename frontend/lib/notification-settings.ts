/**
 * The notification settings' **pure** helpers — the ones a client component may use.
 *
 * **Why these are not in `notification-settings-read.ts`.** That module reads the
 * settings on the server, so it needs the visitor's cookies — `sessionHeaders()` from
 * `lib/session.ts`, which imports `next/headers`. **That makes it a server-only
 * module**, and a `"use client"` component that imports it drags `next/headers` into
 * the client bundle. The production build says so plainly:
 *
 * > You're importing a module that depends on "next/headers". This API is only
 * > available in Server Components in the App Router.
 *
 * So the helpers that are *not* about reading — slicing a stored time, naming the
 * server's default window — live here, where both sides can reach them. The read
 * stays where it belongs, on the server.
 *
 * **The test suite did not catch this; the build did.** The client tests render the
 * island in jsdom, where `next/headers` resolves to a stub and the import is
 * harmless. The bundler is the thing that knows the difference between a server
 * module and a client one, so the build is the gate that catches it.
 */

/**
 * A stored time as the time input wants it.
 *
 * **The server sends `HH:MM:SS`; the input wants `HH:MM`.** Pydantic's `time`
 * serialises with seconds, so a stored `22:00:00` arrives as six characters. The
 * `<input type="time">` reads five. This slices.
 *
 * **It slices rather than parses.** A stored time is a wall clock, not an instant —
 * there is no zone to apply and no date to carry. Slicing the string keeps it the
 * wall clock it is; parsing it into a `Date` would silently attach a zone, and the
 * window would move.
 *
 * **One implementation, because three would be three chances to disagree.** The quiet
 * window and the digest schedule both slice a stored time, and the slice has to be the
 * same slice — a time input that read `22:00` on one screen and `22:0` on another
 * would be a bug that only showed up on the screen nobody tested.
 */
export function clockForInput(stored: string | null | undefined): string {
  if (!stored) return "";
  return stored.slice(0, 5);
}

/**
 * The server's default Quiet Hours window — **the one the user would get back**.
 *
 * **Why the client needs it.** `quiet_hours` is `null` when the user has turned quiet
 * hours **off**, and there is then no window to edit. The screen still shows the two
 * clocks, and it shows the window the user would get if they turned it back on — so
 * the value has to come from somewhere.
 *
 * **It is the server's default, spelled once.** `DEFAULT_QUIET_HOURS_START`/`END` are
 * `time(22, 0)` and `time(8, 0)` on the backend, and the locked label — *"10pm–8am.
 * Nothing during this window."* — says the same. **The two copies have to agree**, and
 * the way to keep them agreeing is to have exactly one copy of the number on this side
 * and a test that says what it is.
 *
 * **Why it is `HH:MM:SS` and not `HH:MM`.** It is a *stored* time — the shape the
 * server stores and the shape `NotificationSettingsOut` carries — so it goes through
 * the same `clockForInput` slice as any other stored time. A default spelled in the
 * input's shape would be a different shape from every other time in this file.
 */
export const DEFAULT_QUIET_HOURS = {
  start: "22:00:00",
  end: "08:00:00",
} as const;
