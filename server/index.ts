import express from "express";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";

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

function readRunData(): object | null {
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

// ── Load HubBot playbook ─────────────────────────────────────────
function loadPlaybook(): string {
  // Try production path first (alongside server binary), then dev path
  const paths = [
    path.resolve(__dirname, "hubbot_playbook.txt"),
    path.resolve(__dirname, "..", "server", "hubbot_playbook.txt"),
  ];
  for (const p of paths) {
    if (fs.existsSync(p)) return fs.readFileSync(p, "utf8");
  }
  return "";
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
    // No-cache so the browser always fetches fresh data
    res.setHeader("Cache-Control", "no-store");
    res.json(data);
  });

  // ── POST /api/run-data  (protected by HUBBOT_API_KEY) ─────────
  app.post("/api/run-data", (req, res) => {
    const apiKey = process.env.HUBBOT_API_KEY;
    const provided = req.headers["x-hubbot-api-key"];

    if (!apiKey || provided !== apiKey) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }

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

  // ── POST /api/run-now  (protected by HUBBOT_API_KEY — triggers a new HubBot run) ──
  app.post("/api/run-now", async (req, res) => {
    const apiKey = process.env.HUBBOT_API_KEY;
    const provided = req.headers["x-hubbot-api-key"];

    if (!apiKey || provided !== apiKey) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }

    const manusApiKey = process.env.MANUS_API_KEY;
    if (!manusApiKey) {
      res.status(500).json({ error: "MANUS_API_KEY not configured" });
      return;
    }

    const playbook = loadPlaybook();
    if (!playbook) {
      res.status(500).json({ error: "HubBot playbook not found" });
      return;
    }

    try {
      const response = await fetch("https://api.manus.ai/v2/task.create", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-manus-api-key": manusApiKey,
        },
        body: JSON.stringify({
          title: "HubActually autonomous community admin (manual run)",
          prompt: playbook,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        console.error("[HubBot] run-now: Manus API error", response.status, errText);
        res.status(502).json({ error: `Manus API error: ${response.status}` });
        return;
      }

      const result = await response.json() as { task?: { id?: string; task_url?: string } };
      const taskId = result?.task?.id ?? "unknown";
      const taskUrl = result?.task?.task_url ?? `https://manus.im/app/${taskId}`;

      console.log("[HubBot] run-now: triggered task", taskId);
      res.json({ ok: true, task_id: taskId, task_url: taskUrl, triggered_at: new Date().toISOString() });
    } catch (err) {
      console.error("[HubBot] run-now: fetch error", err);
      res.status(500).json({ error: "Failed to trigger HubBot run" });
    }
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
