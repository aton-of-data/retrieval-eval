#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { drift, fix } from "./drift.js";
import { evaluateGates, parseGate } from "./gate.js";
import { COMMANDS, COMMAND_HELP, type Command, ROOT_HELP } from "./help.js";
import {
  parseCorpus,
  parseJudgments,
  parseRun,
  serializeJudgments,
  validate,
} from "./judgments.js";
import { fromQrels, toQrels, toTrecRun } from "./qrels.js";
import { TOOL_VERSION, buildReport } from "./report.js";
import type { DriftResult, Report } from "./types.js";
import { type ColorWhen, bar, heading, num, paint, pct, setColor } from "./ui.js";

/** Where the CLI writes. Injected so the command surface is testable without a subprocess. */
export interface Io {
  out: (text: string) => void;
  err: (text: string) => void;
  isTty: boolean;
  env: NodeJS.ProcessEnv;
}

const processIo: Io = {
  out: (text) => process.stdout.write(text),
  err: (text) => process.stderr.write(text),
  isTty: process.stdout.isTTY === true,
  env: process.env,
};

const EXIT_OK = 0;
const EXIT_FAILED = 1;
const EXIT_USAGE = 2;

/** An input or invocation the user can fix. Never a stack trace: see `main`. */
class CliError extends Error {
  constructor(
    message: string,
    readonly hint?: string,
  ) {
    super(message);
  }
}

const OPTIONS = {
  judgments: { type: "string" },
  run: { type: "string" },
  corpus: { type: "string" },
  qrels: { type: "string" },
  baseline: { type: "string" },
  out: { type: "string" },
  to: { type: "string" },
  k: { type: "string", short: "k" },
  threshold: { type: "string" },
  color: { type: "string" },
  gate: { type: "string", multiple: true },
  fix: { type: "boolean", default: false },
  "as-chunk-ids": { type: "boolean", default: false },
  json: { type: "boolean", default: false },
  help: { type: "boolean", short: "h", default: false },
  version: { type: "boolean", short: "v", default: false },
} as const;

type Values = ReturnType<typeof parseArgs<{ options: typeof OPTIONS; allowPositionals: true }>>;

export function main(argv: string[], io: Io = processIo): number {
  let parsed: Values;
  try {
    parsed = parseArgs({ args: argv, options: OPTIONS, allowPositionals: true });
  } catch (error) {
    // Node's own message explains how to pass a positional that starts with a dash, which is
    // never what happened here and buries the option that was actually wrong.
    const unknown = /Unknown option '([^']+)'/.exec((error as Error).message);
    const message = unknown ? `unknown option '${unknown[1]}'` : (error as Error).message;
    return report(io, new CliError(message, "retrieval-eval --help"));
  }

  const { values, positionals } = parsed;
  setColor("auto", io.isTty, io.env);

  try {
    setColor(resolveColor(values.color), io.isTty, io.env);

    if (values.version) {
      io.out(`${TOOL_VERSION}\n`);
      return EXIT_OK;
    }

    const [first, second] = positionals;
    const command = first === "help" ? second : first;

    if (command === undefined) {
      io.out(`${ROOT_HELP}\n`);
      // `help` and `--help` were asked for; a bare invocation was not, and CI should notice.
      return values.help || first === "help" ? EXIT_OK : EXIT_USAGE;
    }
    if (!isCommand(command)) {
      const near = closest(command);
      throw new CliError(
        `unknown command '${command}'`,
        near ? `retrieval-eval ${near}` : "retrieval-eval --help",
      );
    }
    if (values.help || first === "help") {
      io.out(`${COMMAND_HELP[command]}\n`);
      return EXIT_OK;
    }

    switch (command) {
      case "drift":
        return runDrift(values, io);
      case "score":
        return runScore(values, io);
      case "validate":
        return runValidate(values, io);
      case "convert":
        return runConvert(values, io);
    }
  } catch (error) {
    return report(io, error);
  }
}

