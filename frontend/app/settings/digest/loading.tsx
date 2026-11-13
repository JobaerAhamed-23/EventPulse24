/**
 * The Pulse Digest settings screen's skeleton.
 *
 * **A skeleton, not a spinner.** The product has exactly one transition (`.fade-in`),
 * and `styles/motion.test.ts` fails the suite on any other animation. A skeleton in the
 * shape of the page is the in-flight state this product uses.
 *
 * **The control skeleton is one row.** The page holds a heading, a lede and a single
 * control, so the in-flight state is three rectangles — the page does not reflow when
 * the content lands.
 */
export default function SettingsDigestLoading() {
  return (
    <div data-settings-skeleton>
      <div className="h-8 w-30 rounded-subtle bg-surface-subtle" />
      <div className="mt-3 h-4 w-30 rounded-subtle bg-surface-subtle" />

      <div className="mt-8 max-w-(--layout-container-reading)">
        <div className="h-6 w-30 rounded-control bg-surface-subtle" />
      </div>
    </div>
  );
}
