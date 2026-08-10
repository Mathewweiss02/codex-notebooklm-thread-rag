import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  PROJECTION_POLICY_VERSION,
  projectionDueReason,
  readVisibleMessages,
  renderThreadProjection,
  sanitizeSecrets,
  sourceTitle,
} from "./notebooklm_thread_projection_lib.mjs";

function event(timestamp, role, text) {
  return JSON.stringify({ timestamp, type: "response_item", payload: { type: "message", role, content: [{ type: "input_text", text }] } });
}

test("sanitizer redacts common durable credentials without removing ordinary order data", () => {
  const input = [
    "Order 26-12504 has 64,800 rows.",
    "AWS AKIA1234567890ABCDEF",
    "password=hunter-hunter",
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
    "https://alice:secretpass@example.com/path?access_token=topsecretvalue",
    "Root paths C:\\Users\\person and /home/person must not survive.",
    "Jammed path okayC:/Users/person/Downloads and WSL /mnt/c/Users/person/.codex must not survive.",
    "-----BEGIN PRIVATE KEY-----\nabcdef\n-----END PRIVATE KEY-----",
  ].join("\n");
  const result = sanitizeSecrets(input);
  assert.match(result.text, /Order 26-12504 has 64,800 rows/);
  assert.doesNotMatch(result.text, /AKIA1234567890ABCDEF|hunter-hunter|secretpass|topsecretvalue|BEGIN PRIVATE KEY|C:[\\/]Users[\\/]person|\/(?:Users?|home)\/person/);
  assert.match(result.text, /Root paths \[USERPROFILE\] and \[USERPROFILE\] must not survive/);
  assert.ok(Object.values(result.counts).reduce((sum, count) => sum + count, 0) >= 5);
});

