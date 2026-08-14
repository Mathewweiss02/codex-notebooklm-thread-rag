#!/usr/bin/env node

export const TEMPORAL_RANGE_CONTRACT = "temporal-range-v1";

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

function cliUsage() {
  return `Usage: node thread_temporal_resolve.mjs --expression TEXT [options]
       node thread_temporal_resolve.mjs --start TEXT --end TEXT [options]

Options:
  --expression TEXT  today, yesterday, tomorrow, past N hours/days, last week,
                     week to date, or YYYY-MM-DD
  --start TEXT       Explicit half-open range start (ISO timestamp or local date/time)
  --end TEXT         Explicit half-open range end (ISO timestamp or local date/time)
  --timezone ZONE    IANA timezone (default: machine timezone)
  --now ISO          Fixed capture time for deterministic replay/tests
  --week-start DAY   monday (default) or sunday
`;
}

function parseArgs(argv) {
  const options = { expression: null, start: null, end: null, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, now: null, weekStart: "monday" };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--expression" || arg === "-e") options.expression = argv[++index];
    else if (arg === "--start") options.start = argv[++index];
    else if (arg === "--end") options.end = argv[++index];
    else if (arg === "--timezone" || arg === "--tz") options.timezone = argv[++index];
    else if (arg === "--now") options.now = argv[++index];
    else if (arg === "--week-start") options.weekStart = String(argv[++index] || "").toLowerCase();
    else if (arg === "--help" || arg === "-h") { console.log(cliUsage()); process.exit(0); }
    else throw new Error(`Unknown argument: ${arg}`);
  }
  if ((!options.expression && !(options.start && options.end)) || (options.expression && (options.start || options.end))) throw new Error("provide --expression or both --start and --end");
  if (!["monday", "sunday"].includes(options.weekStart)) throw new Error("--week-start must be monday or sunday");
  return options;
}

function assertTimezone(timeZone) {
  try { new Intl.DateTimeFormat("en-US", { timeZone }).format(); }
  catch { throw new Error(`INVALID_TIMEZONE: ${timeZone}`); }
}

function nowDate(value) {
  const date = value ? new Date(value) : new Date();
  if (!Number.isFinite(date.getTime())) throw new Error("INVALID_NOW: expected an ISO timestamp");
  return date;
}

function formatter(timeZone) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    calendar: "gregory",
    numberingSystem: "latn",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
}

function localFieldsAt(date, timeZone) {
  const fields = {};
  for (const part of formatter(timeZone).formatToParts(date)) {
    if (["year", "month", "day", "hour", "minute", "second"].includes(part.type)) fields[part.type] = Number(part.value);
  }
  return fields;
}

function fieldsEqual(left, right) {
  return ["year", "month", "day", "hour", "minute", "second"].every((key) => left[key] === right[key]);
}

function offsetAt(instantMs, timeZone) {
  const fields = localFieldsAt(new Date(instantMs), timeZone);
  return Date.UTC(fields.year, fields.month - 1, fields.day, fields.hour, fields.minute, fields.second) - instantMs;
}

function localWallToUtc(fields, timeZone) {
  const naiveMs = Date.UTC(fields.year, fields.month - 1, fields.day, fields.hour || 0, fields.minute || 0, fields.second || 0);
  const offsets = new Set();
  for (let delta = -48; delta <= 48; delta += 1) offsets.add(offsetAt(naiveMs + delta * HOUR_MS, timeZone));
  const candidates = [...offsets]
    .map((offset) => naiveMs - offset)
    .filter((candidate, index, values) => values.indexOf(candidate) === index)
    .filter((candidate) => fieldsEqual(localFieldsAt(new Date(candidate), timeZone), fields))
    .sort((a, b) => a - b);
  if (candidates.length === 0) throw new Error("NONEXISTENT_LOCAL_TIME: local wall time does not exist in the selected timezone");
  if (candidates.length > 1) throw new Error("AMBIGUOUS_LOCAL_TIME: supply an explicit UTC offset");
  return candidates[0];
}

function dateFields(date) {
  return { year: date.year, month: date.month, day: date.day, hour: 0, minute: 0, second: 0 };
}

function addLocalDays(fields, amount) {
  const date = new Date(Date.UTC(fields.year, fields.month - 1, fields.day + amount));
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate(), hour: 0, minute: 0, second: 0 };
}

function localMidnight(fields, timeZone) {
  return localWallToUtc(dateFields(fields), timeZone);
}

function dayOfWeek(fields) {
  return new Date(Date.UTC(fields.year, fields.month - 1, fields.day)).getUTCDay();
}

function startOfWeek(fields, weekStart) {
  const day = dayOfWeek(fields);
  const offset = weekStart === "sunday" ? day : (day + 6) % 7;
  return addLocalDays(dateFields(fields), -offset);
}

