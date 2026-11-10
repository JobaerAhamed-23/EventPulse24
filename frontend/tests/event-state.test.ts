// @vitest-environment node
/**
 * The event-state table, checked against the backend's vocabulary and against the
 * surfaces that use it.
 *
 * **The vocabulary is the backend's.** `Event.Status` is a Django `TextChoices` in
 * `backend/apps/ingestion/models.py`, and it reaches the frontend as `status` on the
 * digest card and on the public page. The frontend cannot import Python, so the words
 * are restated in `lib/event-state.ts` — and this test is what stops the restatement
 * from going stale.
 *
 * **The restatement has two halves, and both are checked here.**
 *
 * 1. **The vocabulary.** Every status the backend can send is either one the frontend
 *    has a line for or one the frontend deliberately says nothing about. A backend status
 *    that arrives with no frontend line is not an error — `scheduled` and `superseded`
 *    are both silent on purpose — but a status the frontend has a *word* for and the
 *    backend does not have is a sentence about a state that cannot occur.
 * 2. **The duplication.** The sentences used to live in `public-event-page.tsx` and were
 *    copied into the city card and the Detail page. This test reads those files and
 *    fails if a literal copy of a sentence reappears — the point of the table is that
 *    there is exactly one copy of each sentence.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { SOLD_OUT_LABEL, SOLD_OUT_LINE, cardStateFor, statusLineFor } from "@/lib/event-state";

const ROOT = path.resolve(__dirname, "..");

/**
 * The source with its comments removed.
 *
 * **A comment is not code.** The card's docstrings quote the spec — including the
 * sentences this file exists to keep from being copied — and a source-text assertion
 * that read them would be asserting on prose. So the comments come out first, and what
 * is left is what the compiler sees. This is the same rule
 * `tests/pulse-card-boundary.test.ts` applies.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

/**
 * The backend's `Event.Status` choices, read from the Django model.
 *
 * **The `Event` class is named, because there are two `Status` choices classes in this
 * file.** `Source.Status` is `active` / `paused` — a registry entry's state — and
 * `Event.Status` is the event's lifecycle. A regex that took the first match would read
 * the registry's and compare it against the frontend's event vocabulary, and every
 * assertion below would be about the wrong thing.
 */
function backendStatuses(): string[] {
  const source = readFileSync(path.resolve(ROOT, "../backend/apps/ingestion/models.py"), "utf8");
  const event = /class Event\(UUIDv7Model\):([\s\S]*?)\n    class Meta:/.exec(source);
  if (!event) throw new Error("backend Event model not found");

  const block = /class Status\(models\.TextChoices\):([\s\S]*?)\n\n/.exec(event[1]);
  if (!block) throw new Error("backend Event.Status choices not found");

  return [...block[1].matchAll(/^\s+([A-Z_]+)\s*=\s*"([^"]+)"/gm)].map((match) => match[2]);
}

/** The statuses the frontend says nothing about, on purpose. */
const SILENT_BY_DESIGN = ["scheduled", "superseded"];

describe("the event-state vocabulary", () => {
  it("reads the backend's status choices", () => {
    // A guard that silently matched nothing would pass every assertion below.
    const statuses = backendStatuses();
    expect(statuses.length).toBeGreaterThan(0);
    expect(statuses).toContain("cancelled");
    expect(statuses).toContain("postponed");
  });

  it("says nothing about a status it has no line for", () => {
    for (const status of backendStatuses()) {
      if (SILENT_BY_DESIGN.includes(status)) {
        expect(statusLineFor(status), status).toBeNull();
      }
    }
  });

  it("has a line for every status that is not silent by design", () => {
    for (const status of backendStatuses()) {
      if (SILENT_BY_DESIGN.includes(status)) continue;
      expect(statusLineFor(status), status).not.toBeNull();
    }
  });

  it("says nothing about a status the backend does not have", () => {
    // ASSUMPTION-9: a status this system has never heard of is a fact the frontend
    // cannot put into words. Rendering one as "unknown" would invent a claim.
    expect(statusLineFor("rescheduled_for_tuesday")).toBeNull();
    expect(statusLineFor("")).toBeNull();
    expect(statusLineFor(null)).toBeNull();
    expect(statusLineFor(undefined)).toBeNull();
  });

  it("gives a status line that says what the state means", () => {
    // A bare "Cancelled" would leave the reader to work out whether the event is off,
    // moved, or merely renamed. The public page wrote these as sentences and they stay
    // sentences.
    expect(statusLineFor("cancelled")).toBe("Cancelled — this event is not happening.");
    expect(statusLineFor("postponed")).toBe(
      "Postponed — this event is not happening at the time shown.",
    );
  });

  it("gives a status line that ends in a full stop", () => {
    // The sentence is read aloud by a screen reader, and a line that runs into the next
    // one on the card would be announced as a single run-on.
    for (const status of ["cancelled", "postponed"]) {
      expect(statusLineFor(status), status).toMatch(/\.$/);
    }
  });
});

