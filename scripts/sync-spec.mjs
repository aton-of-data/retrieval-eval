#!/usr/bin/env node
/**
 * Copy the canonical spec/ into each package so it ships with the implementation.
 *
 * The spec is the product; the implementations are two reference readings of it. A published
 * package that omits it forces anyone porting to a third language back to the GitHub UI, and
 * `files: ["spec"]` in package.json was silently shipping nothing because spec/ lives at the
 * repo root, outside the package directory.
 *
 * The copies are build output, not sources: they are gitignored and regenerated on every build.
 */

import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = join(ROOT, "spec");

const TARGETS = [
  join(ROOT, "packages", "retrieval-eval", "spec"),
  join(ROOT, "python", "retrieval-eval", "spec"),
];

if (!existsSync(SOURCE)) {
  process.stderr.write(`error: ${SOURCE} is missing\n`);
  process.exit(1);
}

for (const target of TARGETS) {
  rmSync(target, { recursive: true, force: true });
  cpSync(SOURCE, target, { recursive: true });
  process.stdout.write(`synced spec -> ${target.replace(`${ROOT}/`, "")}\n`);
}
