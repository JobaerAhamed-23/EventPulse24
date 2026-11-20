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
  avatarUrl,
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
  /**
   * The user's picture — `""` when the account has none.
   *
   * **It is the seed, not the truth.** The shell is rendered on the server, so this is
   * the picture the page was drawn with; a picture uploaded *after* the render is
   * newer, and the shell reads it from the avatar store. Threading it here is what
   * puts the picture in all three places — the rail, the bottom bar and the account
   * sheet — from one seed.
   */
  avatarUrl: string;
  children: React.ReactNode;
}) {
  return (
    // **The shell is full-bleed: the rail sits on the viewport's left edge and the
    // content runs to its right edge.** A capped, centred shell put equal margins
    // outside it, which read as dead space at both edges rather than as composition —
    // so the cap is gone and the app occupies the window it is given.
    <div className="flex min-h-screen bg-surface-paper">
      <Sidenav name={name} email={email} avatarUrl={avatarUrl} />

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
          **The content fills the column the rail leaves, at every width.** It used to
          be capped at `--layout-container-max` (1180px) and centred inside that column
          — the §10 reading, "desktop adds whitespace, never features, screens, actions
          or copy", applied as a hard container.

          **Two things were wrong with it in the authed shell.** The rail is a flex
          sibling, so it had already taken its width off the left before this `mx-auto`
          saw any surplus: the content sat half a rail right of the screen's centre,
          and the surplus opened as a dead band between the rail and the first pixel of
          content — 570px of it at 2560px, with the content beginning 810px in. Capping
          the *shell* instead made the two outer gutters equal, but equal gutters are
          still gutters, and at 2560px they were 570px of nothing at each edge.

          **So the app is full-bleed and the whitespace rule lives in the padding
          instead.** §10 still holds in the sense that matters — a wider viewport adds
          no features, screens, actions or copy — it simply no longer buys that with
          margins the reader reads as emptiness. The public surfaces keep their own
          container: they have no rail, so theirs centres on the viewport and composes.

          **The frame is the whitespace now, and it is the design's own three steps.**
          `--layout-page-padding-mobile|tablet|desktop` (24px, 48px, 80px) were defined
          in `tokens.css` and used by nothing — `<main>` hardcoded `px-6` at every
          width, so a 2560px window got the same 24px edge as a phone. They are wired
          here, which is the one place every authed surface passes through.

          **Every surface therefore shares one left edge.** Browse used to add `px-2`
          on top of this to make its own 32px frame, which put its heading 8px right of
          Settings', Timeline's and the digest's — an 8px step the reader walks into on
          every nav change. The frame belongs to the shell, so Browse no longer carries
          one.

          The bottom padding is the bottom-tab bar's height, so the last card is not
          hidden under it on mobile. On desktop the bar is `md:hidden`, and the padding
          is harmless.
        */}
        <main className="w-full flex-1 px-(--layout-page-padding-mobile) pt-8 pb-(--layout-bottom-tab-height) md:px-(--layout-page-padding-tablet) md:pb-12 xl:px-(--layout-page-padding-desktop)">
          {children}
        </main>
      </div>

      <BottomTabNav name={name} email={email} avatarUrl={avatarUrl} />
    </div>
  );
}
