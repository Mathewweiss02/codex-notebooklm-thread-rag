#!/usr/bin/env node

import { mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { locateThreads } from "./thread_origin_lib.mjs";
import { workspaceIdentity } from "./notebooklm_thread_projection_lib.mjs";

function usage() {
  return `Usage:
  node thread_temporal_manifest.mjs --thread ID [--thread ID ...] --out FILE
  node thread_temporal_manifest.mjs --state FILE --out FILE

Options:
  --thread ID       Thread ID to locate; repeatable.
  --state FILE      Projection/index state JSON; use every state thread ID.
  --root PATH       Session root; repeatable. Defaults to Codex session roots.
  --allow-missing   Write found threads and report missing IDs instead of failing.
  --out FILE        Local path-bearing manifest for the temporal extractor.
`;
}

function parseArgs(argv) {
  const options = { threadIds: [], state: null, roots: [], allowMissing: false, out: null };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--thread") options.threadIds.push(String(argv[++index] || ""));
    else if (arg === "--state") options.state = resolve(argv[++index]);
    else if (arg === "--root") options.roots.push(resolve(argv[++index]));
    else if (arg === "--allow-missing") options.allowMissing = true;
    else if (arg === "--out") options.out = resolve(argv[++index]);
    else if (arg === "--help" || arg === "-h") { console.log(usage()); process.exit(0); }
    else throw new Error(`USAGE: unknown argument ${arg}`);
  }
  if (options.state && options.threadIds.length) throw new Error("USAGE: use --state or --thread, not both");
  if (!options.state && !options.threadIds.length) throw new Error("THREAD_SCOPE_REQUIRED: provide --state or --thread");
  if (!options.out) throw new Error("USAGE: --out is required");
  return options;
}

function readStateIds(path) {
  let parsed;
  try { parsed = JSON.parse(readFileSync(path, "utf8")); }
  catch (error) { throw new Error(`STATE_INVALID: ${error.message}`); }
  const threads = parsed?.threads;
  if (!threads || typeof threads !== "object" || Array.isArray(threads)) throw new Error("STATE_INVALID: state threads must be an object");
  const ids = Object.keys(threads).filter(Boolean).sort();
  if (!ids.length) throw new Error("THREAD_SCOPE_REQUIRED: state contains no threads");
  return ids;
}

function atomicJson(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  renameSync(temporary, path);
}

const options = parseArgs(process.argv.slice(2));
const ids = options.state ? readStateIds(options.state) : [...new Set(options.threadIds.filter(Boolean))].sort();
const roots = options.roots.length ? options.roots : undefined;
// locateThreads owns the default session/archive search roots.  Keep this
// utility's manifest contract aligned with that source of truth instead of
// passing an ignored third argument that could imply subagent coverage we have
// not independently proved.
const records = await locateThreads(ids, roots);
const found = new Map(records.map((record) => [record.id, record]));
const missing = ids.filter((id) => !found.has(id));
if (missing.length && !options.allowMissing) throw new Error(`THREAD_NOT_FOUND: ${missing.length} requested thread session file(s) could not be located`);

const threads = records
  .filter((record) => found.has(record.id))
  .map((record) => {
    const workspace = workspaceIdentity(record.cwd);
    return {
      id: record.id,
      path: record.path,
      canonicalPath: record.path,
      updatedAt: statSync(record.path).mtimeMs,
      archived: Boolean(record.archived),
      source: record.source || "unknown",
      workspaceLabel: workspace.label,
      workspaceHash: workspace.hash,
    };
  });
const manifest = { schemaVersion: 1, generatedAt: new Date().toISOString(), threadCount: threads.length, missingThreadCount: missing.length, threads };
atomicJson(options.out, manifest);
console.log(JSON.stringify({ status: missing.length ? "degraded" : "ok", requestedThreadCount: ids.length, foundThreadCount: threads.length, missingThreadCount: missing.length, output: options.out }));
