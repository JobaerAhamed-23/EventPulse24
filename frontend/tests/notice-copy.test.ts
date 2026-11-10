// @vitest-environment node
/**
 * The notice vocabulary, checked against the backend's.
 *
 * **The vocabulary is the backend's.** `domain/notices.py` owns it — `NOTICE_SUBJECTS`
 * says what a change of each kind is called, and `REMINDER_CONSEQUENCE` says what it
 * means for the user's reminders. The frontend cannot import Python, so the words are
 * restated in `lib/notice-copy.ts` — and this test is what stops the restatement from
 * going stale.
 *
 * **This is the second of two drift guards, and it works exactly like the first.**
 * `tests/event-state.test.ts` holds the *event status* vocabulary (`Event.Status`) to
 * the frontend's `lib/event-state.ts`; this one holds the *notice* vocabulary
 * (`ChangeKind`, `NOTICE_SUBJECTS`, `REMINDER_CONSEQUENCE`) to the frontend's
 * `lib/notice-copy.ts`. Two vocabularies, two guards, one rule: **a fact said in two
 * places is a fact that will be said in two different ways, and one of them will be
 * wrong.**
 *
 * **The reminder line is checked verbatim, and that is the point of the whole file.**
 * "Your reminders have been rescheduled to the new time." is a *promise* — a promise
 * about sends the server has already decided, derived from `LIFECYCLE_SEND_BEHAVIOUR`.
 * A frontend that reworded it would be making a weaker claim, and a user reading it
 * would be less sure than they should be. So the sentences must be identical, character
 * for character.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  NOTICE_CHANGE_LINES,
  NOTICE_REMINDER_LINES,
  noticeChangeLineFor,
  noticeLinesFor,
  noticeReminderLineFor,
} from "@/lib/notice-copy";

const ROOT = path.resolve(__dirname, "..");

/**
 * The source with its comments removed.
 *
 * **A comment is not code.** Three kinds of comment carry these sentences without
 * defining them:
 *
 * - the backend's module docstring, which *quotes* the sentences in its prose;
 * - the backend's `#:` comments beside each table entry;
 * - the frontend's JSX doc-comments, `{/* … *\/}`, which quote the sentences to explain
 *   why they read the way they do.
 *
 * A source-text scan that read any of those would find the sentences in the wrong
 * places — and would fail on the components that are *most* careful about them. So all
 * three come out first, and what is left is what the code actually defines.
 */
function withoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "")
    .replace(/\{?\/\*[\s\S]*?\*\/\}?/g, "")
    .replace(/"""[\s\S]*?"""/g, "")
    .replace(/#.*$/gm, "");
}

/** The backend's `domain/notices.py`, with its comments removed. */
function backendNotices(): string {
  return withoutComments(readFileSync(path.resolve(ROOT, "../backend/domain/notices.py"), "utf8"));
}

/**
 * The backend's `domain/lifecycle.py`, with its comments removed.
 */
function backendLifecycle(): string {
  return withoutComments(
    readFileSync(path.resolve(ROOT, "../backend/domain/lifecycle.py"), "utf8"),
  );
}

/**
 * The backend's `ChangeKind` members.
 *
 * **The `ChangeKind` class is named**, because `domain/lifecycle.py` holds other
 * enums. A regex that took the first match would read the wrong vocabulary, and every
 * assertion below would be about the wrong thing.
 */
function backendChangeKinds(): string[] {
  const source = backendLifecycle();
  const block = /class ChangeKind\(StrEnum\):([\s\S]*?)\n\n/.exec(source);
  if (!block) throw new Error("backend ChangeKind not found");

  return [...block[1].matchAll(/^\s+([A-Z_]+)\s*=\s*"([^"]+)"/gm)].map((match) => match[2]);
}

/**
 * The backend's `NOTICE_SUBJECTS` table, as `{kind: template}`.
 *
 * **The keys are resolved from `ChangeKind.X.value`** — the backend writes
 * `ChangeKind.CANCELLED.value: "{title} was cancelled."`, and the value is the string
 * the frontend's table is keyed by. So the two tables are compared on the same keys.
 */
function backendSubjects(): Record<string, string> {
  const source = backendNotices();
  const block = /NOTICE_SUBJECTS: dict\[str, str\] = \{([\s\S]*?)\n\}/.exec(source);
  if (!block) throw new Error("backend NOTICE_SUBJECTS not found");

  const subjects: Record<string, string> = {};
  for (const match of block[1].matchAll(/ChangeKind\.([A-Z_]+)\.value:\s*"([^"]*)"/g)) {
    subjects[match[1].toLowerCase()] = match[2];
  }
  return subjects;
}

/**
 * The backend's `REMINDER_CONSEQUENCE` table, as `{kind: sentence}`.
 */
function backendConsequences(): Record<string, string> {
  const source = backendNotices();
  const block = /REMINDER_CONSEQUENCE: dict\[str, str\] = \{([\s\S]*?)\n\}/.exec(source);
  if (!block) throw new Error("backend REMINDER_CONSEQUENCE not found");

  const consequences: Record<string, string> = {};
  for (const match of block[1].matchAll(/ChangeKind\.([A-Z_]+)\.value:\s*"([^"]*)"/g)) {
    consequences[match[1].toLowerCase()] = match[2];
  }
  return consequences;
}

