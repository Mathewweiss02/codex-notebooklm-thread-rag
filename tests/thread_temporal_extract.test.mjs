import assert from "node:assert/strict";
import { execFile, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import test from "node:test";

const execFileAsync = promisify(execFile);
const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const EXTRACTOR = join(ROOT, "scripts", "thread_temporal_extract.mjs");

function message(timestamp, role, text) {
  const value = { type: "response_item", payload: { type: "message", role, content: [{ text }] } };
  if (timestamp !== undefined) value.timestamp = timestamp;
  return JSON.stringify(value);
}

async function makeManifest(root, threads) {
  const rows = [];
  for (const [index, thread] of threads.entries()) {
    const fileName = `session-${index}.jsonl`;
    await writeFile(join(root, fileName), `${thread.lines.join("\n")}\n`, "utf8");
    rows.push({
      id: thread.id,
      path: fileName,
      updatedAt: 1786507200 + index,
      archived: Boolean(thread.archived),
      source: thread.source || "appServer",
      ...(thread.workspaceLabel ? { workspaceLabel: thread.workspaceLabel } : {}),
      ...(thread.workspaceHash ? { workspaceHash: thread.workspaceHash } : {}),
    });
  }
  const manifest = join(root, "manifest.json");
  await writeFile(manifest, JSON.stringify({ threads: rows }), "utf8");
  return manifest;
}

async function runExtractor(manifest, out, extra = []) {
  return execFileAsync(process.execPath, [EXTRACTOR, "--thread-manifest", manifest, "--out", out, ...extra], { windowsHide: true });
}

async function readRecords(out) {
  return (await readFile(out, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
}

function trailerOf(records) {
  return records.find((record) => record.recordType === "trailer");
}

function eventsOf(records) {
  return records.filter((record) => record.recordType === "event");
}

test("emits parity-ready events and quarantine records atomically", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-"));
  try {
    const manifest = await makeManifest(root, [
      {
        id: "active-thread",
        lines: [
          message("2026-08-12T04:00:00Z", "user", "hello temporal index"),
          message("2026-08-12T04:00:00Z", "user", "hello temporal index"),
          message(undefined, "assistant", "missing timestamp"),
          message("not-a-timestamp", "assistant", "invalid timestamp"),
          message("2026-08-12T04:01:00Z", "developer", "hidden developer content"),
        ],
      },
      {
        id: "active-thread",
        archived: true,
        lines: [message("2026-08-12T04:00:00Z", "user", "hello temporal index")],
      },
    ]);
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const records = (await readFile(out, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    const events = records.filter((record) => record.recordType === "event");
    const quarantines = records.filter((record) => record.recordType === "quarantine");
    const trailer = records.find((record) => record.recordType === "trailer");
    assert.equal(records[0].recordType, "header");
    assert.equal(records[0].contractVersion, "temporal-event-v1");
    assert.equal(events.length, 2);
    assert.equal(quarantines.length, 2);
    assert.equal(trailer.eventCount, 2);
    assert.equal(trailer.quarantineCount, 2);
    assert.equal(trailer.duplicateMessages, 1);
    assert.equal(events[0].timestampUtc, "2026-08-12T04:00:00.000Z");
    assert.equal(events[0].eventId, events[1].eventId);
    assert.ok(records.every((record) => !JSON.stringify(record).includes(root)));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("indexes every visible message in a new session exactly once", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-new-session-"));
  try {
    const manifest = await makeManifest(root, [{
      id: "new-session",
      lines: [
        message("2026-08-12T04:00:00Z", "user", "first visible message"),
        message("2026-08-12T04:01:00Z", "assistant", "second visible message"),
      ],
    }]);
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const records = await readRecords(out);
    const events = eventsOf(records);
    assert.equal(events.length, 2);
    assert.deepEqual(events.map((record) => record.text), ["first visible message", "second visible message"]);
    assert.equal(trailerOf(records).eventCount, 2);
    assert.equal(trailerOf(records).quarantineCount, 0);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("keeps tool and reasoning payloads out of visible temporal events", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-hidden-payloads-"));
  try {
    const hiddenTool = JSON.stringify({ type: "response_item", payload: { type: "function_call", name: "search", arguments: "private" } });
    const hiddenReasoning = JSON.stringify({ type: "response_item", payload: { type: "reasoning", summary: "private chain" } });
    const manifest = await makeManifest(root, [{
      id: "hidden-payload-thread",
      lines: [hiddenTool, hiddenReasoning, message("2026-08-12T04:00:00Z", "user", "visible only")],
    }]);
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const records = await readRecords(out);
    const events = eventsOf(records);
    assert.equal(events.length, 1);
    assert.equal(events[0].text, "visible only");
    assert.equal(trailerOf(records).eventCount, 1);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("quarantines missing and invalid timestamps without assigning a day", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-timestamp-quarantine-"));
  try {
    const manifest = await makeManifest(root, [{
      id: "timestamp-quarantine-thread",
      lines: [
        message(undefined, "user", "missing timestamp"),
        message("not-a-timestamp", "assistant", "invalid timestamp"),
      ],
    }]);
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const records = await readRecords(out);
    assert.equal(eventsOf(records).length, 0);
    assert.deepEqual(records.filter((record) => record.recordType === "quarantine").map((record) => record.reason), ["missing-timestamp", "invalid-timestamp"]);
    assert.equal(trailerOf(records).quarantineCount, 2);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("preserves canonical identity when a thread moves from active to archive", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-archive-move-"));
  try {
    const manifest = join(root, "manifest.json");
    const source = join(root, "session.jsonl");
    await writeFile(source, `${message("2026-08-12T04:00:00Z", "user", "stable thread identity")}\n`, "utf8");
    await writeFile(manifest, JSON.stringify({ threads: [{ id: "moving-thread", path: "session.jsonl", updatedAt: 1786507200, archived: false }] }), "utf8");
    const activeOut = join(root, "active.jsonl");
    await runExtractor(manifest, activeOut);
    const activeEvent = eventsOf(await readRecords(activeOut))[0];

    await writeFile(manifest, JSON.stringify({ threads: [{ id: "moving-thread", path: "session.jsonl", updatedAt: 1786507201, archived: true }] }), "utf8");
    const archiveOut = join(root, "archive.jsonl");
    await runExtractor(manifest, archiveOut);
    const archiveEvent = eventsOf(await readRecords(archiveOut))[0];
    assert.equal(archiveEvent.eventId, activeEvent.eventId);
    assert.equal(archiveEvent.threadId, activeEvent.threadId);
    assert.equal(archiveEvent.sourceRef.sourceKind, "archive");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("does not publish a destination after a missing source failure", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-failure-"));
  try {
    const manifest = join(root, "manifest.json");
    await writeFile(manifest, JSON.stringify({ threads: [{ id: "missing", path: "missing.jsonl", updatedAt: 1786507200 }] }), "utf8");
    const out = join(root, "handoff.jsonl");
    await assert.rejects(runExtractor(manifest, out), /session-path-missing:missing/);
    assert.equal(existsSync(out), false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("carries path-free workspace metadata into the temporal handoff", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-metadata-"));
  try {
    const manifest = await makeManifest(root, [{
      id: "metadata-thread",
      workspaceLabel: "Hermes",
      workspaceHash: "abc123",
      lines: [message("2026-08-12T04:00:00Z", "user", "workspace metadata fixture")],
    }]);
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const records = (await readFile(out, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    assert.deepEqual(records[0].threadMetadata, {
      "metadata-thread": { workspaceLabel: "Hermes", workspaceHash: "abc123", archived: false, source: "appServer" },
    });
    assert.ok(!JSON.stringify(records[0]).includes(root));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("retries a transient Windows file lock and publishes one complete handoff", async (testContext) => {
  if (process.platform !== "win32") {
    testContext.skip("Windows sharing semantics are required for this failure-injection case");
    return;
  }
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-lock-"));
  let locker;
  try {
    const manifest = await makeManifest(root, [{ id: "locked-thread", lines: [message("2026-08-12T04:00:00Z", "user", "locked source retries safely")] }]);
    const source = join(root, "session-0.jsonl");
    const lockScript = join(root, "hold-lock.ps1");
    await writeFile(lockScript, [
      "param([string]$Path)",
      "$stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)",
      "[Console]::Out.WriteLine('locked')",
      "Start-Sleep -Milliseconds 900",
      "$stream.Dispose()",
    ].join("\n"), "utf8");
    locker = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", lockScript, source], {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("lock helper did not acquire the file")), 10_000);
      locker.stdout.on("data", (chunk) => {
        if (String(chunk).includes("locked")) {
          clearTimeout(timer);
          resolve();
        }
      });
      locker.once("error", reject);
      locker.once("exit", (code) => {
        if (code !== 0) reject(new Error("lock helper exited before signaling"));
      });
    });
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out, ["--file-retries", "4", "--file-retry-delay-ms", "100"]);
    const records = (await readFile(out, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    const trailer = records.find((record) => record.recordType === "trailer");
    assert.ok(trailer.fileRetryCount >= 1);
    assert.equal(trailer.eventCount, 1);
    assert.equal(records.filter((record) => record.recordType === "event").length, 1);
  } finally {
    if (locker && locker.exitCode === null) {
      locker.kill();
      await new Promise((resolve) => locker.once("close", resolve));
    }
    await rm(root, { recursive: true, force: true });
  }
});

test("blocks an oversized visible line instead of publishing a partial handoff", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-overflow-"));
  try {
    const manifest = await makeManifest(root, [{ id: "overflow", lines: [message("2026-08-12T04:00:00Z", "user", "x".repeat(500))] }]);
    const out = join(root, "handoff.jsonl");
    await assert.rejects(runExtractor(manifest, out, ["--max-line-bytes", "200"]), /visible-message-line-exceeded-limit:overflow/);
    assert.equal(existsSync(out), false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("accepts a Windows UTF-8 BOM in the manifest without copying it into output", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-bom-"));
  try {
    const manifest = await makeManifest(root, [{ id: "bom-thread", lines: [message("2026-08-12T04:00:00Z", "user", "bom input")] }]);
    const original = await readFile(manifest);
    await writeFile(manifest, Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), original]));
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const firstLine = (await readFile(out, "utf8")).split(/\r?\n/, 1)[0];
    assert.equal(JSON.parse(firstLine).recordType, "header");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("excludes subagent sources by default and includes them only with explicit opt-in", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-subagent-"));
  try {
    const manifest = await makeManifest(root, [
      {
        id: "subagent-thread",
        source: "subAgent",
        lines: [message("2026-08-12T04:00:00Z", "user", "subagent content")],
      },
    ]);
    const defaultOut = join(root, "default.jsonl");
    await runExtractor(manifest, defaultOut);
    const defaultRecords = (await readFile(defaultOut, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    assert.equal(defaultRecords.find((record) => record.recordType === "header").threadCount, 0);
    assert.equal(defaultRecords.find((record) => record.recordType === "trailer").eventCount, 0);

    const includedOut = join(root, "included.jsonl");
    await runExtractor(manifest, includedOut, ["--include-subagents"]);
    const includedRecords = (await readFile(includedOut, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    assert.equal(includedRecords.find((record) => record.recordType === "header").threadCount, 1);
    assert.equal(includedRecords.find((record) => record.recordType === "trailer").eventCount, 1);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("keeps valid events around malformed and partial lines with deterministic Unicode text", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-fuzz-"));
  try {
    const source = join(root, "session.jsonl");
    const unicodeText = "emoji 🔐 and bidi \u202E marker";
    await writeFile(
      source,
      `${message("2026-08-12T04:00:00Z", "user", "before malformed")}\n`+
        '{"type":"response_item","payload":{"type":"message","role":"user","content":[{"text":"unterminated"}]}' +
        `\n${message("2026-08-12T04:01:00Z", "assistant", unicodeText)}`,
      "utf8",
    );
    const manifest = join(root, "manifest.json");
    await writeFile(manifest, JSON.stringify({ threads: [{ id: "fuzz-thread", path: "session.jsonl", updatedAt: 1786507200, source: "appServer" }] }), "utf8");
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const records = (await readFile(out, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    const events = records.filter((record) => record.recordType === "event");
    const trailer = records.find((record) => record.recordType === "trailer");
    assert.equal(events.length, 2);
    assert.equal(trailer.malformedLines, 1);
    assert.equal(events[1].text, unicodeText);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("attributes a resumed old thread by message timestamp", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-resume-"));
  try {
    const manifest = await makeManifest(root, [{
      id: "resumed-old-thread",
      lines: [message("2026-08-14T04:00:00Z", "user", "resumed today")],
    }]);
    const manifestValue = JSON.parse(await readFile(manifest, "utf8"));
    manifestValue.threads[0].updatedAt = 946684800;
    await writeFile(manifest, JSON.stringify(manifestValue), "utf8");
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const records = (await readFile(out, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    const event = records.find((record) => record.recordType === "event");
    assert.equal(event.timestampUtc, "2026-08-14T04:00:00.000Z");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("preserves forked thread identity instead of merging parent content", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-fork-"));
  try {
    const manifest = await makeManifest(root, [
      { id: "parent-thread", lines: [message("2026-08-14T04:00:00Z", "user", "same content")] },
      { id: "fork-thread", lines: [message("2026-08-14T04:00:00Z", "user", "same content")] },
    ]);
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const records = (await readFile(out, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    const events = records.filter((record) => record.recordType === "event");
    assert.equal(events.length, 2);
    assert.notEqual(events[0].eventId, events[1].eventId);
    assert.deepEqual(new Set(events.map((record) => record.threadId)), new Set(["parent-thread", "fork-thread"]));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("excludes compaction summaries from temporal visible-message events", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-compaction-"));
  try {
    const compaction = JSON.stringify({ type: "response_item", payload: { type: "context_compaction", summary: "hidden summary" } });
    const manifest = await makeManifest(root, [{
      id: "compaction-thread",
      lines: [compaction, message("2026-08-14T04:00:00Z", "user", "visible message")],
    }]);
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const records = (await readFile(out, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    const events = records.filter((record) => record.recordType === "event");
    assert.equal(events.length, 1);
    assert.equal(events[0].text, "visible message");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("keeps same text at different timestamps as distinct events", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-temporal-extract-time-identity-"));
  try {
    const manifest = await makeManifest(root, [{
      id: "time-identity-thread",
      lines: [
        message("2026-08-14T04:00:00Z", "user", "same text"),
        message("2026-08-14T05:00:00Z", "user", "same text"),
      ],
    }]);
    const out = join(root, "handoff.jsonl");
    await runExtractor(manifest, out);
    const records = (await readFile(out, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    const events = records.filter((record) => record.recordType === "event");
    assert.equal(events.length, 2);
    assert.notEqual(events[0].eventId, events[1].eventId);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
