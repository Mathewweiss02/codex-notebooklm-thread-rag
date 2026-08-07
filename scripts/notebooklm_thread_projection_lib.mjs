import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { basename } from "node:path";

export const PROJECTION_POLICY_VERSION = "visible-messages-secrets-redacted-v2";

const SECRET_PATTERNS = [
  ["pem-private-key", /-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/g],
  ["aws-access-key", /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g],
  ["google-api-key", /\bAIza[0-9A-Za-z_-]{30,}\b/g],
  ["openai-key", /\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{12,}\b/g],
  ["github-token", /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b/g],
  ["slack-token", /\bxox[baprs]-[A-Za-z0-9-]{12,}\b/g],
  ["stripe-secret", /\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{12,}\b/g],
  ["jwt", /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g],
  ["authorization", /\b(?:Authorization\s*:\s*)?(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}/gi],
  ["cookie-header", /\b(?:Cookie|Set-Cookie)\s*:\s*[^\r\n]{12,}/gi],
  ["url-credential", /\bhttps?:\/\/([^\s:/?#]+):([^\s@/?#]+)@/gi],
  ["user-home-path", /\b[A-Za-z]:[\\/]Users[\\/][^\\/\s"'<>\]\)]+[\\/]/gi],
  ["unix-home-path", /(?:^|\s)\/(?:Users|home)\/[^/\s"'<>\]\)]+\//g],
  ["query-secret", /([?&](?:access_token|auth_token|api_key|apikey|client_secret|refresh_token|signature|sig)=)[^&\s#]+/gi],
  ["named-secret", /\b(password|passwd|pwd|secret|client[_ -]?secret|private[_ -]?key|refresh[_ -]?token|access[_ -]?token|auth[_ -]?token|api[_ -]?key|access[_ -]?key|session[_ -]?token)\s*[:=]\s*(?:["'][^"'\r\n]{6,}["']|[^\s,;\r\n]{6,})/gi],
  ["data-url", /data:[A-Za-z0-9.+/-]+;base64,[A-Za-z0-9+/=\r\n]{80,}/g],
  ["large-base64", /\b[A-Za-z0-9+/]{240,}={0,2}\b/g],
];

export function sha256(value) {
  return createHash("sha256").update(String(value ?? ""), "utf8").digest("hex");
}

export function sanitizeSecrets(value) {
  let text = String(value ?? "").replace(/\u0000/g, "");
  const counts = {};
  for (const [label, pattern] of SECRET_PATTERNS) {
    pattern.lastIndex = 0;
    text = text.replace(pattern, (match, prefix) => {
      counts[label] = (counts[label] || 0) + 1;
      if (label === "url-credential") return match.replace(/\/\/[^@]+@/, "//[REDACTED]@");
      if (label === "user-home-path") return "[USERPROFILE]\\";
      if (label === "unix-home-path") return `${/^\s/.test(match) ? match[0] : ""}[USERPROFILE]/`;
      if (label === "query-secret") return `${prefix}[REDACTED]`;
      if (label === "named-secret") {
        const name = match.match(/^\s*([^:=]+)\s*[:=]/)?.[1]?.trim() || "secret";
        return `${name}=[REDACTED]`;
      }
      if (label === "authorization") {
        const scheme = /Basic/i.test(match) ? "Basic" : "Bearer";
        return `${scheme} [REDACTED]`;
      }
      return `[REDACTED_${label.toUpperCase().replace(/-/g, "_")}]`;
    });
  }
  return { text, counts };
}

function addCounts(target, source) {
  for (const [key, value] of Object.entries(source || {})) target[key] = (target[key] || 0) + value;
}

function textFromContent(content) {
  return (Array.isArray(content) ? content : [content])
    .map((item) => {
      if (typeof item === "string") return item;
      if (typeof item?.text === "string") return item.text;
      if (typeof item?.content === "string") return item.content;
      return "";
    })
    .filter(Boolean)
    .join("\n");
}

function truncateMessage(text, maxChars) {
  if (text.length <= maxChars) return { text, truncated: false, originalChars: text.length };
  const marker = `\n\n[TRUNCATED_MIDDLE original_chars=${text.length} sha256=${sha256(text)}]\n\n`;
  const keep = Math.max(1, maxChars - marker.length);
  const first = Math.ceil(keep / 2);
  const last = Math.floor(keep / 2);
  return {
    text: `${text.slice(0, first)}${marker}${text.slice(text.length - last)}`,
    truncated: true,
    originalChars: text.length,
  };
}

export function visibleMessageFromEvent(event, options = {}) {
  if (event?.type !== "response_item" || event?.payload?.type !== "message") return null;
  const role = event.payload.role;
  if (role !== "user" && role !== "assistant") return null;
  const raw = textFromContent(event.payload.content);
  if (!raw.trim()) return null;
  const sanitized = sanitizeSecrets(raw);
  const truncated = truncateMessage(sanitized.text.trim(), options.maxMessageChars ?? 100_000);
  return {
    role,
    timestamp: event.timestamp || null,
    text: truncated.text,
    truncated: truncated.truncated,
    originalChars: truncated.originalChars,
    redactions: sanitized.counts,
  };
}

async function* boundedLines(file, maxLineBytes) {
  const input = createReadStream(file);
  let carry = Buffer.alloc(0);
  let dropping = false;
  let overflowPrefix = null;
  let lineNumber = 0;
  for await (const chunk of input) {
    let start = 0;
    for (let index = 0; index < chunk.length; index += 1) {
      if (chunk[index] !== 0x0a) continue;
      const segment = chunk.subarray(start, index);
      lineNumber += 1;
      if (dropping) {
        yield { lineNumber, text: null, overflow: true, prefix: overflowPrefix?.toString("utf8") || "" };
        dropping = false;
        overflowPrefix = null;
      } else if (carry.length + segment.length > maxLineBytes) {
        const prefix = carry.length ? Buffer.concat([carry, segment]) : segment;
        yield { lineNumber, text: null, overflow: true, prefix: prefix.subarray(0, 8192).toString("utf8") };
      } else {
        const line = carry.length ? Buffer.concat([carry, segment]) : segment;
        yield { lineNumber, text: line.toString("utf8").replace(/\r$/, ""), overflow: false };
      }
      carry = Buffer.alloc(0);
      start = index + 1;
    }
    const tail = chunk.subarray(start);
    if (dropping) continue;
    if (carry.length + tail.length > maxLineBytes) {
      const prefix = carry.length ? Buffer.concat([carry, tail]) : tail;
      overflowPrefix = prefix.subarray(0, 8192);
      carry = Buffer.alloc(0);
      dropping = true;
    } else if (tail.length) {
      carry = carry.length ? Buffer.concat([carry, tail]) : Buffer.from(tail);
    }
  }
  if (dropping) yield { lineNumber: lineNumber + 1, text: null, overflow: true, prefix: overflowPrefix?.toString("utf8") || "" };
  else if (carry.length) yield { lineNumber: lineNumber + 1, text: carry.toString("utf8").replace(/\r$/, ""), overflow: false };
}

export async function readVisibleMessages(file, options = {}) {
  const maxLineBytes = options.maxLineBytes ?? 4 * 1024 * 1024;
  const messages = [];
  const seen = new Set();
  const redactions = {};
  let overflowLines = 0;
  let overflowVisibleLines = 0;
  let malformedLines = 0;
  let duplicateMessages = 0;
  for await (const line of boundedLines(file, maxLineBytes)) {
    if (line.overflow) {
      overflowLines += 1;
      if (line.prefix?.includes('"type":"response_item"')
        && line.prefix.includes('"type":"message"')
        && (line.prefix.includes('"role":"user"') || line.prefix.includes('"role":"assistant"'))) overflowVisibleLines += 1;
      continue;
    }
    if (!line.text.includes('"type":"response_item"')
      || !line.text.includes('"type":"message"')
      || (!line.text.includes('"role":"user"') && !line.text.includes('"role":"assistant"'))) continue;
    let event;
    try { event = JSON.parse(line.text); } catch {
      malformedLines += 1;
      continue;
    }
    const message = visibleMessageFromEvent(event, options);
    if (!message) continue;
    const key = sha256(`${message.role}\0${message.timestamp || ""}\0${message.text}`);
    if (seen.has(key)) {
      duplicateMessages += 1;
      continue;
    }
    seen.add(key);
    addCounts(redactions, message.redactions);
    messages.push({ ...message, lineNumber: line.lineNumber });
  }
  return { messages, stats: { redactions, overflowLines, overflowVisibleLines, malformedLines, duplicateMessages } };
}

function wordCount(value) {
  return String(value || "").match(/\S+/g)?.length || 0;
}

function safeTitle(value, max = 140) {
  const sanitized = sanitizeSecrets(value || "Untitled Codex task").text
    .replace(/[\r\n\t]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return (sanitized || "Untitled Codex task").slice(0, max);
}

function isoFromSeconds(value) {
  return typeof value === "number" && Number.isFinite(value) ? new Date(value * 1000).toISOString() : null;
}

function workspaceIdentity(cwd) {
  if (!cwd) return { label: "unknown", hash: null };
  const normalized = String(cwd).replace(/^\\\\\?\\/, "").replace(/[\\/]+$/, "");
  return { label: safeTitle(basename(normalized), 80), hash: sha256(normalized.toLocaleLowerCase()).slice(0, 12) };
}

function renderHeader(metadata, part, totalParts) {
  return [
    `# ${metadata.title}`,
    "",
    "## Codex task provenance",
    "",
    `- Thread ID: \`${metadata.threadId}\``,
    `- Session ID: \`${metadata.sessionId || ""}\``,
    `- Forked from: \`${metadata.forkedFromId || ""}\``,
    `- Parent thread: \`${metadata.parentThreadId || ""}\``,
    `- Created: ${metadata.createdAt || ""}`,
    `- Updated: ${metadata.updatedAt || ""}`,
    `- Archived: ${metadata.archived}`,
    `- Device: \`${metadata.deviceId}\``,
    `- Workspace: \`${metadata.workspaceLabel}\` (${metadata.workspaceHash || "unknown"})`,
    `- Projection policy: \`${PROJECTION_POLICY_VERSION}\``,
    `- Part: ${part} of ${totalParts}`,
    "- Scope: visible user and Codex messages only; tool traces, reasoning, raw paths, and attachments are excluded.",
    "",
  ].join("\n");
}

function renderMessage(message, number) {
  const role = message.role === "user" ? "User" : "Codex";
  const details = [message.timestamp ? `timestamp=${message.timestamp}` : null, `source_line=${message.lineNumber}`, message.truncated ? `truncated_from=${message.originalChars}_chars` : null]
    .filter(Boolean)
    .join("; ");
  return `## Message ${number} — ${role}\n\n_${details}_\n\n${message.text.trim()}\n`;
}

export function renderThreadProjection(thread, visible, options = {}) {
  const deviceId = safeTitle(options.deviceId || "unknown-device", 64).toLocaleLowerCase().replace(/[^a-z0-9._-]+/g, "-");
  const workspace = workspaceIdentity(thread.cwd);
  const title = safeTitle(thread.name || thread.preview || thread.id);
  const metadata = {
    threadId: thread.id,
    sessionId: thread.sessionId || null,
    forkedFromId: thread.forkedFromId || null,
    parentThreadId: thread.parentThreadId || null,
    createdAt: isoFromSeconds(thread.createdAt),
    updatedAt: isoFromSeconds(thread.updatedAt),
    archived: Boolean(thread.archived),
    deviceId,
    workspaceLabel: workspace.label,
    workspaceHash: workspace.hash,
    title,
  };
  const renderedMessages = visible.messages.map(renderMessage);
  const maxWords = options.maxWords ?? 120_000;
  const chunks = [];
  let current = [];
  let currentWords = 0;
  for (const message of renderedMessages) {
    const count = wordCount(message);
    if (current.length && currentWords + count > maxWords) {
      chunks.push(current);
      current = [];
      currentWords = 0;
    }
    current.push(message);
    currentWords += count;
  }
  if (current.length || chunks.length === 0) chunks.push(current);
  const totalParts = chunks.length;
  const parts = chunks.map((messages, index) => {
    const body = messages.length ? messages.join("\n") : "## Messages\n\nNo visible user or Codex messages were found.\n";
    const text = `${renderHeader(metadata, index + 1, totalParts)}${body}`;
    return { part: index + 1, totalParts, text, words: wordCount(text), bytes: Buffer.byteLength(text, "utf8") };
  });
  const canonical = JSON.stringify({ policy: PROJECTION_POLICY_VERSION, metadata, messages: visible.messages.map(({ redactions, ...message }) => message) });
  return {
    metadata,
    contentDigest: sha256(canonical),
    parts,
    stats: {
      messages: visible.messages.length,
      truncatedMessages: visible.messages.filter((message) => message.truncated).length,
      ...visible.stats,
    },
  };
}

export function sourceTitle(projection, revision, part) {
  const meta = projection.metadata;
  const suffix = `r${String(revision).padStart(4, "0")} p${part.part}/${part.totalParts}`;
  return safeTitle(`Codex ${meta.deviceId} | ${meta.title} | ${meta.threadId.slice(0, 8)} | ${suffix}`, 190);
}
