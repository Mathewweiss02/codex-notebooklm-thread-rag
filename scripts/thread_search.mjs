#!/usr/bin/env node
import { formatHumanReport, searchThreads } from "./thread_search_lib.mjs";
import { pathToFileURL } from "node:url";

function printUsage() {
  console.log(`Usage:
  node thread_search.mjs --query "remembered clues" [options]
  node thread_search.mjs "remembered clues" [options]

Options:
  -q, --query TEXT          Natural-language memory or exact clues
      --cwd PATH            Restrict to one workspace cwd
      --cwd-mode MODE       exact (default), prefix, or contains
      --after DATE          Keep matching messages on/after an ISO date
      --before DATE         Keep matching messages on/before an ISO date
      --limit N             Return at most N threads (default: 10)
      --excerpts N          Evidence excerpts per result (default: 3)
      --window-days N       Event-cluster window (default: 4)
      --min-score N         Abstain below this score (default: 18; use 0 for maximum recall)
      --alias A=B|C         Add a query concept and variants; repeatable
      --thread ID           Restrict ranking to a known candidate task; repeatable
      --exclude-thread ID   Exclude a thread id; repeatable
      --include-current     Do not auto-exclude CODEX_THREAD_ID
      --include-subagents   Include hidden worker/guardian session threads
      --active-only         Search active session logs only
      --archived-only       Search archived session logs only
      --root PATH           Override a corpus root; repeatable
      --no-hydrate          Skip app-server title/preview hydration
      --hydrate             Force app-server hydration with custom roots
      --json                Emit structured JSON
  -h, --help                Show this help

The search is read-only. It scans only user and assistant message items, collapses
active/archived duplicates, redacts common credential forms in excerpts, and
excludes the current Codex thread by default when CODEX_THREAD_ID is available.`);
}

function requiredValue(argv, index, option) {
  const value = argv[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`${option} requires a value.`);
  return value;
}

function positiveInteger(value, option) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) throw new Error(`${option} must be a positive integer.`);
  return parsed;
}

export function parseArgs(argv) {
  const options = {
    query: null,
    roots: [],
    aliases: [],
    includeThreadIds: [],
    excludeThreadIds: [],
    cwd: null,
    cwdMode: "exact",
    after: null,
    before: null,
    limit: 10,
    excerpts: 3,
    windowDays: 4,
    minScore: 18,
    archivedMode: "both",
    hydrate: null,
    json: false,
    includeCurrent: false,
    includeSubagents: false,
  };
  const positional = [];
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else if (arg === "--query" || arg === "-q") {
      options.query = requiredValue(argv, index, arg);
      index += 1;
    } else if (arg === "--cwd") {
      options.cwd = requiredValue(argv, index, arg);
      index += 1;
    } else if (arg === "--cwd-mode") {
      options.cwdMode = requiredValue(argv, index, arg);
      index += 1;
    } else if (arg === "--after") {
      options.after = requiredValue(argv, index, arg);
      index += 1;
    } else if (arg === "--before") {
      options.before = requiredValue(argv, index, arg);
      index += 1;
    } else if (arg === "--limit") {
      options.limit = positiveInteger(requiredValue(argv, index, arg), arg);
      index += 1;
    } else if (arg === "--excerpts") {
      options.excerpts = positiveInteger(requiredValue(argv, index, arg), arg);
      index += 1;
    } else if (arg === "--window-days") {
      options.windowDays = positiveInteger(requiredValue(argv, index, arg), arg);
      index += 1;
    } else if (arg === "--min-score") {
      options.minScore = Number(requiredValue(argv, index, arg));
      if (!Number.isFinite(options.minScore) || options.minScore < 0) throw new Error("--min-score must be a non-negative number.");
      index += 1;
    } else if (arg === "--alias") {
      options.aliases.push(requiredValue(argv, index, arg));
      index += 1;
    } else if (arg === "--thread") {
      options.includeThreadIds.push(requiredValue(argv, index, arg));
      index += 1;
    } else if (arg === "--exclude-thread") {
      options.excludeThreadIds.push(requiredValue(argv, index, arg));
      index += 1;
    } else if (arg === "--include-current") {
      options.includeCurrent = true;
    } else if (arg === "--include-subagents") {
      options.includeSubagents = true;
    } else if (arg === "--active-only") {
      options.archivedMode = "active";
    } else if (arg === "--archived-only") {
      options.archivedMode = "archived";
    } else if (arg === "--root") {
      options.roots.push(requiredValue(argv, index, arg));
      index += 1;
    } else if (arg === "--no-hydrate") {
      options.hydrate = false;
    } else if (arg === "--hydrate") {
      options.hydrate = true;
    } else if (arg === "--json") {
      options.json = true;
    } else if (arg.startsWith("-")) {
      throw new Error(`Unknown option: ${arg}`);
    } else {
      positional.push(arg);
    }
  }
  if (!options.query && positional.length > 0) options.query = positional.join(" ");
  if (!options.includeCurrent && process.env.CODEX_THREAD_ID) options.excludeThreadIds.push(process.env.CODEX_THREAD_ID);
  if (options.hydrate === null) options.hydrate = options.roots.length === 0;
  if (!["exact", "prefix", "contains"].includes(options.cwdMode)) throw new Error("--cwd-mode must be exact, prefix, or contains.");
  return options;
}

async function main() {
  let options;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    printUsage();
    process.exitCode = 2;
    return;
  }
  if (options.help) {
    printUsage();
    return;
  }
  if (!options.query) {
    console.error("A query is required.");
    printUsage();
    process.exitCode = 2;
    return;
  }
  try {
    const report = await searchThreads(options);
    console.log(options.json ? JSON.stringify(report, null, 2) : formatHumanReport(report));
  } catch (error) {
    console.error(`Thread search failed: ${error.stack || error.message}`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
