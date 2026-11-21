import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";

/**
 * The brand lockup, as a topbar: `Component.Topbar.PreAuth` on the public routes, and the
 * same mark on the signed-in home.
 *
 * It is one component because `EXPERIENCE.md` says the pre-auth brand-wrap is
 * "byte-identical to the authed topbar" — two copies could only drift. Only the anchor
 * differs: the public routes point at `/preview`, the signed-in home at `/`.
 *
 * **It holds the brand and nothing else** (the topbar-quiet rule, ASSUM-11). No "Sign
 * in", no "Sign up", no nav: those live in the page footer and in surface-level CTAs.
 * `EXPERIENCE.md` is explicit that putting "Sign in" in the topbar of `/signin` would be
 * the same inversion the rule forbids elsewhere, so the only interactive thing here is
 * the brand anchor itself.
 *
 * The logo is the mark from `BrandMark` — the same component the authed topbar, the
 * sidenav rail and the pre-auth footer use, so the brand cannot differ from one
 * surface to another. It is rendered at 36×36 and must not grow past 40×40 on a
 * pre-auth surface.
 */
export function BrandTopbar({ href = "/preview" }: { href?: string }) {
  return (
    <nav aria-label="Brand" className="px-6 pt-8 pb-4">
      <Link href={href} aria-label="EventPulse24 home" className="inline-block">
        <span className="flex items-center gap-3">
          <BrandMark size={36} priority />
          <span className="flex flex-col">
            <span className="text-ink-primary [font:var(--type-scale-headline-sm)]">
              EventPulse24
            </span>
            <span className="text-ink-muted [font:var(--type-scale-microtag)]">
              calm intelligence for events
            </span>
          </span>
        </span>
      </Link>
    </nav>
  );
}
