"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Sheet } from "@/components/sheets/sheet";
import { AccountPanel, type AccountProps } from "@/components/shell/account-menu";
import { BrowseGlyph, MoreGlyph } from "@/components/shell/nav-glyphs";

/**
 * `Component.BottomTab.MoreMenu` — the overflow sheet behind the bottom-tab's trailing
 * affordance.
 *
 * **Browse is the sixth route, and it does not fit in five slots.** The bottom-tab's
 * geometry is five slots at twenty percent each, and Browse lives behind **More** on
 * the trailing edge. So More is a **control, not a route**: it opens this sheet, and it
 * carries no `aria-current="page"` — the row *inside* the sheet carries that when
 * Browse is the current one.
 *
 * **Browse is a real route now.** The Browse surface shipped, so the sheet's row is a
 * link — the same `/browse` the sidenav's Browse row points at, so a phone and a
 * desktop land on the same place.
 *
 * **The row carries `aria-current="page"` when Browse is the current route.** More
 * itself carries none, and that distinction is the point: **More is a control and the
 * row is a route.** A screen-reader user on `/browse` needs to be told where they are,
 * and the thing they are in is the sheet's row, not the button that opened the sheet.
 *
 * **The sheet is dismissible.** It is an ordinary modal, not a forced choice: the user
 * opened it by tapping More and can close it by tapping outside it or pressing Escape.
 *
 * **The account panel is here because the sidenav is not.** The rail is `hidden md:flex`,
 * so mounting Sign out only in its footer would leave every phone with no way out of a
 * session. This sheet is the one non-route control the bottom bar has, so the same
 * `AccountPanel` the rail opens is rendered here *inline* — a sheet inside a sheet would
 * be a second overlay level, and `Sheet` keeps there being exactly one.
 */
export function MoreMenu({ name, email, avatarUrl }: AccountProps) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label="More"
        className="flex flex-1 flex-col items-center justify-center gap-1 text-ink-muted [font:var(--type-scale-meta-sm)]"
      >
        <MoreGlyph />
        <span>More</span>
      </button>

      <Sheet open={open} onClose={() => setOpen(false)} label="More">
        <div className="p-4">
          <ul className="flex flex-col gap-1">
            <li>
              {/*
                **The route row.** It was an inert `<span aria-disabled="true">` with a
                "Coming soon" note, because a link to a 404 is a lie about where the
                label goes. The surface exists now, so the lie would be the other way
                round — a stub claiming there is nothing there when there is a whole
                city to browse.

                **The active rule is an equality.** Browse has no child routes, so a
                prefix rule would be a claim about screens that do not exist.
              */}
              <Link
                href="/browse"
                aria-current={pathname === "/browse" ? "page" : undefined}
                className="flex items-center gap-3 rounded-subtle px-2 py-2 text-ink-secondary hover:bg-surface-subtle hover:text-ink-primary [font:var(--type-scale-body-md)]"
              >
                <BrowseGlyph />
                <span>Browse</span>
              </Link>
            </li>
          </ul>

          {/*
            The account panel, below a rule. It is not a destination, so it is outside the
            list: a Sign out button inside a `<ul>` of routes would read as a sixth route.
          */}
          <div className="my-3 h-px bg-border-subtle" />
          <AccountPanel name={name} email={email} avatarUrl={avatarUrl} />
        </div>
      </Sheet>
    </>
  );
}
