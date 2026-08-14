import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { parseQuery, redactSensitiveText, searchThreads } from "./thread_search_lib.mjs";
import { formatCliError, localTodayBounds, parseArgs } from "./thread_search.mjs";

const FAKE_AWS_KEY = ["AKIA", "ABCDEFGHIJKLMNOP"].join("");
const FAKE_OPENAI_KEY = ["sk", "proj_abcdefghijklmnop"].join("-");

function meta(id, cwd, source = "vscode") {
  return {
    timestamp: "2026-01-01T00:00:00.000Z",
    type: "session_meta",
    payload: { id, session_id: id, timestamp: "2026-01-01T00:00:00.000Z", cwd, source },
  };
}

function message(timestamp, role, text) {
  return {
    timestamp,
    type: "response_item",
    payload: {
      type: "message",
      role,
      content: [{ type: role === "user" ? "input_text" : "output_text", text }],
    },
  };
}

async function writeThread(file, id, cwd, messages, source = "vscode") {
  await mkdir(join(file, ".."), { recursive: true });
  const rows = [meta(id, cwd, source), ...messages].map((row) => JSON.stringify(row)).join("\n");
  await writeFile(file, `${rows}\n`, "utf8");
}

async function makeFixture() {
  const root = await mkdtemp(join(tmpdir(), "codex-thread-search-"));
  const active = join(root, "sessions", "2026", "08", "03");
  const archived = join(root, "archived_sessions");
  const cwd = "C:\\Work\\Pixel";
  const targetId = "11111111-1111-4111-8111-111111111111";
  const decoyId = "22222222-2222-4222-8222-222222222222";
  const currentId = "33333333-3333-4333-8333-333333333333";
  const archiveId = "44444444-4444-4444-8444-444444444444";
  const recapId = "55555555-5555-4555-8555-555555555555";
  const weakId = "66666666-6666-4666-8666-666666666666";

  await writeThread(join(active, `rollout-${targetId}.jsonl`), targetId, cwd, [
    message("2026-08-01T00:26:21.000Z", "assistant", "Michelle copied 420 DentalPlans suppression files into Mike's private Files.com SFTP route."),
    message("2026-08-03T19:47:03.000Z", "user", "Can we upload those files into our AWS bucket or S3?"),
    message("2026-08-03T20:08:46.000Z", "assistant", `The AWS S3 upload passed. access_key=${FAKE_AWS_KEY} and all source checksums matched.`),
  ]);

  await writeThread(join(active, `rollout-${decoyId}.jsonl`), decoyId, cwd, [
    message("2026-01-01T00:00:00.000Z", "user", "AWS architecture notes."),
    message("2026-02-15T00:00:00.000Z", "assistant", "Mike reviewed an unrelated report."),
    message("2026-04-01T00:00:00.000Z", "user", "VendorData contract discussion."),
    message("2026-05-20T00:00:00.000Z", "assistant", "Michelle joined another project."),
    message("2026-07-01T00:00:00.000Z", "user", "SFTP maintenance."),
    message("2026-08-01T00:00:00.000Z", "assistant", "Suppression policy notes."),
    message("2026-09-20T00:00:00.000Z", "assistant", "Uploaded a logo."),
  ]);

  await writeThread(join(active, `rollout-${currentId}.jsonl`), currentId, cwd, [
    message("2026-08-07T12:00:00.000Z", "user", "Find the AWS suppression file from Mike and Michelle uploaded through VendorData SFTP."),
  ]);

  await writeThread(join(active, `rollout-${recapId}.jsonl`), recapId, cwd, [
    message("2026-08-06T12:00:00.000Z", "assistant", "The pieces I remember are that Mike and Michelle had an AWS suppression upload through the SFTP route."),
  ]);

  await writeThread(join(active, `rollout-${weakId}.jsonl`), weakId, cwd, [
    message("2026-08-05T12:00:00.000Z", "assistant", "Scrapy uses an asyncio reactor on this platform."),
  ]);

  await writeThread(join(archived, `rollout-target-copy-${targetId}.jsonl`), targetId, cwd, [
    message("2026-08-01T00:26:21.000Z", "assistant", "Michelle copied suppression files into Mike's SFTP route."),
  ]);

  await writeThread(join(archived, `rollout-${archiveId}.jsonl`), archiveId, "C:\\Work\\Other", [
    message("2026-08-02T00:00:00.000Z", "user", "An archived Michelle suppression note."),
  ]);
  return { root, cwd, targetId, decoyId, currentId, archiveId, recapId, weakId };
}

test("query parsing builds useful concepts and aliases", () => {
  const parsed = parseQuery("AWS suppression file from Mike and Michelle uploaded to VendorData SFTP");
  const ids = new Set(parsed.concepts.map((concept) => concept.id));
  for (const expected of ["aws", "suppression", "mike", "upload", "vendordata", "sftp", "term-michelle"]) {
    assert.ok(ids.has(expected), `missing concept ${expected}`);
  }
});

