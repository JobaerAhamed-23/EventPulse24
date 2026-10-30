import { redirect } from "next/navigation";

import { SignupForm } from "@/components/auth/signup-form";
import { AuthPageShell } from "@/components/pre-auth/auth-page-shell";
import { getSession } from "@/lib/session";

/**
 * `/signup` — account creation (Amendment A-20, FR-1).
 *
 * A signed-in visitor is sent to `/` the way `/signin` sends them. `EXPERIENCE.md` states
 * the rule for `/signin` only, but the reason carries over exactly: someone who already
 * has a session has nothing to create, and showing them a sign-up form invites a second
 * account they did not want.
 *
 * The column is the wider of the two (520 px) because the OIDC provider stack belongs
 * above the form. The stack itself is a later intent's work; its position is held in
 * `SignupForm`.
 */
export const dynamic = "force-dynamic";

export default async function SignupPage() {
  const session = await getSession();
  if (session.kind === "signed-in") redirect("/");

  return (
    <AuthPageShell
      title="Create your account"
      lede="Three events a day, one notification, no feeds. Free in Brooklyn and 200+ cities."
      current="/signup"
      wide
    >
      <SignupForm />
    </AuthPageShell>
  );
}
