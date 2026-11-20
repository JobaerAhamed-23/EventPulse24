"use client";

/**
 * The account's picture — **chosen, uploaded, and removed.**
 *
 * ## Why this control is not save-on-change
 *
 * **Every other settings island saves on change, because the control the user pressed
 * *is* the change.** The quiet window, the digest's delivery time, the default reminder
 * plan — the control is the whole of the thing being saved.
 *
 * **A file picker is different, and the difference is the undo.** The picker has a
 * moment — the file is chosen — and that moment is the save. **But there is no undo on a
 * file picker**: a replaced picture is gone, and the old one was removed from the store
 * when the new one committed. So the screen says what will happen *before* it happens
 * rather than after, which is why the copy here is written the way it is.
 *
 * **The removal is a separate, explicit control** — and the same is true of it. Removing
 * a picture is a thing a person does deliberately, so it gets its own button rather than
 * riding on the picker's on-change.
 *
 * ## The failure line is the API's, when the API refused
 *
 * **The same rule the rest of the frontend follows**, and the same reader: the
 * project's error shape is `{code, message, details}`, and the message is written for
 * the person who typed it — so it is shown as it arrived. **The generic offline line is
 * shown only when the request never reached the API**, because then the API said
 * nothing to quote.
 *
 * **The API's refusals are specific and worth keeping.** *"That file isn't an image we
 * can read. Try a PNG, JPEG, WebP or GIF."* says what to do; a generic "Couldn't save."
 * would throw that away.
 *
 * ## Nothing is published before the server accepts
 *
 * **The shell is rendered on the server**, so the picture it was drawn with is fixed for
 * the life of the render — and a save that does not show up is a save that did not
 * happen. So the island publishes the new URL to the shell **after** the server has
 * accepted the write, and **never before**: the server validates the bytes, re-encodes
 * them and may refuse the file outright, so a URL published early would name a picture
 * that does not exist.
 *
 * ## Two uploads racing would leave two objects
 *
 * **The hazard is worse here than it is for the name.** A name is typed a character at a
 * time, and a late response overwrites a newer value — bad, but recoverable. **Two
 * uploads racing leave two objects in the bucket**, one of them orphaned, and the
 * account's row points at whichever committed last.
 *
 * **So the control is not pressable twice into two uploads**, and a late response for a
 * superseded upload is dropped whole — the same counter pattern `profile-name.tsx` uses,
 * for the same reason.
 */
import { useCallback, useRef, useState } from "react";

import { SaveFeedback } from "@/components/settings/save-feedback";
import { AvatarDisc } from "@/components/shell/avatar-disc";
import { publishAvatar } from "@/lib/avatar-store";
import { type AvatarResult, removeAvatar, uploadAvatar } from "@/lib/avatar-upload";

export type AvatarUploadProps = {
  /**
   * The picture the account holds now — `""` when it holds none.
   *
   * **It is the seed, not the truth.** The island shows what the account holds when it
   * was rendered; a picture chosen since then is published to the shell, and this
   * island's own preview follows the write.
   */
  initialAvatarUrl: string;
  /** The display name — the source of the initials when there is no picture. */
  name: string;
};

/**
 * The failure line for a request that **never reached the API**.
 *
 * **It is shown only in that case.** When the API refused, its own message is shown
 * instead — the API writes its messages for the person who typed them, and replacing
 * one with a generic sentence throws away the only line that says what to change.
 */
const FAILURE = "Couldn't save.";

/**
 * The formats the server accepts, as the browser's `accept` attribute.
 *
 * **The server's allow-list, not a guess.** `shared/constants.py` allows PNG, JPEG,
 * WebP and GIF, and it identifies the format *from the bytes* — so this attribute is a
 * convenience for the person choosing a file, not the enforcement. The enforcement is
 * the server's, and its refusal message names the formats.
 */
const ACCEPT = "image/png,image/jpeg,image/webp,image/gif";

