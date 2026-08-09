#!/usr/bin/env node
import { spawn, execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, writeFileSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import {
  PROJECTION_POLICY_VERSION,
  classifyTaskExecution,
  projectionDueReason,
  readTaskLifecycle,
  readVisibleMessages,
  renderThreadProjection,
  sha256,
  sourceTitle,
} from "./notebooklm_thread_projection_lib.mjs";

const SOURCE_KINDS = ["cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview", "subAgentCompact", "subAgentThreadSpawn", "subAgentOther", "unknown"];
const SUBAGENT_SOURCE_KINDS = new Set(["subAgent", "subAgentReview", "subAgentCompact", "subAgentThreadSpawn", "subAgentOther"]);

function timestampSlug() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function safeDevice(value) {
  return String(value || "unknown-device").toLocaleLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "unknown-device";
}

function defaultRoot(device) {
  const home = process.env.CODEX_HOME || join(process.env.USERPROFILE || process.env.HOME || ".", ".codex");
  return join(home, "thread-rag", safeDevice(device));
}

function parseArgs(argv) {
  const device = safeDevice(process.env.CODEX_THREAD_RAG_DEVICE || process.env.COMPUTERNAME || "unknown-device");
  const options = {
    device,
    outDir: null,
    limit: null,
    threads: [],
    quietMinutes: 60,
    hardMaxHours: 6,
    openTurnStaleHours: 24,
    maxWords: 120_000,
    maxMessageChars: 100_000,
    maxLineBytes: 4 * 1024 * 1024,
    threadManifest: null,
    includeSubagents: false,
    force: false,
    dryRun: false,
    fast: true,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") {
      printUsage();
      process.exit(0);
    } else if (arg === "--device") options.device = safeDevice(argv[++index]);
    else if (arg === "--out") options.outDir = argv[++index];
    else if (arg === "--limit") options.limit = Number(argv[++index]);
    else if (arg === "--thread") options.threads.push(argv[++index]);
    else if (arg === "--quiet-minutes") options.quietMinutes = Number(argv[++index]);
    else if (arg === "--hard-max-hours") options.hardMaxHours = Number(argv[++index]);
    else if (arg === "--open-turn-stale-hours") options.openTurnStaleHours = Number(argv[++index]);
    else if (arg === "--max-words") options.maxWords = Number(argv[++index]);
    else if (arg === "--max-message-chars") options.maxMessageChars = Number(argv[++index]);
    else if (arg === "--max-line-bytes") options.maxLineBytes = Number(argv[++index]);
    else if (arg === "--thread-manifest") options.threadManifest = resolve(argv[++index]);
    else if (arg === "--include-subagents") options.includeSubagents = true;
    else if (arg === "--force") options.force = true;
    else if (arg === "--dry-run") options.dryRun = true;
    else if (arg === "--scan-repair") options.fast = false;
    else throw new Error(`Unknown argument: ${arg}`);
  }
  options.outDir = resolve(options.outDir || defaultRoot(options.device));
  if (!Number.isFinite(options.quietMinutes) || options.quietMinutes < 0) throw new Error("--quiet-minutes must be >= 0");
  if (!Number.isFinite(options.hardMaxHours) || options.hardMaxHours <= 0) throw new Error("--hard-max-hours must be > 0");
  if (!Number.isFinite(options.openTurnStaleHours) || options.openTurnStaleHours <= 0) throw new Error("--open-turn-stale-hours must be > 0");
  return options;
}

function printUsage() {
  console.log(`Usage: node notebooklm_thread_projection.mjs [options]

Builds an incremental, secret-redacted NotebookLM projection of Codex tasks.
It never uploads and never includes reasoning, tool calls/results, raw paths, or attachments.

Options:
  --device NAME          Stable device namespace (default: COMPUTERNAME)
  --out DIR              Projection/state directory
  --thread ID            Project one task id; repeatable
  --limit N              Consider at most N newest tasks
  --quiet-minutes N      Wait after last update before projecting (default: 60)
  --hard-max-hours N     Reproject a still-active changed task after N hours (default: 6)
  --open-turn-stale-hours N  Treat an unmatched task start as abandoned after N hours (default: 24)
  --max-words N          Maximum words per source part (default: 120000)
  --max-message-chars N  Keep first/last content beyond this size (default: 100000)
  --max-line-bytes N     Skip any JSONL line above this size (default: 4194304)
  --thread-manifest FILE Use an explicit thread metadata fixture instead of app-server
  --include-subagents    Include hidden worker/review sessions (excluded by default)
  --force                Ignore quiet/unchanged gates
  --dry-run              Report candidates without reading or writing projections
  --scan-repair          Ask Codex to scan/repair state rather than DB-only listing
`);
}

