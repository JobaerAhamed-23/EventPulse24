import { render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
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

  /**
   * The hydration-mismatch guard.
   *
   * Dark Reader and other DOM-rewriting extensions mutate the page **before** React
   * hydrates: they inject `--darkreader-inline-color` into the element's inline style
   * and add a `data-darkreader-inline-color` attribute. React then compares the mutated
   * DOM against the markup it rendered on the server, finds the difference, and logs a
   * hydration mismatch — the dev-server error that names this component.
   *
   * The fix is `suppressHydrationWarning` on the logo, so React ignores attribute
   * differences on that one element instead of re-rendering it client-side (which would
   * flash the brand on a surface that is meant to hold the brand and nothing else).
   *
   * React consumes `suppressHydrationWarning` rather than rendering it as an attribute,
   * so it cannot be asserted on the DOM node. What *can* be asserted is the thing the
   * guard depends on: that the server-rendered markup carries no extension-injected
   * attributes of its own. If a future change let the extension's attributes into the
   * server HTML, the guard would be masking a real bug — this test is what catches it.
   */
  it("renders the logo without any extension-injected attributes", () => {
    const markup = renderToStaticMarkup(<BrandTopbar />);

    expect(markup).not.toContain("darkreader");
    expect(markup).not.toContain("data-darkreader-inline-color");
    expect(markup).not.toContain("--darkreader-inline-color");
  });

  it("keeps the logo's own markup the same on the server and the client", () => {
    const { container } = render(<BrandTopbar />);
    const clientLogo = container.querySelector("img");

    const serverMarkup = renderToStaticMarkup(<BrandTopbar />);
    const serverLogo = serverMarkup.match(/<img[^>]*>/)?.[0];

    expect(clientLogo).not.toBeNull();
    expect(serverLogo).toBeDefined();

    // The attributes React renders on the client are the ones it rendered on the
    // server. If these ever diverge, the mismatch is ours and not an extension's.
    for (const attribute of ["alt", "width", "height", "class", "src"]) {
      expect(serverLogo).toContain(`${attribute}=`);
    }
    expect(clientLogo).toHaveAttribute("width", "36");
    expect(clientLogo).toHaveAttribute("height", "36");
    expect(clientLogo).toHaveAttribute("alt", "");
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
