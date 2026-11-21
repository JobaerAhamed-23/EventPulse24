/**
 * `PlaceSettings` — the city and the zone, sharing one zone.
 *
 * **The thing worth testing here is not either control.** Both have their own tests, and
 * both pass whichever value they are handed. What this component exists for is the
 * **coupling**: `HomeCity` posts `timezone` back unchanged with every city change, so on
 * a screen that also edits the zone, the city can silently undo a zone change.
 *
 * So every test below reads the **city's request body**, which is the only place the bug
 * would ever have shown itself.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PlaceSettings } from "@/components/settings/place-settings";

const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

const CITY_ROUTE = "/api/personal/onboarding/digest-preference";
const ZONE_ROUTE = "/api/settings/notifications";

/** The body the city control sent, or `undefined` if it never sent one. */
function cityBody(): Record<string, unknown> | undefined {
  const call = PUT.mock.calls.find(([route]) => route === CITY_ROUTE);
  return call?.[1]?.body as Record<string, unknown> | undefined;
}

function renderPlace() {
  return render(
    <PlaceSettings
      initialCity="Dhaka"
      initialCitySource="choice"
      choices={[
        { value: "Chattogram, Bangladesh", label: "Chattogram, Bangladesh" },
        { value: "Dhaka", label: "Dhaka, Bangladesh" },
      ]}
      deliveryTime="09:00:00"
      initialTimezone="America/New_York"
    />,
  );
}

/** Change the zone, and wait for the control to settle on what it now holds. */
async function pickZone(value: string, settlesOn: string) {
  fireEvent.change(screen.getByRole("combobox", { name: "Timezone" }), { target: { value } });
  await waitFor(() => {
    expect(screen.getByRole("combobox", { name: "Timezone" })).toHaveValue(settlesOn);
  });
}

/** Change the city, and wait for its request to have gone out. */
async function pickCity(value: string) {
  fireEvent.change(screen.getByRole("combobox", { name: "City" }), { target: { value } });
  await waitFor(() => expect(cityBody()).toBeDefined());
}

beforeEach(() => {
  PUT.mockReset();
  PUT.mockImplementation(
    async (route: string, options: { body: { city?: string; digest?: { timezone: string } } }) => {
      if (route === ZONE_ROUTE) {
        // **The server echoes what it was sent**, which is what the real one does with a
        // zone it accepts. The test below that matters most replaces this with one that
        // answers something else.
        return { data: { digest: { timezone: options.body.digest?.timezone } } };
      }
      return { data: { digest: { city: options.body.city, city_source: "choice" } } };
    },
  );
});

describe("the zone the city control sends", () => {
  it("is the zone the account was rendered with, when nothing changed it", async () => {
    renderPlace();

    await pickCity("Chattogram, Bangladesh");

    expect(cityBody()).toEqual({
      city: "Chattogram, Bangladesh",
      delivery_time: "09:00:00",
      timezone: "America/New_York",
    });
  });

  it("is the new zone, when the zone was changed first", async () => {
    /**
     * **The bug this component exists to prevent.** With a server-rendered copy, this
     * body would carry `America/New_York` — and the server would take it, undoing a save
     * the user had just watched succeed.
     */
    renderPlace();

    await pickZone("Asia/Dhaka", "Asia/Dhaka");
    await pickCity("Chattogram, Bangladesh");

    expect(cityBody()?.timezone).toBe("Asia/Dhaka");
  });

  it("is the zone the server stored, not the one the user picked", async () => {
    // **AD-10: the server's answer replaces the client's guess** — and the guess is what
    // a naive shared value would propagate.
    PUT.mockImplementation(async (route: string) => {
      if (route === ZONE_ROUTE) return { data: { digest: { timezone: "Europe/London" } } };
      return { data: { digest: { city: "Chattogram, Bangladesh", city_source: "choice" } } };
    });

    renderPlace();

    await pickZone("Asia/Dhaka", "Europe/London");
    await pickCity("Chattogram, Bangladesh");

    expect(cityBody()?.timezone).toBe("Europe/London");
  });

  it("is the old zone again, when the zone's save was refused", async () => {
    /**
     * **The revert has to travel too.** The zone control puts itself back on a refusal;
     * a city change that still carried the refused zone would store the very value the
     * server had just rejected — through a different endpoint, which may well accept it.
     */
    PUT.mockImplementation(async (route: string) => {
      if (route === ZONE_ROUTE) return { error: { detail: "Nope." } };
      return { data: { digest: { city: "Chattogram, Bangladesh", city_source: "choice" } } };
    });

    renderPlace();

    await pickZone("Asia/Dhaka", "America/New_York");
    await pickCity("Chattogram, Bangladesh");

    expect(cityBody()?.timezone).toBe("America/New_York");
  });
});
