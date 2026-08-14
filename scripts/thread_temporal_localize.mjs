#!/usr/bin/env node

export const TEMPORAL_LOCAL_DAY_CONTRACT = "temporal-local-day-v1";

function assertTimezone(timeZone) {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone }).format();
  } catch {
    throw new Error(`INVALID_TIMEZONE: ${timeZone}`);
  }
}

function localFieldsAt(timestampUtc, timeZone) {
  const instant = new Date(timestampUtc);
  if (!Number.isFinite(instant.getTime())) throw new Error(`INVALID_TIMESTAMP: ${timestampUtc}`);
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    calendar: "gregory",
    numberingSystem: "latn",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hourCycle: "h23",
  });
  const fields = {};
  for (const part of formatter.formatToParts(instant)) {
    if (["year", "month", "day"].includes(part.type)) fields[part.type] = Number(part.value);
  }
  return fields;
}

export function localDay(timestampUtc, timeZone) {
  assertTimezone(timeZone);
  const fields = localFieldsAt(timestampUtc, timeZone);
  return `${String(fields.year).padStart(4, "0")}-${String(fields.month).padStart(2, "0")}-${String(fields.day).padStart(2, "0")}`;
}

export function localizeEvents(events, timeZone) {
  assertTimezone(timeZone);
  if (!Array.isArray(events)) throw new Error("INVALID_INPUT: events must be an array");
  return events.map((event) => ({
    eventId: String(event.eventId || ""),
    localDate: localDay(String(event.timestampUtc || ""), timeZone),
  }));
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return chunks.join("");
}

if (process.argv[1] && process.argv[1].replaceAll("\\", "/").endsWith("thread_temporal_localize.mjs")) {
  try {
    const timezoneIndex = process.argv.indexOf("--timezone");
    const timeZone = timezoneIndex >= 0 ? process.argv[timezoneIndex + 1] : Intl.DateTimeFormat().resolvedOptions().timeZone;
    const parsed = JSON.parse((await readStdin()).replace(/^\uFEFF/, ""));
    const events = Array.isArray(parsed) ? parsed : parsed.events;
    console.log(JSON.stringify({ contractVersion: TEMPORAL_LOCAL_DAY_CONTRACT, timezone: timeZone, events: localizeEvents(events, timeZone) }));
  } catch (error) {
    const message = String(error?.message || error);
    console.error(JSON.stringify({ status: "error", code: message.split(":", 1)[0], message }));
    process.exitCode = 1;
  }
}
