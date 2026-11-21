import type { components } from "@/lib/api/schema";
import { apiBaseUrl } from "@/lib/api-base-url";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The user's home city, and the cities they may choose from.
 *
 * **One city, read from the one place that stores it.** The home city is a column on the
 * digest preference, and Browse reads the same column — `browse_read._read_preference`
 * calls it "deliberately the digest's city — one meaning of 'your city' across both
 * surfaces". A settings screen that stored the city somewhere of its own would give the
 * product two answers to the same question.
 *
 * **The choices are the catalog's, not a list written here.** `GET /api/public/cities`
 * answers "which places may a reader pick?" — a static question about the curated
 * catalog, and it answers it the same whether that city has a thousand ingested events or
 * none. **A reader in Chittagong may pick Chittagong before anything has ever been
 * collected there**; finding the events is the provisioning service's job.
 *
 * **Not the preview's list.** `GET /api/public/preview/cities` answers a different
 * question — "which cities can the Pulse Preview serve *right now*?" — computed from
 * `EventFit` rows and true only while those events are upcoming. **A picker built from
 * it is a mirror of what we happen to have**, and a reader in a city we have not collected
 * for yet would not be offered their own city. The preview keeps its own list; the picker
 * reads the catalog.
 *
 * **Each choice is a pair, and the two halves are different strings on purpose.**
 * `value` is what a preference holds — "Portland, OR" — and `label` is what a reader
 * reads — "Portland, Oregon". The reader sees the label; the server stores the value.
 *
 * **`city_source` comes back with the city, and it matters.** A city the catalog fell back
 * to is not a city the user picked, and the control says which it is rather than passing a
 * fallback off as a choice.
 *
 * **This module is server-only.** It reaches `sessionHeaders()`, and so `next/headers`.
 */

/** The stored digest preference: the city, how it was arrived at, and the schedule. */
export type DigestPreferenceOut = components["schemas"]["DigestPreferenceOut"];

/**
 * One pickable city: what gets stored, and what the reader reads.
 *
 * **The generated contract's own type (AD-19).** The control reaches for `choice.value`
 * and `choice.label`, and a shape that drifted from the endpoint's would be a compile
 * error here rather than `undefined` at runtime.
 */
export type CityChoice = components["schemas"]["CityChoiceOut"];

/** What the settings screen needs to render the city control. */
export type HomeCityRead =
  | {
      kind: "found";
      /** The stored city, or `null` when the user has none. */
      city: string | null;
      /** `geo` | `choice` | `fallback` | `backfill`, or `null` with no city. */
      citySource: string | null;
      /**
       * The delivery time and zone, carried so a city change can send them back unchanged.
       *
       * `PUT /onboarding/digest-preference` requires both — "a wall clock without its zone
       * is not a schedule" — and this control changes neither.
       */
      deliveryTime: string;
      timezone: string;
      /**
       * The cities the catalog offers, alphabetical by the label a reader sees.
       *
       * **One entry per city, and the pairs are the catalog's own** — the value is what
       * gets stored, the label is what gets read.
       */
      choices: CityChoice[];
    }
  | { kind: "unavailable" };

/** The server's defaults when the user never finished the digest step. */
const FALLBACK_DELIVERY_TIME = "09:00:00";
const FALLBACK_TIMEZONE = "UTC";

/**
 * The home city and its choices, or `unavailable`.
 *
 * **Two requests, not one**, because they answer different questions and only one of them
 * is about this user. The city list is public and sessionless; the preference is the
 * caller's own. Folding them into one endpoint would make a public list need a session.
 *
 * **A failure is never an empty city.** Rendering "no city set" because the API blinked
 * would invite the user to fix something that is not broken — the same lie `readBrowse`
 * refuses to tell about an empty city.
 */
export async function readHomeCity(): Promise<HomeCityRead> {
  if (!apiBaseUrl()) return { kind: "unavailable" };

  try {
    const headers = await sessionHeaders();
    const [state, cities] = await Promise.all([
      api.GET("/api/personal/onboarding", { headers }),
      api.GET("/api/public/cities", {}),
    ]);
    if (!state.data || !cities.data) return { kind: "unavailable" };

    const digest: DigestPreferenceOut = state.data.digest;
    return {
      kind: "found",
      city: digest.city ?? null,
      citySource: digest.city_source ?? null,
      deliveryTime: digest.delivery_time ?? FALLBACK_DELIVERY_TIME,
      timezone: digest.timezone ?? FALLBACK_TIMEZONE,
      choices: cities.data.cities,
    };
  } catch {
    return { kind: "unavailable" };
  }
}
