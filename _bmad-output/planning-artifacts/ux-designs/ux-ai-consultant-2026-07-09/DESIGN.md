---
name: ai-consultant
description: >
  Spec-Driven AI Development Team Simulator — a self-hosted developer and PM tool
  for delegating multi-ticket implementation to a coordinated AI agent team.
  shadcn/ui on Next.js + Tailwind. This DESIGN.md specifies the brand-layer delta only;
  all unlisted tokens inherit shadcn defaults.
status: final
created: 2026-07-09
updated: 2026-07-09
colors:
  # --- Brand layer overrides. All unlisted tokens inherit from shadcn. ---

  # Primary: Cool Indigo — interactive elements, links, active nav, primary buttons.
  primary: '#4F46E5'
  primary-foreground: '#FFFFFF'
  primary-dark: '#818CF8'
  primary-foreground-dark: '#0F0E1A'

  # Agent Active: Amber — exclusively for "agent is currently running" states.
  # Never used for chrome, hover, or generic accents.
  agent-active: '#F59E0B'
  agent-active-foreground: '#1C1108'
  agent-active-dark: '#FCD34D'
  agent-active-foreground-dark: '#1C1108'

  # Success: Emerald — ticket Done, tests passed, Spec confirmed.
  success: '#10B981'
  success-foreground: '#FFFFFF'
  success-dark: '#34D399'
  success-foreground-dark: '#052E16'

  # Pending: Slate — ticket Pending, queue items not yet started.
  pending: '#64748B'
  pending-foreground: '#FFFFFF'
  pending-dark: '#94A3B8'
  pending-foreground-dark: '#0F172A'

  # Surface tokens (dark-mode primary — this product lives in dark mode)
  # shadcn dark defaults are used; these are semantic aliases.
  log-surface: '#0D1117'          # terminal-style log background (near GitHub dark)
  log-surface-border: '#21262D'   # border around log/stream blocks

typography:
  # Body, label, muted inherit shadcn defaults (Geist Sans / system sans).
  # Only the monospace and display roles are brand-overridden.

  mono:
    fontFamily: "'Geist Mono', 'JetBrains Mono', 'Fira Code', monospace"
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: '0'

  display:
    fontFamily: "'Geist Sans', system-ui, sans-serif"
    fontSize: 28px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: '-0.02em'

  display-sm:
    fontFamily: "'Geist Sans', system-ui, sans-serif"
    fontSize: 18px
    fontWeight: '500'
    lineHeight: '1.3'
    letterSpacing: '-0.01em'

rounded:
  # Tighter than shadcn defaults — tool aesthetic reads crisper than consumer app.
  sm: 3px
  md: 6px
  lg: 8px
  xl: 10px

spacing:
  # Tailwind 4-based scale inherited. One override: chat message gutters.
  chat-gutter: 16px
  card-pad: 16px
  sidebar-width: 240px

components:
  button-primary:
    background: '{colors.primary}'
    foreground: '{colors.primary-foreground}'
    radius: '{rounded.md}'

  ticket-card:
    background: 'hsl(var(--card))'
    border: '1px solid hsl(var(--border))'
    radius: '{rounded.lg}'
    padding: '{spacing.card-pad}'

  ticket-card-done:
    border: '1px solid {colors.success}'
    opacity: '0.7'

  ticket-card-error:
    border: '1px solid hsl(var(--destructive))'

  execution-status-block:
    background: '{colors.log-surface}'
    border: '1px solid {colors.log-surface-border}'
    radius: '{rounded.lg}'
    fontFamily: '{typography.mono.fontFamily}'
    fontSize: '{typography.mono.fontSize}'

  log-stream:
    background: '{colors.log-surface}'
    border: '1px solid {colors.log-surface-border}'
    radius: '{rounded.md}'
    fontFamily: '{typography.mono.fontFamily}'
    fontSize: '{typography.mono.fontSize}'
    lineHeight: '{typography.mono.lineHeight}'

  agent-active-badge:
    background: '{colors.agent-active}'
    foreground: '{colors.agent-active-foreground}'
    radius: '{rounded.sm}'
    fontSize: '11px'
    fontWeight: '600'
    textTransform: 'uppercase'
    letterSpacing: '0.05em'

  cost-indicator:
    background: 'hsl(var(--muted))'
    foreground: 'hsl(var(--muted-foreground))'
    radius: '{rounded.sm}'
    fontFamily: '{typography.mono.fontFamily}'
    fontSize: '12px'

  file-tree-item:
    fontFamily: '{typography.mono.fontFamily}'
    fontSize: '13px'
    radius: '{rounded.sm}'

  spec-preview:
    background: '{colors.log-surface}'
    border: '1px solid {colors.log-surface-border}'
    radius: '{rounded.md}'
    fontFamily: '{typography.mono.fontFamily}'
    fontSize: '13px'
