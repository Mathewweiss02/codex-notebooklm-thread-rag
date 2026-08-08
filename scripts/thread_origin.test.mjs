import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { discoverOrigins } from "./thread_origin_lib.mjs";

function row(timestamp, type, payload) { return JSON.stringify({ timestamp, type, payload }); }
function user(timestamp, text) { return row(timestamp, "response_item", { type: "message", role: "user", content: [{ type: "input_text", text }] }); }
function tool(timestamp, text) { return row(timestamp, "response_item", { type: "custom_tool_call_output", call_id: "call_source", output: [{ type: "input_text", text }] }); }
function legacyTool(timestamp, text) { return row(timestamp, "response_item", { type: "function_call_output", call_id: "call_legacy_source", output: [{ type: "input_text", text }] }); }

test("original supplied order outranks a later confirmation summary", async () => {
  const root = await mkdtemp(join(tmpdir(), "codex-origin-"));
  const id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const folder = join(root, "sessions");
  const path = join(folder, `rollout-${id}.jsonl`);
  await mkdir(folder, { recursive: true });
  const lines = [
    row("2026-07-16T10:00:00Z", "session_meta", { id, session_id: id, cwd: "C:\\Work\\Pixel", source: "vscode" }),
    user("2026-07-16T11:00:00Z", "Forwarded message\nFrom: client@example.com\nSubject: New lists to test\nPlease provide 5K frequent travelers and 5K high net worth consumers, plus airline, airport, and cruise C-level technology and marketing lists."),
    user("2026-07-16T15:00:00Z", "Mission Control confirmation summary: AirGuide needs 5K frequent travelers, 5K high net worth, airline, airport, cruise, technology, and marketing audiences. This is the controlling contract."),
  ];
  await writeFile(path, `${lines.join("\n")}\n`, "utf8");
  try {
    const report = await discoverOrigins({
      query: "5K frequent travelers high net worth airline airport cruise technology marketing",
      threadIds: [id],
      roots: [root],
      limit: 5,
      minCoverage: 0.35,
    });
    assert.equal(report.candidates[0].timestamp, "2026-07-16T11:00:00Z");
    assert.ok(report.candidates[0].sourceSignals.includes("forwarded-email"));
    assert.equal(report.candidates[0].retellingSignals.length, 0);
    assert.ok(report.candidates[1].retellingSignals.includes("mission-or-automation"));
    assert.match(report.candidates[0].messageSha256, /^[0-9a-f]{64}$/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("tool-returned source material can be authoritative without becoming a user turn", async () => {
  const root = await mkdtemp(join(tmpdir(), "codex-origin-tool-"));
  const id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const folder = join(root, "sessions");
  const path = join(folder, `rollout-${id}.jsonl`);
  await mkdir(folder, { recursive: true });
  const lines = [
    row("2026-07-16T10:00:00Z", "session_meta", { id, session_id: id, cwd: "C:\\Work\\Pixel", source: "vscode" }),
    tool("2026-07-16T11:00:00Z", "From: Scott@example.com\nSubject: counts\nNew Mexico full state foreclosures debt delinquency repo. Houston ZIP 77017. Need volume by select and grand total."),
    user("2026-07-16T15:00:00Z", "Mission Control summary: New Mexico foreclosure debt delinquency repo and Houston ZIP 77017 counts. This is the controlling contract."),
  ];
  await writeFile(path, `${lines.join("\n")}\n`, "utf8");
  try {
    const report = await discoverOrigins({
      query: "New Mexico foreclosure debt delinquency repo Houston ZIP 77017 volume select grand total",
      threadIds: [id], roots: [root], limit: 5, minCoverage: 0.35,
    });
    assert.equal(report.candidates[0].sourceKind, "tool");
    assert.equal(report.candidates[0].callId, "call_source");
    assert.ok(report.candidates[0].sourceSignals.includes("tool-source"));
    assert.equal(report.candidates[0].provenanceLayer, "original-source");
    assert.ok(report.candidates[1].retellingSignals.includes("mission-or-automation"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("structured email with 20K outranks a later 20,000 completion report", async () => {
  const root = await mkdtemp(join(tmpdir(), "codex-origin-gift-"));
  const id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
  const folder = join(root, "sessions");
  const path = join(folder, `rollout-${id}.jsonl`);
  await mkdir(folder, { recursive: true });
  const lines = [
    row("2026-07-16T10:00:00Z", "session_meta", { id, session_id: id, cwd: "C:\\Work\\Pixel", source: "vscode" }),
    legacyTool("2026-07-16T11:00:00Z", 'Outlook result: {"Subject":"Gift Card buyers","Sender":"Eric","Body":"In our data we have gift card buyers, grab those names based on this ZIP code list and see if you can get me 20K names.","Attachments":[{"FileName":"target zips.xlsx"}]}'),
    user("2026-07-17T11:00:00Z", "Can you pull 20K gift card buyers from the ZIPs in Eric's workbook?"),
    tool("2026-07-17T15:00:00Z", "Completed final deliverable summary: 20,000 gift-interest names selected from 2,820 ZIPs in Eric's workbook."),
  ];
  await writeFile(path, `${lines.join("\n")}\n`, "utf8");
  try {
    const report = await discoverOrigins({
      query: "gift card buyers 20000 Eric ZIP workbook names",
      threadIds: [id], roots: [root], limit: 5, minCoverage: 0.35,
    });
    assert.equal(report.candidates[0].timestamp, "2026-07-16T11:00:00Z");
    assert.equal(report.candidates[0].callId, "call_legacy_source");
    assert.equal(report.candidates[0].provenanceLayer, "original-source");
    assert.ok(report.candidates[0].matchedConcepts.includes("20,000"));
    assert.equal(report.candidates.at(-1).provenanceLayer, "downstream-summary");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("direct email record outranks a composite Markdown transcript containing the same order", async () => {
  const root = await mkdtemp(join(tmpdir(), "codex-origin-composite-"));
  const id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
  const folder = join(root, "sessions");
  const path = join(folder, `rollout-${id}.jsonl`);
  await mkdir(folder, { recursive: true });
  const order = "New Movers: run counts for five locations in about a 10-mile radius and include a distance column.";
  const lines = [
    row("2026-07-16T10:00:00Z", "session_meta", { id, session_id: id, cwd: "C:\\Work\\Pixel", source: "vscode" }),
    legacyTool("2026-07-16T11:00:00Z", `{"Subject":"FW: New Movers","Body":"${order}"}`),
    tool("2026-07-16T12:00:00Z", `## Assistant — 2026-07-16T11:30:00Z\nRecap summary\nForwarded message\n${order}`),
  ];
  await writeFile(path, `${lines.join("\n")}\n`, "utf8");
  try {
    const report = await discoverOrigins({
      query: "New Movers five locations 10-mile radius counts distance column",
      threadIds: [id], roots: [root], limit: 5, minCoverage: 0.35,
    });
    assert.equal(report.candidates[0].timestamp, "2026-07-16T11:00:00Z");
    assert.equal(report.candidates[0].provenanceLayer, "original-source");
    assert.equal(report.candidates[1].provenanceLayer, "downstream-summary");
    assert.ok(report.candidates[1].retellingSignals.includes("embedded-transcript"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
