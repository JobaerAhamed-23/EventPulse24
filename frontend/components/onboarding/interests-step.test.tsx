import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InterestsStep, nextSelection } from "@/components/onboarding/interests-step";

/**
 * Step 2 — the chips, and the cap of three.
 *
 * The chips are the API's, not this component's: `shared/constants.py` holds the ten, and
 * the endpoint projects them. The mockup draws twelve, two of which do not exist in that
 * set, so a hard-coded list here would be a second copy that disagrees with the database.
 */

const CHIPS = [
  { key: "tech_meetups", label: "Tech & meetups" },
  { key: "sports_fitness", label: "Sports & fitness" },
  { key: "arts_culture", label: "Arts & culture" },
  { key: "family_kids", label: "Family & kids" },
  { key: "community_volunteering", label: "Community & volunteering" },
];

function renderStep(picked: string[] = []) {
  const onChange = vi.fn();
  render(<InterestsStep chips={CHIPS} picked={picked} onChange={onChange} />);
  return onChange;
}

const chip = (label: string) => screen.getByRole("button", { name: new RegExp(label) });

describe("the cap rule", () => {
  // The rule, driven directly. The chips' `disabled` attribute is tested below, but a
  // disabled button swallows the click — so a test that clicks one proves the attribute
  // and nothing about the rule behind it.
  it("refuses a fourth pick", () => {
    expect(nextSelection(["a", "b", "c"], "d")).toEqual(["a", "b", "c"]);
  });

  it("adds a pick below the cap", () => {
    expect(nextSelection(["a"], "b")).toEqual(["a", "b"]);
  });

  it("always allows unpicking, even at the cap", () => {
    expect(nextSelection(["a", "b", "c"], "b")).toEqual(["a", "c"]);
  });

  it("never adds the same key twice", () => {
    expect(nextSelection(["a"], "a")).toEqual([]);
  });
});

describe("InterestsStep", () => {
  it("renders the chips the API gave it, and nothing else", () => {
    renderStep();

    expect(screen.getAllByRole("button")).toHaveLength(CHIPS.length);
    // The mockup's extra chips are not in the locked ten and must not appear from here.
    expect(screen.queryByRole("button", { name: /^Music/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Food & dining/ })).toBeNull();
  });

  it("toggles a pick, and says so through aria-pressed", () => {
    const onChange = renderStep();

    expect(chip("Tech & meetups")).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(chip("Tech & meetups"));

    expect(chip("Tech & meetups")).toHaveAttribute("aria-pressed", "true");
    expect(onChange).toHaveBeenLastCalledWith(["tech_meetups"]);
  });

  it("unpicks a chosen chip", () => {
    const onChange = renderStep(["tech_meetups"]);

    fireEvent.click(chip("Tech & meetups"));

    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("reports the picks by key, never by label", () => {
    const onChange = renderStep();

    fireEvent.click(chip("Community & volunteering"));

    expect(onChange).toHaveBeenLastCalledWith(["community_volunteering"]);
  });

  it("stops at three picks", () => {
    // FR-1 allows three. The API refuses a fourth; the UI makes it unreachable so the
    // refusal is never the way a user finds out.
    const onChange = renderStep(["tech_meetups", "sports_fitness", "arts_culture"]);

    expect(chip("Family & kids")).toBeDisabled();
    expect(chip("Family & kids")).toHaveAttribute("aria-disabled", "true");

    fireEvent.click(chip("Family & kids"));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("says why the rest are closed, and frees them when one is unpicked", () => {
    renderStep(["tech_meetups", "sports_fitness", "arts_culture"]);

    expect(screen.getByRole("status")).toHaveTextContent("That's three — unpick one to change it.");

    fireEvent.click(chip("Tech & meetups"));

    expect(chip("Family & kids")).not.toBeDisabled();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("keeps a chosen chip clickable at the cap, so a pick can be swapped", () => {
    renderStep(["tech_meetups", "sports_fitness", "arts_culture"]);

    expect(chip("Arts & culture")).not.toBeDisabled();
  });

  it("stays skippable when the chips could not be read", () => {
    render(<InterestsStep chips={[]} picked={[]} onChange={vi.fn()} />);

    expect(screen.getByText(/couldn't load the interests/)).toBeInTheDocument();
  });
});
