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

  // ── POST /api/run-now  (DISABLED — manual run trigger removed) ──
  app.post("/api/run-now", (_req, res) => {
    res.status(404).json({ error: "Manual run trigger is disabled. HubBot runs on its autonomous daily schedule." });
  });

  // ── GET /api/community-token  (protected by HUBBOT_API_KEY) ─────
  // Returns the COMMUNITY_ESTAGE_TOKEN for use by the scheduled HubBot task.
  // This is the permanent fix for scheduled runs that start in a fresh sandbox
  // with no browser cookies — the token is stored securely as a webdev secret.
  app.get("/api/community-token", (req, res) => {
    const apiKey = process.env.HUBBOT_API_KEY;
    const provided = req.headers["x-hubbot-api-key"];
    if (!apiKey || provided !== apiKey) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }
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
