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
    //
    // **`suppressHydrationWarning` is here for Dark Reader.** The extension rewrites
    // the page before React hydrates, and it stamps the document element with its own
    // attributes — `data-darkreader-mode`, `data-darkreader-scheme`,
    // `data-darkreader-proxy-injected`. React then compares the mutated `<html>`
    // against the markup it rendered on the server, finds the extra attributes, and
    // reports a hydration mismatch on the root of the tree.
    //
    // **The flag is on `<html>` because that is the element being mutated.** React's
    // guard is one level deep: it silences a mismatch on the element that carries it,
    // not on that element's descendants. So the attributes Dark Reader puts on `<html>`
    // are silenced here, and the attributes it puts on the nav `<svg>`s are silenced
    // there — on those elements, individually. Putting the flag on `<html>` alone would
    // not have covered the SVGs, and putting it on a wrapper would not have covered
    // either.
    //
    // **This is not a workaround for a bug in this code.** The server markup is
    // correct and the extension's attributes are the extension's business. React
    // patching them back would undo Dark Reader's work and fight the reader who
    // installed it.
    <html
      lang="en"
      data-theme="dark"
      className={`${inter.variable} ${sourceSerif.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body>{children}</body>
    </html>
  );
}
