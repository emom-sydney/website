#!/usr/bin/env node

// Admin API:
// - S3 presign endpoints for media uploads
// - SQLite-backed performer interest workflow
// - Optional SMTP mail delivery for workflow notifications

import fs from "fs";
import http from "http";
import path from "path";
import { randomBytes } from "crypto";
import { URL } from "url";
import { DatabaseSync } from "node:sqlite";
import { parse as parseCsv } from "csv-parse/sync";
import nodemailer from "nodemailer";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import galleries from "../src/_data/galleries.js";

const PORT = Number(process.env.ADMIN_PORT || 8787);
const BUCKET = process.env.S3_BUCKET || "sydney.emom.me";
const REGION = process.env.AWS_REGION || "ap-southeast-2";
const ADMIN_USER = process.env.ADMIN_USER;
const ADMIN_PASS = process.env.ADMIN_PASS;
const PRESIGN_EXPIRES = Math.min(
  Math.max(Number(process.env.PRESIGN_EXPIRES || 1800), 60),
  43200
);
const WORKFLOW_DB_PATH =
  process.env.WORKFLOW_DB_PATH ||
  path.join(process.cwd(), "data", "performer-workflow.sqlite");
const EVENTS_CSV_PATH = path.join(process.cwd(), "src", "_data", "events.csv");
const PUBLIC_SITE_URL = String(process.env.PUBLIC_SITE_URL || "").trim();
const MAIL_FROM = String(process.env.MAIL_FROM || "").trim();
const MAIL_REPLY_TO = String(process.env.MAIL_REPLY_TO || "").trim();
const SMTP_HOST = String(process.env.SMTP_HOST || "").trim();
const SMTP_PORT = Number(process.env.SMTP_PORT || 587);
const SMTP_SECURE = String(process.env.SMTP_SECURE || "").trim() === "true";
const SMTP_USER = String(process.env.SMTP_USER || "").trim();
const SMTP_PASS = String(process.env.SMTP_PASS || "");
const ALLOWED_STORAGE = new Set([
  "STANDARD",
  "STANDARD_IA",
  "ONEZONE_IA",
  "INTELLIGENT_TIERING",
  "DEEP_ARCHIVE",
  "GLACIER",
  "GLACIER_IR"
]);
const WORKFLOW_STATUSES = new Set([
  "new",
  "reviewing",
  "accepted",
  "waitlisted",
  "declined",
  "confirmed",
  "withdrawn",
  "change_requested",
  "cancelled_by_org"
]);

if (!ADMIN_USER || !ADMIN_PASS) {
  console.error("ADMIN_USER and ADMIN_PASS must be set");
  process.exit(1);
}

const s3 = new S3Client({ region: REGION });
const eventMap = loadEventMap();
const db = initWorkflowDb();
const mailer = createMailer();

const BASE_INTEREST_SELECT = `
SELECT
  pi.id,
  pi.performer_id,
  pi.event_id,
  pi.status,
  pi.set_description,
  pi.gear_notes,
  pi.availability,
  pi.manage_token,
  pi.created_at,
  pi.updated_at,
  pp.name,
  pp.stage_name,
  pp.email,
  pp.email_normalized,
  pp.mobile,
  pp.socials,
  pp.tech_notes,
  wl.id AS last_log_id,
  wl.action AS last_action,
  wl.actor AS last_actor,
  wl.note AS last_note,
  wl.created_at AS last_action_at
FROM performance_interest pi
JOIN performer_profiles pp ON pp.id = pi.performer_id
LEFT JOIN workflow_log wl ON wl.id = (
  SELECT id
  FROM workflow_log
  WHERE interest_id = pi.id
    AND action NOT IN ('interest_email_sent', 'admin_email_sent')
  ORDER BY id DESC
  LIMIT 1
)
`;

function loadEventMap() {
  if (!fs.existsSync(EVENTS_CSV_PATH)) {
    return new Map();
  }

  const csv = fs.readFileSync(EVENTS_CSV_PATH, "utf8");
  const rows = parseCsv(csv, {
    columns: true,
    skip_empty_lines: true,
    trim: true
  });

  return new Map(
    rows.map((row) => [
      String(row.ID),
      {
        id: String(row.ID),
        name: String(row.EventName || "").trim(),
        date: String(row.Date || "").trim(),
        typeId: String(row.TypeID || "").trim(),
        galleryUrl: String(row.GalleryURL || "").trim()
      }
    ])
  );
}