function parseLocalOrAbsolute(value, timeZone, boundary) {
  const trimmed = String(value || "").trim();
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  if (dateOnly) return localMidnight({ year: Number(dateOnly[1]), month: Number(dateOnly[2]), day: Number(dateOnly[3]) }, timeZone);
  const absolute = Date.parse(trimmed);
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(trimmed) && Number.isFinite(absolute)) return absolute;
  const local = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?)?$/.exec(trimmed);
  if (!local) throw new Error(`INVALID_TIME_RANGE: cannot parse ${boundary}`);
  return localWallToUtc({
    year: Number(local[1]), month: Number(local[2]), day: Number(local[3]),
    hour: Number(local[4] || 0), minute: Number(local[5] || 0), second: Number(local[6] || 0),
  }, timeZone);
}

function iso(ms) { return new Date(ms).toISOString(); }

function resolvedLocalLabel(ms, timeZone) {
  const fields = localFieldsAt(new Date(ms), timeZone);
  return `${String(fields.year).padStart(4, "0")}-${String(fields.month).padStart(2, "0")}-${String(fields.day).padStart(2, "0")}T${String(fields.hour).padStart(2, "0")}:${String(fields.minute).padStart(2, "0")}:${String(fields.second).padStart(2, "0")}`;
}

export function resolveExpression(options = {}) {
  const timeZone = options.timezone || options.timeZone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  assertTimezone(timeZone);
  const now = nowDate(options.now);
  const nowMs = now.getTime();
  let startMs;
  let endMs;
  let kind;
  let expression = options.expression;
  if (options.start && options.end) {
    expression = expression || `${options.start}/${options.end}`;
    startMs = parseLocalOrAbsolute(options.start, timeZone, "start");
    endMs = parseLocalOrAbsolute(options.end, timeZone, "end");
    kind = "explicit-range";
  } else {
    expression = String(expression || "").trim();
    const normalized = expression.toLocaleLowerCase().replace(/\s+/g, " ");
    const nowLocal = localFieldsAt(now, timeZone);
    const today = dateFields(nowLocal);
    if (normalized === "today") {
      startMs = localMidnight(today, timeZone); endMs = nowMs; kind = "today";
    } else if (normalized === "yesterday") {
      const yesterday = addLocalDays(today, -1); startMs = localMidnight(yesterday, timeZone); endMs = localMidnight(today, timeZone); kind = "yesterday";
    } else if (normalized === "tomorrow") {
      const tomorrow = addLocalDays(today, 1); const dayAfter = addLocalDays(today, 2); startMs = localMidnight(tomorrow, timeZone); endMs = localMidnight(dayAfter, timeZone); kind = "tomorrow";
    } else if (normalized === "last week") {
      const currentWeek = startOfWeek(today, options.weekStart || "monday"); const previousWeek = addLocalDays(currentWeek, -7); startMs = localMidnight(previousWeek, timeZone); endMs = localMidnight(currentWeek, timeZone); kind = "last-week";
    } else if (normalized === "week to date") {
      const currentWeek = startOfWeek(today, options.weekStart || "monday"); startMs = localMidnight(currentWeek, timeZone); endMs = nowMs; kind = "week-to-date";
    } else {
      const rolling = /^past (\d+) (hour|hours|day|days)$/.exec(normalized);
      const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(normalized);
      if (rolling) {
        const amount = Number(rolling[1]);
        if (!Number.isSafeInteger(amount) || amount < 1) throw new Error("INVALID_TIME_RANGE: duration must be positive");
        startMs = nowMs - amount * (rolling[2].startsWith("hour") ? HOUR_MS : DAY_MS); endMs = nowMs; kind = "rolling-duration";
      } else if (dateOnly) {
        const selected = { year: Number(dateOnly[1]), month: Number(dateOnly[2]), day: Number(dateOnly[3]) };
        startMs = localMidnight(selected, timeZone); endMs = localMidnight(addLocalDays(selected, 1), timeZone); kind = "explicit-date";
      } else throw new Error("INVALID_TIME_RANGE: unsupported period expression");
    }
  }
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) throw new Error("INVALID_TIME_RANGE: end must not precede start");
  const future = startMs > nowMs;
  return {
    contractVersion: TEMPORAL_RANGE_CONTRACT,
    requestedExpression: expression,
    kind,
    timezone: timeZone,
    nowUtc: iso(nowMs),
    nowLocal: resolvedLocalLabel(nowMs, timeZone),
    startUtc: iso(startMs),
    endUtc: iso(endMs),
    startLocal: resolvedLocalLabel(startMs, timeZone),
    endLocal: resolvedLocalLabel(endMs, timeZone),
    boundary: "half-open [start,end)",
    durationSeconds: (endMs - startMs) / 1000,
    future,
    expectedActivity: future ? "empty-unless-now-advances" : "query-index",
  };
}

if (process.argv[1] && process.argv[1].replaceAll("\\", "/").endsWith("thread_temporal_resolve.mjs")) {
  try {
    console.log(JSON.stringify(resolveExpression(parseArgs(process.argv.slice(2))), null, 2));
  } catch (error) {
    console.error(JSON.stringify({ status: "error", code: String(error?.message || error).split(":", 1)[0], message: String(error?.message || error) }, null, 2));
    process.exitCode = 1;
  }
}
