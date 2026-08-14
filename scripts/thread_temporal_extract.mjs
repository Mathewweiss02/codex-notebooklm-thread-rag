#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createWriteStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, unlinkSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import {
  PROJECTION_POLICY_VERSION,
  readVisibleMessages,
  sha256,
} from "./notebooklm_thread_projection_lib.mjs";

export const TEMPORAL_EVENT_CONTRACT = "temporal-event-v1";

function usage() {
  return `Usage: node thread_temporal_extract.mjs --thread-manifest FILE --out FILE [options]

Options:
  --thread-manifest FILE  JSON array or {threads:[...]} with id, path, and updatedAt
  --out FILE              Atomic NDJSON handoff destination
  --include-subagents     Include explicitly requested subagent sources
  --file-retries N        Bounded retries for transient Windows file access (default: 4)
  --file-retry-delay-ms N Initial retry delay with exponential backoff (default: 100)
  --max-message-chars N   Match projection truncation ceiling
  --max-line-bytes N      Match projection line ceiling
`;
}

function parseArgs(argv) {
  const options = {
    manifest: null,
    out: null,
    includeSubagents: false,
    fileRetries: 4,
    fileRetryDelayMs: 100,
    maxMessageChars: 100_000,
    maxLineBytes: 8 * 1024 * 1024,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--thread-manifest") options.manifest = argv[++index];
    else if (arg === "--out") options.out = argv[++index];
    else if (arg === "--include-subagents") options.includeSubagents = true;
    else if (arg === "--file-retries") options.fileRetries = Number(argv[++index]);
    else if (arg === "--file-retry-delay-ms") options.fileRetryDelayMs = Number(argv[++index]);
    else if (arg === "--max-message-chars") options.maxMessageChars = Number(argv[++index]);
    else if (arg === "--max-line-bytes") options.maxLineBytes = Number(argv[++index]);
    else if (arg === "--help" || arg === "-h") {
      console.log(usage());
      process.exit(0);
    } else throw new Error(`Unknown argument: ${arg}`);
  }
  if (!options.manifest || !options.out) throw new Error("--thread-manifest and --out are required");
  if (!Number.isInteger(options.fileRetries) || options.fileRetries < 0 || options.fileRetries > 8) throw new Error("--file-retries must be an integer from 0 to 8");
  if (!Number.isInteger(options.fileRetryDelayMs) || options.fileRetryDelayMs < 1 || options.fileRetryDelayMs > 10_000) throw new Error("--file-retry-delay-ms must be an integer from 1 to 10000");
  if (!Number.isInteger(options.maxMessageChars) || options.maxMessageChars < 1) throw new Error("--max-message-chars must be a positive integer");
  if (!Number.isInteger(options.maxLineBytes) || options.maxLineBytes < 1) throw new Error("--max-line-bytes must be a positive integer");
  return options;
}

function loadManifest(manifestPath, includeSubagents = false) {
  const resolved = resolve(manifestPath);
  const data = JSON.parse(readFileSync(resolved, "utf8").replace(/^\uFEFF/, ""));
  const rows = Array.isArray(data) ? data : data?.threads;
  if (!Array.isArray(rows)) throw new Error("--thread-manifest must contain an array or {threads:[...]}");
  const base = dirname(resolved);
  const normalized = rows.map((thread) => {
    if (!thread?.id || !thread?.path || !Number.isFinite(thread?.updatedAt)) {
      throw new Error("Every manifest thread needs id, path, and numeric updatedAt");
    }
    const source = String(thread.source || "unknown");
    if (!thread.archived && /^subAgent/i.test(source) && !includeSubagents && !thread.include) return null;
    return {
      id: String(thread.id),
      path: resolve(base, String(thread.path)),
      canonicalPath: String(thread.canonicalPath || thread.path),
      updatedAt: Number(thread.updatedAt),
      archived: Boolean(thread.archived),
      source,
      workspaceLabel: String(thread.workspaceLabel || "unknown"),
      workspaceHash: thread.workspaceHash == null ? null : String(thread.workspaceHash),
    };
  }).filter(Boolean);
  normalized.sort((a, b) => a.id.localeCompare(b.id));
  return { path: resolved, threads: normalized };
}

function timestampUtc(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds) ? new Date(milliseconds).toISOString() : null;
}

function sourceKind(thread) {
  return thread.archived ? "archive" : "active";
}

function manifestDigest(manifest) {
  const canonical = manifest.threads.map((thread) => ({
    id: thread.id,
    updatedAt: thread.updatedAt,
    archived: thread.archived,
    source: thread.source,
    workspaceLabel: thread.workspaceLabel,
    workspaceHash: thread.workspaceHash,
    pathDigest: sha256(thread.canonicalPath || thread.path),
  }));
  return sha256(JSON.stringify(canonical));
}

async function fileDigest(file) {
  const hash = createHash("sha256");
  const input = (await import("node:fs")).createReadStream(file);
  for await (const chunk of input) hash.update(chunk);
  return hash.digest("hex");
}

function retryableFileError(error) {
  return new Set(["EACCES", "EBUSY", "EPERM", "EMFILE", "ENFILE"]).has(error?.code);
}

export async function withFileRetries(operation, options = {}) {
  const maxRetries = options.maxRetries ?? 4;
  const baseDelayMs = options.baseDelayMs ?? 100;
  let retries = 0;
  for (let attempt = 0; ; attempt += 1) {
    try {
      return { value: await operation(), retries };
    } catch (error) {
      if (!retryableFileError(error) || attempt >= maxRetries) throw error;
      retries += 1;
      await new Promise((resolve) => setTimeout(resolve, baseDelayMs * (2 ** attempt)));
    }
  }
}

