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
import { RETENTION_ROWS } from "@/lib/retention-categories";

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

  describe("/privacy content", () => {
    it("publishes every retention category it mirrors", () => {
      render(<PrivacyPage />);

      // The rows come from `lib/retention-categories.ts`, which
      // `backend/tests/shared/test_retention_published.py` pins to the live
      // `RetentionCategory` registry. This assertion is the frontend half: the data is
      // not merely imported, it reaches the page.
      for (const row of RETENTION_ROWS) {
        expect(screen.getByText(row.label)).toBeInTheDocument();
      }
      expect(RETENTION_ROWS.length).toBeGreaterThan(5);
    });

    it("names the 30-day grace period", () => {
      render(<PrivacyPage />);

      // `DELETION_GRACE_PERIOD = timedelta(days=30)`. A policy that stated a different
      // number would be describing a product that does not exist.
      expect(screen.getByText(/30 days to change your mind/)).toBeInTheDocument();
    });

    it("is explicit that billing records and audit logs survive deletion", () => {
      render(<PrivacyPage />);

      // `SURVIVING_CATEGORIES`. The unflattering half, and the half a reader most needs
      // — a policy that only lists what is deleted is telling half a truth.
      expect(screen.getByText(/Two things survive/)).toBeInTheDocument();
      expect(screen.getByText(/seven years because tax law requires it/)).toBeInTheDocument();
    });

    it("claims no training-data opt-out, because none is configured", () => {
      const { container } = render(<PrivacyPage />);

      // PRD §10.2 says the system opts out of the provider's training-data retention
      // "where the provider's terms permit". `adapters/llm/voyage.py` contains no such
      // configuration, so the page must not say it does. This asserts the absence of a
      // claim, which is the only kind of guard that keeps an unverified promise off a
      // legal page.
      expect(container.textContent).not.toMatch(/opt(ed)?[ -]out/i);
      expect(container.textContent).toMatch(/do not use your personal data to train/i);
    });
  });

  it("does not offer a route that was never specified", () => {
    render(<PrivacyPage />);

    // "How it works" linked `/how` from this footer on eight surfaces and had no route
    // and no spec: §323 lists "Log in, Privacy, Terms, social links", and names "How it
    // works" only as something that must not sit in the topbar. It was removed rather
    // than built, because a route would have to be a page somebody decided to write.
    expect(screen.queryByRole("link", { name: "How it works" })).toBeNull();
  });
});
