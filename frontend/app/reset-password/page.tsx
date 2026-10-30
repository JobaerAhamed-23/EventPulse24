import type { Metadata } from "next";

import { ResetConfirmForm } from "@/components/auth/reset-confirm-form";
import { ResetRequestForm } from "@/components/auth/reset-request-form";
import { AuthPageShell } from "@/components/pre-auth/auth-page-shell";

/**
 * `/reset-password` — one route, two jobs.
 *
 * Without a token it is the **request** form: an address, and the locked success line
 * "We've sent a reset link to {email}.". With a token — the link in the reset email is
 * `{FRONTEND_BASE_URL}/reset-password?token=…` (`apps/identity/services/emails.py`) — it
 * is the **set-a-new-password** form.
 *
 * **`referrer: "no-referrer"`.** The token is a 30-minute bearer credential for the
 * account, and it is in the URL. Without this, any request this page makes to another
 * origin would carry the full URL in its `Referer` header. The client form also strips
 * the query string from the address bar once it has the token.
 *
 * The expired-or-used state is the confirm form's, and it appears on submit: there is no
 * way to ask whether a token is still good without spending it, and an endpoint that
 * answered would be an oracle for guessed tokens.
 */
export const metadata: Metadata = {
  title: "Reset your password",
  referrer: "no-referrer",
};

/** The token comes from the request, so the route cannot be prerendered. */
export const dynamic = "force-dynamic";

export default async function ResetPasswordPage({ searchParams }: PageProps<"/reset-password">) {
  const { token } = await searchParams;
  // A repeated `?token=a&token=b` arrives as an array. There is one token per link, so a
  // list is not one of ours; it is treated as no token rather than guessed at.
  const single = typeof token === "string" && token !== "" ? token : null;

  return (
    <AuthPageShell
      title={single === null ? "Reset your password" : "Set a new password"}
      lede={
        single === null
          ? "We'll email you a link. It works once, and for 30 minutes."
          : "Choose a new password. Your other sessions will end."
      }
    >
      {single === null ? <ResetRequestForm /> : <ResetConfirmForm token={single} />}
    </AuthPageShell>
  );
}
