import type { Metadata } from "next";

import { LegalPage, LegalSection } from "@/components/legal/legal-page";
import { RETENTION_ROWS } from "@/lib/retention-categories";
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
 * ## Every claim here was read out of running code
 *
 * The retention table is `RETENTION_ROWS`, a mirror of `backend/shared/retention.py`
 * pinned to it by `backend/tests/shared/test_retention_published.py` — add a category or
 * change a window and that test fails until this page follows. The 30-day figure is
 * `DELETION_GRACE_PERIOD`. The list of third parties is the contents of
 * `backend/adapters/`. What survives deletion is `SURVIVING_CATEGORIES`.
 *
 * **Two of PRD §10.2's nine published categories are deliberately absent.**
 * `EMAIL_DELIVERY_EVENTS` and `ANALYTICS_AGGREGATES` have no models: the open-and-click
 * store is not built (`apps/delivery/email_api.py`) and there is no analytics vendor in
 * the codebase at all. Publishing their windows would describe a product that watches
 * more than this one does.
 *
 * **One claim §10.2 makes is not repeated here.** It says that where the LLM provider's
 * terms permit opting out of training-data retention, the system is configured to opt
 * out. `adapters/llm/voyage.py` contains no such configuration. So this page says only
 * what is true: we do not train on your data, and the embedding provider never receives
 * any of it.
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
      <LegalSection id="summary" heading="The short version">
        <p>
          EventPulse24 collects what it needs to show you events worth your attention,
          and stops there. We do not sell your data. We do not use it to train AI
          models. We do not track whether you open our emails, and we run no analytics
          or advertising tracker of any kind. You can export everything we hold, or
          delete your account, without asking us.
        </p>
        <p>
          The rest of this page is the detail behind those sentences, including the
          parts that are less flattering &mdash; what we keep after you leave, and why.
        </p>
      </LegalSection>

      <LegalSection id="what-we-store" heading="What we store, and for how long">
        <p>
          Every table in our database is tagged with a retention category, and the
          tagging is enforced: the application refuses to start if any table is
          untagged. The table below is generated from those same categories, so it
          describes what the database actually does rather than what we intend.
        </p>
        <div className="flex flex-col gap-6">
          {RETENTION_ROWS.map((row) => (
            <div key={row.key}>
              <h3 className="text-ink-primary [font:var(--type-scale-body-md)] font-semibold">
                {row.label}
              </h3>
              <p className="mt-1">{row.holds}</p>
              <p className="mt-1 text-ink-muted [font:var(--type-scale-meta-md)]">
                {row.window} <span aria-hidden="true">&middot;</span>{" "}
                <span>If you delete your account: {row.onDelete.toLowerCase()}</span>
              </p>
            </div>
          ))}
        </div>
      </LegalSection>

      <LegalSection id="what-we-do-not-collect" heading="What we do not collect">
        <p>
          Some things are worth naming because most products in this category do collect
          them.
        </p>
        <p>
          <strong className="font-semibold">We do not track email opens or clicks.</strong>{" "}
          There is no tracking pixel in our emails and no table recording that you read
          one. We know we sent it; we do not know whether you looked.
        </p>
        <p>
          <strong className="font-semibold">We run no analytics product.</strong> There
          is no Google Analytics, no Segment, no Mixpanel, no session recorder and no
          advertising pixel anywhere in this application.
        </p>
        <p>
          <strong className="font-semibold">
            We do not send your location to anyone.
          </strong>{" "}
          When we guess your city, we read a single value our own content network
          attaches to the request. We do not look your address up with a geo-IP vendor,
          because that would mean handing your address to a third party on every page
          load. You can turn the guess off, and we will ask before using it.
        </p>
      </LegalSection>

      <LegalSection id="who-else-sees-it" heading="Who else sees your data">
        <p>
          Six outside services are involved in running EventPulse24. This is the whole
          list.
        </p>
        <p>
          <strong className="font-semibold">Stripe</strong> handles payments, and
          receives what a payment needs. We never see or store your card number.{" "}
          <strong className="font-semibold">Our email provider</strong> receives your
          address and the message, in order to deliver it.{" "}
          <strong className="font-semibold">Our file storage</strong> holds your profile
          picture if you upload one.
        </p>
        <p>
          <strong className="font-semibold">Voyage AI</strong> turns event descriptions
          into the numbers that let us tell similar events apart. It receives{" "}
          <strong className="font-semibold">
            public event titles and descriptions only
          </strong>{" "}
          &mdash; never your personal events, your saved events, or anything we know
          about your taste.
        </p>
        <p>
          <strong className="font-semibold">Your calendar host</strong> is contacted only
          if you connect a calendar, and only at the address you gave us.{" "}
          <strong className="font-semibold">Our content network</strong> serves the site
          and tells us the city a request came from.
        </p>
        <p>
          <strong className="font-semibold">We do not sell your data</strong>, share it
          for advertising, or give it to data brokers. Not now, and not later: it is a
          commitment, not a current practice.
        </p>
      </LegalSection>

      <LegalSection id="ai" heading="AI, and what it is not trained on">
        <p>
          We do not use your personal data to train, fine-tune or improve any AI model,
          ours or anyone else&rsquo;s. There is no training pipeline in this product, and
          the one AI service we use receives only public event text.
        </p>
        <p>
          What AI does here is narrow: it reads public event listings so we can recognise
          when two sources are describing the same event, and so we can tell that a jazz
          night resembles another jazz night. It does not read your calendar, and it does
          not decide anything about you.
        </p>
      </LegalSection>

      <LegalSection id="your-rights" heading="Your rights, and where to use them">
        <p>
          <strong className="font-semibold">Export everything we hold.</strong> Settings
          &rarr; Account. We prepare the file and email you when it is ready.
        </p>
        <p>
          <strong className="font-semibold">Delete your account.</strong> Settings &rarr;
          Privacy. See the next section for exactly what happens.
        </p>
        <p>
          <strong className="font-semibold">Correct your details.</strong> Settings &rarr;
          Profile, for your name, email address and picture.
        </p>
        <p>
          Depending on where you live, you may also have the right to object to
          processing, to restrict it, or to complain to a data protection authority. You
          do not need to go through us to do that last one, and we would rather you told
          us first.
        </p>
      </LegalSection>

      <LegalSection id="deletion" heading="What happens when you delete your account">
        <p>
          Deletion is not immediate, on purpose.{" "}
          <strong className="font-semibold">
            You have 30 days to change your mind
          </strong>
          , and during that window your account is marked for deletion but still intact.
          Cancelling restores it completely &mdash; including your profile picture, which
          is why we do not remove it from storage at the moment you ask. A grace period
          that could not actually restore your account would not be a grace period.
        </p>
        <p>
          After 30 days, we permanently delete your account and credentials, everything
          you made and saved, and everything we learned about your taste. Your calendar
          connection goes with it.
        </p>
        <p>
          <strong className="font-semibold">Two things survive, and you should know.</strong>{" "}
          Billing records are kept for seven years because tax law requires it. Security
          logs are kept for 24 months &mdash; these record that an action happened, not
          what it contained, and are built to identify no one.
        </p>
      </LegalSection>

      <LegalSection id="security" heading="How it is protected">
        <p>
          Your password is stored as a hash, never as a password. Calendar credentials
          are encrypted at rest. Personal events and calendar data are kept in separate
          database tables from the public event catalog, so the two cannot be mixed up by
          accident.
        </p>
      </LegalSection>

      <LegalSection id="children" heading="Children">
        <p>
          EventPulse24 is not intended for children under 13, and we do not knowingly
          collect their data. If you believe a child has created an account, tell us and
          we will remove it.
        </p>
      </LegalSection>

      <LegalSection id="changes" heading="Changes to this policy">
        <p>
          When this policy changes, the date at the top changes with it. If a change
          materially affects what we collect or who sees it, we will tell you rather than
          relying on you to re-read this page.
        </p>
      </LegalSection>

      <LegalSection id="contact" heading="Contact">
        <p>
          Questions about your data, or anything on this page:{" "}
          <span className="text-ink-primary">privacy@eventpulse24.example</span>.
        </p>
        <p className="text-ink-muted [font:var(--type-scale-meta-md)]">
          That address is a placeholder, and the draft notice at the top of this page is
          why. The real contact address lands with legal review. If you need to reach us
          before then, use the account you signed up with.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
