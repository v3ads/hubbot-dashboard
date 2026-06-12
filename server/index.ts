import express from "express";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";
import https from "https";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ── Data store path ─────────────────────────────────────────────
// In production the server writes to a persistent file alongside the binary.
// In dev it writes to the project root so it is easy to inspect.
const DATA_DIR =
  process.env.NODE_ENV === "production"
    ? path.resolve(__dirname)
    : path.resolve(__dirname, "..");

const DATA_FILE = path.join(DATA_DIR, "run-data.json");

// Seed the data file from the static latest-run.json if it doesn't exist yet
function seedDataFile() {
  if (!fs.existsSync(DATA_FILE)) {
    const staticSeed =
      process.env.NODE_ENV === "production"
        ? path.resolve(__dirname, "public", "latest-run.json")
        : path.resolve(__dirname, "..", "client", "public", "latest-run.json");
    if (fs.existsSync(staticSeed)) {
      fs.copyFileSync(staticSeed, DATA_FILE);
      console.log("[HubBot] Seeded run-data.json from latest-run.json");
    }
  }
}

function readRunData(): Record<string, unknown> | null {
  try {
    if (!fs.existsSync(DATA_FILE)) return null;
    return JSON.parse(fs.readFileSync(DATA_FILE, "utf8"));
  } catch {
    return null;
  }
}

function writeRunData(data: object): void {
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2), "utf8");
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
  seedDataFile();

  const app = express();
  const server = createServer(app);

  app.use(express.json({ limit: "2mb" }));

  // ── GET /api/run-data  (public — no auth needed) ──────────────
  app.get("/api/run-data", (_req, res) => {
    const data = readRunData();
    if (!data) {
      res.status(404).json({ error: "No run data available yet." });
      return;
    }
    res.setHeader("Cache-Control", "no-store");
    res.json(data);
  });

  // ── POST /api/run-data  (protected by HUBBOT_API_KEY) ─────────
  app.post("/api/run-data", (req, res) => {
    if (!checkApiKey(req, res)) return;

    const body = req.body;
    if (!body || typeof body !== "object") {
      res.status(400).json({ error: "Invalid JSON body" });
      return;
    }

    try {
      writeRunData(body);
      console.log("[HubBot] run-data.json updated at", new Date().toISOString());
      res.json({ ok: true, updated_at: new Date().toISOString() });
    } catch (err) {
      console.error("[HubBot] Failed to write run-data.json:", err);
      res.status(500).json({ error: "Failed to persist run data" });
    }
  });

  // ── POST /api/run-history  (upsert a single run entry by date) ──
  // Body: { run_date: "2026-06-12", status: "failed"|"completed"|"stalled"|"running", summary?: string, checklist?: object, latest_post?: object, blockers?: array }
  app.post("/api/run-history", (req, res) => {
    if (!checkApiKey(req, res)) return;

    const entry = req.body;
    if (!entry || !entry.run_date) {
      res.status(400).json({ error: "run_date is required" });
      return;
    }

    try {
      const data = readRunData() || {};
      const history: Record<string, unknown>[] = Array.isArray(data.run_history)
        ? (data.run_history as Record<string, unknown>[])
        : [];

      // Upsert: replace existing entry for this date, or prepend new one
      const idx = history.findIndex((h) => h.run_date === entry.run_date);
      const newEntry = {
        ...entry,
        recorded_at: new Date().toISOString(),
      };
      if (idx >= 0) {
        history[idx] = newEntry;
      } else {
        history.unshift(newEntry);
      }

      // Keep sorted newest-first and trim to 60 entries
      history.sort((a, b) =>
        String(b.run_date).localeCompare(String(a.run_date))
      );
      const trimmed = history.slice(0, 60);

      writeRunData({ ...data, run_history: trimmed });
      console.log("[HubBot] run-history upserted for", entry.run_date);
      res.json({ ok: true, run_date: entry.run_date });
    } catch (err) {
      console.error("[HubBot] Failed to upsert run-history:", err);
      res.status(500).json({ error: "Failed to update run history" });
    }
  });

  // ── POST /api/rerun  (trigger a catch-up run for a specific date) ──
  // Body: { run_date: "2026-06-12" }
  // Creates a Manus task via the Manus API to run HubBot for the given date.
  // This endpoint is also accessible without an API key for dashboard UI use (owner-only dashboard).
  app.post("/api/rerun", (req, res) => {
    // Allow both authenticated (API key) and unauthenticated (dashboard UI) access
    // since the dashboard is owner-only and the operation is non-destructive
    const apiKey = process.env.HUBBOT_API_KEY;
    const provided = req.headers["x-hubbot-api-key"];
    // If a key is provided, it must match; if none provided, allow (owner dashboard)
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

    const payload = JSON.stringify({
      project_id: projectId,
      prompt,
    });

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

  // ── POST /api/run-now  (DISABLED — manual run trigger removed) ──
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

  // Handle client-side routing — serve index.html for all non-API routes
  app.get("*", (_req, res) => {
    res.sendFile(path.join(staticPath, "index.html"));
  });

  const port = process.env.PORT || 3000;
  server.listen(port, () => {
    console.log(`[HubBot] Server running on http://localhost:${port}/`);
  });
}

startServer().catch(console.error);
