"use client";

import { useCallback, useState } from "react";

import { PersonalEventsPanel } from "@/components/personal-events-panel";
import { TimelineBlockView } from "@/components/timeline/timeline-block";
import { QuietDay } from "@/components/timeline/timeline-states";
import type { TimelineBlock, TimelineDay } from "@/lib/timeline-read";
import { dayOfMonth, weekdayShort, type LocalDate } from "@/lib/timeline-dates";

/**
 * The Timeline's client island.
 *
 * **The only interactive thing on the Timeline is the edit sheet.** The Timeline is
 * read-only at MVP (ASSUM-7): no drag-to-reschedule, no inline rename, no inline
 * conflict resolution. What it does have is the **Edit personal event** sheet, which
 * already exists — `PersonalEventsPanel` owns the create → conflict → resolve → edit
 * round trip, and the sheet is native `<dialog>`, so closed it takes no space.
 *
 * **Why both layouts are drawn here and not on the server.** A personal block is a
 * **button** that opens the sheet, and the sheet's state lives in the panel's island. A
 * server-rendered button cannot reach it — there is no context to reach across the
 * boundary, and a custom DOM event would be a worse version of the same idea. So the
 * island draws the blocks.
 *
 * **The server still decides everything about them.** The days, the order, the
 * indicator, the names and the times are the server's, and they arrive here as plain
 * data — the island draws them and decides nothing (AD-10).
 *
 * **The refresh needs no extra call.** The panel already calls `router.refresh()` after
 * a successful write, and the Timeline is a server component — so a saved edit re-runs
 * the server read and the week re-renders with the new time.
 */
export function TimelinePanel({
  days,
  today,
  mobileDay,
}: {
  /** The week's days, in the server's order. */
  days: TimelineDay[];
  /** Today's date, in the user's zone. */
  today: LocalDate;
  /** The day the mobile view shows, or `null` when there is none. */
  mobileDay: LocalDate | null;
}) {
  const [editing, setEditing] = useState<string | null>(null);

  const openEdit = useCallback((block: TimelineBlock) => setEditing(block.id), []);

  // **The blocks become the sheet's seeds.** The panel takes the narrow shape the
  // sheet reads, so nothing is invented: the block payload carries no `version`, and
  // a fabricated one would be a lie about the event.
  const personalEvents = days
    .flatMap((day) => day.blocks)
    .filter((block) => block.kind === "personal")
    .map((block) => ({
      id: block.id,
      name: block.name ?? "Personal event",
      start_time_utc: block.start_time_utc,
      end_time_utc: block.end_time_utc ?? null,
      start_time_tz: block.start_time_tz,
    }));

  const shownDay = days.find((day) => day.date === mobileDay) ?? null;

  return (
    <>
      {/*
        The panel mounts only the flow's sheets. It once had a list branch too, which
        *whole* would push a headline between the week's grid and the nav, and the
        Timeline has its own heading.
      */}
      <PersonalEventsPanel
        editingEvents={personalEvents}
        editingEventId={editing}
        onEditingEventChange={setEditing}
      />

      {/*
        The desktop grid. Seven columns, one continuous grid: only the outer corners
        round, and the inner shared edges are square, so the columns read as one
        surface rather than as seven cards.
      */}
      <div
        aria-label="Week grid"
        className="hidden overflow-hidden rounded-timeline-cell border border-border-subtle bg-surface-elevated md:grid md:grid-cols-(--layout-timeline-grid)"
      >
        {days.map((day) => (
          <DayColumn key={day.date} day={day} isToday={day.date === today} onEdit={openEdit} />
        ))}
      </div>

      {/*
        The mobile stack: one day at a time. The blocks are the server's, in the
        server's order.
      */}
      {shownDay ? (
        <section aria-label={shownDay.date} className="flex flex-col gap-3 md:hidden">
          {shownDay.blocks.length === 0 ? (
            <QuietDay />
          ) : (
            shownDay.blocks.map((block) => (
              <TimelineBlockView key={block.id} block={block} onEditPersonal={openEdit} />
            ))
          )}
        </section>
      ) : null}
    </>
  );
}

/**
 * One day of the week grid.
 *
 * **Today's column is marked twice**: the fill swaps to `surface.subtle`, and the date
 * number is terracotta — `Indicator.Today`'s treatment, the sanctioned terracotta use.
 * The cell also carries `aria-current="date"`, so a screen reader knows which column
 * is today without reading the colour.
 */
function DayColumn({
  day,
  isToday,
  onEdit,
}: {
  day: TimelineDay;
  isToday: boolean;
  onEdit: (block: TimelineBlock) => void;
}) {
  return (
    <section
      aria-label={day.date}
      aria-current={isToday ? "date" : undefined}
      className={[
        "flex min-h-[480px] flex-col gap-2 border-r border-border-subtle p-3 last:border-r-0",
        isToday ? "bg-surface-subtle" : "",
      ].join(" ")}
    >
      {/*
        The column header: the day-of-week in muted meta ink, the date number in
        primary. **Today's date number is terracotta** — the same treatment the Pulse
        Card's `Indicator.Today` dot gets.
      */}
      <header className="flex items-baseline gap-2 border-b border-border-subtle pb-2">
        <span className="[font:var(--type-scale-meta-sm)] text-ink-muted uppercase">
          {weekdayShort(day.date)}
        </span>
        <span
          className={[
            "[font:var(--type-scale-meta-md)]",
            isToday ? "text-accent-terracotta" : "text-ink-primary",
          ].join(" ")}
        >
          {dayOfMonth(day.date)}
        </span>
      </header>

      {day.blocks.length === 0 ? (
        <QuietDay />
      ) : (
        day.blocks.map((block) => (
          <TimelineBlockView key={block.id} block={block} onEditPersonal={onEdit} />
        ))
      )}
    </section>
  );
}