function cachedCodexCopy() {
  try {
    return readdirSync(tmpdir()).filter((name) => /^codex-app-.*\.exe$/i.test(name))
      .map((name) => join(tmpdir(), name)).sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs)[0];
  } catch { return undefined; }
}

function copiedExecutable(exe) {
  const st = statSync(exe);
  const copied = join(tmpdir(), `codex-app-${st.size}-${Math.trunc(st.mtimeMs)}.exe`);
  if (!existsSync(copied)) copyFileSync(exe, copied);
  return copied;
}

function latestBundledCodex() {
  if (process.env.CODEX_APP_CLI) return process.env.CODEX_APP_CLI;
  if (process.platform !== "win32") return process.env.CODEX_CLI || "codex";
  try {
    const bundled = execFileSync("where.exe", ["codex.exe"], { windowsHide: true }).toString().split(/\r?\n/)
      .map((line) => line.trim()).filter(Boolean)
      .find((line) => /\\WindowsApps\\OpenAI\.Codex_.*\\app\\resources\\codex\.exe$/i.test(line));
    if (bundled) return copiedExecutable(bundled);
  } catch { /* probe below */ }
  try {
    const root = "C:\\Program Files\\WindowsApps";
    for (const dir of readdirSync(root).filter((name) => /^OpenAI\.Codex_.*__2p2nqsd0c76g0$/.test(name)).sort().reverse()) {
      const exe = join(root, dir, "app", "resources", "codex.exe");
      if (existsSync(exe)) return copiedExecutable(exe);
    }
  } catch { /* cache/PATH below */ }
  return cachedCodexCopy() || process.env.CODEX_CLI || "codex";
}

class AppServerClient {
  constructor() { this.nextId = 2; this.pending = new Map(); this.buffer = ""; this.closed = false; }
  async start() {
    this.child = spawn(latestBundledCodex(), ["app-server", "--listen", "stdio://"], { stdio: ["pipe", "pipe", "pipe"], windowsHide: true });
    this.child.stdout.on("data", (chunk) => this.onData(chunk.toString()));
    this.child.stderr.on("data", () => {});
    this.child.on("close", () => { this.closed = true; this.rejectAll(new Error("Codex app-server closed.")); });
    await this.raw({ id: 1, method: "initialize", params: { clientInfo: { name: "codex-thread-rag", title: "Codex Thread RAG", version: "0.1.0" }, capabilities: { experimentalApi: true, optOutNotificationMethods: [] } } });
    this.send({ method: "initialized" });
  }
  send(value) { this.child.stdin.write(`${JSON.stringify(value)}\n`); }
  onData(chunk) {
    this.buffer += chunk;
    const lines = this.buffer.split(/\r?\n/);
    this.buffer = lines.pop() || "";
    for (const line of lines) {
      let message;
      try { message = JSON.parse(line); } catch { continue; }
      if (message.id === undefined || !this.pending.has(message.id)) continue;
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      clearTimeout(pending.timeout);
      if (message.error) pending.reject(new Error(JSON.stringify(message.error))); else pending.resolve(message.result);
    }
  }
  rejectAll(error) { for (const pending of this.pending.values()) { clearTimeout(pending.timeout); pending.reject(error); } this.pending.clear(); }
  raw(request, timeoutMs = 60_000) {
    return new Promise((accept, reject) => {
      const timeout = setTimeout(() => { this.pending.delete(request.id); reject(new Error(`Timed out: ${request.method}`)); }, timeoutMs);
      this.pending.set(request.id, { resolve: accept, reject, timeout });
      this.send(request);
    });
  }
  request(method, params = {}) { return this.raw({ id: this.nextId++, method, params }); }
  close() { if (!this.child || this.closed) return; this.child.stdin.end(); setTimeout(() => this.child.kill(), 250).unref?.(); }
}

