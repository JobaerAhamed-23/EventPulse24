"use client";

/**
 * The Pulse Preview's client state, and the two places it surfaces: the consent banner at
 * the top of the page, and the cards below the hero.
 *
 * It is **one** island with two slots rather than two islands, because both need the same
 * answer: the banner names the city the request resolved to, and the cards are that
 * request's result. The slots sit far apart in the page — the mockup puts the banner
 * above the topbar — so the state is shared through a context that only this file
 * defines, and `page.tsx` composes the page around it. The topbar, hero and footer stay
 * server components, passed through as children.
 *
 * **The read happens in the browser, and that is the design** (AD-12, FR-2):
 *
 *   - the page itself stays static and identical for every visitor, signed in or not —
 *     nothing here reads a session, and the only cookie is the visitor's own location
 *     choice, written and read on this side;
 *   - the edge's location header travels on the **visitor's** request, which `proxy.ts`
 *     forwards to Django. A read from the Next.js server would carry the server's own
 *     headers, and the city would be wrong for everyone;
 *   - there is a loading state to show, which is what `EXPERIENCE.md` asks for. A
 *     server-rendered page has nothing to put there.
 */

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { type PreviewChoice, previewQuery, readChoice, rememberChoice } from "@/lib/preview-choice";

import { CardSkeletons } from "./card-skeleton";
import { GeoBanner } from "./geo-banner";
import { PreviewCard } from "./preview-card";

type Preview = components["schemas"]["PreviewOut"];

/** FR-2: "soft-walls at the 3rd card". The third save is the one that asks. */
const SAVES_BEFORE_SIGNUP = 2;

/**
 * What a save says once it has happened.
 *
 * **Pre-signup saves are not carried into the account.** There is no anonymous save
 * endpoint — `POST /api/personal/saved-events` needs a session — and nothing in this
 * intent replays them after sign-up. Saying so is better than a "Saved!" that quietly
 * means nothing the moment the tab closes.
 */
const SAVED_NOTE = "Saved for this visit. Sign up to keep it.";

type State = { kind: "loading" } | { kind: "ready"; preview: Preview } | { kind: "failed" };

/**
 * Read the preview for a choice. **No state, no React** — it answers with what to show.
 *
 * Keeping the request separate from the setting is what lets the mount effect apply its
 * result only after awaiting it, and it makes the three outcomes one expression: a 429
 * and an unreachable API say the same calm thing, because there is nothing a visitor can
 * do with the distinction.
 */
async function readPreview(choice: PreviewChoice): Promise<State> {
  try {
    const response = await api.GET("/api/public/preview", {
      params: { query: previewQuery(choice) },
    });
    return response.data ? { kind: "ready", preview: response.data } : { kind: "failed" };
  } catch {
    return { kind: "failed" };
  }
}

type PreviewContext = {
  state: State;
  banner: {
    city: string;
    cities: string[];
    loadingCities: boolean;
    onUseThis: () => void;
    onChange: () => void;
    onPickCity: (city: string) => void;
    onOptOut: () => void;
  } | null;
  saved: string[];
  save: (id: string) => void;
};

const Context = createContext<PreviewContext | null>(null);

function usePreview(): PreviewContext {
  const value = useContext(Context);
  if (value === null) {
    throw new Error("A preview slot was rendered outside PreviewProvider.");
  }
  return value;
}

