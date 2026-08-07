import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  PROJECTION_POLICY_VERSION,
  readVisibleMessages,
  renderThreadProjection,
  sanitizeSecrets,
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
    "-----BEGIN PRIVATE KEY-----\nabcdef\n-----END PRIVATE KEY-----",
  ].join("\n");
  const result = sanitizeSecrets(input);
  assert.match(result.text, /Order 26-12504 has 64,800 rows/);
  assert.doesNotMatch(result.text, /AKIA1234567890ABCDEF|hunter-hunter|secretpass|topsecretvalue|BEGIN PRIVATE KEY/);
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
  assert.equal(PROJECTION_POLICY_VERSION, "visible-messages-secrets-redacted-v2");
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
