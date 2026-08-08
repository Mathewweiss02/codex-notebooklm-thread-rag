#!/usr/bin/env node
import { spawn } from "node:child_process";
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

function cachedCodexCopy() {
  try {
    const cached = readdirSync(tmpdir())
      .filter((name) => /^codex-app-.*\.exe$/i.test(name))
      .map((name) => join(tmpdir(), name))
      .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
    return cached[0];
  } catch {
    return undefined;
  }
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
    const lines = execFileSync("where.exe", ["codex.exe"], { windowsHide: true })
      .toString()
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const bundled = lines.find((line) => /\\WindowsApps\\OpenAI\.Codex_.*\\app\\resources\\codex\.exe$/i.test(line));
    if (bundled) return copiedExecutable(bundled);
  } catch {
    // Fall through to directory probing and cache.
  }

  const root = "C:\\Program Files\\WindowsApps";
  try {
    const dirs = readdirSync(root)
      .filter((name) => /^OpenAI\.Codex_.*__2p2nqsd0c76g0$/.test(name))
      .sort()
      .reverse();
    for (const dir of dirs) {
      const exe = join(root, dir, "app", "resources", "codex.exe");
      if (existsSync(exe)) return copiedExecutable(exe);
    }
  } catch {
    // Fall through to cache or PATH.
  }
  const cached = cachedCodexCopy();
  if (cached) return cached;
  return process.env.CODEX_CLI || "codex";
}

function normalizeRequests(value) {
  const items = Array.isArray(value) ? value : [value];
  return items.map((parsed, index) => {
    if (!parsed.method) throw new Error(`request ${index + 1} is missing method`);
    return { params: parsed.params ?? {}, ...parsed };
  });
}

function parseRequestText(text) {
  const trimmed = text.trim();
  if (!trimmed) return [];
  try {
    return normalizeRequests(JSON.parse(trimmed));
  } catch {
    return trimmed
      .split(/\r?\n/)
      .filter((line) => line.trim())
      .flatMap((line) => normalizeRequests(JSON.parse(line)));
  }
}

function parseRequests(argv) {
  if (argv.length === 0) {
    console.error("Usage: node app_server_rpc.mjs --stdin");
    console.error("       node app_server_rpc.mjs --file request.json");
    console.error("       node app_server_rpc.mjs --print-cli");
    console.error("       node app_server_rpc.mjs '<json request>' ['<json request>' ...]");
    console.error("Example: '{\"method\":\"thread/list\",\"params\":{\"limit\":5}}' | node app_server_rpc.mjs --stdin");
    process.exit(2);
  }
  const parsed =
    argv[0] === "--stdin"
      ? parseRequestText(readFileSync(0, "utf8"))
      : argv[0] === "--file"
        ? parseRequestText(readFileSync(argv[1], "utf8"))
        : argv.flatMap((raw) => parseRequestText(raw));
  return parsed.map((request, index) => ({ id: request.id ?? index + 2, ...request }));
}

if (process.argv[2] === "--print-cli") {
  console.log(latestBundledCodex());
  process.exit(0);
}

const requests = parseRequests(process.argv.slice(2));
const expectedIds = new Set([1, ...requests.map((r) => r.id)]);
const seenIds = new Set();
const exe = latestBundledCodex();
const child = spawn(exe, ["app-server", "--listen", "stdio://"], {
  stdio: ["pipe", "pipe", "pipe"],
  windowsHide: true,
  shell: /\.cmd$/i.test(exe),
});

let stdoutBuffer = "";
let stderrBuffer = "";
let initialized = false;
let done = false;

function send(obj) {
  child.stdin.write(`${JSON.stringify(obj)}\n`);
}

const timeout = setTimeout(() => {
  if (![...expectedIds].every((id) => seenIds.has(id))) {
    child.kill();
    process.exitCode = 124;
  }
}, 15000);
timeout.unref?.();

function maybeDone() {
  if (!done && [...expectedIds].every((id) => seenIds.has(id))) {
    done = true;
    clearTimeout(timeout);
    child.stdin.end();
    setTimeout(() => child.kill(), 250);
  }
}

child.on("error", (err) => {
  console.error(`Failed to start Codex app-server via ${exe}: ${err.message}`);
  process.exitCode = 1;
});

child.stdout.on("data", (chunk) => {
  stdoutBuffer += chunk.toString();
  const lines = stdoutBuffer.split(/\r?\n/);
  stdoutBuffer = lines.pop() ?? "";
  for (const line of lines) {
    if (!line.trim()) continue;
    console.log(line);
    try {
      const msg = JSON.parse(line);
      if (msg.id !== undefined) seenIds.add(msg.id);
      if (msg.id === 1 && !initialized) {
        initialized = true;
        send({ method: "initialized" });
        for (const req of requests) send(req);
      }
    } catch {
      // Keep non-JSON output visible.
    }
    maybeDone();
  }
});

child.stderr.on("data", (chunk) => {
  stderrBuffer += chunk.toString();
});

child.on("close", (code) => {
  if (stderrBuffer.trim()) process.stderr.write(stderrBuffer);
  const missing = [...expectedIds].filter((id) => !seenIds.has(id));
  if (missing.length > 0) {
    console.error(`Codex app-server closed before response id(s): ${missing.join(", ")}`);
    process.exitCode = process.exitCode || 1;
  }
  if (code !== 0 && code !== null) process.exitCode = code;
});

send({
  method: "initialize",
  id: 1,
  params: {
    clientInfo: {
      name: "codex-thread-ops",
      title: "Codex Thread Ops",
      version: "0.1.0",
    },
    capabilities: {
      experimentalApi: true,
      optOutNotificationMethods: [],
    },
  },
});
