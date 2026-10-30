import { BrandTopbar } from "@/components/brand-topbar";

import { PreAuthFooter } from "./pre-auth-footer";

/**
 * The pre-auth page frame the three auth routes share: the brand topbar, a centred card,
 * and the pre-auth footer.
 *
 * **The card is 480 px wide, or 520 px where the sign-up form needs it.** That is the
 * mockups' and `EXPERIENCE.md`'s number ("480px column — narrower than the 720px
 * onboarding column because auth forms are single-decision, not content-rich"), and it is
 * the one place in this item where a width is not `--layout-container-form`: that token
 * is 720 px, aliased to the reading column, and the two sources disagree. The mockup is
 * the more specific instruction and the binding artefact for these routes, so it wins
 * here and the token keeps its meaning everywhere else.
 */
export function AuthPageShell({
  title,
  lede,
  current,
  wide = false,
  children,
}: {
  title: string;
  lede: string;
  /** The route being rendered, for the footer's `aria-current`. */
  current?: string;
  /** The sign-up column, which the OIDC stack will widen to 520 px. */
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar />
      <main className="fade-in flex flex-1 items-center justify-center px-6 py-12">
        <div className={`w-full ${wide ? "max-w-[520px]" : "max-w-[480px]"}`}>
          <div className="mb-8">
            <h1 className="text-ink-primary [font:var(--type-scale-display-md)]">{title}</h1>
            <p className="mt-3 [font:var(--type-scale-body-md)] text-ink-secondary">{lede}</p>
          </div>
          {children}
        </div>
      </main>
      <PreAuthFooter current={current} />
    </div>
  );
}
