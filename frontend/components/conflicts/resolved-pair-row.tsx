import { cardTime } from "@/lib/detail-time";
import { resolutionPhrase, type ConflictSide } from "@/lib/conflict-wording";
import type { ConflictPair } from "@/lib/conflict-list-read";

/**
 * One resolved conflict pair: history.
 *
 * **A resolved pair is immutable.** The system never re-prompts for a pair the user has
 * already decided on, so this row carries **no edit affordance at all** — no button, no
 * link, nothing focusable. A control that re-opened a decided pair would be a control
 * that lies about what it does.
 *
 * **The line says what was decided, in the words the user chose.** "Skipped public ·
 * Poetry reading · Fri Sep 11" — the past tense of the decision, the event it was
 * about, and when. The wording comes from the shared module, so it is the same
 * vocabulary the active row's buttons use.
 */
export function ResolvedPairRow({ pair }: { pair: ConflictPair }) {
  // **The event the decision was about.** `skip_public` and `delete_new` are about one
  // side; `edit_new` and `update_existing` are about a personal one; `keep_both` is
  // about neither. The first is the pair's public side when it has one, because that
  // is the event the "Skipped public" line names.
  const subject = pair.right.kind === "saved_event" ? pair.right : pair.left;
  const when = cardTime(subject.start_time_utc, subject.start_time_tz);
  const day = when ? when.split(" · ")[0] : null;

  return (
    <div className="flex flex-col gap-2 border-b border-border-subtle px-4 py-3 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        <SideStripe side={pair.left} />
        <span className="[font:var(--type-scale-body-sm)] text-ink-primary">
          {sideTitle(pair.left)}
        </span>
        <span aria-hidden="true" className="text-ink-muted">
          ↔
        </span>
        <SideStripe side={pair.right} />
        <span className="[font:var(--type-scale-body-sm)] text-ink-primary">
          {sideTitle(pair.right)}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 [font:var(--type-scale-meta-sm)] text-ink-muted">
        {/*
          The dot is decorative — the words beside it say what was decided, so the colour
          is never the only carrier of the meaning.
        */}
        <span aria-hidden="true" className="size-[6px] rounded-full bg-signal-success" />
        <span>
          {resolutionPhrase(pair.resolution)}
          {subject.name ? ` · ${subject.name}` : ""}
          {day ? ` · ${day}` : ""}
        </span>
      </div>
    </div>
  );
}

/**
 * A side's stripe.
 *
 * **The same 8px square the mockup uses** — and it is `aria-hidden`, because the name
 * beside it carries the meaning. The stripe is the second signal, never the only one.
 */
function SideStripe({ side }: { side: ConflictSide }) {
  return (
    <span
      aria-hidden="true"
      className={[
        "inline-block size-2 shrink-0 rounded-[2px]",
        side.kind === "personal_event" ? "bg-warm-personal" : "bg-accent-slate",
      ].join(" ")}
    />
  );
}

/** A side's name, or the honest line for one that cannot be read. */
function sideTitle(side: ConflictSide): string {
  if (!side.available) return "Event no longer available";
  return side.name ?? "Event no longer available";
}
