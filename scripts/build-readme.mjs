#!/usr/bin/env node
/**
 * Generate the per-package READMEs from the canonical root README.
 *
 * There were three hand-maintained copies and they had already drifted: the npm copy had lost
 * the `pip install` block, the PyPI copy still said `npx`, and a CI snippet existed in two
 * versions. Keeping three prose files in sync by hand is the same class of problem this project
 * exists to catch, so it is solved the same way: one source of truth, and a check that fails
 * when a derived copy stops matching.
 *
 * Two transforms are applied:
 *
 *   1. Variant blocks. `<!--:npm-->` / `<!--:pypi-->` / `<!--:root-->` ... `<!--:end-->` keep a
 *      block only for that target. Unmarked prose is shared.
 *   2. Link absolutization. A package README is read on npmjs.com and pypi.org, where relative
 *      links resolve against nothing. Every relative link is rewritten to a GitHub blob URL.
 *
 * Usage:
 *   node scripts/build-readme.mjs          write the derived copies
 *   node scripts/build-readme.mjs --check  exit 1 if they are out of date (CI)
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = "https://github.com/aton-of-data/retrieval-eval";
const SOURCE = join(ROOT, "README.md");

const TARGETS = [
  { variant: "npm", path: join(ROOT, "packages", "retrieval-eval", "README.md") },
  { variant: "pypi", path: join(ROOT, "python", "retrieval-eval", "README.md") },
];

const VARIANTS = ["root", "npm", "pypi"];

/** Keep blocks marked for `variant`, drop the rest, leave unmarked prose alone. */
function applyVariants(markdown, variant) {
  const block = new RegExp(`<!--:(${VARIANTS.join("|")})-->\\n([\\s\\S]*?)<!--:end-->\\n`, "g");
  return markdown.replace(block, (_match, marker, body) => (marker === variant ? body : ""));
}

/**
 * Rewrite relative links to absolute ones. Anchors (`#why-zero-dependencies`) still work on
 * both registries, so they are left alone; everything else would 404.
 */
function absolutizeLinks(markdown) {
  return markdown.replace(/\]\((?!https?:|#|mailto:)([^)]+)\)/g, (_match, target) => {
    const clean = target.replace(/^\.\//, "");
    const kind = clean === "LICENSE" || clean.includes(".") ? "blob" : "tree";
    return `](${REPO}/${kind}/main/${clean})`;
  });
}

function render(source, variant) {
  const generated = absolutizeLinks(applyVariants(source, variant));
  // Variant removal leaves runs of blank lines where blocks used to be.
  return `${generated.replace(/\n{3,}/g, "\n\n").trimEnd()}\n`;
}

const source = readFileSync(SOURCE, "utf8");
const check = process.argv.includes("--check");
let stale = 0;

for (const { variant, path } of TARGETS) {
  const expected = render(source, variant);
  const relative = path.replace(`${ROOT}/`, "");

  if (check) {
    let actual = "";
    try {
      actual = readFileSync(path, "utf8");
    } catch {
      /* missing counts as stale */
    }
    if (actual === expected) {
      process.stdout.write(`ok   ${relative}\n`);
    } else {
      stale += 1;
      process.stdout.write(`STALE ${relative}\n`);
    }
  } else {
    writeFileSync(path, expected);
    process.stdout.write(`wrote ${relative}\n`);
  }
}

if (check && stale > 0) {
  process.stderr.write(
    `\n${stale} README(s) no longer match the root README.
Edit README.md, never the generated copies, then run:

    node scripts/build-readme.mjs
`,
  );
  process.exit(1);
}
