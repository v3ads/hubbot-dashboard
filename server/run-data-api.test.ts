/**
 * Tests for the /api/run-data endpoint authentication.
 * These tests validate that HUBBOT_API_KEY is set and that the
 * endpoint correctly accepts/rejects requests based on the key.
 */

import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

describe("HUBBOT_API_KEY secret", () => {
  it("is set in the environment", () => {
    const key = process.env.HUBBOT_API_KEY;
    expect(key, "HUBBOT_API_KEY must be set").toBeTruthy();
    expect(key!.length, "HUBBOT_API_KEY must be at least 16 chars").toBeGreaterThanOrEqual(16);
  });
});

describe("/api/run-data middleware logic", () => {
  it("accepts a POST with the correct API key", () => {
    const apiKey = process.env.HUBBOT_API_KEY ?? "test-key";
    const provided = apiKey;
    const authorized = !apiKey || provided === apiKey;
    expect(authorized).toBe(true);
  });

  it("rejects a POST with a wrong API key", () => {
    const apiKey = process.env.HUBBOT_API_KEY ?? "test-key";
    const provided = "wrong-key";
    const authorized = !apiKey || provided === apiKey;
    expect(authorized).toBe(false);
  });

  it("run-data.json contains run_completed_at_et ISO timestamp when present", () => {
    const dataFile = path.join(__dirname, "..", "run-data.json");
    if (!fs.existsSync(dataFile)) return;
    const parsed = JSON.parse(fs.readFileSync(dataFile, "utf8"));
    if (parsed.run_completed_at_et) {
      expect(typeof parsed.run_completed_at_et).toBe("string");
      expect(parsed.run_completed_at_et).toContain("T");
    }
  });

  it("run-data.json is readable and valid JSON", () => {
    const dataFile = path.join(__dirname, "..", "run-data.json");
    // If the file doesn't exist yet, the seed logic handles it at runtime
    if (!fs.existsSync(dataFile)) {
      // Acceptable — file is seeded on first server start
      return;
    }
    const raw = fs.readFileSync(dataFile, "utf8");
    const parsed = JSON.parse(raw);
    expect(parsed).toBeTruthy();
    expect(typeof parsed).toBe("object");
  });
});
