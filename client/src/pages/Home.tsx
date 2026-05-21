/* ============================================================
   HubBot Dashboard — Home Page
   Design: Terminal Ops Log (phosphor-green on near-black)
   Data source: /api/run-data (fetched at runtime — no-cache)
   Mobile: sidebar collapses to horizontal strip on small screens
   ============================================================ */

import { useCallback, useEffect, useState } from "react";

// ── Types ────────────────────────────────────────────────────

interface ChecklistItem {
  task: string;
  outcome: string;
}

interface RunHistoryEntry {
  run_date: string;
  status: string;
  primary_result: string;
  posts_published: number;
  tasks_completed: number;
  tasks_failed: number;
  error_detail?: string;
  blockers?: string[];
}

interface RunData {
  run_date: string;
  run_completed_at_et?: string;
  run_weekday: string;
  timezone: string;
  status: string;
  last_run_label: string;
  primary_result: string;
  community: string;
  agent: string;
  agent_version?: string;
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
  saturday_digest?: {
    status: string; // "sent" | "skipped_not_saturday" | "blocked"
    sent_at_et?: string;
    recipient_count?: number;
    subject?: string;
    reason?: string;
  };
  run_history?: RunHistoryEntry[];
  community_stats?: {
    fetched_at: string;
    total_members: number;
    new_members_7d: number;
    new_members_30d: number | null;
    active_members_7d: number | null;
    total_posts: number | null;
    new_members_7d_list: { name: string; joined: string }[];
    interesting_posts: {
      title: string;
      author: string;
      likes: number;
      comments: number;
      url: string;
      date: string;
    }[];
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
  if (outcome === "skipped_existing_post") return "— skipped / existing post";
  if (outcome === "skipped_existing_same_day_post") return "— skipped / existing same-day post";
  if (outcome === "failed") return "✗ failed";
  return outcome;
}

function relativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch {
    return iso;
  }
}

function RelativeTime({ iso, fallback }: { iso: string; fallback?: string }) {
  const [label, setLabel] = useState(() => relativeTime(iso));
  useEffect(() => {
    setLabel(relativeTime(iso));
    const id = setInterval(() => setLabel(relativeTime(iso)), 60000);
    return () => clearInterval(id);
  }, [iso]);
  if (!iso.includes("T") && fallback) return <>{fallback}</>;
  return <>{label}</>;
}

function statusPillClass(status: string): string {
  if (status === "completed") return "status-pill status-pill-green";
  if (status === "blocked") return "status-pill status-pill-red";
  if (status === "schedule_missing") return "status-pill status-pill-amber";
  if (status === "running") return "status-pill status-pill-amber";
  return "status-pill status-pill-dim";
}

// ── Sidebar (desktop: left column | mobile: top strip) ───────

