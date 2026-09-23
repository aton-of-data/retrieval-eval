#!/usr/bin/env node
/**
 * Assert the version agrees in all four places it is written.
 *
 * It lives in package.json, pyproject.toml, and a TOOL_VERSION constant in each implementation
 * because the constant is stamped into every report, and reading it back out of package
 * metadata at runtime would mean either a bundler plugin or a filesystem read on startup, both
 * of which cost more than this check does.
 *
 * Four hand-edited copies of one number is a drift problem. A tool whose entire subject is
 * drift should not have one in its own release process, and "the report says 0.1.0 but the
 * package is 0.2.0" is exactly the kind of quiet wrongness that makes people stop trusting
 * every other number a tool prints.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

const read = (...parts) => readFileSync(join(ROOT, ...parts), "utf8");

/** Pull one capture group out of a file, or explain precisely what could not be found. */
function extract(label, path, pattern) {
  const match = read(...path).match(pattern);
  if (!match) {
    process.stderr.write(`error: no version found in ${path.join("/")} (${label})\n`);
    process.exit(2);
  }
  return { label, source: path.join("/"), version: match[1] };
}

const found = [
  extract("npm package", ["packages", "retrieval-eval", "package.json"], /"version":\s*"([^"]+)"/),
  extract(
    "ts TOOL_VERSION",
    ["packages", "retrieval-eval", "src", "report.ts"],
    /TOOL_VERSION\s*=\s*"([^"]+)"/,
  ),
  extract("pypi package", ["python", "retrieval-eval", "pyproject.toml"], /^version = "([^"]+)"/m),
  extract(
    "py TOOL_VERSION",
    ["python", "retrieval-eval", "src", "retrieval_eval", "report.py"],
    /TOOL_VERSION\s*=\s*"([^"]+)"/,
  ),
];

const distinct = [...new Set(found.map((entry) => entry.version))];

for (const entry of found) {
  process.stdout.write(`  ${entry.version.padEnd(10)} ${entry.source}  (${entry.label})\n`);
}

if (distinct.length !== 1) {
  process.stderr.write(`\nerror: ${distinct.length} different versions: ${distinct.join(", ")}\n`);
  process.stderr.write("All four must match before a release.\n");
  process.exit(1);
}

process.stdout.write(`\nok  version ${distinct[0]} is consistent in all ${found.length} places\n`);
