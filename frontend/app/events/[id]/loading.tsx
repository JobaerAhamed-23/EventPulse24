import { DetailSkeleton } from "@/components/detail/detail-states";

/**
 * The Detail Screen's loading state.
 *
 * **One header block, one meta row and three chip skeletons**, with the same fade as the
 * content they stand in for (`EXPERIENCE.md` §12).
 *
 * **The digest's `skeleton-pulse` is not used here.** The pulse belongs to the digest's
 * skeleton, where the surface genuinely waits; a detail page's skeleton is a *shape*
 * that fades in. The pulse keyframe is not copied here, and `styles/motion.test.ts`
 * still fails if it appears in a second file.
 */
export default function Loading() {
  return (
    <div className="fade-in mx-auto w-full max-w-(--layout-container-reading)">
      <DetailSkeleton />
    </div>
  );
}
