import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { type Io, main } from "../src/cli.js";
import { TOOL_VERSION } from "../src/report.js";

const SPEC = join(import.meta.dirname, "..", "..", "..", "spec", "fixtures");
const fixture = (...parts: string[]): string => join(SPEC, ...parts);

interface Capture extends Io {
  stdout: string;
  stderr: string;
}

function capture(overrides: Partial<Io> = {}): Capture {
  const io: Capture = {
    stdout: "",
    stderr: "",
    out(text) {
      io.stdout += text;
    },
    err(text) {
      io.stderr += text;
    },
    isTty: false,
    env: {},
    ...overrides,
  };
  return io;
}

/** Run the CLI and return everything a shell would observe. */
function run(...argv: string[]): Capture & { code: number } {
  const io = capture();
  const code = main(argv, io);
  return { ...io, code };
}

const scratch = mkdtempSync(join(tmpdir(), "retrieval-eval-"));
const temps: string[] = [];

function scratchCopy(name: string, source: string): string {
  const path = join(scratch, `${temps.length}-${name}`);
  writeFileSync(path, readFileSync(source, "utf8"), "utf8");
  temps.push(path);
  return path;
}

afterEach(() => {
  temps.length = 0;
});

describe("invocation", () => {
  it("prints the version alone, so CI can parse it", () => {
    const result = run("--version");
    expect(result.stdout).toBe(`${TOOL_VERSION}\n`);
    expect(result.code).toBe(0);
  });

  it("exits 0 for requested help and 2 for a bare invocation", () => {
    expect(run("--help").code).toBe(0);
    expect(run("help").code).toBe(0);
    const bare = run();
    expect(bare.code).toBe(2);
    expect(bare.stdout).toContain("Usage");
  });

  it("documents each command on its own", () => {
    for (const command of ["drift", "score", "validate", "convert"]) {
      const result = run(command, "--help");
      expect(result.code).toBe(0);
      expect(result.stdout).toContain(`retrieval-eval ${command}`);
      expect(result.stdout).toContain("Exit codes");
    }
  });

  it("suggests the command a typo meant", () => {
    const result = run("drif");
    expect(result.code).toBe(2);
    expect(result.stderr).toContain("unknown command 'drif'");
    expect(result.stderr).toContain("try retrieval-eval drift");
  });

  it("names the offending option rather than explaining positional syntax", () => {
    const result = run("drift", "--nope");
    expect(result.code).toBe(2);
    expect(result.stderr).toBe(
      "error  unknown option '--nope'\n        try retrieval-eval --help\n",
    );
  });

  it("names the missing flags together with the command that documents them", () => {
    const result = run("score", "--judgments", fixture("basic", "judgments.jsonl"));
    expect(result.code).toBe(2);
    expect(result.stderr).toContain("score needs --judgments and --run");
    expect(result.stderr).toContain("try retrieval-eval score --help");
  });

  it("answers a missing file with one line, never a stack trace", () => {
    const result = run("drift", "--judgments", "nope.jsonl", "--corpus", "nope.json");
    expect(result.code).toBe(2);
    expect(result.stderr).toBe("error  cannot read nope.jsonl: no such file or directory\n");
  });

  it("rejects a -k that cannot be a cutoff", () => {
    const result = run(
      "score",
      "--judgments",
      fixture("basic", "judgments.jsonl"),
      "--run",
      fixture("basic", "run.jsonl"),
      "-k",
      "0",
    );
    expect(result.code).toBe(2);
    expect(result.stderr).toContain("-k expects a positive integer, got '0'");
  });
});

describe("colour", () => {
  const args = ["validate", "--judgments", fixture("basic", "judgments.jsonl")];

  it("stays plain when stdout is not a terminal", () => {
    expect(run(...args).stdout).not.toContain("\u001b[");
  });

  it("honours NO_COLOR on a terminal", () => {
    const io = capture({ isTty: true, env: { NO_COLOR: "1" } });
    main(args, io);
    expect(io.stdout).not.toContain("\u001b[");
  });

  it("obeys --color over both", () => {
    const always = capture();
    main([...args, "--color", "always"], always);
    expect(always.stdout).toContain("\u001b[");

    const never = capture({ isTty: true, env: {} });
    main([...args, "--color", "never"], never);
    expect(never.stdout).not.toContain("\u001b[");
  });

  it("rejects a colour mode it does not have", () => {
    const result = run(...args, "--color", "mauve");
    expect(result.code).toBe(2);
    expect(result.stderr).toContain("--color expects auto, always or never");
  });
});

