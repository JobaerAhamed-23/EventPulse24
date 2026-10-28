import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { HealthPanel } from "./health-panel";

export const metadata: Metadata = { title: "Service health · EventPulse24" };

// A developer page: it doesn't exist in production builds.
export default function DevHealthPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <HealthPanel />;
}