describe("the notice vocabulary", () => {
  it("reads the backend's change kinds", () => {
    // A guard that silently matched nothing would pass every assertion below.
    const kinds = backendChangeKinds();
    expect(kinds.length).toBeGreaterThan(0);
    expect(kinds).toContain("cancelled");
    expect(kinds).toContain("postponed");
  });

  it("has a line for every change kind the backend defines", () => {
    // **Seven kinds, seven lines.** A kind `domain.lifecycle` gains without the
    // frontend learning it must produce *nothing*, not a wrong line — but it must also
    // not be silently forgotten, because a notice about it would render as a fallback.
    for (const kind of backendChangeKinds()) {
      expect(noticeChangeLineFor(kind), kind).not.toBeNull();
      expect(noticeReminderLineFor(kind), kind).not.toBeNull();
    }
  });

  it("has no line for a kind the backend does not have", () => {
    // ASSUMPTION-9: a kind this system has never heard of is a fact the frontend cannot
    // put into words. "Something changed." would be inventing a claim.
    expect(noticeChangeLineFor("rescheduled_for_tuesday")).toBeNull();
    expect(noticeReminderLineFor("rescheduled_for_tuesday")).toBeNull();
    expect(noticeChangeLineFor("")).toBeNull();
    expect(noticeReminderLineFor(null as unknown as string)).toBeNull();
    expect(noticeReminderLineFor(undefined as unknown as string)).toBeNull();
  });

  it("names the same kinds the backend names, and no others", () => {
    // The tables are keyed the same way, so a kind added on one side and forgotten on
    // the other is caught here.
    expect(Object.keys(NOTICE_CHANGE_LINES).sort()).toEqual(backendChangeKinds().slice().sort());
    expect(Object.keys(NOTICE_REMINDER_LINES).sort()).toEqual(backendChangeKinds().slice().sort());
  });
});

describe("the reminder consequence is the backend's, verbatim", () => {
  it("matches the backend's table, character for character", () => {
    // **This is the assertion that matters most in the whole file.**
    //
    // The backend's sentence is a *promise* about sends it has already decided, and it
    // derives it from `LIFECYCLE_SEND_BEHAVIOUR` precisely so the body cannot promise
    // something the send machinery did not do. A frontend that reworded it would be
    // making a weaker — or a different — claim, and a user reading it would be less
    // sure than they should be about whether their reminder still fires.
    const backend = backendConsequences();
    expect(Object.keys(backend).length).toBeGreaterThan(0);

    for (const [kind, sentence] of Object.entries(backend)) {
      expect(NOTICE_REMINDER_LINES[kind as keyof typeof NOTICE_REMINDER_LINES], kind).toBe(
        sentence,
      );
    }
  });

  it("says what happened to the reminders, and it says it as a sentence", () => {
    for (const [kind, sentence] of Object.entries(NOTICE_REMINDER_LINES)) {
      // A sentence, with a full stop — so it reads as its own line on the banner and is
      // not announced as a run-on with the line below it.
      expect(sentence, kind).toMatch(/\.$/);
      expect(sentence, kind).toMatch(/^Your reminders/);
    }
  });

  it("distinguishes the three outcomes the reminders can have", () => {
    // Cancelled, rescheduled, unchanged — and "back on" for a reinstatement, whose
    // behaviour is `REMINT` but whose wording the backend overrides, because
    // "rescheduled to the new time" would promise a new time a reinstatement does not
    // have.
    const outcomes = new Set(Object.values(NOTICE_REMINDER_LINES));
    expect(outcomes.size).toBeGreaterThanOrEqual(4);
    expect(NOTICE_REMINDER_LINES.cancelled).toContain("cancelled");
    expect(NOTICE_REMINDER_LINES.postponed).toContain("rescheduled");
    expect(NOTICE_REMINDER_LINES.sold_out).toContain("unchanged");
    expect(NOTICE_REMINDER_LINES.reinstated).toContain("back on");
  });
});

