"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { api } from "@/lib/backend-client";
import type { BrowseQuota } from "@/lib/browse-read";

/**
 * The live save allowance, and the way to ask the server for a newer one.
 *
 * ## Why this exists
 *
 * **The allowance moves, and the page has to move with it.** The Free allowance is one
 * save a day. The reader presses Save on a card; the server spends the slot; and from
 * that moment the page's own copy of the allowance is a lie: the hero still says "0 of 1
 * save used today", and every *other* card's button still reads "Save" and is still
 * pressable. The reader presses a second card and the server refuses it — so the surface
 * offered a press it knew was going to be refused.
 *
 * **The server's gate was never the problem.** `save_cap.py` refuses the second save
 * correctly, and the client is not allowed to decide anything the server decided. What
 * was missing was the *second half* of the contract: the server states the fact, and the
 * client shows the fact it was given. **A client that never asks again is a client
 * showing a stale fact.**
 *
 * ## Why the provider, and not a prop
 *
 * **The note and the buttons are in different subtrees.** The quota note is in the hero
 * and the buttons are in the grid, and the hero is a server component while the grid is
 * a client island. A prop cannot cross that boundary, and a callback threaded down
 * through the grid, the cards and each button would be four layers of plumbing for one
 * number. A context provider is the shape the problem has.
 *
 * **The provider holds the *last known* quota, not the truth.** The truth is the
 * server's, and the only way to learn it is to ask. So the provider holds what the
 * server said at page load, and `refresh()` asks again.
 *
 * ## What a refresh does, and what it does not do
 *
 * **It asks the server, and it takes the answer.** `refresh()` re-reads
 * `GET /api/personal/browse` and takes the `quota` the payload carries — the same
 * number the page rendered on its first paint, from the same endpoint, under the same
 * session. **The client never computes the allowance.** It does not add one to `used`,
 * it does not set `used` to `cap` when a save lands, and it does not decide that a save
 * was "big". A save that the server *refused* spends nothing, and a client that
 * incremented on every press would show a wall the server is not enforcing.
 *
 * **A failed refresh leaves the last known quota in place.** The provider keeps what it
 * had and says nothing: the allowance did not change because the request failed, and a
 * line that said "0 of 1" when the server says "1 of 1" is not better than a line that
 * was merely stale. The server's gate is still the gate, so a stale note costs the
 * reader a refused press — never a wrong save.
 *
 * **The refresh keeps the quota and drops the cards.** The endpoint answers with the
 * whole payload — the quota *and* the cards — but the provider holds only the quota,
 * because the quota is the one thing that has to move. **The cards do not need it.**
 * Each card's `is_saved` was true at the first paint, and the only card whose saved
 * state can have changed since is the one the reader just saved — and that card updates
 * its own state, because the press that saved it is the press it handled. So dropping
 * the cards from the refresh loses nothing, and the surface does not re-render a
 * hundred cards to move one number.
 *
 * **The refresh asks for one card, not twenty-four.** It passes `limit: 1` because it
 * wants the quota, and the quota is in the payload whatever the page size. The number
 * of cards in the answer is the provider's business, and the smaller the better.
 */

export type BrowseQuotaContextValue = {
  /** The allowance as it last stood. The server's number, never a computed one. */
  quota: BrowseQuota;
  /**
   * Ask the server what the allowance stands at now, and adopt the answer.
   *
   * **Returns whether the answer arrived.** A caller that cares — the Save button, which
   * wants to know whether the wall is now up — can act on it; a caller that does not can
   * ignore it.
   */
  refresh: () => Promise<boolean>;
};

const BrowseQuotaContext = createContext<BrowseQuotaContextValue | null>(null);

export function BrowseQuotaProvider({
  quota,
  children,
}: {
  /** The allowance the server stated when the page was rendered. */
  quota: BrowseQuota;
  children: React.ReactNode;
}) {
  const [current, setCurrent] = useState<BrowseQuota>(quota);

  const refresh = useCallback(async (): Promise<boolean> => {
    try {
      const response = await api.GET("/api/personal/browse", {
        params: { query: { offset: 0, limit: 1 } },
      });
      if (!response.data) return false;
      setCurrent(response.data.quota);
      return true;
    } catch {
      // **A failed refresh is not a failed allowance.** The last known number stays.
      return false;
    }
  }, []);

  const value = useMemo<BrowseQuotaContextValue>(
    () => ({ quota: current, refresh }),
    [current, refresh],
  );

  return <BrowseQuotaContext.Provider value={value}>{children}</BrowseQuotaContext.Provider>;
}

/**
 * The live allowance, and the way to ask for a newer one — or `null` outside a provider.
 *
 * **It returns `null` rather than throwing, on purpose.** The Save button is rendered
 * in places that are not this island, and a component that threw outside a provider
 * would take those surfaces down with it. So the hook reports "there is no live
 * allowance here" and the caller falls back to what it was given.
 */
export function useBrowseQuota(): BrowseQuotaContextValue | null {
  return useContext(BrowseQuotaContext);
}