function Sidebar({ data }: { data: RunData | null }) {
  const metrics = data
    ? [
        ["posts published", data.metrics.posts_published],
        ["tasks completed", data.metrics.required_tasks_completed],
        ["tasks failed", data.metrics.required_tasks_failed],
        ["alerts sent", data.metrics.owner_alerts_sent],
        ["welcomes sent", data.metrics.new_welcomes_sent],
      ]
    : [];

  return (
    <aside className="hubbot-sidebar">
      {/* Identity row */}
      <div className="sidebar-identity">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div className="pulse-dot" />
          <span className="sidebar-agent-name">HubBot</span>
          <span className="sidebar-agent-version">{data?.agent_version ?? "v2"}</span>
        </div>
        <div className="sidebar-community-label">
          <span className="term-label">community</span>
          <span className="term-value sidebar-community-value">
            {data?.community ?? "HubActually"}
          </span>
        </div>
      </div>

      <div className="sidebar-divider" />

      {/* Schedule */}
      <div className="sidebar-section">
        <div className="term-label sidebar-section-title">schedule</div>
        <div className="term-value" style={{ fontSize: "0.78rem", marginBottom: "0.2rem" }}>
          {data?.schedule.label ?? "Daily at 9:00 AM ET"}
        </div>
        <div className="sidebar-cron">
          {data?.schedule.cron ?? "0 0 9 * * *"}
        </div>
        <div style={{ marginTop: "0.4rem" }}>
          <span className={data?.schedule.status === "active" ? "status-pill status-pill-green" : "status-pill status-pill-amber"}>
            {data?.schedule.status ?? "active"}
          </span>
        </div>
      </div>

      <div className="sidebar-divider" />

      {/* Last run */}
      <div className="sidebar-section">
        <div className="term-label sidebar-section-title">last run</div>
        <div className="term-value" style={{ fontSize: "0.75rem", lineHeight: 1.5 }}>
          {data?.last_run_label ?? "—"}
        </div>
      </div>

      <div className="sidebar-divider" />

      {/* Metrics */}
      <div className="sidebar-section">
        <div className="term-label sidebar-section-title">metrics</div>
        {data ? (
          <div className="metrics-grid">
            {metrics.map(([label, val]) => (
              <div key={String(label)} className="metric-row">
                <span className="metric-label">{label}</span>
                <span
                  className="term-value"
                  style={{
                    fontSize: "0.8rem",
                    color:
                      label === "tasks failed" && Number(val) > 0
                        ? "var(--terminal-red)"
                        : "var(--terminal-green)",
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

// ── Cards ─────────────────────────────────────────────────────

function RunLedgerCard({ data }: { data: RunData }) {
  return (
    <div className="term-card card-enter" style={{ animationDelay: "0ms" }}>
      <div className="term-label" style={{ marginBottom: "0.75rem" }}>latest run ledger</div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
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

      {/* Checklist — 2 cols on desktop, 1 col on mobile */}
      <div className="checklist-grid">
        {data.checklist.map((item) => (
          <div key={item.task} className="checklist-row">
            <span className="checklist-task">{item.task}</span>
            <span className={outcomeClass(item.outcome)} style={{ whiteSpace: "nowrap", flexShrink: 0 }}>
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

      <div className="post-card-inner">
        {post.image_url && (
          <img
            src={post.image_url}
            alt="Post cover"
            className="post-thumb"
          />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="post-title">{post.title}</div>
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
            className="term-value post-link"
          >
            {post.thread_url}
          </a>
        </div>
      </div>
    </div>
  );
}

function CommunityStatsCard({ stats }: { stats: NonNullable<RunData["community_stats"]> }) {
  return (
    <div className="term-card card-enter" style={{ animationDelay: "120ms" }}>
      <div className="term-label" style={{ marginBottom: "0.85rem" }}>community stats</div>

      {/* Top-level numbers */}
      <div className="comm-stat-grid">
        <div className="comm-stat-tile">
          <div className="comm-stat-value">{stats.total_members}</div>
          <div className="comm-stat-label">total members</div>
        </div>
        <div className="comm-stat-tile">
          <div className="comm-stat-value" style={{ color: stats.new_members_7d > 0 ? "var(--terminal-green)" : "var(--terminal-dim)" }}>
            +{stats.new_members_7d}
          </div>
          <div className="comm-stat-label">new (7 days)</div>
        </div>
        <div className="comm-stat-tile">
          <div className="comm-stat-value">{stats.active_members_7d ?? "—"}</div>
          <div className="comm-stat-label">active (7 days)</div>
        </div>
        <div className="comm-stat-tile">
          <div className="comm-stat-value">{stats.total_posts ?? "—"}</div>
          <div className="comm-stat-label">total posts</div>
        </div>
      </div>

      {/* New members list */}
      {stats.new_members_7d_list.length > 0 && (
        <>
          <hr className="term-rule" />
          <div className="term-label" style={{ marginBottom: "0.5rem", fontSize: "0.72rem" }}>new members this week</div>
          <div className="new-members-list">
            {stats.new_members_7d_list.map((m) => (
              <div key={m.name + m.joined} className="new-member-row">
                <span className="new-member-name">{m.name}</span>
                <span className="new-member-date">{m.joined}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Recent posts */}
      {stats.interesting_posts.length > 0 && (
        <>
          <hr className="term-rule" />
          <div className="term-label" style={{ marginBottom: "0.5rem", fontSize: "0.72rem" }}>recent posts</div>
          <div className="recent-posts-list">
            {stats.interesting_posts.map((p) => (
              <div key={p.url} className="recent-post-row">
                <div className="recent-post-meta">
                  <span className="recent-post-date">{p.date}</span>
                  <span className="recent-post-author">{p.author}</span>
                  {(p.likes > 0 || p.comments > 0) && (
                    <span className="recent-post-engagement">
                      {p.likes > 0 && <span>♥ {p.likes}</span>}
                      {p.comments > 0 && <span>💬 {p.comments}</span>}
                    </span>
                  )}
                </div>
                <a
                  href={p.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="recent-post-title"
                >
                  {p.title}
                </a>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="comm-stat-footer">
        fetched at {stats.fetched_at.replace('T', ' ').slice(0, 16)} UTC
      </div>
    </div>
  );
}

function BlockersCard({ blockers }: { blockers: string[] }) {
  return (
    <div
      className={`term-card card-enter ${blockers.length > 0 ? "term-card-red" : "term-card-dim"}`}
      style={{ animationDelay: "80ms" }}
    >
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

// ── Saturday Digest Card ─────────────────────────────────────

function SaturdayDigestCard({ digest }: { digest: NonNullable<RunData["saturday_digest"]> }) {
  const isSent = digest.status === "sent";
  const isBlocked = digest.status === "blocked";
  const pillClass = isSent
    ? "status-pill status-pill-green"
    : isBlocked
    ? "status-pill status-pill-red"
    : "status-pill status-pill-dim";
  const pillLabel = isSent ? "✓ sent" : isBlocked ? "✗ blocked" : "— skipped / not saturday";

  return (
    <div className="term-card">
      <div className="term-card-header">
        <span className="term-label">Saturday Weekly Digest</span>
        <span className={pillClass}>{pillLabel}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", marginTop: "0.6rem" }}>
        {isSent && digest.subject && (
          <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: "0.85rem", color: "var(--foreground)" }}>
            <span className="term-label" style={{ marginRight: "0.5rem" }}>subject</span>
            {digest.subject}
          </div>
        )}
        {isSent && digest.recipient_count !== undefined && (
          <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: "0.85rem", color: "var(--foreground)" }}>
            <span className="term-label" style={{ marginRight: "0.5rem" }}>recipients</span>
            {digest.recipient_count}
          </div>
        )}
        {isSent && digest.sent_at_et && (
          <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: "0.85rem", color: "var(--foreground)" }}>
            <span className="term-label" style={{ marginRight: "0.5rem" }}>sent at</span>
            {digest.sent_at_et}
          </div>
        )}
        {!isSent && digest.reason && (
          <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: "0.82rem", color: "var(--muted-foreground)" }}>
            {digest.reason}
          </div>
        )}
        {!isSent && !digest.reason && (
          <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", fontSize: "0.82rem", color: "var(--muted-foreground)" }}>
            Digest runs every Saturday at 10:00 AM ET.
          </div>
        )}
      </div>
    </div>
  );
}

// ── Run History Card ──────────────────────────────────────────

function RunHistoryCard({ history }: { history: RunHistoryEntry[] }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  if (!history.length) return null;

  return (
    <div className="term-card">
      <div className="term-card-header">
        <span className="term-label">Run History</span>
        <span className="term-label" style={{ opacity: 0.6 }}>{history.length} run{history.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="run-history-list">
        {history.map((run, i) => {
          const hasFailed = run.status === "failed" || run.tasks_failed > 0 || run.status === "blocked" || run.status === "schedule_missing";
          const isExpanded = expandedIdx === i;
          const hasDetail = hasFailed && (run.error_detail || (run.blockers && run.blockers.length > 0) || run.status === "schedule_missing");

          return (
            <div key={i}>
              <div
                className={`run-history-row ${hasDetail ? "run-history-row-clickable" : ""}`}
                onClick={() => hasDetail ? setExpandedIdx(isExpanded ? null : i) : undefined}
                title={hasDetail ? (isExpanded ? "Click to collapse" : "Click to see error details") : undefined}
              >
                <div className="run-history-date">{run.run_date}</div>
                <div className={`status-pill ${
                  run.status === "completed" ? "status-pill-green" :
                  run.status === "schedule_missing" ? "status-pill-amber" :
                  run.status === "blocked" ? "status-pill-red" :
                  run.tasks_failed > 0 ? "status-pill-red" :
                  "status-pill-amber"
                }`}>{run.status === "schedule_missing" ? "⚠ no schedule" : run.status}</div>
                <div className="run-history-result">{run.primary_result}</div>
                <div className="run-history-metrics">
                  {run.status !== "schedule_missing" && (
                    <>
                      <span>{run.posts_published} post{run.posts_published !== 1 ? "s" : ""}</span>
                      <span>{run.tasks_completed} done</span>
                    </>
                  )}
                  {run.tasks_failed > 0 && <span style={{ color: "var(--terminal-red)" }}>{run.tasks_failed} failed</span>}
                  {hasDetail && (
                    <span className="run-history-expand-hint" style={{ color: "var(--terminal-amber, #f59e0b)", marginLeft: "0.3rem" }}>
                      {isExpanded ? "▲ hide" : "▼ details"}
                    </span>
                  )}
                </div>
              </div>
              {isExpanded && hasDetail && (
                <div className="run-history-detail">
                  {run.status === "schedule_missing" && (
                    <div className="run-history-detail-msg">
                      <span style={{ color: "var(--terminal-amber, #f59e0b)" }}>⚠</span> HubBot schedule was not active on this date. The schedule has since been recreated and is now active.
                    </div>
                  )}
                  {run.error_detail && (
                    <div className="run-history-detail-msg">
                      <span style={{ color: "var(--terminal-red)" }}>✗ error:</span> {run.error_detail}
                    </div>
                  )}
                  {run.blockers && run.blockers.length > 0 && (
                    <div>
                      <div style={{ color: "var(--terminal-dim)", fontSize: "0.72rem", marginBottom: "0.3rem" }}>blockers:</div>
                      {run.blockers.map((b, bi) => (
                        <div key={bi} className="run-history-detail-msg">
                          <span style={{ color: "var(--terminal-red)" }}>✗</span> {b}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
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
        style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "1.1rem", color: "var(--terminal-green)" }}
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
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const r = await fetch("/api/run-data", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const json: RunData = await r.json();
      setData(json);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <div className="hubbot-root">
      {/* ── Top bar ── */}
      <header className="hubbot-header">
        <div className="header-left">
          <span className="header-title">HubBot Dashboard</span>
          <span className="header-sep">|</span>
          <span className="header-subtitle">HubActually autonomous community admin</span>
        </div>
        <div className="header-right">
          {data && <span className={statusPillClass(data.status)}>{data.status}</span>}
          {/* Refresh button */}
          <button
            className="refresh-btn"
            onClick={() => fetchData(true)}
            disabled={refreshing}
            title="Refresh dashboard data"
          >
            {refreshing ? "↻" : "↻"}
          </button>
          <a
            href="https://community.hubactually.com"
            target="_blank"
            rel="noopener noreferrer"
            className="header-community-link"
          >
            community ↗
          </a>
        </div>
      </header>

      {/* ── Body ── */}
      <div className="hubbot-body">
        <Sidebar data={data} />

        <main className="hubbot-main">
          {loading && (
            <div className="loading-msg">loading run ledger…</div>
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
              {data.community_stats && <CommunityStatsCard stats={data.community_stats} />}
              <PostCard data={data} />
              <BlockersCard blockers={data.blockers} />
              {data.saturday_digest && <SaturdayDigestCard digest={data.saturday_digest} />}
              {data.run_history && data.run_history.length > 0 && <RunHistoryCard history={data.run_history} />}
            </>
          )}
        </main>
      </div>

      {/* ── Footer ── */}
      <footer className="hubbot-footer">
        <span className="footer-text">data source: /api/run-data</span>
        {data && (
          <span className="footer-text footer-updated">
            last updated: <RelativeTime iso={data.run_completed_at_et ?? data.run_date} fallback={data.last_run_label} />
          </span>
        )}
        <span className="footer-text footer-cron">
          {data?.schedule.cron ?? "0 0 9 * * *"} · {data?.schedule.timezone ?? "America/New_York"}
        </span>
      </footer>
    </div>
  );
}
