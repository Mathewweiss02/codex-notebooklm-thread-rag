import test from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { appendFile, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECTOR = resolve(HERE, "..", "scripts", "notebooklm_thread_projection.mjs");

function message(timestamp, role, text) {
  return JSON.stringify({ timestamp, type: "response_item", payload: { type: "message", role, content: [{ type: "input_text", text }] } });
}

async function runProjection(manifest, out) {
  return execFileAsync(process.execPath, [PROJECTOR, "--thread-manifest", manifest, "--out", out, "--device", "fixture-pc", "--quiet-minutes", "0", "--max-words", "35"], { windowsHide: true });
}

test("fixture projection survives compaction, splits deterministically, no-ops, and preserves old lineage on revision", async () => {
  const root = await mkdtemp(join(tmpdir(), "thread-rag-cli-"));
  const rollout = join(root, "rollout.jsonl");
  const manifest = join(root, "threads.json");
  const out = join(root, "projection");
  const oldUpdated = Math.floor(Date.now() / 1000) - 7200;
  const lines = [
    message("2026-08-01T12:00:00Z", "user", `Before compaction ${"alpha ".repeat(55)} api_key=secretvalue123`),
    JSON.stringify({ timestamp: "2026-08-01T12:01:00Z", type: "compacted", payload: { summary: "private compacted summary" } }),
    JSON.stringify({ timestamp: "2026-08-01T12:01:01Z", type: "response_item", payload: { type: "function_call_output", output: "private tool payload" } }),
    message("2026-08-01T12:02:00Z", "assistant", `After compaction ${"beta ".repeat(55)}`),
  ];
  await writeFile(rollout, `${lines.join("\n")}\n`, "utf8");
  const thread = {
    id: "019fixture-1111-2222-3333-444444444444",
    sessionId: "019fixture-1111-2222-3333-444444444444",
    forkedFromId: "019parent-0000-0000-0000-000000000000",
    name: "Fixture original",
    path: rollout,
    cwd: "C:\\Users\\someone\\Private Workspace",
    createdAt: oldUpdated - 100,
    updatedAt: oldUpdated,
  };
  const hiddenRollout = join(root, "hidden.jsonl");
  await writeFile(hiddenRollout, `${message("2026-08-01T12:00:00Z", "user", "copied parent context in a hidden worker")}\n`, "utf8");
  const hidden = { ...thread, id: "019hidden-1111-2222-3333-444444444444", sessionId: "019hidden-1111-2222-3333-444444444444", path: hiddenRollout, source: "subAgent" };
  await writeFile(manifest, JSON.stringify({ threads: [thread, hidden] }), "utf8");

  await runProjection(manifest, out);
  let state = JSON.parse(await readFile(join(out, "state.json"), "utf8"));
  assert.equal(Object.keys(state.threads).length, 1);
  assert.equal(state.threads[hidden.id], undefined);
  let projected = state.threads[thread.id];
  assert.equal(projected.revision, 1);
  assert.ok(projected.parts.length >= 2);
  assert.equal(projected.forkedFromId, thread.forkedFromId);
  const texts = await Promise.all(projected.parts.map((part) => readFile(part.file, "utf8")));
  const joined = texts.join("\n");
  assert.match(joined, /Before compaction/);
  assert.match(joined, /After compaction/);
  assert.doesNotMatch(joined, /secretvalue123|private compacted summary|private tool payload|C:\\Users\\someone/);

  projected.parts.forEach((part, index) => { part.sourceId = `old-source-${index + 1}`; part.status = "ready"; });
  projected.uploadRevision = 1;
  projected.uploadStatus = "ready";
  await writeFile(join(out, "state.json"), JSON.stringify(state, null, 2), "utf8");
  await runProjection(manifest, out);
  state = JSON.parse(await readFile(join(out, "state.json"), "utf8"));
  assert.equal(state.threads[thread.id].revision, 1);

  await appendFile(rollout, `${message("2026-08-01T12:03:00Z", "user", "New visible instruction after the prior projection.")}\n`, "utf8");
  thread.updatedAt = oldUpdated + 1;
  await writeFile(manifest, JSON.stringify({ threads: [thread, hidden] }), "utf8");
  await runProjection(manifest, out);
  state = JSON.parse(await readFile(join(out, "state.json"), "utf8"));
  projected = state.threads[thread.id];
  assert.equal(projected.revision, 2);
  assert.deepEqual(projected.previousSources.map((part) => part.sourceId), ["old-source-1", "old-source-2", "old-source-3", "old-source-4"] .slice(0, projected.previousSources.length));
  assert.ok(projected.previousSources.length >= 2);
});
