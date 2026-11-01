// @vitest-environment node
/**
 * The Detail Screen's structural rules, asserted against the source rather than the DOM.
 *
 * **These are the rules a rendering test cannot catch.** `app/events/[id]/page.test.tsx`
 * can see that the neighbor line reads "A few neighbors saved this."; it cannot see that
 * a literal `12` has been typed into a second file, that an emoji has crept into the
 * breakdown's markup, or that a reliability score has been added to a factor line.
 * Those are properties of the source, so they are asserted on the source — the same
 * house pattern as `tests/digest-home-boundary.test.ts`.
 *
 * **The rules are the ones whose violation would be silent.** An exact neighbor count
 * in the source would look right in one bucket and wrong in another. A reliability score
 * would look like the mockup. A distance claim would look like a fact. Each of those is
 * a lie the product cannot tell, and each is invisible to a render test that only checks
 * the prose it was given.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

/** The files the Detail Screen is made of. */
const FILES = [
  "app/events/[id]/page.tsx",
  "app/events/[id]/loading.tsx",
  "components/conflicts/conflict-indicator.tsx",
  "components/conflicts/detail-conflict-mark.tsx",
  "components/detail/detail-actions.tsx",
  "components/detail/detail-breakdown.tsx",
  "components/detail/detail-header.tsx",
  "components/detail/detail-neighbors.tsx",
  "components/detail/detail-reminder-link.tsx",
  "components/detail/detail-states.tsx",
  "components/detail/trigger-tip.tsx",
  "lib/conflict-open.ts",
  "lib/detail-labels.ts",
  "lib/detail-time.ts",
  "lib/event-detail-read.ts",
];

const sources = new Map(FILES.map((file) => [file, readFileSync(path.join(ROOT, file), "utf8")]));

/**
 * The source with its comments removed.
 *
 * **A comment is not code.** These files' docstrings quote the spec — they mention the
 * reliability score, the `👥` emoji and the distance wording in order to explain why
 * they are *absent* — and a source-text assertion that read them would be asserting on
 * prose. So the comments come out first.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

const code = new Map([...sources].map(([file, source]) => [file, withoutComments(source)]));

/** The class-name strings in a .tsx file. */
function classStrings(source: string): string[] {
  return [...source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\}|\{"([^"]*)"\})/g)].map(
    (match) => match[1] ?? match[2] ?? match[3] ?? "",
  );
}

/** Every class-name token across the surface. */
function allTokens(): string[] {
  return [...code.values()].flatMap((source) =>
    classStrings(source).flatMap((value) => value.split(/\s+/)),
  );
}

