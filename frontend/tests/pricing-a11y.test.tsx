/**
 * The pricing page's **axe-core gate**.
 *
 * **`/pricing` — the public screen that sells the plan** (FR-48).
 *
 * **"axe-core reports zero serious or critical violations on this surface."** Every
 * surface in this project carries one axe gate, and the pricing page is a *new public
 * surface* — a stranger lands on it from a search result — so it carries one too.
 *
 * **The gate runs over every state, not just the happy one.** This page has three
 * visitor states, and they are three different documents:
 *
 * - the **signed-out** state (a link to sign-in, no buy button),
 * - the **Free** state (the buy button, the annual/monthly radio group), and
 * - the **Pro** state (the portal button, and no second buy button).
 *
 * The Free and the Pro states are the easy ones to forget to audit separately: the Pro
 * state swaps a button for a link, and a swapped control is exactly where an accessible
 * name or a focus order goes wrong.
 *
 * **Serious and critical only.** `minor` and `moderate` findings are advisory, and a
 * gate that fails on a moderate finding is a gate that gets disabled.
 *
 * **`color-contrast` is disabled explicitly.** jsdom computes no layout, so axe has no
 * boxes to compare and the rule reports false positives rather than findings. The
 * contrast requirement belongs to a real browser — and to `tests/contrast.test.ts`,
 * which checks the tokens themselves.
 */
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";

import { PricingPage } from "@/components/pricing/pricing-page";

vi.mock("@/lib/backend-client", () => ({
  api: { POST: vi.fn() },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

/**
 * Run axe over the rendered page.
 *
 * **The container is the whole document.** axe walks the DOM it is given, so auditing
 * the screen alone would miss the shell — the topbar's landmark, the footer's nav, the
 * account links' accessible names — and those are part of the surface.
 */
async function audit() {
  const results = await axe.run(document.body, {
    resultTypes: ["violations"],
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
}

/** The violations, in a form a failure message can read. */
function describeViolations(violations: Awaited<ReturnType<typeof audit>>) {
  return violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(", ")}`);
}

describe("the pricing page's axe-core gate", () => {
  it("has zero serious or critical violations in the signed-out state", async () => {
    render(<PricingPage tier="signed-out" />);

    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations in the Free state", async () => {
    render(<PricingPage tier="free" />);

    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations in the Pro state", async () => {
    // **A different document, not the Free one with a button changed.** The Pro card's
    // buy button is replaced by the portal button, so this is its own audit.
    render(<PricingPage tier="pro" />);

    expect(describeViolations(await audit())).toEqual([]);
  });

  it("has zero serious or critical violations with the annual option chosen", async () => {
    // **The radio group swaps the price text**, and the price is a live region — a
    // swapped price can leave the announcement stale.
    render(<PricingPage tier="free" />);

    const annual = screen.getByRole("radio", { name: /Annual/ });
    annual.click();

    expect(describeViolations(await audit())).toEqual([]);
  });

  it("audits a document with the real landmarks in place", async () => {
    // A gate that passed because the page rendered nothing would pass forever. The
    // audit is only meaningful if it ran over the real surface.
    render(<PricingPage tier="free" />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Two ways to keep calm." }),
    ).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "Billing cycle" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue to checkout →" })).toBeInTheDocument();
  });

  it("can fail, so the passes above mean something", async () => {
    // **A gate that cannot fail is a gate that has been switched off.**
    //
    // The mutation here is the one this page is most likely to develop: **the feature
    // list's `<li>`s replaced by `<div>`s.** Both cards carry a `<ul>` of features, and a
    // future edit that swaps the element — for a layout reason, with no thought to the
    // semantics — silently breaks the list. A screen reader would announce the features
    // as ungrouped text, and the count of them would be lost with it.
    //
    // **The `list` rule is serious**, so the gate's own filter catches it — which is
    // exactly what this test is checking.
    render(
      <ul>
        <div>a feature</div>
      </ul>,
    );

    const ids = (await audit()).map((violation) => violation.id);

    expect(ids).toContain("list");
  });
});