describe("the change line is the backend's subject, adapted", () => {
  it("covers every kind the backend's subject table covers", () => {
    const backend = backendSubjects();
    expect(Object.keys(backend).length).toBeGreaterThan(0);

    for (const kind of Object.keys(backend)) {
      expect(noticeChangeLineFor(kind), kind).not.toBeNull();
    }
  });

  it("keeps the backend's sense, with the title replaced by 'This event'", () => {
    // **The adaptation is one substitution, and it is the same one everywhere.**
    //
    // The backend's subject is "{title} was cancelled." — it names the event, because
    // the subject of an *email* has to say which email it is about. The screen does not
    // have a title to substitute (the payload carries none — AD-13), and both surfaces
    // that show this line are already about a specific event: the Detail screen *is* the
    // event's page, and the strip's entry links to it.
    //
    // **So the substitution is "{title}" → "This event"**, and the rest of the sentence
    // is the backend's, unchanged. That is what this test checks: the backend's
    // template with its placeholder substituted is the frontend's line.
    const backend = backendSubjects();

    for (const [kind, template] of Object.entries(backend)) {
      const expected = template
        .replace("{title}", "This event")
        .replace("{when}", "a new time")
        .replace("{where}", "a new location")
        // **The one exception, and it is a substitution too.** See below.
        .replace("by a new event", "by another event");
      expect(NOTICE_CHANGE_LINES[kind as keyof typeof NOTICE_CHANGE_LINES], kind).toBe(expected);
    }
  });

  it("degrades a missing time or place the way the backend does", () => {
    // The backend's `notice_subject` replaces a missing `{when}` with "a new time" and a
    // missing `{where}` with "a new location", because a subject that cannot be built is
    // worse than one that says less. The screen has the same gap — the notice payload
    // carries no new date and no new venue — so it uses the same words.
    //
    // **And the degradation is not optional.** The frontend has no `{when}` to fill, so
    // a line reading "This event was moved to {when}." would put a template placeholder
    // on the screen.
    const backend = backendSubjects();

    expect(NOTICE_CHANGE_LINES.postponed).toBe(
      backend.postponed.replace("{title}", "This event").replace("{when}", "a new time"),
    );
    expect(NOTICE_CHANGE_LINES.detail_changed).toBe(
      backend.detail_changed.replace("{title}", "This event").replace("{where}", "a new location"),
    );
    expect(NOTICE_CHANGE_LINES.postponed).not.toContain("{when}");
    expect(NOTICE_CHANGE_LINES.detail_changed).not.toContain("{where}");
  });

  it("is the backend's subject with exactly one wording exception", () => {
    // **The exception is the supersede, and it is a wording one.**
    //
    // The backend's subject is "{title} was replaced by a new event." — written for a
    // *named* subject, where "Brooklyn Symphony was replaced by a new event." reads
    // naturally. With "This event" substituted for the title it becomes "This event was
    // replaced by a new event.", which trips over itself: the reader has just been told
    // the thing is an event, twice, and the second one sounds like a different thing.
    //
    // **So the object becomes "another event."** The same fact, said without the
    // repetition — and it is the *only* place the frontend's wording is not a pure
    // substitution, which is why this test names it rather than letting it drift.
    expect(NOTICE_CHANGE_LINES.superseded).toBe("This event was replaced by another event.");
    expect(NOTICE_CHANGE_LINES.superseded).not.toContain("a new event");
  });
});

describe("the notice is the two sentences together", () => {
  it("gives both sentences for a known kind", () => {
    const lines = noticeLinesFor("cancelled");
    expect(lines).not.toBeNull();
    expect(lines?.change).toBe("This event was cancelled.");
    expect(lines?.reminder).toBe("Your reminders for this event have been cancelled.");
  });

  it("gives nothing at all for an unknown kind", () => {
    // **All or nothing.** A notice that says what changed but not what it means for
    // the user's reminders is FR-54's requirement half-met, and a user reading "This
    // event was cancelled." with no consequence line would not know whether to cancel
    // their own plans.
    expect(noticeLinesFor("rescheduled_for_tuesday")).toBeNull();
    expect(noticeLinesFor("")).toBeNull();
  });
});

describe("the sentences are not copied", () => {
  /**
   * The files that render these facts.
   *
   * **Every one of them must import the table.** The whole point of restating the
   * sentences in `lib/notice-copy.ts` is that there is exactly one copy of each; a
   * second literal is how the two drift apart, and how a fix to one surface leaves the
   * other showing the old words.
   */
  const CONSUMERS = [
    "components/state/notice-strip.tsx",
    "components/state/detail-notice-banner.tsx",
  ];

  it.each(CONSUMERS)("%s reads the shared table", (relative) => {
    const source = readFileSync(path.join(ROOT, relative), "utf8");
    expect(source, relative).toContain("@/lib/notice-copy");
  });

  it.each(CONSUMERS)("%s holds no literal copy of a change line", (relative) => {
    const source = withoutComments(readFileSync(path.join(ROOT, relative), "utf8"));
    // The table's own name is allowed; the sentences are not.
    for (const line of Object.values(NOTICE_CHANGE_LINES)) {
      expect(source, relative).not.toContain(line);
    }
  });

  it.each(CONSUMERS)("%s holds no literal copy of a reminder line", (relative) => {
    const source = withoutComments(readFileSync(path.join(ROOT, relative), "utf8"));
    for (const line of Object.values(NOTICE_REMINDER_LINES)) {
      expect(source, relative).not.toContain(line);
    }
  });

  it("the shared table itself is the only copy", () => {
    // **One copy, in one place.** The table is where the sentences live, and nothing
    // else may hold them.
    const table = readFileSync(path.join(ROOT, "lib/notice-copy.ts"), "utf8");
    for (const line of Object.values(NOTICE_CHANGE_LINES)) {
      expect(table).toContain(line);
    }
    for (const line of Object.values(NOTICE_REMINDER_LINES)) {
      expect(table).toContain(line);
    }
  });
});
