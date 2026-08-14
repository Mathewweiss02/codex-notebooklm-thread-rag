import assert from "node:assert/strict";
import test from "node:test";
import { resolveExpression } from "../scripts/thread_temporal_resolve.mjs";

const NEW_YORK = "America/New_York";

test("resolves today, yesterday, and rolling durations with one captured now", () => {
  const now = "2026-08-12T16:00:00.000Z";
  const today = resolveExpression({ expression: "today", timezone: NEW_YORK, now });
  assert.equal(today.startUtc, "2026-08-12T04:00:00.000Z");
  assert.equal(today.endUtc, now);
  assert.equal(today.boundary, "half-open [start,end)");
  const yesterday = resolveExpression({ expression: "yesterday", timezone: NEW_YORK, now });
  assert.equal(yesterday.startUtc, "2026-08-11T04:00:00.000Z");
  assert.equal(yesterday.endUtc, "2026-08-12T04:00:00.000Z");
  const rolling = resolveExpression({ expression: "past 24 hours", timezone: NEW_YORK, now });
  assert.equal(rolling.startUtc, "2026-08-11T16:00:00.000Z");
  assert.equal(rolling.endUtc, now);
  assert.equal(rolling.durationSeconds, 86400);
});

test("resolves calendar weeks, explicit dates, and future dates", () => {
  const now = "2026-08-12T16:00:00.000Z";
  const lastWeek = resolveExpression({ expression: "last week", timezone: NEW_YORK, now });
  assert.equal(lastWeek.startUtc, "2026-08-03T04:00:00.000Z");
  assert.equal(lastWeek.endUtc, "2026-08-10T04:00:00.000Z");
  const weekToDate = resolveExpression({ expression: "week to date", timezone: NEW_YORK, now });
  assert.equal(weekToDate.startUtc, "2026-08-10T04:00:00.000Z");
  assert.equal(weekToDate.endUtc, now);
  const explicit = resolveExpression({ expression: "2026-08-12", timezone: NEW_YORK, now });
  assert.equal(explicit.startUtc, "2026-08-12T04:00:00.000Z");
  assert.equal(explicit.endUtc, "2026-08-13T04:00:00.000Z");
  const future = resolveExpression({ expression: "tomorrow", timezone: NEW_YORK, now });
  assert.equal(future.future, true);
  assert.equal(future.expectedActivity, "empty-unless-now-advances");
});

test("preserves 23-hour spring-forward and 25-hour fall-back calendar days", () => {
  const spring = resolveExpression({ expression: "yesterday", timezone: NEW_YORK, now: "2026-03-09T16:00:00.000Z" });
  assert.equal(spring.startUtc, "2026-03-08T05:00:00.000Z");
  assert.equal(spring.endUtc, "2026-03-09T04:00:00.000Z");
  assert.equal(spring.durationSeconds, 23 * 3600);
  const fall = resolveExpression({ expression: "yesterday", timezone: NEW_YORK, now: "2026-11-02T17:00:00.000Z" });
  assert.equal(fall.startUtc, "2026-11-01T04:00:00.000Z");
  assert.equal(fall.endUtc, "2026-11-02T05:00:00.000Z");
  assert.equal(fall.durationSeconds, 25 * 3600);
});

test("rejects ambiguous, nonexistent, invalid, and backwards local ranges", () => {
  assert.throws(() => resolveExpression({ start: "2026-11-01 01:30", end: "2026-11-01 02:30", timezone: NEW_YORK, now: "2026-11-02T17:00:00.000Z" }), /AMBIGUOUS_LOCAL_TIME/);
  assert.throws(() => resolveExpression({ start: "2026-03-08 02:30", end: "2026-03-08 03:30", timezone: NEW_YORK, now: "2026-03-09T16:00:00.000Z" }), /NONEXISTENT_LOCAL_TIME/);
  assert.throws(() => resolveExpression({ expression: "sometime later", timezone: NEW_YORK, now: "2026-08-12T16:00:00.000Z" }), /INVALID_TIME_RANGE/);
  assert.throws(() => resolveExpression({ start: "2026-08-13", end: "2026-08-12", timezone: NEW_YORK, now: "2026-08-12T16:00:00.000Z" }), /INVALID_TIME_RANGE/);
  assert.throws(() => resolveExpression({ expression: "today", timezone: "Not/AZone", now: "2026-08-12T16:00:00.000Z" }), /INVALID_TIMEZONE/);
});

test("requires an explicit offset for repeated local time but accepts offset-bearing input", () => {
  const explicit = resolveExpression({
    start: "2026-11-01T01:30:00-04:00",
    end: "2026-11-01T02:30:00-05:00",
    timezone: NEW_YORK,
    now: "2026-11-02T17:00:00.000Z",
  });
  assert.equal(explicit.startUtc, "2026-11-01T05:30:00.000Z");
  assert.equal(explicit.endUtc, "2026-11-01T07:30:00.000Z");
});

test("allows an empty today range at exactly local midnight", () => {
  const result = resolveExpression({ expression: "today", timezone: NEW_YORK, now: "2026-08-12T04:00:00.000Z" });
  assert.equal(result.startUtc, result.endUtc);
  assert.equal(result.durationSeconds, 0);
});