function initWorkflowDb() {
  fs.mkdirSync(path.dirname(WORKFLOW_DB_PATH), { recursive: true });
  const database = new DatabaseSync(WORKFLOW_DB_PATH);
  database.exec("PRAGMA foreign_keys = ON;");
  database.exec("PRAGMA journal_mode = WAL;");
  database.exec(`
    CREATE TABLE IF NOT EXISTS performer_profiles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      stage_name TEXT,
      email TEXT NOT NULL,
      email_normalized TEXT NOT NULL UNIQUE,
      mobile TEXT,
      socials TEXT,
      tech_notes TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS performance_interest (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      performer_id INTEGER NOT NULL,
      event_id TEXT NOT NULL,
      status TEXT NOT NULL,
      set_description TEXT,
      gear_notes TEXT,
      availability TEXT,
      manage_token TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY (performer_id) REFERENCES performer_profiles(id) ON DELETE CASCADE,
      UNIQUE (performer_id, event_id)
    );

    CREATE TABLE IF NOT EXISTS workflow_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      interest_id INTEGER NOT NULL,
      action TEXT NOT NULL,
      actor TEXT NOT NULL,
      note TEXT,
      metadata TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY (interest_id) REFERENCES performance_interest(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_interest_status ON performance_interest(status, updated_at DESC);
    CREATE INDEX IF NOT EXISTS idx_log_interest_id ON workflow_log(interest_id, id DESC);
  `);
  return database;
}

function createMailer() {
  if (!MAIL_FROM || !SMTP_HOST) {
    return {
      enabled: false,
      async sendMail({ to, subject, text }) {
        console.log("[mailer disabled]", JSON.stringify({ to, subject, text }, null, 2));
        return {
          enabled: false,
          sent: false,
          mode: "disabled"
        };
      }
    };
  }

  const transporter = nodemailer.createTransport({
    host: SMTP_HOST,
    port: SMTP_PORT,
    secure: SMTP_SECURE || SMTP_PORT === 465,
    auth: SMTP_USER ? { user: SMTP_USER, pass: SMTP_PASS } : undefined
  });

  return {
    enabled: true,
    async sendMail({ to, subject, text }) {
      const info = await transporter.sendMail({
        from: MAIL_FROM,
        replyTo: MAIL_REPLY_TO || undefined,
        to,
        subject,
        text
      });

      return {
        enabled: true,
        sent: true,
        mode: "smtp",
        messageId: info.messageId,
        accepted: Array.isArray(info.accepted) ? info.accepted : []
      };
    }
  };
}

function sendJson(res, status, payload = {}) {
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Allow-Methods": "OPTIONS, POST, GET"
  });
  res.end(JSON.stringify(payload));
}

function unauthorized(res) {
  res.writeHead(401, {
    "Content-Type": "application/json",
    "WWW-Authenticate": 'Basic realm="admin"',
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Allow-Methods": "OPTIONS, POST, GET"
  });
  res.end(JSON.stringify({ error: "unauthorized" }));
}

function badRequest(res, message, details) {
  sendJson(res, 400, details ? { error: message, details } : { error: message });
}

function notFound(res) {
  sendJson(res, 404, { error: "not found" });
}

function ok(res, payload) {
  sendJson(res, 200, payload);
}

function isAuthorized(req) {
  const header = req.headers.authorization;
  if (!header || !header.startsWith("Basic ")) return false;
  const decoded = Buffer.from(header.slice(6), "base64").toString("utf8");
  const [user, pass] = decoded.split(":");
  return user === ADMIN_USER && pass === ADMIN_PASS;
}

async function readJsonBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }

  if (!chunks.length) return {};

  const value = Buffer.concat(chunks).toString("utf8");
  try {
    return JSON.parse(value);
  } catch {
    throw new Error("Invalid JSON body");
  }
}

function nowIso() {
  return new Date().toISOString();
}

function cleanText(value, maxLength = 2000) {
  return String(value || "").trim().slice(0, maxLength);
}

function normalizeEmail(value) {
  return cleanText(value, 320).toLowerCase();
}

function sanitizePart(part) {
  return String(part || "")
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-.]+|[-.]+$/g, "")
    .slice(0, 100);
}

function buildKey({ gallery, subdir, filename }) {
  const safeGallery = sanitizePart(gallery);
  if (!safeGallery || !galleries.includes(safeGallery)) {
    throw new Error("Unknown gallery prefix");
  }

  const segments = ["gallery", safeGallery];
  if (subdir) {
    const parts = String(subdir)
      .split("/")
      .map(sanitizePart)
      .filter(Boolean);
    segments.push(...parts);
  }

  const safeFile = sanitizePart(filename);
  if (!safeFile) {
    throw new Error("Missing filename");
  }

  return segments.concat(safeFile).join("/");
}

function withTransaction(fn) {
  db.exec("BEGIN");
  try {
    const value = fn();
    db.exec("COMMIT");
    return value;
  } catch (err) {
    db.exec("ROLLBACK");
    throw err;
  }
}

function generateToken() {
  return randomBytes(24).toString("hex");
}

function getEventInfo(eventId) {
  const event = eventMap.get(String(eventId));
  if (!event) {
    return {
      id: String(eventId || ""),
      name: "Unknown event",
      date: "",
      label: `Unknown event (${eventId})`
    };
  }

  return {
    ...event,
    label: event.date ? `${event.name} (${event.date})` : event.name
  };
}

