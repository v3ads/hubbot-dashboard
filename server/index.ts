import express from "express";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";
import https from "https";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ── Data store path ─────────────────────────────────────────────
// File is used as a local cache / fallback only.
// TiDB (DATABASE_URL) is the primary persistent store.
const DATA_DIR =
  process.env.NODE_ENV === "production"
    ? path.resolve(__dirname)
    : path.resolve(__dirname, "..");

const DATA_FILE = path.join(DATA_DIR, "run-data.json");

// ── TiDB helpers ─────────────────────────────────────────────────
// We use the raw `mysql2` package which is available in the Manus WebDev
// Node runtime.  We import it dynamically so the server still starts if the
// package is missing (file fallback takes over).

let dbPool: import("mysql2/promise").Pool | null = null;

async function getDbPool(): Promise<import("mysql2/promise").Pool | null> {
  if (dbPool) return dbPool;
  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) return null;
  try {
    const mysql = await import("mysql2/promise");
    // Parse mysql://user:pass@host:port/db
    const m = dbUrl.match(/mysql:\/\/([^:]+):([^@]+)@([^:]+):(\d+)\/([^?]+)/);
    if (!m) return null;
    const [, user, password, host, portStr, database] = m;
    dbPool = mysql.createPool({
      host,
      user,
      password,
      database,
      port: parseInt(portStr, 10),
      ssl: { rejectUnauthorized: false },
      waitForConnections: true,
      connectionLimit: 5,
      connectTimeout: 10000,
    });
    // Ensure the kv table exists
    await dbPool.execute(`
      CREATE TABLE IF NOT EXISTS hubbot_kv (
        k VARCHAR(64) NOT NULL PRIMARY KEY,
        v MEDIUMTEXT NOT NULL,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
      )
    `);
    console.log("[HubBot] TiDB connected — using database as primary store");
    return dbPool;
  } catch (err) {
    console.warn("[HubBot] TiDB unavailable, falling back to file store:", err);
    dbPool = null;
    return null;
  }
}

async function dbRead(): Promise<Record<string, unknown> | null> {
  try {
    const pool = await getDbPool();
    if (!pool) return null;
    const [rows] = await pool.execute("SELECT v FROM hubbot_kv WHERE k = 'run_data'") as [Array<{v: string}>, unknown];
    if (!rows.length) return null;
    return JSON.parse(rows[0].v);
  } catch {
    return null;
  }
}

async function dbWrite(data: object): Promise<boolean> {
  try {
    const pool = await getDbPool();
    if (!pool) return false;
    await pool.execute(
      "INSERT INTO hubbot_kv (k, v, updated_at) VALUES ('run_data', ?, NOW()) ON DUPLICATE KEY UPDATE v = VALUES(v), updated_at = NOW()",
      [JSON.stringify(data)]
    );
    return true;
  } catch (err) {
    console.warn("[HubBot] DB write failed:", err);
    return false;
  }
}

// ── File helpers (fallback) ───────────────────────────────────────
function fileRead(): Record<string, unknown> | null {
  try {
    if (!fs.existsSync(DATA_FILE)) return null;
    return JSON.parse(fs.readFileSync(DATA_FILE, "utf8"));
  } catch {
    return null;
  }
}

function fileWrite(data: object): void {
  try {
    fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2), "utf8");
  } catch (err) {
    console.warn("[HubBot] File write failed:", err);
  }
}

