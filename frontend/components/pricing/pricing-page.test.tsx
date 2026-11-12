import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PricingPage } from "@/components/pricing/pricing-page";

/**
 * The pricing screen's copy and its three states.
 *
 * **The no-upsell rule is the point of this file.** FR-48: *"Pricing page is a single
 * screen; no upsell copy beyond 'fewer interruptions, more control.'"* That is a product
 * constraint, so it is asserted: no countdown, no scarcity, no "limited time", no
 * urgency badges, and no second tagline doing the work of the first.
 *
 * **The feature lists are FR-48's, not the mockup's.** The mockup names Phase 2
 * features, "priority support from Brooklyn" and public share-links; FR-48 does not, and
 * FR-48 is the authority on copy.
 */

const POST = vi.fn();
const push = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
}));

const assign = vi.fn();

beforeEach(() => {
  POST.mockReset();
  push.mockReset();
  assign.mockReset();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...window.location, assign },
  });
});

/** The Free card, by its heading. */
function freeCard(): HTMLElement {
  const card = screen.getByRole("heading", { level: 2, name: "Free" }).closest("article");
  if (card === null) throw new Error("the Free card is not in the document");
  return card;
}

/** The Pro card, by its heading. */
function proCard(): HTMLElement {
  const card = screen.getByRole("heading", { level: 2, name: "Pro" }).closest("article");
  if (card === null) throw new Error("the Pro card is not in the document");
  return card;
}

