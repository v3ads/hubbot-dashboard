# HubBot Dashboard — Design Brainstorm

<response>
<text>
**Idea 1 — Terminal Ops Log**
- **Design Movement:** Brutalist terminal / operational logging aesthetic
- **Core Principles:** Raw data legibility, monospace hierarchy, zero decoration, information density
- **Color Philosophy:** Near-black background (#0d0f0e), phosphor-green accents (#00ff88), amber warnings (#ffb300), red alerts (#ff3b30). Emotional intent: the dashboard feels like a live ops console, not a marketing page.
- **Layout Paradigm:** Full-width log-strip layout — left sidebar with agent status, right main pane with scrollable run ledger cards stacked vertically. No centered hero.
- **Signature Elements:** Blinking cursor on active status, monospace timestamps in muted green, thin 1px rule separators
- **Interaction Philosophy:** Hover reveals raw JSON payload in a slide-out drawer. Clicks copy values to clipboard.
- **Animation:** Entrance: cards slide in from left with 40ms stagger. Status indicator pulses at 2s interval. No decorative motion.
- **Typography System:** JetBrains Mono for all data fields; IBM Plex Sans for labels and headings. Tight line-height (1.3).
</text>
<probability>0.07</probability>
</response>

<response>
<text>
**Idea 2 — Minimal Newspaper**
- **Design Movement:** Swiss editorial / newspaper grid
- **Core Principles:** Strict column grid, typographic hierarchy, ink-on-paper contrast, no gradients
- **Color Philosophy:** Off-white background (#f7f5f0), near-black ink (#1a1a18), single accent in deep teal (#006d5b). Emotional intent: authoritative, readable, trustworthy — like a daily briefing.
- **Layout Paradigm:** 12-column editorial grid. Masthead spans full width. Below: left 4-col sidebar (schedule meta, agent status), right 8-col main area (run ledger, post card, checklist). Cards have ruled top borders, not rounded corners.
- **Signature Elements:** Ruled horizontal dividers, large bold run-date as masthead, small-caps section labels
- **Interaction Philosophy:** Static, readable. Minimal hover states — only underline on links. No animations except a subtle fade-in on load.
- **Animation:** Single fade-in (opacity 0→1, 300ms ease-out) on page load. No per-card stagger.
- **Typography System:** Playfair Display for the masthead date; IBM Plex Serif for card titles; IBM Plex Sans for body/labels.
</text>
<probability>0.08</probability>
</response>

<response>
<text>
**Idea 3 — Dark Ops Dashboard**
- **Design Movement:** Modern SaaS ops dashboard, dark mode, subtle glassmorphism
- **Core Principles:** Information hierarchy through luminance, card-based data grouping, accent-driven status signaling, generous whitespace
- **Color Philosophy:** Deep slate background (oklch 0.13), slightly lighter card surfaces (oklch 0.17), electric teal primary (#00c9a7), amber for warnings, red for blockers. Emotional intent: professional, calm, trustworthy — like a Datadog or Linear dashboard.
- **Layout Paradigm:** Left sidebar (fixed, 220px) for navigation and agent meta. Right content area with a 2-column asymmetric grid: wide left column for run ledger + post card, narrow right column for checklist + metadata badges.
- **Signature Elements:** Thin teal left-border accent on active sidebar item, status badge pills (green/amber/red), subtle card glow on hover
- **Interaction Philosophy:** Cards expand on click to show full detail. Status badges animate in on load. Hover lifts card with shadow increase.
- **Animation:** Cards enter with opacity + translateY(8px) → 0, 200ms ease-out, 40ms stagger. Sidebar items have 120ms color transitions. Status pulse on active agent indicator.
- **Typography System:** Space Grotesk for headings and labels; Inter for body text. Tight tracking on uppercase labels.
</text>
<probability>0.06</probability>
</response>

**Selected approach: Idea 1 — Terminal Ops Log**

The dashboard is an internal ops tool, not a public-facing product. The terminal aesthetic is the most honest expression of what HubBot actually is: an autonomous agent that writes logs and publishes posts. The phosphor-green-on-black palette makes run status immediately legible, and the monospace data fields eliminate ambiguity about values. This approach also makes the `latest-run.json` data feel native rather than dressed up.