function isCommand(value: string): value is Command {
  return (COMMANDS as readonly string[]).includes(value);
}

/** The command a typo most likely meant, by edit distance, or nothing if none is close. */
function closest(typo: string): Command | undefined {
  let best: Command | undefined;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const candidate of COMMANDS) {
    const distance = editDistance(typo, candidate);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = candidate;
    }
  }
  return bestDistance <= 3 ? best : undefined;
}

function editDistance(a: string, b: string): number {
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const current = [i];
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      current[j] = Math.min(
        (current[j - 1] as number) + 1,
        (previous[j] as number) + 1,
        (previous[j - 1] as number) + cost,
      );
    }
    previous = current;
  }
  return previous[b.length] as number;
}

function resolveColor(value: string | undefined): ColorWhen {
  if (value === undefined) return "auto";
  if (value === "auto" || value === "always" || value === "never") return value;
  throw new CliError(`--color expects auto, always or never, got '${value}'`);
}

/** Turn any failure into one readable line plus, where there is one, the way out of it. */
function report(io: Io, error: unknown): number {
  const message = error instanceof Error ? error.message : String(error);
  io.err(`${paint("red", "error")}  ${message}\n`);
  if (error instanceof CliError && error.hint !== undefined) {
    io.err(`${paint("dim", "        try")} ${error.hint}\n`);
  }
  return EXIT_USAGE;
}

/** Filesystem reasons, phrased identically in both implementations so CI can diff them. */
const READ_ERRORS: Record<string, string> = {
  ENOENT: "no such file or directory",
  EACCES: "permission denied",
  EISDIR: "is a directory",
};

function read(path: string): string {
  try {
    return readFileSync(path, "utf8");
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code ?? "";
    throw new CliError(`cannot read ${path}: ${READ_ERRORS[code] ?? (error as Error).message}`);
  }
}

function required(values: Values["values"], command: Command, flags: string[]): void {
  const missing = flags.filter((flag) => values[flag as keyof typeof values] === undefined);
  if (missing.length > 0) {
    throw new CliError(
      `${command} needs ${flags.map((flag) => `--${flag}`).join(" and ")}`,
      `retrieval-eval ${command} --help`,
    );
  }
}

function integer(raw: string | undefined, flag: string, fallback: number): number {
  if (raw === undefined) return fallback;
  const value = Number.parseInt(raw, 10);
  if (!Number.isInteger(value) || value < 1) {
    throw new CliError(`${flag} expects a positive integer, got '${raw}'`);
  }
  return value;
}

function runDrift(values: Values["values"], io: Io): number {
  required(values, "drift", ["judgments", "corpus"]);
  const path = values.judgments as string;
  const judgments = parseJudgments(read(path));
  const corpus = parseCorpus(read(values.corpus as string));
  const result = drift(judgments, corpus);

  if (values.json) io.out(`${JSON.stringify(result, null, 2)}\n`);
  else printDrift(io, result, judgments.length, values.fix === true);

  if (values.fix) {
    const fixed = fix(judgments, result);
    writeFileSync(path, serializeJudgments(fixed.judgments), "utf8");
    io.out(
      `\n  ${paint("green", "fixed")}   re-anchored ${fixed.reanchored} label(s) in ${path}\n` +
        `  ${paint("yellow", "review")}  ${fixed.needsReview.length} label(s) still need a human\n`,
    );
  }

  // Non-zero when labels have decayed, so `drift` stands alone as a CI check.
  return result.summary.invalid_ratio > 0 ? EXIT_FAILED : EXIT_OK;
}

