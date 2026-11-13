"use client";

import { quotaNote } from "@/lib/browse-labels";
import type { BrowseQuota } from "@/lib/browse-read";

import { useBrowseQuota } from "@/components/browse/browse-quota-provider";

/**
 * The hero's quota note — the sign above the gate.
 *
 * ## Why it is an island and not part of the hero
 *
 * **The hero is a server component and the note has to move.** The hero renders the
 * server's payload, and the payload's allowance is true *when the page was rendered*.
 * The allowance moves while the reader is on the page — one save spends it — and a note
 * that cannot move is a note that lies. So the note is a small client island that reads
 * the live allowance from the provider, and the provider asks the server again whenever
 * a save lands.
 *
 * **The rest of the hero stays a server component.** The eyebrow, the h1, the lede and
 * the city-meta pill are all facts the server stated and the client does not second-
 * guess. Only the allowance moves under the reader's hands, so only the allowance is
 * an island. Moving the whole hero into the client would make it a client bundle for
 * one number that changes.
 *
 * ## What it says
 *
 * **The server's numbers, in the server's own vocabulary.** `quotaNote()` is the
 * translation from the payload to the sentence, and it is the same function the hero
 * used before the note became an island — so the wording did not change with the
 * plumbing. A Pro account has no cap and the note says so; a Free account's note is
 * "0 of 1 save used today · resets in 24h".
 *
 * **It is a status line, so it is in mono and it is quiet.** The design puts it in
 * `{family.mono}`, and it is muted ink — it is information about the account, not prose.
 *
 * **The line is the note and nothing else.** There is no button here and no link: the
 * note says what the allowance stands at, and the way to change the allowance is the
 * pricing page, which the *refusal* links to rather than this line. A line that linked
 * to Upgrade on every page would be a sales pitch on a page whose whole point is that
 * it is not one.
 */
export function BrowseQuotaNote({ fallback }: { fallback: BrowseQuota }) {
  const live = useBrowseQuota();
  // **The live allowance wins; the payload's is the fallback.** On the Browse page the
  // provider is present, so the note tracks the server's latest answer. Rendered
  // without one — a test, or the hero on its own — it still states the number the
  // payload carried rather than nothing.
  const quota = live?.quota ?? fallback;
  const note = quotaNote(quota);

  return (
    <p
      className="mt-4 [font-family:var(--type-family-mono)] text-ink-muted [font:var(--type-scale-meta-sm)]"
      data-browse-quota
    >
      {note.text}
    </p>
  );
}