describe("the sold-out words", () => {
  it("says the event exists and its tickets are gone", () => {
    expect(SOLD_OUT_LINE).toBe("Sold out — tickets no longer available.");
    expect(SOLD_OUT_LABEL).toBe("Sold out");
  });
});

describe("the card's state", () => {
  it("is null when there is nothing to say", () => {
    // `scheduled` is silent by design, and so is a card with no status at all.
    expect(cardStateFor("scheduled", false)).toBeNull();
    expect(cardStateFor(null, false)).toBeNull();
    expect(cardStateFor(undefined, null)).toBeNull();
  });

  it("is null for a status the frontend has no word for", () => {
    // ASSUMPTION-9, on the badge as well as on the sentence.
    expect(cardStateFor("rescheduled_for_tuesday", false)).toBeNull();
    // Even when the flag is set — the sold-out state is still a state this system can
    // put into words, so it is shown; the unknown status is simply not added to it.
    expect(cardStateFor("rescheduled_for_tuesday", true)).toBe("sold_out");
  });

  it("is the sold-out state when the flag is set", () => {
    expect(cardStateFor("scheduled", true)).toBe("sold_out");
    expect(cardStateFor(null, true)).toBe("sold_out");
  });

  it("is the lifecycle state when there is one", () => {
    // **The lifecycle state wins over the sold-out flag.** The backend keeps sold-out as
    // a *separate boolean* precisely because an event can be scheduled and sold out at
    // the same time — so the frontend keeps both fields and only the badge picks one.
    //
    // **It picks the cancellation**, because a badge reading "Sold out" on a cancelled
    // event would invite a reader to wait for tickets for an event that is not
    // happening.
    expect(cardStateFor("cancelled", false)).toBe("cancelled");
    expect(cardStateFor("cancelled", true)).toBe("cancelled");
    expect(cardStateFor("postponed", false)).toBe("postponed");
    expect(cardStateFor("postponed", true)).toBe("postponed");
  });
});

describe("the sentences are not copied", () => {
  /**
   * The files that render these facts.
   *
   * **Every one of them must import the table.** The whole point of moving the
   * sentences into `lib/event-state.ts` is that there is exactly one copy of each; a
   * second literal is how the two drift apart, and how a fix to one surface leaves the
   * other showing the old words.
   *
   * **The badge is in the list**, and it is the most likely place for a copy to
   * reappear: it renders a state's *label*, so a literal "Sold out" written straight
   * into the component would look entirely reasonable and would quietly fork the
   * vocabulary. The badge reads `STATE_LABELS` for the same reason.
   *
   * **The Detail page is in the list because it renders the status line too.** It
   * used to render only the sold-out sentence, while the public page rendered the
   * cancelled and postponed ones — two surfaces, two vocabularies, for one fact. Both
   * now ask the shared table the same question.
   */
  const CONSUMERS = [
    "components/public-event/public-event-page.tsx",
    "components/city-page/city-event-card.tsx",
    "app/events/[id]/page.tsx",
    "components/digest/pulse-card.tsx",
    "components/state/event-state-badge.tsx",
  ];

  it.each(CONSUMERS)("%s reads the shared table", (relative) => {
    const source = readFileSync(path.join(ROOT, relative), "utf8");
    expect(source, relative).toContain("@/lib/event-state");
  });

  it.each(CONSUMERS)("%s holds no literal copy of the sold-out line", (relative) => {
    const source = withoutComments(readFileSync(path.join(ROOT, relative), "utf8"));
    // The table's own name is allowed; the sentence is not.
    expect(source, relative).not.toContain("tickets no longer available");
  });

  it.each(CONSUMERS)("%s holds no literal copy of a status line", (relative) => {
    const source = withoutComments(readFileSync(path.join(ROOT, relative), "utf8"));
    expect(source, relative).not.toContain("this event is not happening");
  });

  it.each(CONSUMERS)("%s holds no literal copy of a state label", (relative) => {
    const source = withoutComments(readFileSync(path.join(ROOT, relative), "utf8"));
    // The *labels* are as much a vocabulary as the sentences are. A literal
    // "Cancelled" in a component would look right and would fork the table.
    expect(source, relative).not.toMatch(/["'`]Cancelled["'`]/);
    expect(source, relative).not.toMatch(/["'`]Postponed["'`]/);
  });
});