function printDrift(io: Io, result: DriftResult, total: number, fixing: boolean): void {
  const s = result.summary;
  // Marks are padded before colouring: escape codes have width in the string, not on screen.
  const row = (
    mark: string,
    color: Parameters<typeof paint>[0],
    count: number,
    label: string,
    note: string,
  ) =>
    `  ${paint(color, mark.padEnd(2))} ${String(count).padStart(3)}  ${label.padEnd(14)} ${paint("dim", note)}\n`;

  let out = "\n";
  out += `  ${total} judgments · labeled @ fingerprint ${paint("cyan", result.judgments_fingerprint ?? "unknown")}\n`;
  out += `  live corpus    @ fingerprint ${paint("cyan", result.corpus_fingerprint ?? "unknown")}\n\n`;
  out += row("ok", "green", s.valid, "VALID", "chunk_id still present");
  out += row("!", "yellow", s.re_anchorable, "RE-ANCHORABLE", "text moved to a new chunk_id");
  out += row("!", "yellow", s.merged, "MERGED", "text absorbed into a coarser chunk");
  out += row("!", "yellow", s.split, "SPLIT", "labeled text now spans 2+ chunks");
  out += row("x", "red", s.orphaned, "ORPHANED", "source text or document is gone");

  if (s.invalid_ratio > 0) {
    const recoverable = s.re_anchorable + s.merged;
    const needsHuman = s.split + s.orphaned;
    out += `\n  ${paint("bold", `${pct(s.invalid_ratio)} of your judgment set no longer matches the live corpus.`)}\n`;
    out += `  ${paint("dim", "Any metric computed against it is measuring two changes at once.")}\n`;
    // Split the number so it is actionable rather than merely alarming.
    out += `  ${paint("dim", `${recoverable} recoverable automatically · ${needsHuman} need a human`)}\n`;
    if (recoverable > 0 && !fixing) {
      out += `\n  ${paint("dim", "next")}    retrieval-eval drift --fix, to re-anchor the recoverable labels\n`;
    }
  } else {
    out += `\n  ${paint("green", "Every label still points at the text it was written for.")}\n`;
  }
  io.out(out);
}

