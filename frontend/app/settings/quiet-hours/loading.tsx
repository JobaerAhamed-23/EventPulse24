/**
 * The Quiet Hours route's skeleton.
 *
 * **A skeleton, not a spinner.** The product has exactly one transition (`.fade-in`),
 * and `styles/motion.test.ts` fails the suite on any other animation. A skeleton in the
 * shape of the page is the in-flight state this product uses.
 *
 * **Two time inputs, because the window is two clocks.**
 */
export default function SettingsQuietHoursLoading() {
  return (
    <div data-settings-skeleton>
      <div className="h-8 w-30 rounded-subtle bg-surface-subtle" />
      <div className="mt-3 h-4 w-30 rounded-subtle bg-surface-subtle" />

      <div className="mt-8 max-w-(--layout-container-reading)">
        <div className="h-4 w-30 rounded-subtle bg-surface-subtle" />
        <div className="mt-6 flex flex-wrap items-end gap-3">
          <div className="h-12 w-30 rounded-control bg-surface-subtle" />
          <div className="h-12 w-30 rounded-control bg-surface-subtle" />
        </div>
      </div>

      <div className="mt-12 max-w-(--layout-container-reading)">
        <div className="h-6 w-20 rounded-subtle bg-surface-subtle" />
        <div className="mt-6 h-12 w-30 rounded-control bg-surface-subtle" />
      </div>
    </div>
  );
}
