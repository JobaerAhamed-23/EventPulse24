/**
 * The report flag's **page-level probes** — the presence and the absence.
 *
 * **These are the claims that live in `tests/event-detail-a11y.test.tsx`**, because that
 * is the file that renders the **real** action row. (`app/events/[id]/page.test.tsx`
 * stubs `DetailActions` out — it tests the page's contribution to the row — so it
 * cannot see the flag at all.)
 *
 * **The claim being probed.** The flag is there for a signed-in reader and absent for an
 * anonymous one — **the same rule Save follows**, because the whole row is behind one
 * `personal` gate (`app/events/[id]/page.tsx:477`). The flag is not implemented for
 * anonymous readers and routed to sign-in; it is simply not there, inherited from Save's
 * own gate.
 *
 * **The failure this file guards against is a false green in the other direction.** A
 * page that rendered the flag for *everyone* would satisfy "the flag is there for a
 * signed-in reader" and fail nothing — so the anonymous case is the load-bearing half,
 * and it gets its own probe.
 *
 * **Every pattern is checked before any edit is applied**, and a missing pattern is a
 * **BROKEN** probe, which counts as a failure. (This is the bug work item 9's e2e probe
 * had: it hard-coded a literal that no longer existed, so its edit found nothing and the
 * suite stayed green while proving nothing.)
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");

const FILES = {
  page: path.join(ROOT, "app/events/[id]/page.tsx"),
  actions: path.join(ROOT, "components/detail/detail-actions.tsx"),
};

const SUITE = "tests/event-detail-a11y.test.tsx";

const PROBES = [
  {
    description: "the action row renders for an anonymous reader too",
    file: "page",
    edits: [
      // **The whole row is behind one `personal` gate.** Lifting it is the defect:
      // the flag (and Save, and Share) would then show to someone with no account,
      // and every one of them would fail to persist.
      ["      {personal ? (\n        <>\n", "      {true ? (\n        <>\n"],
    ],
    suite: SUITE,
  },
  {
    description: "the report flag is removed from the action row",
    file: "actions",
    edits: [["        <EventReportControl eventId={eventId} eventName={eventName} />\n", ""]],
    suite: SUITE,
  },
];

const originals = {};
for (const [key, file] of Object.entries(FILES)) {
  originals[key] = readFileSync(file, "utf8");
}

let failures = 0;
let broken = 0;

for (const probe of PROBES) {
  const file = FILES[probe.file];
  const original = originals[probe.file];

  let missing = null;
  for (const [pattern] of probe.edits) {
    if (!original.includes(pattern)) {
      missing = pattern;
      break;
    }
  }
  if (missing !== null) {
    console.log(`BROKEN  ${probe.description} — pattern not found: ${missing.slice(0, 80)}`);
    broken += 1;
    failures += 1;
    continue;
  }

  let mutated = original;
  for (const [pattern, replacement] of probe.edits) {
    mutated = mutated.replace(pattern, replacement);
  }
  writeFileSync(file, mutated);

  let caught = false;
  let output = "";
  try {
    execFileSync("npx", ["vitest", "run", probe.suite], {
      cwd: ROOT,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    caught = true;
    output = `${error.stdout ?? ""}${error.stderr ?? ""}`;
  } finally {
    writeFileSync(file, original);
  }

  const names = [...output.matchAll(/FAIL[^\n]*> ([^\n]+)/g)].map((m) => m[1].trim());
  console.log(
    `${caught ? "CAUGHT" : "MISSED"}  ${probe.description}` +
      (caught ? `\n          ${names.slice(0, 3).join("\n          ")}` : ""),
  );
  if (!caught) failures += 1;
}

console.log(`\n${PROBES.length - failures}/${PROBES.length} probes caught`);
if (broken > 0) console.log(`${broken} probe(s) were BROKEN — the probe itself is wrong`);
process.exit(failures === 0 ? 0 : 1);
