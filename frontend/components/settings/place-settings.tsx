"use client";

/**
 * `Component.Settings.PlaceSettings` — **the city and the zone, sharing one zone.**
 *
 * ## Why these two are one component
 *
 * They are two independent controls on `/settings/profile`, and they would be two
 * independent controls here too — except that **one of them sends the other's value**.
 *
 * `HomeCity` posts `city`, `delivery_time` *and* `timezone` on every city change, because
 * `PUT /onboarding/digest-preference` requires the schedule as well: *"a wall clock
 * without its zone is not a schedule"*. The city control does not change the zone, so it
 * sends back the zone it was handed.
 *
 * **On a page that also edits the zone, "the zone it was handed" goes stale.** The page is
 * rendered on the server, so the zone the city control was handed is the zone at render
 * time. A user who changes the zone to `Asia/Dhaka` and *then* picks a city would send
 * `timezone: "America/New_York"` with it — and the server would take it. The zone change
 * would be undone by a control that is not about zones, with a "Saved." under each of
 * them and nothing on screen saying what happened.
 *
 * So the zone lives here, in the one place both controls can see it: `DigestTimezone`
 * reports every zone it comes to hold, and `HomeCity` is handed that value rather than
 * the server-rendered one.
 *
 * **The delivery time needs no such treatment.** Neither control changes it — both send
 * it back unchanged — so there is nothing for it to go stale against. It is edited on
 * `/settings/general`, which is a different render.
 *
 * ## The order: the city, then the zone
 *
 * The city is the one a reader came for — it is the destination of Browse's "Change city"
 * — and the zone is the thing that explains the times they will then read. The headings
 * on the page say the same thing in the same order.
 */
import { useState } from "react";

import { DigestTimezone } from "@/components/settings/digest-timezone";
import { HomeCity } from "@/components/settings/home-city";

export type PlaceSettingsProps = {
  /** The stored city, or `null` when the user has none. */
  initialCity: string | null;
  /** How the stored city was arrived at: `geo` | `choice` | `fallback` | `backfill`. */
  initialCitySource: string | null;
  /** The cities the catalog can serve. One entry per city, already alphabetical. */
  choices: string[];
  /** The stored delivery time. Both controls send it back unchanged. */
  deliveryTime: string;
  /** The stored zone — an IANA name. The zone control owns it from here. */
  initialTimezone: string;
};

export function PlaceSettings({
  initialCity,
  initialCitySource,
  choices,
  deliveryTime,
  initialTimezone,
}: PlaceSettingsProps) {
  // **The zone, held once.** See the module docstring: the city control sends this value
  // back on every city change, so a copy that did not follow the zone control would undo
  // it.
  const [timezone, setTimezone] = useState(initialTimezone);

  return (
    <>
      <HomeCity
        initialCity={initialCity}
        initialCitySource={initialCitySource}
        choices={choices}
        deliveryTime={deliveryTime}
        timezone={timezone}
      />

      <div className="mt-8">
        <DigestTimezone
          initialTimezone={initialTimezone}
          deliveryTime={deliveryTime}
          onTimezoneChange={setTimezone}
        />
      </div>
    </>
  );
}
