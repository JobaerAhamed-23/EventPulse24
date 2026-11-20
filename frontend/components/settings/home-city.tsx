"use client";

/**
 * `Component.Settings.HomeCity` — the city Browse and the Pulse Digest both read.
 *
 * ## It was unreachable, and a link already promised otherwise
 *
 * Browse's hero carries a "Change city" link, and its own comment says why: *"a control
 * that goes nowhere is a lie about what the page can do."* The link shipped; the control
 * did not. It pointed at `/settings/account`, which had **Plan** and **Your data** and
 * nothing about a city — so the one route the product offers for fixing an empty Browse
 * led to a page that could not fix it.
 *
 * **The control now lives on `/settings/profile`, and the link points there.** Where a
 * person lives is a fact about them rather than about their billing, and it sits beside
 * the zone, which answers the same question.
 *
 * The same link is in Browse's *empty* state, which is where it matters most: a user
 * whose city has nothing on, or who has no city at all, is sent here precisely to change
 * it.
 *
 * ## The choices come from the catalog, not from a list written here
 *
 * `GET /api/public/preview/cities` is derived from the events that exist — a city is
 * offered when the catalog has an upcoming public event with an Event Fit for it. A
 * hard-coded list would offer cities Browse then comes back empty for, which is the
 * failure this control exists to end rather than to reproduce.
 *
 * **And it is why this is a select rather than a text box.** The server replaces a city
 * it cannot serve with a fallback (FR-2), silently — so typing "Chittagong" would appear
 * to work and quietly store somewhere else. A picker cannot express the request that
 * would be mishandled.
 *
 * ## The schedule rides along unchanged
 *
 * `PUT /onboarding/digest-preference` takes `delivery_time` and `timezone` as required
 * fields — *"a wall clock without its zone is not a schedule"* — and this control changes
 * neither. It sends back exactly what it was handed, the mirror image of what
 * `DigestTimezone` does with the delivery time it does not own.
 *
 * ## A fallback city is labelled as one
 *
 * `city_source` exists so that *"a fallback the user did not pick must be labelled as
 * one, not passed off as their city"*. A user whose city reads `fallback` is told the
 * catalog chose it, so an unexpected city is explained rather than merely wrong.
 */
import { useCallback, useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { SaveFeedback } from "@/components/settings/save-feedback";
import { SettingRow } from "@/components/settings/setting-row";
import { api } from "@/lib/backend-client";

export type HomeCityProps = {
  /** The stored city, or `null` when the user has none. */
  initialCity: string | null;
  /** How the stored city was arrived at: `geo` | `choice` | `fallback` | `backfill`. */
  initialCitySource: string | null;
  /** The cities the catalog can serve. One entry per city, already alphabetical. */
  choices: string[];
  /** The stored delivery time, sent back unchanged — the server requires it. */
  deliveryTime: string;
  /** The stored zone, sent back unchanged — the server requires it. */
  timezone: string;
};

/** The offline failure line. The same shape the other settings controls use. */
const FAILURE = "Couldn't save.";

/**
 * The value the select carries when the user has no city.
 *
 * **An empty string, and it is never submitted.** `PUT /onboarding/digest-preference`
 * reads a `null` city as "leave it alone" and *cannot clear* — so there is no request
 * this control could send that would mean "no city". The placeholder therefore exists to
 * be replaced, and `save` ignores it.
 */
const NO_CITY = "";

/** What to say under the row, given where the stored city came from. */
export function citySourceNote(city: string | null, source: string | null): string {
  if (city === null) return "Browse and your Pulse Digest both use this city.";
  if (source === "fallback") {
    return `We don't have your city yet, so we're showing ${city}. Pick yours below.`;
  }
  if (source === "geo") {
    return `Guessed from your connection. Browse and your Pulse Digest both use this city.`;
  }
  return "Browse and your Pulse Digest both use this city.";
}

export function HomeCity({
  initialCity,
  initialCitySource,
  choices,
  deliveryTime,
  timezone,
}: HomeCityProps) {
  const [city, setCity] = useState<string | null>(initialCity);
  const [source, setSource] = useState<string | null>(initialCitySource);
  const [busy, setBusy] = useState(false);
  /** The message, not a flag — so the API's own refusal can be shown verbatim. */
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const save = useCallback(
    async (next: string) => {
      // The placeholder is not a city. See `NO_CITY`.
      if (next === NO_CITY) return;

      const previous = city;
      const previousSource = source;
      // **Optimistic, and reverted on failure** — the same bargain `DigestTimezone`
      // makes. A select that springs back while the request is in flight reads as a
      // control that rejected the choice.
      setCity(next);
      setBusy(true);
      setFailure(null);
      setSaved(false);
      try {
        const response = await api.PUT("/api/personal/onboarding/digest-preference", {
          body: { city: next, delivery_time: deliveryTime, timezone },
        });
        if (response.error) {
          setFailure(saveFailureMessage(response.error, FAILURE));
          setCity(previous);
          setSource(previousSource);
          return;
        }
        if (!response.data) {
          setFailure(FAILURE);
          setCity(previous);
          setSource(previousSource);
          return;
        }
        // **The server's answer replaces the client's guess** (AD-10). It matters here
        // more than elsewhere: the server may have stored a *different* city from the
        // one sent, and `city_source` is how it says so.
        // The endpoint answers with the whole onboarding state, so the preference it
        // actually stored is under `digest` — not at the top level.
        setCity(response.data.digest.city ?? null);
        setSource(response.data.digest.city_source ?? null);
        setSaved(true);
      } catch {
        // The request never reached the API, so there is nothing to quote.
        setFailure(FAILURE);
        setCity(previous);
        setSource(previousSource);
      } finally {
        setBusy(false);
      }
    },
    [city, source, deliveryTime, timezone],
  );

  // **The stored city is always an option, even when the catalog stopped serving it.** A
  // select whose value is absent from its options renders as blank, which would read as
  // "no city" for a user who has one.
  const options = choices.includes(city ?? "") || city === null ? choices : [city, ...choices];

  return (
    <SettingRow
      label="City"
      description={citySourceNote(city, source)}
      control={
        <span className="flex items-center gap-3">
          {/*
            **`aria-label`, not a second `<label>`.** The row already shows the word
            "City" beside the control, and a second element with that name would be read
            out twice.
          */}
          <select
            aria-label="City"
            value={city ?? NO_CITY}
            disabled={busy}
            onChange={(event) => {
              void save(event.target.value);
            }}
            data-home-city-select
            className="min-h-[44px] rounded-control border border-border-subtle bg-surface-subtle px-3 text-ink-primary [font:var(--type-scale-meta-md)] disabled:opacity-60"
          >
            {/*
              **The placeholder appears only when there is nothing to show.** Leaving it
              in the list once a city is set would offer "Choose a city" as a choice that
              this endpoint cannot carry out.
            */}
            {city === null ? <option value={NO_CITY}>Choose a city</option> : null}
            {options.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>

          <SaveFeedback busy={busy} saved={saved} failure={failure} />
        </span>
      }
    />
  );
}
