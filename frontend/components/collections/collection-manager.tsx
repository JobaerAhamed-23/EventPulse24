"use client";

/**
 * Collections, on screen for the first time (FR-49) — create, rename, reorder, delete, and
 * take a save out of one.
 *
 * **This surface has no approved design, and that is a fact about the build rather than an
 * oversight.** EXPERIENCE.md's coverage table claims `settings-desktop.html` covers FR-49;
 * TRACEABILITY.md checked and found *"the mockup contains zero 'collection' content"*. So
 * it is assembled from the design system's existing vocabulary — the quiet empty state, the
 * settings surfaces' controls, the inline prompt — and invents no new visual language. If
 * it ever grows past a modest management UI, that is the signal to stop and get a design
 * pass.
 *
 * **Reorder is move up / move down, not drag.** It is keyboard-operable with no pointer, it
 * needs no library, and it needs no motion — the product has exactly one transition and
 * `styles/motion.test.ts` fails the suite on any other animation. Each press sends the
 * **whole ordering** in one request, which is what `saved-collections-api` requires so the
 * server never sees a partially reordered list.
 *
 * **Delete confirms in place, and the copy says what survives.** "Delete" sitting above a
 * list of events reads as deleting the events, so the confirmation names the truth: the
 * saves stay saved. No overlay and no focus trap — a grouping being removed does not
 * warrant the weight A-16 specifies for deleting an account.
 *
 * **The server's list is the source of truth after every write.** Each command returns the
 * list or is followed by a re-read, so positions and counts come from the server rather
 * than from an optimistic guess that could drift.
 */
