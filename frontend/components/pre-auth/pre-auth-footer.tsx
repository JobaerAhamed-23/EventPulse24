import Link from "next/link";

/**
 * `Component.Footer.PreAuth` — the footer the pre-auth surfaces share.
 *
 * This is where the conversion affordances live. The topbar carries identity only, so
 * "Log in" and "Sign up free" are **here**, as drawn in `signin-desktop.html` and
 * `signup-desktop.html` (the same block, byte-identical, in both).
 *
 * The link list is the mockups' list, including the two that are drawn as `#` — About and
 * Contact have no route in the route map. They are rendered as drawn rather than dropped,
 * because this footer is shared with `/preview`, which draws the same block.
 *
 * **"How it works" is gone (2026-11-20), and Privacy now resolves.** This comment used to
 * say that "How it works", Privacy and Terms *"point at routes that do not exist yet
 * either, and will 404 until they do; that is the mockups' link list, not an invention
 * here."* That was true, and it stayed true for long enough that a user found one of these
 * 404s for us. Two things changed:
 *
 * - **`/privacy` and `/terms` are built**, so the footer's spec'd rows work. `EXPERIENCE.md`
 *   §323 names this footer's secondary affordances as *"Log in, Privacy, Terms, social
 *   links"*, so those rows are required and are now kept.
 * - **`/how` is removed.** It is in no spec. §323's list does not contain it, and "How it
 *   works" appears in that section only as something that must *not* sit in the topbar. It
 *   came from the mockups' chrome, it never had a route, and this footer renders on eight
 *   surfaces — both auth screens, `/preview`, `/pricing`, the public event and city pages,
 *   and both not-found pages — so it was the furthest-reaching dead link in the product.
 *   Removing the row is the honest fix; a route would have to be a page somebody decided
 *   to write.
 *
 * **Terms was missing from this list, and §323 requires it.** The row was added on
 * 2026-11-20, when `/terms` was built. The comment above used to name Terms among the
 * rows pointing at unbuilt routes, but the link list never actually held one — the
 * document was named in the prose and absent from the array, so the footer quietly fell
 * short of §323 for as long as it has existed. It sits next to Privacy, which is where
 * §323 names it.
 *
 * **About and Contact now resolve (2026-11-20).** Both rendered as `href="#"` until a
 * user asked what the About link did. **A `#` is not a 404**, so the link guard never
 * flagged either — which is how a page §326 explicitly promises stayed unbuilt with
 * nothing going red. `tests/internal-links.test.ts` now rejects placeholder hrefs too.
 *
 * The two were not the same case. **About is named by §326**; Contact appears in no
 * section and came from the mockups, like "How it works". Contact was built rather than
 * removed because the footer already linked it on eight surfaces and the legal pages
 * needed somewhere real to point.
 *
 * **Pricing is here because the footer is the conversion surface.** "Log in" and "Sign up
 * free" live here, so the price of the paid tier belongs here too — a visitor who has to
 * go hunting for it is a visitor who never finds out what Pro costs. The link is a real
 * route: `/pricing` exists, so this is not one of the mockups' `#` placeholders.
 */

const LINKS = [
  { href: "/about", label: "About" },
  { href: "/privacy", label: "Privacy" },
  { href: "/terms", label: "Terms" },
  { href: "/contact", label: "Contact" },
  { href: "/pricing", label: "Pricing" },
  { href: "/signin", label: "Log in" },
  { href: "/signup", label: "Sign up free" },
];

export type PreAuthFooterProps = {
  /** The route being rendered, so its own link is marked `aria-current="page"`. */
  current?: string;
};

export function PreAuthFooter({ current }: PreAuthFooterProps) {
  return (
    <footer className="border-t border-border-subtle px-6 py-8">
      <div className="mx-auto flex max-w-(--layout-container-max) flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 [font:var(--type-scale-meta-md)] text-ink-secondary">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-accent-terracotta" />
          EventPulse24
        </div>
        <nav aria-label="Footer">
          <ul className="flex flex-wrap items-center gap-x-6 gap-y-2">
            {LINKS.map((link) => (
              <li key={link.label}>
                <Link
                  href={link.href}
                  aria-current={link.href === current ? "page" : undefined}
                  className="[font:var(--type-scale-body-sm)] text-ink-muted"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <p className="[font:var(--type-scale-body-sm)] text-ink-muted">
          © 2026 EventPulse24 · Available in 200+ cities
        </p>
      </div>
    </footer>
  );
}
