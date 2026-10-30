/**
 * The visitor's location choice for the Pulse Preview (FR-2).
 *
 * FR-2: the choice "persists in a cookie for the session". It is read and written **in
 * the browser only**, and that is what keeps `/preview` cacheable: a choice written
 * server-side would make the page vary per visitor, and AD-12 requires the opposite —
 * the page renders identically for everyone, signed in or not.
 *
 * Three shapes, because there are three answers:
 *
 *   - **absent** — the visitor has not been asked yet. Show the banner, use geo.
 *   - **`off`** — "Don't use my location". The request carries `use_geo=false`, so the
 *     backend does not consult the location header at all, and the banner never returns
 *     this session.
 *   - **a city name** — "Use this" or a pick from "Change". The request carries `city=`.
 */

/** The cookie's name. One name, read and written in one place. */
export const CHOICE_COOKIE = "ep_preview_city";

/** The value that means "don't use my location". Not a city, and never confusable with one. */
export const OPT_OUT = "off";

export type PreviewChoice =
  { kind: "unasked" } | { kind: "opted-out" } | { kind: "city"; city: string };

function readCookie(jar: string, name: string): string | null {
  for (const part of jar.split(";")) {
    const separator = part.indexOf("=");
    if (separator === -1) continue;
    if (part.slice(0, separator).trim() !== name) continue;
    const value = part.slice(separator + 1).trim();
    return value === "" ? null : decodeURIComponent(value);
  }
  return null;
}

/** The choice this visitor has already made, if any. */
export function readChoice(
  jar: string = typeof document === "undefined" ? "" : document.cookie,
): PreviewChoice {
  const value = readCookie(jar, CHOICE_COOKIE);
  if (value === null) return { kind: "unasked" };
  if (value === OPT_OUT) return { kind: "opted-out" };
  return { kind: "city", city: value };
}

/**
 * Remember the choice for this session.
 *
 * **No `Max-Age` and no `Expires`**: a session cookie is what FR-2 asks for, and it is
 * also the lightest promise to make about a location preference — it lasts as long as the
 * tab does and then it is gone. `SameSite=Lax` because nothing cross-site has any
 * business carrying it.
 */
export function rememberChoice(choice: Exclude<PreviewChoice, { kind: "unasked" }>): void {
  if (typeof document === "undefined") return;
  const value = choice.kind === "opted-out" ? OPT_OUT : choice.city;
  document.cookie = `${CHOICE_COOKIE}=${encodeURIComponent(value)}; Path=/; SameSite=Lax`;
}

/** The query the preview request carries for this choice. */
export function previewQuery(choice: PreviewChoice): { city?: string; use_geo?: boolean } {
  if (choice.kind === "opted-out") return { use_geo: false };
  if (choice.kind === "city") return { city: choice.city };
  return {};
}
