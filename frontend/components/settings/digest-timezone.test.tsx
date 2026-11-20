/**
 * `Component.Settings.Timezone` — the control that restores a setting nobody could reach.
 *
 * The zone was written once by onboarding, defaulted to `UTC` for anyone who skipped that
 * step, and then sent back unchanged forever by `DigestDeliveryTime`. It decides which
 * day the digest composes for, when quiet hours fall, and which week the timeline draws —
 * so an account on the wrong zone was wrong in three places with nothing on screen to say
 * so.
 *
 * What is pinned here: the zone is **shown**, it is **changeable**, the delivery time
 * rides along unchanged (the server takes both or neither), and a refusal puts the old
 * zone back rather than leaving a select that lies.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DigestTimezone } from "@/components/settings/digest-timezone";

const PUT = vi.fn();
const browserZone = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

/**
 * **The device's zone is mocked, and it has to be.**
 *
 * `browserZone()` reads `Intl.DateTimeFormat().resolvedOptions().timeZone`, which is the
 * zone of whatever machine the suite runs on — `Asia/Dhaka` on the machine this was
 * written on, `UTC` in CI. A test that asserted "the offer appears" against the real one
 * would pass or fail depending on where the developer is sitting, which is not a property
 * of the code. `ZONE_CHOICES` stays real, because it is a constant.
 */
vi.mock("@/lib/timezones", async () => {
  const actual = await vi.importActual<typeof import("@/lib/timezones")>("@/lib/timezones");
  return { ...actual, browserZone: () => browserZone() };
});

function answer(timezone: string, delivery_time = "09:00:00") {
  return { data: { digest: { delivery_time, timezone } }, error: null };
}

beforeEach(() => {
  PUT.mockReset();
  browserZone.mockReset();
  PUT.mockResolvedValue(answer("Asia/Dhaka"));
  // No device zone by default: the offer is a separate concern from everything above it.
  browserZone.mockReturnValue(null);
});

function renderControl(zone = "UTC", deliveryTime = "09:00:00") {
  render(<DigestTimezone initialTimezone={zone} deliveryTime={deliveryTime} />);
  return screen.getByRole("combobox", { name: "Timezone" });
}

describe("showing the zone", () => {
  it("shows the stored zone, which nothing else in the product did", () => {
    const select = renderControl("Asia/Dhaka");

    expect(select).toHaveValue("Asia/Dhaka");
  });

  it("names the settings that are read in this zone", () => {
    // **It used to say "everything below", and that was a claim about the page.** The
    // control opened `/settings/general`, with the quiet window and the digest beneath
    // it. It now sits on `/settings/profile` under the city, where there is nothing
    // below it at all — so it names the settings the zone governs instead of pointing
    // down the page at them.
    renderControl("UTC");

    expect(
      screen.getByText(/Your Pulse Digest, quiet hours and timeline are read in this zone/i),
    ).toBeInTheDocument();
  });

  it("shows the zone's current offset, computed rather than stored", () => {
    // An offset moves with daylight saving, so storing one would store something that
    // goes stale twice a year.
    renderControl("Asia/Dhaka");

    expect(screen.getByText(/Currently GMT\+6/)).toBeInTheDocument();
  });

  it("keeps a stored zone that is not on the curated list", () => {
    // The backend accepts more zones than the form offers. A select that dropped the
    // user's own zone would show them somebody else's and save it on the next change.
    const select = renderControl("Antarctica/Troll");

    expect(select).toHaveValue("Antarctica/Troll");
    expect(screen.getByRole("option", { name: "Antarctica/Troll" })).toBeInTheDocument();
  });
});

describe("changing the zone", () => {
  it("sends the new zone with the delivery time unchanged", async () => {
    // **Both or neither**: `DigestScheduleIn` refuses a zone without a time. And the
    // time is unchanged because the clock is what is being kept — 09:00 stays 09:00.
    const select = renderControl("UTC", "09:00:00");

    fireEvent.change(select, { target: { value: "Asia/Dhaka" } });

    await waitFor(() =>
      expect(PUT).toHaveBeenCalledWith("/api/settings/notifications", {
        body: { digest: { delivery_time: "09:00:00", timezone: "Asia/Dhaka" } },
      }),
    );
  });

  it("takes the server's answer, not the user's choice", async () => {
    // AD-10: the state is the server's fact. If it resolved the zone differently, the
    // select shows what was stored.
    PUT.mockResolvedValue(answer("Asia/Kolkata"));
    const select = renderControl("UTC");

    fireEvent.change(select, { target: { value: "Asia/Dhaka" } });

    await waitFor(() => expect(select).toHaveValue("Asia/Kolkata"));
  });

  it("puts the old zone back when the server refuses", async () => {
    // A select left showing a zone that was not saved is a control that lies about the
    // account — and the next change would send the wrong delivery time with it.
    PUT.mockResolvedValue({ error: { code: "invalid_timezone", message: "Not a zone." } });
    const select = renderControl("UTC");

    fireEvent.change(select, { target: { value: "Asia/Dhaka" } });

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Not a zone."));
    expect(select).toHaveValue("UTC");
  });

  it("puts the old zone back when the request never leaves", async () => {
    PUT.mockRejectedValue(new Error("offline"));
    const select = renderControl("UTC");

    fireEvent.change(select, { target: { value: "Asia/Dhaka" } });

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Couldn't save."));
    expect(select).toHaveValue("UTC");
  });
});

describe("the device's own zone", () => {
  it("is offered when it differs from the stored one", () => {
    browserZone.mockReturnValue("Asia/Dhaka");

    renderControl("UTC");

    expect(screen.getByRole("button", { name: "Use it" })).toBeInTheDocument();
  });

  it("is not offered when it already matches", () => {
    // A button that would change nothing teaches the user to distrust the others.
    browserZone.mockReturnValue("UTC");

    renderControl("UTC");

    expect(screen.queryByRole("button", { name: "Use it" })).toBeNull();
  });

  it("saves the device's zone when taken", async () => {
    browserZone.mockReturnValue("Asia/Dhaka");
    PUT.mockResolvedValue(answer("Asia/Dhaka"));
    renderControl("UTC");

    fireEvent.click(screen.getByRole("button", { name: "Use it" }));

    await waitFor(() =>
      expect(PUT).toHaveBeenCalledWith("/api/settings/notifications", {
        body: { digest: { delivery_time: "09:00:00", timezone: "Asia/Dhaka" } },
      }),
    );
  });

  it("is not offered when the device's zone is not one we accept", () => {
    // `browserZone` answers null for a zone outside `ZONE_CHOICES`. Offering it would
    // offer a value the server refuses.
    browserZone.mockReturnValue(null);

    renderControl("UTC");

    expect(screen.queryByRole("button", { name: "Use it" })).toBeNull();
  });
});
