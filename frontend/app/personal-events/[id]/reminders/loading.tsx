/**
 * The personal-event reminder picker's skeleton.
 *
 * **A skeleton, not a spinner** — the product has exactly one transition (`.fade-in`), and
 * `styles/motion.test.ts` fails the suite on any other animation. Shaped like the crumb,
 * the heading and a row of slot chips.
 *
 * **Every width and height is on the sanctioned scale.** `tests/spacing-scale.test.ts`
 * fails the suite on any other value, and it caught this file using four that are not —
 * the skeleton is built from the same vocabulary as its saved-event sibling.
 */
export default function PersonalEventRemindersLoading() {
  return (
    <div data-reminders-skeleton>
      <div className="h-4 w-30 rounded-subtle bg-surface-subtle" />
      <div className="mt-8 max-w-(--layout-container-reading)">
        <div className="h-8 w-20 rounded-subtle bg-surface-subtle" />
        <div className="mt-3 h-4 w-30 rounded-subtle bg-surface-subtle" />
        <div className="mt-8 flex flex-wrap gap-3">
          <div className="h-12 w-16 rounded-control bg-surface-subtle" />
          <div className="h-12 w-16 rounded-control bg-surface-subtle" />
          <div className="h-12 w-16 rounded-control bg-surface-subtle" />
          <div className="h-12 w-16 rounded-control bg-surface-subtle" />
        </div>
      </div>
    </div>
  );
}
