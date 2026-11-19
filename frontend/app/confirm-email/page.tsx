import type { Metadata } from "next";

import { ConfirmEmailForm } from "@/components/auth/confirm-email-form";
import { AuthPageShell } from "@/components/pre-auth/auth-page-shell";

/**
 * `/confirm-email` — where the link in the confirmation mail lands.
 *
 * ## It must work signed out, and that is the whole difficulty
 *
 * The link is opened from a mailbox, and the browser reading that mailbox may never have
 * signed in to this product. **So this route cannot sit behind `homeRoute(session)`**,
 * which sends an anonymous visitor to `/preview` — a confirmation link that gets
 * redirected is a confirmation link that does not work. It is a pre-auth route, like
 * `/reset-password`, and it is built on the same shell for that reason.
 *
 * ## `referrer: "no-referrer"`, for the same reason the reset route has it
 *
 * **The token is a bearer credential and it is in the URL.** Without this, any request
 * this page makes to another origin would carry the whole URL — token included — in its
 * `Referer` header. The form also strips the query string from the address bar once it
 * has read the token, so it does not sit in history or in a shared screenshot.
 *
 * ## The token is spent by a POST, never by loading the page
 *
 * **A `GET` that moves a login is performed by every mail scanner and link prefetcher
 * that touches the message.** The account would change address because a security
 * appliance followed a link. So this page renders a form and the *person* submits it.
 *
 * ## There is no "is this token still good?" check
 *
 * The same reason `/reset-password` has none: there is no way to ask without spending it,
 * and an endpoint that answered would be an oracle for guessed tokens. Expired, already
 * used, and address-taken-in-the-meantime all appear on submit, as one message.
 */
export const metadata: Metadata = {
  title: "Confirm your email address",
  referrer: "no-referrer",
};

/** The token comes from the request, so the route cannot be prerendered. */
export const dynamic = "force-dynamic";

export default async function ConfirmEmailPage({ searchParams }: PageProps<"/confirm-email">) {
  const { token } = await searchParams;
  // A repeated `?token=a&token=b` arrives as an array. There is one token per link, so a
  // list is not one of ours; it is treated as no token rather than guessed at.
  const single = typeof token === "string" && token !== "" ? token : null;

  return (
    <AuthPageShell
      title="Confirm your email address"
      lede={
        single === null
          ? "This page needs the link from the email we sent you."
          : "One step, and your account moves to this address."
      }
    >
      <ConfirmEmailForm token={single} />
    </AuthPageShell>
  );
}