describe("drift", () => {
  const args = [
    "drift",
    "--judgments",
    fixture("drift", "judgments.jsonl"),
    "--corpus",
    fixture("drift", "corpus.json"),
  ];

  it("exits 1 on decay, so it stands alone as a CI check", () => {
    const result = run(...args);
    expect(result.code).toBe(1);
    expect(result.stdout).toContain("RE-ANCHORABLE");
    expect(result.stdout).toContain("1 recoverable automatically · 2 need a human");
  });

  it("points at --fix only while there is something to fix", () => {
    expect(run(...args).stdout).toContain("retrieval-eval drift --fix");

    const judgments = join(scratch, "clean.jsonl");
    writeFileSync(
      judgments,
      `${JSON.stringify({
        query_id: "c1",
        doc_uri: "wiki://refunds",
        chunk_id: "c1:d577264d22f91060a5abc8d3df2b1cea",
        relevance: 2,
        labeled_by: "human:ana",
      })}\n`,
      "utf8",
    );
    const clean = run(
      "drift",
      "--judgments",
      judgments,
      "--corpus",
      fixture("merge", "corpus.json"),
    );
    expect(clean.code).toBe(0);
    expect(clean.stdout).toContain("Every label still points at the text it was written for.");
    expect(clean.stdout).not.toContain("--fix");
  });

  it("rewrites recoverable labels in place and leaves the rest alone", () => {
    const path = scratchCopy("judgments.jsonl", fixture("drift", "judgments.jsonl"));
    const result = run(
      "drift",
      "--judgments",
      path,
      "--corpus",
      fixture("drift", "corpus.json"),
      "--fix",
    );

    expect(result.stdout).toContain("re-anchored 1 label(s)");
    expect(result.stdout).toContain("2 label(s) still need a human");

    const before = readFileSync(fixture("drift", "judgments.jsonl"), "utf8");
    const after = readFileSync(path, "utf8");
    expect(after).not.toBe(before);

    // A second pass must change nothing further: fixing is not a ratchet that drifts on its own.
    const again = run(
      "drift",
      "--judgments",
      path,
      "--corpus",
      fixture("drift", "corpus.json"),
      "--fix",
    );
    expect(again.stdout).toContain("re-anchored 0 label(s)");
    expect(readFileSync(path, "utf8")).toBe(after);
  });

  it("emits the whole finding list under --json", () => {
    const result = run(...args, "--json");
    const parsed = JSON.parse(result.stdout) as { findings: unknown[] };
    expect(parsed.findings).toHaveLength(4);
  });
});

describe("score", () => {
  const args = [
    "score",
    "--judgments",
    fixture("strata", "judgments.jsonl"),
    "--run",
    fixture("strata", "run.jsonl"),
    "-k",
    "3",
  ];

  it("passes an average gate while failing the worst stratum, and exits 1", () => {
    const result = run(...args, "--gate", "recall@3:0.5", "--gate", "worst-stratum:recall@3:0.7");
    expect(result.code).toBe(1);
    expect(result.stdout).toContain("ok recall@3:0.5");
    expect(result.stdout).toContain("x  worst-stratum:recall@3:0.7");
    expect(result.stdout).toContain("FAIL");
  });

  it("marks the weakest query class in the stratum table", () => {
    const result = run(...args);
    expect(result.stdout).toMatch(/legal\s+0\.0000.*worst/);
    expect(result.code).toBe(0);
  });

  it("writes the report to --out while printing for a human", () => {
    const out = join(scratch, "report.json");
    const result = run(...args, "--out", out);
    expect(result.stdout).toContain("recall@3");
    const report = JSON.parse(readFileSync(out, "utf8")) as { spec_version: string };
    expect(report.spec_version).toBe("1");
  });
});

describe("validate and convert", () => {
  it("exits 0 with warnings and 1 with errors", () => {
    const ok = run("validate", "--judgments", fixture("strata", "judgments.jsonl"));
    expect(ok.code).toBe(0);
    expect(ok.stdout).toContain("warning");

    const broken = join(scratch, "no-positives.jsonl");
    writeFileSync(broken, '{"query_id":"q1","doc_uri":"d1","relevance":0}\n', "utf8");
    const bad = run("validate", "--judgments", broken);
    expect(bad.code).toBe(1);
    expect(bad.stdout).toContain("[no-positives]");
  });

  it("writes qrels to stdout and nothing else", () => {
    const result = run(
      "convert",
      "--judgments",
      fixture("basic", "judgments.jsonl"),
      "--to",
      "qrels",
    );
    expect(result.code).toBe(0);
    expect(result.stderr).toBe("");
    for (const line of result.stdout.trim().split("\n")) {
      expect(line.split(" ")).toHaveLength(4);
    }
  });

  it("refuses a format it cannot produce", () => {
    const result = run(
      "convert",
      "--judgments",
      fixture("basic", "judgments.jsonl"),
      "--to",
      "csv",
    );
    expect(result.code).toBe(2);
    expect(result.stderr).toContain("unknown --to 'csv'");
  });
});
