import Link from "next/link";
import { redirect } from "next/navigation";

import { SigninForm } from "@/components/auth/signin-form";
import { AuthPageShell } from "@/components/pre-auth/auth-page-shell";
import { getSession } from "@/lib/session";

/**
 * `/signin` — the returning user's landing surface (Amendment A-20, FR-4).
 *
 * **A visitor whose cookie is still valid is sent straight to `/`**, silently
 * (`EXPERIENCE.md`: "Returns the user to session if the cookie is still valid"). That is
 * the gap this route closes: before it, a user with a live session who typed the URL had
 * nowhere sensible to land.
 *
 * The route reads the session, so it is rendered per request. It must not be prerendered
 * at build time: a build-time render would bake one visitor's answer — in practice the
 * anonymous one — into a page whose whole job is to tell them apart.
 */
export const dynamic = "force-dynamic";

export default async function SigninPage() {
  const session = await getSession();
  // `redirect` throws to unwind the render, so it is called outside any try/catch.
  if (session.kind === "signed-in") redirect("/");

  return (
    <AuthPageShell
      title="Sign in"
      lede="Welcome back. We'll take you to your Pulse Digest."
      current="/signin"
    >
      <SigninForm />
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