function eventFor(thread, message, sourceFileDigest) {
  const normalizedTimestamp = timestampUtc(message.timestamp);
  const eventId = sha256([thread.id, message.role, normalizedTimestamp, message.text].join("\u0000"));
  return {
    recordType: "event",
    contractVersion: TEMPORAL_EVENT_CONTRACT,
    eventId,
    threadId: thread.id,
    role: message.role,
    timestampUtc: normalizedTimestamp,
    text: message.text,
    textDigest: sha256(message.text),
    sourceRef: {
      sourceKind: sourceKind(thread),
      sourceFileDigest,
      lineNumber: message.lineNumber,
    },
  };
}

function quarantineFor(thread, message, reason, sourceFileDigest) {
  return {
    recordType: "quarantine",
    contractVersion: TEMPORAL_EVENT_CONTRACT,
    threadId: thread.id,
    reason,
    sourceRef: {
      sourceKind: sourceKind(thread),
      sourceFileDigest,
      lineNumber: message.lineNumber,
    },
  };
}

async function writeLine(stream, value) {
  if (stream.write(`${JSON.stringify(value)}\n`, "utf8")) return;
  await once(stream, "drain");
}

export async function extractManifest(manifestPath, outPath, options = {}) {
  const manifest = loadManifest(manifestPath, Boolean(options.includeSubagents));
  const destination = resolve(outPath);
  mkdirSync(dirname(destination), { recursive: true });
  const temporary = `${destination}.tmp-${process.pid}-${Date.now()}`;
  const stream = createWriteStream(temporary, { encoding: "utf8" });
  const eventDigest = createHash("sha256");
  let eventCount = 0;
  let quarantineCount = 0;
  let malformedLines = 0;
  let overflowLines = 0;
  let overflowVisibleLines = 0;
  let duplicateMessages = 0;
  let fileRetryCount = 0;
  try {
    await writeLine(stream, {
      recordType: "header",
      contractVersion: TEMPORAL_EVENT_CONTRACT,
      policyVersion: PROJECTION_POLICY_VERSION,
      generatedAt: new Date().toISOString(),
      threadCount: manifest.threads.length,
      manifestDigest: manifestDigest(manifest),
      threadMetadata: Object.fromEntries(manifest.threads.map((thread) => [thread.id, {
        workspaceLabel: thread.workspaceLabel,
        workspaceHash: thread.workspaceHash,
        archived: thread.archived,
        source: thread.source,
      }])),
    });
    for (const thread of manifest.threads) {
      const scanned = await withFileRetries(async () => {
        if (!existsSync(thread.path)) throw new Error(`session-path-missing:${thread.id}`);
        const before = statSync(thread.path);
        const sourceFileDigest = await fileDigest(thread.path);
        const visible = await readVisibleMessages(thread.path, {
          maxMessageChars: options.maxMessageChars ?? 100_000,
          maxLineBytes: options.maxLineBytes ?? 8 * 1024 * 1024,
        });
        const after = statSync(thread.path);
        if (before.size !== after.size || before.mtimeMs !== after.mtimeMs) throw new Error(`source-changed-during-scan:${thread.id}`);
        return { visible, sourceFileDigest };
      }, {
        maxRetries: options.fileRetries ?? 4,
        baseDelayMs: options.fileRetryDelayMs ?? 100,
      });
      fileRetryCount += scanned.retries;
      const { visible, sourceFileDigest } = scanned.value;
      malformedLines += visible.stats.malformedLines;
      overflowLines += visible.stats.overflowLines;
      overflowVisibleLines += visible.stats.overflowVisibleLines;
      duplicateMessages += visible.stats.duplicateMessages;
      if (visible.stats.overflowVisibleLines > 0) throw new Error(`visible-message-line-exceeded-limit:${thread.id}`);
      for (const message of visible.messages) {
        const normalizedTimestamp = timestampUtc(message.timestamp);
        const record = normalizedTimestamp
          ? eventFor(thread, message, sourceFileDigest)
          : quarantineFor(thread, message, message.timestamp ? "invalid-timestamp" : "missing-timestamp", sourceFileDigest);
        if (record.recordType === "event") {
          const line = `${JSON.stringify(record)}\n`;
          eventDigest.update(line, "utf8");
          eventCount += 1;
        } else quarantineCount += 1;
        await writeLine(stream, record);
      }
    }
    await writeLine(stream, {
      recordType: "trailer",
      contractVersion: TEMPORAL_EVENT_CONTRACT,
      eventCount,
      quarantineCount,
      malformedLines,
      overflowLines,
      overflowVisibleLines,
      duplicateMessages,
      fileRetryCount,
      eventDigest: eventDigest.digest("hex"),
    });
    stream.end();
    await once(stream, "finish");
    renameSync(temporary, destination);
  } catch (error) {
    stream.destroy();
    try { unlinkSync(temporary); } catch { /* best effort cleanup of an uncommitted handoff */ }
    throw error;
  }
  return { out: destination, threadCount: manifest.threads.length, eventCount, quarantineCount, malformedLines, overflowLines, overflowVisibleLines, duplicateMessages, fileRetryCount };
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  try {
    const options = parseArgs(process.argv.slice(2));
    const result = await extractManifest(options.manifest, options.out, options);
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error(error?.message || String(error));
    process.exitCode = 1;
  }
}
