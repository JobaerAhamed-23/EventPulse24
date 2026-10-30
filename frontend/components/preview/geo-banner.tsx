"use client";

/**
 * The geo-IP consent banner (FR-2).
 *
 * The locked sentence and the three actions: *"Showing events near [city]. Use a
 * different city? [Change] [Use this] [Don't use my location]."*
 *
 * **"Don't use my location" is not just a dismissal.** It sends the opt-out, so the next
 * request carries `use_geo=false` and the backend does not consult the location header at
 * all — "never consulted" is a property that can be checked, while "consulted and
 * ignored" is a promise nobody can see kept. The preview then falls back to NYC, and the
 * banner does not come back this session.
 *
 * It is a labelled region with real buttons, so it is reachable and announced; it renders
 * only once the city is known, because it has to name it.
 */

import { useState } from "react";

export type GeoBannerProps = {
  /** The city the preview resolved to — the banner names it. */
  city: string;
  /** The cities the picker offers, read when "Change" is tapped. */
  cities: string[];
  /** Whether the city list is being read. */
  loadingCities: boolean;
  onUseThis: () => void;
  onChange: () => void;
  onPickCity: (city: string) => void;
  onOptOut: () => void;
};

export function GeoBanner({
  city,
  cities,
  loadingCities,
  onUseThis,
  onChange,
  onPickCity,
  onOptOut,
}: GeoBannerProps) {
  const [picking, setPicking] = useState(false);

  return (
    <section
      aria-label="Location consent"
      className="border-b border-border-subtle bg-surface-subtle px-6 py-3"
    >
      <div className="mx-auto flex max-w-(--layout-container-max) flex-wrap items-center justify-between gap-3">
        <p className="[font:var(--type-scale-body-sm)] text-ink-secondary">
          <span aria-hidden="true" className="mr-2 text-accent-terracotta">
            ●
          </span>
          Showing events near <strong className="text-ink-primary">{city}</strong>. Use a different
          city?
        </p>
        <div className="flex flex-wrap items-center gap-4">
          <button
            type="button"
            onClick={onUseThis}
            className="[font:var(--type-scale-meta-md)] text-ink-primary underline underline-offset-4"
          >
            Use this
          </button>
          <button
            type="button"
            onClick={() => {
              setPicking(true);
              onChange();
            }}
            className="[font:var(--type-scale-meta-md)] text-ink-secondary"
          >
            Change
          </button>
          <button
            type="button"
            onClick={onOptOut}
            className="[font:var(--type-scale-body-sm)] text-ink-muted"
          >
            Don&apos;t use my location
          </button>
        </div>
      </div>

      {picking ? (
        <div className="mx-auto mt-3 max-w-(--layout-container-max)">
          {loadingCities ? (
            <p role="status" className="[font:var(--type-scale-body-sm)] text-ink-muted">
              Loading cities…
            </p>
          ) : cities.length === 0 ? (
            <p className="[font:var(--type-scale-body-sm)] text-ink-muted">
              We couldn&apos;t load the city list. Try again shortly.
            </p>
          ) : (
            <ul aria-label="Choose a city" className="flex flex-wrap gap-2">
              {cities.map((candidate) => (
                <li key={candidate}>
                  <button
                    type="button"
                    onClick={() => onPickCity(candidate)}
                    className="rounded-control border border-border-subtle px-3 py-1.5 [font:var(--type-scale-meta-sm)] text-ink-secondary"
                  >
                    {candidate}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </section>
  );
}
