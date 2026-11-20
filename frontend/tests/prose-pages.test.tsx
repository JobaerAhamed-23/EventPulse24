// @vitest-environment jsdom
/**
 * `/about` and `/contact` — the two footer rows that pointed at `#`.
 *
 * **They were not the same case**, and these tests record which was which: About is named
 * by `EXPERIENCE.md` §326's canonical footer bullet and was simply never built; Contact
 * appears in no section at all and was built because the footer already linked it on
 * eight surfaces and the legal pages needed a real destination.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AboutPage from "@/app/about/page";
import ContactPage from "@/app/contact/page";

const PAGES = [
  { name: "/about", heading: "About EventPulse24", Page: AboutPage, row: "About" },
  { name: "/contact", heading: "Contact", Page: ContactPage, row: "Contact" },
] as const;

describe("the pre-auth prose pages", () => {
  for (const { name, heading, Page, row } of PAGES) {
    describe(name, () => {
      it("renders with its own heading", () => {
        render(<Page />);

        expect(screen.getByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
      });

      it("carries the pre-auth footer and marks its own row", () => {
        render(<Page />);

        expect(screen.getByRole("link", { name: row })).toHaveAttribute(
          "aria-current",
          "page",
        );
      });

      it("gives every section an id, so it can be linked to", () => {
        const { container } = render(<Page />);

        const sections = [...container.querySelectorAll("article section")];
        expect(sections.length).toBeGreaterThan(0);
        for (const section of sections) {
          expect(section.id).not.toBe("");
        }
      });

      it("carries no draft banner — these are not legal documents", () => {
        render(<Page />);

        // `LegalPage` adds that banner and `ProsePage` does not. An About page telling a
        // reader it has "not been reviewed by a lawyer" would be a category error.
        expect(screen.queryByLabelText("Draft notice")).toBeNull();
      });
    });
  }

  it("about states the business model, because it is the product's whole argument", () => {
    render(<AboutPage />);

    // PRD §15.2. The calm bet is only credible if the money is not coming from
    // attention, so the page that explains the bet has to say where it does come from.
    expect(screen.getByText(/No ads\. No commissions\. No data sales\./)).toBeInTheDocument();
  });

  it("contact points at what a user can do without waiting for a reply", () => {
    render(<ContactPage />);

    // Most of what someone would write in about, they can do themselves immediately.
    // Saying so is more useful than an address that answers in three days.
    const links = [...document.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(links).toContain("/settings/account");
    expect(links).toContain("/settings/privacy");
  });

  it("contact marks its addresses as placeholders", () => {
    render(<ContactPage />);

    // The same honesty the legal pages' banner carries: an address that bounces is worse
    // than one that admits it is not live yet.
    expect(screen.getByText(/Those addresses are placeholders/)).toBeInTheDocument();
  });
});
