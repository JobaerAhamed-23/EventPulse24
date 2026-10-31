import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PreviewPage from "@/app/preview/page";

/**
 * `/preview` — the anonymous gateway.
 *
 * The property this file exists to defend is AD-12: the page renders **identically for an
 * anonymous and a signed-in visitor**, and so can be cached. That is a property of the
 * module, not only of a render, so it is checked both ways — by rendering the page
 * without any session machinery available, and by reading the source for the things that
 * would break it.
 */

const GET = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { GET: (...args: unknown[]) => GET(...args) },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

beforeEach(() => {
  GET.mockReset();
  GET.mockResolvedValue({
    data: { city: "Brooklyn", city_source: "geo", items: [] },
    error: undefined,
  });
});

describe("AD-12: no session, nothing per-visitor on the server", () => {
  it("exports no dynamic rendering flag, so the page can be prerendered", async () => {
    // A `force-dynamic` here would make every visitor's request render the page afresh,
    // which is exactly what a public, cacheable surface must not need.
    const page = await import("@/app/preview/page");

    expect("dynamic" in page).toBe(false);
    expect("revalidate" in page).toBe(false);
  });

  it("reads no session and no cookies on the server", () => {
    // The comments *discuss* these names, so the check is on the code with comments
    // stripped — otherwise the file's own explanation of what it avoids would fail it.
    const source = readFileSync(path.resolve(__dirname, "page.tsx"), "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

    for (const forbidden of ["getSession", "next/headers", "sessionHeaders", "cookies("]) {
      expect(code, forbidden).not.toContain(forbidden);
    }
  });

  it("strips comments before checking, and would still catch a real read", () => {
    // The guard above is only worth having if it can fail: a planted call is caught.
    const planted = `
      /* a comment mentioning getSession */
      import { getSession } from "@/lib/session";
    `;
    const code = planted.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

    expect(code).toContain("getSession");
  });

  it("renders without any session being available", () => {
    // Nothing is mocked for `@/lib/session` in this file: if the page reached for it, the
    // render would have to go through it.
    render(<PreviewPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Three things matter.");
  });
});

describe("the page", () => {
  it("carries the brand topbar and nothing else in it", () => {
    render(<PreviewPage />);

    const topbar = screen.getByRole("navigation", { name: "Brand" });
    expect(topbar).toBeInTheDocument();
    // The topbar-quiet rule: conversion affordances live in the hero and the footer.
    expect(topbar.querySelectorAll("a")).toHaveLength(1);
    expect(topbar.querySelectorAll("button")).toHaveLength(0);
  });

  it("puts the sign-up CTA in the hero", () => {
    render(<PreviewPage />);

    expect(screen.getByRole("link", { name: "Sign up" })).toHaveAttribute("href", "/signup");
  });

  it("carries the pre-auth footer, with sign-in and sign-up", () => {
    render(<PreviewPage />);

    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/signin");
    expect(screen.getByRole("link", { name: "Sign up free" })).toHaveAttribute("href", "/signup");
  });

  it("mounts the preview, which does its own reading in the browser", async () => {
    render(<PreviewPage />);

    // The heading is queried by its name, not by its level alone. A level-only query
    // throws if the document ever carries a second `h2`, and the preview's own shell
    // is free to grow one — the assertion should be about *this* heading.
    expect(
      await screen.findByRole("heading", { level: 2, name: /Next 3 days in Brooklyn/ }),
    ).toBeInTheDocument();
    expect(GET).toHaveBeenCalledWith("/api/public/preview", { params: { query: {} } });
  });
});
