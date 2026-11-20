import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The published Relevance Pulse formula, its scale and its amendment (FR-22).
 *
 * **Every number comes from the server.** `shared/constants.py` holds the weights the
 * product actually computes with, and this read carries them to the page unchanged. A
 * weights table typed into TypeScript would be a second source of truth on the one screen
 * whose entire purpose is that there is exactly one — and it would drift silently, which
 * is the failure FR-22 was written to prevent.
 *
 * **A failure is "unavailable", not an empty formula.** A transparency page rendering a
 * blank table is a worse answer than one saying it cannot answer: the first looks like a
 * product with no ranking, the second looks like a read that blinked.
 *
 * **The read carries the visitor's cookies.** The endpoint is behind `auth=current_user`
 * like every other settings read, so a server-side read without them is anonymous and
 * refused.
 *
 * **This module is server-only.** It reaches `sessionHeaders()`, and so `next/headers` — a
 * `"use client"` component importing it breaks the production build.
 */
export type RankingTransparency = components["schemas"]["RankingTransparencyOut"];

export type RankingTransparencyRead =
  | { kind: "found"; ranking: RankingTransparency }
  | { kind: "unavailable" };

export async function readRankingTransparency(): Promise<RankingTransparencyRead> {
  try {
    const response = await api.GET("/api/settings/ranking", {
      headers: await sessionHeaders(),
    });
    if (!response.data) return { kind: "unavailable" };
    return { kind: "found", ranking: response.data };
  } catch {
    return { kind: "unavailable" };
  }
}