---

## Brand & Style

ai-consultant is a self-hosted AI development team simulator. It gives solo developers and PMs a spec-as-contract entry point and a coordinated AI agent team that implements tickets sequentially with persistent cross-session memory, live reasoning streams, and mandatory test artifacts. The product promise is *autonomous, transparent, exception-driven development* — the user directs; the agents implement.

The visual identity follows a **power-tool posture**: dark-mode-primary, information-dense but not cluttered, terminal-inflected without being retro. The reference lineage is Linear (sharp edges, keyboard-first, no decoration), Vercel Dashboard (monospace log streams, dark surfaces, status vocabulary), and GitHub (status color semantics: green/amber/red mean done/active/error everywhere, with no ambiguity).

The product is built on shadcn/ui + Next.js + Tailwind. This DESIGN.md specifies brand-layer deltas only. The 80% of components that ship from shadcn (Button, Card, Dialog, Sheet, Input, Badge, Separator, Toast, Skeleton, Tabs, Popover, DropdownMenu) inherit shadcn's visual spec as-is. Do not customize those.

Dark mode is the primary and default mode. Light mode should be available via shadcn's theming mechanism but is not the design target — every color decision above is made with dark surfaces in mind.

## Colors

The ai-consultant palette is built around **function-first semantics**: every color answers "what does this state mean?" rather than "what looks nice?". Color carries meaning, not decoration.

**Primary Indigo (`#4F46E5` light / `#818CF8` dark)** is the interactive action color. Used on primary buttons, active navigation, link underlines, and focus rings. Replaces shadcn's default `primary`.

**Agent Active Amber (`#F59E0B` light / `#FCD34D` dark)** is the live-execution indicator. Used *only* when an agent is currently running — the animated badge in the Execution Status Block, the pulsing dot in the project nav, and the active queue item in the ticket list. It means "work is happening right now." Never used decoratively, never used for selection, never used for hover states.

**Success Emerald (`#10B981` light / `#34D399` dark)** is the completion color. Used when a ticket reaches `Done`, when a spec is validated, when tests pass. It means "this is finished and verified."

**Pending Slate (`#64748B` light / `#94A3B8` dark)** is the queue-waiting color. Used on tickets in `Pending` state and on queue items not yet started. Intentionally muted — it should read as "not active yet."

**Destructive** — shadcn's default destructive token (red) is used unchanged for `Error` states, failed tests, and agent escalations.

**Log Surface (`#0D1117`)** is the terminal background for log-stream blocks, Execution Status Blocks, Spec previews, and the Dev View file tree. Matches GitHub's dark surface, which developers recognize as "this is output, not UI."

**Color discipline:** One interactive color. One live-execution color. One success color. One pending color. One terminal surface. Shadcn defaults for everything else. Any new state without a color should use shadcn's `muted` or `muted-foreground` tokens — not a new brand color.

## Typography

Body, label, caption, and most UI text inherit shadcn's Geist Sans (or system-ui fallback) at default weights and sizes.

**Mono (`Geist Mono` / `JetBrains Mono` fallback, 13px)** is used for log stream output, Execution Status Block content, ticket IDs, Spec previews, the Dev View file tree, and cost/token counters. Any output from an agent or subprocess appears in mono. Any persistent identifier (`TICKET-42`, branch names) appears in mono. Mono = "this is machine output."

**Display (`Geist Sans`, 28px / 600)** is used for the home page empty state and project headings only. One display moment per surface. No serif — this is a power tool.

**Display-sm** is used for section headers within the Chat View and for the "Welcome back" state when a project has no prior history.

Body stays in shadcn defaults. No custom body weight overrides. No italic as a semantic device.

## Layout & Spacing

