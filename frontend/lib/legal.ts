/**
 * The one date both legal documents carry.
 *
 * **A policy's date is a factual claim**, not a decoration: it tells a reader how current
 * what they are reading is, and in several of the regimes PRD §10.5 lists it is the thing
 * a regulator asks for first. Two hand-typed dates drift, and the stale one then says
 * something untrue.
 *
 * **Update it when the text changes, not when the file is touched.** A date that moves on
 * every deploy tells the reader nothing.
 */
export const LEGAL_LAST_UPDATED = "20 November 2026";
