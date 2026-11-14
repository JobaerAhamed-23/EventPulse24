/**
 * The Default Reminder Plan's skeleton.
 *
 * **A skeleton, not a spinner.** The product has exactly one transition (`.fade-in`),
 * and `styles/motion.test.ts` fails the suite on any other animation. A skeleton in the
 * shape of the page is the in-flight state this product uses.
 *
 * **The chip skeletons are the chips' real shape.** Four rectangles where the four
 * chips will be, so the page does not reflow when the content lands.
 */
export default function SettingsRemindersLoading() {
  return (
    <div data-settings-skeleton>
      <div className="h-8 w-30 rounded-subtle bg-surface-subtle" />
      <div className="mt-3 h-4 w-30 rounded-subtle bg-surface-subtle" />

      <div className="mt-8 max-w-(--layout-container-reading)">
        <div className="h-4 w-30 rounded-subtle bg-surface-subtle" />
        <div className="mt-6 flex flex-wrap gap-2">
          <div className="h-12 w-16 rounded-control bg-surface-subtle" />
          <div className="h-12 w-16 rounded-control bg-surface-subtle" />
          <div className="h-12 w-16 rounded-control bg-surface-subtle" />
          <div className="h-12 w-16 rounded-control bg-surface-subtle" />
        </div>
      </div>
    </div>
  );
}
