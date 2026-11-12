import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The signed-in user's collections, read on the server (FR-49).
 *
 * **A failure is "unavailable", not an empty list.** The two look identical on screen and
 * mean opposite things: a Pro user with three collections whose read blinked would be shown
 * the "you have none yet" empty state, which reads as data loss. The page distinguishes
 * them.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is anonymous,
 * and an anonymous read of somebody's collections is nobody's collections.
 *
 * **This module is server-only.** It reaches `sessionHeaders()`, and so `next/headers` — a
 * `"use client"` component importing it breaks the production build.
 */
export type CollectionOut = components["schemas"]["CollectionOut"];

export type CollectionsRead =
  { kind: "found"; collections: CollectionOut[] } | { kind: "unavailable" };

export async function readCollections(): Promise<CollectionsRead> {
  try {
    const response = await api.GET("/api/personal/collections", {
      headers: await sessionHeaders(),
    });
    if (!response.data) return { kind: "unavailable" };
    return { kind: "found", collections: response.data };
  } catch {
    return { kind: "unavailable" };
  }
}
