import { BrowseSkeleton } from "@/components/browse/browse-states";

/**
 * `/browse`'s loading state.
 *
 * **Twelve card-shaped skeletons, pulsing at 1800ms** — the product's single animation,
 * and no spinners anywhere (PRD §13.1 refuses urgency badges; a skeleton says "a card is
 * coming and it is about this big").
 *
 * **It is a skeleton and not a spinner because the thing being loaded has a shape.** The
 * read returns a grid of cards, and a skeleton that shows the grid's shape means the
 * page does not reflow when the cards arrive.
 *
 * **The shell stays.** This file replaces the *content*, not the frame — Next renders it
 * inside the route's own layout, so the sidenav and the bottom-tab bar remain usable
 * while the read is in flight. A loading state that took the navigation away would
 * leave the reader with nowhere to go.
 */
export default function BrowseLoading() {
  return <BrowseSkeleton />;
}
