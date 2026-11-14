/**
 * `Component.Settings.Row` — the mockup's label-left, control-right settings row.
 *
 * It is a layout component, so what is worth pinning is small and structural: the parts
 * it renders, the parts it leaves out, and the hairline rule that keeps a list of rows
 * from opening with a stray line above the first one.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SettingRow } from "@/components/settings/setting-row";

describe("the row", () => {
  it("renders the label, the description and the control", () => {
    render(
      <SettingRow
        label="Personal events"
        description="Personal events are in your Pulse Digest"
        control={<button type="button">Toggle</button>}
      />,
    );

    expect(screen.getByText("Personal events")).toBeInTheDocument();
    expect(screen.getByText("Personal events are in your Pulse Digest")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Toggle" })).toBeInTheDocument();
  });

  it("renders no description element when there is none to render", () => {
    // An empty muted line under the label would be a gap the eye reads as a missing
    // sentence.
    const { container } = render(
      <SettingRow label="Timezone" control={<button type="button">Change</button>} />,
    );

    const labelColumn = container.querySelector("[data-setting-row] span");
    expect(labelColumn?.querySelectorAll("span")).toHaveLength(1);
  });

  it("puts the footer below the row, not beside the control", () => {
    // A save status belongs under the setting it reports on, full width — squeezed in
    // beside the control it would wrap at the first long word.
    render(
      <SettingRow
        label="Personal events"
        control={<button type="button">Toggle</button>}
        footer={<p>Saved.</p>}
      />,
    );

    const row = document.querySelector("[data-setting-row]");
    expect(row?.lastElementChild?.textContent).toBe("Saved.");
  });

  it("carries the hairline on top, so the first row in a list has none", () => {
    // `first:border-t-0` keeps the rule with the row rather than asking every caller to
    // remember which of its children is first.
    const { container } = render(<SettingRow label="Personal events" control={<span>x</span>} />);

    const row = container.querySelector("[data-setting-row]");
    expect(row?.className).toContain("border-t");
    expect(row?.className).toContain("first:border-t-0");
  });
});
