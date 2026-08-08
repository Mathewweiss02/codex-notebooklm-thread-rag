import { createHash } from "node:crypto";
import { createReadStream, existsSync } from "node:fs";
import { readdir, stat } from "node:fs/promises";
import { basename, join } from "node:path";
import readline from "node:readline";
import { parseQuery, redactSensitiveText, searchThreads } from "./thread_search_lib.mjs";

function defaultRoots() {
  const codexHome = process.env.CODEX_HOME || join(process.env.USERPROFILE || process.env.HOME || "", ".codex");
  return [join(codexHome, "sessions"), join(codexHome, "archived_sessions")].filter(existsSync);
}

async function findJsonlFiles(root, wantedIds, output) {
  const entries = await readdir(root, { withFileTypes: true });
  for (const entry of entries) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) await findJsonlFiles(path, wantedIds, output);
    else if (entry.isFile() && entry.name.endsWith(".jsonl")
      && [...wantedIds].some((id) => entry.name.includes(id))) output.push(path);
  }
}

async function readFirstLine(path) {
  const stream = createReadStream(path, { encoding: "utf8" });
  const reader = readline.createInterface({ input: stream, crlfDelay: Infinity });
  try {
    for await (const line of reader) return line;
  } finally {
    reader.close();
    stream.destroy();
  }
  return "";
}

async function fileRecord(path) {
  let meta = {};
  try {
    const parsed = JSON.parse(await readFirstLine(path));
    if (parsed.type === "session_meta") meta = parsed.payload || {};
  } catch { /* path-derived fallback */ }
  let fileStat = null;
  try { fileStat = await stat(path); } catch { /* ignore */ }
  return {
    id: meta.id || basename(path).match(/([0-9a-f]{8}-[0-9a-f-]{27,})/i)?.[1] || path,
    sessionId: meta.session_id || meta.sessionId || null,
    parentThreadId: meta.parent_thread_id || meta.parentThreadId || null,
    cwd: meta.cwd || null,
    source: meta.source || null,
    path,
    archived: /[\\/]archived_sessions[\\/]/i.test(path),
    mtimeMs: fileStat?.mtimeMs || 0,
    sizeBytes: fileStat?.size || 0,
  };
}

function chooseCanonical(left, right) {
  if (left.archived !== right.archived) return left.archived ? right : left;
  if (left.mtimeMs !== right.mtimeMs) return left.mtimeMs > right.mtimeMs ? left : right;
  return left.sizeBytes >= right.sizeBytes ? left : right;
}

export async function locateThreads(threadIds, roots = defaultRoots()) {
  const wanted = new Set(threadIds);
  const paths = [];
  await Promise.all(roots.map((root) => findJsonlFiles(root, wanted, paths)));
  const canonical = new Map();
  for (const record of await Promise.all(paths.map(fileRecord))) {
    if (!wanted.has(record.id)) continue;
    const existing = canonical.get(record.id);
    canonical.set(record.id, existing ? chooseCanonical(existing, record) : record);
  }
  return [...canonical.values()];
}

function textFromParts(parts) {
  return (Array.isArray(parts) ? parts : [parts]).map((item) => {
    if (typeof item === "string") return item;
    if (typeof item?.text === "string") return item.text;
    if (typeof item?.content === "string") return item.content;
    return "";
  }).filter(Boolean).join(" ");
}

function extractSourceRecord(obj) {
  if (obj?.type !== "response_item") return null;
  if (obj?.payload?.type === "message" && obj?.payload?.role === "user") {
    const text = textFromParts(obj.payload.content || []);
    return text ? { text, sourceKind: "user", callId: null } : null;
  }
  if (obj?.payload?.type === "custom_tool_call_output" || obj?.payload?.type === "function_call_output") {
    const text = textFromParts(obj.payload.output || []);
    return text ? { text, sourceKind: "tool", callId: obj.payload.call_id || null } : null;
  }
  return null;
}

function conceptMatches(text, concepts) {
  const matches = [];
  for (const concept of concepts) {
    concept.jsRegex.lastIndex = 0;
    const match = concept.jsRegex.exec(text);
    concept.jsRegex.lastIndex = 0;
    if (match) matches.push({ concept, start: match.index, end: match.index + match[0].length });
  }
  return matches;
}

function signalList(text, rules) {
  return rules.filter((rule) => rule.pattern.test(text)).map((rule) => rule.label);
}

