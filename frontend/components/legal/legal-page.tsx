import { ProsePage, ProseSection } from "@/components/pre-auth/prose-page";

/**
 * The frame the two legal documents share — `/terms` and `/privacy`.
 *
 * ## These are pre-auth surfaces by specification, not by inference
 *
 * `EXPERIENCE.md` §323 names the pre-auth footer's secondary affordances as *"Log in,
 * Privacy, Terms, social links"*. The footer that links these documents is
 * `Component.Footer.PreAuth`, so the documents belong to the same family — brand topbar,
 * no sidenav, pre-auth footer. They are also read **before** an account exists: the
 * sign-up form asks the visitor to agree to them, which is the one moment they are most
 * likely to be opened.
 *
 * **No session is read here, and none may be.** `lib/session.ts` routes an
 * unauthenticated visitor to `/preview` or `/onboarding`; a legal document that
 * redirected a signed-out reader somewhere else would be unreadable at exactly the
 * moment it is needed. These routes are static and public.
 *
 ## The frame is `ProsePage`; this adds a legal document's contract
 *
 * `ProsePage` holds the chrome every pre-auth prose surface shares — brand topbar,
 * reading column, pre-auth footer. **What this component adds is the draft banner and
 * the last-updated date**, which belong to a legal document and to nothing else:
 * `/about` carrying a "not reviewed by a lawyer" notice would be a category error.
 *
 * (It is not `AuthPageShell`, whose 480 px card `EXPERIENCE.md` specifies for forms that
 * are *"single-decision, not content-rich"*. A policy is the opposite.)
 *
 * ## The banner is not decoration
 *
 * Both documents are drafts describing as-built behaviour, written without legal review.
 * **Saying so is the most important sentence on either page**, so it is rendered above
 * the first clause in `signal-warn` rather than as a footnote — a reader who stops after
 * one paragraph must still have been told. `tests/legal-pages.test.tsx` asserts it is
 * present on both routes.
 *
 * ## One date, one source
 *
 * `lastUpdated` is passed in from a single shared constant. A policy's date is a factual
 * claim, and two hand-typed dates drift apart — the stale one then says something untrue
 * about when the document last changed.
 */
export function LegalPage({
  title,
  lede,
  lastUpdated,
  current,
  children,
}: {
  title: string;
  lede: string;
  lastUpdated: string;
  /** This route, so the footer marks its own row with `aria-current="page"`. */
  current: string;
  children: React.ReactNode;
}) {
  return (
    <ProsePage
      title={title}
      lede={lede}
      current={current}
      beforeContent={
        <>
          <p className="mt-2 [font:var(--type-scale-meta-md)] text-ink-muted">
            Last updated {lastUpdated}
          </p>

          {/*
            Above the first clause, and deliberately hard to miss. The reader is being
            asked to rely on this document; the one thing they must know first is how
            much weight it can carry.
          */}
          <aside
            aria-label="Draft notice"
            className="mt-8 rounded-card border border-signal-warn/40 bg-surface-subtle px-4 py-3 [font:var(--type-scale-body-sm)] text-signal-warn"
          >
            <strong className="font-semibold">This is an unreviewed draft.</strong> It
            describes how EventPulse24 actually behaves today, written from the running
            code. It has <strong className="font-semibold">not</strong> been reviewed by a
            lawyer and it is not legal advice. Where this document and the product
            disagree, the product is what is true — and that is a bug in this page, which
            we would like to hear about.
          </aside>
        </>
      }
    >
      {children}
    </ProsePage>
  );
}

/**
 * One clause of a legal document.
 *
 * **The `id` is the point.** A clause nobody can link to cannot be quoted in a support
 * thread, a complaint or a regulator's question, and "see the fourth paragraph of the
 * privacy policy" is not a citation. Every section is addressable.
 */
export function LegalSection({
  id,
  heading,
  children,
}: {
  id: string;
  heading: string;
  children: React.ReactNode;
}) {
  return (
    <ProseSection id={id} heading={heading}>
      {children}
    </ProseSection>
  );
}
