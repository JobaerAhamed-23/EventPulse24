import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Source_Serif_4 } from "next/font/google";

import "@/styles/globals.css";
import { siteUrl } from "@/lib/site-url";

// Self-hosted at build time: visitors' browsers never contact Google. All three are variable
// fonts, so every weight DESIGN.md uses (400–700) is included.
const inter = Inter({
  subsets: ["latin"],
  style: ["normal", "italic"], // type.scale.microtag is italic in the body family
  variable: "--font-inter",
});

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

export const metadata: Metadata = {
  title: "EventPulse24",
  description: "What's actually worth your attention right now.",
  /**
   * **The site's public origin, so every absolute URL in a share card resolves.**
   *
   * **Without it Next resolves a relative OG image against `http://localhost:3000`** —
   * which is what a share card would then point at, and a card whose image is
   * `localhost` shows nothing. The canonical and the OG URL are relative for the same
   * reason: they name a path, and a path is not an address until it has an origin.
   *
   * **It lives in the root layout, not in one page.** A share image is not a per-page
   * concern — every public surface's metadata resolves against the same origin, and
   * the public event page's card has the same defect.
   */
  metadataBase: siteUrl(),
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // The font classes must stay on <html>: they define the --font-* variables, and the
    // --type-family-* tokens read them on :root. On <body>, headings silently lose the font.
    // Dark is the default theme; light is a swap to data-theme="light" (no OS auto-switch).
    <html
      lang="en"
      data-theme="dark"
      className={`${inter.variable} ${sourceSerif.variable} ${jetbrainsMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