export function AvatarUpload({ initialAvatarUrl, name }: AvatarUploadProps) {
  /** The picture the island is showing. */
  const [avatarUrl, setAvatarUrl] = useState(initialAvatarUrl);
  /** Whether a request is in flight. */
  const [busy, setBusy] = useState(false);
  /** The failure line to show, or `null`. */
  const [failure, setFailure] = useState<string | null>(null);
  /** Whether the last write succeeded. */
  const [saved, setSaved] = useState(false);
  /**
   * How many writes have been started.
   *
   * **This is the defence in depth behind the `inFlight` guard.** The guard means only
   * one write is ever in flight from the UI, so the counter's counterparty — a second
   * write started while the first was running — cannot happen through the screen. **But
   * the counter costs nothing and the hazard is real**: a write that is started in the
   * narrow window where the previous write's `inFlight` has been cleared but its state
   * update has not been committed yet would otherwise let a late response overwrite the
   * newer picture.
   *
   * **The counter is a ref, not state**: it must not trigger a render of its own.
   */
  const writes = useRef(0);
  /**
   * Whether a write is in flight.
   *
   * **It is a ref and not the `busy` state, because the guard has to be readable
   * *inside* the event handler** — and by the time a handler runs, a `setState` from the
   * previous write may not have been committed yet. A ref is the same value in the same
   * tick, which is what a "is one already running?" question needs.
   */
  const inFlight = useRef(false);

  /**
   * The write, for both directions.
   *
   * **Upload and removal are one shape** — one request, one answer, one publish — so
   * they share the bookkeeping rather than each keeping their own.
   */
  const write = useCallback(async (action: () => Promise<AvatarResult>) => {
    writes.current += 1;
    const mine = writes.current;

    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setSaved(false);
    try {
      const result = await action();
      // **A response for a write the person has already superseded says nothing about
      // the picture on screen.** It is dropped whole: no failure line, no "Saved.", no
      // write to the preview.
      if (mine !== writes.current) return;
      if (result.kind === "refused") {
        setFailure(result.message);
        return;
      }
      // **The server's answer replaces the server's answer.** The URL the server hands
      // back is the one for the object it actually stored — and a replaced picture is a
      // different URL, so the browser's cache invalidates itself.
      setAvatarUrl(result.avatarUrl);
      /*
        **The rail follows the write.** The shell was rendered on the server with the
        picture the account held *before* this write, so the rail would keep showing the
        old one — and the rail is on every page. **A save that does not show up is a save
        that did not happen**, so the new URL is published to the shell.

        **This happens only after the server accepted the write.** Publishing earlier
        would publish a guess: the server validates the bytes, re-encodes them and may
        refuse the file outright.
      */
      publishAvatar(result.avatarUrl);
      setSaved(true);
    } catch {
      // **The request never reached the API**, so there is nothing to quote.
      if (mine !== writes.current) return;
      setFailure(FAILURE);
    } finally {
      // **Only the newest write owns the in-flight state.** An older one going quiet
      // must not clear the dot of a write that is still running.
      if (mine === writes.current) {
        inFlight.current = false;
        setBusy(false);
      }
    }
  }, []);

  /**
   * A file was chosen.
   *
   * **The chosen file is the save.** There is no Save button, and no second step —
   * the moment the file is chosen is the moment it is sent.
   *
   * **A file that was chosen again is a new write**, and the counter above decides
   * which answer wins.
   *
   * **And a file chosen while a write is in flight is refused.** The input is
   * `disabled` while the write runs, which is the *affordance* — but a disabled
   * attribute is a hint to the browser, not a guarantee, and **two uploads racing leave
   * two objects in the bucket, one of them orphaned.** So the guard is here as well:
   * the enforcement does not depend on the browser honouring the attribute.
   *
   * **The refusal is silent on purpose.** The person who chose a second file while the
   * first was uploading is already told by the control being disabled, and the wait is
   * already announced — a line of text naming the refusal would be noise.
   */
  const choose = useCallback(
    (file: File | undefined) => {
      if (file === undefined) return;
      if (inFlight.current) return;
      void write(() => uploadAvatar(file));
    },
    [write],
  );

  /**
   * The picture is removed.
   *
   * **It is its own control** — removing a picture is a deliberate act, and it has no
   * undo on the server either: the object behind it is removed with the row.
   *
   * **And it refuses while a write is in flight**, for the same reason the upload does:
   * a removal racing an upload would leave the account in whichever state committed
   * last, and the object behind the other one would be orphaned.
   */
  const remove = useCallback(() => {
    if (inFlight.current) return;
    void write(removeAvatar);
  }, [write]);

  const hasPicture = avatarUrl !== "";

  return (
    /*
      **The section is labelled "Profile picture", and the heading is the name of the
      thing.** The screen's own heading is "Profile"; a section inside it that also
      called itself "Profile" would be two elements answering the same question.
    */
    <section aria-label="Profile picture" data-avatar-upload>
      {/*
        **The disc and the controls, side by side.** The disc is the same component the
        shell draws — **the same component**, not a copy — so the preview on this screen
        and the face in the rail cannot drift apart.
      */}
      <div className="flex items-center gap-4">
        {/*
          **The preview is the shell's own disc** — **the same component**, not a copy —
          so the picture on this screen and the face in the rail cannot drift apart. It
          is drawn larger, which is the `lg` size the sheet uses.
        */}
        <span data-avatar-preview>
          <AvatarDisc avatarUrl={avatarUrl} name={name} size="lg" />
        </span>

        <div className="flex flex-col gap-2">
          {/*
            **The file input, hidden but not gone.**

            **A `display: none` input cannot be reached**, and dropping it out of the
            accessibility tree would mean the control the person actually presses is
            invisible to a screen reader. So it is `sr-only` — out of sight, still
            operable, still focusable — and the visible button is a `<label>` for it.

            **`disabled` while a write is in flight**, which is what stops a second
            upload being started into a second object. And `aria-busy` on the region,
            so the wait is announced.
          */}
          <label
            className={[
              "inline-flex min-h-[44px] cursor-pointer items-center justify-center rounded-control border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-md)]",
              busy ? "pointer-events-none opacity-60" : "",
            ].join(" ")}
          >
            {hasPicture ? "Choose another picture" : "Choose a picture"}
            <input
              type="file"
              accept={ACCEPT}
              disabled={busy}
              /*
                **`aria-busy` is on the control, not on the region below it.**

                **The wait belongs to the thing being waited on.** Every other settings
                island puts `aria-busy` on the control itself — the name's input, the
                email's button — and a screen reader announces a busy *control* as busy.
                A `aria-busy` on a wrapper that holds only the feedback line would say
                "this region is busy" about a region that has nothing in flight to wait
                for.
              */
              aria-busy={busy}
              onChange={(event) => {
                choose(event.target.files?.[0]);
                // **The input is cleared, so choosing the same file twice fires twice.**
                // Without this, picking the same picture again would change nothing —
                // the input's value had not changed — and the on-change would not fire.
                event.target.value = "";
              }}
              data-avatar-input
              className="sr-only"
            />
          </label>

          {/*
            **The removal control exists only when there is a picture to remove.** A
            "Remove picture" button on an account with no picture is an affordance that
            cannot work — the same lie as a link to a 404.
          */}
          {hasPicture ? (
            <button
              type="button"
              onClick={remove}
              disabled={busy}
              data-avatar-remove
              className="inline-flex min-h-[44px] items-center justify-center self-start rounded-control px-3 py-2 text-ink-secondary underline underline-offset-4 [font:var(--type-scale-body-sm)] disabled:opacity-60"
            >
              Remove picture
            </button>
          ) : null}
        </div>
      </div>

      {/*
        **The line that says the picture replaces the old one.** There is no undo on a
        file picker — the old object is removed when the new one commits — so the
        screen says so *before* the choice rather than after it.
      */}
      <p className="mt-3 text-ink-secondary [font:var(--type-scale-meta-sm)]">
        {hasPicture
          ? "Choosing another picture replaces the one you have now."
          : "A picture shows in the rail and on your account sheet. PNG, JPEG, WebP or GIF."}
      </p>

      {/*
        **The region is busy too, and it is not redundant.** The input's `aria-busy`
        says the *control* is waiting; the region's says the *section* is. A screen
        reader user who has just activated the picker and moved on hears the section
        still working — which is the thing they cannot see.
      */}
      <div className="mt-4" aria-busy={busy} data-avatar-region>
        <SaveFeedback busy={busy} saved={saved} failure={failure} />
      </div>
    </section>
  );
}
