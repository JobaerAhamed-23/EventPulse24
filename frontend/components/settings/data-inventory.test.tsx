// @vitest-environment jsdom
/**
 * "What we store" — PRD §10.2's data inventory.
 *
 * **The rule this surface exists to keep is that it never restates a retention window.**
 * The windows live in `backend/shared/retention.py`, mirrored by `RETENTION_ROWS` and
 * pinned by `backend/tests/shared/test_retention_published.py`. These tests assert the
 * mirror actually reaches the screen — an import that stopped rendering would otherwise
 * empty this section silently, on the one page a user opens to find out what is true.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataInventory } from "@/components/settings/data-inventory";
import { RETENTION_ROWS } from "@/lib/retention-categories";

describe("the data inventory", () => {
  it("renders every category the registry publishes", () => {
    const { container } = render(<DataInventory />);

    for (const row of RETENTION_ROWS) {
      const item = container.querySelector(`[data-retention-row="${row.key}"]`);
      expect(item, `missing row for ${row.key}`).not.toBeNull();
      expect(within(item as HTMLElement).getByText(row.label)).toBeInTheDocument();
    }

    // The count is asserted too: a row rendering twice, or a stale extra row, is as
    // wrong as a missing one.
    expect(container.querySelectorAll("[data-retention-row]")).toHaveLength(
      RETENTION_ROWS.length,
    );
  });

  it("states a window and a deletion outcome for every category", () => {
    const { container } = render(<DataInventory />);

    // §10.2 asks for "the categories and current retention windows". A category with no
    // window is half an answer.
    for (const row of RETENTION_ROWS) {
      const item = container.querySelector(`[data-retention-row="${row.key}"]`);
      expect(item?.textContent).toContain(row.window);
      expect(item?.textContent).toContain("If you delete your account");
    }
  });

  it("does not publish the two categories that have no models", () => {
    const { container } = render(<DataInventory />);

    // Amendment A-27 withdrew EMAIL_DELIVERY_EVENTS and ANALYTICS_AGGREGATES from §10.2
    // because no model declares either — there is no open-and-click store and no
    // analytics vendor. A page listing them would tell a user we watch something we do
    // not. The backend test fails if either ever gains a model.
    expect(container.querySelector('[data-retention-row="email_delivery_events"]')).toBeNull();
    expect(container.querySelector('[data-retention-row="analytics_aggregates"]')).toBeNull();
  });

  it("points at the full policy and at export", () => {
    render(<DataInventory />);

    expect(screen.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute(
      "href",
      "/privacy",
    );
    expect(screen.getByRole("link", { name: "export everything we hold" })).toHaveAttribute(
      "href",
      "/settings/account",
    );
  });
});
