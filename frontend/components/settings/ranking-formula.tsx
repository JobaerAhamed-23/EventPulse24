import type { RankingTransparency } from "@/lib/ranking-transparency-read";

/**
 * **The published ranking formula, as FR-22 promises a user can read it.**
 *
 * FR-22's promise is not that a formula exists — it is that the formula is *published*,
 * "immutable post-launch", and that "a user reading the PRD can compute the Confidence
 * Pulse for any Event given the inputs". This is the product's half of that promise.
 *
 * ## Every number is the server's
 *
 * There is **no numeric weight in this file**. The terms, their weights, the scale and the
 * amendment all arrive as props from `/api/settings/ranking`, which projects them from
 * `shared/constants.py` — the same constants `domain/ranking.py` computes with.
 * `ranking-formula.test.tsx` asserts this file contains no weight literal, because a
 * hard-coded table here would be a second source of truth on the one screen whose job is
 * that there is one, and it would drift without anything going red.
 *
 * ## The weights are text, and they are never summed in the browser
 *
 * They cross the wire as decimal strings and are rendered as given. `Decimal("0.85")` is
 * not the float `0.85`, and the whole of `domain/ranking.py` turns on that distinction
 * because an exact boundary decides a dot count. **The total is the server's too** — this
 * component does not add the weights up, because a floating-point sum displayed as `1.0000000000000002`
 * on the transparency page would discredit the very thing the page is demonstrating.
 *
 * ## There is no worked example
 *
 * Tempting on this screen, and wrong for the same reason: an example score computed in
 * JavaScript could land on the wrong side of a boundary, on the one page that exists to
 * prove the arithmetic is sound. The page shows the terms, the weights and the
 * boundaries; the reader does the multiplication, which is precisely what FR-22 says they
 * are entitled to do.
 *
 * ## The scale's size is the served scale's size
 *
 * The empty dots are `buckets.length - bucket.dots`, not `5 - bucket.dots`. Five is the
 * scale today (`RANKING_BUCKET_MAX`), but it is the server's fact, and a literal here
 * would be one more number on this page that did not come from the thing it describes —
 * which is the whole failure this screen exists to close.
 *
 * ## The boundary rule is stated, not implied
 *
 * `boundary_rule` is `"lower"`: a score of exactly 0.85 shows four dots, not five. A
 * reader checking a score that lands on a boundary gets the wrong answer without being
 * told, so the rule is published beside the scale rather than left in the backend.
 */
export type RankingFormulaProps = {
  ranking: RankingTransparency;
};

export function RankingFormula({ ranking }: RankingFormulaProps) {
  const { terms, total, buckets, boundary_rule: boundaryRule, amendment } = ranking;

  return (
    <div className="flex flex-col gap-12">
      <section aria-labelledby="ranking-formula-heading" className="flex flex-col gap-3">
        <h2
          id="ranking-formula-heading"
          className="text-ink-primary [font:var(--type-scale-headline-sm)]"
        >
          How your Pulse is ranked
        </h2>
        <p className="text-ink-secondary [font:var(--type-scale-body-md)]">
          Every event you see is scored out of 1.00. These are the parts of that score, and
          what each one is worth.
        </p>

        <table className="mt-2 w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-border-subtle">
              <th scope="col" className="py-2 text-ink-secondary [font:var(--type-scale-meta-md)]">
                What we look at
              </th>
              <th
                scope="col"
                className="py-2 text-right text-ink-secondary [font:var(--type-scale-meta-md)]"
              >
                Weight
              </th>
            </tr>
          </thead>
          <tbody>
            {terms.map((term) => (
              <tr key={term.key} className="border-b border-border-subtle">
                <td className="py-3 text-ink-primary [font:var(--type-scale-body-md)]">
                  {term.label}
                </td>
                <td className="py-3 text-right font-mono text-ink-primary [font:var(--type-scale-body-md)]">
                  {term.weight}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th
                scope="row"
                className="py-3 text-left text-ink-primary [font:var(--type-scale-meta-md)]"
              >
                Total
              </th>
              <td className="py-3 text-right font-mono text-ink-primary [font:var(--type-scale-meta-md)]">
                {total}
              </td>
            </tr>
          </tfoot>
        </table>
      </section>

      <section aria-labelledby="ranking-scale-heading" className="flex flex-col gap-3">
        <h2
          id="ranking-scale-heading"
          className="text-ink-primary [font:var(--type-scale-headline-sm)]"
        >
          How the score becomes dots
        </h2>
        <p className="text-ink-secondary [font:var(--type-scale-body-md)]">
          The dots on a card are the score, banded.
        </p>

        <ul className="mt-2 flex flex-col gap-2">
          {buckets.map((bucket) => (
            <li
              key={bucket.dots}
              className="flex items-baseline justify-between border-b border-border-subtle py-2"
            >
              <span className="text-ink-primary [font:var(--type-scale-body-md)]">
                <span aria-hidden="true">
                  {"●".repeat(bucket.dots)}
                  {"○".repeat(buckets.length - bucket.dots)}
                </span>{" "}
                <span className="sr-only">
                  {bucket.dots} {bucket.dots === 1 ? "dot" : "dots"}
                </span>
              </span>
              <span className="font-mono text-ink-secondary [font:var(--type-scale-meta-md)]">
                {bucket.dots === 1 ? `from ${bucket.min_score}` : `${bucket.min_score} and above`}
              </span>
            </li>
          ))}
        </ul>

        {boundaryRule === "lower" ? (
          <p className="text-ink-secondary [font:var(--type-scale-meta-md)]">
            A score that lands exactly on a boundary takes the lower band.
          </p>
        ) : null}
      </section>

      <section aria-labelledby="ranking-version-heading" className="flex flex-col gap-3">
        <h2
          id="ranking-version-heading"
          className="text-ink-primary [font:var(--type-scale-headline-sm)]"
        >
          Ranking algorithm version
        </h2>
        <p className="text-ink-secondary [font:var(--type-scale-body-md)]">
          These weights are fixed. Changing them takes a published amendment, and this is
          the one they are on.
        </p>
        <dl className="mt-2 flex flex-col gap-2">
          <div className="flex items-baseline justify-between border-b border-border-subtle py-2">
            <dt className="text-ink-secondary [font:var(--type-scale-meta-md)]">Amendment</dt>
            <dd className="font-mono text-ink-primary [font:var(--type-scale-body-md)]">
              {amendment.id}
            </dd>
          </div>
          <div className="flex items-baseline justify-between border-b border-border-subtle py-2">
            <dt className="text-ink-secondary [font:var(--type-scale-meta-md)]">Record</dt>
            <dd className="font-mono text-ink-primary [font:var(--type-scale-body-md)]">
              {amendment.record}
            </dd>
          </div>
          <div className="flex items-baseline justify-between border-b border-border-subtle py-2">
            <dt className="text-ink-secondary [font:var(--type-scale-meta-md)]">Last changed</dt>
            <dd className="font-mono text-ink-primary [font:var(--type-scale-body-md)]">
              {amendment.date}
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