test("query parsing normalizes small numbers and preservation intent", () => {
  const parsed = parseQuery("keep the styling unchanged across five pages");
  const ids = new Set(parsed.concepts.map((concept) => concept.id));
  assert.ok(ids.has("number-5"));
  assert.ok(ids.has("preserve"));
  assert.ok(parsed.concepts.find((concept) => concept.id === "number-5").weight < 0.5);
  const preserve = parsed.concepts.find((concept) => concept.id === "preserve");
  assert.ok(preserve.jsRegex.test("The styling must not change."));
});

test("today expands to the machine-local calendar day and rejects mixed bounds", () => {
  const now = new Date(2026, 7, 10, 15, 30, 0, 0);
  const bounds = localTodayBounds(now);
  const start = new Date(bounds.after);
  const end = new Date(bounds.before);
  assert.equal(start.getFullYear(), 2026);
  assert.equal(start.getMonth(), 7);
  assert.equal(start.getDate(), 10);
  assert.equal(start.getHours(), 0);
  assert.equal(end.getFullYear(), 2026);
  assert.equal(end.getMonth(), 7);
  assert.equal(end.getDate(), 10);
  assert.equal(end.getHours(), 23);
  assert.equal(end.getMinutes(), 59);
  assert.equal(end.getSeconds(), 59);
  assert.equal(end.getMilliseconds(), 999);

  const options = parseArgs(["--query", "what was I doing", "--today"], { now });
  assert.equal(options.after, bounds.after);
  assert.equal(options.before, bounds.before);
  assert.throws(
    () => parseArgs(["--query", "work", "--today", "--after", "2026-08-01"]),
    /cannot be combined/,
  );
});

