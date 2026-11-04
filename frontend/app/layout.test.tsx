import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import RootLayout, { metadata } from "@/app/layout";

// next/font only works inside Next's compiler; each mock returns a distinct variable class.
vi.mock("next/font/google", () => ({
  Inter: () => ({ variable: "font-var-inter" }),
  Source_Serif_4: () => ({ variable: "font-var-source-serif" }),
  JetBrains_Mono: () => ({ variable: "font-var-jetbrains-mono" }),
}));

vi.mock("@/styles/globals.css", () => ({}));

const FONT_CLASSES = ["font-var-inter", "font-var-source-serif", "font-var-jetbrains-mono"];

type HtmlProps = { lang: string; "data-theme": string; className: string; children: ReactElement };
type BodyProps = { className?: string; children: unknown };

// Calling the layout directly returns the <html> element; rendering it with Testing Library
// would nest <html> inside a <div>.
function renderLayout() {
  const html = RootLayout({
    children: <p>child</p>,
  } as LayoutProps<"/">) as ReactElement<HtmlProps>;
  const body = html.props.children as ReactElement<BodyProps>;
  return { html, body };
}

describe("RootLayout", () => {
  it("renders <html> in English with the dark theme by default", () => {
    const { html } = renderLayout();

    expect(html.type).toBe("html");
    expect(html.props.lang).toBe("en");
    expect(html.props["data-theme"]).toBe("dark");
  });

  it("puts every font variable class on <html> and none on <body>", () => {
    const { html, body } = renderLayout();

    expect(html.props.className.split(" ").sort()).toEqual([...FONT_CLASSES].sort());
    expect(body.type).toBe("body");
    for (const fontClass of FONT_CLASSES) {
      expect(body.props.className ?? "").not.toContain(fontClass);
    }
  });
});

describe("the root layout's metadata", () => {
  it("names the site's public origin as its metadataBase", () => {
    // **Without a `metadataBase`, Next resolves a relative OG image against
    // `http://localhost:3000`** — so a share card would point its image at a loopback
    // address and render nothing. The origin is what turns a path into an address.
    expect(metadata.metadataBase).toBeInstanceOf(URL);
  });

  it("keeps the site's own title and description", () => {
    expect(metadata.title).toBe("EventPulse24");
    expect(metadata.description).toBe("What's actually worth your attention right now.");
  });
});
