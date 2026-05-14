/* ============================================================
   HubBot Dashboard — Home Page
   Design: Terminal Ops Log (phosphor-green on near-black)
   Data source: /latest-run.json (fetched at runtime)
   ============================================================ */

import { useEffect, useState } from "react";

// ── Types ────────────────────────────────────────────────────

interface ChecklistItem {
  task: string;
  outcome: string;
}

interface RunData {
  run_date: string;
  run_weekday: string;
  timezone: string;
  status: string;
  last_run_label: string;
  primary_result: string;
  community: string;
  agent: string;
  published_post: {
    title: string;
    thread_url: string;
    category: string;
    image_url: string;
    image_attached: boolean;
  };
  checklist: ChecklistItem[];
  metrics: {
    required_tasks_completed: number;
    required_tasks_failed: number;
    owner_alerts_sent: number;
    posts_published: number;
    new_welcomes_sent: number;
  };
  blockers: string[];
  schedule: {
    cron: string;
    label: string;
    timezone: string;
    status: string;
  };
}

// ── Helpers ──────────────────────────────────────────────────

function outcomeClass(outcome: string): string {
  if (outcome === "completed") return "status-pill status-pill-green";
  if (outcome.startsWith("skipped")) return "status-pill status-pill-dim";
  if (outcome === "failed") return "status-pill status-pill-red";
  return "status-pill status-pill-amber";
}

function outcomeLabel(outcome: string): string {
  if (outcome === "completed") return "✓ completed";
  if (outcome === "skipped_not_saturday") return "— skipped / not saturday";
  if (outcome === "skipped_no_escalation") return "— skipped / no escalation";
  if (outcome === "failed") return "✗ failed";
  return outcome;
}

function statusPillClass(status: string): string {
  if (status === "completed") return "status-pill status-pill-green";
  if (status === "blocked") return "status-pill status-pill-red";
  if (status === "running") return "status-pill status-pill-amber";
  return "status-pill status-pill-dim";
}

// ── Sub-components ───────────────────────────────────────────

function Sidebar({ data }: { data: RunData | null }) {
  return (
    <aside
      style={{
        width: 220,
        minWidth: 220,
        borderRight: "1px solid var(--border)",
        padding: "1.5rem 1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
        background: "var(--card)",
      }}
    >
      {/* Agent identity */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem" }}>
          <div className="pulse-dot" />
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: "1rem",
              fontWeight: 600,
              color: "var(--terminal-green)",
            }}
          >
            HubBot
          </span>
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: "0.7rem",
              color: "var(--muted-foreground)",
            }}
          >
            v1
          </span>
        </div>
        <div className="term-label" style={{ marginBottom: "0.25rem" }}>community</div>
        <div className="term-value" style={{ fontSize: "0.78rem" }}>
          {data?.community ?? "HubActually"}
        </div>
      </div>

      <hr className="term-rule" style={{ margin: "0" }} />

      {/* Schedule */}
      <div>
        <div className="term-label" style={{ marginBottom: "0.5rem" }}>schedule</div>
        <div className="term-value" style={{ fontSize: "0.78rem", marginBottom: "0.25rem" }}>
          {data?.schedule.label ?? "Daily at 9:00 AM ET"}
        </div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "0.7rem", color: "var(--terminal-dim)" }}>
          {data?.schedule.cron ?? "0 0 9 * * *"}
        </div>
        <div style={{ marginTop: "0.5rem" }}>
          <span className={data?.schedule.status === "active" ? "status-pill status-pill-green" : "status-pill status-pill-amber"}>
            {data?.schedule.status ?? "active"}
          </span>
        </div>
      </div>

      <hr className="term-rule" style={{ margin: "0" }} />

      {/* Last run */}
      <div>
        <div className="term-label" style={{ marginBottom: "0.4rem" }}>last run</div>
        <div className="term-value" style={{ fontSize: "0.75rem", lineHeight: 1.5 }}>
          {data?.last_run_label ?? "—"}
        </div>
      </div>

      <hr className="term-rule" style={{ margin: "0" }} />

      {/* Metrics */}
      <div>
        <div className="term-label" style={{ marginBottom: "0.6rem" }}>metrics</div>
        {data ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {[
              ["posts published", data.metrics.posts_published],
              ["tasks completed", data.metrics.required_tasks_completed],
              ["tasks failed", data.metrics.required_tasks_failed],
              ["alerts sent", data.metrics.owner_alerts_sent],
              ["welcomes sent", data.metrics.new_welcomes_sent],
            ].map(([label, val]) => (
              <div key={String(label)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: "0.72rem", color: "var(--muted-foreground)" }}>
                  {label}
                </span>
                <span
                  className="term-value"
                  style={{
                    fontSize: "0.8rem",
                    color: label === "tasks failed" && Number(val) > 0 ? "var(--terminal-red)" : "var(--terminal-green)",
                  }}
                >
                  {val}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="term-value" style={{ fontSize: "0.78rem" }}>—</div>
        )}
      </div>
    </aside>
  );
}

