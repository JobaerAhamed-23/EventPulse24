import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PreAuthFooter } from "@/components/pre-auth/pre-auth-footer";
import { BrandTopbar } from "@/components/brand-topbar";

/**
 * The brand topbar and the pre-auth footer, and the **topbar-quiet rule** (ASSUM-11,
 * locked).
 *
 * The topbar holds the brand and nothing else; "Sign in", "Sign up" and the rest live in
 * the footer. `EXPERIENCE.md` calls inversions of this rule bugs, so the test looks for
 * the inversion rather than merely for the brand.
 */

describe("BrandTopbar", () => {
  it("carries the brand, pointing at the public preview", () => {
    render(<BrandTopbar />);

    expect(screen.getByRole("link", { name: "EventPulse24 home" })).toHaveAttribute(
      "href",
      "/preview",
    );
    expect(screen.getByText("calm intelligence for events")).toBeInTheDocument();
  });

  it("points at the home when the signed-in home renders it", () => {
    render(<BrandTopbar href="/" />);

    expect(screen.getByRole("link", { name: "EventPulse24 home" })).toHaveAttribute("href", "/");
  });

  it("carries no other link and no button at all", () => {
    render(<BrandTopbar />);

    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("gives the logo an empty alt, because the wordmark beside it carries the name", () => {
    const { container } = render(<BrandTopbar />);

    const logo = container.querySelector("img");
    expect(logo).not.toBeNull();
    expect(logo).toHaveAttribute("alt", "");
  });
});

describe("PreAuthFooter", () => {
  it("carries the conversion affordances, as drawn", () => {
    render(<PreAuthFooter />);

    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/signin");
    expect(screen.getByRole("link", { name: "Sign up free" })).toHaveAttribute("href", "/signup");
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute("href", "/how");
  });

  it("marks the current route's own link", () => {
    render(<PreAuthFooter current="/signin" />);

    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Sign up free" })).not.toHaveAttribute("aria-current");
  });
});
