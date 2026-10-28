import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Source_Serif_4 } from "next/font/google";

import "@/styles/globals.css";

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
