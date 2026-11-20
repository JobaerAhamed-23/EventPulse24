"use client";

/**
 * The account's face — **the picture when there is one, the initials when there is not.**
 *
 * ## Why this is one component
 *
 * **The disc is drawn in three places**: the sidenav's account row, the bottom bar's
 * More sheet and the account sheet. Three copies would be three places for the fallback
 * to differ from itself in — and the difference would be visible, because the fallback
 * is *what the account looks like* to somebody who has not set a picture.
 *
 * **So the rule and the drawing are both in one place**: `lib/avatar.ts` holds the
 * initials rule, and this component holds the disc.
 *
 * ## The picture is `alt=""`, and that is the whole alt-text decision
 *
 * **The name is beside the disc, in text, always.** So the picture is *decorative* — it
 * repeats what the text beside it already says, and a screen reader that reads both
 * reads the name twice.
 *
 * **The word "avatar" is never the alt text.** "avatar" is a fact about the markup, not
 * about the person, and an alt text of "avatar" next to a name reads as
 * "avatar, Maya Ahmed" in the accessibility tree — which tells the person something
 * they did not ask about and repeats their name.
 *
 * **And the disc keeps its `aria-hidden`.** The initials fallback is *also* decorative
 * for the same reason: the letters abbreviate the name that is beside them.
 *
 * ## Why a plain `<img>` and not `next/image`
 *
 * **The URL is same-origin.** `me` hands out `/api/auth/profile/avatar/{version}` — an
 * app-owned path on the frontend's own origin, which 302s to a freshly-minted
 * presigned URL. **So there is no remote host to allowlist**, and `next/image`'s
 * optimizer — which would have to be configured with `remotePatterns` — buys nothing
 * here: it cannot optimize a URL that is a redirect to a signature that expires.
 *
 * **And the redirect is the answer to "the signature expires while the page is open".**
 * The URL the shell carries never carries a signature; the browser follows the redirect
 * under it, so the signature is minted per request and never sits in the page's HTML.
 */
import { initials } from "@/lib/avatar";

export type AvatarDiscProps = {
  /** The picture's URL, or `""` when the account has no picture. */
  avatarUrl: string;
  /** The display name — the source of the initials when there is no picture. */
  name: string;
  /** The disc's size. The rail's disc and the sheet's disc are the same size. */
  size?: "sm" | "lg";
};

/**
 * The disc.
 *
 * **The rail's size is a spacing token; the sheet's is an exact one.** The rail's disc
 * is 32px, and 32px is a step on the spacing scale — so it is `size-8`. **The sheet's is
 * 40px, and 40px is not a step on the scale**, so it is written as the exact size it
 * is: `size-[40px]`. The tenth step of Tailwind's own scale would generate no CSS at
 * all here — the scale reset makes off-scale utilities silently absent, which is a disc
 * with no size rather than an error.
 */
export function AvatarDisc({ avatarUrl, name, size = "sm" }: AvatarDiscProps) {
  const dimension = size === "lg" ? "size-[40px]" : "size-8";
  const typeScale =
    size === "lg" ? "[font:var(--type-scale-body-md)]" : "[font:var(--type-scale-meta-sm)]";

  if (avatarUrl !== "") {
    return (
      /*
        **The picture, with `alt=""`.** The name is beside it in text, so the image is
        decorative — and "avatar" is not an alt text anybody wants read aloud next to
        their own name.

        **`object-cover`**, so a square crop of a wide photograph fills the circle
        rather than being letterboxed inside it.

        **`aria-hidden` on the wrapper**, because the image itself is decorative and the
        wrapper is what the initials fallback is hidden behind.

        **`data-avatar-disc` on the wrapper.** The picture is *out* of the accessibility
        tree by design, so a screen-reader locator cannot reach it — and a test that
        needs to know whether the rail is showing a picture or the initials has to
        look at the DOM. The hook is on the wrapper rather than the `<img>` so it names
        **the disc**, which is the thing being drawn, rather than one of its two forms.
      */
      <span
        aria-hidden="true"
        data-avatar-disc
        className={`flex ${dimension} shrink-0 items-center justify-center overflow-hidden rounded-full bg-surface-inset`}
      >
        <img src={avatarUrl} alt="" className="size-full object-cover" />
      </span>
    );
  }

  return (
    /*
      **The initials.** The fallback, and it is a real one: the disc still says who this
      is, so an account with no picture looks like an account rather than like a hole in
      the rail.

      **`aria-hidden`**, for the same reason the picture is: the name is beside it.

      **`data-avatar-disc` on the wrapper too**, for the same reason the picture's is
      there — so a test can ask the disc what it is showing without knowing which of its
      two forms it took.
    */
    <span
      aria-hidden="true"
      data-avatar-disc
      className={`flex ${dimension} shrink-0 items-center justify-center rounded-full bg-surface-inset text-ink-secondary ${typeScale}`}
    >
      {initials(name)}
    </span>
  );
}
