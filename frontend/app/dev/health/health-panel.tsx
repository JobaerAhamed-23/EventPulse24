"use client";

import { useEffect, useState } from "react";

import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";

type Components = components["schemas"]["ComponentsOut"];
type Component = components["schemas"]["ComponentOut"];

type State =
  | { kind: "checking" }
  | { kind: "loaded"; components: Components; message: string }
  | { kind: "unreachable" };

const LABELS: Record<keyof Components, string> = {
  personal: "Personal database",
  catalog: "Catalog database",
  redis: "Redis",
};

const REASONS: Record<NonNullable<Component["reason"]>, string> = {
  unreachable: "not reachable",
  wrong_schema: "connected to the wrong schema",
};

async function checkHealth(): Promise<State> {
  try {
    const { data, error } = await api.GET("/api/health");
    if (data)
      return { kind: "loaded", components: data.components, message: "Everything is responding." };
    // 503 from Django carries per-component details; anything else means the API itself is out.
    if (error?.details?.components) {
      return { kind: "loaded", components: error.details.components, message: error.message };
    }
  } catch {
    // Network failure: fall through.
  }
  return { kind: "unreachable" };
}

export function HealthPanel() {
  const [state, setState] = useState<State>({ kind: "checking" });

  useEffect(() => {
    let active = true;
    void checkHealth().then((next) => {
      if (active) setState(next);
    });
    return () => {
      active = false;
    };
  }, []);

  const summary =
    state.kind === "checking"
      ? "Checking…"
      : state.kind === "unreachable"
        ? "The API isn't reachable. Is make dev running?"
        : state.message;

  return (
    <main className="fade-in mx-auto max-w-(--layout-container-reading) px-6 py-20">
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">Service health</h1>
      <p aria-live="polite" className="mt-2 text-ink-muted [font:var(--type-scale-meta-md)]">
        {summary}
      </p>
      {state.kind === "loaded" && (
        <ul className="mt-8 rounded-card border border-border-subtle bg-surface-elevated">
          {(Object.keys(LABELS) as (keyof Components)[]).map((name) => {
            const component = state.components[name];
            const ok = component.status === "ok";
            return (
              <li
                key={name}
                className="flex items-center gap-3 border-b border-border-subtle p-4 last:border-b-0"
              >
                <span
                  aria-hidden="true"
                  className={`h-2 w-2 rounded-full ${ok ? "bg-signal-success" : "bg-signal-warn"}`}
                />
                <span className="text-ink-primary [font:var(--type-scale-body-md)]">
                  {LABELS[name]}
                </span>
                <span className="ml-auto text-ink-secondary [font:var(--type-scale-meta-md)]">
                  {ok ? "OK" : `Down: ${component.reason ? REASONS[component.reason] : "unknown"}`}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
