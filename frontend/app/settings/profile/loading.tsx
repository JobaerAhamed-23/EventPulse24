/**
 * The Profile route's skeleton.
 *
 * **A skeleton, not a spinner.** The product has exactly one transition (`.fade-in`), and
 * `styles/motion.test.ts` fails the suite on any other animation.
 *
 * Two blocks, in the shape of the page: the heading, and the one field with its control.
 */
export default function SettingsProfileLoading() {
  return (
    <div data-settings-skeleton>
      <div className="h-8 w-30 rounded-subtle bg-surface-subtle" />
      <div className="mt-3 h-4 w-30 rounded-subtle bg-surface-subtle" />

      <div className="mt-8 max-w-(--layout-container-reading)">
        <div className="h-4 w-20 rounded-subtle bg-surface-subtle" />
        <div className="mt-6 h-12 w-30 rounded-control bg-surface-subtle" />
      </div>
    </div>
  );
}
