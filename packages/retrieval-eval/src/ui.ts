/**
 * Terminal presentation: colour policy, number formatting and the small layout primitives the
 * CLI shares. Kept separate from `cli.ts` so the Python implementation has an obvious
 * counterpart to stay byte-identical with.
 */

export type ColorWhen = "auto" | "always" | "never";

const CODES = {
  reset: "[0m",
  dim: "[2m",
  bold: "[1m",
  red: "[31m",
  green: "[32m",
  yellow: "[33m",
  cyan: "[36m",
} as const;

export type Color = keyof typeof CODES;

let enabled = false;

/**
 * Decide whether to emit escape codes. `never` and `always` are explicit; `auto` follows the
 * NO_COLOR convention first, then whether stdout is a terminal, so redirected output and CI
 * logs stay diffable.
 */
export function setColor(when: ColorWhen, isTty: boolean, env: NodeJS.ProcessEnv): void {
  if (when === "never") enabled = false;
  else if (when === "always") enabled = true;
  else enabled = isTty && env.NO_COLOR === undefined;
}

export function paint(color: Color, text: string): string {
  return enabled ? `${CODES[color]}${text}${CODES.reset}` : text;
}

export const num = (value: number): string => value.toFixed(4);
export const pct = (value: number): string => `${(value * 100).toFixed(0)}%`;

/** A value between 0 and 1 as eight cells, so a column of strata is scannable at a glance. */
export function bar(value: number, width = 8): string {
  const clamped = Math.min(Math.max(value, 0), 1);
  const filled = Math.round(clamped * width);
  return "█".repeat(filled) + "░".repeat(width - filled);
}

/** A dim section heading with a blank line above it. */
export function heading(text: string): string {
  return `\n  ${paint("dim", text)}\n`;
}
