/**
 * The report control's **mutation probes** — every assertion proved able to fail.
 *
 * **Why this file exists.** A test whose assertions cannot fail is a *false green*: it
 * passes against code that does the wrong thing, and it is worse than no test at all,
 * because it is a claim. The house rule in this run is that every proof is verified by
 * **mutation** — never by inspection, and never by assertion.
 *
 * **The failure mode this probe file guards against is itself a false green.** A probe
 * that edits a string the file does not contain finds nothing to replace, the suite
 * stays green, and the probe reports "MISSED" — which looks like a caught defect but is
 * actually a broken probe. So **every probe checks its pattern exists before it
 * applies the edit**, and a missing pattern is reported as a **BROKEN** probe, which
 * counts as a failure. (This is the exact bug found in work item 9's e2e probe: it
 * hard-coded a weight literal that no longer existed, so its edit found nothing and the
 * suite stayed green while proving nothing.)
 *
 * **Each probe restores the file it touched**, in a `finally`, so a failure cannot leave
 * the tree broken.
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");

const FILES = {
  control: path.join(ROOT, "components/detail/event-report-control.tsx"),
};

const SUITE = "components/detail/event-report-control.test.tsx";

/**
 * The probes.
 *
 * **`suite` is the file each probe must turn red.** The page-level and axe-level
 * claims live in other files, and they get their own probes below.
 */
