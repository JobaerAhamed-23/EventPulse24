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
 * `GET /api/public/cities` answers *"which places may a reader pick?"* — a static
 * question about the curated catalog, and it answers it the same whether that city has a
 * thousand ingested events or none. **A reader in Chittagong may pick Chittagong before
 * anything has ever been collected there**; finding the events is the provisioning
 * service's job, and saying so honestly while it tries is the Browse states' job.
 *
 * **Not the preview's list.** `GET /api/public/preview/cities` answers a different
 * question — "which cities can the Pulse Preview serve *right now*?" — and is computed
 * from the events that exist. A picker built from it is a mirror of what we happen to
 * have, and a reader in a city we have not collected for yet would not be offered their
 * own city.
 *
 * ## The reader sees a label; the server stores a value
 *
 * Each choice is a pair, and **the two halves are different strings on purpose**.
 * `"Portland, Oregon"` is what a reader reads; `"Portland, OR"` is what a preference
 * holds and what `split_region` understands. A native `<select>` already does exactly
 * this — the option's *text* is what is read and the option's *value* is what is
 * submitted — so the control renders one and lets the browser do the rest.
 *
 * ## And it is still a select rather than a text box
 *
 * **The reason changed, and the docstring had to change with it.** The old one said a
 * text box would "quietly store somewhere else", because the server replaced a city it
 * could not serve with a fallback, silently. **That is no longer true of a chosen
 * city**: a city outside the catalog is now *refused* (422), not quietly substituted.
 *
 * **So the real reason is the catalog's size and the catalog's canonical spellings.**
 * There are a hundred and sixty-odd pickable places, and a native `<select>` gives the
 * platform's own type-ahead and the mobile picker's own wheel for free. A text box would
 * offer neither, and would add a second job — resolving what the reader typed into
 * something we hold. A reader who writes "chitagong" gets a refusal; a picker shows them
 * the spelling we do hold.
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
 *
 * **The fallback is still live** — only a *chosen* city outside the catalog is refused.
 * A geo guess and a backfill still fall back, and their accounts still carry one.
 */
import { useCallback, useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { SaveFeedback } from "@/components/settings/save-feedback";
import { SettingRow } from "@/components/settings/setting-row";
import { api } from "@/lib/backend-client";
import type { CityChoice } from "@/lib/home-city-read";

export type HomeCityProps = {
  /** The stored city, or `null` when the user has none. */
  initialCity: string | null;
  /** How the stored city was arrived at: `geo` | `choice` | `fallback` | `backfill`. */
  initialCitySource: string | null;
  /**
   * The cities the catalog offers, alphabetical by the label a reader sees.
   *
   * **Each is a pair: the `value` to store, the `label` to show.**
   */
  choices: CityChoice[];
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
  //
  // **The stored city is matched by *value*.** The catalog's two strings are different on
  // purpose — "Portland, Oregon" is read, "Portland, OR" is stored — so the question is
  // "does some choice's value equal the stored city", never "does some choice's label".
  //
  // **And a stored city the catalog no longer holds has no label of its own.** So the
  // option synthesised for it shows the stored city as its own label: there is nothing
  // better to show, because we do not know what it is, and inventing a disambiguating
  // form for a city we do not hold would be a fabrication.
  const stored = city === null ? null : choices.find((choice) => choice.value === city);
  const options: CityChoice[] =
    city === null || stored !== undefined ? choices : [{ value: city, label: city }, ...choices];

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
            {/*
              **The text is the label and the value is the catalog's own.**
              A native `<select>` shows the option's text and submits its value — so the
              reader reads "Portland, Oregon" and the server stores "Portland, OR", with
              nothing here translating between them.
            */}
            {options.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </select>

          <SaveFeedback busy={busy} saved={saved} failure={failure} />
        </span>
      }
    />
  );
}
