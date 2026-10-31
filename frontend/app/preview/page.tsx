import type { Metadata } from "next";
import Link from "next/link";

import { BrandTopbar } from "@/components/brand-topbar";
import { PreAuthFooter } from "@/components/pre-auth/pre-auth-footer";
import {
  PreviewBannerSlot,
  PreviewCardsSlot,
  PreviewProvider,
} from "@/components/preview/preview-section";

/**
 * `/preview` — the Pulse Preview, the anonymous gateway (FR-2, AD-12).
 *
 * **This page is static, and that is a requirement rather than an optimisation.** AD-12:
 * "Public event pages render fully without a session", and this item's criterion adds
 * that the page "renders identically for an anonymous and a signed-in visitor". So there
 * is no `dynamic` export, no `cookies()`, no `getSession()` — nothing here can vary by
 * who is asking, which is what makes the page cacheable at the edge.
 *
 * Everything that *is* per-visitor — the resolved city, the remembered location choice,
 * the save count behind the soft wall — lives in the one client island below, in the
 * browser. The island's request is also the reason the city works: the edge's location
 * header rides on the visitor's own request to `/api/*`, which `proxy.ts` forwards to
 * Django.
 */
export const metadata: Metadata = {
  title: "Pulse Preview",
  description: "Three events a day in your city. Hand-picked, not algorithmic.",
};

export default function PreviewPage() {
  return (
    // The provider wraps the page so the banner can sit above the topbar, as the mockup
    // draws it, while the cards sit below the hero. The topbar, hero and footer inside it
    // stay server components: they are children, not imports of a client module.
    <PreviewProvider>
      <PreviewBannerSlot />
      <div className="flex min-h-screen flex-col">
        <BrandTopbar />

        <main className="fade-in mx-auto w-full max-w-(--layout-container-max) flex-1 px-6 py-8">
          <section aria-label="What EventPulse24 is">
            <p className="[font:var(--type-scale-meta-sm)] tracking-wide text-ink-muted uppercase">
              Three events a day. Hand-picked, not algorithmic.
            </p>
            <h1 className="mt-4 text-ink-primary [font:var(--type-scale-display-lg)]">
              Three things matter.{" "}
              <em className="text-ink-secondary">Three picks, every morning.</em>
            </h1>
            <p className="mt-4 max-w-(--layout-container-reading) [font:var(--type-scale-body-lg)] text-ink-secondary">
              Every morning, your <strong className="text-ink-primary">Pulse</strong> arrives —
              three events the open web suggests, hand-picked for you. No feeds. No badges. No
              infinite scroll.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-6">
              {/* The hero CTA is the surface's primary conversion affordance; the topbar
                carries identity only (the topbar-quiet rule). */}
              <Link
                href="/signup"
                className="rounded-control bg-accent-terracotta px-6 py-3 [font:var(--type-scale-meta-md)] text-ink-inverse"
              >
                Sign up
              </Link>
              <Link
                href="#today"
                className="[font:var(--type-scale-body-sm)] text-ink-secondary underline underline-offset-4"
              >
                See today&apos;s preview →
              </Link>
              <span className="[font:var(--type-scale-body-sm)] text-ink-muted">
                Free. No card.
              </span>
            </div>
          </section>

          <PreviewCardsSlot />
        </main>

        <PreAuthFooter />
      </div>
    </PreviewProvider>
  );
}
