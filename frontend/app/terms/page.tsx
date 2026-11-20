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
 * ## The clauses describe the product, not an aspiration
 *
 * The subscription section matches `adapters/billing/stripe.py` and the portal that
 * `components/settings/plan-summary.tsx` documents — including the detail that a
 * subscription cancelled in the portal keeps reading `active` until the period it was
 * paid for ends, which is why this page says Pro runs to the end of that period rather
 * than stopping on cancellation.
 *
 * **The accuracy disclaimer is the one clause that matters most here.** FR-17 makes the
 * catalog third-party content gathered from other people's sites and feeds, and the
 * product cannot promise an event it did not create is correct. Saying so in the Terms
 * is not boilerplate; it is the honest description of what this service is.
 *
 * **Still a draft.** The banner stays until counsel reviews it. Nothing here was written
 * by a lawyer.
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
      <LegalSection id="what-this-is" heading="What EventPulse24 is">
        <p>
          EventPulse24 collects public event listings from around the web, works out
          which of them are likely to matter to you, and tells you about them once a day.
          You can also add your own events and connect a calendar so the two sit side by
          side.
        </p>
        <p>
          By creating an account you agree to these terms. If you do not agree with them,
          do not create an account &mdash; and if you already have one, you can delete it
          from Settings &rarr; Privacy at any time.
        </p>
      </LegalSection>

      <LegalSection id="accuracy" heading="We did not write the event listings">
        <p>
          <strong className="font-semibold">
            This is the most important thing on this page.
          </strong>{" "}
          Almost every event you see here came from somewhere else &mdash; a venue&rsquo;s
          website, a public calendar, an organiser&rsquo;s feed. We gather it, tidy it up
          and try to tell when two sources are describing the same thing. We did not
          create it and we cannot vouch for it.
        </p>
        <p>
          Events get cancelled, moved, sold out and rescheduled, and the places that
          publish them do not always say so. We show you what we were told, with how
          confident we are and where it came from. <strong className="font-semibold">
            Check with the organiser before you travel, pay, or rely on anything here.
          </strong>
        </p>
        <p>
          If you find something wrong, report it from the event page. That is a real
          queue that real changes come out of.
        </p>
      </LegalSection>

      <LegalSection id="your-account" heading="Your account">
        <p>
          Keep your password to yourself, and tell us if you think someone else has it.
          You are responsible for what happens under your account.
        </p>
        <p>
          One person, one account. You need to be 13 or older to use EventPulse24.
        </p>
      </LegalSection>

      <LegalSection id="acceptable-use" heading="Using the service">
        <p>
          Use EventPulse24 for finding events and managing your own calendar. Do not
          scrape it, resell its contents, or use it to build a competing catalog &mdash;
          the listings are gathered under agreements with the sources they came from, and
          those agreements are not transferable.
        </p>
        <p>
          Do not attack the service, work around its limits, or use it to harass anyone.
          Do not upload anything to your profile that you do not have the right to use.
        </p>
      </LegalSection>

      <LegalSection id="your-content" heading="What you add stays yours">
        <p>
          Your personal events, your saved lists, your collections and your profile
          picture remain yours. You give us permission to store and display them back to
          you, which is what makes the product work, and nothing beyond that. We do not
          publish them, sell them, or use them to train AI models.
        </p>
      </LegalSection>

      <LegalSection id="pro" heading="Pro subscriptions">
        <p>
          EventPulse24 is free to use. Pro adds features and is billed through Stripe,
          our payment provider, on the period you choose at checkout.
        </p>
        <p>
          You can manage or cancel your subscription at any time from Settings &rarr;
          Account, which opens Stripe&rsquo;s billing portal.{" "}
          <strong className="font-semibold">
            Cancelling stops future charges and Pro keeps working until the end of the
            period you have already paid for.
          </strong>{" "}
          We do not charge you again after that.
        </p>
        <p>
          If a payment fails we will tell you in the app and the portal is where to fix
          it. Prices can change, and we will tell you before a change affects you.
        </p>
      </LegalSection>

      <LegalSection id="ending" heading="Ending things">
        <p>
          You can delete your account whenever you like, from Settings &rarr; Privacy.
          You get 30 days to change your mind before anything is permanently removed, and
          the Privacy Policy explains exactly what is deleted and what is kept.
        </p>
        <p>
          We may suspend or close an account that breaks these terms, or that we are
          legally required to act on. Except where something is seriously or repeatedly
          wrong, we will tell you first and give you a chance to put it right.
        </p>
      </LegalSection>

      <LegalSection id="liability" heading="What we can and cannot promise">
        <p>
          We work to keep EventPulse24 running and accurate, but we provide it as it is.
          We do not promise it will never be unavailable, never miss an event, or never
          get one wrong &mdash; and because the listings come from other people, we
          cannot be responsible for a missed concert, a cancelled show, or a wasted
          journey.
        </p>
        <p>
          Nothing in these terms limits rights you have under the law where you live, and
          in some places those rights cannot be signed away. Where that is so, those
          rights win over anything on this page.
        </p>
      </LegalSection>

      <LegalSection id="changes" heading="Changes to these terms">
        <p>
          When these terms change, the date at the top changes with them. If a change
          materially affects what you have agreed to, we will tell you rather than
          relying on you to re-read this page.
        </p>
      </LegalSection>

      <LegalSection id="contact" heading="Contact">
        <p>
          Questions about these terms:{" "}
          <span className="text-ink-primary">legal@eventpulse24.example</span>.
        </p>
        <p className="text-ink-muted [font:var(--type-scale-meta-md)]">
          That address is a placeholder, and the draft notice at the top of this page is
          why. The real contact address lands with legal review.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