import { useCallback, useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";
import type { CollectionOut } from "@/lib/collections-read";

/** One save inside a collection — the snapshot, which is all the API returns. */
type CollectionEvent = {
  id: string;
  event_id: string;
  start_time_utc: string;
  end_time_utc: string | null;
  event_version: number;
};

/**
 * One of the user's saves, as the picker needs it.
 *
 * **This comes from a different endpoint than the collection's contents, and deliberately
 * so.** `CollectionEventOut` carries no title, because *"reading them here would put a
 * `catalog` query behind a `personal` endpoint, and AD-3 forbids relating the two"*
 * (`schemas.py:1461`). Its docstring names the remedy: *"A surface that wants titles has
 * `GET /api/personal/saved-events`, which is the endpoint that owns that join."* The picker
 * wants titles — a list of bare timestamps is not something a person can choose from — so
 * it reads that endpoint.
 *
 * **The two endpoints agree about identity.** `SavedEventOut.id` is *"the personal row's
 * id"* and `CollectionEventOut.id` is *"the personal save's id — its identity, and what
 * membership points at"*. The same id, so "already in this collection" is a set difference
 * and not a translation.
 */
type AssignableSave = {
  id: string;
  title: string;
  start_time_utc: string;
};

export type CollectionManagerProps = {
  /** The user's collections, in their order, as the server read them. */
  initial: CollectionOut[];
};

/** The offline failure line. Nothing was lost, so it invites a retry. */
const FAILED = "Couldn't save that. Try again in a moment.";

/**
 * The picker's read failure.
 *
 * **A read is not a save, and the line says so.** Reusing `FAILED` here would tell a user
 * whose saves failed to load that we could not save something — a sentence about the wrong
 * operation, on a screen where both happen.
 */
const READ_FAILED = "Couldn't read your saves. Try again in a moment.";

/** One stored instant as a date a person reads. */
function readableWhen(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function CollectionManager({ initial }: CollectionManagerProps) {
  const [collections, setCollections] = useState<CollectionOut[]>(initial);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  /** Which collection is awaiting a delete confirmation, if any. */
  const [confirming, setConfirming] = useState<string | null>(null);
  /** Which collection is being renamed, and to what. */
  const [renaming, setRenaming] = useState<{ id: string; value: string } | null>(null);
  /** Which collection is expanded, and the saves inside it. */
  const [opened, setOpened] = useState<{ id: string; events: CollectionEvent[] } | null>(null);
  /**
   * The picker's state: whether it is open, and what the user has to choose from.
   *
   * **`saves` is `null` until the read lands**, which is how "not read yet" is told apart
   * from "read, and there are none". The two look identical on screen and mean opposite
   * things — the same distinction the collections page draws between "unavailable" and
   * "you have none".
   */
  const [picking, setPicking] = useState<{ saves: AssignableSave[] | null } | null>(null);

  /** Re-read the list, so positions and counts are the server's rather than a guess. */
  const refresh = useCallback(async (): Promise<void> => {
    const response = await api.GET("/api/personal/collections");
    if (response.data) setCollections(response.data);
  }, []);

  /**
   * Run one write, then re-read.
   *
   * **The failure line is set from the server's own refusal when there is one.** A cap
   * refusal reaches here as a 409 whose `upgrade_hint` the page above renders — this
   * component shows the message and does not try to build a second prompt.
   */
  const run = useCallback(
    async (write: () => Promise<{ error?: unknown; data?: unknown }>): Promise<boolean> => {
      setBusy(true);
      setFailure(null);
      try {
        const response = await write();
        if (response.error) {
          setFailure(saveFailureMessage(response.error, FAILED) || FAILED);
          return false;
        }
        await refresh();
        return true;
      } catch {
        setFailure(FAILED);
        return false;
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const create = useCallback(async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const ok = await run(() => api.POST("/api/personal/collections", { body: { name: trimmed } }));
    if (ok) setName("");
  }, [name, run]);

  const rename = useCallback(async () => {
    if (!renaming) return;
    const trimmed = renaming.value.trim();
    if (!trimmed) return;
    const ok = await run(() =>
      api.PATCH("/api/personal/collections/{collection_id}", {
        params: { path: { collection_id: renaming.id } },
        body: { name: trimmed },
      }),
    );
    if (ok) setRenaming(null);
  }, [renaming, run]);

  const remove = useCallback(
    async (id: string) => {
      const ok = await run(() =>
        api.DELETE("/api/personal/collections/{collection_id}", {
          params: { path: { collection_id: id } },
        }),
      );
      if (ok) {
        setConfirming(null);
        if (opened?.id === id) setOpened(null);
      }
    },
    [opened, run],
  );

  /**
   * Move one collection one place, by sending the **whole** resulting order.
   *
   * A pairwise swap endpoint would let the server observe a half-reordered list; the API
   * takes the complete ordering for exactly that reason.
   */
  const move = useCallback(
    async (index: number, delta: number) => {
      const target = index + delta;
      if (target < 0 || target >= collections.length) return;
      const next = [...collections];
      const [moved] = next.splice(index, 1);
      if (!moved) return;
      next.splice(target, 0, moved);
      await run(() =>
        api.PUT("/api/personal/collections/order", {
          body: { collection_ids: next.map((collection) => collection.id) },
        }),
      );
    },
    [collections, run],
  );

  /**
   * Read one collection's contents and show them. **This does not toggle.**
   *
   * `open()` is the toggle, and a write that wants to refresh what is on screen must not
   * go through it: calling `open()` on the collection that is already open *closes* it, so
   * an assign that re-read that way would collapse the collection the user is filling.
   */
  const readEvents = useCallback(async (id: string): Promise<void> => {
    const response = await api.GET("/api/personal/collections/{collection_id}/events", {
      params: { path: { collection_id: id } },
    });
    setOpened({ id, events: (response.data as CollectionEvent[] | undefined) ?? [] });
  }, []);

  /** Open a collection and read what is in it — or close it if it is already open. */
  const open = useCallback(
    async (id: string) => {
      // **Closing or switching closes the picker.** It belongs to the collection it was
      // opened inside; leaving it up across a switch would offer to assign into a
      // collection the user is no longer looking at.
      setPicking(null);
      if (opened?.id === id) {
        setOpened(null);
        return;
      }
      setFailure(null);
      await readEvents(id);
    },
    [opened, readEvents],
  );

  /**
   * Open the picker and read the user's saves.
   *
   * **The read happens here, not in `open()`.** A user who expands a collection to look at
   * what is in it does not pay for a saves read; only pressing "Add a save" does. The saves
   * list is unbounded for a Pro account, so this is not a trivial difference.
   */
  const startPicking = useCallback(async (): Promise<void> => {
    setFailure(null);
    setPicking({ saves: null });
    try {
      const response = await api.GET("/api/personal/saved-events");
      // **No refusal to quote, so none is invented.** This endpoint declares a 200 and
      // nothing else, so the generated client types its `error` as `never` — there is no
      // server sentence to render, and `saveFailureMessage`'s refusal branch would be
      // dead code here. A missing body is the only failure shape there is.
      if (!response.data) {
        setFailure(READ_FAILED);
        setPicking(null);
        return;
      }
      const items = (response.data as { items?: AssignableSave[] }).items ?? [];
      setPicking({ saves: items });
    } catch {
      setFailure(READ_FAILED);
      setPicking(null);
    }
  }, []);

  /**
   * Put one save into the open collection.
   *
   * **The write goes through `run()`**, which owns the refusal/offline split every other
   * command here uses. A Free account's 409 carries `{cap, upgrade_hint}` and
   * `saveFailureMessage` renders the server's own sentence — this component builds no
   * second prompt, and a cap is never a modal.
   */
  const assign = useCallback(
    async (collectionId: string, savedEventId: string): Promise<void> => {
      const ok = await run(() =>
        api.PUT("/api/personal/collections/{collection_id}/events/{saved_event_id}", {
          params: { path: { collection_id: collectionId, saved_event_id: savedEventId } },
        }),
      );
      // **Re-read rather than splice.** The server's list is this component's source of
      // truth after every write, and the re-read is what removes the save from the picker:
      // the picker is derived from what the collection holds, so it cannot drift from it.
      // `readEvents`, not `open` — `open` would toggle the collection shut.
      if (ok) await readEvents(collectionId);
    },
    [readEvents, run],
  );

  const unassign = useCallback(
    async (collectionId: string, savedEventId: string) => {
      const ok = await run(() =>
        api.DELETE("/api/personal/collections/{collection_id}/events/{saved_event_id}", {
          params: {
            path: { collection_id: collectionId, saved_event_id: savedEventId },
          },
        }),
      );
      if (ok) await open(collectionId === opened?.id ? collectionId : collectionId);
    },
    [open, opened, run],
  );

  return (
    <section aria-label="Collections" data-collection-manager>
      {/* ── Create ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-ink-secondary [font:var(--type-scale-meta-sm)]">
            New collection
          </span>
          <input
            type="text"
            value={name}
            maxLength={80}
            placeholder="Music this month"
            onChange={(event) => setName(event.target.value)}
            data-new-collection-name
            className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-md)]"
          />
        </label>
        <button
          type="button"
          onClick={create}
          disabled={busy || !name.trim()}
          aria-busy={busy}
          data-create-collection
          className="min-h-[44px] rounded-control border border-border-strong px-4 py-3 text-ink-primary [font:var(--type-scale-meta-md)] disabled:cursor-default"
        >
          Create
        </button>
      </div>

      {failure ? (
        <p
          role="alert"
          className="mt-3 text-warn-amber [font:var(--type-scale-body-sm)]"
          data-collections-failed
        >
          {failure}
        </p>
      ) : null}

      {/* ── The list, or the quiet empty state ─────────────────────────────── */}
      {collections.length === 0 ? (
        // `component.emptystate.quiet`: a dashed border so it reads as intentional
        // rather than failed, which is the whole point of the pattern.
        <div
          data-collections-empty
          className="mt-8 rounded-card border border-dashed border-border-strong px-6 py-12 text-center"
        >
          <p className="text-ink-primary [font:var(--type-scale-headline-sm)]">
            No collections yet.
          </p>
          <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
            Group your saves into something like “Music this month” or “For the kids”.
          </p>
        </div>
      ) : (
        <ul className="mt-8 flex flex-col gap-3" data-collection-list>
          {collections.map((collection, index) => (
            <li
              key={collection.id}
              data-collection-row={collection.id}
              className="rounded-card border border-border-subtle px-4 py-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                {renaming?.id === collection.id ? (
                  <div className="flex flex-wrap items-end gap-2">
                    <label className="flex flex-col gap-1">
                      <span className="text-ink-secondary [font:var(--type-scale-meta-sm)]">
                        Name
                      </span>
                      <input
                        type="text"
                        value={renaming.value}
                        maxLength={80}
                        onChange={(event) =>
                          setRenaming({ id: collection.id, value: event.target.value })
                        }
                        data-rename-input
                        className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-md)]"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={rename}
                      disabled={busy}
                      data-rename-save
                      className="min-h-[44px] px-3 text-ink-primary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
                    >
                      Save name
                    </button>
                    <button
                      type="button"
                      onClick={() => setRenaming(null)}
                      className="min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => open(collection.id)}
                    aria-expanded={opened?.id === collection.id}
                    data-open-collection={collection.id}
                    className="min-h-[44px] text-left text-ink-primary [font:var(--type-scale-body-md)]"
                  >
                    {collection.name}
                    <span className="ml-3 text-ink-muted [font:var(--type-scale-meta-sm)]">
                      {collection.item_count === 1 ? "1 event" : `${collection.item_count} events`}
                    </span>
                  </button>
                )}

                <div className="flex items-center gap-1">
                  {/*
                    **Move up / move down rather than drag.** Operable from the keyboard
                    with no pointer, and the ends are `disabled` rather than silently
                    inert, so the boundary is announced rather than discovered.
                  */}
                  <button
                    type="button"
                    onClick={() => move(index, -1)}
                    disabled={busy || index === 0}
                    aria-label={`Move ${collection.name} up`}
                    data-move-up={collection.id}
                    className="min-h-[44px] min-w-[44px] text-ink-secondary disabled:text-ink-faint"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => move(index, 1)}
                    disabled={busy || index === collections.length - 1}
                    aria-label={`Move ${collection.name} down`}
                    data-move-down={collection.id}
                    className="min-h-[44px] min-w-[44px] text-ink-secondary disabled:text-ink-faint"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    onClick={() => setRenaming({ id: collection.id, value: collection.name })}
                    data-rename-collection={collection.id}
                    className="min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
                  >
                    Rename
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirming(collection.id)}
                    data-delete-collection={collection.id}
                    className="min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {/*
                **The confirmation says what survives.** "Delete" above a list of events
                reads as deleting the events; it does not, and the copy is where that is
                made true for the user rather than only in the API.
              */}
              {confirming === collection.id ? (
                <div className="mt-3 flex flex-wrap items-center gap-3" data-delete-confirm>
                  <p className="text-ink-secondary [font:var(--type-scale-body-sm)]">
                    Delete “{collection.name}”? Your saved events stay saved.
                  </p>
                  <button
                    type="button"
                    onClick={() => remove(collection.id)}
                    disabled={busy}
                    data-delete-confirm-yes
                    className="min-h-[44px] rounded-control border border-border-strong px-4 text-ink-primary [font:var(--type-scale-meta-sm)]"
                  >
                    Delete it
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirming(null)}
                    data-delete-confirm-no
                    className="min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
                  >
                    Keep it
                  </button>
                </div>
              ) : null}

              {opened?.id === collection.id ? (
                <div className="mt-4 border-t border-border-subtle pt-3" data-collection-events>
                  {opened.events.length === 0 ? (
                    // An empty collection is a container somebody made on purpose, not a
                    // failure — so it says so plainly rather than borrowing the dashed
                    // "nothing here went wrong" treatment.
                    <p className="text-ink-muted [font:var(--type-scale-body-sm)]">
                      Nothing in here yet. Add a save to it below.
                    </p>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {opened.events.map((event) => (
                        <li
                          key={event.id}
                          className="flex flex-wrap items-center justify-between gap-2"
                          data-collection-event={event.id}
                        >
                          {/*
                            **The snapshot, which is all the API sends.** The time is the
                            user's own row, kept current by AD-17 propagation, so a
                            postponement shows here with no catalog read.
                          */}
                          <span className="text-ink-secondary [font:var(--type-scale-body-sm)]">
                            {readableWhen(event.start_time_utc)}
                          </span>
                          <button
                            type="button"
                            onClick={() => unassign(collection.id, event.id)}
                            disabled={busy}
                            data-unassign={event.id}
                            className="min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
                          >
                            Take out
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}

                  {/* ── Add a save ─────────────────────────────────────────── */}
                  <AssignPicker
                    collectionId={collection.id}
                    picking={picking}
                    alreadyIn={opened.events}
                    busy={busy}
                    onStart={startPicking}
                    onAssign={assign}
                  />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * "Add a save" — the control that makes a collection fillable (FR-49).
 *
 * **The endpoint it reaches has existed, tested, since the collections intent and had no
 * caller until now.** `PUT /api/personal/collections/{id}/events/{saved_event_id}` is
 * idempotent and a save may belong to several collections at once — *"membership is a
 * table, not a column"* (`collections_api.py:235`) — so the picker opens from each
 * collection rather than asking the user to pick several at once.
 *
 * **A save already in this collection is not offered.** The endpoint would answer 204 and
 * write nothing, which is correct of it and wrong of a button: an action that visibly does
 * nothing is the failure this whole surface exists to remove.
 *
 * **The tier gate is inherited, not re-implemented.** `CollectionManager` renders only for
 * a Pro account (`app/settings/collections/page.tsx:86`), so a Free user never reaches this
 * control and no 409 is ever provoked — the same reasoning that page already applies to
 * create: *"A Free user is never refused here, because they are never given a control that
 * could be refused."* Taking a save **out** stays open on every tier, and is untouched.
 */
function AssignPicker({
  collectionId,
  picking,
  alreadyIn,
  busy,
  onStart,
  onAssign,
}: {
  collectionId: string;
  picking: { saves: AssignableSave[] | null } | null;
  alreadyIn: CollectionEvent[];
  busy: boolean;
  onStart: () => void;
  onAssign: (collectionId: string, savedEventId: string) => void;
}) {
  if (picking === null) {
    return (
      <button
        type="button"
        onClick={onStart}
        disabled={busy}
        aria-expanded={false}
        data-add-save
        className="mt-3 min-h-[44px] px-3 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-sm)]"
      >
        Add a save
      </button>
    );
  }

  // **Not read yet is not the same as none.** `saves` is null until the read lands, and
  // showing "nothing saved yet" in that gap would state a fact we do not have.
  if (picking.saves === null) {
    return (
      <p className="mt-3 text-ink-muted [font:var(--type-scale-body-sm)]" data-picker-loading>
        Reading your saves…
      </p>
    );
  }

  // **The filter is a set difference, not a lookup.** `SavedEventOut.id` and
  // `CollectionEventOut.id` are the same id — the personal save's — so what is already in
  // the collection is removed by identity.
  const inThisCollection = new Set(alreadyIn.map((event) => event.id));
  const offered = picking.saves.filter((save) => !inThisCollection.has(save.id));

  if (picking.saves.length === 0) {
    return (
      <p className="mt-3 text-ink-muted [font:var(--type-scale-body-sm)]" data-picker-empty>
        Nothing saved yet. Save an event and it can go in here.
      </p>
    );
  }

  if (offered.length === 0) {
    return (
      <p className="mt-3 text-ink-muted [font:var(--type-scale-body-sm)]" data-picker-exhausted>
        Everything you&apos;ve saved is already in here.
      </p>
    );
  }

  return (
    <div className="mt-3" data-assign-picker>
      {/*
        **The group is named, and the name is the control the user just pressed.** A bare
        list of event titles under a collection reads as the collection's contents — which
        is the list immediately above it.
      */}
      <p className="text-ink-secondary [font:var(--type-scale-meta-sm)]" id={`add-${collectionId}`}>
        Add a save
      </p>
      <ul className="mt-2 flex flex-col gap-2" aria-labelledby={`add-${collectionId}`}>
        {offered.map((save) => (
          <li key={save.id}>
            <button
              type="button"
              onClick={() => onAssign(collectionId, save.id)}
              disabled={busy}
              data-assign={save.id}
              className="min-h-[44px] w-full rounded-control border border-border-subtle px-3 py-2 text-left text-ink-primary [font:var(--type-scale-meta-sm)]"
            >
              <span className="block truncate">{save.title}</span>
              <span className="block text-ink-muted [font:var(--type-scale-body-sm)]">
                {readableWhen(save.start_time_utc)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