test("search ranks a coherent event over a giant scattered decoy and collapses archive duplicates", async () => {
  const fixture = await makeFixture();
  try {
    const report = await searchThreads({
      query: "AWS suppression file from Mike and Michelle uploaded to VendorData SFTP",
      roots: [fixture.root],
      cwd: fixture.cwd,
      excludeThreadIds: [fixture.currentId],
      hydrate: false,
      limit: 10,
      excerpts: 3,
      windowDays: 7,
    });
    assert.equal(report.results[0].id, fixture.targetId);
    assert.equal(report.results.filter((result) => result.id === fixture.targetId).length, 1);
    assert.ok(report.results[0].score > report.results[1].score);
    assert.ok(!JSON.stringify(report).includes(FAKE_AWS_KEY));
    const secretReport = await searchThreads({
      query: "AWS S3 upload checksum",
      roots: [fixture.root],
      cwd: fixture.cwd,
      hydrate: false,
      limit: 3,
      excerpts: 2,
    });
    assert.ok(secretReport.results[0].evidence.some((item) => item.excerpt.includes("REDACTED")));
    assert.ok(!JSON.stringify(secretReport).includes(FAKE_AWS_KEY));
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("source event outranks a later remembered retelling and weak single hits abstain", async () => {
  const fixture = await makeFixture();
  try {
    const sourceReport = await searchThreads({
      query: "AWS suppression upload Mike Michelle SFTP",
      roots: [fixture.root],
      cwd: fixture.cwd,
      excludeThreadIds: [fixture.currentId],
      hydrate: false,
      limit: 10,
    });
    assert.equal(sourceReport.results[0].id, fixture.targetId);
    const weakReport = await searchThreads({
      query: "xylophonic quetzal zz99 marmalade reactor",
      roots: [fixture.root],
      hydrate: false,
    });
    assert.equal(weakReport.results.length, 0);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("candidate-only ranking scans and returns only explicitly included tasks", async () => {
  const fixture = await makeFixture();
  try {
    const report = await searchThreads({
      query: "AWS suppression upload Mike Michelle SFTP",
      roots: [fixture.root],
      includeThreadIds: [fixture.targetId, fixture.recapId],
      hydrate: false,
      limit: 5,
      minScore: 0,
    });
    assert.deepEqual(new Set(report.filters.includedThreadIds), new Set([fixture.targetId, fixture.recapId]));
    assert.equal(report.results[0].id, fixture.targetId);
    assert.ok(report.results.every((result) => [fixture.targetId, fixture.recapId].includes(result.id)));
    assert.ok(report.stats.filesSearched <= 3, `candidate-only search unexpectedly scanned ${report.stats.filesSearched} files`);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("focused conversation outranks same-day clues scattered across many messages", async () => {
  const root = await mkdtemp(join(tmpdir(), "codex-thread-coherence-"));
  const cwd = "C:\\Work\\Orders";
  const targetId = "77777777-7777-4777-8777-777777777777";
  const decoyId = "88888888-8888-4888-8888-888888888888";
  const subagentId = "99999999-9999-4999-8999-999999999999";
  try {
    await writeThread(join(root, "sessions", `rollout-${targetId}.jsonl`), targetId, cwd, [
      message("2026-06-18T12:00:00.000Z", "user", "Process the batch of seventeen AAA scheduled orders and verify every phone number hyperlink against protocol."),
      message("2026-06-18T12:10:00.000Z", "assistant", "Verified the AAA order batch and completed the hyperlink checks."),
    ]);
    const scattered = ["17 fetches", "batch processing", "AAA batteries", "scheduled scrape", "purchase orders", "verify output", "phone directory", "number counts", "hyperlinks on profiles", "network protocol"];
    await writeThread(join(root, "sessions", `rollout-${decoyId}.jsonl`), decoyId, cwd,
      scattered.map((text, index) => message(`2026-06-18T13:${String(index).padStart(2, "0")}:00.000Z`, index % 2 ? "assistant" : "user", text)));
    await writeThread(join(root, "sessions", `rollout-${subagentId}.jsonl`), subagentId, cwd, [
      message("2026-06-18T13:30:00.000Z", "user", "Batch of seventeen AAA scheduled orders verify phone number hyperlinks protocol."),
    ], { subAgent: { other: "guardian" } });
    const report = await searchThreads({
      query: "batch of seventeen AAA scheduled orders verify phone number hyperlinks protocol",
      roots: [root],
      cwd,
      hydrate: false,
      limit: 5,
    });
    assert.equal(report.results[0].id, targetId);
    assert.ok(!report.results.some((result) => result.id === subagentId));
    assert.ok(report.results[0].coverage.windowCoherence > report.results[1].coverage.windowCoherence);
    const forensic = await searchThreads({
      query: "batch of seventeen AAA scheduled orders verify phone number hyperlinks protocol",
      roots: [root],
      cwd,
      hydrate: false,
      includeSubagents: true,
      limit: 5,
    });
    assert.ok(forensic.results.some((result) => result.id === subagentId));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("workspace, date, and archive filters remain deterministic", async () => {
  const fixture = await makeFixture();
  try {
    const active = await searchThreads({
      query: "Michelle suppression",
      roots: [fixture.root],
      cwd: fixture.cwd,
      archivedMode: "active",
      hydrate: false,
      excludeThreadIds: [fixture.currentId],
    });
    assert.ok(active.results.every((result) => !result.archived));
    const archived = await searchThreads({
      query: "Michelle suppression",
      roots: [fixture.root],
      archivedMode: "archived",
      hydrate: false,
      includeCurrent: true,
    });
    assert.ok(archived.results.length > 0);
    assert.ok(archived.results.every((result) => result.archived));
    const future = await searchThreads({
      query: "Michelle suppression",
      roots: [fixture.root],
      after: "2027-01-01T00:00:00Z",
      hydrate: false,
    });
    assert.equal(future.results.length, 0);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("current thread inclusion is excluded by default and explicit when requested", async () => {
  const fixture = await makeFixture();
  const previous = process.env.CODEX_THREAD_ID;
  process.env.CODEX_THREAD_ID = fixture.currentId;
  try {
    const defaultOptions = parseArgs([
      "--query", "Find the AWS suppression file from Mike and Michelle uploaded through VendorData SFTP",
      "--root", fixture.root,
      "--no-hydrate",
    ]);
    assert.deepEqual(defaultOptions.excludeThreadIds, [fixture.currentId]);
    const defaultReport = await searchThreads(defaultOptions);
    assert.ok(!defaultReport.results.some((result) => result.id === fixture.currentId));

    const explicitOptions = parseArgs([
      "--query", "Find the AWS suppression file from Mike and Michelle uploaded through VendorData SFTP",
      "--root", fixture.root,
      "--no-hydrate",
      "--include-current",
    ]);
    assert.deepEqual(explicitOptions.excludeThreadIds, []);
    const explicitReport = await searchThreads(explicitOptions);
    assert.ok(explicitReport.results.some((result) => result.id === fixture.currentId));
  } finally {
    if (previous === undefined) delete process.env.CODEX_THREAD_ID;
    else process.env.CODEX_THREAD_ID = previous;
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("redaction covers common credential shapes", () => {
  const bearer = ["Bear", "er"].join("");
  const redacted = redactSensitiveText(`${bearer} abcdefghijklmnop token=supersecret ${FAKE_AWS_KEY} ${FAKE_OPENAI_KEY}`);
  assert.ok(!redacted.includes("abcdefghijklmnop"));
  assert.ok(!redacted.includes("supersecret"));
  assert.ok(!redacted.includes(FAKE_AWS_KEY));
});

test("CLI errors redact sensitive query material before printing", () => {
  const secret = `${FAKE_AWS_KEY} token=supersecret`;
  const rendered = formatCliError(new Error(`remote query failed for ${secret}`));
  assert.ok(!rendered.includes(FAKE_AWS_KEY));
  assert.ok(!rendered.includes("supersecret"));
  assert.match(rendered, /REDACTED/);
});
