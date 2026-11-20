// @vitest-environment jsdom
/**
 * `Component.Settings.RankingFormula` — FR-22's published formula, made visible.
 *
 * What is pinned here:
 *
 * 1. **Every number on screen came from the server.** The strongest assertion in this
 *    file is not a render at all — it reads the component's own source and fails if a
 *    weight literal appears in it. A hard-coded table would be a second source of truth
 *    on the one screen whose entire job is that there is exactly one, and it would drift
 *    from `shared/constants.py` without anything going red.
 * 2. **The weights are rendered as given, never summed in the browser.** The total is the
 *    server's; a floating-point sum displayed as `1.0000000000000002` on the transparency
 *    page would discredit the thing the page is demonstrating.
 * 3. **The boundary rule is shown**, because a reader checking a score that lands exactly
 *    on a boundary gets the wrong answer without it.
 * 4. **The amendment and its date are shown** — FR-22's "ranking algorithm version".
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RankingFormula } from "@/components/settings/ranking-formula";
import type { RankingTransparency } from "@/lib/ranking-transparency-read";

/**
 * Deliberately **not** the real weights.
 *
 * If this fixture used 0.35 / 0.25 / 0.20 / 0.10 / 0.10, a component that ignored its
 * props and printed the real constants would still pass. These values are arbitrary and
 * sum to 1.00, so only a component that renders what it is given can satisfy them.
 */
const RANKING: RankingTransparency = {
  terms: [
    { key: "interest_overlap", label: "What you picked", weight: "0.41" },
    { key: "source_reliability", label: "How reliable the source is", weight: "0.23" },
    { key: "recency", label: "How soon it starts", weight: "0.19" },
    { key: "city_match", label: "How near it is", weight: "0.11" },
    { key: "confidence", label: "How sure we are of the details", weight: "0.06" },
  ],
  total: "1.00",
  buckets: [
    { dots: 5, min_score: "0.87" },
    { dots: 4, min_score: "0.67" },
    { dots: 3, min_score: "0.47" },
    { dots: 2, min_score: "0.27" },
    { dots: 1, min_score: "0.00" },
  ],
  boundary_rule: "lower",
  amendment: { id: "A-99", record: "ADR-9999", date: "2026-01-02" },
};

describe("the formula", () => {
  it("renders every term the server sent, with the server's own label", () => {
    render(<RankingFormula ranking={RANKING} />);
    for (const term of RANKING.terms) {
      expect(screen.getByText(term.label)).toBeInTheDocument();
    }
  });

  it("renders each weight exactly as the server wrote it", () => {
    render(<RankingFormula ranking={RANKING} />);
    for (const term of RANKING.terms) {
      expect(screen.getByText(term.weight)).toBeInTheDocument();
    }
  });

  it("shows the server's total rather than adding the weights up itself", () => {
    render(<RankingFormula ranking={RANKING} />);
    expect(screen.getByText("Total")).toBeInTheDocument();
    expect(screen.getByText("1.00")).toBeInTheDocument();
  });
});

describe("the scale", () => {
  it("renders all five steps, including the floor", () => {
    render(<RankingFormula ranking={RANKING} />);
    expect(screen.getByText("0.87 and above")).toBeInTheDocument();
    expect(screen.getByText("from 0.00")).toBeInTheDocument();
  });

  it("states which way an exact boundary falls", () => {
    render(<RankingFormula ranking={RANKING} />);
    expect(
      screen.getByText("A score that lands exactly on a boundary takes the lower band."),
    ).toBeInTheDocument();
  });

  it("names each band for a screen reader, because the dots are decorative glyphs", () => {
    render(<RankingFormula ranking={RANKING} />);
    expect(screen.getByText("5 dots")).toBeInTheDocument();
    expect(screen.getByText("1 dot")).toBeInTheDocument();
  });
});

describe("the ranking algorithm version", () => {
  it("shows the amendment, its record and the last-changed date", () => {
    render(<RankingFormula ranking={RANKING} />);
    expect(screen.getByText("A-99")).toBeInTheDocument();
    expect(screen.getByText("ADR-9999")).toBeInTheDocument();
    expect(screen.getByText("2026-01-02")).toBeInTheDocument();
  });
});

describe("the one source of truth", () => {
  /**
   * **The assertion this file exists for.**
   *
   * FR-22's failure mode is a published formula that differs from the computed one. A
   * weights table typed into this component would be exactly that, and every render test
   * above would still pass. So the source itself is read.
   */
  it("contains no weight literal — every number is served", () => {
    const source = readFileSync(
      path.join(__dirname, "ranking-formula.tsx"),
      "utf8",
    );
    const code = source.replace(/\/\*\*[\s\S]*?\*\//g, "");
    const decimals = code.match(/\b0\.\d+\b/g) ?? [];
    expect(decimals).toEqual([]);
  });
});