async function listThreads(client, options) {
  const seen = new Map();
  for (const archived of [false, true]) {
    if (options.limit && seen.size >= options.limit) break;
    let cursor = null;
    do {
      const page = await client.request("thread/list", {
        cursor, limit: 100, sortKey: "updated_at", sortDirection: "desc", archived,
        sourceKinds: SOURCE_KINDS, useStateDbOnly: options.fast,
      });
      for (const thread of page.data || []) {
        if (!seen.has(thread.id)) seen.set(thread.id, { ...thread, archived });
        if (options.limit && seen.size >= options.limit) break;
      }
      if (options.limit && seen.size >= options.limit) break;
      cursor = page.nextCursor || null;
    } while (cursor);
  }
  let rows = [...seen.values()].filter((thread) => options.includeSubagents || !SUBAGENT_SOURCE_KINDS.has(thread.source)).sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  if (options.threads.length) {
    const wanted = new Set(options.threads);
    rows = rows.filter((thread) => wanted.has(thread.id) || [...wanted].some((id) => thread.id.startsWith(id)));
  }
  return rows;
}

function listThreadsFromManifest(options) {
  const value = readJson(options.threadManifest, null);
  const rows = Array.isArray(value) ? value : value?.threads;
  if (!Array.isArray(rows)) throw new Error("--thread-manifest must contain an array or {threads:[...]}.");
  const seen = new Set();
  const normalized = rows.map((thread) => {
    if (!thread?.id || !thread?.path || !Number.isFinite(thread?.updatedAt)) throw new Error("Every manifest thread needs id, path, and numeric updatedAt.");
    if (seen.has(thread.id)) throw new Error(`Duplicate manifest thread id: ${thread.id}`);
    seen.add(thread.id);
    return { archived: false, ...thread, path: resolve(thread.path) };
  });
  let selected = normalized.filter((thread) => options.includeSubagents || !SUBAGENT_SOURCE_KINDS.has(thread.source)).sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  if (options.threads.length) {
    selected = selected.filter((thread) => options.threads.some((id) => thread.id === id || thread.id.startsWith(id)));
  }
  if (options.limit) selected = selected.slice(0, options.limit);
  return selected;
}

function readJson(path, fallback) {
  try { return JSON.parse(readFileSync(path, "utf8")); } catch { return fallback; }
}

function atomicJson(path, value) {
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8" });
  renameSync(temporary, path);
}

