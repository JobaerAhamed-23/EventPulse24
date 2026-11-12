import Link from "next/link";

import { eventCountLabel, quotaNote } from "@/lib/browse-labels";
import type { BrowseOut } from "@/lib/browse-read";

/**
 * The Browse hero — Amendment A-12's `component.hero.citypage` vocabulary, inside the
 * authed shell.
 *
 * **It inherits the pre-auth city page's *structure* and refuses its conversion
 * scaffolding.** The city page is a stranger's landing page: it has a Sign-up row, a
 * How-it-works CTA and an SEO neighbour-cities footer, because a stranger has to be
 * converted and a crawler has to be fed. Browse is a signed-in surface — the reader is
 * already a user — so that scaffolding would be a lie about who is looking, and it is
 * **absent from the markup entirely**, not hidden with CSS.
 *
 * **The eyebrow's dot is terracotta; its text is muted.** `DESIGN.md` says "terracotta
 * 6×6 dot glyph + 'Brooklyn · Tonight + 7 days' in `{color.ink.muted}`" — the *dot*
 * carries the accent and the *text* stays in ink. The built city page puts the whole
 * line in terracotta, which is the pre-auth voice: on a public page the eyebrow is a
 * flourish, and here it is a label.
 *
 * **The quota note reads the API, and states only what the API carries.** The server
 * reports the allowance *without spending it* — the save gate is a separate call — so
 * the note is a sign above the gate, not the gate. The client never refuses a save on
 * the strength of this string.
 */
export type BrowseHeroProps = {
  /** The server's payload. The hero renders it and decides nothing. */
  browse: BrowseOut;
};

export function BrowseHero({ browse }: BrowseHeroProps) {
  const city = browse.city;
  const quota = quotaNote(browse.quota);

  return (
    <section aria-label={`Events in ${city}`} data-browse-hero>
      {/*
        **The eyebrow.** The city, and the window the listing covers.

        **The dot is decorative** — `aria-hidden`, because the text beside it already says
        what the eyebrow says. A screen reader that heard "Brooklyn · Tonight + 7 days"
        twice would be reading the design's decoration aloud.
      */}
      <p className="flex items-center gap-2 uppercase [font:var(--type-scale-meta-sm)] tracking-[0.12em] text-ink-muted">
        <span aria-hidden="true" className="size-[6px] rounded-full bg-accent-terracotta" />
        {city} · Tonight + 7 days
      </p>

      {/*
        **The h1.** The city is in a terracotta italic `<em>`.

        **`<em>` is an emphasis element, and it carries the meaning here**: the city is
        the one word in the line that is the point. It is not a `<span>` with a colour
        class, because a screen reader would then read "Events in Brooklyn" with no
        indication that the city is the emphasised part.
      */}
      <h1 className="mt-4 text-ink-primary [font:var(--type-scale-display-lg)] tracking-[-0.025em]">
        Events in <em className="text-accent-terracotta italic">{city}.</em>
      </h1>

      {/*
        **The lede.** It says what the surface is, in the reader's terms, and claims no
        numbers the payload does not carry. The "Tap Save" invitation is true — the cards
        carry a Save affordance.
      */}
      <p className="mt-4 max-w-[600px] text-ink-secondary [font:var(--type-scale-body-lg)]">
        Browse what&apos;s happening nearby. Tap Save to add it to your Pulse.
      </p>

      {/*
        **The city-meta pill.** The city, the count, and the way out.

        **The count is the pool's size**, which is what the user can page to — not a
        `COUNT(*)` that would count rows the staleness bound then drops.

        **"Change city" is a real link**, and it goes to `/settings/account`: the city is
        the digest preference's city, and account settings is where the preference lives.
        A control that goes nowhere is a lie about what the page can do.
      */}
      <p
        className="mt-8 inline-flex flex-wrap items-center gap-x-4 gap-y-1 rounded-full border border-border-subtle bg-surface-elevated px-4 py-2 text-ink-secondary [font:var(--type-scale-body-sm)]"
        data-browse-city-meta
      >
        <span className="text-ink-primary">
          <span aria-hidden="true">📍</span> {city}
        </span>
        <span aria-hidden="true" className="text-ink-faint">
          ·
        </span>
        <span>{eventCountLabel(browse.total)}</span>
        <span aria-hidden="true" className="text-ink-faint">
          ·
        </span>
        <Link
          href="/settings/account"
          className="text-accent-terracotta underline underline-offset-4"
          data-browse-change-city
        >
          Change city
        </Link>
      </p>

      {/*
        **The quota note.** In mono, because it is a status line and not prose — the
        design puts it in `{family.mono}` and the city page's own meta lines agree.

        **It states a duration, not a clock time.** The payload carries
        `resets_in_seconds`, so the note says "resets in 24h". The mockup's "resets 8:00
        AM" is a wall-clock claim from a persona, and it would be wrong for every user
        but that persona.
      */}
      <p
        className="mt-4 [font-family:var(--type-family-mono)] text-ink-muted [font:var(--type-scale-meta-sm)]"
        data-browse-quota
      >
        {quota.text}
      </p>
    </section>
  );
}
