// @vitest-environment jsdom
/**
 * `/terms` and `/privacy` — the two documents the product asks people to accept.
 *
 * **These routes existed as links long before they existed as pages.** The sign-up form
 * and the sign-in screen have printed *"By creating an account, you agree to our Terms
 * and Privacy Policy"* since Amendment A-20, and the pre-auth footer links Privacy on
 * every public surface. All of it 404'd until 2026-11-20. The rules below are the ones
 * whose violation would put the product back in that position, or worse — showing a page
 * that *looks* authoritative while being an unreviewed draft.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PrivacyPage from "@/app/privacy/page";
import TermsPage from "@/app/terms/page";

const PAGES = [
  { name: "/terms", heading: "Terms of Service", Page: TermsPage },
  { name: "/privacy", heading: "Privacy Policy", Page: PrivacyPage },
] as const;

describe("the legal documents", () => {
  for (const { name, heading, Page } of PAGES) {
    describe(name, () => {
      it("renders, with its own title", () => {
        render(<Page />);

        expect(screen.getByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
      });

      it("says it is an unreviewed draft, above the first clause", () => {
        const { container } = render(<Page />);

        // **The most important sentence on the page.** A reader who stops after one
        // paragraph must still have been told how much weight this document carries.
        const notice = screen.getByLabelText("Draft notice");
        expect(notice).toHaveTextContent("unreviewed draft");
        expect(notice).toHaveTextContent("not been reviewed by a lawyer");

        // And it is *above* the clauses, not a footnote under them. Source order is
        // what a screen reader follows and what a reader who skims sees first.
        const firstSection = container.querySelector("section[id]");
        expect(firstSection).not.toBeNull();
        expect(
          notice.compareDocumentPosition(firstSection as Node) &
            Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
      });

      it("dates itself from the one shared constant", () => {
        render(<Page />);

        // A date is a factual claim about when the text last changed. Both pages read
        // the same constant so they cannot disagree.
        expect(screen.getByText(/Last updated 20 November 2026/)).toBeInTheDocument();
      });

      it("gives every clause an id, so it can be cited", () => {
        const { container } = render(<Page />);

        const sections = [...container.querySelectorAll("article section")];
        expect(sections.length).toBeGreaterThan(0);
        for (const section of sections) {
          expect(section.id).not.toBe("");
        }
      });

      it("carries the pre-auth footer and marks its own row", () => {
        render(<Page />);

        // `EXPERIENCE.md` §323 puts Privacy and Terms in this footer, so these pages
        // link to themselves — and the row for the page you are on must say so.
        const self = screen.getByRole("link", {
          name: heading === "Privacy Policy" ? "Privacy" : "Terms",
        });
        expect(self).toHaveAttribute("aria-current", "page");
      });
    });
  }

  it("does not offer a route that was never specified", () => {
    render(<PrivacyPage />);

    // "How it works" linked `/how` from this footer on eight surfaces and had no route
    // and no spec: §323 lists "Log in, Privacy, Terms, social links", and names "How it
    // works" only as something that must not sit in the topbar. It was removed rather
    // than built, because a route would have to be a page somebody decided to write.
    expect(screen.queryByRole("link", { name: "How it works" })).toBeNull();
  });
});
