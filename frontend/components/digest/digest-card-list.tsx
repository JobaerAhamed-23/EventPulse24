"use client";

/**
 * The digest's cards, and the "less of this" prompt (FR-25).
 *
 * ## Why this is a client component
 *
 * The digest page is a server component: it reads the composed digest and renders it.
 * But FR-25's swipe is a *gesture* — it happens after the page has been delivered, in
 * the browser, on a card the server has already rendered. So the state that FR-25 needs
 * — which cards the user has swiped away, and whether the prompt is open — lives in the
 * browser, and something in the browser has to hold it.
 *
 * **This component holds it, and the page stays a server component.** The page's read
 * is still a server read, and the composition is still persisted and rendered as it
 * came (AD-10) — none of that moved into the browser. What moved is only the part that
 * could not have been on the server: the answer to a gesture.
 *
 * ## The card's removal is local, and it is honest about being local
 *
 * **A dismissed card leaves the list, and the list is the browser's.** The server's
 * composition is a record of a past decision (AD-10), and it does not change because
 * the user swiped a card on this page load — the *next* composition is what will
 * exclude it. So the removal is local state, and the card's absence says "you said no
 * to this one", which is exactly what happened.
 *
 * **The mute is different, and it is the server's.** When the prompt fires and the
 * user accepts, the mute is written to the server, and the next digest is composed
 * without that category. That write is a server fact, and the page re-reads nothing —
 * the next navigation will show it.
 *
 * ## The prompt fires once, and the server decides that
 *
 * **The client opens the prompt only when the server says `prompt_due`.** It does not
 * count dismissals, does not know the cosine threshold, and does not keep a "has this
 * cluster fired" flag — the server owns that, and a client-side counter would be a
 * second opinion about when to interrupt the user. This is the same rule the rest of
 * the digest follows: the client renders decisions, it does not make them.
 */
import { useState } from "react";

import { MutePrompt } from "@/components/digest/mute-prompt";
import { PulseCard } from "@/components/digest/pulse-card";
import type { components } from "@/lib/api/schema";
import { setCategoryMute } from "@/lib/taste-mute-write";

type DigestCard = components["schemas"]["DigestCardOut"];

export type DigestCardListProps = {
  /** The composed cards, in the server's order. */
  cards: DigestCard[];
  /** The site's public origin, resolved on the server (FR-28). */
  origin: string | null;
};

export function DigestCardList({ cards, origin }: DigestCardListProps) {
  /**
   * **The cards the user has swiped away.**
   *
   * **A set of event ids, not a filtered array.** The array stays the server's — its
   * order is the server's — and the set records what has gone. A card leaves the list
   * when its id is in the set, and the surviving cards keep the order they came in.
   */
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set());

  /**
   * **The failure line.**
   *
   * **`null` when there is no failure.** The one failure this screen can have is a
   * mute the user accepted that did not save — and it is stated plainly, with the way
   * out, because the alternative is a user who believes a preference they did not set.
   */
  const [failure, setFailure] = useState<string | null>(null);

  /**
   * **The prompt, when it is open.**
   *
   * **`null` is both "not yet" and "already answered".** The prompt fires *once* per
   * cluster, and the server decides that — so the client opens it when the server says
   * so and closes it when the user answers or dismisses it. It does not track "has this
   * cluster fired" itself, because that is the fact the server owns.
   */
  const [prompt, setPrompt] = useState<components["schemas"]["MutePromptOut"] | null>(null);

  /**
   * **Accepting the prompt writes a mute.**
   *
   * **The default duration is 30 days**, which is the mockup's default ("Mute for 30
   * days") and the middle of the server's closed set. The prompt does not offer a
   * duration picker — the mockup's button names its own duration — and the user who
   * wants a different one has the settings screen, where the row says when it ends.
   *
   * **A failed write closes the prompt anyway.** The prompt has already served its
   * purpose — it asked, and the user answered — and re-opening it would be the nag the
   * guard exists to prevent. The consequence is that the mute did not take, and the
   * user's next digest will contain the category. **The failure is not silent, though:**
   * the failure line says so, because a user who was told "yes" and got nothing is
   * worse off than one who was never asked.
   */
  const acceptPrompt = async (asked: components["schemas"]["MutePromptOut"]) => {
    setPrompt(null);
    // **A generic prompt has no category to mute.** The server sends no
    // `category_key` when the cluster did not agree on one chip, and a mute on nothing
    // would be a mute on nothing. So the generic prompt is a prompt, never a mute's
    // subject.
    const categoryKey = asked.category_key ?? null;
    if (categoryKey === null) return;
    const written = await setCategoryMute(categoryKey, 30);
    if (!written) setFailure("We couldn't save that. You can mute it in Settings → Taste.");
  };

  return (
    <>
      {/*
        The live region announces once, when the cards are in the DOM — not on the
        server, where it would be read before the cards exist. It is visually hidden
        and carries the count, so "Pulse Digest ready, 3 events for today."

        **It is the page's one `role="status"`, and it stays the only one.** The cards'
        own share confirmations are bare `aria-live="polite"` regions — two status
        regions on a page would make "which one is the page talking?" a question the
        DOM cannot answer.
      */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        Pulse Digest ready, {cards.length} events for today.
      </div>

      {failure ? (
        <p role="alert" className="mb-4 text-signal-error [font:var(--type-scale-body-sm)]">
          {failure}
        </p>
      ) : null}

      <div className="flex flex-col gap-(--layout-card-spacing-mobile) md:gap-(--layout-card-spacing-desktop)">
        {cards
          .filter((card) => !dismissed.has(card.event_id))
          .map((card) => (
            <PulseCard
              key={card.event_id}
              card={card}
              explanation={{ kind: "relevance", value: card.bucket }}
              shareOrigin={origin}
              onDismiss={(eventId) =>
                setDismissed((current) => {
                  const next = new Set(current);
                  next.add(eventId);
                  return next;
                })
              }
              onPromptDue={setPrompt}
            />
          ))}
      </div>

      {/*
        **The prompt.**

        **It is rendered by the server's copy and nothing else.** `MutePrompt` takes the
        server's `prompt` object and writes no text of its own — the title names a chip
        in the backend's vocabulary, and the description carries the server's own count.
      */}
      <MutePrompt
        open={prompt !== null}
        prompt={prompt}
        onAccept={(asked) => void acceptPrompt(asked)}
        onDismiss={() => setPrompt(null)}
      />
    </>
  );
}
