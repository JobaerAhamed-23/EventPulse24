import type { Metadata } from "next";

import { ProsePage, ProseSection } from "@/components/pre-auth/prose-page";

/**
 * `/about` — what EventPulse24 is, and the bet it is making.
 *
 * **§326 asked for this link and nobody built the page.** The canonical pre-auth footer
 * bullet names *"Login, Privacy, Terms, About, social links, city nav, 'Made in [city]'
 * provenance"*, and About has rendered as `href="#"` on all eight pre-auth surfaces since
 * the footer shipped. A `#` is not a 404, so the link guard never saw it — which is how a
 * promised page stays unbuilt without anything going red.
 *
 * **The copy is drawn from PRD §1 and §15.2**, not invented: the calm-intelligence
 * positioning, the deliberate misalignment with engagement-optimised products, and the
 * "no ads, no commissions, no data sales" commitment. Where this page makes a claim about
 * behaviour — one notification a day, three cards, no open tracking — the claim is one the
 * product actually keeps and the privacy policy documents.
 *
 * **No draft banner.** This is not a legal document, and `ProsePage` is the frame without
 * one.
 */
export const metadata: Metadata = {
  title: "About · EventPulse24",
  description: "Why EventPulse24 sends you less, on purpose.",
};

export default function AboutPage() {
  return (
    <ProsePage
      title="About EventPulse24"
      lede="A calm layer above every event source — built to send you less, on purpose."
      current="/about"
    >
      <ProseSection id="problem" heading="The problem">
        <p>
          Events are not hard to find. They are impossible to filter. The concert you
          would have loved was announced in a feed you do not read; the meetup you care
          about was buried under forty you do not; and the app that was going to help
          sent you a notification every afternoon until you turned it off.
        </p>
        <p>
          Meanwhile your own calendar — the birthdays, the meetings, the weekend already
          spoken for — sits somewhere else entirely, so nothing you are shown knows
          whether you are even free.
        </p>
      </ProseSection>

      <ProseSection id="what-we-do" heading="What we do about it">
        <p>
          We gather public events from across the open web, work out which few might
          actually matter to you, and tell you once a day. Three cards. Not a feed.
        </p>
        <p>
          Your own events sit beside them on one timeline, so when something clashes we
          can say so before you commit. And every card shows why it is there and where it
          came from, because a recommendation you cannot interrogate is just an
          advertisement with better manners.
        </p>
      </ProseSection>

      <ProseSection id="calm" heading="Why we send you less">
        <p>
          Most products in this category are measured on engagement, which means the
          winning move is always one more notification. We think that is why nobody
          trusts them.
        </p>
        <p>
          So we measure the opposite. One daily summary rather than a stream. Reminders
          you choose per event, which respect quiet hours. No badge counts invented to
          pull you back. <strong className="font-semibold">
            If we are doing this well, you hear from us less over time, not more.
          </strong>
        </p>
      </ProseSection>

      <ProseSection id="how-we-make-money" heading="How we make money">
        <p>
          A subscription. That is the whole model.
        </p>
        <p>
          <strong className="font-semibold">No ads. No commissions. No data sales.</strong>{" "}
          We do not take a cut of ticket sales, because the moment we do we start showing
          you events that pay rather than events that fit. We do not sell what we know
          about you, and we do not use your data to train AI models. The{" "}
          <a href="/privacy" className="underline underline-offset-4">
            Privacy Policy
          </a>{" "}
          sets out exactly what we store and who sees it.
        </p>
      </ProseSection>

      <ProseSection id="honesty" heading="What we cannot promise">
        <p>
          Almost every listing here was published by someone else. Events get moved,
          cancelled and sold out, and the places that announce them do not always say so.
          We show how confident we are and where each listing came from, and we would
          rather tell you we are unsure than pretend otherwise.
        </p>
        <p>
          Check with the organiser before you travel or pay. If you find something wrong,
          report it from the event — that goes to a real queue that real corrections come
          out of.
        </p>
      </ProseSection>
    </ProsePage>
  );
}
