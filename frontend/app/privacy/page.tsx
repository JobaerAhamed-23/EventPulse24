import type { Metadata } from "next";

import { LegalPage, LegalSection } from "@/components/legal/legal-page";
import { LEGAL_LAST_UPDATED } from "@/lib/legal";

/**
 * `/privacy` — the Privacy Policy.
 *
 * **Not to be confused with `/settings/privacy`**, which is the signed-in privacy
 * *settings* screen (FR-22's ranking transparency and the account danger zone, built by
 * `run-eventpulse24-048`). This is the public document, read before an account exists.
 *
 * **A published privacy policy is a compliance requirement, not a courtesy.** PRD §10.5's
 * regulatory tables list it under GDPR, CCPA/CPRA, VCDPA, CPA, CTDPA, UCPA, PIPEDA,
 * Quebec Law 25 and the Privacy Act 1988. It was linked from the two auth screens and
 * from the pre-auth footer — which renders on eight surfaces — and 404'd from all of
 * them until 2026-11-20.
 *
 * **The body is a placeholder, and it says so.** `legal-copy-draft` writes it from the
 * sources that can make it true rather than merely confident: `shared/retention.py`'s
 * `RetentionCategory`, whose nine windows are enforced by system checks and walked by a
 * test; `DELETION_GRACE_PERIOD`; and `backend/adapters/` for the real list of third
 * parties. A policy generated from an enforced registry is true by construction; one
 * written freehand is true until someone changes a model.
 */
export const metadata: Metadata = {
  title: "Privacy Policy · EventPulse24",
  description: "What EventPulse24 stores, for how long, and who it reaches.",
};

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      lede="What we store, for how long, and who it reaches."
      lastUpdated={LEGAL_LAST_UPDATED}
      current="/privacy"
    >
      <LegalSection id="status" heading="This policy is being written">
        <p>
          This page exists because the sign-up screen, the sign-in screen and the footer
          of every public page link to it. The full policy is being drafted from the
          product&rsquo;s own code rather than from intentions: the retention windows it
          will publish are the ones the database actually enforces, and the list of
          third parties it will name is the list of services the system actually talks
          to.
        </p>
        <p>
          Two things are already true and will not change in the drafting.{" "}
          <strong className="font-semibold">
            We do not use your personal data to train AI models
          </strong>
          , and <strong className="font-semibold">we do not sell your data</strong> to
          anyone, for any price. You can export everything we hold and delete your
          account from your settings today, without asking us.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