function resolveSiteBase(req) {
  if (PUBLIC_SITE_URL) {
    return PUBLIC_SITE_URL.replace(/\/+$/, "");
  }

  const origin = cleanText(req.headers.origin, 500);
  if (origin) return origin.replace(/\/+$/, "");

  const referer = cleanText(req.headers.referer, 1000);
  if (referer) {
    try {
      const parsed = new URL(referer);
      return parsed.origin;
    } catch {
      // Ignore invalid referer values.
    }
  }

  const host = cleanText(req.headers.host, 500);
  if (!host) {
    return "http://localhost:8080";
  }

  const proto = cleanText(req.headers["x-forwarded-proto"], 20) || "http";
  return `${proto}://${host}`;
}

function buildManageUrl(req, token) {
  return `${resolveSiteBase(req)}/perform/manage/index.html?token=${encodeURIComponent(token)}`;
}

function parseMetadata(jsonText) {
  if (!jsonText) return null;
  try {
    return JSON.parse(jsonText);
  } catch {
    return null;
  }
}

function fetchLogs(interestId, limit = 10) {
  const rows = db
    .prepare(
      `
      SELECT id, action, actor, note, metadata, created_at
      FROM workflow_log
      WHERE interest_id = ?
      ORDER BY id DESC
      LIMIT ?
      `
    )
    .all(Number(interestId), Number(limit));

  return rows.map((row) => ({
    id: row.id,
    action: row.action,
    actor: row.actor,
    note: row.note || "",
    metadata: parseMetadata(row.metadata),
    createdAt: row.created_at
  }));
}

function adminActionsForStatus(status) {
  switch (status) {
    case "new":
    case "reviewing":
      return ["accept", "waitlist", "decline", "ask_for_info"];
    case "accepted":
      return ["confirmation_reminder", "cancel_by_org"];
    case "confirmed":
      return ["cancel_by_org"];
    case "waitlisted":
      return ["accept", "decline", "ask_for_info"];
    case "withdrawn":
      return ["acknowledge_withdrawal"];
    case "change_requested":
      return ["acknowledge_change_request", "accept", "waitlist", "decline"];
    default:
      return [];
  }
}

function performerActionsForStatus(status) {
  const canEdit = !["declined", "cancelled_by_org"].includes(status);
  const canConfirm = ["accepted", "confirmed", "waitlisted", "change_requested"].includes(status);
  const canWithdraw = !["withdrawn", "declined", "cancelled_by_org"].includes(status);
  const canRequestChange = !["withdrawn", "declined", "cancelled_by_org"].includes(status);

  return {
    canEdit,
    canConfirm,
    canWithdraw,
    canRequestChange
  };
}

function mapInterestRow(row, includeLogs = false) {
  const event = getEventInfo(row.event_id);
  const interest = {
    id: row.id,
    event,
    status: row.status,
    setDescription: row.set_description || "",
    gearNotes: row.gear_notes || "",
    availability: row.availability || "",
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    performer: {
      id: row.performer_id,
      name: row.name,
      stageName: row.stage_name || "",
      email: row.email,
      mobile: row.mobile || "",
      socials: row.socials || "",
      techNotes: row.tech_notes || ""
    },
    lastActivity: row.last_action
      ? {
          action: row.last_action,
          actor: row.last_actor,
          note: row.last_note || "",
          createdAt: row.last_action_at
        }
      : null,
    availableAdminActions: adminActionsForStatus(row.status),
    performerCapabilities: performerActionsForStatus(row.status)
  };

  if (includeLogs) {
    interest.history = fetchLogs(row.id);
  }

  return interest;
}

function fetchInterestById(interestId, includeLogs = true) {
  const row = db.prepare(`${BASE_INTEREST_SELECT} WHERE pi.id = ?`).get(Number(interestId));
  return row ? mapInterestRow(row, includeLogs) : null;
}

function fetchInterestByToken(token, includeLogs = true) {
  const row = db.prepare(`${BASE_INTEREST_SELECT} WHERE pi.manage_token = ?`).get(String(token));
  return row ? mapInterestRow(row, includeLogs) : null;
}

function logWorkflow(interestId, action, actor, note = "", metadata = null) {
  db.prepare(
    `
    INSERT INTO workflow_log (interest_id, action, actor, note, metadata, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    `
  ).run(
    Number(interestId),
    String(action),
    String(actor),
    cleanText(note, 8000) || null,
    metadata ? JSON.stringify(metadata) : null,
    nowIso()
  );
}

function validateEventId(eventId) {
  if (!eventMap.has(String(eventId))) {
    throw new Error("Choose a valid event");
  }
}

