"use client";

import { useState } from "react";

import { Sheet } from "@/components/sheets/sheet";
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
 * **Browse is not built yet.** So the sheet's row is an inert row, exactly like the
 * sidenav's Browse row: a `<span aria-disabled="true">` with a "Coming soon" note, not
 * a link to a 404. **A control that opens a sheet is not the same as a route that
 * exists**, and the two must not be confused — the sheet is a real, working surface
 * whose contents happen to be one inert row.
 *
 * **The sheet is dismissible.** It is an ordinary modal, not a forced choice: the user
 * opened it by tapping More and can close it by tapping outside it or pressing Escape.
 */
export function MoreMenu() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label="More destinations"
        className="flex flex-1 flex-col items-center justify-center gap-1 text-ink-muted [font:var(--type-scale-meta-sm)]"
      >
        <MoreGlyph />
        <span>More</span>
      </button>

      <Sheet open={open} onClose={() => setOpen(false)} label="More destinations">
        <div className="p-4">
          <ul className="flex flex-col gap-1">
            <li>
              {/*
                The inert row. It says what is true: Browse is on the way, and this is
                where it will be. A link to a 404 would be a lie about where the label
                goes.
              */}
              <span
                aria-disabled="true"
                className="flex items-center gap-3 rounded-subtle px-2 py-2 text-ink-secondary [font:var(--type-scale-body-md)]"
              >
                <BrowseGlyph />
                <span>Browse</span>
                <span className="ml-auto text-ink-muted [font:var(--type-scale-meta-sm)]">
                  Coming soon
                </span>
              </span>
            </li>
          </ul>
        </div>
      </Sheet>
    </>
  );
}
