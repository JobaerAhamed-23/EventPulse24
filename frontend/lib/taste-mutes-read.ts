import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The signed-in user's muted categories (FR-25).
 *
 * **A failure is "unavailable", not "you have no muted categories".** The two look
 * identical on screen and mean opposite things — a user whose read blinked would be
 * shown an empty list, on the very screen whose job is to let them undo what they
 * muted.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and an anonymous read of somebody's settings is nobody's settings.
 *
 * **This module is server-only.** It reaches `sessionHeaders()`, and so `next/headers` —
 * a `"use client"` component importing it breaks the production build.
 */
export type CategoryMute = components["schemas"]["CategoryMuteOut"];

export type TasteRead = { kind: "found"; mutes: CategoryMute[] } | { kind: "unavailable" };

export async function readTaste(): Promise<TasteRead> {
  try {
    const response = await api.GET("/api/settings/taste", {
      headers: await sessionHeaders(),
    });
    if (!response.data) return { kind: "unavailable" };
    return { kind: "found", mutes: response.data.mutes };
  } catch {
    return { kind: "unavailable" };
  }
}
