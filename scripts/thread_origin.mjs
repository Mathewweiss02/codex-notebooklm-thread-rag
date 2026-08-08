#!/usr/bin/env node
import { pathToFileURL } from "node:url";
import { discoverOrigins, formatOriginReport } from "./thread_origin_lib.mjs";

function usage() {
  console.log(`Usage:
  node thread_origin.mjs --query "remembered original instructions" [options]

Options:
  -q, --query TEXT          Source-instruction clues (required)
      --thread ID           Restrict to a known thread; repeatable
      --cwd PATH            Restrict discovery to one workspace
      --cwd-mode MODE       exact (default), prefix, or contains
      --limit-threads N     Candidate threads to inspect (default: 5)
      --limit N             Origin turns to return (default: 10)
      --per-thread N        Candidate turns kept per thread (default: 5)
      --min-coverage N      Minimum query-concept coverage 0..1 (default: 0.35)
      --min-concepts N      Minimum matched concepts (default: 2)
      --max-chars N         Maximum redacted excerpt characters (default: 7000)
      --alias A=B|C         Add a query concept and variants; repeatable
      --include-current     Permit the current thread during discovery
      --include-subagents   Include worker/guardian session threads
      --root PATH           Override a corpus root; repeatable
      --no-hydrate          Skip title hydration during discovery
      --json                Emit structured JSON
  -h, --help                Show this help

The command is read-only. It ranks user-authored turns and tool-returned source
evidence that look like original instructions, and penalizes recaps, mission
packets, confirmation restatements, embedded transcripts, and completion updates.`);
}

function value(argv, index, option) {
  const result = argv[index + 1];
  if (!result || result.startsWith("--")) throw new Error(`${option} requires a value.`);
  return result;
}

function positiveInteger(raw, option) {
  const number = Number(raw);
  if (!Number.isInteger(number) || number < 1) throw new Error(`${option} must be a positive integer.`);
  return number;
}

export function parseArgs(argv) {
  const options = { query: null, threadIds: [], roots: [], aliases: [], cwd: null, cwdMode: "exact", limitThreads: 5, limit: 10, limitPerThread: 5, minCoverage: 0.35, minConcepts: 2, maxChars: 7000, hydrate: true, includeCurrent: false, includeSubagents: false, json: false };
  const positional = [];
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") options.help = true;
    else if (arg === "--query" || arg === "-q") { options.query = value(argv, index, arg); index += 1; }
    else if (arg === "--thread") { options.threadIds.push(value(argv, index, arg)); index += 1; }
    else if (arg === "--cwd") { options.cwd = value(argv, index, arg); index += 1; }
    else if (arg === "--cwd-mode") { options.cwdMode = value(argv, index, arg); index += 1; }
    else if (arg === "--limit-threads") { options.limitThreads = positiveInteger(value(argv, index, arg), arg); index += 1; }
    else if (arg === "--limit") { options.limit = positiveInteger(value(argv, index, arg), arg); index += 1; }
    else if (arg === "--per-thread") { options.limitPerThread = positiveInteger(value(argv, index, arg), arg); index += 1; }
    else if (arg === "--min-coverage") { options.minCoverage = Number(value(argv, index, arg)); index += 1; }
    else if (arg === "--min-concepts") { options.minConcepts = positiveInteger(value(argv, index, arg), arg); index += 1; }
    else if (arg === "--max-chars") { options.maxChars = positiveInteger(value(argv, index, arg), arg); index += 1; }
    else if (arg === "--alias") { options.aliases.push(value(argv, index, arg)); index += 1; }
    else if (arg === "--include-current") options.includeCurrent = true;
    else if (arg === "--include-subagents") options.includeSubagents = true;
    else if (arg === "--root") { options.roots.push(value(argv, index, arg)); index += 1; }
    else if (arg === "--no-hydrate") options.hydrate = false;
    else if (arg === "--json") options.json = true;
    else if (arg.startsWith("-")) throw new Error(`Unknown option: ${arg}`);
    else positional.push(arg);
  }
  if (!options.query && positional.length) options.query = positional.join(" ");
  if (!options.help && !options.query) throw new Error("--query is required.");
  if (!Number.isFinite(options.minCoverage) || options.minCoverage < 0 || options.minCoverage > 1) throw new Error("--min-coverage must be between 0 and 1.");
  if (!["exact", "prefix", "contains"].includes(options.cwdMode)) throw new Error("--cwd-mode must be exact, prefix, or contains.");
  return options;
}

async function main() {
  try {
    const options = parseArgs(process.argv.slice(2));
    if (options.help) { usage(); return; }
    const report = await discoverOrigins(options);
    console.log(options.json ? JSON.stringify(report, null, 2) : formatOriginReport(report));
  } catch (error) {
    console.error(`Thread instruction-origin search failed: ${error.stack || error.message}`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
