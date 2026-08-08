import { spawn } from "node:child_process";
import { createReadStream, existsSync } from "node:fs";
import { open, readdir, stat } from "node:fs/promises";
import { dirname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import readline from "node:readline";

const HERE = dirname(fileURLToPath(import.meta.url));

const STOP_WORDS = new Set([
  "a", "about", "actually", "again", "all", "also", "am", "an", "and", "any", "are", "as", "at",
  "basically", "be", "because", "been", "bro", "but", "by", "can", "chat", "conversation", "could",
  "did", "do", "does", "doing", "done", "for", "forgot", "from", "get", "go", "had", "has", "have",
  "he", "help", "her", "here", "him", "his", "how", "i", "if", "in", "into", "is", "it", "its",
  "just", "kind", "know", "like", "make", "maybe", "me", "my", "need", "of", "oh", "okay", "on", "one",
  "or", "our", "out", "prior", "recent", "remember", "said", "search", "shit", "so", "some", "something",
  "stuff", "talk", "talked", "task", "that", "the", "their", "them", "then", "there", "these", "they", "through",
  "thing", "things", "this", "thread", "to", "try", "um", "up", "use", "using", "was", "way", "we",
  "were", "what", "when", "where", "which", "who", "why", "with", "workflow", "would", "yeah", "you",
  "your",
]);

const LOW_VALUE_WORDS = new Set(["data", "file", "files", "folder", "guy", "person", "project"]);

const BUILTIN_CONCEPTS = [
  {
    id: "betterdata",
    label: "BetterData",
    trigger: /\bbettr\s*data\b|\bbetter[\s_-]*data\b/i,
    patterns: ["\\bbettrdata\\b", "\\bbetter[\\s_-]*data\\b"],
    covered: ["bettrdata", "betterdata", "better", "data"],
    weight: 1.25,
  },
  {
    id: "vendordata",
    label: "VendorData",
    trigger: /\bvendor[\s_-]*data\b/i,
    patterns: ["\\bvendor[\\s_-]*data\\b"],
    covered: ["vendordata", "vendor", "data"],
    weight: 1.45,
  },
  {
    id: "aws",
    label: "AWS/S3",
    trigger: /\baws\b|\bamazon web services\b|\bs3\b/i,
    patterns: ["\\baws\\b", "\\bamazon[\\s_-]+web[\\s_-]+services\\b", "\\bs3\\b"],
    covered: ["aws", "amazon", "web", "services", "s3"],
    weight: 1.2,
  },
  {
    id: "sftp",
    label: "SFTP/Files.com",
    trigger: /\bsftp\b|\bfiles\.com\b|\bsecure file transfer\b/i,
    patterns: ["\\bsftp\\b", "\\bfiles\\.com\\b", "\\bsecure[\\s_-]+file[\\s_-]+transfer\\b"],
    covered: ["sftp", "files.com", "secure", "transfer"],
    weight: 1.3,
  },
  {
    id: "upload",
    label: "upload/drop",
    trigger: /\bupload(?:ed|ing|s)?\b|\bdrop(?:ped|ping|s)?\b/i,
    patterns: ["\\bupload(?:ed|ing|s)?\\b", "\\bdrop(?:ped|ping|s)?\\b"],
    covered: ["upload", "uploaded", "uploading", "uploads", "drop", "dropped", "dropping", "drops"],
    weight: 0.9,
  },
  {
    id: "suppression",
    label: "suppression",
    trigger: /\bsuppress(?:ion|ed|ing|ions)?\b/i,
    patterns: ["\\bsuppress(?:ion|ed|ing|ions)?\\b"],
    covered: ["suppress", "suppression", "suppressed", "suppressing", "suppressions"],
    weight: 1.35,
  },
  {
    id: "mike",
    label: "Mike/Michael",
    trigger: /\bmike\b|\bmichael\b/i,
    patterns: ["\\bmike\\b", "\\bmichael\\b"],
    covered: ["mike", "michael"],
    weight: 1.15,
  },
  {
    id: "email",
    label: "email",
    trigger: /\be-?mail(?:ed|ing|s)?\b/i,
    patterns: ["\\be-?mail(?:ed|ing|s)?\\b"],
    covered: ["email", "emails", "emailed", "emailing", "mail"],
    weight: 0.8,
  },
  {
    id: "preserve",
    label: "preserve/unchanged",
    trigger: /\bunchanged\b|\bpreserv(?:e|ed|ing|ation)\b|\bkeep\b.{0,40}\b(?:same|unchanged)\b|\b(?:must|should)\s+not\s+change\b/i,
    patterns: [
      "\\bunchanged\\b",
      "\\bpreserv(?:e|ed|ing|ation)\\b",
      "\\bkeep\\b.{0,40}\\b(?:same|unchanged)\\b",
      "\\b(?:must|should)\\s+not\\s+change\\b",
    ],
    covered: ["unchanged", "preserve", "preserved", "preserving", "keep", "same", "change"],
    weight: 1.25,
  },
];

const NUMBER_EQUIVALENTS = new Map([
  ["zero", "0"], ["one", "1"], ["two", "2"], ["three", "3"], ["four", "4"],
  ["five", "5"], ["six", "6"], ["seven", "7"], ["eight", "8"], ["nine", "9"],
  ["ten", "10"], ["eleven", "11"], ["twelve", "12"], ["thirteen", "13"],
  ["fourteen", "14"], ["fifteen", "15"], ["sixteen", "16"], ["seventeen", "17"],
  ["eighteen", "18"], ["nineteen", "19"], ["twenty", "20"],
]);

function scaledNumberConcept(source) {
  const hadComma = /\b\d{1,3}(?:,\d{3})+\b/.test(source);
  const compact = source.replace(/,/g, "");
  const match = compact.match(/\b(\d+(?:\.\d+)?)\s*([km])?\b/i);
  if (!match) return null;
  const numeric = Number(match[1]);
  if (!Number.isFinite(numeric)) return null;
  const multiplier = match[2]?.toLocaleLowerCase() === "k" ? 1_000
    : match[2]?.toLocaleLowerCase() === "m" ? 1_000_000
      : 1;
  const absolute = numeric * multiplier;
  if (!Number.isInteger(absolute) || absolute < 1_000) return null;
  if (!match[2] && !hadComma && absolute % 1_000 !== 0) return null;
  const patterns = new Set([
    `\\b${absolute.toLocaleString("en-US").replace(/,/g, "[,\\s]?")}\\b`,
    `\\b${absolute}\\b`,
  ]);
  if (absolute % 1_000_000 === 0) patterns.add(`\\b${absolute / 1_000_000}(?:\\.0+)?\\s*m(?:illion)?\\b`);
  if (absolute % 1_000 === 0) patterns.add(`\\b${absolute / 1_000}(?:\\.0+)?\\s*k\\b`);
  return {
    id: `scaled-number-${absolute}`,
    label: absolute.toLocaleString("en-US"),
    patterns: [...patterns],
    weight: 0.7,
    source: "scaled_number_equivalent",
    covered: [match[0].toLocaleLowerCase(), String(absolute), absolute.toLocaleString("en-US")],
  };
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeWhitespace(value) {
  return value.replace(/\s+/g, " ").trim();
}

function stemWord(value) {
  let word = value.toLocaleLowerCase().replace(/^[-_.]+|[-_.]+$/g, "");
  if (word.length > 6 && word.endsWith("ing")) word = word.slice(0, -3);
  else if (word.length > 5 && word.endsWith("ied")) word = `${word.slice(0, -3)}y`;
  else if (word.length > 5 && word.endsWith("ed")) word = word.slice(0, -2);
  else if (word.length > 5 && word.endsWith("ies")) word = `${word.slice(0, -3)}y`;
  else if (word.length > 4 && word.endsWith("es")) word = word.slice(0, -2);
  else if (word.length > 4 && word.endsWith("s")) word = word.slice(0, -1);
  if (/(.)\1$/.test(word) && word.length > 4) word = word.slice(0, -1);
  return word;
}

function tokenPattern(token) {
  if (/[@.]/.test(token)) return escapeRegex(token);
  const stem = stemWord(token);
  if (!stem) return escapeRegex(token);
  return `\\b${escapeRegex(stem)}(?:s|es|ed|ing)?\\b`;
}

function conceptFromAlias(rawAlias, index) {
  const separator = rawAlias.indexOf("=");
  if (separator < 1) throw new Error(`Invalid --alias value: ${rawAlias}. Use label=value1|value2.`);
  const label = rawAlias.slice(0, separator).trim();
  const values = rawAlias
    .slice(separator + 1)
    .split(/[|,]/)
    .map((value) => value.trim())
    .filter(Boolean);
  if (!label || values.length === 0) throw new Error(`Invalid --alias value: ${rawAlias}.`);
  return {
    id: `custom-${index}-${stemWord(label) || "alias"}`,
    label,
    patterns: values.map((value) => tokenPattern(value)),
    weight: 1.15,
    source: "custom_alias",
  };
}

export function parseQuery(query, options = {}) {
  const source = normalizeWhitespace(query || "");
  if (!source) throw new Error("A non-empty query is required.");
  const concepts = [];
  const covered = new Set();

  const scaledNumber = scaledNumberConcept(source);
  if (scaledNumber) {
    concepts.push(scaledNumber);
    for (const token of scaledNumber.covered) covered.add(stemWord(token));
  }

  for (const [word, digit] of NUMBER_EQUIVALENTS) {
    if (!new RegExp(`\\b(?:${word}|${digit})\\b`, "i").test(source)) continue;
    concepts.push({
      id: `number-${digit}`,
      label: `${word}/${digit}`,
      patterns: [`\\b(?:${word}|${digit})\\b`],
      // Numeric equivalence is supporting evidence. Bare numbers are frequent in logs,
      // counts, timestamps, and summaries, so they must not dominate semantic clues.
      weight: 0.35,
      source: "number_equivalent",
    });
    covered.add(word);
    covered.add(digit);
  }

  for (const builtin of BUILTIN_CONCEPTS) {
    if (!builtin.trigger.test(source)) continue;
    concepts.push({
      id: builtin.id,
      label: builtin.label,
      patterns: [...builtin.patterns],
      weight: builtin.weight,
      source: "builtin_alias",
    });
    for (const token of builtin.covered) covered.add(stemWord(token));
  }

  const quoted = [...source.matchAll(/"([^"]+)"|'([^']+)'/g)]
    .map((match) => normalizeWhitespace(match[1] || match[2] || ""))
    .filter(Boolean);
  for (const [index, phrase] of quoted.entries()) {
    const normalized = phrase.split(/\s+/).map(escapeRegex).join("[\\s_-]+");
    concepts.push({
      id: `phrase-${index}`,
      label: `\"${phrase}\"`,
      patterns: [normalized],
      weight: 1.8,
      source: "quoted_phrase",
    });
    for (const token of phrase.match(/[\p{L}\p{N}]+/gu) || []) covered.add(stemWord(token));
  }

  const rawTokens = source
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .match(/[\p{L}\p{N}][\p{L}\p{N}@._-]*/gu) || [];
  const candidates = [];
  for (const raw of rawTokens) {
    const lower = raw.toLocaleLowerCase();
    const stem = stemWord(lower);
    if (!stem || covered.has(stem) || STOP_WORDS.has(lower) || STOP_WORDS.has(stem)) continue;
    if (stem.length < 3 && !/\d/.test(stem)) continue;
    candidates.push({ raw: lower, stem });
  }

  const useful = candidates.filter(({ stem }) => !LOW_VALUE_WORDS.has(stem));
  const selected = useful.length > 0 ? useful : candidates;
  const seen = new Set(concepts.map((concept) => concept.id));
  for (const { raw, stem } of selected) {
    const id = `term-${stem}`;
    if (seen.has(id)) continue;
    seen.add(id);
    concepts.push({
      id,
      label: raw,
      patterns: [tokenPattern(raw)],
      weight: 1,
      source: "query_term",
    });
  }

  for (const [index, alias] of (options.aliases || []).entries()) {
    const concept = conceptFromAlias(alias, index);
    if (!seen.has(concept.id)) concepts.push(concept);
  }

  if (concepts.length === 0) {
    const fallback = source.toLocaleLowerCase();
    concepts.push({ id: "literal-query", label: source, patterns: [escapeRegex(fallback)], weight: 1, source: "literal" });
  }

  concepts.forEach((concept, index) => {
    concept.index = index;
    concept.jsRegex = new RegExp(`(?:${concept.patterns.join("|")})`, "giu");
  });
  return { source, concepts };
}

function extractMessage(obj) {
  if (obj?.type !== "response_item" || obj?.payload?.type !== "message") return null;
  const role = obj.payload.role;
  if (role !== "user" && role !== "assistant") return null;
  const parts = Array.isArray(obj.payload.content) ? obj.payload.content : [];
  const text = parts
    .map((item) => {
      if (typeof item === "string") return item;
      if (typeof item?.text === "string") return item.text;
      if (typeof item?.content === "string") return item.content;
      return "";
    })
    .filter(Boolean)
    .join(" ");
  if (!text) return null;
  return { timestamp: obj.timestamp || null, role, text };
}

function findMinimumSpan(positionLists) {
  const flattened = [];
  for (const [conceptIndex, positions] of positionLists.entries()) {
    for (const position of positions) flattened.push({ ...position, conceptIndex });
  }
  flattened.sort((a, b) => a.start - b.start || a.end - b.end);
  if (flattened.length === 0) return { span: Number.POSITIVE_INFINITY, start: 0, end: 0 };
  const needed = positionLists.size;
  const counts = new Map();
  let present = 0;
  let left = 0;
  let best = { span: Number.POSITIVE_INFINITY, start: flattened[0].start, end: flattened[0].end };
  for (let right = 0; right < flattened.length; right += 1) {
    const current = flattened[right];
    const prior = counts.get(current.conceptIndex) || 0;
    counts.set(current.conceptIndex, prior + 1);
    if (prior === 0) present += 1;
    while (present === needed && left <= right) {
      const first = flattened[left];
      const span = current.end - first.start;
      if (span < best.span) best = { span, start: first.start, end: current.end };
      const firstCount = counts.get(first.conceptIndex);
      counts.set(first.conceptIndex, firstCount - 1);
      if (firstCount === 1) present -= 1;
      left += 1;
    }
  }
  return best;
}

export function redactSensitiveText(value) {
  return value
    .replace(/AKIA[0-9A-Z]{16}/g, "[REDACTED_AWS_KEY]")
    .replace(/\bsk-[A-Za-z0-9_-]{12,}\b/g, "[REDACTED_API_KEY]")
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]{12,}/gi, "Bearer [REDACTED]")
    .replace(/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g, "[REDACTED_JWT]")
    .replace(/\b(password|passwd|secret|token|api[_ -]?key|access[_ -]?key)\s*[:=]\s*["']?[^\s"',;]{6,}/gi, "$1=[REDACTED]");
}

function analyzeMessage(message, concepts, lineNumber) {
  const positions = new Map();
  for (const concept of concepts) {
    concept.jsRegex.lastIndex = 0;
    const hits = [];
    let match;
    while ((match = concept.jsRegex.exec(message.text)) !== null) {
      hits.push({ start: match.index, end: match.index + match[0].length });
      if (hits.length >= 12) break;
      if (match[0].length === 0) concept.jsRegex.lastIndex += 1;
    }
    concept.jsRegex.lastIndex = 0;
    if (hits.length > 0) positions.set(concept.index, hits);
  }
  if (positions.size === 0) return null;
  const minimum = findMinimumSpan(positions);
  const excerptStart = Math.max(0, minimum.start - 280);
  const excerptEnd = Math.min(message.text.length, excerptStart + 1200);
  const excerpt = redactSensitiveText(normalizeWhitespace(message.text.slice(excerptStart, excerptEnd)));
  const completedAction = /\b(created|completed|copied|downloaded|finished|passed|resolved|sent|transferred|uploaded|verified)\b/i.test(message.text);
  const concreteArtifact = /s3:\/\/|checksum|\b\d{2,}[,\d]*\s+(?:csv|file|object|record)s?\b|\bno missing\b|\bversion(?:ed|ing)\b|\bencrypt(?:ed|ion)\b/i.test(message.text);
  const summaryLike = message.text.length > 12000 && /\[\d+\]\s+(?:user|assistant):/i.test(message.text);
  const rememberedRetelling = /\b(?:the\s+)?pieces\s+i\s+remember\b|\bi\s+remember\s+(?:that|the|there|it|are|was|were)\b|\bfrom\s+(?:the|that)\s+(?:other|prior|previous)\s+(?:thread|chat)\b|\bbased\s+on\s+(?:the|that)\s+(?:other|prior|previous)\s+(?:thread|chat)\b/i.test(message.text);
  let quality = summaryLike ? 0.42 : 1;
  if (rememberedRetelling) quality *= 0.78;
  if (message.text.length > 40000) quality *= 0.8;
  if (positions.size >= 3 && minimum.span > 10000) quality *= 0.72;
  const outcomeSignal = (completedAction ? (concreteArtifact ? 1 : 0.55) : 0) * quality;
  return {
    timestamp: message.timestamp,
    timestampMs: Date.parse(message.timestamp || "") || 0,
    role: message.role,
    lineNumber,
    conceptIds: [...positions.keys()].sort((a, b) => a - b),
    occurrences: [...positions.values()].reduce((sum, hits) => sum + hits.length, 0),
    minimumSpan: Number.isFinite(minimum.span) ? minimum.span : null,
    quality,
    outcomeSignal,
    excerpt,
  };
}

function makeSearchPattern(concepts) {
  const terms = concepts.flatMap((concept) => concept.patterns).join("|");
  return `\\"type\\":\\"response_item\\",\\"payload\\":\\{\\"type\\":\\"message\\"[^\\r\\n]{0,700}?\\"role\\":\\"(?:user|assistant)\\"[^\\r\\n]*(?:${terms})`;
}

function consumeJsonLines(onLine) {
  let buffer = "";
  return {
    push(chunk) {
      buffer += chunk;
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) if (line.trim()) onLine(line);
    },
    finish() {
      if (buffer.trim()) onLine(buffer);
      buffer = "";
    },
  };
}

async function scanWithRipgrep(roots, query) {
  const started = performance.now();
  const files = new Map();
  let summary = null;
  const args = [
    "--json",
    "--ignore-case",
    "--no-messages",
    "--glob",
    "*.jsonl",
    "--regexp",
    makeSearchPattern(query.concepts),
    ...roots,
  ];
  const child = spawn("rg", args, { windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  let stderr = "";
  let spawnError = null;
  const parser = consumeJsonLines((line) => {
    let event;
    try {
      event = JSON.parse(line);
    } catch {
      return;
    }
    if (event.type === "summary") {
      summary = event.data?.stats || null;
      return;
    }
    if (event.type !== "match") return;
    const path = event.data?.path?.text;
    const rawLine = event.data?.lines?.text;
    if (!path || !rawLine) return;
    let obj;
    try {
      obj = JSON.parse(rawLine);
    } catch {
      return;
    }
    const message = extractMessage(obj);
    if (!message) return;
    const analyzed = analyzeMessage(message, query.concepts, event.data?.line_number || null);
    if (!analyzed) return;
    const resolvedPath = resolve(path);
    if (!files.has(resolvedPath)) files.set(resolvedPath, []);
    files.get(resolvedPath).push(analyzed);
  });
  child.stdout.on("data", (chunk) => parser.push(chunk.toString()));
  child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
  child.on("error", (error) => { spawnError = error; });
  const code = await new Promise((resolvePromise) => child.on("close", resolvePromise));
  parser.finish();
  if (spawnError) throw spawnError;
  if (code !== 0 && code !== 1) throw new Error(`ripgrep failed with exit code ${code}: ${stderr.trim()}`);
  return {
    engine: "ripgrep",
    files,
    stats: {
      elapsedMs: Math.round(performance.now() - started),
      bytesSearched: summary?.bytes_searched || null,
      filesSearched: summary?.searches || null,
      matchedLines: summary?.matched_lines || [...files.values()].reduce((sum, items) => sum + items.length, 0),
    },
  };
}

async function enumerateJsonl(root) {
  const output = [];
  let rootStat = null;
  try { rootStat = await stat(root); } catch { return output; }
  if (rootStat.isFile()) {
    if (root.toLocaleLowerCase().endsWith(".jsonl")) output.push(root);
    return output;
  }
  let entries = [];
  try {
    entries = await readdir(root, { withFileTypes: true });
  } catch {
    return output;
  }
  for (const entry of entries) {
    const full = join(root, entry.name);
    if (entry.isDirectory()) output.push(...await enumerateJsonl(full));
    else if (entry.isFile() && entry.name.toLocaleLowerCase().endsWith(".jsonl")) output.push(full);
  }
  return output;
}

async function scanFileFallback(file, query) {
  const messages = [];
  const combined = new RegExp(`(?:${query.concepts.flatMap((concept) => concept.patterns).join("|")})`, "iu");
  const input = createReadStream(file, { encoding: "utf8" });
  const lines = readline.createInterface({ input, crlfDelay: Infinity });
  let lineNumber = 0;
  for await (const line of lines) {
    lineNumber += 1;
    if (!line.includes('"type":"response_item"') || (!line.includes('"role":"user"') && !line.includes('"role":"assistant"'))) continue;
    combined.lastIndex = 0;
    if (!combined.test(line)) continue;
    combined.lastIndex = 0;
    let obj;
    try { obj = JSON.parse(line); } catch { continue; }
    const message = extractMessage(obj);
    if (!message) continue;
    const analyzed = analyzeMessage(message, query.concepts, lineNumber);
    if (analyzed) messages.push(analyzed);
  }
  return messages;
}

async function scanFallback(roots, query) {
  const started = performance.now();
  const paths = (await Promise.all(roots.map(enumerateJsonl))).flat();
  const files = new Map();
  let cursor = 0;
  const workers = Array.from({ length: Math.min(3, paths.length) }, async () => {
    while (cursor < paths.length) {
      const index = cursor++;
      const messages = await scanFileFallback(paths[index], query);
      if (messages.length > 0) files.set(resolve(paths[index]), messages);
    }
  });
  await Promise.all(workers);
  return {
    engine: "javascript-fallback",
    files,
    stats: {
      elapsedMs: Math.round(performance.now() - started),
      bytesSearched: null,
      filesSearched: paths.length,
      matchedLines: [...files.values()].reduce((sum, items) => sum + items.length, 0),
    },
  };
}

async function scanCorpus(roots, query) {
  try {
    return await scanWithRipgrep(roots, query);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
    const fallback = await scanFallback(roots, query);
    fallback.stats.fallbackReason = "ripgrep was not available";
    return fallback;
  }
}

function normalizePathForCompare(value) {
  if (!value) return "";
  return normalize(value.replace(/^\\\\\?\\/, "")).replace(/[\\/]+$/, "").toLocaleLowerCase();
}

function inferThreadId(file) {
  return file.match(/([0-9a-f]{8}-[0-9a-f-]{27})\.jsonl$/i)?.[1] || null;
}

async function readFirstLine(file, maxBytes = 16 * 1024 * 1024) {
  const handle = await open(file, "r");
  try {
    const chunks = [];
    let total = 0;
    while (total < maxBytes) {
      const buffer = Buffer.alloc(Math.min(64 * 1024, maxBytes - total));
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, total);
      if (bytesRead === 0) break;
      const slice = buffer.subarray(0, bytesRead);
      const newline = slice.indexOf(0x0a);
      if (newline >= 0) {
        chunks.push(slice.subarray(0, newline));
        break;
      }
      chunks.push(slice);
      total += bytesRead;
    }
    return Buffer.concat(chunks).toString("utf8").replace(/^\uFEFF/, "").trim();
  } finally {
    await handle.close();
  }
}

async function loadFileRecord(file, messages) {
  let meta = {};
  try {
    const firstLine = await readFirstLine(file);
    const parsed = JSON.parse(firstLine);
    if (parsed.type === "session_meta") meta = parsed.payload || {};
  } catch {
    // Fall back to path-derived metadata.
  }
  let fileStat = null;
  try { fileStat = await stat(file); } catch { /* ignore */ }
  const id = meta.id || inferThreadId(file) || file;
  return {
    id,
    sessionId: meta.session_id || meta.sessionId || null,
    parentThreadId: meta.parent_thread_id || meta.parentThreadId || null,
    cwd: meta.cwd || null,
    createdAt: meta.timestamp || null,
    source: meta.source || null,
    path: file,
    archived: /[\\/]archived_sessions[\\/]/i.test(file),
    mtimeMs: fileStat?.mtimeMs || 0,
    sizeBytes: fileStat?.size || 0,
    messages,
  };
}

function chooseCanonical(left, right) {
  if (left.archived !== right.archived) return left.archived ? right : left;
  if (left.mtimeMs !== right.mtimeMs) return left.mtimeMs > right.mtimeMs ? left : right;
  return left.sizeBytes >= right.sizeBytes ? left : right;
}

function cwdMatches(actual, wanted, mode) {
  if (!wanted) return true;
  const normalizedActual = normalizePathForCompare(actual);
  const normalizedWanted = normalizePathForCompare(wanted);
  if (mode === "contains") return normalizedActual.includes(normalizedWanted);
  if (mode === "prefix") return normalizedActual === normalizedWanted || normalizedActual.startsWith(`${normalizedWanted}\\`);
  return normalizedActual === normalizedWanted;
}

function isSubagentSource(source) {
  if (!source) return false;
  if (typeof source === "string") return /sub.?agent|guardian/i.test(source);
  return typeof source === "object" && (source.subAgent || source.subagent || source.guardian);
}

function conceptWeightMap(threads, concepts) {
  const documentFrequency = new Map(concepts.map((concept) => [concept.index, 0]));
  for (const thread of threads) {
    const present = new Set(thread.messages.flatMap((message) => message.conceptIds));
    for (const index of present) documentFrequency.set(index, (documentFrequency.get(index) || 0) + 1);
  }
  const count = Math.max(1, threads.length);
  return new Map(concepts.map((concept) => {
    const frequency = documentFrequency.get(concept.index) || 0;
    const idf = 1 + Math.log((count + 1) / (frequency + 1));
    return [concept.index, concept.weight * idf];
  }));
}

function coverageForSet(set, weights, totalWeight) {
  let matched = 0;
  for (const index of set) matched += weights.get(index) || 0;
  return totalWeight > 0 ? matched / totalWeight : 0;
}

function bestTimeWindow(messages, weights, totalWeight, windowMs) {
  const sorted = [...messages].sort((a, b) => a.timestampMs - b.timestampMs || (a.lineNumber || 0) - (b.lineNumber || 0));
  const qualityBuckets = new Map();
  const outcomeBuckets = new Map();
  const outcomeRelevance = (message) => message.outcomeSignal
    * coverageForSet(new Set(message.conceptIds), weights, totalWeight);
  const addMessage = (message) => {
    for (const index of message.conceptIds) {
      if (!qualityBuckets.has(index)) qualityBuckets.set(index, new Map());
      const bucket = qualityBuckets.get(index);
      bucket.set(message.quality, (bucket.get(message.quality) || 0) + 1);
    }
    const outcome = outcomeRelevance(message);
    outcomeBuckets.set(outcome, (outcomeBuckets.get(outcome) || 0) + 1);
  };
  const removeMessage = (message) => {
    for (const index of message.conceptIds) {
      const bucket = qualityBuckets.get(index);
      if (!bucket) continue;
      const next = (bucket.get(message.quality) || 1) - 1;
      if (next <= 0) bucket.delete(message.quality); else bucket.set(message.quality, next);
      if (bucket.size === 0) qualityBuckets.delete(index);
    }
    const outcome = outcomeRelevance(message);
    const nextOutcome = (outcomeBuckets.get(outcome) || 1) - 1;
    if (nextOutcome <= 0) outcomeBuckets.delete(outcome); else outcomeBuckets.set(outcome, nextOutcome);
  };
  const weightedCoverage = () => {
    let matched = 0;
    for (const [index, bucket] of qualityBuckets) {
      const bestQuality = Math.max(...bucket.keys());
      matched += (weights.get(index) || 0) * bestQuality;
    }
    return totalWeight > 0 ? matched / totalWeight : 0;
  };
  let left = 0;
  let best = { coverage: 0, outcome: 0, start: 0, end: -1, conceptIds: new Set() };
  for (let right = 0; right < sorted.length; right += 1) {
    addMessage(sorted[right]);
    while (left < right
      && sorted[right].timestampMs
      && (!sorted[left].timestampMs || sorted[right].timestampMs - sorted[left].timestampMs > windowMs)) {
      removeMessage(sorted[left]);
      left += 1;
    }
    const conceptIds = new Set(qualityBuckets.keys());
    const coverage = weightedCoverage();
    const outcome = Math.max(...outcomeBuckets.keys(), 0);
    if (coverage > best.coverage
      || (coverage === best.coverage && outcome > best.outcome)
      || (coverage === best.coverage && outcome === best.outcome && right - left < best.end - best.start)) {
      best = { coverage, outcome, start: left, end: right, conceptIds };
    }
  }
  return { ...best, messages: best.end >= best.start ? sorted.slice(best.start, best.end + 1) : [] };
}

function proximitySignal(message) {
  if (message.conceptIds.length <= 1 || message.minimumSpan === null) return 0;
  if (message.minimumSpan <= 180) return 1;
  if (message.minimumSpan <= 800) return 0.72;
  if (message.minimumSpan <= 3000) return 0.42;
  return 0.15;
}

function selectEvidence(messages, weights, totalWeight, limit) {
  const remaining = [...messages];
  const selected = [];
  const covered = new Set();
  while (selected.length < limit && remaining.length > 0) {
    remaining.sort((a, b) => {
      const newA = a.conceptIds.filter((id) => !covered.has(id)).reduce((sum, id) => sum + (weights.get(id) || 0), 0);
      const newB = b.conceptIds.filter((id) => !covered.has(id)).reduce((sum, id) => sum + (weights.get(id) || 0), 0);
      const scoreA = (newA * 10 + coverageForSet(new Set(a.conceptIds), weights, totalWeight) * 4 + proximitySignal(a)) * a.quality + a.outcomeSignal * 2 + (a.role === "user" ? 0.25 : 0);
      const scoreB = (newB * 10 + coverageForSet(new Set(b.conceptIds), weights, totalWeight) * 4 + proximitySignal(b)) * b.quality + b.outcomeSignal * 2 + (b.role === "user" ? 0.25 : 0);
      return scoreB - scoreA || b.timestampMs - a.timestampMs;
    });
    const chosen = remaining.shift();
    selected.push(chosen);
    for (const id of chosen.conceptIds) covered.add(id);
  }
  if (limit > 1 && selected.length > 0) {
    const bestOutcome = [...messages].sort((a, b) => b.outcomeSignal - a.outcomeSignal || b.timestampMs - a.timestampMs)[0];
    if (bestOutcome?.outcomeSignal >= 0.8 && !selected.includes(bestOutcome)) selected[selected.length - 1] = bestOutcome;
  }
  return selected;
}

function scoreThread(thread, query, weights, options) {
  const allConceptIds = new Set(thread.messages.flatMap((message) => message.conceptIds));
  const totalWeight = [...weights.values()].reduce((sum, weight) => sum + weight, 0);
  const threadCoverage = coverageForSet(allConceptIds, weights, totalWeight);
  const window = bestTimeWindow(thread.messages, weights, totalWeight, options.windowDays * 86400000);
  let bestMessage = null;
  let bestMessageCoverage = 0;
  for (const message of thread.messages) {
    const coverage = coverageForSet(new Set(message.conceptIds), weights, totalWeight) * message.quality;
    if (!bestMessage || coverage + proximitySignal(message) * 0.15 > bestMessageCoverage + proximitySignal(bestMessage) * 0.15) {
      bestMessage = message;
      bestMessageCoverage = coverage;
    }
  }
  const proximity = bestMessage ? proximitySignal(bestMessage) : 0;
  const windowCoherence = window.coverage > 0 ? Math.min(1, bestMessageCoverage / window.coverage) : 0;
  // A broad time window may collect every clue from hundreds of unrelated messages.
  // Anchor window coverage to the strongest message so focused conversations beat
  // giant same-day corpora while still allowing genuine multi-message events.
  const effectiveWindowCoverage = window.coverage * (0.35 + 0.65 * windowCoherence);
  const userEvidence = window.messages.some((message) => message.role === "user") ? 1 : 0;
  const phraseEvidence = query.concepts.some((concept) => concept.source === "quoted_phrase" && allConceptIds.has(concept.index)) ? 1 : 0;
  const frequencySignal = Math.min(1, Math.log2(thread.messages.length + 1) / 5);
  const outcomeSignal = Math.max(...window.messages.map((message) => (message.outcomeSignal || 0)
    * coverageForSet(new Set(message.conceptIds), weights, totalWeight)), 0);
  const score = 50 * effectiveWindowCoverage
    + 20 * bestMessageCoverage
    + 20 * threadCoverage
    + 5 * proximity
    + 2.5 * userEvidence
    + 1.5 * phraseEvidence
    + 1 * frequencySignal
    + 6 * outcomeSignal;
  const evidencePool = window.messages.length > 0
    ? thread.messages.filter((message) => {
      if (!message.timestampMs) return window.messages.includes(message);
      const start = window.messages[0].timestampMs || message.timestampMs;
      const end = window.messages.at(-1).timestampMs || message.timestampMs;
      return message.timestampMs >= start - 86400000 && message.timestampMs <= end + 86400000;
    })
    : thread.messages;
  const evidence = selectEvidence(evidencePool, weights, totalWeight, options.excerpts).map((message) => ({
    timestamp: message.timestamp,
    role: message.role,
    lineNumber: message.lineNumber,
    matched: message.conceptIds.map((index) => query.concepts[index].label),
    excerpt: message.excerpt,
  }));
  const lastMatchMs = Math.max(...thread.messages.map((message) => message.timestampMs || 0), 0);
  const firstMatchMs = Math.min(...thread.messages.map((message) => message.timestampMs || Number.POSITIVE_INFINITY));
  return {
    ...thread,
    score: Math.round(score * 100) / 100,
    coverage: {
      thread: Math.round(threadCoverage * 1000) / 1000,
      bestWindow: Math.round(window.coverage * 1000) / 1000,
      effectiveWindow: Math.round(effectiveWindowCoverage * 1000) / 1000,
      windowCoherence: Math.round(windowCoherence * 1000) / 1000,
      bestMessage: Math.round(bestMessageCoverage * 1000) / 1000,
    },
    matchedConcepts: query.concepts.filter((concept) => allConceptIds.has(concept.index)).map((concept) => concept.label),
    unmatchedConcepts: query.concepts.filter((concept) => !allConceptIds.has(concept.index)).map((concept) => concept.label),
    bestWindow: {
      start: window.messages[0]?.timestamp || null,
      end: window.messages.at(-1)?.timestamp || null,
      messageCount: window.messages.length,
    },
    firstMatchAt: Number.isFinite(firstMatchMs) ? new Date(firstMatchMs).toISOString() : null,
    lastMatchAt: lastMatchMs ? new Date(lastMatchMs).toISOString() : null,
    evidence,
  };
}

async function hydrateResults(results) {
  if (results.length === 0) return { hydrated: 0, error: null };
  const rpc = join(HERE, "app_server_rpc.mjs");
  if (!existsSync(rpc)) return { hydrated: 0, error: "app_server_rpc.mjs was not found" };
  const requests = results.map((result, index) => ({
    id: 1000 + index,
    method: "thread/read",
    params: { threadId: result.id, includeTurns: false },
  }));
  const byRequestId = new Map(requests.map((request, index) => [request.id, results[index]]));
  const child = spawn(process.execPath, [rpc, "--stdin"], { windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
  let stderr = "";
  let hydrated = 0;
  const parser = consumeJsonLines((line) => {
    let message;
    try { message = JSON.parse(line); } catch { return; }
    const target = byRequestId.get(message.id);
    const thread = message.result?.thread;
    if (!target || !thread) return;
    target.name = typeof thread.name === "string" ? redactSensitiveText(thread.name) : target.name || null;
    target.preview = typeof thread.preview === "string" ? redactSensitiveText(thread.preview) : target.preview || null;
    target.cwd = thread.cwd || target.cwd;
    target.status = thread.status || null;
    target.recencyAt = thread.recencyAt || null;
    target.createdAtEpoch = thread.createdAt || null;
    target.updatedAtEpoch = thread.updatedAt || null;
    hydrated += 1;
  });
  child.stdout.on("data", (chunk) => parser.push(chunk.toString()));
  child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
  child.stdin.end(`${requests.map((request) => JSON.stringify(request)).join("\n")}\n`);
  const code = await new Promise((resolvePromise) => child.on("close", resolvePromise));
  parser.finish();
  return { hydrated, error: code === 0 ? null : (stderr.trim() || `app-server hydration exited ${code}`) };
}

function defaultRoots(options) {
  if (options.roots?.length) return options.roots.map((root) => resolve(root)).filter(existsSync);
  const codexHome = process.env.CODEX_HOME || join(process.env.USERPROFILE || process.env.HOME || ".", ".codex");
  const roots = [];
  if (options.archivedMode !== "archived") roots.push(join(codexHome, "sessions"));
  if (options.archivedMode !== "active") roots.push(join(codexHome, "archived_sessions"));
  return roots.filter(existsSync);
}

export async function searchThreads(options) {
  const normalizedOptions = {
    query: options.query,
    roots: options.roots || null,
    aliases: options.aliases || [],
    cwd: options.cwd || null,
    cwdMode: options.cwdMode || "exact",
    after: options.after || null,
    before: options.before || null,
    limit: Number.isFinite(options.limit) ? options.limit : 10,
    excerpts: Number.isFinite(options.excerpts) ? options.excerpts : 3,
    windowDays: Number.isFinite(options.windowDays) ? options.windowDays : 4,
    minScore: Number.isFinite(options.minScore) ? options.minScore : 18,
    includeSubagents: Boolean(options.includeSubagents),
    archivedMode: options.archivedMode || "both",
    includeThreadIds: new Set(options.includeThreadIds || []),
    excludeThreadIds: new Set(options.excludeThreadIds || []),
    hydrate: options.hydrate !== false,
  };
  const query = parseQuery(normalizedOptions.query, { aliases: normalizedOptions.aliases });
  const roots = defaultRoots(normalizedOptions);
  if (roots.length === 0) throw new Error("No Codex session roots were found.");
  let scanRoots = roots;
  if (normalizedOptions.includeThreadIds.size > 0) {
    const allPaths = (await Promise.all(roots.map(enumerateJsonl))).flat();
    scanRoots = allPaths.filter((file) => {
      const threadId = inferThreadId(file);
      return threadId && normalizedOptions.includeThreadIds.has(threadId);
    });
    if (scanRoots.length === 0) {
      throw new Error(`None of the requested task IDs were found: ${[...normalizedOptions.includeThreadIds].join(", ")}`);
    }
  }
  const scan = await scanCorpus(scanRoots, query);
  const records = await Promise.all([...scan.files.entries()].map(([file, messages]) => loadFileRecord(file, messages)));
  const afterMs = normalizedOptions.after ? Date.parse(normalizedOptions.after) : Number.NEGATIVE_INFINITY;
  const beforeMs = normalizedOptions.before ? Date.parse(normalizedOptions.before) : Number.POSITIVE_INFINITY;
  if (Number.isNaN(afterMs)) throw new Error(`Invalid --after date: ${normalizedOptions.after}`);
  if (Number.isNaN(beforeMs)) throw new Error(`Invalid --before date: ${normalizedOptions.before}`);

  const canonical = new Map();
  let excludedSubagentThreads = 0;
  for (const record of records) {
    if (normalizedOptions.includeThreadIds.size > 0 && !normalizedOptions.includeThreadIds.has(record.id)) continue;
    if (normalizedOptions.excludeThreadIds.has(record.id)) continue;
    if (!normalizedOptions.includeSubagents && isSubagentSource(record.source)) {
      excludedSubagentThreads += 1;
      continue;
    }
    if (normalizedOptions.archivedMode === "active" && record.archived) continue;
    if (normalizedOptions.archivedMode === "archived" && !record.archived) continue;
    if (!cwdMatches(record.cwd, normalizedOptions.cwd, normalizedOptions.cwdMode)) continue;
    record.messages = record.messages.filter((message) => message.timestampMs >= afterMs && message.timestampMs <= beforeMs);
    if (record.messages.length === 0) continue;
    const existing = canonical.get(record.id);
    canonical.set(record.id, existing ? chooseCanonical(existing, record) : record);
  }
  const threads = [...canonical.values()];
  const weights = conceptWeightMap(threads, query.concepts);
  const ranked = threads
    .map((thread) => scoreThread(thread, query, weights, normalizedOptions))
    .sort((a, b) => b.score - a.score
      || b.coverage.bestWindow - a.coverage.bestWindow
      || b.coverage.bestMessage - a.coverage.bestMessage
      || Date.parse(b.lastMatchAt || 0) - Date.parse(a.lastMatchAt || 0));
  const eligible = ranked.filter((result) => result.score >= normalizedOptions.minScore);
  const hydrationTargets = eligible.slice(0, Math.max(normalizedOptions.limit * 2, 20));
  const hydration = normalizedOptions.hydrate ? await hydrateResults(hydrationTargets) : { hydrated: 0, error: null };
  const results = eligible.slice(0, normalizedOptions.limit).map((result) => ({
    rank: 0,
    id: result.id,
    sessionId: result.sessionId,
    parentThreadId: result.parentThreadId,
    name: result.name || null,
    preview: result.preview || null,
    cwd: result.cwd,
    path: result.path,
    archived: result.archived,
    source: result.source,
    score: result.score,
    coverage: result.coverage,
    matchedConcepts: result.matchedConcepts,
    unmatchedConcepts: result.unmatchedConcepts,
    bestWindow: result.bestWindow,
    firstMatchAt: result.firstMatchAt,
    lastMatchAt: result.lastMatchAt,
    evidence: result.evidence,
  }));
  results.forEach((result, index) => { result.rank = index + 1; });
  return {
    query: query.source,
    concepts: query.concepts.map(({ id, label, source }) => ({ id, label, source })),
    roots,
    filters: {
      cwd: normalizedOptions.cwd,
      cwdMode: normalizedOptions.cwdMode,
      after: normalizedOptions.after,
      before: normalizedOptions.before,
      archivedMode: normalizedOptions.archivedMode,
      includeSubagents: normalizedOptions.includeSubagents,
      includedThreadIds: [...normalizedOptions.includeThreadIds],
      excludedThreadIds: [...normalizedOptions.excludeThreadIds],
    },
    stats: {
      ...scan.stats,
      engine: scan.engine,
      matchedPhysicalFiles: scan.files.size,
      candidateThreads: threads.length,
      eligibleThreads: eligible.length,
      excludedSubagentThreads,
      returned: results.length,
      hydration,
    },
    results,
  };
}

export function formatHumanReport(report) {
  const seconds = (report.stats.elapsedMs / 1000).toFixed(2);
  const lines = [
    `Thread content search: ${report.query}`,
    `Engine: ${report.stats.engine}; searched ${report.stats.filesSearched ?? "?"} files in ${seconds}s; ${report.stats.candidateThreads} candidate thread(s).`,
  ];
  if (report.filters.excludedThreadIds.length > 0) lines.push(`Excluded current/explicit thread(s): ${report.filters.excludedThreadIds.join(", ")}`);
  if (report.results.length === 0) {
    lines.push("No matching user/assistant thread content was found.");
    return lines.join("\n");
  }
  for (const result of report.results) {
    const title = result.name || result.preview?.slice(0, 80) || "Untitled thread";
    lines.push("");
    lines.push(`${result.rank}. ${title} — score ${result.score}`);
    lines.push(`   ID: ${result.id}${result.archived ? " (archived)" : ""}`);
    if (result.cwd) lines.push(`   CWD: ${result.cwd}`);
    lines.push(`   Matched: ${result.matchedConcepts.join(", ") || "none"}`);
    if (result.unmatchedConcepts.length > 0) lines.push(`   Missing: ${result.unmatchedConcepts.join(", ")}`);
    if (result.bestWindow.start || result.bestWindow.end) lines.push(`   Strongest window: ${result.bestWindow.start || "?"} → ${result.bestWindow.end || "?"}`);
    for (const evidence of result.evidence) {
      lines.push(`   - ${evidence.timestamp || "unknown time"} ${evidence.role}: ${evidence.excerpt}`);
    }
  }
  if (report.stats.hydration.error) lines.push(`\nTitle hydration warning: ${report.stats.hydration.error}`);
  return lines.join("\n");
}