Two-panel desktop layout:
- **Left sidebar (240px fixed):** Project list navigation, agent status dots, "New Project" CTA. Collapses to icon-only rail on `md`.
- **Main area (flex-1):** Context-dependent — Project List on home, Chat View inside a project.

Within Chat View, the main area optionally splits:
- Default: full-width chat surface.
- Dev View open (local mode only): 60/40 split — chat left, Dev View right.

Chat gutter: 16px. Ticket card padding: 16px. Sidebar width: 240px. No max-content-width constraint inside Chat View (it is a log/stream product, not a reading product).

The interface does not use large padded hero sections or marketing-style whitespace. Every pixel of vertical space is occupied by information. Empty states are short: a single `display-sm` line and one action button.

## Elevation & Depth

Inherited from shadcn. No custom shadow tokens. Ticket cards use the shadcn `card` shadow on hover; no elevation as a hierarchy device outside that. The terminal-surface blocks (`log-surface`) create visual separation via color contrast, not shadow.

## Shapes

Tighter than shadcn defaults to reinforce the tool posture:
- `rounded/sm` (3px) — badges, cost indicator, small tags, file tree items
- `rounded/md` (6px) — buttons, inputs, log stream blocks
- `rounded/lg` (8px) — ticket cards, panels, dialogs
- `rounded/xl` (10px) — Execution Status Block

Pill shapes (`rounded-full`) only for animated pulse dots on the agent-active badge and the queue item status indicator.

## Components

shadcn components used as-is (do not customize): `Button`, `Card`, `Dialog`, `Sheet`, `Input`, `Textarea`, `Badge`, `Separator`, `Toast`, `Skeleton`, `Tabs`, `Popover`, `DropdownMenu`, `Avatar`, `Checkbox`, `ScrollArea`.

Brand-layer components:

- **Ticket Card** — `{ticket-card}` token. Bordered card embedding title, description, acceptance criteria, dependency list, and action controls. State variants: default, done (`{ticket-card-done}`), error (`{ticket-card-error}`). Embedded inline in the chat scroll surface, never in a separate panel.

- **Execution Status Block** — `{execution-status-block}` token. Terminal-surface block pinned at the top of the Chat View during active execution. Contains: current ticket name, elapsed timer (updates every second), queue list with state icons. Hidden when no execution is active.

- **Log Stream** — `{log-stream}` token. Scrollable mono-font block receiving SSE lines from agents and subprocess output. Max-height: 40vh; overflows with scroll. New lines append at the bottom; auto-scroll to bottom unless the user has scrolled up.

- **Agent Active Badge** — `{agent-active-badge}` token. Appears in the sidebar next to the active project name and inside the Execution Status Block. Animated: a 2px pulsing amber dot + "RUNNING" label. Disappears on execution complete.

- **Cost Indicator** — `{cost-indicator}` token. Fixed at the bottom of the Chat View. Two rows: session usage / session cost; cumulative project usage / cost. Mono font, muted surface. Never hidden — shows `0 tokens / $0.00` when no usage yet.

- **Spec Preview** — `{spec-preview}` token. Collapsible terminal-surface block in the chat showing the confirmed Spec content. Collapsed by default (shows first 5 lines + "Show full spec" toggle).

- **File Tree Item** — `{file-tree-item}` token. Row in the Dev View panel. Icon (file/folder) + mono filename. State: created (emerald dot), modified (amber dot), deleted (destructive strikethrough).

## Do's and Don'ts

| Do | Don't |
|---|---|
| Use `{colors.agent-active}` only when an agent is actively running | Use amber for selection, hover, or generic accents |
| Use `{colors.success}` only for confirmed completion events | Use green for progress, partial success, or "good" states that aren't Done |
| Render all agent output in `{log-stream}` mono blocks | Render agent log output as chat messages styled like user messages |
| Inherit shadcn defaults for unlisted components | Override shadcn's `background`, `foreground`, `border`, `ring`, `muted` tokens |
| Keep empty states to one `display-sm` line + one action | Use long empty-state marketing copy or illustrations |
| Show exactly one `agent-active-badge` at a time in the sidebar | Show multiple amber-active indicators simultaneously |
| Use `{rounded.lg}` for ticket cards, `{rounded.md}` for buttons/inputs | Mix corner radii without following the scale |
| Keep the cost indicator always visible (show zeros, not hidden) | Hide the cost indicator when there is no usage |