function getProfileByEmail(emailNormalized) {
  return db
    .prepare(
      `
      SELECT id, email_normalized
      FROM performer_profiles
      WHERE email_normalized = ?
      `
    )
    .get(emailNormalized);
}

function getInterestRecordByPerformerAndEvent(performerId, eventId) {
  return db
    .prepare(
      `
      SELECT id, status, manage_token
      FROM performance_interest
      WHERE performer_id = ? AND event_id = ?
      `
    )
    .get(Number(performerId), String(eventId));
}

function createOrUpdateInterestSubmission(payload) {
  validateEventId(payload.eventId);

  return withTransaction(() => {
    const timestamp = nowIso();
    const existingProfile = getProfileByEmail(payload.emailNormalized);
    let performerId = existingProfile?.id;

    if (performerId) {
      db.prepare(
        `
        UPDATE performer_profiles
        SET name = ?, stage_name = ?, email = ?, email_normalized = ?, mobile = ?, socials = ?, tech_notes = ?, updated_at = ?
        WHERE id = ?
        `
      ).run(
        payload.name,
        payload.stageName || null,
        payload.email,
        payload.emailNormalized,
        payload.mobile || null,
        payload.socials || null,
        payload.techNotes || null,
        timestamp,
        performerId
      );
    } else {
      const result = db.prepare(
        `
        INSERT INTO performer_profiles (name, stage_name, email, email_normalized, mobile, socials, tech_notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        `
      ).run(
        payload.name,
        payload.stageName || null,
        payload.email,
        payload.emailNormalized,
        payload.mobile || null,
        payload.socials || null,
        payload.techNotes || null,
        timestamp,
        timestamp
      );
      performerId = Number(result.lastInsertRowid);
    }

    const existingInterest = getInterestRecordByPerformerAndEvent(performerId, payload.eventId);
    let interestId;
    let action = "interest_submitted";

    if (existingInterest) {
      const reopened = ["withdrawn", "declined", "cancelled_by_org"].includes(existingInterest.status);
      const nextStatus = reopened ? "new" : existingInterest.status;

      db.prepare(
        `
        UPDATE performance_interest
        SET status = ?, set_description = ?, gear_notes = ?, availability = ?, updated_at = ?
        WHERE id = ?
        `
      ).run(
        nextStatus,
        payload.setDescription || null,
        payload.gearNotes || null,
        payload.availability || null,
        timestamp,
        existingInterest.id
      );

      interestId = Number(existingInterest.id);
      action = reopened ? "interest_reopened" : "interest_updated";
    } else {
      const result = db.prepare(
        `
        INSERT INTO performance_interest (performer_id, event_id, status, set_description, gear_notes, availability, manage_token, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        `
      ).run(
        performerId,
        payload.eventId,
        "new",
        payload.setDescription || null,
        payload.gearNotes || null,
        payload.availability || null,
        generateToken(),
        timestamp,
        timestamp
      );
      interestId = Number(result.lastInsertRowid);
    }

    logWorkflow(interestId, action, "performer", "", {
      eventId: payload.eventId
    });

    return fetchInterestById(interestId);
  });
}

function ensureEmailAvailable(action, subject, body) {
  if (!subject || !body) {
    throw new Error(`Action "${action}" does not have an email body to send`);
  }
}

function templateWithNote(text, note) {
  const cleanNote = cleanText(note, 4000);
  if (!cleanNote) return text;
  return `${text}\n\nNote from EMOM:\n${cleanNote}`;
}