describe("the pricing screen", () => {
  describe("the prices", () => {
    it("shows the monthly price first", () => {
      render(<PricingPage tier="free" />);

      expect(within(proCard()).getByText("$4.99")).toBeInTheDocument();
      expect(within(proCard()).getByText("/ month")).toBeInTheDocument();
    });

    it("shows the yearly price when the annual option is chosen", () => {
      render(<PricingPage tier="free" />);

      fireEvent.click(screen.getByRole("radio", { name: /Annual/ }));

      expect(within(proCard()).getByText("$49")).toBeInTheDocument();
      expect(within(proCard()).getByText("/ year")).toBeInTheDocument();
    });

    it("shows Free as free, and says so plainly", () => {
      render(<PricingPage tier="free" />);

      expect(within(freeCard()).getByText("$0")).toBeInTheDocument();
      expect(within(freeCard()).getByText("/ forever")).toBeInTheDocument();
    });

    it("keeps both prices visible, so the discount is legible", () => {
      render(<PricingPage tier="free" />);

      // $49 a year against $4.99 × 12 is an 18.2% discount — the "save 18%" is
      // arithmetic, not persuasion.
      expect(within(proCard()).getByText(/or \$49\/yr/)).toBeInTheDocument();
    });
  });

  describe("the copy", () => {
    it("uses FR-48's sentence as the only Pro tagline", () => {
      render(<PricingPage tier="free" />);

      expect(within(proCard()).getByText("Fewer interruptions, more control.")).toBeInTheDocument();
    });

    it("carries no upsell copy", () => {
      const { container } = render(<PricingPage tier="free" />);

      // **The trust strip's own promise is excluded.** "No 'limited time!' copy." is the
      // product *denying* it has any, so it names the phrase in order to disown it.
      // Reading that as upsell would be reading the promise as the thing it forbids.
      const trust = container.querySelector("section[aria-label='What we promise']");
      const text = (container.textContent ?? "")
        .replace(trust?.textContent ?? "", "")
        .toLowerCase();

      for (const banned of [
        "limited time",
        "act now",
        "hurry",
        "expires",
        "ends soon",
        "last chance",
        "save big",
        "most popular",
        "best value",
        "don't miss out",
        "only for",
      ]) {
        expect(text).not.toContain(banned);
      }
    });

    it("says exactly one piece of Pro marketing copy — FR-48's sentence", () => {
      render(<PricingPage tier="free" />);

      // **The strong form of the no-upsell rule.** A banned-word list is a tripwire: any
      // upsell phrase outside those eleven words slips past it. This asserts the
      // *allowlist* instead — the Pro card's prose is FR-48's sentence and the feature
      // list, and nothing else. A second tagline, however well written, fails here.
      const card = proCard();

      // The taglines, which is where marketing copy lives. The feature list is a
      // `<ul>` and the price is a `<div>`, so neither is prose.
      const prose = [...card.querySelectorAll("[data-tagline]")]
        .map((node) => node.textContent?.trim() ?? "")
        .filter((text) => text !== "");

      expect(prose).toEqual(["Fewer interruptions, more control."]);
    });

    it("says exactly one piece of Free marketing copy", () => {
      render(<PricingPage tier="free" />);

      const prose = [...freeCard().querySelectorAll("[data-tagline]")]
        .map((node) => node.textContent?.trim() ?? "")
        .filter((text) => text !== "");

      // The mockup's Free tagline. It is descriptive — it says what Free *is*, not what
      // the visitor is missing by not having Pro — so it is allowed, and it is the only
      // one.
      expect(prose).toEqual(["Everything you need to start calm."]);
    });

    it("says no marketing copy beyond the taglines, in either state", () => {
      // **The allowlist, kept strict.** `data-tagline` marks the marketing copy; the
      // cards' other `<p>`s are *state labels* — "You're on Free", "Free, without Pro" —
      // which are facts about the visitor, not salesmanship. So the assertion is not
      // "there is one `<p>`", it is "every paragraph is either the tagline or a state
      // label". A second tagline fails; a state label does not.
      const STATE_LABELS = ["You’re on Free", "Free, without Pro"];

      for (const tier of ["free", "pro"] as const) {
        const { unmount } = render(<PricingPage tier={tier} />);

        for (const card of [freeCard(), proCard()]) {
          const allowed = [
            card.querySelector("[data-tagline]")?.textContent?.trim() ?? "",
            ...STATE_LABELS,
          ];

          const paragraphs = [...card.querySelectorAll("p")]
            .map((node) => node.textContent?.trim() ?? "")
            .filter((text) => text !== "");

          for (const paragraph of paragraphs) {
            expect(allowed).toContain(paragraph);
          }
        }

        unmount();
      }
    });

    it("carries no countdown, no scarcity badge and no urgency timer", () => {
      const { container } = render(<PricingPage tier="free" />);

      expect(container.querySelector('[role="timer"]')).toBeNull();
      expect(container.textContent).not.toMatch(/\d+\s*(hours?|minutes?|days?)\s+left/i);
      // The trust strip *says* there are no urgency badges. That is the promise, not the
      // thing itself, so the promise's own sentence is allowed to name them.
      expect(screen.getByText("No dark patterns")).toBeInTheDocument();
    });

    it("offers no comparison table that editorialises the tiers", () => {
      const { container } = render(<PricingPage tier="free" />);

      expect(container.querySelector("table")).toBeNull();
    });

    it("states the Free tier's limits as facts about the plan", () => {
      render(<PricingPage tier="free" />);

      const free = within(freeCard());
      expect(free.getByText("1 save a day")).toBeInTheDocument();
      expect(free.getByText("1 connected calendar provider")).toBeInTheDocument();
    });

    it("states what Free keeps, as FR-48 lists it", () => {
      render(<PricingPage tier="free" />);

      const free = within(freeCard());
      expect(free.getByText("Pulse Digest")).toBeInTheDocument();
      expect(free.getByText("Reminders")).toBeInTheDocument();
      expect(free.getByText("Personal events")).toBeInTheDocument();
    });

    it("states what Pro adds, as FR-48 lists it", () => {
      render(<PricingPage tier="free" />);

      const pro = within(proCard());
      expect(pro.getByText("Unlimited saves")).toBeInTheDocument();
      expect(pro.getByText("Saved collections")).toBeInTheDocument();
      expect(pro.getByText("3 connected calendar providers")).toBeInTheDocument();
      expect(pro.getByText("Per-weekday quiet hours")).toBeInTheDocument();
      expect(pro.getByText("JSON + ICS export")).toBeInTheDocument();
    });

    it("does not list the mockup's Phase 2 features, which FR-48 does not", () => {
      render(<PricingPage tier="free" />);

      const { container } = render(<PricingPage tier="free" />);
      const text = (container.textContent ?? "").toLowerCase();
      expect(text).not.toContain("phase 2");
      expect(text).not.toContain("priority support");
      expect(text).not.toContain("share-link");
    });

    it("keeps the trust strip, because it states policies rather than selling", () => {
      render(<PricingPage tier="free" />);

      expect(screen.getByText("Cancel anytime")).toBeInTheDocument();
      expect(screen.getByText("Your data is yours")).toBeInTheDocument();
      expect(screen.getByText("No dark patterns")).toBeInTheDocument();
    });
  });

  describe("the three visitor states", () => {
    it("offers a signed-out visitor the sign-in route, not a failing button", () => {
      render(<PricingPage tier="signed-out" />);

      expect(screen.getByRole("link", { name: "Sign in to buy" })).toHaveAttribute(
        "href",
        "/signin?next=%2Fpricing",
      );
      expect(
        screen.queryByRole("button", { name: /Continue to checkout/ }),
      ).not.toBeInTheDocument();
    });

    it("offers a Free user the checkout button", () => {
      render(<PricingPage tier="free" />);

      expect(screen.getByRole("button", { name: "Continue to checkout →" })).toBeInTheDocument();
      expect(within(freeCard()).getByText("You’re on Free")).toBeInTheDocument();
    });

    it("shows a Pro user their plan and a portal, and no second buy button", () => {
      render(<PricingPage tier="pro" />);

      expect(screen.getByRole("button", { name: /You’re on Pro/ })).toBeInTheDocument();
      // **The criterion in one assertion:** a Pro user sees no buy button at all.
      expect(
        screen.queryByRole("button", { name: /Continue to checkout/ }),
      ).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /Sign in to buy/ })).not.toBeInTheDocument();
    });

    it("still shows a Pro user what Free keeps", () => {
      render(<PricingPage tier="pro" />);

      expect(within(freeCard()).getByText("1 save a day")).toBeInTheDocument();
    });

    it("swaps to the Pro state when the server says the visitor already subscribes", async () => {
      POST.mockResolvedValue({
        data: undefined,
        error: { code: "already_subscribed", message: "Your Pro subscription is already active." },
        response: { status: 409 },
      });
      render(<PricingPage tier="free" />);

      fireEvent.click(screen.getByRole("button", { name: "Continue to checkout →" }));

      expect(await screen.findByRole("button", { name: /You’re on Pro/ })).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Continue to checkout/ }),
      ).not.toBeInTheDocument();
    });
  });

  describe("the layout", () => {
    it("renders one screen: a hero, two tiers, a trust strip and a contact line", () => {
      render(<PricingPage tier="free" />);

      expect(
        screen.getByRole("heading", { level: 1, name: "Two ways to keep calm." }),
      ).toBeInTheDocument();
      expect(screen.getByRole("heading", { level: 2, name: "Free" })).toBeInTheDocument();
      expect(screen.getByRole("heading", { level: 2, name: "Pro" })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "hello@eventpulse24.com" })).toHaveAttribute(
        "href",
        "mailto:hello@eventpulse24.com",
      );
    });

    it("offers the billing cycle as one radio group", () => {
      render(<PricingPage tier="free" />);

      const group = screen.getByRole("radiogroup", { name: "Billing cycle" });
      const options = within(group).getAllByRole("radio");
      expect(options).toHaveLength(2);
      expect(options[0]).toHaveAttribute("aria-checked", "true");
      expect(options[1]).toHaveAttribute("aria-checked", "false");
    });

    it("keeps both columns in the layout at mobile width rather than hiding one", () => {
      const { container } = render(<PricingPage tier="free" />);

      // The grid collapses to one column rather than hiding a tier: a phone visitor must
      // still be able to read what Pro adds.
      const grid = container.querySelector("section[aria-label='Pricing tiers']");
      if (grid === null) throw new Error("the tier grid is not in the document");
      expect(grid.className).toContain("grid-cols-1");
      expect(grid.className).toContain("md:grid-cols-2");
      expect(container.querySelectorAll("article")).toHaveLength(2);
    });
  });
});