// ── Seed on startup ───────────────────────────────────────────────
// On cold start: load from DB first. If DB is empty, seed from the bundled
// latest-run.json and write it to DB so future restarts also get it from DB.
async function seedOnStartup(): Promise<void> {
  const staticSeed =
    process.env.NODE_ENV === "production"
      ? path.resolve(__dirname, "public", "latest-run.json")
      : path.resolve(__dirname, "..", "client", "public", "latest-run.json");

  // 1. Try DB first
  const dbData = await dbRead();
  if (dbData) {
    console.log(`[HubBot] Loaded run data from DB (run_date: ${dbData.run_date})`);
    // Also sync to local file cache
    fileWrite(dbData);
    return;
  }

  // 2. DB empty — try local file
  const fileData = fileRead();
  if (fileData && fileData.run_date) {
    console.log(`[HubBot] DB empty — seeding from local file (run_date: ${fileData.run_date})`);
    await dbWrite(fileData);
    return;
  }

  // 3. Try bundled seed
  if (fs.existsSync(staticSeed)) {
    try {
      const seedData = JSON.parse(fs.readFileSync(staticSeed, "utf8"));
      console.log(`[HubBot] Seeding from bundled latest-run.json (run_date: ${seedData.run_date})`);
      fileWrite(seedData);
      await dbWrite(seedData);
    } catch (err) {
      console.warn("[HubBot] Failed to read seed file:", err);
    }
  }
}

// ── Unified read/write ────────────────────────────────────────────
async function readRunData(): Promise<Record<string, unknown> | null> {
  // DB first, file fallback
  const dbData = await dbRead();
  if (dbData) return dbData;
  return fileRead();
}

async function writeRunData(data: object): Promise<void> {
  // Write to DB (primary) and file (cache)
  const dbOk = await dbWrite(data);
  fileWrite(data);
  if (!dbOk) {
    console.warn("[HubBot] DB write failed — data saved to file only");
  }
}

// ── Auth helper ──────────────────────────────────────────────────
function checkApiKey(req: express.Request, res: express.Response): boolean {
  const apiKey = process.env.HUBBOT_API_KEY;
  const provided = req.headers["x-hubbot-api-key"];
  if (!apiKey || provided !== apiKey) {
    res.status(401).json({ error: "Unauthorized" });
    return false;
  }
  return true;
}

