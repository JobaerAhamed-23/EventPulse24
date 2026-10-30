/**
 * The three calendar providers, as onboarding step 1 presents them (FR-3, FR-50).
 *
 * **All three are equal.** The mockup-onboarding parity rule is explicit: the providers
 * render "with identical visual weight (no 'primary' Google + ghost Apple/Outlook)". The
 * order here is the mockup's order and carries no ranking.
 *
 * **The mechanism is a pasted secret address, not OAuth.** The step-1 mockup's sub-labels
 * say "1-click OAuth" and "app-specific password", but Amendment A-9 and AD-18 set the
 * MVP mechanism as the provider's secret ICS/webcal address, which the user pastes and
 * the backend stores encrypted. The sub-labels below therefore say what the step actually
 * does. Keeping the mockup's wording would promise a handshake that does not exist.
 *
 * The `key` is what `POST /api/personal/calendars` takes as `provider`; it matches the
 * backend's `CalendarConnection.Provider` values, and the contract refuses anything else.
 */

export type CalendarProvider = {
  /** The API's provider value. */
  key: "google" | "apple" | "outlook";
  /** The monogram tile's letter. Decorative — the name is the accessible text. */
  monogram: string;
  name: string;
  /** What the connection is: read-only, by secret address. */
  subLabel: string;
  /** Where this provider hides its secret address. */
  guidance: string;
};

export const CALENDAR_PROVIDERS: readonly CalendarProvider[] = [
  {
    key: "google",
    monogram: "G",
    name: "Google Calendar",
    subLabel: "Read-only · secret calendar address",
    guidance:
      "In Google Calendar, open Settings → Settings for my calendars, pick the calendar, then copy the Secret address in iCal format.",
  },
  {
    key: "apple",
    monogram: "A",
    name: "Apple Calendar",
    subLabel: "Read-only · shared calendar address",
    guidance:
      "In iCloud Calendar, click the share icon beside the calendar, tick Public Calendar, and copy the address it shows.",
  },
  {
    key: "outlook",
    monogram: "O",
    name: "Outlook Calendar",
    subLabel: "Read-only · published calendar address",
    guidance:
      "In Outlook, open Settings → Calendar → Shared calendars, publish the calendar, and copy the ICS link.",
  },
];

/**
 * The standing warning under every provider's field.
 *
 * It is here because it is true and because it explains the masked input: anyone holding
 * the address can read the calendar, which is why the backend treats it as a credential
 * and never hands it back.
 */
export const SECRET_ADDRESS_WARNING =
  "This address is a key to your calendar. Anyone who has it can read it, so we store it encrypted and never show it again.";

export function providerByKey(key: string): CalendarProvider | undefined {
  return CALENDAR_PROVIDERS.find((provider) => provider.key === key);
}