function buildEmailTemplate(action, interest, req, note = "") {
  const performerName = interest.performer.stageName || interest.performer.name;
  const eventLabel = interest.event.label;
  const manageUrl = buildManageUrl(req, fetchManageToken(interest.id));

  switch (action) {
    case "interest_submitted":
      return {
        subject: `We received your EMOM interest for ${interest.event.name}`,
        text: templateWithNote(
          `Hi ${performerName},

Thanks for submitting interest to perform at ${eventLabel}.

Use your private link to update your details, confirm later, withdraw, or request changes:
${manageUrl}

We will review the queue and email you when there is an update.`,
          note
        )
      };
    case "accept":
      return {
        subject: `EMOM performance update: accepted for ${interest.event.name}`,
        text: templateWithNote(
          `Hi ${performerName},

You have been accepted to perform at ${eventLabel}.

Please use your private link to confirm that you can still play:
${manageUrl}`,
          note
        )
      };
    case "waitlist":
      return {
        subject: `EMOM performance update: waitlisted for ${interest.event.name}`,
        text: templateWithNote(
          `Hi ${performerName},

You're currently on the waitlist for ${eventLabel}.

Keep your private link handy in case your plans change:
${manageUrl}`,
          note
        )
      };
    case "decline":
      return {
        subject: `EMOM performance update for ${interest.event.name}`,
        text: templateWithNote(
          `Hi ${performerName},

Thanks for your interest in ${eventLabel}. We are not able to offer you a slot for this event.

Your private link remains active if you need to review the original submission:
${manageUrl}`,
          note
        )
      };
    case "ask_for_info":
      return {
        subject: `EMOM needs more info for ${interest.event.name}`,
        text: templateWithNote(
          `Hi ${performerName},

We need a little more information before we can finalise your request for ${eventLabel}.

Please update your details using your private link:
${manageUrl}`,
          note
        )
      };
    case "confirmation_reminder":
      return {
        subject: `Please confirm your EMOM slot for ${interest.event.name}`,
        text: templateWithNote(
          `Hi ${performerName},

This is a reminder to confirm whether you can still play at ${eventLabel}.

Use your private link to confirm, withdraw, or request changes:
${manageUrl}`,
          note
        )
      };
    case "acknowledge_withdrawal":
      return {
        subject: `Withdrawal received for ${interest.event.name}`,
        text: templateWithNote(
          `Hi ${performerName},

Thanks for letting us know. We have marked you as withdrawn from ${eventLabel}.`,
          note
        )
      };
    case "acknowledge_change_request":
      return {
        subject: `Change request received for ${interest.event.name}`,
        text: templateWithNote(
          `Hi ${performerName},

We received your change request for ${eventLabel} and will review it shortly.

You can keep updating your details here:
${manageUrl}`,
          note
        )
      };
    case "cancel_by_org":
      return {
        subject: `EMOM update: ${interest.event.name} status changed`,
        text: templateWithNote(
          `Hi ${performerName},

We need to cancel your performance booking for ${eventLabel}.

Your private link is still available if you need to review the submission:
${manageUrl}`,
          note
        )
      };
    default:
      return null;
  }
}

function buildActionTemplate(action, interest, req) {
  const defaultNotes = {
    ask_for_info: "Please update your set details or let us know what has changed.",
    confirmation_reminder: "Please confirm if you can still play this event.",
    acknowledge_withdrawal: "Thanks for the update. We've marked this slot as withdrawn.",
    acknowledge_change_request: "Thanks for the update. We'll review the requested changes."
  };
  const emailTemplate = buildEmailTemplate(action, interest, req, defaultNotes[action] || "");

  return {
    action,
    note: defaultNotes[action] || "",
    sendEmail: Boolean(emailTemplate),
    email: emailTemplate
  };
}

function fetchManageToken(interestId) {
  const row = db
    .prepare(
      `
      SELECT manage_token
      FROM performance_interest
      WHERE id = ?
      `
    )
    .get(Number(interestId));
  return row?.manage_token || "";
}

async function maybeSendEmail({ to, subject, text }) {
  return mailer.sendMail({ to, subject, text });
}

async function handlePresign(req, res) {
  if (!isAuthorized(req)) return unauthorized(res);

  let body;
  try {
    body = await readJsonBody(req);
  } catch (err) {
    return badRequest(res, err.message);
  }

  const { gallery, subdir = "", filename, contentType, storageClass, metadata } = body || {};
  if (!gallery || !filename) {
    return badRequest(res, "gallery and filename are required");
  }

  let key;
  try {
    key = buildKey({ gallery, subdir, filename });
  } catch (err) {
    return badRequest(res, err.message);
  }

  const ct = contentType || "application/octet-stream";
  const sc = storageClass ? String(storageClass).toUpperCase() : "STANDARD";
  if (!ALLOWED_STORAGE.has(sc)) {
    return badRequest(res, "Invalid storage class");
  }

  const uploadUrl = await getSignedUrl(
    s3,
    new PutObjectCommand({
      Bucket: BUCKET,
      Key: key,
      ContentType: ct,
      StorageClass: sc
    }),
    { expiresIn: PRESIGN_EXPIRES }
  );

  let metadataUrl = null;
  let metadataKey = null;
  if (metadata && typeof metadata === "object" && Object.keys(metadata).length) {
    metadataKey = `${key}.meta.json`;
    metadataUrl = await getSignedUrl(
      s3,
      new PutObjectCommand({
        Bucket: BUCKET,
        Key: metadataKey,
        ContentType: "application/json"
      }),
      { expiresIn: PRESIGN_EXPIRES }
    );
  }

  ok(res, {
    key,
    uploadUrl,
    metadataKey,
    metadataUrl,
    expiresIn: PRESIGN_EXPIRES,
    bucket: BUCKET,
    storageClass: sc
  });
}