function runScore(values: Values["values"], io: Io): number {
  required(values, "score", ["judgments", "run"]);
  const judgments = parseJudgments(read(values.judgments as string));
  const run = parseRun(read(values.run as string));
  const k = integer(values.k, "-k", 10);
  const threshold = integer(values.threshold, "--threshold", 1);

  const corpus = values.corpus ? parseCorpus(read(values.corpus)) : undefined;
  const driftResult = corpus ? drift(judgments, corpus) : undefined;
  const report = buildReport({ judgments, run, k, threshold, corpus, driftResult });

  const gates = (values.gate ?? []).map(parseGate);
  if (gates.length > 0) {
    const baseline = values.baseline ? (JSON.parse(read(values.baseline)) as Report) : undefined;
    const evaluated = evaluateGates({ report, baseline, gates });
    report.verdict.status = evaluated.status;
    report.verdict.gates = evaluated.results;
    report.verdict.reasons = [...report.verdict.reasons, ...evaluated.reasons];
  }

  if (values.out) writeFileSync(values.out, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  if (values.json) io.out(`${JSON.stringify(report, null, 2)}\n`);
  else printScore(io, report);

  return report.verdict.status === "PASS" ? EXIT_OK : EXIT_FAILED;
}

function printScore(io: Io, report: Report): void {
  let out = `\n  ${report.judgments.queries} queries · ${report.judgments.labels} labels`;
  if (report.judgments.human_labels !== undefined) {
    out += paint(
      "dim",
      ` (${report.judgments.human_labels} human, ${report.judgments.synthetic_labels ?? 0} synthetic)`,
    );
  }
  out += "\n\n";

  for (const [name, measurement] of Object.entries(report.metrics)) {
    const ci = measurement.ci
      ? paint("dim", `  [${num(measurement.ci[0])}, ${num(measurement.ci[1])}]`)
      : "";
    out += `  ${name.padEnd(16)} ${num(measurement.value)}${ci}\n`;
  }

  if (report.per_stratum) {
    const primary = Object.keys(report.metrics).find((m) => m.startsWith("recall@")) ?? "mrr";
    const ranked = Object.entries(report.per_stratum)
      .map(([name, stratum]) => ({
        name,
        n: stratum.n,
        value: stratum.metrics[primary]?.value ?? 0,
      }))
      .sort((a, b) => a.value - b.value || a.name.localeCompare(b.name));

    out += heading(`${primary} by stratum`);
    for (const [index, stratum] of ranked.entries()) {
      const flag = index === 0 && ranked.length > 1 ? paint("yellow", "  worst") : "";
      out += `  ${paint("dim", "·")} ${stratum.name.padEnd(20)} ${num(stratum.value)}  ${paint("dim", bar(stratum.value))}  ${paint("dim", `n=${stratum.n}`)}${flag}\n`;
    }
  }

  if (report.judgments.drift && report.judgments.drift.invalid_ratio > 0) {
    out += `\n  ${paint("yellow", "warning")} ${pct(report.judgments.drift.invalid_ratio)} of judgments no longer match the corpus\n`;
  }

  const gates = report.verdict.gates ?? [];
  if (gates.length > 0) {
    out += heading("gates");
    for (const gate of gates) {
      const mark =
        gate.status === "PASS"
          ? paint("green", "ok")
          : gate.status === "FAIL"
            ? paint("red", "x ")
            : paint("yellow", "? ");
      out += `  ${mark} ${gate.expression}\n`;
    }
  }

  for (const reason of report.verdict.reasons) {
    out += `  ${paint("dim", `→ ${reason}`)}\n`;
  }

  const color =
    report.verdict.status === "PASS"
      ? "green"
      : report.verdict.status === "FAIL"
        ? "red"
        : "yellow";
  out += `\n  ${paint(color, paint("bold", report.verdict.status))}\n`;
  io.out(out);
}

function runValidate(values: Values["values"], io: Io): number {
  required(values, "validate", ["judgments"]);
  const result = validate(parseJudgments(read(values.judgments as string)));

  if (values.json) {
    io.out(`${JSON.stringify(result, null, 2)}\n`);
    return result.ok ? EXIT_OK : EXIT_FAILED;
  }

  let out = `\n  ${result.labels} labels · ${result.queries} queries · ${Object.keys(result.strata).length} strata\n\n`;
  if (result.issues.length === 0) {
    out += `  ${paint("green", "ok")}      no issues\n`;
  } else {
    for (const issue of result.issues) {
      const mark =
        issue.severity === "error" ? paint("red", "error  ") : paint("yellow", "warning");
      out += `  ${mark} ${paint("dim", `[${issue.code}]`)} ${issue.message}\n`;
    }
  }
  io.out(out);
  return result.ok ? EXIT_OK : EXIT_FAILED;
}

function runConvert(values: Values["values"], io: Io): number {
  const target = values.to;
  if (target === undefined) {
    throw new CliError(
      "convert needs --to qrels, trec-run or judgments",
      "retrieval-eval convert --help",
    );
  }

  switch (target) {
    case "judgments": {
      required(values, "convert", ["qrels"]);
      const judgments = fromQrels(read(values.qrels as string), {
        asChunkIds: values["as-chunk-ids"] === true,
      });
      io.out(serializeJudgments(judgments));
      return EXIT_OK;
    }
    case "qrels": {
      required(values, "convert", ["judgments"]);
      io.out(toQrels(parseJudgments(read(values.judgments as string))));
      return EXIT_OK;
    }
    case "trec-run": {
      required(values, "convert", ["run"]);
      io.out(toTrecRun(parseRun(read(values.run as string))));
      return EXIT_OK;
    }
    default:
      throw new CliError(
        `unknown --to '${target}', expected qrels, trec-run or judgments`,
        "retrieval-eval convert --help",
      );
  }
}

const entry = process.argv[1];
if (entry !== undefined && import.meta.url === pathToFileURL(entry).href) {
  process.exit(main(process.argv.slice(2)));
}
