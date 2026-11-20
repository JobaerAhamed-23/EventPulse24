import type { Metadata } from "next";

import { ProsePage, ProseSection } from "@/components/pre-auth/prose-page";

/**
 * `/contact` — how to reach us, and what each route is actually for.
 *
 * **Unlike About, no spec asked for this.** Neither `EXPERIENCE.md` §323 nor §326 lists a
 * Contact row; it came from the mockups' chrome, as `/how` did. It is built rather than
 * removed because it earns its place twice over: the footer already linked it on eight
 * surfaces, and `/privacy` and `/terms` both ship placeholder email addresses that a real
 * page can stand behind.
 *
 * **The honest shape of this page is that most of it points back into the product.**
 * Reporting a bad listing, exporting your data and deleting your account are all things
 * a user can do themselves, immediately, without waiting on a reply — and saying so is
 * more useful than an address that answers in three days.
 *
 * **The general address is still a placeholder**, and this page says so in the same words
 * the legal pages use. It stops being one when a real inbox exists.
 */
export const metadata: Metadata = {
  title: "Contact · EventPulse24",
  description: "How to reach EventPulse24, and what you can do without us.",
};

export default function ContactPage() {
  return (
    <ProsePage
      title="Contact"
      lede="Most things you might write to us about, you can do yourself in seconds. Here is both."
      current="/contact"
    >
      <ProseSection id="wrong-event" heading="An event is wrong, moved or cancelled">
        <p>
          Report it from the event itself — there is a control on every event page. That
          goes into our editorial queue with your report attached, which is faster and
          more precise than an email, because we can see exactly which listing you mean.
        </p>
        <p>
          Listings come from other people&rsquo;s sites and feeds, so this is the single
          most useful thing anyone sends us.
        </p>
      </ProseSection>

      <ProseSection id="your-data" heading="Something about your data">
        <p>
          You do not need us for most of it.{" "}
          <a href="/settings/account" className="underline underline-offset-4">
            Settings &rarr; Account
          </a>{" "}
          exports everything we hold.{" "}
          <a href="/settings/privacy" className="underline underline-offset-4">
            Settings &rarr; Privacy
          </a>{" "}
          lists exactly what we store and for how long, and deletes your account — with 30
          days to change your mind.
        </p>
        <p>
          For anything those do not cover, including a formal data-protection request,
          write to{" "}
          <span className="text-ink-primary">privacy@eventpulse24.example</span>.
        </p>
      </ProseSection>

      <ProseSection id="billing" heading="Billing and subscriptions">
        <p>
          Manage or cancel Pro from{" "}
          <a href="/settings/account" className="underline underline-offset-4">
            Settings &rarr; Account
          </a>
          , which opens our payment provider&rsquo;s billing portal. Cancelling stops
          future charges and Pro keeps working until the end of the period you have
          already paid for.
        </p>
      </ProseSection>

      <ProseSection id="everything-else" heading="Everything else">
        <p>
          Questions, problems, or something we have got wrong:{" "}
          <span className="text-ink-primary">hello@eventpulse24.example</span>. Questions
          about the{" "}
          <a href="/terms" className="underline underline-offset-4">
            Terms
          </a>
          : <span className="text-ink-primary">legal@eventpulse24.example</span>.
        </p>
        <p className="text-ink-muted [font:var(--type-scale-meta-md)]">
          Those addresses are placeholders, and they are marked as such for the same
          reason the drafts on our Terms and Privacy pages are: the real inboxes land with
          legal review, and we would rather say so than publish an address that bounces.
          The in-product routes above all work today.
        </p>
      </ProseSection>
    </ProsePage>
  );
}
