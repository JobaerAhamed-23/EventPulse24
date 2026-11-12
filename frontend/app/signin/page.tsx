import Link from "next/link";
import { redirect } from "next/navigation";

import { SigninForm } from "@/components/auth/signin-form";
import { AuthPageShell } from "@/components/pre-auth/auth-page-shell";
import { returnPath } from "@/lib/return-path";
import { getSession } from "@/lib/session";

/**
 * `/signin` — the returning user's landing surface (Amendment A-20, FR-4).
 *
 * **A visitor whose cookie is still valid is sent straight to `/`**, silently
 * (`EXPERIENCE.md`: "Returns the user to session if the cookie is still valid"). That is
 * the gap this route closes: before it, a user with a live session who typed the URL had
 * nowhere sensible to land.
 *
 * **A visitor who came here to do something is sent back to it.** The `next` parameter
 * carries where they were going — the pricing page sends a signed-out visitor here with
 * `/pricing`, so a person who chose a plan and was asked to sign in lands back on the
 * pricing page with their intent intact, rather than at the digest home with the intent
 * gone.
 *
 * **`next` is guarded, and the guard is not optional.** It is a redirect target taken
 * from the query string, so an unguarded one is an open redirect — the classic link
 * that sends somebody who has just typed their password to somebody else's site.
 * `returnPath()` accepts only a path on this site and falls back to `/` for anything
 * else; the rules are in `lib/return-path.ts` and are tested there.
 *
 * The route reads the session, so it is rendered per request. It must not be prerendered
 * at build time: a build-time render would bake one visitor's answer — in practice the
 * anonymous one — into a page whose whole job is to tell them apart.
 */
export const dynamic = "force-dynamic";

export default async function SigninPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const session = await getSession();
  // **The path is resolved before the session check**, so a visitor whose cookie is
  // already valid is returned to where they were going rather than to the home.
  const { next } = await searchParams;
  const destination = returnPath(next);

  // `redirect` throws to unwind the render, so it is called outside any try/catch.
  if (session.kind === "signed-in") redirect(destination);

  return (
    <AuthPageShell
      title="Sign in"
      lede="Welcome back. We'll take you to your Pulse Digest."
      current="/signin"
    >
      <SigninForm next={destination} />
      <div className="mt-8 border-t border-border-subtle pt-6 text-center">
        <p className="[font:var(--type-scale-body-sm)] text-ink-secondary">
          New to EventPulse24?{" "}
          <Link href="/signup" className="text-accent-terracotta underline underline-offset-4">
            Sign up →
          </Link>
        </p>
        <p className="mt-2 [font:var(--type-scale-body-sm)] text-ink-muted">
          By signing in, you agree to our{" "}
          <Link href="/terms" className="underline underline-offset-4">
            Terms
          </Link>{" "}
          and{" "}
          <Link href="/privacy" className="underline underline-offset-4">
            Privacy Policy
          </Link>
          .
        </p>
      </div>
    </AuthPageShell>
  );
}
