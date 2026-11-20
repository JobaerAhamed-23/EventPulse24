import type { Metadata } from "next";

import { LegalPage, LegalSection } from "@/components/legal/legal-page";
import { LEGAL_LAST_UPDATED } from "@/lib/legal";

/**
 * `/terms` — the Terms of Service.
 *
 * **This route existed as a link before it existed as a page.** `signup-form.tsx` and
 * `app/signin/page.tsx` have asked visitors to agree to "our Terms" since Amendment
 * A-20 shipped the auth surfaces, and both links 404'd until 2026-11-20. Asking somebody
 * to accept a document and then failing to show it is the worst version of a dead link,
 * which is why this and `/privacy` were built ahead of their own copy.
 *
 * **The body is a placeholder, and it says so.** `legal-copy-draft` writes the clauses
 * from the running code in this same run. Until it does, this page carries the draft
 * banner and one honest paragraph — **not lorem, and not nothing**. A blank page reads as
 * broken; a page that states its own condition reads as honest, and a reader who arrives
 * mid-run learns something true either way.
 */
export const metadata: Metadata = {
  title: "Terms of Service · EventPulse24",
  description: "The terms you agree to when you use EventPulse24.",
};

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      lede="What you agree to when you use EventPulse24, in plain language."
      lastUpdated={LEGAL_LAST_UPDATED}
      current="/terms"
    >
      <LegalSection id="status" heading="These terms are being written">
        <p>
          This page exists because the sign-up and sign-in screens link to it, and a
          document you are asked to accept should be one you can read. The clauses
          themselves are being drafted from how the product actually works — what the
          service does, how event listings from third parties are handled, what happens
          to a Pro subscription, and what we can and cannot promise about an event
          someone else published.
        </p>
        <p>
          Until that draft lands, nothing on this page limits your rights or ours. If you
          need an answer before then, ask us and we will answer in writing.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
