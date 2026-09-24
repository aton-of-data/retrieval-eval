#!/usr/bin/env node
/**
 * Build the GitHub Pages site: one static page, rendered from the root README.
 *
 * The README is the documentation. A second, hand-written landing page would be a fourth copy
 * of the same prose, and would drift from it the way the package READMEs once did. So the site
 * is not written, it is derived: the README goes through GitHub's own markdown renderer (the
 * same one github.com uses, so tables, alerts and highlighting match), and the result is wrapped
 * in a single template. No markdown library, no static site generator, nothing to install.
 *
 * Usage:
 *   GITHUB_TOKEN=... node scripts/build-site.mjs   write _site/index.html
 *
 * The token is optional locally (the API allows 60 unauthenticated calls an hour) and is the
 * workflow's own GITHUB_TOKEN in CI.
 */

import { execSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = "https://github.com/aton-of-data/retrieval-eval";
const OUT = join(ROOT, "_site");

const readme = readFileSync(join(ROOT, "README.md"), "utf8");
const pkg = JSON.parse(
  readFileSync(join(ROOT, "packages", "retrieval-eval", "package.json"), "utf8"),
);

/** Relative links would resolve against the Pages origin and 404. Point them at the repo. */
function absolutizeLinks(markdown) {
  return markdown.replace(/\]\((?!https?:|#|mailto:)([^)]+)\)/g, (_match, target) => {
    const clean = target.replace(/^\.\//, "");
    const kind = clean === "LICENSE" || clean.includes(".") ? "blob" : "tree";
    return `](${REPO}/${kind}/main/${clean})`;
  });
}

async function render(markdown) {
  const headers = { Accept: "application/vnd.github+json", "Content-Type": "application/json" };
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  const response = await fetch("https://api.github.com/markdown", {
    method: "POST",
    headers,
    body: JSON.stringify({
      text: markdown,
      mode: "markdown",
      context: "aton-of-data/retrieval-eval",
    }),
  });
  if (!response.ok) {
    process.stderr.write(
      `error: markdown API returned ${response.status}: ${await response.text()}\n`,
    );
    process.exit(1);
  }
  return addHeadingIds(await response.text());
}

/**
 * The API renders headings without ids (github.com adds them with JavaScript), so in-page links
 * like #why-zero-dependencies would miss. Slug them the way GitHub does.
 */
function addHeadingIds(html) {
  const seen = new Map();
  return html.replace(/<h([1-4])([^>]*)>([\s\S]*?)<\/h\1>/g, (_match, level, attrs, inner) => {
    const text = inner.replace(/<[^>]+>/g, "").replace(/&[a-z]+;|&#\d+;/g, "");
    const base = text
      .trim()
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s_-]/gu, "")
      .replace(/\s/g, "-");
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    const id = count ? `${base}-${count}` : base;
    return `<h${level}${attrs} id="${id}">${inner}</h${level}>`;
  });
}

function commit() {
  try {
    return execSync("git rev-parse --short HEAD", { cwd: ROOT }).toString().trim();
  } catch {
    return "local";
  }
}

const body = await render(absolutizeLinks(readme));
const sha = commit();
const template = readFileSync(join(ROOT, "scripts", "site", "template.html"), "utf8");

const html = template
  .replaceAll("{{version}}", pkg.version)
  .replaceAll("{{description}}", pkg.description.replaceAll('"', "&quot;"))
  .replaceAll("{{repo}}", REPO)
  .replaceAll("{{sha}}", sha)
  .replace("{{content}}", () => body);

mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, "index.html"), html);
writeFileSync(join(OUT, ".nojekyll"), "");
process.stdout.write(`ok   _site/index.html  (v${pkg.version} @ ${sha})\n`);
