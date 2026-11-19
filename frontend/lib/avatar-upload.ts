import { api } from "@/lib/backend-client";

/**
 * Uploading and removing the profile picture — **the one place that sends a file**.
 *
 * ## Why this file exists at all
 *
 * This is the project's first `multipart/form-data` endpoint, and two things about the
 * generated client cannot express it. Both are handled here, once, rather than in every
 * component that wants to upload a picture.
 *
 * **1. The generated type says `string`, and a `File` is not a string.** OpenAPI describes
 * the field as `type: string, format: binary`; `openapi-typescript` has no TypeScript
 * equivalent for that and emits `file: string`. There is no CLI flag to change it — the
 * generator's `transform` hook is Node-API only, and `make client` is the one sanctioned
 * way to produce `schema.ts` (AD-19), so the generator is left alone and the mismatch is
 * absorbed here in a single cast that this comment explains.
 *
 * **2. `openapi-fetch` serialises bodies as JSON by default.** A `FormData` body must be
 * passed through untouched, because the browser has to set the `multipart/form-data`
 * boundary itself — a hand-written `Content-Type` header would omit the boundary and the
 * server would fail to parse the body. `bodySerializer` is how openapi-fetch is told to
 * leave it alone.
 *
 * **The CSRF token rides along automatically.** `backend-client` registers
 * `csrfOnRequest` on this client, so these writes carry the token like every other write
 * in the app.
 */

/** What the caller gets back: the saved profile, or a message to show the person. */
export type AvatarResult =
  | { kind: "saved"; avatarUrl: string }
  | { kind: "refused"; message: string };

/** The message shown when the server refused but said nothing usable. */
const FALLBACK_MESSAGE = "That picture couldn't be saved. Try a different one.";

function refusal(error: unknown): AvatarResult {
  // The project's error shape is `{code, message, details}`; the message is written for
  // the person who typed it, so it is shown as-is when present.
  const message =
    typeof error === "object" && error !== null && "message" in error
      ? String((error as { message: unknown }).message)
      : "";
  return { kind: "refused", message: message || FALLBACK_MESSAGE };
}

/**
 * Store `file` as the signed-in user's profile picture.
 *
 * The server validates the bytes — the filename and the browser's guessed content type
 * are not trusted — so no client-side check is a substitute for the refusal path. A
 * client-side size check is still worth doing before calling this, to save the person a
 * round trip, but it is politeness rather than enforcement.
 */
export async function uploadAvatar(file: File): Promise<AvatarResult> {
  const form = new FormData();
  form.append("file", file);

  const { data, error } = await api.POST("/api/auth/profile/avatar", {
    // See the module docstring: the generated type says `string` because OpenAPI's
    // `format: binary` has no TypeScript equivalent, and this is the one place that
    // reconciles the two.
    body: form as unknown as { file: string },
    // Pass the FormData straight through, so the browser sets the multipart boundary.
    bodySerializer: (body: unknown) => body as FormData,
  });

  if (error || !data) return refusal(error);
  return { kind: "saved", avatarUrl: data.avatar_url };
}

/** Remove the signed-in user's profile picture. Removing nothing is a success. */
export async function removeAvatar(): Promise<AvatarResult> {
  const { data, error } = await api.DELETE("/api/auth/profile/avatar", {});

  if (error || !data) return refusal(error);
  return { kind: "saved", avatarUrl: data.avatar_url };
}
