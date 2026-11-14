import Image from "next/image";
import Link from "next/link";

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
 * The logo's halo is painted into the PNG — it is a brand asset, not a CSS glow, and so
 * it is outside the token system and exempt from the terracotta glow rationing. It is
 * rendered at 36×36 and must not grow past 40×40 on a pre-auth surface.
 */
export function BrandTopbar({ href = "/preview" }: { href?: string }) {
  return (
    <nav aria-label="Brand" className="px-6 pt-8 pb-4">
      <Link href={href} aria-label="EventPulse24 home" className="inline-block">
        <span className="flex items-center gap-3">
          <Image
            src="/brand/eventpulse24-logo.png"
            alt=""
            width={36}
            height={36}
            priority
            className="size-[36px]"
            /**
             * Dark Reader (and similar extensions) rewrite the DOM before React hydrates:
             * they inject `--darkreader-inline-color` into the inline style and a
             * `data-darkreader-inline-color` attribute onto the element. React then finds
             * markup that differs from what it rendered on the server and reports a
             * hydration mismatch.
             *
             * The mismatch is in the extension's injected attributes, not in this
             * component's own markup, and React would only strip them at the cost of a
             * client re-render of the logo — a visible flash on a surface that is meant to
             * hold the brand and nothing else.
             *
             * `suppressHydrationWarning` is scoped to this element's attributes and
             * text content; it does not silence hydration warnings from its children.
             */
            suppressHydrationWarning
          />
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