function normalizePath(path) { return String(path || "").replace(/^\\\\\?\\/, ""); }

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const statePath = join(options.outDir, "state.json");
  const manifestPath = join(options.outDir, "manifest.json");
  const projectionsDir = join(options.outDir, "projections");
  const runsDir = join(options.outDir, "runs");
  const prior = readJson(statePath, { schemaVersion: 1, policyVersion: PROJECTION_POLICY_VERSION, deviceId: options.device, threads: {} });
  const client = options.threadManifest ? null : new AppServerClient();
  if (client) await client.start();
  const now = new Date();
  const nowMs = now.getTime();
  const run = { startedAt: now.toISOString(), deviceId: options.device, policyVersion: PROJECTION_POLICY_VERSION, dryRun: options.dryRun, counts: {}, tasks: [] };
  try {
    const threads = options.threadManifest ? listThreadsFromManifest(options) : await listThreads(client, options);
    run.counts.considered = threads.length;
    for (const thread of threads) {
      const previous = prior.threads?.[thread.id] || null;
      const unchanged = !options.force
        && previous
        && previous.inputUpdatedAt === thread.updatedAt
        && previous.inputName === thread.name
        && previous.policyVersion === PROJECTION_POLICY_VERSION;
      if (unchanged) { run.tasks.push({ threadId: thread.id, action: "unchanged" }); continue; }
      const path = normalizePath(thread.path);
      if (!path || !existsSync(path)) { run.tasks.push({ threadId: thread.id, action: "error", error: "session-path-missing" }); continue; }
      const lifecycle = await readTaskLifecycle(path, { maxLineBytes: options.maxLineBytes });
      thread.executionState = classifyTaskExecution(lifecycle, options, nowMs);
      if (client) {
        try {
          const result = await client.request("thread/goal/get", { threadId: thread.id });
          thread.goalStatus = result?.goal?.status || result?.status || null;
        } catch { thread.goalStatus = null; }
      }
      const reason = projectionDueReason(thread, previous, options, nowMs);
      if (!reason) { run.tasks.push({ threadId: thread.id, action: "unchanged" }); continue; }
      if (["active", "running-turn", "active-goal"].includes(reason)) {
        run.tasks.push({ threadId: thread.id, action: reason === "running-turn" ? "deferred-running-turn" : reason === "active-goal" ? "deferred-active-goal" : "deferred-active", updatedAt: thread.updatedAt });
        continue;
      }
      if (options.dryRun) { run.tasks.push({ threadId: thread.id, action: "would-project", reason }); continue; }
      const visible = await readVisibleMessages(path, { maxMessageChars: options.maxMessageChars, maxLineBytes: options.maxLineBytes });
      if (visible.stats.overflowVisibleLines > 0) {
        run.tasks.push({ threadId: thread.id, action: "error", error: "visible-message-line-exceeded-limit", overflowVisibleLines: visible.stats.overflowVisibleLines });
        continue;
      }
      const projection = renderThreadProjection(thread, visible, { deviceId: options.device, maxWords: options.maxWords });
      if (!options.force && previous?.contentDigest === projection.contentDigest && previous?.policyVersion === PROJECTION_POLICY_VERSION) {
        prior.threads[thread.id] = { ...previous, inputUpdatedAt: thread.updatedAt, inputName: thread.name, lastCheckedAt: now.toISOString() };
        run.tasks.push({ threadId: thread.id, action: "digest-unchanged", reason });
        continue;
      }
      const revision = (previous?.revision || 0) + 1;
      const threadDir = join(projectionsDir, thread.id);
      mkdirSync(threadDir, { recursive: true });
      const parts = projection.parts.map((part) => {
        const fileName = `r${String(revision).padStart(4, "0")}-p${String(part.part).padStart(3, "0")}.md`;
        const pathOut = join(threadDir, fileName);
        writeFileSync(pathOut, part.text, "utf8");
        return { part: part.part, totalParts: part.totalParts, file: pathOut, fileName, title: sourceTitle(projection, revision, part), words: part.words, bytes: part.bytes, sha256: sha256(part.text), sourceId: null, status: "projected" };
      });
      prior.threads[thread.id] = {
        threadId: thread.id,
        policyVersion: PROJECTION_POLICY_VERSION,
        inputUpdatedAt: thread.updatedAt,
        inputName: thread.name,
        inputFileSize: statSync(path).size,
        inputPathHash: sha256(path.toLocaleLowerCase()).slice(0, 16),
        contentDigest: projection.contentDigest,
        revision,
        title: projection.metadata.title,
        workspaceLabel: projection.metadata.workspaceLabel,
        workspaceHash: projection.metadata.workspaceHash,
        archived: projection.metadata.archived,
        forkedFromId: projection.metadata.forkedFromId,
        parentThreadId: projection.metadata.parentThreadId,
        lastProjectedAt: now.toISOString(),
        lastCheckedAt: now.toISOString(),
        lastUploadedAt: previous?.lastUploadedAt || null,
        notebookId: previous?.notebookId || null,
        previousSources: previous?.parts?.filter((part) => part.sourceId) || [],
        parts,
        stats: projection.stats,
      };
      run.tasks.push({ threadId: thread.id, action: "projected", reason, revision, parts: parts.length, messages: projection.stats.messages, redactions: projection.stats.redactions, overflowLines: projection.stats.overflowLines, overflowVisibleLines: projection.stats.overflowVisibleLines });
    }
    run.completedAt = new Date().toISOString();
    for (const action of ["unchanged", "deferred-active", "deferred-running-turn", "deferred-active-goal", "would-project", "digest-unchanged", "projected", "error"]) run.counts[action] = run.tasks.filter((task) => task.action === action).length;
    if (!options.dryRun) {
      mkdirSync(options.outDir, { recursive: true });
      mkdirSync(runsDir, { recursive: true });
      prior.schemaVersion = 1;
      prior.policyVersion = PROJECTION_POLICY_VERSION;
      prior.deviceId = options.device;
      prior.updatedAt = run.completedAt;
      atomicJson(statePath, prior);
      const manifest = {
        schemaVersion: 1,
        generatedAt: run.completedAt,
        deviceId: options.device,
        policyVersion: PROJECTION_POLICY_VERSION,
        threadCount: Object.keys(prior.threads).length,
        threads: Object.values(prior.threads).map((thread) => ({ threadId: thread.threadId, title: thread.title, revision: thread.revision, updatedAt: thread.inputUpdatedAt, lastProjectedAt: thread.lastProjectedAt, lastUploadedAt: thread.lastUploadedAt, parts: thread.parts })),
      };
      atomicJson(manifestPath, manifest);
      atomicJson(join(runsDir, `${timestampSlug()}.json`), run);
    }
    console.log(JSON.stringify({ outDir: options.outDir, ...run.counts }, null, 2));
  } finally { client?.close(); }
}

main().catch((error) => { console.error(error.stack || error.message); process.exit(1); });
