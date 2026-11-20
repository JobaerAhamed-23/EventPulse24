import { BrandTopbar } from "@/components/brand-topbar";
import { PreAuthFooter } from "@/components/pre-auth/pre-auth-footer";

/**
 * The frame every pre-auth prose surface shares — `/about`, `/contact`, and (through
 * `LegalPage`) `/terms` and `/privacy`.
 *
 * **Brand topbar, reading column, pre-auth footer.** `EXPERIENCE.md` §326 names these
 * surfaces' home: the page footer carries *"Login, Privacy, Terms, About, social links,
 * city nav"*, so everything that footer links belongs to the same family.
 *
 * **It reads no session**, and none of its callers may. `lib/session.ts` routes an
 * unauthenticated visitor to `/preview` or `/onboarding`; a page explaining what the
 * product is, or how to reach us, must be readable by someone who has not signed up —
 * that is the entire audience for it.
 *
 * **Not `AuthPageShell`.** That centres a 480 px card, which `EXPERIENCE.md` specifies
 * for forms that are *"single-decision, not content-rich"*. Prose is the opposite and
 * uses the reading column.
 *
 * `LegalPage` composes this and adds the draft banner and the last-updated date, which
 * are a legal document's contract and not a general one's. An About page carrying a
 * "not reviewed by a lawyer" banner would be a category error.
 */
export function ProsePage({
  title,
  lede,
  current,
  children,
  beforeContent,
}: {
  title: string;
  lede: string;
  /** This route, so the footer marks its own row with `aria-current="page"`. */
  current: string;
  children: React.ReactNode;
  /** Rendered between the lede and the sections. `LegalPage` puts its banner here. */
  beforeContent?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <BrandTopbar />
      <main className="fade-in flex-1 px-6 py-12">
        <article className="mx-auto w-full max-w-(--layout-container-reading)">
          <h1 className="text-ink-primary [font:var(--type-scale-display-md)]">{title}</h1>
          <p className="mt-3 [font:var(--type-scale-body-md)] text-ink-secondary">{lede}</p>
          {beforeContent}
          <div className="mt-12 flex flex-col gap-8">{children}</div>
        </article>
      </main>
      <PreAuthFooter current={current} />
    </div>
  );
}

/**
 * One addressable section of a prose page.
 *
 * **The `id` is the point.** A section nobody can link to cannot be quoted in a support
 * thread or a regulator's question, and "the fourth paragraph" is not a citation.
 */
export function ProseSection({
  id,
  heading,
  children,
}: {
  id: string;
  heading: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-8">
      <h2 className="text-ink-primary [font:var(--type-scale-headline-md)]">{heading}</h2>
      <div className="mt-3 flex flex-col gap-3 [font:var(--type-scale-body-md)] text-ink-secondary">
        {children}
      </div>
    </section>
  );
}