test("projection contains visible messages and provenance but excludes tool traces and raw paths", async () => {
  const dir = await mkdtemp(join(tmpdir(), "thread-projection-test-"));
  const file = join(dir, "fixture.jsonl");
  const lines = [
    JSON.stringify({ timestamp: "2026-08-01T12:00:00Z", type: "session_meta", payload: { id: "thread-1", cwd: "C:\\Users\\person\\Secret Project" } }),
    event("2026-08-01T12:01:00Z", "user", "Find the Mike suppression-file instructions in C:\\Users\\person\\Secret Project. api_key=secretvalue123"),
    JSON.stringify({ timestamp: "2026-08-01T12:01:10Z", type: "response_item", payload: { type: "function_call_output", output: "tool-only private payload" } }),
    event("2026-08-01T12:02:00Z", "assistant", "The source task is Better Data files."),
    event("2026-08-01T12:02:00Z", "assistant", "The source task is Better Data files."),
    JSON.stringify({ timestamp: "2026-08-01T12:03:00Z", type: "response_item", payload: { type: "message", role: "developer", content: [{ text: "hidden developer policy" }] } }),
  ];
  await writeFile(file, `${lines.join("\n")}\n`, "utf8");
  const visible = await readVisibleMessages(file);
  assert.equal(visible.messages.length, 2);
  assert.equal(visible.stats.duplicateMessages, 1);
  const projected = renderThreadProjection({
    id: "019abcde-1111-2222-3333-444444444444",
    sessionId: "019abcde-1111-2222-3333-444444444444",
    name: "AWS suppression workflow",
    cwd: "C:\\Users\\person\\Secret Project",
    createdAt: 1785585600,
    updatedAt: 1785585720,
    archived: false,
  }, visible, { deviceId: "ADS-PC", maxWords: 1000 });
  const text = projected.parts[0].text;
  assert.match(text, /Thread ID: `019abcde/);
  assert.match(text, /Workspace: `Secret Project`/);
  assert.match(text, /Mike suppression-file instructions/);
  assert.match(text, /api_key=\[REDACTED\]/);
  assert.match(text, /Better Data files/);
  assert.doesNotMatch(text, /tool-only private payload|hidden developer policy|C:\\Users\\person/);
  assert.equal(projected.metadata.deviceId, "ads-pc");
  assert.equal(PROJECTION_POLICY_VERSION, "visible-messages-secrets-redacted-v4");
});

test("oversized messages and lines are bounded and projection splits deterministically", async () => {
  const dir = await mkdtemp(join(tmpdir(), "thread-projection-bounds-"));
  const file = join(dir, "fixture.jsonl");
  const hugeTool = JSON.stringify({ type: "response_item", payload: { type: "function_call_output", output: "x".repeat(20_000) } });
  const lines = [
    event("2026-08-01T12:00:00Z", "user", `alpha ${"a ".repeat(400)}`),
    hugeTool,
    event("2026-08-01T12:01:00Z", "assistant", `beta ${"b ".repeat(400)}`),
  ];
  await writeFile(file, `${lines.join("\n")}\n`, "utf8");
  const visible = await readVisibleMessages(file, { maxLineBytes: 5000, maxMessageChars: 350 });
  assert.equal(visible.stats.overflowLines, 1);
  assert.equal(visible.stats.overflowVisibleLines, 0);
  assert.equal(visible.messages.length, 2);
  assert.equal(visible.stats.redactions["large-base64"] || 0, 0);
  assert.ok(visible.messages.every((message) => message.truncated));
  const thread = { id: "thread-two", name: "Bounds", cwd: "C:\\Work", createdAt: 1, updatedAt: 2 };
  const first = renderThreadProjection(thread, visible, { deviceId: "test", maxWords: 80 });
  const second = renderThreadProjection(thread, visible, { deviceId: "test", maxWords: 80 });
  assert.ok(first.parts.length >= 2);
  assert.equal(first.contentDigest, second.contentDigest);
  assert.deepEqual(first.parts.map((part) => part.text), second.parts.map((part) => part.text));
});

test("default line ceiling accepts image-heavy visible messages while projecting text only", async () => {
  const dir = await mkdtemp(join(tmpdir(), "thread-projection-image-line-"));
  const file = join(dir, "fixture.jsonl");
  const record = {
    timestamp: "2026-08-01T12:00:00Z",
    type: "response_item",
    payload: {
      type: "message",
      role: "user",
      content: [
        { type: "input_text", text: "Keep this visible text." },
        { type: "input_image", image_url: `data:image/png;base64,${"A".repeat(4_500_000)}` },
      ],
    },
  };
  await writeFile(file, `${JSON.stringify(record)}\n`, "utf8");

  const visible = await readVisibleMessages(file);

  assert.equal(visible.messages.length, 1);
  assert.equal(visible.messages[0].text, "Keep this visible text.");
  assert.equal(visible.stats.overflowVisibleLines, 0);
  assert.equal(visible.stats.overflowLines, 0);
});

test("source titles stay unique when names and time-ordered id prefixes collide", () => {
  const part = { part: 1, totalParts: 1 };
  const first = { metadata: { deviceId: "ads-pc", title: "Repeated task", threadId: "019abcde-1111-7111-8111-111111111111" } };
  const second = { metadata: { deviceId: "ads-pc", title: "Repeated task", threadId: "019abcde-2222-7222-8222-222222222222" } };
  const long = { metadata: { deviceId: "ads-pc", title: "x".repeat(500), threadId: first.metadata.threadId } };

  assert.notEqual(sourceTitle(first, 1, part), sourceTitle(second, 1, part));
  assert.match(sourceTitle(first, 1, part), /\| [a-f0-9]{16} \| r0001 p1\/1$/);
  assert.match(sourceTitle(long, 42, part), /\| [a-f0-9]{16} \| r0042 p1\/1$/);
  assert.ok(sourceTitle(long, 42, part).length <= 190);
});

test("context-compaction records stay excluded while visible conversation history remains", async () => {
  const dir = await mkdtemp(join(tmpdir(), "thread-projection-compaction-"));
  const file = join(dir, "fixture.jsonl");
  const lines = [
    event("2026-08-01T12:00:00Z", "user", "Original instruction before compaction: preserve the blue cohort."),
    JSON.stringify({ timestamp: "2026-08-01T12:10:00Z", type: "compacted", payload: { summary: "hidden compacted context" } }),
    JSON.stringify({ timestamp: "2026-08-01T12:10:01Z", type: "response_item", payload: { type: "message", role: "developer", content: [{ text: "hidden context summary" }] } }),
    event("2026-08-01T12:20:00Z", "assistant", "Visible answer after compaction: blue cohort preserved."),
  ];
  await writeFile(file, `${lines.join("\n")}\n`, "utf8");
  const visible = await readVisibleMessages(file);
  assert.equal(visible.messages.length, 2);
  const projected = renderThreadProjection({ id: "compact-thread", name: "Compacted", updatedAt: 2 }, visible, { deviceId: "test" });
  const text = projected.parts.map((part) => part.text).join("\n");
  assert.match(text, /Original instruction before compaction/);
  assert.match(text, /Visible answer after compaction/);
  assert.doesNotMatch(text, /hidden compacted context|hidden context summary/);
});

test("incremental eligibility enforces unchanged, quiet, active, forced, and hard-ceiling gates", () => {
  const now = Date.parse("2026-08-07T12:00:00Z");
  const options = { force: false, quietMinutes: 60, hardMaxHours: 6 };
  const thread = { name: "Task", updatedAt: Date.parse("2026-08-07T11:30:00Z") / 1000 };
  const current = { inputUpdatedAt: thread.updatedAt, inputName: thread.name, policyVersion: PROJECTION_POLICY_VERSION, lastProjectedAt: "2026-08-07T10:00:00Z" };
  assert.equal(projectionDueReason(thread, current, options, now), null);
  assert.equal(projectionDueReason(thread, { ...current, inputUpdatedAt: thread.updatedAt - 1 }, options, now), "active");
  assert.equal(projectionDueReason({ ...thread, updatedAt: Date.parse("2026-08-07T10:30:00Z") / 1000 }, null, options, now), "quiet");
  assert.equal(projectionDueReason(thread, { ...current, inputUpdatedAt: thread.updatedAt - 1, lastProjectedAt: "2026-08-07T05:00:00Z" }, options, now), "hard-max");
  assert.equal(projectionDueReason(thread, null, { ...options, force: true }, now), "forced");
});