function RunLedgerCard({ data }: { data: RunData }) {
  return (
    <div className="term-card card-enter" style={{ animationDelay: "0ms" }}>
      <div className="term-label" style={{ marginBottom: "0.75rem" }}>latest run ledger</div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
        <span className={statusPillClass(data.status)}>{data.status}</span>
        <span className="term-value" style={{ fontSize: "0.8rem" }}>{data.last_run_label}</span>
      </div>

      <div
        style={{
          fontFamily: "'IBM Plex Sans', sans-serif",
          fontSize: "0.85rem",
          color: "var(--foreground)",
          lineHeight: 1.6,
          marginBottom: "0.75rem",
        }}
      >
        {data.primary_result}
      </div>

      <hr className="term-rule" />

      {/* Checklist */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.4rem 1.5rem" }}>
        {data.checklist.map((item) => (
          <div key={item.task} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: "0.78rem", color: "var(--muted-foreground)" }}>
              {item.task}
            </span>
            <span className={outcomeClass(item.outcome)} style={{ whiteSpace: "nowrap" }}>
              {outcomeLabel(item.outcome)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PostCard({ data }: { data: RunData }) {
  const post = data.published_post;
  return (
    <div className="term-card card-enter" style={{ animationDelay: "40ms" }}>
      <div className="term-label" style={{ marginBottom: "0.75rem" }}>daily ai-news post</div>

      <div style={{ display: "flex", gap: "1rem", alignItems: "flex-start" }}>
        {post.image_url && (
          <img
            src={post.image_url}
            alt="Post cover"
            style={{
              width: 90,
              height: 64,
              objectFit: "cover",
              borderRadius: 2,
              border: "1px solid var(--border)",
              flexShrink: 0,
            }}
          />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontFamily: "'IBM Plex Sans', sans-serif",
              fontWeight: 600,
              fontSize: "0.9rem",
              color: "var(--foreground)",
              lineHeight: 1.4,
              marginBottom: "0.5rem",
            }}
          >
            {post.title}
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
            <span className="status-pill status-pill-dim">{post.category}</span>
            {post.image_attached && (
              <span className="status-pill status-pill-green">image attached</span>
            )}
          </div>
          <a
            href={post.thread_url}
            target="_blank"
            rel="noopener noreferrer"
            className="term-value"
            style={{
              fontSize: "0.72rem",
              textDecoration: "none",
              borderBottom: "1px solid oklch(0.78 0.22 155 / 0.4)",
              paddingBottom: "1px",
            }}
          >
            {post.thread_url}
          </a>
        </div>
      </div>
    </div>
  );
}

function BlockersCard({ blockers }: { blockers: string[] }) {
  return (
    <div className={`term-card card-enter ${blockers.length > 0 ? "term-card-red" : "term-card-dim"}`} style={{ animationDelay: "80ms" }}>
      <div className="term-label" style={{ marginBottom: "0.6rem" }}>blockers &amp; flagged items</div>
      {blockers.length === 0 ? (
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span className="status-pill status-pill-green">✓ no blockers recorded</span>
        </div>
      ) : (
        <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {blockers.map((b, i) => (
            <li key={i} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
              <span className="term-value" style={{ color: "var(--terminal-red)", flexShrink: 0 }}>✗</span>
              <span style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: "0.82rem", color: "var(--foreground)" }}>{b}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1rem",
        padding: "3rem",
        opacity: 0.6,
      }}
    >
      <div
        className="cursor-blink"
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: "1.1rem",
          color: "var(--terminal-green)",
        }}
      >
        awaiting first run
      </div>
      <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: "0.82rem", color: "var(--muted-foreground)" }}>
        Dashboard will populate after the first 9:00 AM ET run completes.
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────

export default function Home() {
  const [data, setData] = useState<RunData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/latest-run.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((json: RunData) => {
        setData(json);
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, []);

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "var(--background)",
        fontFamily: "'IBM Plex Sans', sans-serif",
      }}
    >
      {/* ── Top bar ── */}
      <header
        style={{
          borderBottom: "1px solid var(--border)",
          padding: "0.75rem 1.5rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "var(--card)",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 600,
              fontSize: "0.85rem",
              color: "var(--terminal-green)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            HubBot Dashboard
          </span>
          <span style={{ color: "var(--border)" }}>|</span>
          <span
            style={{
              fontFamily: "'IBM Plex Sans', sans-serif",
              fontSize: "0.78rem",
              color: "var(--muted-foreground)",
            }}
          >
            HubActually autonomous community admin
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {data && (
            <span className={statusPillClass(data.status)}>{data.status}</span>
          )}
          <a
            href="https://community.hubactually.com"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: "0.72rem",
              color: "var(--terminal-dim)",
              textDecoration: "none",
              borderBottom: "1px solid var(--border)",
              paddingBottom: "1px",
            }}
          >
            community ↗
          </a>
        </div>
      </header>

      {/* ── Body ── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <Sidebar data={data} />

        <main
          style={{
            flex: 1,
            padding: "1.5rem",
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: "1rem",
          }}
        >
          {loading && (
            <div
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: "0.82rem",
                color: "var(--terminal-dim)",
                padding: "2rem",
              }}
            >
              loading run ledger…
            </div>
          )}

          {error && (
            <div className="term-card term-card-red">
              <div className="term-label" style={{ marginBottom: "0.5rem" }}>error loading run data</div>
              <div className="term-value" style={{ color: "var(--terminal-red)", fontSize: "0.8rem" }}>{error}</div>
            </div>
          )}

          {!loading && !error && !data && <EmptyState />}

          {data && (
            <>
              <RunLedgerCard data={data} />
              <PostCard data={data} />
              <BlockersCard blockers={data.blockers} />
            </>
          )}
        </main>
      </div>

      {/* ── Footer ── */}
      <footer
        style={{
          borderTop: "1px solid var(--border)",
          padding: "0.5rem 1.5rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "var(--card)",
          flexShrink: 0,
        }}
      >
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "0.68rem", color: "var(--terminal-dim)" }}>
          data source: /latest-run.json
        </span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "0.68rem", color: "var(--terminal-dim)" }}>
          {data?.schedule.cron ?? "0 0 9 * * *"} · {data?.schedule.timezone ?? "America/New_York"}
        </span>
      </footer>
    </div>
  );
}