export function PreviewProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "loading" });
  // Read once, lazily. The cookie is an external value, so it is read where React reads
  // initial state rather than set from an effect — an effect that calls `setState`
  // synchronously is a second render for something that was known before the first.
  //
  // On the server `document` does not exist and this is "unasked", which is also what the
  // first client render shows: the banner only appears once the preview has loaded, so
  // the two renders agree on the markup and hydration is clean.
  const [choice, setChoice] = useState<PreviewChoice>(readChoice);
  const [dismissed, setDismissed] = useState(false);
  const [cities, setCities] = useState<string[]>([]);
  const [loadingCities, setLoadingCities] = useState(false);
  const [saved, setSaved] = useState<string[]>([]);

  const load = useCallback(async (next: PreviewChoice): Promise<void> => {
    setState({ kind: "loading" });
    setState(await readPreview(next));
  }, []);

  useEffect(() => {
    // The read is started here and its result is applied **after** the await, so nothing
    // is set synchronously inside the effect. The flag is the unmount guard: a visitor
    // who leaves while the request is in flight must not have state written behind them.
    let live = true;
    void (async () => {
      // `readChoice()` rather than the state: the state was initialised before hydration,
      // and this is the moment the real cookie is certainly readable.
      const next = await readPreview(readChoice());
      if (live) setState(next);
    })();
    return () => {
      live = false;
    };
  }, []);

  const keepCity = (city: string): void => {
    const next: PreviewChoice = { kind: "city", city };
    rememberChoice(next);
    setChoice(next);
    setDismissed(true);
  };

  const optOut = (): void => {
    const next: PreviewChoice = { kind: "opted-out" };
    rememberChoice(next);
    setChoice(next);
    setDismissed(true);
    // Not merely remembered: the preview is re-read with the location switched off, so
    // the fallback city is what the visitor actually ends up looking at.
    void load(next);
  };

  const pickCity = (city: string): void => {
    keepCity(city);
    void load({ kind: "city", city });
  };

  const openPicker = async (): Promise<void> => {
    setLoadingCities(true);
    try {
      const response = await api.GET("/api/public/preview/cities");
      setCities(response.data?.cities ?? []);
    } catch {
      setCities([]);
    }
    setLoadingCities(false);
  };

  /**
   * The soft wall: the first two saves are remembered on this page, and the third asks
   * for an account. It counts **saves**, not cards — three taps across three cards is the
   * case FR-2 describes.
   */
  const save = (id: string): void => {
    if (saved.includes(id)) return;
    if (saved.length >= SAVES_BEFORE_SIGNUP) {
      router.push("/signup");
      return;
    }
    setSaved([...saved, id]);
  };

  const preview = state.kind === "ready" ? state.preview : null;
  const showBanner = preview !== null && choice.kind === "unasked" && !dismissed;

  return (
    <Context.Provider
      value={{
        state,
        banner: showBanner
          ? {
              city: preview.city,
              cities,
              loadingCities,
              onUseThis: () => keepCity(preview.city),
              onChange: () => void openPicker(),
              onPickCity: pickCity,
              onOptOut: optOut,
            }
          : null,
        saved,
        save,
      }}
    >
      {children}
    </Context.Provider>
  );
}

/** The consent banner's slot — the top of the page, above the topbar, as drawn. */
export function PreviewBannerSlot() {
  const { banner } = usePreview();
  if (banner === null) return null;
  return <GeoBanner {...banner} />;
}

/** The cards' slot — below the hero. */
export function PreviewCardsSlot() {
  const { state, saved, save } = usePreview();
  const preview = state.kind === "ready" ? state.preview : null;

  return (
    <section id="today" aria-label="Pulse Preview" className="mt-16">
      <h2 className="[font:var(--type-scale-headline-lg)] text-ink-primary">
        {preview ? `Next 3 days in ${preview.city}` : "Next 3 days near you"}
      </h2>
      <p className="mt-2 max-w-(--layout-container-reading) [font:var(--type-scale-body-sm)] text-ink-muted">
        Event Fit shows how soon an event is and how complete our details are. It is the same for
        everyone — your own Pulse is personal, and that starts when you sign up.
      </p>

      <div className="mt-6">
        {state.kind === "loading" ? <CardSkeletons /> : null}

        {state.kind === "failed" ? (
          <p role="alert" className="[font:var(--type-scale-body-md)] text-ink-secondary">
            Couldn&apos;t load the preview. Refresh.
          </p>
        ) : null}

        {preview && preview.items.length === 0 ? (
          <p className="[font:var(--type-scale-body-md)] text-ink-secondary">
            No preview available in {preview.city} yet.
          </p>
        ) : null}

        {preview && preview.items.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {preview.items.map((card) => (
              <PreviewCard
                key={card.id}
                card={card}
                onSave={() => save(card.id)}
                savedNote={saved.includes(card.id) ? SAVED_NOTE : null}
              />
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
