/**
 * `Component.Control.Switch` — the mockup's sliding control, with the house's semantics.
 *
 * **The point of contention this component settles** is that
 * `settings-desktop.html` draws `role="switch" aria-checked`, while
 * `digest-personal-events.tsx` and `reminders/reminder-picker.tsx` record a deliberate
 * decision *against* `role="switch"` in favour of `<button aria-pressed>`. These tests
 * pin the resolution: the mockup's pixels, the codebase's markup.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SwitchControl } from "@/components/settings/switch-control";

function renderSwitch(overrides: Partial<Parameters<typeof SwitchControl>[0]> = {}) {
  const onToggle = vi.fn();
  render(
    <SwitchControl checked={false} onToggle={onToggle} label="Personal events" {...overrides} />,
  );
  return { onToggle, button: () => screen.getByRole("button", { name: "Personal events" }) };
}

describe("the markup", () => {
  it("is a button with aria-pressed, not a switch with aria-checked", () => {
    // **The decision this component exists to honour.** A visual refresh must not
    // quietly reverse an accessibility choice somebody wrote down.
    const { button } = renderSwitch({ checked: true });

    expect(button()).toHaveAttribute("aria-pressed", "true");
    expect(button()).not.toHaveAttribute("aria-checked");
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("keeps one accessible name whatever the state", () => {
    // A control renamed by its own state is announced as a *different control* each
    // time it is pressed. The name says what it is; `aria-pressed` says how it is set.
    const { rerender } = render(
      <SwitchControl checked={false} onToggle={vi.fn()} label="Personal events" />,
    );
    expect(screen.getByRole("button", { name: "Personal events" })).toBeInTheDocument();

    rerender(<SwitchControl checked onToggle={vi.fn()} label="Personal events" />);

    expect(screen.getByRole("button", { name: "Personal events" })).toBeInTheDocument();
  });
});

describe("the state", () => {
  it("says which way it is set, in words", () => {
    // WCAG 1.4.1: neither the colour of the track nor the position of the knob can be
    // the only carrier. A reader who has never seen the other position gets a word.
    renderSwitch({ checked: true });

    expect(screen.getByText("On")).toBeInTheDocument();
  });

  it("takes the caller's words when the default two are wrong", () => {
    renderSwitch({ checked: false, stateLabel: { on: "Included", off: "Excluded" } });

    expect(screen.getByText("Excluded")).toBeInTheDocument();
  });

  it("exposes the painted state as data, so a test need not read a colour", () => {
    const { button } = renderSwitch({ checked: true });

    expect(button()).toHaveAttribute("data-state", "on");
  });
});

describe("pressing it", () => {
  it("calls back", () => {
    const { onToggle, button } = renderSwitch();

    fireEvent.click(button());

    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("does nothing while disabled", () => {
    const { onToggle, button } = renderSwitch({ disabled: true });

    fireEvent.click(button());

    expect(button()).toBeDisabled();
    expect(onToggle).not.toHaveBeenCalled();
  });
});

describe("the target", () => {
  it("is at least 44px tall, whatever the track is drawn at", () => {
    // **The track is 22px and the target is 44px**, which is the whole reason the
    // button wraps the track rather than being it. A control that looks right and
    // misses the thumb is a control that does not work.
    const { button } = renderSwitch();

    expect(button().className).toContain("min-h-[44px]");
  });
});
