import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const fixturePath = resolve(process.argv[2] || dirname(fileURLToPath(import.meta.url)), process.argv[2] ? "" : "fixtures/oracle-fixtures.json");
const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));

function timestampMs(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function canonicalEvents(events) {
  const visible = events
    .filter((event) => (event.role === "user" || event.role === "assistant") && typeof event.text === "string" && event.text.trim())
    .map((event) => ({ ...event, timestampMs: timestampMs(event.timestamp) }))
    .filter((event) => event.timestampMs !== null);
  const sourceRank = { active: 0, archive: 1 };
  const selected = new Map();
  for (const event of visible) {
    const key = [event.threadId, event.role, event.timestamp, event.text].join("\u0000");
    const previous = selected.get(key);
    const rank = sourceRank[event.sourceKind] ?? 99;
    const previousRank = previous ? (sourceRank[previous.sourceKind] ?? 99) : 99;
    if (!previous || rank < previousRank || (rank === previousRank && event.recordId < previous.recordId)) selected.set(key, event);
  }
  return [...selected.values()].sort((a, b) => a.timestampMs - b.timestampMs || a.recordId.localeCompare(b.recordId));
}

function digest(value) {
  return createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex");
}

const canonical = canonicalEvents(fixture.events);
const results = fixture.cases.map((testCase) => {
  const start = timestampMs(testCase.start);
  const end = timestampMs(testCase.end);
  if (start === null || end === null || end <= start) throw new Error(`invalid case bounds: ${testCase.id}`);
  const actual = canonical.filter((event) => event.timestampMs >= start && event.timestampMs < end).map((event) => event.logicalId);
  const expected = [...testCase.expectedLogicalIds];
  const passed = JSON.stringify(actual) === JSON.stringify(expected);
  return { id: testCase.id, passed, actualCount: actual.length, expectedCount: expected.length, actual, expected };
});

const payload = {
  schemaVersion: fixture.schemaVersion,
  timezone: fixture.timezone,
  eventCount: fixture.events.length,
  canonicalVisibleTimestampedCount: canonical.length,
  caseCount: results.length,
  passedCases: results.filter((item) => item.passed).length,
  resultDigest: digest(results.map(({ id, passed, actualCount, expectedCount }) => ({ id, passed, actualCount, expectedCount }))),
};
console.log(JSON.stringify(payload, null, 2));
if (results.some((item) => !item.passed)) {
  console.error(JSON.stringify(results.filter((item) => !item.passed), null, 2));
  process.exitCode = 1;
}
