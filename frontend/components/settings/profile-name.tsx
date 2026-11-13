"use client";

/**
 * The account's display name — **editable in place, and saved on change.**
 *
 * **This is the one thing about an account a person can change.** The email is the login
 * and the key; the password is changed by the reset flow, which ends the account's other
 * sessions. So this control is the whole of the profile surface, and it is a single
 * field rather than a form with a Save button.
 *
 * **There is no Save button.** The other settings islands save on change — the quiet
 * window, the digest's delivery time, the default reminder plan — and a Save button here
 * would be the one control on the screen that behaves differently from its neighbours.
 * The control the user pressed is the thing that saves.
 *
 * **An emptied name is saved, and that is not a mistake.** Every other island refuses to
 * send a half-finished value: a time with nothing in it is not a schedule, and a window
 * with one end missing is not a window. **A name with nothing in it is a name.** It means
 * *"no name set"*, the backend stores `""`, and the product falls back to the
 * email-derived name. So unlike the time control, this one does not hold a value back.
 *
 * **The failure line is the API's, when the API refused.** A name carrying a line break
 * is refused by the backend with a message written for the person who typed it, and that
 * message says what to change. A generic *"Couldn't save."* would throw it away and leave
 * the user with a screen that did nothing and no idea why — which is why the failure is
 * stored as a **message string** and not a boolean. The offline line is shown only when
 * the request never reached the API, because then the API said nothing to quote.
 *
 * **The island does not own the session.** It takes the name as a prop from the server
 * page, which already has the session; it never calls `me` itself. A second read would
 * be a second answer to a question already answered.
 *
 * **The island shows the stored name; the shell shows the display name.** Those are two
 * different questions. The field shows what the account holds — `""` when no name is set,
 * which is what "no name set" looks like. The rail shows what to call the person, and
 * that is the stored name when there is one and the address-derived name when there is
 * not. **So the island is handed the stored name and the address, and it derives the
 * display name with the *same* shared helper the pages use** — one rule, one
 * implementation, and no second copy to keep in sync.
 *
 * **And the island publishes the display name to the shell after a save.** The shell is
 * rendered on the server, so the name it was drawn with is fixed for the life of the
 * render — and a person who saves a name and sees the rail unchanged has been told the
 * save did not happen. **A save that does not show up is a save that did not happen.**
 */
import { useCallback, useRef, useState } from "react";

import { SaveFeedback } from "@/components/settings/save-feedback";
import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";
import { displayName } from "@/lib/display-name";
import { publishName } from "@/lib/session-name";

export type ProfileNameProps = {
  /** The stored name — `""` when no name is set. */
  initialName: string;
  /**
   * The account's address.
   *
   * **It is here so the island can publish the *display* name, and not the stored one.**
   * The rail shows what to call the person, and the display rule has two branches: the
   * stored name when there is one, the address-derived name when there is not. **An
   * island that only knows the stored name cannot answer the second branch** — when
   * the name is cleared, the name the rail must show is the fallback, and only the
   * address can produce it. So the island holds the address and applies the *same*
   * shared helper the pages apply — one rule, one implementation.
   */
  email: string;
};

/**
 * The failure line, **verbatim** — and it is the **offline** line.
 *
 * The same short line the quiet-hours and delivery-time routes use, because the same
 * thing happened: the save did not take. **The API's own refusal is shown instead of
 * this one, when the API made one.**
 */
const FAILURE = "Couldn't save.";

/**
 * The column's own limit — the backend's cap.
 *
 * **It is a courtesy, not a rule.** The server truncates to this length anyway; the
 * attribute just means the browser stops the paste before the round trip, so the field
 * cannot hold a name the server is going to cut in half anyway.
 */
const NAME_MAX_LENGTH = 120;