// ── Server ───────────────────────────────────────────────────────
async function startServer() {
  await seedOnStartup();

  const app = express();
  const server = createServer(app);

  app.use(express.json({ limit: "2mb" }));

  // ── GET /api/run-data  (public — no auth needed) ──────────────
  app.get("/api/run-data", async (_req, res) => {
    const data = await readRunData();
    if (!data) {
      res.status(404).json({ error: "No run data available yet." });
      return;
    }
    res.setHeader("Cache-Control", "no-store");
    res.json(data);
  });

  // ── POST /api/run-data  (protected by HUBBOT_API_KEY) ─────────
  app.post("/api/run-data", async (req, res) => {
    if (!checkApiKey(req, res)) return;

    const body = req.body;
    if (!body || typeof body !== "object") {
      res.status(400).json({ error: "Invalid JSON body" });
      return;
    }

    try {
      await writeRunData(body);
      console.log("[HubBot] run data updated at", new Date().toISOString());
      res.json({ ok: true, updated_at: new Date().toISOString() });
    } catch (err) {
      console.error("[HubBot] Failed to write run data:", err);
      res.status(500).json({ error: "Failed to persist run data" });
    }
  });

  // ── POST /api/run-history  (upsert a single run entry by date) ──
  app.post("/api/run-history", async (req, res) => {
    if (!checkApiKey(req, res)) return;

    const entry = req.body;
    if (!entry || !entry.run_date) {
      res.status(400).json({ error: "run_date is required" });
      return;
    }

    try {
      const data = (await readRunData()) || {};
      const history: Record<string, unknown>[] = Array.isArray(data.run_history)
        ? (data.run_history as Record<string, unknown>[])
        : [];

      const idx = history.findIndex((h) => h.run_date === entry.run_date);
      const newEntry = { ...entry, recorded_at: new Date().toISOString() };
      if (idx >= 0) {
        history[idx] = newEntry;
      } else {
        history.unshift(newEntry);
      }

      history.sort((a, b) => String(b.run_date).localeCompare(String(a.run_date)));
      const trimmed = history.slice(0, 60);

      await writeRunData({ ...data, run_history: trimmed });
      console.log("[HubBot] run-history upserted for", entry.run_date);
      res.json({ ok: true, run_date: entry.run_date });
    } catch (err) {
      console.error("[HubBot] Failed to upsert run-history:", err);
      res.status(500).json({ error: "Failed to update run history" });
    }
  });

  // ── POST /api/rerun  (trigger a catch-up run for a specific date) ──
  app.post("/api/rerun", (req, res) => {
    const apiKey = process.env.HUBBOT_API_KEY;
    const provided = req.headers["x-hubbot-api-key"];
    if (provided && apiKey && provided !== apiKey) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }

    const { run_date } = req.body || {};
    if (!run_date) {
      res.status(400).json({ error: "run_date is required" });
      return;
    }

    const manusApiKey = process.env.MANUS_API_KEY;
    if (!manusApiKey) {
      res.status(503).json({ error: "MANUS_API_KEY not configured" });
      return;
    }

    const projectId = "5QxQCU6iNAWbRVxntRM63p";
    const prompt = `HUBBOT CATCH-UP RUN for ${run_date}.\n\nThe scheduled HubBot run for ${run_date} did not complete successfully. Please run the full HubBot daily playbook now as a catch-up run for ${run_date}. Follow the HUBBOT_PLAYBOOK exactly. This is a manual catch-up triggered from the dashboard.`;

    const payload = JSON.stringify({ project_id: projectId, prompt });

    const options = {
      hostname: "api.manus.im",
      path: "/api/v1/tasks",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${manusApiKey}`,
        "Content-Length": Buffer.byteLength(payload),
      },
    };

    const apiReq = https.request(options, (apiRes) => {
      let body = "";
      apiRes.on("data", (chunk) => (body += chunk));
      apiRes.on("end", () => {
        try {
          const result = JSON.parse(body);
          if (apiRes.statusCode && apiRes.statusCode >= 200 && apiRes.statusCode < 300) {
            console.log("[HubBot] Rerun task created for", run_date, result.task_id || result.id);
            res.json({ ok: true, run_date, task_id: result.task_id || result.id, task_url: result.url });
          } else {
            console.error("[HubBot] Manus API error:", apiRes.statusCode, body);
            res.status(502).json({ error: "Failed to create Manus task", detail: body });
          }
        } catch {
          res.status(502).json({ error: "Invalid response from Manus API" });
        }
      });
    });

    apiReq.on("error", (err) => {
      console.error("[HubBot] Manus API request error:", err);
      res.status(502).json({ error: "Network error contacting Manus API" });
    });

    apiReq.write(payload);
    apiReq.end();
  });

  // ── POST /api/run-now  (DISABLED) ──
  app.post("/api/run-now", (_req, res) => {
    res.status(404).json({ error: "Manual run trigger is disabled. Use /api/rerun with a run_date." });
  });

  // ── GET /api/community-token  (protected by HUBBOT_API_KEY) ─────
  app.get("/api/community-token", (req, res) => {
    if (!checkApiKey(req, res)) return;
    const token = process.env.COMMUNITY_ESTAGE_TOKEN || "";
    if (!token) {
      res.status(404).json({ error: "COMMUNITY_ESTAGE_TOKEN not configured" });
      return;
    }
    res.setHeader("Cache-Control", "no-store");
    res.json({ token });
  });

  // ── Static files ─────────────────────────────────────────────
  const staticPath =
    process.env.NODE_ENV === "production"
      ? path.resolve(__dirname, "public")
      : path.resolve(__dirname, "..", "dist", "public");

  app.use(express.static(staticPath));

  app.get("*", (_req, res) => {
    res.sendFile(path.join(staticPath, "index.html"));
  });

  const port = process.env.PORT || 3000;
  server.listen(port, () => {
    console.log(`[HubBot] Server running on http://localhost:${port}/`);
  });
}

startServer().catch(console.error);
