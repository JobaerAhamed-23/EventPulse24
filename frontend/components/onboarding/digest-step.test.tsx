import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DigestStep, initialDigestValues } from "@/components/onboarding/digest-step";

/**
 * Step 3 — the delivery time and the zone it is a time in.
 *
 * The pair is meaningless apart: `DigestPreferenceIn` says "09:00" means nine in the
 * morning *where the user is*. So the zone defaults to the browser's own, through the
 * same helpers the personal-event form uses.
 */

function renderStep(values = { deliveryTime: "08:00", timezone: "UTC" }) {
  const onChange = vi.fn();
  render(<DigestStep values={values} onChange={onChange} />);
  return onChange;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DigestStep", () => {
  it("offers one labelled time control", () => {
    renderStep();

    const time = screen.getByLabelText("Pulse Digest delivery time");
    expect(time).toHaveAttribute("type", "time");
    expect(time).toHaveValue("08:00");
  });

  it("reports a typed time", () => {
    const onChange = renderStep();

    fireEvent.change(screen.getByLabelText("Pulse Digest delivery time"), {
      target: { value: "07:30" },
    });

    expect(onChange).toHaveBeenCalledWith({ deliveryTime: "07:30", timezone: "UTC" });
  });

  it("sets the time from a preset", () => {
    const onChange = renderStep();

    fireEvent.click(screen.getByRole("button", { name: "18:00" }));

    expect(onChange).toHaveBeenCalledWith({ deliveryTime: "18:00", timezone: "UTC" });
  });

  it("marks the preset that matches the current time", () => {
    renderStep();

    expect(screen.getByRole("button", { name: "08:00" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "07:00" })).toHaveAttribute("aria-pressed", "false");
  });

  it("reports a chosen zone", () => {
    const onChange = renderStep();

    fireEvent.change(screen.getByLabelText("Timezone"), {
      target: { value: "America/New_York" },
    });

    expect(onChange).toHaveBeenCalledWith({
      deliveryTime: "08:00",
      timezone: "America/New_York",
    });
  });

  it("shows the error the API gave, on the time field", () => {
    render(
      <DigestStep
        values={{ deliveryTime: "08:00", timezone: "UTC" }}
        onChange={vi.fn()}
        error="Some details need another look."
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Some details need another look.");
    expect(screen.getByLabelText("Pulse Digest delivery time")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });
});

describe("initialDigestValues", () => {
  it("defaults to the browser's own zone", () => {
    // `browserZone()` reads Intl's resolved zone and keeps it only if it is one of the
    // zones the app offers.
    vi.stubGlobal("Intl", {
      ...Intl,
      DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: "America/Chicago" }) }),
    });

    expect(initialDigestValues({}).timezone).toBe("America/Chicago");
  });

  it("falls back to UTC when the browser's zone is not one we offer", () => {
    vi.stubGlobal("Intl", {
      ...Intl,
      DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: "Mars/Olympus" }) }),
    });

    expect(initialDigestValues({}).timezone).toBe("UTC");
  });

  it("prefers what the user has already stored", () => {
    expect(initialDigestValues({ delivery_time: "19:45:00", timezone: "Europe/Berlin" })).toEqual({
      deliveryTime: "19:45",
      timezone: "Europe/Berlin",
    });
  });

  it("trims a stored time to the minutes the control takes", () => {
    // The API stores a `time`, which arrives as `HH:MM:SS`; the input takes `HH:MM`.
    expect(initialDigestValues({ delivery_time: "09:00:00" }).deliveryTime).toBe("09:00");
  });
});
