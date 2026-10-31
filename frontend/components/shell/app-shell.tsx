import { BottomTabNav } from "@/components/shell/bottom-tab-nav";
import { Sidenav } from "@/components/shell/sidenav";

/**
 * `AppShell` — the authed frame: the sidenav, the brand-only topbar, and the content.
 *
 * **The topbar is brand-only** (ASSUM-11, the topbar-quiet rule): the brand mark and
 * nothing else. No nav links, no action buttons, no sign-in, no account. The sidenav is
 * the nav on desktop and the bottom-tab bar is the nav on mobile; the topbar is the
 * identity zone, and an affordance in it is an inversion.
 *
 * **The shell is a server component's shell.** The sidenav and the bottom-tab bar are
 * themselves client components — they need the current pathname to mark the active
 * route, and the Add slot opens a panel in place — but this wrapper needs none of that,
 * so it stays a server component. The *content* it wraps is passed in as `children` and
 * stays a server component too, so the digest is read on the server and rendered there.
 */
export function AppShell({
  name,
  email,
  children,
}: {
  /** The user's name, for the sidenav's account row. */
  name: string;
  /**
   * The user's email, shown in the account sheet.
   *
   * Both navs need it, because both carry the account surface: the sidenav in its footer
   * on desktop, the bottom bar's More sheet on mobile. One prop, threaded to both.
   */
  email: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen bg-surface-paper">
      <Sidenav name={name} email={email} />

      <div className="flex min-w-0 flex-1 flex-col">
        {/*
          The brand-only topbar. It carries the brand mark and nothing else — see the
          docstring. The wordmark is `aria-hidden` on the logo and the text carries the
          name, so a screen reader reads "EventPulse24" once.
        */}
        <header className="border-b border-border-subtle px-6 py-6">
          <span className="flex items-center gap-2 text-ink-primary [font:var(--type-scale-body-md)] font-semibold">
            <span aria-hidden="true" className="text-accent-terracotta">
              ◉
            </span>
            EventPulse24
          </span>
        </header>

        {/*
          The content is constrained to `--layout-container-max` (1180px) and centred,
          so at `xl` the whitespace expands *outward* and the digest does not reflow.

          **"Desktop adds whitespace, never features, screens, actions or copy"** (§10).
          A wider viewport stretches a card; a wider *card* changes how the card reads.
          So the constraint is the whole of the desktop's contribution to the layout.

          The bottom padding is the bottom-tab bar's height, so the last card is not
          hidden under it on mobile. On desktop the bar is `md:hidden`, and the padding
          is harmless.
        */}
        <main className="mx-auto w-full max-w-(--layout-container-max) flex-1 px-6 pt-8 pb-(--layout-bottom-tab-height) md:pb-12">
          {children}
        </main>
      </div>

      <BottomTabNav name={name} email={email} />
    </div>
  );
}
