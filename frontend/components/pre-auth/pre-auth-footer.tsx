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
 * because this footer is shared with `/preview`, which is built next and draws the same
 * block. "How it works", Privacy and Terms point at routes that do not exist yet either,
 * and will 404 until they do; that is the mockups' link list, not an invention here.
 */

const LINKS = [
  { href: "/how", label: "How it works" },
  { href: "#", label: "About" },
  { href: "/privacy", label: "Privacy" },
  { href: "#", label: "Contact" },
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