export function ProfileName({ initialName, email }: ProfileNameProps) {
  /** The name, as the user has it. */
  const [value, setValue] = useState(initialName);
  /** Whether a save is in flight. */
  const [busy, setBusy] = useState(false);
  /**
   * The failure line to show, or `null`.
   *
   * **The message, not a flag** — so the API's own refusal can be shown verbatim.
   */
  const [failure, setFailure] = useState<string | null>(null);
  /** Whether the last save succeeded. */
  const [saved, setSaved] = useState(false);
  /**
   * How many saves have been started.
   *
   * **This is what makes a late response harmless.** A free-text field is typed a
   * character at a time, so a person can start a second save before the first comes
   * back. **Whichever response arrives last is not necessarily the newest request** —
   * and a slow first response would otherwise overwrite the name the user has since
   * typed, and then replace it with the server's answer to the *older* name.
   *
   * **So each save takes a number, and only the newest one may write to the field.**
   * The counter is a ref, not state: it must not trigger a render of its own.
   */
  const saves = useRef(0);

  /**
   * Saving the name.
   *
   * **The payload is the name and nothing else.** The endpoint takes one field, and
   * sending more would be sending more than the server has agreed to store.
   */
  const save = useCallback(async (name: string) => {
    saves.current += 1;
    const mine = saves.current;

    setBusy(true);
    setFailure(null);
    setSaved(false);
    try {
      const response = await api.PUT("/api/auth/profile", { body: { name } });
      // **A response for a save the user has already superseded says nothing about the
      // name on screen.** It is dropped whole: no failure line, no "Saved.", no write
      // to the field.
      if (mine !== saves.current) return;
      if (response.error) {
        // **The API refused it, and it said why.**
        setFailure(saveFailureMessage(response.error, FAILURE));
        return;
      }
      if (!response.data) {
        setFailure(FAILURE);
        return;
      }
      // **The server's answer replaces the server's answer.** The server trims and
      // collapses the name, so the stored value is not always the one that was typed —
      // and the field shows what the account now holds.
      setValue(response.data.name);
      /*
        **The rail follows the save.** The shell was rendered on the server with the name
        the account held *before* this save, so the rail would keep showing the old one
        — and the rail is on every page, and the account sheet is opened from it. **A
        save that does not show up is a save that did not happen**, so the new name is
        published to the shell.

        **What is published is the *display* name, not the stored one.** The rail shows
        what to call the person, and when the name has been cleared that is the
        address-derived fallback — which is why the island holds the address and
        applies the same shared helper the pages apply. **Publishing the stored name
        instead would blank the rail** for anyone who clears their name.

        **This happens only after the server accepted the write.** Publishing earlier
        would publish a guess: the server trims, collapses and caps, so the account's
        name is not always the one that was typed.
      */
      publishName(displayName({ name: response.data.name, email }));
      setSaved(true);
    } catch {
      // **The request never reached the API**, so there is nothing to quote.
      if (mine !== saves.current) return;
      setFailure(FAILURE);
    } finally {
      // **Only the newest save owns the in-flight state.** An older one going quiet
      // must not clear the dot of a save that is still running.
      if (mine === saves.current) setBusy(false);
    }
  }, [email]);

  /**
   * The name changing.
   *
   * **Every value is saved, including an empty one.** A name with nothing in it means
   * *"no name set"* — that is a thing a person does, and the server stores it as `""`.
   */
  const change = useCallback(
    (name: string) => {
      setSaved(false);
      setFailure(null);
      setValue(name);
      void save(name);
    },
    [save],
  );

  return (
    /*
      **The section is labelled "Profile", not "Your name".** The field's own label is
      "Your name", and a section that carried the same name would be two elements
      answering the same question — which is also why the label is not the same string
      twice in the accessibility tree.
    */
    <section aria-label="Profile" data-profile-name>
      <label className="flex flex-col gap-1">
        <span className="text-ink-secondary [font:var(--type-scale-meta-sm)]">Your name</span>
        <input
          type="text"
          value={value}
          maxLength={NAME_MAX_LENGTH}
          placeholder="Maya Ahmed"
          onChange={(event) => change(event.target.value)}
          data-profile-name-input
          aria-busy={busy}
          /*
            **The field is marked invalid when the save was refused.**
            The failure line already says what went wrong, but the field itself has to
            say it too — a person tabbing back to it has no reason to know it holds a
            value the server will not take. **Only a refusal marks it invalid**: an
            offline failure is not the field's fault, and an invalid empty field with no
            error on it would be a form demanding something.

            **There is no `aria-describedby` pointing at the failure line.** The line is
            rendered by `SaveFeedback`, which is shared by four islands and renders no id
            of its own — so a reference to an id that does not exist would be a
            description of nothing. The `role="alert"` on the line already announces
            it.
          */
          aria-invalid={failure !== null || undefined}
          className="min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-3 py-2 text-ink-primary [font:var(--type-scale-body-md)]"
        />
      </label>

      <div className="mt-4">
        <SaveFeedback busy={busy} saved={saved} failure={failure} />
      </div>
    </section>
  );
}