function validateInterestPayload(body) {
  const payload = {
    name: cleanText(body.name, 200),
    stageName: cleanText(body.stageName, 200),
    email: cleanText(body.email, 320),
    emailNormalized: normalizeEmail(body.email),
    mobile: cleanText(body.mobile, 80),
    socials: cleanText(body.socials, 500),
    techNotes: cleanText(body.techNotes, 2000),
    eventId: cleanText(body.eventId, 40),
    setDescription: cleanText(body.setDescription, 3000),
    gearNotes: cleanText(body.gearNotes, 3000),
    availability: cleanText(body.availability, 1000)
  };

  if (!payload.name) throw new Error("Name is required");
  if (!payload.email || !payload.email.includes("@")) throw new Error("A valid email is required");
  if (!payload.mobile) throw new Error("Mobile is required");
  if (!payload.eventId) throw new Error("Event is required");
  if (!payload.setDescription) throw new Error("Short set description is required");
  validateEventId(payload.eventId);

  return payload;
}

async function handlePerformerInterestSubmit(req, res) {
  let body;
  try {
    body = await readJsonBody(req);
  } catch (err) {
    return badRequest(res, err.message);
  }

  let payload;
  try {
    payload = validateInterestPayload(body);
  } catch (err) {
    return badRequest(res, err.message);
  }

  try {
    const interest = createOrUpdateInterestSubmission(payload);
    const emailTemplate = buildEmailTemplate("interest_submitted", interest, req);
    const mail = await maybeSendEmail({
      to: interest.performer.email,
      subject: emailTemplate.subject,
      text: emailTemplate.text
    });

    logWorkflow(interest.id, "interest_email_sent", "system", "", {
      template: "interest_submitted",
      mail
    });

    return ok(res, {
      success: true,
      interest,
      manageUrl: buildManageUrl(req, fetchManageToken(interest.id)),
      email: mail
    });
  } catch (err) {
    console.error("performer interest submit error", err);
    return sendJson(res, 500, { error: "internal error" });
  }
}

function extractBearerToken(req, url) {
  const header = cleanText(req.headers.authorization, 500);
  if (header.startsWith("Bearer ")) {
    return header.slice(7).trim();
  }
  return cleanText(url.searchParams.get("token"), 200);
}

async function handlePerformerManageGet(req, res, url) {
  const token = extractBearerToken(req, url);
  if (!token) {
    return badRequest(res, "Missing performer token");
  }

  const interest = fetchInterestByToken(token);
  if (!interest) {
    return sendJson(res, 404, { error: "invalid token" });
  }

  return ok(res, {
    success: true,
    interest
  });
}

function updatePerformerDetails(interestId, performerId, body) {
  const timestamp = nowIso();
  const name = cleanText(body.name, 200);
  const stageName = cleanText(body.stageName, 200);
  const email = cleanText(body.email, 320);
  const emailNormalized = normalizeEmail(email);
  const mobile = cleanText(body.mobile, 80);
  const socials = cleanText(body.socials, 500);
  const techNotes = cleanText(body.techNotes, 2000);
  const setDescription = cleanText(body.setDescription, 3000);
  const gearNotes = cleanText(body.gearNotes, 3000);
  const availability = cleanText(body.availability, 1000);

  if (!name) throw new Error("Name is required");
  if (!email || !email.includes("@")) throw new Error("A valid email is required");
  if (!mobile) throw new Error("Mobile is required");
  if (!setDescription) throw new Error("Short set description is required");

  const existing = getProfileByEmail(emailNormalized);
  if (existing && Number(existing.id) !== Number(performerId)) {
    throw new Error("That email is already attached to another performer profile");
  }

  withTransaction(() => {
    db.prepare(
      `
      UPDATE performer_profiles
      SET name = ?, stage_name = ?, email = ?, email_normalized = ?, mobile = ?, socials = ?, tech_notes = ?, updated_at = ?
      WHERE id = ?
      `
    ).run(
      name,
      stageName || null,
      email,
      emailNormalized,
      mobile,
      socials || null,
      techNotes || null,
      timestamp,
      Number(performerId)
    );

    db.prepare(
      `
      UPDATE performance_interest
      SET set_description = ?, gear_notes = ?, availability = ?, updated_at = ?
      WHERE id = ?
      `
    ).run(setDescription, gearNotes || null, availability || null, timestamp, Number(interestId));

    logWorkflow(interestId, "details_updated", "performer", "", {
      fields: ["profile", "interest"]
    });
  });
}

