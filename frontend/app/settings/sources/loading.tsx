/**
 * The Sources route's skeleton.
 *
 * **A skeleton, not a spinner** — the product has exactly one transition (`.fade-in`), and
 * `styles/motion.test.ts` fails the suite on any other animation.
 *
 * **The rows are the skeleton, not a card.** A source row is a name with a trust badge and
 * a three-state control beside it, so the placeholder is a short bar where the name would
 * be and a longer one where the control's buttons would be — the shape of the thing that is
 * coming, so the page does not jump when it arrives.
 */
export default function SettingsSourcesLoading() {
  return (
    <div data-settings-skeleton>
      <div className="h-8 w-30 rounded-subtle bg-surface-subtle" />
      <div className="mt-3 h-4 w-30 rounded-subtle bg-surface-subtle" />

      <div className="mt-8 flex max-w-(--layout-container-reading) flex-col gap-8">
        {[0, 1, 2].map((group) => (
          <div key={group} className="flex flex-col gap-3">
            <div className="h-4 w-20 rounded-subtle bg-surface-subtle" />
            <div className="h-16 rounded-card bg-surface-subtle" />
            <div className="h-16 rounded-card bg-surface-subtle" />
          </div>
        ))}
      </div>
    </div>
  );
}
