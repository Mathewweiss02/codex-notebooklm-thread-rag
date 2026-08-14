import assert from "node:assert/strict";
import test from "node:test";
import { localDay, localizeEvents, TEMPORAL_LOCAL_DAY_CONTRACT } from "../scripts/thread_temporal_localize.mjs";

test("local-day conversion uses ICU and crosses midnight correctly", () => {
  assert.equal(TEMPORAL_LOCAL_DAY_CONTRACT, "temporal-local-day-v1");
  assert.equal(localDay("2026-02-02T04:55:00.000Z", "America/New_York"), "2026-02-01");
  assert.equal(localDay("2026-02-02T05:05:00.000Z", "America/New_York"), "2026-02-02");
  assert.deepEqual(localizeEvents([
    { eventId: "a", timestampUtc: "2026-11-01T05:30:00.000Z" },
    { eventId: "b", timestampUtc: "2026-11-01T06:30:00.000Z" },
  ], "America/New_York"), [
    { eventId: "a", localDate: "2026-11-01" },
    { eventId: "b", localDate: "2026-11-01" },
  ]);
});

test("local-day conversion rejects an invalid timezone", () => {
  assert.throws(() => localDay("2026-02-02T05:05:00.000Z", "Not/AZone"), /INVALID_TIMEZONE/);
});