function applyPerformerAction(interest, action, note) {
  if (!WORKFLOW_STATUSES.has(interest.status)) {
    throw new Error("Unknown current workflow status");
  }

  const timestamp = nowIso();
  const cleanNoteValue = cleanText(note, 4000);

  return withTransaction(() => {
    switch (action) {
      case "confirm": {
        const nextStatus = interest.status === "accepted" ? "confirmed" : interest.status;
        db.prepare(
          `
          UPDATE performance_interest
          SET status = ?, updated_at = ?
          WHERE id = ?
          `
        ).run(nextStatus, timestamp, Number(interest.id));
        logWorkflow(
          interest.id,
          interest.status === "waitlisted" ? "availability_confirmed" : "confirmed_by_performer",
          "performer",
          cleanNoteValue || "Performer confirmed availability.",
          {
            previousStatus: interest.status,
            nextStatus
          }
        );
        break;
      }
      case "withdraw": {
        db.prepare(
          `
          UPDATE performance_interest
          SET status = ?, updated_at = ?
          WHERE id = ?
          `
        ).run("withdrawn", timestamp, Number(interest.id));
        logWorkflow(interest.id, "withdrawn_by_performer", "performer", cleanNoteValue, {
          previousStatus: interest.status,
          nextStatus: "withdrawn"
        });
        break;
      }
      case "request_change": {
        if (!cleanNoteValue) {
          throw new Error("Add a note so organisers know what needs to change");
        }
        db.prepare(
          `
          UPDATE performance_interest
          SET status = ?, updated_at = ?
          WHERE id = ?
          `
        ).run("change_requested", timestamp, Number(interest.id));
        logWorkflow(interest.id, "change_requested_by_performer", "performer", cleanNoteValue, {
          previousStatus: interest.status,
          nextStatus: "change_requested"
        });
        break;
      }
      default:
        throw new Error("Unsupported performer action");
    }

    return fetchInterestById(interest.id);
  });
}

async function handlePerformerManagePost(req, res, url) {
  const token = extractBearerToken(req, url);
  if (!token) {
    return badRequest(res, "Missing performer token");
  }

  const existing = fetchInterestByToken(token);
  if (!existing) {
    return sendJson(res, 404, { error: "invalid token" });
  }

  let body;
  try {
    body = await readJsonBody(req);
  } catch (err) {
    return badRequest(res, err.message);
  }

  const action = cleanText(body.action, 50);
  try {
    if (action === "update_details") {
      updatePerformerDetails(existing.id, existing.performer.id, body);
      return ok(res, {
        success: true,
        interest: fetchInterestById(existing.id)
      });
    }

    const interest = applyPerformerAction(existing, action, body.note);
    return ok(res, {
      success: true,
      interest
    });
  } catch (err) {
    return badRequest(res, err.message);
  }
}

function queueSectionsFromRows(rows) {
  const sections = [
    {
      key: "newInterest",
      label: "New interest",
      statuses: new Set(["new", "reviewing"])
    },
    {
      key: "acceptedAwaitingConfirmation",
      label: "Accepted, awaiting confirmation",
      statuses: new Set(["accepted"])
    },
    {
      key: "confirmed",
      label: "Confirmed",
      statuses: new Set(["confirmed"])
    },
    {
      key: "changeRequests",
      label: "Change requests",
      statuses: new Set(["change_requested"])
    },
    {
      key: "withdrawn",
      label: "Withdrawn",
      statuses: new Set(["withdrawn"])
    },
    {
      key: "waitlist",
      label: "Waitlist",
      statuses: new Set(["waitlisted"])
    },
    {
      key: "closed",
      label: "Closed",
      statuses: new Set(["declined", "cancelled_by_org"])
    }
  ];

  return sections.map((section) => ({
    key: section.key,
    label: section.label,
    items: rows.filter((row) => section.statuses.has(row.status))
  }));
}

function fetchQueueData() {
  const rows = db
    .prepare(`${BASE_INTEREST_SELECT} ORDER BY pi.updated_at DESC, pi.id DESC`)
    .all()
    .map((row) => mapInterestRow(row));

  return queueSectionsFromRows(rows);
}

async function handleAdminQueue(req, res) {
  if (!isAuthorized(req)) return unauthorized(res);
  return ok(res, {
    success: true,
    generatedAt: nowIso(),
    sections: fetchQueueData()
  });
}

function validateAdminAction(action) {
  const allowed = new Set([
    "accept",
    "waitlist",
    "decline",
    "ask_for_info",
    "confirmation_reminder",
    "acknowledge_withdrawal",
    "acknowledge_change_request",
    "cancel_by_org"
  ]);

  if (!allowed.has(action)) {
    throw new Error("Unknown admin action");
  }
}

async function handleAdminTemplate(req, res) {
  if (!isAuthorized(req)) return unauthorized(res);

  let body;
  try {
    body = await readJsonBody(req);
  } catch (err) {
    return badRequest(res, err.message);
  }

  const interestId = Number(body.interestId);
  const action = cleanText(body.action, 80);

  try {
    validateAdminAction(action);
  } catch (err) {
    return badRequest(res, err.message);
  }

  const interest = fetchInterestById(interestId, false);
  if (!interest) {
    return sendJson(res, 404, { error: "interest not found" });
  }

  return ok(res, {
    success: true,
    template: buildActionTemplate(action, interest, req)
  });
}

function adminActionStatus(action, currentStatus) {
  switch (action) {
    case "accept":
      return "accepted";
    case "waitlist":
      return "waitlisted";
    case "decline":
      return "declined";
    case "ask_for_info":
      return currentStatus === "new" ? "reviewing" : currentStatus;
    case "cancel_by_org":
      return "cancelled_by_org";
    default:
      return currentStatus;
  }
}