const PROBES = [
  {
    description: "the flag loses its accessible name",
    file: "control",
    edits: [['aria-label="Report this event"', 'aria-label="Report it"']],
    suite: SUITE,
  },
  {
    description: "the flag is styled as a primary button",
    file: "control",
    edits: [
      [
        'className="min-h-[44px] text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-md)]"',
        'className="min-h-[44px] bg-accent-terracotta text-ink-secondary underline underline-offset-4 [font:var(--type-scale-meta-md)]"',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the modal is not dismissible — Escape no longer closes it",
    file: "control",
    edits: [
      [
        '<Sheet open={open} onClose={closeModal} label="Report this event">',
        '<Sheet open={open} dismissible={false} onClose={closeModal} label="Report this event">',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "a fifth category is offered",
    file: "control",
    edits: [
      [
        '  {\n    value: "duplicate",',
        '  {\n    value: "duplicate",\n    label: "Nothing else",\n    description: "x",\n    glyph: "x",\n  },\n  {\n    value: "duplicate",',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "a free-text field is added to the modal",
    file: "control",
    edits: [
      [
        '          <div role="radiogroup" aria-label="Report category"',
        '          <textarea aria-label="Tell us more" />\n          <div role="radiogroup" aria-label="Report category"',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the Submit is enabled before a category is chosen",
    file: "control",
    edits: [["disabled={!selected || busy}", "disabled={busy}"]],
    suite: SUITE,
  },
  {
    description: "choosing an option also submits it",
    file: "control",
    edits: [
      // **The defect is a post that carries the newly chosen category.** Calling
      // `submit()` from the click handler would *not* be the defect — `submit` reads
      // `selected` from its closure, which is still `null` at that moment, so it would
      // return early and post nothing. The mutation has to be the post itself.
      [
        "onClick={() => setSelected(category.value)}",
        'onClick={() => { setSelected(category.value); void api.POST("/api/personal/event-reports", { body: { event_id: eventId, category: category.value } }); }}',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the request body carries a hand-written shape",
    file: "control",
    edits: [
      [
        "const body: ReportBody = { event_id: eventId, category: selected };",
        "const body: ReportBody = { event_id: eventId, category: selected, note: 'x' } as ReportBody;",
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the request goes around the generated client",
    file: "control",
    edits: [
      [
        'const response = await api.POST("/api/personal/event-reports", { body });',
        'const response = await fetch("/api/personal/event-reports", { method: "POST", body: JSON.stringify(body) });',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the success toast says something else",
    file: "control",
    edits: [
      [
        'const REPORTED_MESSAGE = "Thanks — we\'ll review this.";',
        'const REPORTED_MESSAGE = "Thanks for reporting.";',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the modal does not close on success",
    file: "control",
    edits: [
      [
        '      setOpen(false);\n      setSelected(null);\n      setMessage("reported");',
        '      setSelected(null);\n      setMessage("reported");',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the focus does not return to the flag",
    file: "control",
    edits: [
      [
        "    if (wasOpen.current && !open) {\n      flagRef.current?.focus();\n    }",
        "    if (false && wasOpen.current && !open) {\n      flagRef.current?.focus();\n    }",
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the event is visibly marked as reported",
    file: "control",
    edits: [
      [
        '      setOpen(false);\n      setSelected(null);\n      setMessage("reported");',
        '      setOpen(false);\n      setSelected(null);\n      setMessage("reported");\n      setReportedBadge(true);',
      ],
      [
        "  const [refusal, setRefusal] = useState<string | null>(null);",
        "  const [refusal, setRefusal] = useState<string | null>(null);\n  const [reportedBadge, setReportedBadge] = useState(false);",
      ],
      [
        "          Report this event\n        </button>",
        '          {reportedBadge ? "Reported" : "Report this event"}\n        </button>',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the toast becomes a second status region",
    file: "control",
    edits: [
      [
        '<p aria-live="polite" className="text-ink-muted [font:var(--type-scale-meta-sm)]">',
        '<p role="status" aria-live="polite" className="text-ink-muted [font:var(--type-scale-meta-sm)]">',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the toast's live region is only rendered once there is a message",
    file: "control",
    edits: [
      [
        '        <p aria-live="polite" className="text-ink-muted [font:var(--type-scale-meta-sm)]">\n          {message === "reported" ? REPORTED_MESSAGE : null}\n        </p>',
        '        {message ? (\n          <p aria-live="polite" className="text-ink-muted [font:var(--type-scale-meta-sm)]">\n            {REPORTED_MESSAGE}\n          </p>\n        ) : null}',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the rate limit is swallowed instead of shown",
    file: "control",
    edits: [
      [
        "      if (response.response.status === 429) {\n        setRefusal(response.error?.message ?? OFFLINE_MESSAGE);\n        return;\n      }",
        "      if (response.response.status === 429) {\n        return;\n      }",
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the rate limit closes the modal instead of staying open",
    file: "control",
    edits: [
      [
        "      if (response.response.status === 429) {\n        setRefusal(response.error?.message ?? OFFLINE_MESSAGE);\n        return;\n      }",
        "      if (response.response.status === 429) {\n        setRefusal(response.error?.message ?? OFFLINE_MESSAGE);\n        setOpen(false);\n        return;\n      }",
      ],
    ],
    suite: SUITE,
  },
  {
    description: "a network failure clears the selection",
    file: "control",
    edits: [
      [
        "    } catch {\n      /**\n       * **The request never reached the API.** The modal stays open, the selection is\n       * still chosen, and the Submit is live again — so the user can simply press it\n       * once more.\n       */\n      setRefusal(OFFLINE_MESSAGE);",
        "    } catch {\n      setRefusal(OFFLINE_MESSAGE);\n      setSelected(null);",
      ],
    ],
    suite: SUITE,
  },
  {
    description: "a network failure leaves the Submit disabled — no retry",
    file: "control",
    edits: [
      [
        "    } finally {\n      setBusy(false);\n    }",
        "    } finally {\n      setBusy(true);\n    }",
      ],
    ],
    suite: SUITE,
  },
  {
    description: "the options stop being a radio group",
    file: "control",
    edits: [
      [
        'role="radiogroup" aria-label="Report category"',
        'role="group" aria-label="Report category"',
      ],
      [
        'role="radio"\n                  aria-checked={isSelected}',
        'role="button"\n                  aria-pressed={isSelected}',
      ],
    ],
    suite: SUITE,
  },
  {
    description: "two options can be checked at once",
    file: "control",
    edits: [["const isSelected = selected === category.value;", "const isSelected = true;"]],
    suite: SUITE,
  },
  {
    description: "the option's accessible name swallows the description",
    file: "control",
    edits: [
      [
        '                    <span\n                      aria-hidden="true"\n                      className="mt-1 block [font:var(--type-scale-body-sm)] text-ink-muted"\n                    >\n                      {category.description}\n                    </span>',
        '                    <span\n                      className="mt-1 block [font:var(--type-scale-body-sm)] text-ink-muted"\n                    >\n                      {category.description}\n                    </span>',
      ],
      ["aria-label={category.label}", "aria-label={undefined}"],
    ],
    suite: SUITE,
  },
  {
    description: "the modal's accessible name is something else",
    file: "control",
    edits: [['label="Report this event">', 'label="Send feedback">']],
    suite: SUITE,
  },
  {
    description: "the heading no longer takes the focus when the modal opens",
    file: "control",
    edits: [
      [
        "  useEffect(() => {\n    if (open) headerRef.current?.focus();\n  }, [open]);",
        "  useEffect(() => {\n    if (false && open) headerRef.current?.focus();\n  }, [open]);",
      ],
    ],
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

  // **Every pattern is checked before any edit is applied.**
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
      (caught ? `\n          ${names.slice(0, 2).join("\n          ")}` : ""),
  );
  if (!caught) failures += 1;
}

console.log(`\n${PROBES.length - failures}/${PROBES.length} probes caught`);
if (broken > 0) console.log(`${broken} probe(s) were BROKEN — the probe itself is wrong`);
process.exit(failures === 0 ? 0 : 1);