describe("the Detail Screen's tokens", () => {
  it("uses no literal hex colour", () => {
    for (const [file, source] of code) {
      expect(source.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [], file).toEqual([]);
    }
  });

  it("uses no raw rgb() or hsl() colour", () => {
    for (const [file, source] of code) {
      expect(source.match(/\b(?:rgb|rgba|hsl|hsla)\(/g) ?? [], file).toEqual([]);
    }
  });

  it("takes every colour from a token utility", () => {
    const alignments = new Set([
      "text-left",
      "text-center",
      "text-right",
      "text-justify",
      "text-start",
      "text-end",
    ]);

    const colours = allTokens().filter(
      (token) =>
        /^(?:bg|text|border|ring|outline|fill|stroke)-/.test(token) && !alignments.has(token),
    );

    expect(colours.length).toBeGreaterThan(0);
    for (const token of colours) {
      if (/^(?:ring|border)-?\d/.test(token)) continue;
      if (/^border-[trblxy]?$/.test(token)) continue;
      expect(
        /^(?:bg|text|border|ring|outline|fill|stroke)-(?:surface|ink|accent|warm|warn|signal|border)/.test(
          token,
        ),
        token,
      ).toBe(true);
    }
  });

  it("names no font family outside the type scale", () => {
    const families = allTokens().filter((token) => token.includes("[font:"));

    expect(families.length).toBeGreaterThan(0);
    for (const token of families) {
      expect(token, token).toContain("--type-scale-");
    }
  });
});

describe("the Detail Screen's motion", () => {
  it("uses no motion class in the markup", () => {
    // The product has exactly one transition — `motion.fadeIn` — and no other. The
    // digest's `skeleton-pulse` belongs to the digest's skeleton and nowhere else.
    const motion = allTokens().filter((token) =>
      /^(?:animate-|transition|duration-|delay-|ease-)/.test(token),
    );

    expect(motion).toEqual([]);
  });

  it("does not use the digest's skeleton pulse", () => {
    for (const [file, source] of code) {
      expect(source.match(/skeleton-pulse/g) ?? [], file).toEqual([]);
    }
  });
});

describe("the neighbor count", () => {
  it("states no exact count anywhere", () => {
    // FR-24: "Exact counts are never exposed." The API sends a bucket key and no count
    // field at all, so a number in the source would be a number the client could have
    // been given.
    for (const [file, source] of code) {
      expect(source.match(/(?:5[–-]9|10[–-]24|25[–-]99|100\+)/g) ?? [], file).toEqual([]);
    }
  });

  it("states no neighbor number in prose", () => {
    for (const [file, source] of code) {
      expect(source.match(/\bneighbors?\s+\d/gi) ?? [], file).toEqual([]);
    }
  });

  it("carries no emoji prefix", () => {
    // `EXPERIENCE.md` §12's `_RECONCILE_` note revised the bucketed rendering to
    // prose-only under the emoji-as-CTA ban.
    for (const [file, source] of code) {
      expect(source.match(/👥/g) ?? [], file).toEqual([]);
    }
  });

  it("renders the four buckets and no fifth", () => {
    const labels = code.get("lib/detail-labels.ts") ?? "";
    for (const bucket of ["few", "some", "many", "a_lot"]) {
      expect(labels, bucket).toContain(`${bucket}:`);
    }
    // No "suppressed" key: the suppression is silence, and a key for it would tell the
    // client the count was computed and discarded.
    expect(labels).not.toContain("suppressed:");
  });
});

describe("the breakdown's factors", () => {
  it("states no reliability score", () => {
    // FR-16 is unbuilt — `Source` has no score field — so a factor line claiming a
    // reliability number would be stating something nobody computed.
    for (const [file, source] of code) {
      expect(source.match(/reliability/gi) ?? [], file).toEqual([]);
      expect(source.match(/bayesian/gi) ?? [], file).toEqual([]);
      expect(source.match(/0\.\d+/g) ?? [], file).toEqual([]);
    }
  });

  it("states no distance", () => {
    // `Venue` has no coordinates, so no distance is computable.
    for (const [file, source] of code) {
      expect(source.match(/\d+\s*km\b/gi) ?? [], file).toEqual([]);
      expect(source.match(/blocks? from/gi) ?? [], file).toEqual([]);
    }
  });

  it("states no attendance and no price", () => {
    // There is no attendance model and no price field.
    for (const [file, source] of code) {
      expect(source.match(/attended/gi) ?? [], file).toEqual([]);
      expect(source.match(/no ticket required/gi) ?? [], file).toEqual([]);
    }
  });

  it("carries no emoji glyph", () => {
    // The mockup's `📍 ⭐ 🆓 ✅` — the emoji-as-CTA ban, decided once and applied
    // consistently.
    for (const [file, source] of code) {
      expect(source.match(/[📍⭐🆓✅📌🔥]/g) ?? [], file).toEqual([]);
    }
  });

  it("uses no CSS pseudo-element for visible helper text", () => {
    for (const [file, source] of code) {
      expect(source.match(/::(?:after|before)/g) ?? [], file).toEqual([]);
      expect(source.match(/content-\[/g) ?? [], file).toEqual([]);
    }
  });
});

describe("the sections that do not ship", () => {
  it("renders no reviews, no similar events and no report link", () => {
    for (const [file, source] of code) {
      expect(source.match(/\breviews?\b/gi) ?? [], file).toEqual([]);
      expect(source.match(/similar events/gi) ?? [], file).toEqual([]);
      expect(source.match(/report this event/gi) ?? [], file).toEqual([]);
    }
  });

  it("renders no dismissal control", () => {
    // FR-25's dismissal is a swipe on the Pulse Card, and there is no dismissal
    // endpoint — so a "Dismiss" button here would be a control that does nothing.
    for (const [file, source] of code) {
      expect(source.match(/less like this/gi) ?? [], file).toEqual([]);
      expect(source.match(/>\s*Dismiss\s*</g) ?? [], file).toEqual([]);
    }
  });
});

describe("the reminder section on the Detail Screen", () => {
  it("is a link to the picker, and contains no control of its own", () => {
    // **The section is a link now.** It used to render the plan's chips as `<span>`s,
    // because "nothing schedules sends" — the delivery intent had not built the
    // scheduler. That reason is gone: the plan is written through
    // `PUT /api/reminders/…`, and the Reminder Picker is where it is edited.
    //
    // **So the section links out and holds no control.** A `<span>` that looks like a
    // control and is not one is worse than a link that plainly is — and a button here
    // would be a second, redundant route into the picker.
    const source = code.get("components/detail/detail-reminder-link.tsx") ?? "";
    expect(source).toContain("/reminders");
    expect(source).not.toContain("<button");
    expect(source).not.toContain("onClick");
  });

  it("carries no terracotta on the section", () => {
    // `EXPERIENCE.md` §4 `Input.ReminderSlot`: selection is communicated by ink
    // inversion, not by accent. The section carries no selection at all, so it carries
    // no accent either.
    const source = code.get("components/detail/detail-reminder-link.tsx") ?? "";
    expect(source).not.toContain("terracotta");
  });
});

describe("the tooltip", () => {
  it("uses a button trigger with aria-describedby", () => {
    const source = code.get("components/detail/trigger-tip.tsx") ?? "";
    expect(source).toContain("<button");
    expect(source).toContain("aria-describedby");
    expect(source).toContain('role="tooltip"');
  });

  it("dismisses on Escape and on an outside tap", () => {
    // "No hover-only tooltips on touch" — and the dismissal rules are the half CSS
    // cannot do.
    const source = code.get("components/detail/trigger-tip.tsx") ?? "";
    expect(source).toContain("Escape");
    expect(source).toContain("pointerdown");
  });

  it("keeps the tooltip in the DOM", () => {
    // A `display: none` element is not a description target, and the content has to be
    // assertable without a browser.
    const source = code.get("components/detail/trigger-tip.tsx") ?? "";
    expect(source).toContain("hidden={!open}");
    expect(source).not.toContain("display: none");
  });
});

describe("the read", () => {
  it("does not read a session for the personal payload", () => {
    // The API's `personal: null` is the authority on whether it found a personal
    // payload. A client that inferred it from its own cookie could render the personal
    // surface to a caller the API refused.
    const source = code.get("lib/event-detail-read.ts") ?? "";
    expect(source).toContain("personal === null");
    expect(source).not.toContain("getSession");
  });

  it("carries the session's cookies", () => {
    const source = code.get("lib/event-detail-read.ts") ?? "";
    expect(source).toContain("sessionHeaders");
  });
});

describe("the conflict mark", () => {
  it("is amber and never red", () => {
    // `DESIGN.md`: "Never red". ASSUM-13 locks the size at 6px. The mark is the same
    // one the Pulse Card draws, so the two surfaces cannot drift.
    const source = code.get("components/conflicts/conflict-indicator.tsx") ?? "";
    expect(source).toContain("bg-warn-amber");
    expect(source).not.toMatch(/text-signal-warn|bg-signal-warn|text-red|bg-red/);
    expect(source).toContain("size-[6px]");
  });

  it("carries an accessible name, so colour is not the sole carrier", () => {
    // WCAG 1.4.1: an amber dot with no name says nothing to a screen-reader user.
    const source = code.get("components/conflicts/conflict-indicator.tsx") ?? "";
    expect(source).toContain('aria-label="Schedule conflict"');
  });

  it("is a button on the Detail Screen, and says what pressing it does", () => {
    // On the Pulse Card the mark is a fact and the card is the target. Here the prompt
    // is opened from it, so it is a button — and its name says there is a choice.
    const source = code.get("components/conflicts/detail-conflict-mark.tsx") ?? "";
    expect(source).toContain("ConflictIndicatorButton");
    expect(source).toContain("Choose how to handle it");
  });

  it("is drawn from the one shared component", () => {
    // Two copies of the mark would drift, and a mark that drifted would be one screen
    // saying "conflict" in amber and another saying it in something else.
    const source = code.get("components/conflicts/detail-conflict-mark.tsx") ?? "";
    expect(source).toContain("@/components/conflicts/conflict-indicator");
    expect(source).not.toContain("rounded-full bg-warn-amber");
  });
});

describe("the conflict prompt", () => {
  /**
   * **The sheet is shared, so it is not in the Detail Screen's file list.**
   *
   * `components/sheets/conflict-resolution.tsx` is drawn by two surfaces — the personal
   * event flow and the Detail Screen — and it is asserted on by both. Putting it in
   * `FILES` would subject it to *this* surface's rules: the Detail Screen has no
   * `text-xl` because it has no amber glyph, and it has no opacity modifiers because
   * it states no score. Those rules belong to the sheet's own home, and the assertions
   * below read the file directly so they can be about the sheet's contract rather than
   * about this surface's palette.
   */
  const sheet = withoutComments(
    readFileSync(path.join(ROOT, "components/sheets/conflict-resolution.tsx"), "utf8"),
  );

  it("names the side the action is about, not the pair", () => {
    // The prompt's row is symmetric, so the label has to name the event the action is
    // about. A label that says "the new one" would name an event the user never
    // created — they *saved* one.
    //
    // **The island builds the map and the sheet renders it.** The sheet's own labels
    // come from the wording module, so the two surfaces cannot describe the same
    // action differently.
    const island = code.get("components/detail/detail-actions.tsx") ?? "";
    expect(island).toContain("buildSubjects");
    expect(sheet).toContain("reviewActionLabel");
    expect(sheet).toContain('wording === "named"');
  });

  it("computes the request's side from the pair's kinds", () => {
    // The server checks the side, and it enforces it. A client that named the side
    // any other way would be refused — and the prompt would offer an action that
    // cannot be taken.
    const source = code.get("components/detail/detail-actions.tsx") ?? "";
    expect(source).toContain("actionSide");
  });

  it("does not name the catalog event id as the saved side", () => {
    // The pair stores a `SavedEvent` by **that row's** id, and a `skip_public` releases
    // the save by the same id. The catalog event's id would name a side the pair does
    // not have.
    const source = code.get("components/detail/detail-actions.tsx") ?? "";
    expect(source).toContain("saved_side_id");
    expect(source).not.toContain("id: eventId,");
  });

  it("has no dismiss path of its own", () => {
    // FR-58: no dismiss button, no X, no escape-key close, no outside-click close. The
    // sheet is `dismissible={false}` — one place, next to the code that opens it.
    const source = code.get("components/detail/detail-actions.tsx") ?? "";
    expect(source).not.toMatch(/dismiss(?!ible)/i);
  });
});
