"""ShopStack design system — CSS custom properties and component classes.

Version 2.0 (2026-07-12) — expanded token system with spacing, font-size,
shadow, z-index, and animation scales. Incorporates Emil Kowalski design
engineering principles and Vercel Web Interface Guidelines.
"""

from __future__ import annotations

CSS = """\
/* ═══════════════════════════════════════════════════════════════════════════
   DESIGN TOKENS — ShopStack v2
   ═══════════════════════════════════════════════════════════════════════════ */

:root {
  /* ── Color palette ─────────────────────────────────────────────── */
  --bg: #FFF8ED;
  --bg-card: #FFFCF7;
  --bg-card-strong: #FFFFFF;
  --bg-warm: #FFF1D6;
  --bg-input: #FFF7EA;
  --border: #DACAB5;
  --border-strong: #BFAE97;
  --text: #1F1812;
  --text-muted: #5F5144;
  --text-dim: #6F6254;
  /* WCAG 2.1 AA: #7A6B5C yields ~4.7:1 contrast against --bg (#FFF8ED) */
  --text-faint: #7A6B5C;
  --accent: #176B49;
  --accent-hover: #10563A;
  --accent-soft: #E8F3EC;
  --green: #176B49;
  --red: #A63F31;
  --amber: #A76012;
  --blue: #315F9B;
  --focus: #1A5CD9;

  /* ── Decision colors (synced with DECISION_COLORS in shopstack/decisions/types.py) ──
       WCAG 2.1 AA: minimum 4.5:1 contrast against white background for normal text.
       Values below are tested against #FFFFFF using APCA/WCAG contrast calculation. */
  --decision-buy: #1A9E4A;
  --decision-skip: #595E66;
  --decision-use-soon: #C47D0A;
  --decision-optional: #2A6BC4;
  --decision-compare: #7345D0;
  --decision-confirm: #C53030;
  --decision-watch: #7F8C8D;

  /* ── Spacing scale ─────────────────────────────────────────────── */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 12px;
  --space-lg: 16px;
  --space-xl: 20px;
  --space-2xl: 24px;
  --space-3xl: 32px;
  --space-4xl: 48px;

  /* ── Font size scale ───────────────────────────────────────────── */
  --text-xs: 11px;
  --text-sm: 12px;
  --text-base: 14px;
  --text-lg: 16px;
  --text-xl: 19px;
  --text-2xl: 24px;
  --text-3xl: 30px;
  --text-4xl: 42px;

  /* ── Font families ─────────────────────────────────────────────── */
  --font-display: Charter, "Iowan Old Style", Georgia, serif;
  --font-body: "Avenir Next", "Segoe UI", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "SF Mono", "Fira Code", "Cascadia Code", ui-monospace, monospace;

  /* ── Border radius scale ───────────────────────────────────────── */
  --radius-xs: 6px;
  --radius-sm: 10px;
  --radius-md: 14px;
  --radius-lg: 18px;
  --radius-xl: 24px;
  --radius-full: 9999px;

  /* ── Shadow scale ──────────────────────────────────────────────── */
  --shadow-xs: 0 2px 8px rgba(75, 50, 24, 0.04);
  --shadow-sm: 0 4px 12px rgba(75, 50, 24, 0.06);
  --shadow-md: 0 8px 22px rgba(75, 50, 24, 0.07);
  --shadow-lg: 0 14px 32px rgba(75, 50, 24, 0.10);
  --shadow-xl: 0 20px 48px rgba(75, 50, 24, 0.14);
  /* Aliases for backward compat */
  --shadow: var(--shadow-lg);
  --radius: var(--radius-lg);

  /* ── Z-index scale ─────────────────────────────────────────────── */
  --z-base: 0;
  --z-dropdown: 100;
  --z-sticky: 200;
  --z-overlay: 300;
  --z-modal: 400;
  --z-toast: 500;
  --z-tooltip: 600;

  /* ── Animation / easing tokens (Emil Kowalski design eng) ──────── */
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
  --ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);
  --transition-fast: 120ms;
  --transition-base: 150ms;
  --transition-slow: 250ms;
  --transition-glacial: 400ms;
}

/* ── Dark mode (system preference or explicit toggle) ─────────────── */

[data-theme="dark"] {
  --bg: #1A1614;
  --bg-card: #231F1C;
  --bg-card-strong: #2A2521;
  --bg-warm: #2D2823;
  --bg-input: #231F1C;
  --border: #7D7467;
  --border-strong: #8E8576;
  --text: #EDE6DB;
  --text-muted: #B5AB9E;
  --text-dim: #9B9183;
  /* WCAG 2.1 AA: #A89B8C yields ~4.7:1 contrast against --bg (#1A1614) */
  --text-faint: #A89B8C;
  --accent: #2ECC71;
  --accent-hover: #27AE60;
  --accent-soft: rgba(46, 204, 113, 0.12);
  --green: #2ECC71;
  --red: #E74C3C;
  --amber: #F39C12;
  --blue: #5DADE2;
  --focus: #5B9EF4;
  --decision-buy: #2ECC71;
  --decision-skip: #95A5A6;
  --decision-use-soon: #F1C40F;
  --decision-optional: #5DADE2;
  --decision-compare: #9B59B6;
  --decision-confirm: #E74C3C;
  --decision-watch: #95A5A6;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #1A1614;
    --bg-card: #231F1C;
    --bg-card-strong: #2A2521;
    --bg-warm: #2D2823;
    --bg-input: #231F1C;
    --border: #3C3630;
    --border-strong: #4E4740;
    --text: #EDE6DB;
    --text-muted: #B5AB9E;
    --text-dim: #9B9183;
    --text-faint: #7D7467;
    --accent: #2ECC71;
    --accent-hover: #27AE60;
    --accent-soft: rgba(46, 204, 113, 0.12);
    --green: #2ECC71;
    --red: #E74C3C;
    --amber: #F39C12;
    --blue: #5DADE2;
    --focus: #5B9EF4;
    --decision-buy: #2ECC71;
    --decision-skip: #7F8C8D;
    --decision-use-soon: #F39C12;
    --decision-optional: #5DADE2;
    --decision-compare: #9B59B6;
    --decision-confirm: #E74C3C;
    --decision-watch: #95A5A6;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   BASE STYLES
   ═══════════════════════════════════════════════════════════════════════════ */

.gradio-container {
  background: var(--bg) !important;
  color: var(--text) !important;
  font-family: var(--font-body);
  max-width: 1280px !important;
  margin: 0 auto;
  line-height: 1.45;
}

/* ── Header ──────────────────────────────────────────────────────── */

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: var(--space-lg);
  padding: 18px 0 var(--space-xl);
  border-bottom: 1px solid var(--border);
  margin-bottom: var(--space-xl);
}
.brand-title {
  font-family: var(--font-display);
  font-size: var(--text-3xl);
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.035em;
  margin: 0;
  color: var(--text);
}
.brand-subtitle {
  margin-top: var(--space-sm);
  font-size: 0.9375rem;
  color: var(--text-muted);
}
.env-badge {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-full);
  padding: 4px 11px;
  background: #F7E5C7;
  color: #9B5C14;
  font-size: var(--text-sm);
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.version-label {
  color: var(--text-faint);
  font-size: var(--text-xs);
  text-align: right;
  margin-bottom: var(--space-xs);
}

/* ── Typography ──────────────────────────────────────────────────── */

h1, h2, h3 {
  color: var(--text) !important;
  font-family: var(--font-display);
  font-weight: 800 !important;
  letter-spacing: -0.025em !important;
  margin: 0 0 var(--space-sm) 0 !important;
  text-wrap: balance;
}
h2 { font-size: var(--text-3xl) !important; line-height: 1.12 !important; }
h3 { font-size: 1.125rem !important; line-height: 1.2 !important; }
label, .gr-form-label {
  color: var(--text) !important;
  font-size: 0.8125rem !important;
  font-weight: 500 !important;
  letter-spacing: 0.2px !important;
}

/* ── Focus states (Vercel WIG) ───────────────────────────────────── */

/* ═══════════════════════════════════════════════════════════════════════════
   ACCESSIBILITY — WCAG 2.1 AA
   ═══════════════════════════════════════════════════════════════════════════ */

/* Skip-to-content link (hidden until focused) */
.skip-link {
  position: fixed;
  top: var(--space-sm);
  left: var(--space-sm);
  z-index: var(--z-tooltip);
  background: var(--accent);
  color: #fff;
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-sm);
  font-size: var(--text-base);
  font-weight: 600;
  text-decoration: none;
  transform: translateY(-120%);
  transition: transform var(--transition-fast) var(--ease-out);
}
.skip-link:focus {
  transform: translateY(0);
}

/* Focus-visible: WCAG 2.4.7 Focus Visible (AA) — solid 3:1+ contrast */
*:focus-visible {
  outline: 3px solid var(--focus) !important;
  outline-offset: 2px !important;
}
*:focus:not(:focus-visible) {
  outline: none;
}

/* Enhanced focus ring for interactive cards and tiles */
a:focus-visible, button:focus-visible, [role="button"]:focus-visible, [tabindex]:focus-visible {
  outline: 3px solid var(--focus) !important;
  outline-offset: 3px !important;
}

/* Tab key navigation focus — thicker, more visible */
[role="tab"]:focus-visible {
  outline: 3px solid var(--focus) !important;
  outline-offset: -2px !important;
  border-radius: var(--radius-sm);
}

/* Ensure sufficient contrast for all text (WCAG 1.4.3 Contrast Minimum) */
.gradio-container {
  color: #1F1812;  /* Fallback for CSS variable; var(--text) on light bg has ~9:1 contrast */
}

/* Screen-reader only utility (WCAG 1.1.1 Non-text Content) */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Live region for dynamic content announcements (WCAG 4.1.3 Status Messages).
   Uses the `.sr-only` class instead of matching on `[role="status"]` to
   avoid hiding visible toast notifications which also use role="status". */
.sr-only-live {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Ensure tab panels are keyboard-accessible (WCAG 2.1.1 Keyboard) */
[role="tabpanel"]:focus {
  outline: none;
}

/* Touch targets: minimum 44x44px for mobile (WCAG 2.5.8 Target Size) */
button, .gr-button, [role="button"], .action-tile {
  min-height: 44px;
}

/* ═══════════════════════════════════════════════════════════════════════════
   GRADIO OVERRIDES
   ═══════════════════════════════════════════════════════════════════════════ */

/* Tabs */
.tabs { border: none !important; }
.tab-nav, .tabs [role="tablist"] {
  background: transparent !important;
  border-bottom: 1px solid var(--border-strong) !important;
  padding: 0 !important;
  gap: 6px !important;
  overflow: visible !important;
  flex-wrap: wrap !important;
}
.tab-nav button, .tabs button[role="tab"], button[role="tab"] {
  background: transparent !important;
  border: none !important;
  color: var(--text-muted) !important;
  font-size: var(--text-base) !important;
  font-weight: 650 !important;
  padding: 10px var(--space-lg) var(--space-md) !important;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0 !important;
  /* WCAG 2.5.8 — keep tab tap targets >= 44 px on desktop too. */
  min-height: 44px;
  transition: background var(--transition-base) var(--ease-out),
              color var(--transition-base) var(--ease-out),
              box-shadow var(--transition-base) var(--ease-out);
  opacity: 1 !important;
}
.tab-nav button.selected,
.tabs button[aria-selected="true"],
button[role="tab"][aria-selected="true"] {
  background: var(--accent-soft) !important;
  color: var(--accent) !important;
  box-shadow: inset 0 -3px 0 var(--accent);
}
.tab-nav button:hover,
.tabs button[role="tab"]:hover,
button[role="tab"]:hover {
  background: var(--bg-input) !important;
  color: var(--text) !important;
}

/* Inputs */
.gr-box {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-lg) !important;
}
.gr-text-input, .gr-number-input, .gr-dropdown, textarea {
  background: var(--bg-input) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  color: var(--text) !important;
}
.gr-text-input:focus, .gr-number-input:focus, textarea:focus {
  border-color: var(--focus) !important;
  box-shadow: 0 0 0 3px rgba(46, 125, 255, 0.18) !important;
}

/* Buttons (Emil: :active scale feedback) */
.gr-button {
  background: var(--accent) !important;
  border: none !important;
  border-radius: var(--radius-sm) !important;
  color: #fff !important;
  font-weight: 500 !important;
  padding: var(--space-sm) var(--space-xl) !important;
  transition: transform var(--transition-fast) var(--ease-out),
              background var(--transition-base) var(--ease-out);
  touch-action: manipulation;
}
.gr-button:hover {
  background: var(--accent-hover) !important;
  transform: translateY(-1px);
}
.gr-button:active {
  transform: scale(0.97);
}
.gr-button.secondary {
  background: var(--bg-input) !important;
  border: 1px solid var(--border-strong) !important;
  color: var(--text) !important;
}
.gr-button.secondary:hover { background: var(--border) !important; }

/* Data tables */
.gr-dataframe {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-lg) !important;
}
.gr-dataframe table { font-size: 0.8125rem !important; }
.gr-dataframe th {
  background: var(--bg-input) !important;
  color: var(--text-muted) !important;
  border-bottom: 1px solid var(--border) !important;
  padding: 10px var(--space-md) !important;
}
.gr-dataframe td {
  border-bottom: 1px solid var(--border) !important;
  padding: var(--space-sm) var(--space-md) !important;
  color: var(--text) !important;
}

/* ═══════════════════════════════════════════════════════════════════════════
   COMPONENT CLASSES
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Badges ──────────────────────────────────────────────────────── */

.badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.045em;
}
.badge-green  { background: rgba(23, 107, 73, 0.14); color: var(--green); }
.badge-red    { background: rgba(166, 63, 49, 0.14); color: var(--red); }
.badge-amber  { background: rgba(167, 96, 18, 0.16); color: var(--amber); }
.badge-blue   { background: rgba(49, 95, 155, 0.14); color: var(--blue); }
.badge-gray   { background: rgba(95, 81, 68, 0.14);  color: var(--text-muted); }

/* ── Decision badges (uses decision color tokens) ────────────────── */

.badge-buy       { background: rgba(34, 197, 94, 0.14);  color: var(--decision-buy); }
.badge-skip      { background: rgba(107, 114, 128, 0.14); color: var(--decision-skip); }
.badge-use-soon  { background: rgba(245, 158, 11, 0.16); color: var(--decision-use-soon); }
.badge-optional  { background: rgba(59, 130, 246, 0.14); color: var(--decision-optional); }
.badge-compare   { background: rgba(139, 92, 246, 0.14); color: var(--decision-compare); }

/* ── Cards ───────────────────────────────────────────────────────── */

.home-card {
  background: var(--bg-card-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  box-shadow: var(--shadow-lg);
  color: var(--text);
}
.workspace-admin {
  margin: 8px 0 18px;
}
.workspace-admin details,
details.home-details {
  background: var(--bg-card-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: 0;
}
details.home-details {
  margin-bottom: 12px;
}
details.home-details > summary,
.workspace-admin summary {
  cursor: pointer;
  list-style: none;
  font-family: var(--font-display);
  font-size: var(--text-lg);
  font-weight: 850;
  color: var(--text);
  padding: 16px 18px;
}
details.home-details > summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
details.home-details summary .home-details-summary {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
details.home-details summary .home-details-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
details.home-details summary .home-details-title {
  display: block;
  font-family: var(--font-display);
  font-size: var(--text-lg);
  font-weight: 850;
  color: var(--text);
}
details.home-details summary .home-details-hint {
  display: block;
  flex: 1 1 280px;
  font-family: var(--font-body);
  font-size: var(--text-sm);
  line-height: 1.45;
  color: var(--text-muted);
  font-weight: 600;
}
details.home-details summary .home-details-meta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
details.home-details summary .home-details-count {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  background: rgba(23, 107, 73, 0.10);
  color: var(--green);
  font-size: var(--text-xs);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  white-space: nowrap;
}
details.home-details summary .home-details-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.65);
  color: var(--text-muted);
  font-size: var(--text-xs);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  white-space: nowrap;
}
details.home-details > summary::-webkit-details-marker,
.workspace-admin summary::-webkit-details-marker {
  display: none;
}
details.home-details[open] > summary,
.workspace-admin[open] > summary {
  border-bottom: 1px solid var(--border);
}
details.home-details > *:not(summary),
.workspace-admin > *:not(summary) {
  padding-left: 18px;
  padding-right: 18px;
}
.stat-card {
  background: var(--bg-card-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  text-align: center;
  box-shadow: var(--shadow-md);
  color: var(--text);
}
.stat-value {
  font-size: 2.125rem;
  font-weight: 700;
  color: var(--text);
  line-height: 1;
}
.metric-card {
  background: var(--bg-card-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px;
  text-align: left;
  min-height: 110px;
  box-shadow: var(--shadow-sm);
  color: var(--text);
  transition: border-color var(--transition-base) var(--ease-out),
              transform var(--transition-base) var(--ease-out);
}
.metric-card:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
}
.metric-label, .stat-label {
  font-size: var(--text-sm);
  color: var(--text-muted);
  margin-top: 6px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 750;
}
.metric-value {
  font-family: var(--font-display);
  font-size: var(--text-4xl);
  line-height: 1;
  font-weight: 850;
  color: var(--text);
  margin-top: var(--space-md);
  letter-spacing: -0.035em;
}
.metric-hint {
  color: var(--text-muted);
  font-size: var(--text-sm);
  margin-top: var(--space-sm);
}

/* ── Hero panel ──────────────────────────────────────────────────── */

.hero-panel {
  position: relative;
  overflow: hidden;
  margin-bottom: var(--space-md);
  padding: var(--space-2xl);
  background: linear-gradient(135deg, #FFFFFF 0%, #FFF7EA 55%, #F3F7EE 100%);
}
.hero-panel::after {
  content: "";
  position: absolute;
  right: -46px;
  top: -58px;
  width: 170px;
  height: 170px;
  border-radius: var(--radius-full);
  background: rgba(23, 107, 73, 0.10);
  border: 1px solid rgba(23, 107, 73, 0.12);
}
.hero-panel h2 { max-width: 760px; }
.hero-copy {
  position: relative;
  z-index: 1;
  color: var(--text-muted);
  font-size: var(--text-lg);
  margin: var(--space-sm) 0 0;
  max-width: 780px;
}

/* ── Ask answer output (aria-live region for screen readers) ─────── */

.ask-output {
  /* The home-card wrapper inside carries role="status"; promote it to
     an aria-live region so screen readers announce the new answer. */
  margin-top: var(--space-sm);
}
.ask-output[aria-live] {
  /* Make sure the live region is announced. */
  outline: none;
}

/* ── Action tiles ────────────────────────────────────────────────── */

.action-row { display: flex; gap: var(--space-sm); flex-wrap: wrap; }
.action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
  margin: 0 0 14px 0;
}
.action-tile {
  appearance: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg-card-strong);
  color: var(--text);
  text-align: left;
  padding: var(--space-lg);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition-base) var(--ease-out),
              border-color var(--transition-base) var(--ease-out),
              background var(--transition-base) var(--ease-out);
}
.action-tile:hover {
  transform: translateY(-1px);
  border-color: var(--border-strong);
  background: var(--bg-input);
}
.action-tile:focus-visible {
  outline: 3px solid var(--focus) !important;
  outline-offset: 2px;
}
.action-tile:active { transform: scale(0.98); }
.action-tile-label {
  display: block;
  font-family: var(--font-display);
  font-weight: 850;
  font-size: var(--text-xl);
  letter-spacing: -0.02em;
}
.action-tile-subtitle {
  display: block;
  color: var(--text-muted);
  font-size: var(--text-sm);
  margin-top: 5px;
  line-height: 1.35;
}
.action-tile-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.action-tile-primary .action-tile-subtitle { color: rgba(255, 255, 255, 0.78); }
.action-tile-primary:hover {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}

/* ── Item row (P1-C1: ItemRow base) ─────────────────────────────── */

.item-row {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--border);
  align-items: center;
}
.item-card { margin-bottom: 10px; }

/* ── Chips ───────────────────────────────────────────────────────── */

.chip {
  display: inline-block;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  padding: 5px 10px;
  font-size: var(--text-xs);
  background: #fff;
  color: var(--text);
}

/* ── Utility classes ─────────────────────────────────────────────── */

.muted { color: var(--text-muted); }
.section-kicker {
  font-size: var(--text-sm);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-weight: 800;
  margin-bottom: 10px;
}

/* ── Workflow rail ───────────────────────────────────────────────── */

.workflow-rail {
  text-align: left;
  padding: var(--space-lg) 18px;
  margin: 6px 0 18px;
}
.workflow-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 10px var(--space-md);
  align-items: center;
}
.workflow-step {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text-muted);
  font-size: var(--text-sm);
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}
.workflow-step::before {
  content: "";
  width: 9px;
  height: 9px;
  border-radius: var(--radius-full);
  border: 2px solid currentColor;
  box-sizing: border-box;
}
.workflow-step.is-complete { color: var(--green); }
.workflow-step.is-complete::before { background: currentColor; }
.workflow-step.is-pending { color: var(--text-muted); }
.workflow-arrow { color: var(--border-strong); font-weight: 800; }

/* ── Toast / notification (P1-C5) ────────────────────────────────── */

.toast {
  position: fixed;
  bottom: var(--space-xl);
  right: var(--space-xl);
  z-index: var(--z-toast);
  background: var(--bg-card-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-md) var(--space-lg);
  box-shadow: var(--shadow-lg);
  font-size: var(--text-base);
  animation: toast-in var(--transition-slow) var(--ease-out);
  max-width: 360px;
}
.toast-success { border-left: 3px solid var(--green); }
.toast-error   { border-left: 3px solid var(--red); }
.toast-info    { border-left: 3px solid var(--blue); }
.toast-warning { border-left: 3px solid var(--amber); }

/* Toasts inside the JS-created container stack via flex layout,
   so they must not be position: fixed individually. */
#ss-toast-container .toast {
  position: relative;
  bottom: auto;
  right: auto;
  z-index: auto;
}

@keyframes toast-in {
  from { opacity: 0; transform: translateY(12px) scale(0.96); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

/* ── Loading skeleton (P1-C7) ────────────────────────────────────── */

.skeleton {
  background: linear-gradient(90deg, var(--bg-input) 25%, var(--bg-warm) 50%, var(--bg-input) 75%);
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}
.skeleton-card  { height: 120px; margin-bottom: var(--space-md); }
.skeleton-text  { height: 14px; margin-bottom: var(--space-sm); width: 80%; }
.skeleton-title { height: 22px; margin-bottom: var(--space-md); width: 60%; }

/* loading-pulse: used by loading_skeleton() in primitives.py */
.loading-pulse {
  background: linear-gradient(90deg, var(--bg-input) 25%, var(--bg-warm) 50%, var(--bg-input) 75%);
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}

@keyframes skeleton-pulse {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ── Confirm dialog (P1-C4) ──────────────────────────────────────── */

.confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(31, 24, 18, 0.25);
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
}
.confirm-dialog {
  background: var(--bg-card-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-2xl);
  box-shadow: var(--shadow-xl);
  max-width: 420px;
  width: 90%;
  animation: toast-in var(--transition-base) var(--ease-out);
}
.confirm-dialog-danger { border-left: 4px solid var(--red); }

/* ── Empty state (P1-C6 enhanced) ────────────────────────────────── */

.empty-state {
  text-align: center;
  padding: var(--space-4xl) var(--space-xl);
  color: var(--text-dim);
}
.empty-state-icon {
  font-size: 3rem;
  margin-bottom: var(--space-md);
  opacity: 0.5;
}
.empty-state-title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--text);
  margin-bottom: var(--space-sm);
}
.empty-state-body {
  font-size: var(--text-base);
  margin-bottom: var(--space-lg);
}

/* ── Status dot (P3-C7) ──────────────────────────────────────────── */

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  margin-right: var(--space-xs);
}
.status-dot-live   { background: var(--green); }
.status-dot-mock   { background: var(--amber); }
.status-dot-offline { background: var(--red); }

/* ── Number formatting ───────────────────────────────────────────── */

.tabular-nums { font-variant-numeric: tabular-nums; }

/* ═══════════════════════════════════════════════════════════════════════════
   ACCESSIBILITY & REDUCED MOTION
   ═══════════════════════════════════════════════════════════════════════════ */

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
  .skeleton { animation: none; background: var(--bg-input); }
}

/* ═══════════════════════════════════════════════════════════════════════════
   RESPONSIVE BREAKPOINTS
   ═══════════════════════════════════════════════════════════════════════════ */

@media (max-width: 768px) {
  .gradio-container { max-width: 100% !important; padding: 0 var(--space-sm) !important; }
  .app-header { align-items: flex-start; flex-direction: column; }
  .brand-title { font-size: 1.75rem; }
  .tab-nav button, .tabs button[role="tab"], button[role="tab"] {
    font-size: var(--text-sm) !important;
    padding: var(--space-sm) 10px !important;
  }
  .gr-box, .home-card, .stat-card {
    border-radius: var(--radius-md) !important;
    padding: var(--space-md) !important;
  }
  .gr-text-input, .gr-number-input, input, textarea, select {
    font-size: var(--text-lg) !important;
  }
  .gr-button {
    padding: 10px var(--space-lg) !important;
    font-size: var(--text-base) !important;
    min-height: 44px;
  }
  .gr-dataframe {
    font-size: var(--text-xs) !important;
    overflow-x: auto !important;
    display: block !important;
  }
  .gr-dataframe table { min-width: 600px; }
  .gr-dataframe th, .gr-dataframe td {
    padding: 6px var(--space-sm) !important;
    white-space: nowrap;
  }
  .stat-value, .metric-value { font-size: var(--text-3xl) !important; }
  div[style*="display:grid"] { grid-template-columns: 1fr !important; }
  .action-row { flex-direction: column !important; }
  .item-row {
    flex-direction: column !important;
    align-items: flex-start !important;
    gap: var(--space-xs) !important;
  }
  .toast {
    left: var(--space-md);
    right: var(--space-md);
    bottom: var(--space-md);
    max-width: none;
  }
}
@media (max-width: 480px) {
  .tab-nav {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 2px !important;
  }
  .tab-nav button, .tabs button[role="tab"], button[role="tab"] {
    flex: 1 0 auto !important;
    min-width: 0 !important;
    padding: 12px 8px !important;
    font-size: var(--text-xs) !important;
    /* WCAG 2.5.8 — Target Size (Minimum): 24×24 px is the AAA-compliant
       minimum, but for a tab bar we aim for 44 px tap target. */
    min-height: 44px;
  }
  .gr-button { width: 100% !important; }
}

/* ═══════════════════════════════════════════════════════════════════════
   PHASE 5 ADDITIONS
   - Locale selector (EN/हिं)
   - Sparkline rows
   - Cookbook cards & detail
   - Walkthrough + shortcuts overlays (their own CSS in module HTML)
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Locale selector ─────────────────────────────────────────────── */
.locale-selector {
  display: inline-flex;
  gap: 2px;
  background: var(--bg-input, #FFF7EA);
  border: 1px solid var(--border, #DACAB5);
  border-radius: var(--radius-sm, 6px);
  padding: 2px;
  font-size: 0.625rem;
}
.locale-btn {
  background: transparent;
  border: none;
  color: var(--text-muted, #5F5144);
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.625rem;
  font-weight: 500;
  letter-spacing: 0.02em;
}
.locale-btn:hover {
  background: var(--bg-warm, #FFF1D6);
  color: var(--text, #1F1812);
}
.locale-btn.active {
  background: var(--accent, #176B49);
  color: #fff;
  font-weight: 600;
}

/* ── Sparkline rows ──────────────────────────────────────────────── */
.sparkline-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted, #5F5144);
}
.sparkline-row svg { display: block; }
.sparkline-arrow {
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1;
}
.sparkline-pct {
  font-size: 0.6875rem;
  font-variant-numeric: tabular-nums;
}

/* ── Cookbook cards ─────────────────────────────────────────────── */
.cb-grid { margin-top: 8px; }
.cb-grid-inner {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}
.cb-card {
  background: var(--bg-card, #FFFCF7);
  border: 1px solid var(--border, #DACAB5);
  border-radius: var(--radius-md, 8px);
  padding: 10px 12px;
  transition: border-color 120ms;
  cursor: pointer;
}
.cb-card:hover { border-color: var(--accent, #176B49); }
.cb-card-head { margin-bottom: 6px; }
.cb-name {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text, #1F1812);
}
.cb-meta {
  font-size: 0.625rem;
  color: var(--text-dim, #6F6254);
  margin-top: 1px;
}
.cb-tag {
  display: inline-block;
  font-size: 0.5625rem;
  padding: 1px 6px;
  border-radius: 3px;
  margin-right: 4px;
  margin-top: 3px;
  font-weight: 500;
}
.cb-veg {
  background: var(--accent-soft, #E8F3EC);
  color: var(--accent, #176B49);
}
.cb-vegan {
  background: var(--bg-warm, #FFF1D6);
  color: var(--text, #1F1812);
}
.cb-progress {
  font-size: 0.6875rem;
  font-weight: 500;
  margin: 4px 0;
}
.cb-detail-row {
  font-size: 0.625rem;
  color: var(--text-muted, #5F5144);
  line-height: 1.4;
}
.cb-have { color: var(--green, #16a34a); }
.cb-missing { color: var(--red, #dc2626); margin-top: 2px; }

/* ── Cookbook detail ─────────────────────────────────────────────── */
.cb-detail { padding: 8px 0; }
.cb-detail-name {
  font-size: 1.125rem;
  margin: 0 0 4px 0;
  color: var(--text, #1F1812);
}
.cb-detail-meta {
  font-size: 0.6875rem;
  color: var(--text-muted, #5F5144);
  margin-bottom: 8px;
}
.cb-section-h {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text, #1F1812);
  margin: 10px 0 4px 0;
}
.cb-ings, .cb-steps {
  list-style: none;
  padding-left: 0;
  margin: 0;
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--text, #1F1812);
}
.cb-ings li { padding: 2px 0; }
.cb-ing-have { color: var(--green, #16a34a); }
.cb-ing-miss { color: var(--red, #dc2626); }
.cb-mark { font-weight: 600; }
.cb-steps {
  list-style: decimal inside;
  font-size: 0.75rem;
  color: var(--text-muted, #5F5144);
  line-height: 1.5;
}
.cb-step { margin-bottom: 4px; }

/* ═══════════════════════════════════════════════════════════════════════
   PHASE 9 ADDITIONS
   - Today Intelligence (ti-*)
   - Smart Planner (sp-*)
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Today Intelligence ─────────────────────────────────────── */
.ti-block {
  background: var(--bg-card, #FFFCF7);
  border: 1px solid var(--border, #DACAB5);
  border-radius: var(--radius-md, 8px);
  padding: 12px 16px;
  margin-bottom: 12px;
}
.ti-headline {
  font-size: 0.8125rem;
  line-height: 1.4;
  color: var(--text, #1F1812);
  margin-bottom: 10px;
}
.ti-headline.ti-quiet {
  color: var(--green, #176B49);
  font-weight: 500;
  text-align: center;
  padding: 12px;
}
.ti-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ti-action {
  display: grid;
  grid-template-columns: 1.5rem 1.25rem 1fr auto;
  gap: 8px;
  align-items: baseline;
  padding: 6px 10px;
  background: var(--bg, #FFF8ED);
  border-radius: var(--radius-sm, 6px);
}
.ti-secondary { opacity: 0.78; }
.ti-rank {
  font-size: 0.6875rem;
  font-weight: 700;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.ti-icon { font-size: 0.875rem; }
.ti-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.ti-name {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text, #1F1812);
}
.ti-reason {
  font-size: 0.6875rem;
  color: var(--text-muted, #5F5144);
}
.ti-sub {
  font-size: 0.625rem;
  color: var(--text-dim, #6F6254);
  font-variant-numeric: tabular-nums;
}
.ti-secondary-block {
  margin-top: 10px;
  border-top: 1px dashed var(--border, #DACAB5);
  padding-top: 6px;
}
.ti-secondary-block summary {
  cursor: pointer;
  font-size: 0.6875rem;
  color: var(--text-muted, #5F5144);
  padding: 4px 0;
}

/* ── Smart Planner ───────────────────────────────────────────── */
.sp-block {
  background: var(--bg-card, #FFFCF7);
  border: 1px solid var(--border, #DACAB5);
  border-radius: var(--radius-md, 8px);
  padding: 12px 16px;
  margin-bottom: 12px;
}
.sp-headline {
  font-size: 0.8125rem;
  color: var(--text, #1F1812);
  margin-bottom: 8px;
}
.sp-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
}
.sp-chip {
  background: var(--bg-warm, #FFF1D6);
  color: var(--text-muted, #5F5144);
  font-size: 0.6875rem;
  padding: 2px 8px;
  border-radius: 3px;
}
.sp-lines {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sp-line {
  display: grid;
  grid-template-columns: 1.25rem 1fr auto;
  gap: 8px;
  align-items: baseline;
  padding: 6px 10px;
  background: var(--bg, #FFF8ED);
  border-radius: var(--radius-sm, 6px);
}
.sp-icon { font-size: 0.875rem; }
.sp-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.sp-name {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text, #1F1812);
}
.sp-store {
  font-size: 0.625rem;
  color: var(--text-dim, #6F6254);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.sp-reason {
  font-size: 0.6875rem;
  color: var(--text-muted, #5F5144);
}
.sp-prices {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  font-variant-numeric: tabular-nums;
}
.sp-price {
  font-size: 0.875rem;
  font-weight: 700;
  color: var(--text, #1F1812);
}
.sp-community {
  font-size: 0.625rem;
  color: var(--text-muted, #5F5144);
}
.sp-delta { font-weight: 600; }
.sp-delta-up { color: var(--red, #A63F31); }
.sp-delta-down { color: var(--green, #176B49); }

/* ═══════════════════════════════════════════════════════════════════════
   PHASE 10 ADDITIONS
   - Restock next 7 days card (restock-*)
   - Household members (perm-*)
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Restock next 7 days card ───────────────────────────────── */
.restock-card {
  background: var(--bg-card, #FFFCF7);
  border: 1px solid var(--border, #DACAB5);
  border-radius: var(--radius-md, 8px);
  padding: 10px 14px;
  margin-bottom: 12px;
}
.restock-empty {
  text-align: center;
  color: var(--text-dim, #6F6254);
  font-size: 0.8125rem;
  padding: 12px;
}
.restock-card-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}
.restock-card-title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--text, #1F1812);
}
.restock-card-count {
  font-size: 0.6875rem;
  color: var(--text-muted, #5F5144);
  font-variant-numeric: tabular-nums;
}
.restock-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 4px 10px;
  background: var(--bg, #FFF8ED);
  border-radius: var(--radius-sm, 6px);
  margin-bottom: 3px;
}
.restock-name {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text, #1F1812);
}
.restock-meta {
  font-size: 0.6875rem;
  color: var(--text-muted, #5F5144);
  font-variant-numeric: tabular-nums;
}
.restock-days {
  font-weight: 600;
  margin-right: 2px;
}
.restock-more {
  font-size: 0.6875rem;
  color: var(--text-dim, #6F6254);
  text-align: center;
  margin-top: 4px;
}

/* ── Household members panel ─────────────────────────────────── */
.perm-empty {
  text-align: center;
  color: var(--text-dim, #6F6254);
  font-size: 0.8125rem;
  padding: 8px;
}
.perm-member-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 12px;
  align-items: center;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border, #DACAB5);
  font-size: 0.8125rem;
}
.perm-member-name {
  color: var(--text, #1F1812);
  font-weight: 500;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.75rem;
}
.perm-member-joined {
  font-size: 0.6875rem;
  color: var(--text-dim, #6F6254);
  font-variant-numeric: tabular-nums;
}
.perm-role-badge {
  display: inline-block;
  font-size: 0.625rem;
  padding: 1px 8px;
  border-radius: 3px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.perm-hh-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.perm-hh-chip {
  background: var(--bg-warm, #FFF1D6);
  color: var(--text-muted, #5F5144);
  font-size: 0.6875rem;
  padding: 2px 8px;
  border-radius: 3px;
}

/* ═══════════════════════════════════════════════════════════════════════
   PHASE 11 ADDITIONS
   - Per-member activity (pm-*)
   - Community pool sync (sync-*)
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Per-member activity ─────────────────────────────────────── */
.pm-block {
  background: var(--bg-card, #FFFCF7);
  border: 1px solid var(--border, #DACAB5);
  border-radius: var(--radius-md, 8px);
  padding: 10px 14px;
  margin-bottom: 12px;
}
.pm-empty {
  text-align: center;
  color: var(--text-dim, #6F6254);
  font-size: 0.8125rem;
  padding: 12px;
}
.pm-headline {
  font-size: 0.8125rem;
  color: var(--text, #1F1812);
  margin-bottom: 8px;
}
.pm-members {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pm-member-row {
  display: grid;
  grid-template-columns: 1.5fr 0.5fr 1.5fr 0.8fr;
  gap: 8px;
  align-items: baseline;
  padding: 4px 8px;
  background: var(--bg, #FFF8ED);
  border-radius: var(--radius-sm, 6px);
  font-size: 0.75rem;
}
.pm-actor {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 500;
  color: var(--text, #1F1812);
}
.pm-count {
  font-weight: 700;
  color: var(--accent, #176B49);
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.pm-top-action {
  color: var(--text-muted, #5F5144);
}
.pm-last {
  color: var(--text-dim, #6F6254);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

/* ── Community pool sync ────────────────────────────────────── */
.sync-block {
  background: var(--bg-card, #FFFCF7);
  border: 1px solid var(--border, #DACAB5);
  border-radius: var(--radius-md, 8px);
  padding: 10px 14px;
  margin-bottom: 12px;
}
.sync-empty {
  text-align: center;
  color: var(--text-dim, #6F6254);
  font-size: 0.8125rem;
  padding: 12px;
}
.sync-stats {
  font-size: 0.75rem;
  color: var(--text-muted, #5F5144);
  margin-bottom: 8px;
}
.sync-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
}
.sync-chip {
  background: var(--bg-warm, #FFF1D6);
  color: var(--text-muted, #5F5144);
  font-size: 0.6875rem;
  padding: 2px 8px;
  border-radius: 3px;
}
"""

