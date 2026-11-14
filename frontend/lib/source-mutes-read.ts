import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The source registry and the signed-in user's visibility settings (FR-13, FR-16).
 *
 * **A failure is "unavailable", not "you have no sources".** The two look identical on
 * screen and mean opposite things — a user whose read blinked would be shown an empty
 * registry, on the very screen whose job is to tell them what is informing their
 * timeline.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and an anonymous read of somebody's settings is nobody's settings.
 *
 * **This module is server-only.** It reaches `sessionHeaders()`, and so `next/headers` —
 * a `"use client"` component importing it breaks the production build.
 */
export type SourceMuteState = "mute" | "show_less" | "default";

export type RegistrySource = components["schemas"]["SourceOut"];
export type RegistryGroup = components["schemas"]["SourceGroupOut"];

export type SourcesRead = { kind: "found"; groups: RegistryGroup[] } | { kind: "unavailable" };

export async function readSources(): Promise<SourcesRead> {
  try {
    const response = await api.GET("/api/settings/sources", {
      headers: await sessionHeaders(),
    });
    if (!response.data) return { kind: "unavailable" };
    return { kind: "found", groups: response.data.groups };
  } catch {
    return { kind: "unavailable" };
  }
}