function adminWorkflowActionName(action) {
  switch (action) {
    case "accept":
      return "accepted_by_admin";
    case "waitlist":
      return "waitlisted_by_admin";
    case "decline":
      return "declined_by_admin";
    case "ask_for_info":
      return "info_requested";
    case "confirmation_reminder":
      return "confirmation_reminder_sent";
    case "acknowledge_withdrawal":
      return "withdrawal_acknowledged";
    case "acknowledge_change_request":
      return "change_request_acknowledged";
    case "cancel_by_org":
      return "cancelled_by_org";
    default:
      return action;
  }
}

async function handleAdminInterestAction(req, res) {
  if (!isAuthorized(req)) return unauthorized(res);

  let body;
  try {
    body = await readJsonBody(req);
  } catch (err) {
    return badRequest(res, err.message);
  }

  const interestId = Number(body.interestId);
  const action = cleanText(body.action, 80);
  const note = cleanText(body.note, 4000);
  const sendEmail = Boolean(body.sendEmail);
  const emailSubject = cleanText(body.emailSubject, 500);
  const emailBody = cleanText(body.emailBody, 12000);

  try {
    validateAdminAction(action);
  } catch (err) {
    return badRequest(res, err.message);
  }

  const existing = fetchInterestById(interestId, false);
  if (!existing) {
    return sendJson(res, 404, { error: "interest not found" });
  }

  const nextStatus = adminActionStatus(action, existing.status);
  const workflowAction = adminWorkflowActionName(action);
  const defaultTemplate = buildEmailTemplate(action, existing, req, note);

  let mail = null;

  try {
    const updated = withTransaction(() => {
      if (nextStatus !== existing.status) {
        db.prepare(
          `
          UPDATE performance_interest
          SET status = ?, updated_at = ?
          WHERE id = ?
          `
        ).run(nextStatus, nowIso(), Number(existing.id));
      } else {
        db.prepare(
          `
          UPDATE performance_interest
          SET updated_at = ?
          WHERE id = ?
          `
        ).run(nowIso(), Number(existing.id));
      }

      logWorkflow(existing.id, workflowAction, "admin", note, {
        previousStatus: existing.status,
        nextStatus,
        sendEmail
      });

      return fetchInterestById(existing.id);
    });

    if (sendEmail) {
      const subject = emailSubject || defaultTemplate?.subject;
      const text = emailBody || defaultTemplate?.text;
      ensureEmailAvailable(action, subject, text);
      mail = await maybeSendEmail({
        to: updated.performer.email,
        subject,
        text
      });
      logWorkflow(updated.id, "admin_email_sent", "system", "", {
        action,
        mail,
        subject
      });
    }

    return ok(res, {
      success: true,
      interest: fetchInterestById(existing.id),
      email: mail
    });
  } catch (err) {
    if (err.message?.startsWith("Action")) {
      return badRequest(res, err.message);
    }
    console.error("admin interest action error", err);
    return sendJson(res, 500, { error: "internal error" });
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (req.method === "OPTIONS") {
    res.writeHead(200, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Access-Control-Allow-Methods": "OPTIONS, POST, GET"
    });
    return res.end();
  }

  if (url.pathname === "/api/health") {
    return ok(res, {
      status: "ok",
      bucket: BUCKET,
      region: REGION,
      workflowDb: WORKFLOW_DB_PATH,
      mailEnabled: mailer.enabled
    });
  }

  if (url.pathname === "/api/presign" && req.method === "POST") {
    try {
      return await handlePresign(req, res);
    } catch (err) {
      console.error("presign error", err);
      return sendJson(res, 500, { error: "internal error" });
    }
  }

  if (url.pathname === "/api/performer-interest" && req.method === "POST") {
    return handlePerformerInterestSubmit(req, res);
  }

  if (url.pathname === "/api/performer/manage" && req.method === "GET") {
    return handlePerformerManageGet(req, res, url);
  }

  if (url.pathname === "/api/performer/manage" && req.method === "POST") {
    return handlePerformerManagePost(req, res, url);
  }

  if (url.pathname === "/api/admin/performer-queue" && req.method === "GET") {
    return handleAdminQueue(req, res);
  }

  if (url.pathname === "/api/admin/action-template" && req.method === "POST") {
    return handleAdminTemplate(req, res);
  }

  if (url.pathname === "/api/admin/interest-action" && req.method === "POST") {
    return handleAdminInterestAction(req, res);
  }

  return notFound(res);
});

server.listen(PORT, () => {
  console.log(`Admin API listening on http://localhost:${PORT}`);
  console.log(`Workflow DB: ${WORKFLOW_DB_PATH}`);
  console.log(`Workflow mail: ${mailer.enabled ? "smtp" : "disabled"}`);
});