const SOURCE_RULES = [
  { label: "forwarded-email", pattern: /forwarded message|original message|sent from my (?:iphone|phone)/i },
  { label: "email-headers", pattern: /(?:^|\n)\s*["']?(?:from|to|cc|subject|date|sender)["']?\s*:/im },
  { label: "meeting-transcript", pattern: /(?:^|\n)\s*\*\*[A-Z][A-Za-z .'-]{1,40}:\*\*|(?:^|\n)\s*#{1,4}\s*\*\*[0-9]{1,2}:[0-9]{2}/m },
  { label: "file-or-attachment", pattern: /# files mentioned|attachment|\.xlsx\b|\.xls\b|\.csv\b|\.zip\b/i },
  { label: "quoted-source-request", pattern: /(?:client|customer|requester).{0,80}(?:asked|requested|need)|\bdata order\b/i },
  { label: "explicit-user-direction", pattern: /\b(?:i need you|i want you|can you|could you|what i want|we need to|please)\b/i },
];

function provenanceLayer(sourceKind, sourceSignals, retellingSignals) {
  const signals = new Set(sourceSignals);
  if (signals.has("structured-email-record")) return "original-source";
  if (retellingSignals.length > 0) return "downstream-summary";
  if (signals.has("forwarded-email") || signals.has("email-headers")) return "original-source";
  if (signals.has("meeting-transcript")) return "clarification-source";
  if (sourceKind === "user" && signals.has("explicit-user-direction")) return "direct-user-instruction";
  if (sourceKind === "tool") return "retrieved-evidence";
  return "candidate-source";
}

const LAYER_BONUS = new Map([
  ["original-source", 14],
  ["clarification-source", 5],
  ["direct-user-instruction", 7],
  ["retrieved-evidence", 2],
  ["candidate-source", 0],
  ["downstream-summary", -8],
]);

const RETELLING_RULES = [
  { label: "mission-or-automation", pattern: /mission control|future task prompt|automation id:|persistent goal|controlling contract/i },
  { label: "recap-or-summary", pattern: /\b(?:recap|summary|here(?:'s| is) what (?:i|we) remember|the pieces i remember|based on (?:the|our) (?:prior|previous|other) thread)\b/i },
  { label: "confirmation-restatement", pattern: /confirming scope|before we begin fulfillment, i want to confirm my interpretation/i },
  { label: "embedded-transcript", pattern: /\[\d+\]\s+(?:user|assistant):|<source_thread_id>|>>> transcript|(?:^|\n)\s*##\s+(?:user|assistant)\s+[—-]\s+\d{4}-\d{2}-\d{2}/im },
  { label: "completion-update", pattern: /\b(?:completed|final deliverable|work log|investigation outcome)\b/i },
];

function boundedExcerpt(text, firstMatch, maxChars) {
  const start = Math.max(0, firstMatch - 900);
  const end = Math.min(text.length, start + maxChars);
  return {
    excerptStart: start,
    excerptTruncated: start > 0 || end < text.length,
    excerpt: redactSensitiveText(text.slice(start, end).replace(/\s+/g, " ").trim()),
  };
}

export async function extractOriginCandidates(thread, query, options = {}) {
  const parsed = typeof query === "string" ? parseQuery(query, { aliases: options.aliases || [] }) : query;
  const totalWeight = parsed.concepts.reduce((sum, concept) => sum + concept.weight, 0) || 1;
  const minCoverage = Number.isFinite(options.minCoverage) ? options.minCoverage : 0.35;
  const minConcepts = Number.isFinite(options.minConcepts) ? options.minConcepts : 2;
  const maxChars = Number.isFinite(options.maxChars) ? options.maxChars : 7000;
  const stream = createReadStream(thread.path, { encoding: "utf8" });
  const reader = readline.createInterface({ input: stream, crlfDelay: Infinity });
  const candidates = [];
  let lineNumber = 0;
  try {
    for await (const line of reader) {
      lineNumber += 1;
      if (!line.includes('"type":"response_item"')
        || (!line.includes('"role":"user"')
          && !line.includes('"type":"custom_tool_call_output"')
          && !line.includes('"type":"function_call_output"'))) continue;
      let obj;
      try { obj = JSON.parse(line); } catch { continue; }
      const sourceRecord = extractSourceRecord(obj);
      if (!sourceRecord) continue;
      const { text, sourceKind, callId } = sourceRecord;
      const matches = conceptMatches(text, parsed.concepts);
      const coverage = matches.reduce((sum, match) => sum + match.concept.weight, 0) / totalWeight;
      if (matches.length < minConcepts || coverage < minCoverage) continue;
      const sourceSignals = signalList(text, SOURCE_RULES);
      if (/["']subject["']\s*:/i.test(text) && /["']body["']\s*:/i.test(text)) sourceSignals.push("structured-email-record");
      if (sourceKind === "tool") sourceSignals.unshift("tool-source");
      let retellingSignals = signalList(text, RETELLING_RULES);
      const isStructuredOriginal = sourceSignals.some((signal) => ["forwarded-email", "structured-email-record", "email-headers"].includes(signal));
      if (isStructuredOriginal) retellingSignals = retellingSignals.filter((signal) => signal !== "completion-update");
      const layer = provenanceLayer(sourceKind, sourceSignals, retellingSignals);
      const sortedStarts = matches.map((match) => match.start).sort((a, b) => a - b);
      const span = sortedStarts.length > 1 ? sortedStarts.at(-1) - sortedStarts[0] : text.length;
      const proximity = span <= 500 ? 1 : span <= 2500 ? 0.7 : span <= 10000 ? 0.35 : 0;
      const baseScore = coverage * 100
        + Math.min(18, sourceSignals.length * 6)
        + (LAYER_BONUS.get(layer) || 0)
        + proximity * 8
        - Math.min(30, retellingSignals.length * 10)
        - (text.length > 50000 ? 8 : text.length > 20000 ? 4 : 0);
      candidates.push({
        threadId: thread.id,
        path: thread.path,
        cwd: thread.cwd,
        archived: thread.archived,
        timestamp: obj.timestamp || null,
        timestampMs: Date.parse(obj.timestamp || "") || 0,
        lineNumber,
        sourceKind,
        callId,
        messageSha256: createHash("sha256").update(text).digest("hex"),
        coverage: Number(coverage.toFixed(3)),
        matchedConcepts: matches.map((match) => match.concept.label),
        unmatchedConcepts: parsed.concepts.filter((concept) => !matches.some((match) => match.concept.index === concept.index)).map((concept) => concept.label),
        sourceSignals,
        retellingSignals,
        provenanceLayer: layer,
        proximity,
        baseScore,
        ...boundedExcerpt(text, sortedStarts[0] || 0, maxChars),
      });
    }
  } finally {
    reader.close();
    stream.destroy();
  }
  const chronological = [...candidates].sort((a, b) => a.timestampMs - b.timestampMs || a.lineNumber - b.lineNumber);
  const chronologicalIndex = new Map(chronological.map((candidate, index) => [`${candidate.lineNumber}:${candidate.messageSha256}`, index]));
  for (const candidate of candidates) {
    const index = chronologicalIndex.get(`${candidate.lineNumber}:${candidate.messageSha256}`) || 0;
    candidate.chronologyBonus = Number((12 / (index + 1)).toFixed(2));
    candidate.originScore = Number((candidate.baseScore + candidate.chronologyBonus).toFixed(2));
    delete candidate.baseScore;
    delete candidate.timestampMs;
  }
  return candidates.sort((a, b) => b.originScore - a.originScore
    || Date.parse(a.timestamp || 0) - Date.parse(b.timestamp || 0)
    || a.lineNumber - b.lineNumber);
}

export async function discoverOrigins(options) {
  const roots = options.roots?.length ? options.roots : defaultRoots();
  let threads;
  let discovery = null;
  if (options.threadIds?.length) {
    threads = await locateThreads(options.threadIds, roots);
  } else {
    const excludedThreadIds = [...(options.excludeThreadIds || [])];
    if (!options.includeCurrent && process.env.CODEX_THREAD_ID) excludedThreadIds.push(process.env.CODEX_THREAD_ID);
    discovery = await searchThreads({
      query: options.query,
      roots,
      aliases: options.aliases || [],
      cwd: options.cwd || null,
      cwdMode: options.cwdMode || "exact",
      limit: options.limitThreads || 5,
      excerpts: 1,
      hydrate: options.hydrate !== false,
      excludeThreadIds,
      includeSubagents: Boolean(options.includeSubagents),
    });
    threads = discovery.results.map((result) => ({
      id: result.id,
      name: result.name,
      path: result.path,
      cwd: result.cwd,
      archived: result.archived,
    }));
  }
  const all = [];
  for (const thread of threads) {
    const candidates = await extractOriginCandidates(thread, options.query, options);
    for (const candidate of candidates.slice(0, options.limitPerThread || 5)) {
      candidate.threadName = thread.name || null;
      all.push(candidate);
    }
  }
  all.sort((a, b) => b.originScore - a.originScore
    || Date.parse(a.timestamp || 0) - Date.parse(b.timestamp || 0));
  return {
    query: options.query,
    threadsExamined: threads.map((thread) => ({ id: thread.id, name: thread.name || null, path: thread.path, cwd: thread.cwd, archived: thread.archived })),
    discovery: discovery ? { results: discovery.results.map((result) => ({ rank: result.rank, id: result.id, name: result.name, score: result.score })) } : null,
    candidates: all.slice(0, options.limit || 10).map((candidate, index) => ({ rank: index + 1, ...candidate })),
  };
}

export function formatOriginReport(report) {
  const lines = [`Thread instruction-origin search: ${report.query}`, `Examined ${report.threadsExamined.length} thread(s); found ${report.candidates.length} ranked candidate turn(s).`];
  for (const candidate of report.candidates) {
    lines.push("");
    lines.push(`${candidate.rank}. ${candidate.threadName || candidate.threadId} — origin score ${candidate.originScore}`);
    lines.push(`   Thread: ${candidate.threadId}; ${candidate.timestamp || "unknown time"}; JSONL line ${candidate.lineNumber}`);
    lines.push(`   Source kind: ${candidate.sourceKind}; provenance: ${candidate.provenanceLayer}${candidate.callId ? `; call ${candidate.callId}` : ""}`);
    lines.push(`   Coverage: ${candidate.coverage}; source signals: ${candidate.sourceSignals.join(", ") || "none"}; retelling signals: ${candidate.retellingSignals.join(", ") || "none"}`);
    lines.push(`   SHA-256: ${candidate.messageSha256}`);
    lines.push(`   ${candidate.excerpt}`);
  }
  return lines.join("\n");
}
