"""FastAPI frontend shell for ShopStack.

This is the real user-facing entrypoint for the app. The shell is
intentionally API-driven: it pulls state from the v1 HTTP contract
instead of reaching into UI internals.
"""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)

_API_BASE = "/api/v1"
_AUTH_STORAGE_KEY = "shopstack.shell.session"


def render_frontend_shell_html() -> str:
    """Return the HTML for the FastAPI frontend shell."""
    html = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark light">
  <title>__APP_TITLE__</title>
  <meta name="description" content="__APP_SUBTITLE__">
  <link rel="manifest" href="/manifest.json">
  <meta name="theme-color" content="#6F8A6A">
  <style>
    /* ShopStack Warm Pantry Tokens — aligned with shopstack-mobile/src/theme/tokens.ts */
    :root {
      /* Palette */
      --paper-50: #FFFCF7; --paper-100: #FFF8ED; --paper-200: #F5EDE0; --paper-300: #EBE2D5;
      --paper-400: #D8CFC2; --paper-500: #A8A199; --paper-600: #6B655F; --paper-700: #4A4641;
      --paper-800: #2E2C28; --paper-900: #1A1814;
      --green-50: #F1F8F0; --green-100: #DDEEDD; --green-200: #B6D5B4; --green-300: #8EB98C;
      --green-400: #6F8A6A; --green-500: #4F6B4C; --green-600: #3B5239; --green-700: #2A3D28;
      --green-800: #1E2B1D; --green-900: #121A12;
      --terracotta-50: #FFF4EE; --terracotta-100: #FFE3D5; --terracotta-200: #FFC7AA;
      --terracotta-300: #FFA47C; --terracotta-400: #E58555; --terracotta-500: #C96B3E;
      --terracotta-600: #A3502E; --terracotta-700: #7F3A20; --terracotta-800: #5C2815;
      --terracotta-900: #3B160B;
      --amber-50: #FFFBEB; --amber-100: #FEF3C7; --amber-200: #FDE68A; --amber-300: #FCD34D;
      --amber-400: #D4A34B; --amber-500: #B58430; --amber-600: #966520; --amber-700: #714B17;
      --amber-800: #523612; --amber-900: #33210B;
      --berry-400: #DC4444; --berry-500: #B91C1C;
      --espresso-400: #8B7A6A; --espresso-500: #6B5D50; --espresso-600: #4F443A;
      --espresso-700: #3A3129; --espresso-800: #271F1A; --espresso-900: #1A1512;

      /* Semantic */
      --bg: var(--paper-50);
      --bg-elevated: var(--paper-100);
      --bg-card: #FFFFFF;
      --bg-soft: var(--paper-100);
      --bg-hover: var(--paper-200);
      --text: var(--espresso-800);
      --text-muted: var(--espresso-500);
      --text-dim: var(--espresso-400);
      --accent: var(--amber-400);
      --accent-strong: var(--amber-500);
      --accent-cool: var(--green-400);
      --accent-red: var(--terracotta-500);
      --success: var(--green-500);
      --warn: var(--amber-400);
      --border: var(--paper-300);
      --border-strong: var(--paper-400);
      --border-focus: rgba(111, 138, 106, 0.5);
      --radius: 10px;
      --radius-sm: 6px;
      --radius-pill: 999px;
      --shadow: 0 1px 2px rgba(26, 24, 20, 0.06), 0 1px 3px rgba(26, 24, 20, 0.08);
      --shadow-lg: 0 4px 12px rgba(26, 24, 20, 0.08), 0 2px 4px rgba(26, 24, 20, 0.06);
      --font-display: Georgia, "Times New Roman", serif;
      --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;

      /* Decision badges */
      --badge-buy: var(--green-500);
      --badge-buy-fg: var(--paper-50);
      --badge-use-soon: var(--amber-100);
      --badge-use-soon-fg: var(--espresso-800);
      --badge-skip: var(--paper-200);
      --badge-skip-fg: var(--espresso-500);
      --badge-compare: var(--paper-200);
      --badge-compare-fg: var(--espresso-500);
      --badge-confirm: var(--terracotta-500);
      --badge-confirm-fg: var(--paper-50);
      --badge-watch: var(--green-100);
      --badge-watch-fg: var(--espresso-800);
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: var(--paper-900);
        --bg-elevated: var(--paper-800);
        --bg-card: var(--paper-800);
        --bg-soft: var(--paper-700);
        --bg-hover: var(--paper-700);
        --text: var(--paper-100);
        --text-muted: var(--paper-400);
        --text-dim: var(--paper-500);
        --border: rgba(212, 163, 75, 0.12);
        --border-strong: rgba(212, 163, 75, 0.18);
        --shadow: 0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.2);
        --shadow-lg: 0 4px 12px rgba(0,0,0,0.35), 0 2px 4px rgba(0,0,0,0.25);
      }
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0; min-height: 100%;
      background: var(--bg);
      color: var(--text);
      font-family: var(--font-body);
      font-size: 15px;
      line-height: 1.55;
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden;
    }
    a { color: inherit; text-decoration: none; }
    a:hover { color: var(--accent-strong); }
    button, input, select, textarea { font: inherit; }
    ::selection { background: rgba(212, 163, 75, 0.25); color: var(--text); }
    .shell {
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px 20px 48px;
    }
    .masthead {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-mark {
      width: 32px; height: 32px;
      border-radius: var(--radius);
      background: var(--accent-cool);
      display: flex; align-items: center; justify-content: center;
      font-family: var(--font-display); font-weight: 700; font-size: 1rem;
      color: var(--paper-50); flex-shrink: 0;
    }
    .brand-text h1 {
      margin: 0;
      font-family: var(--font-display);
      font-size: 1.25rem;
      font-weight: 650;
      letter-spacing: -0.02em;
      line-height: 1.2;
    }
    .brand-text .lede {
      margin: 0;
      font-size: 0.78rem;
      color: var(--text-dim);
    }
    .status-bar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .storyboard {
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
      gap: 16px;
      margin-bottom: 20px;
      align-items: stretch;
    }
    .story-panel {
      position: relative;
      overflow: hidden;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }
    .story-panel-inner {
      position: relative;
      z-index: 1;
      display: grid;
      gap: 12px;
    }
    .story-kicker {
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.16em;
      color: var(--accent-strong);
      font-weight: 650;
    }
    .story-title {
      margin: 0;
      font-family: var(--font-display);
      font-size: clamp(1.5rem, 3vw, 2.25rem);
      line-height: 1.02;
      letter-spacing: -0.03em;
      max-width: 12ch;
    }
    .story-copy {
      margin: 0;
      max-width: 60ch;
      color: var(--text-muted);
    }
    .story-badges {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .story-rail {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .story-tile {
      display: grid;
      gap: 10px;
      align-content: start;
      text-align: left;
      border: 1px solid var(--border);
      border-radius: calc(var(--radius) + 2px);
      background: var(--bg-card);
      color: var(--text);
      padding: 14px;
      min-height: 132px;
      transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
    }
    .story-tile:hover {
      transform: translateY(-1px);
      border-color: var(--border-strong);
      background: var(--bg-soft);
    }
    .story-tile-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
    }
    .story-tile-title {
      font-family: var(--font-display);
      font-size: 1rem;
      font-weight: 650;
      letter-spacing: -0.02em;
    }
    .story-tile-note {
      color: var(--text-dim);
      font-size: 0.84rem;
      line-height: 1.4;
    }
    .status-dot {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 10px;
      border-radius: var(--radius-pill);
      background: var(--bg-card);
      border: 1px solid var(--border);
      font-size: 0.72rem;
      font-weight: 500;
      color: var(--text-muted);
      white-space: nowrap;
    }
    .status-dot::before {
      content: "";
      width: 6px; height: 6px;
      border-radius: 50%;
      background: var(--border-strong);
      flex-shrink: 0;
    }
    .status-dot[data-tone="good"]::before { background: var(--success); }
    .status-dot[data-tone="warn"]::before { background: var(--warn); }
    .status-dot[data-tone="bad"]::before { background: var(--accent-red); }

    /* Decision badge system — aligned with mobile decision tokens */
    .decision {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 5px 10px;
      border-radius: var(--radius-pill);
      font-size: 0.75rem;
      font-weight: 600;
      white-space: nowrap;
      border: 1px solid transparent;
    }
    .decision-buy { background: var(--badge-buy); color: var(--badge-buy-fg); }
    .decision-use-soon { background: var(--badge-use-soon); color: var(--badge-use-soon-fg); border-color: var(--amber-200); }
    .decision-skip { background: var(--badge-skip); color: var(--badge-skip-fg); border-color: var(--paper-300); }
    .decision-compare { background: var(--badge-compare); color: var(--badge-compare-fg); border-color: var(--paper-300); }
    .decision-confirm { background: var(--badge-confirm); color: var(--badge-confirm-fg); }
    .decision-watch { background: var(--badge-watch); color: var(--badge-watch-fg); border-color: var(--green-200); }
    .decision-unknown { background: var(--bg-soft); color: var(--text-dim); border-color: var(--border); }
    .panel {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
    }
    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
    }
    .panel-header h2, .panel-header h3 {
      margin: 0;
      font-family: var(--font-display);
      font-size: 1rem;
      font-weight: 600;
      letter-spacing: -0.01em;
    }
    .panel-header h3 { font-size: 0.85rem; color: var(--text-muted); }
    .panel-badge {
      font-size: 0.7rem;
      padding: 2px 8px;
      border-radius: var(--radius-pill);
      background: var(--bg-soft);
      color: var(--text-dim);
      border: 1px solid var(--border);
    }
    .panel-badge[data-tone="good"] { color: var(--success); border-color: var(--green-200); background: var(--green-50); }
    .panel-badge[data-tone="warn"] { color: var(--warn); border-color: var(--amber-200); background: var(--amber-50); }
    .panel-badge[data-tone="bad"] { color: var(--accent-red); border-color: var(--terracotta-200); background: var(--terracotta-50); }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
    }
    .metric {
      padding: 14px;
      border-radius: var(--radius);
      background: var(--bg-elevated);
      border: 1px solid var(--border);
    }
    .metric .label {
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-dim);
      margin-bottom: 6px;
    }
    .metric .value {
      font-family: var(--font-display);
      font-size: 1.6rem;
      font-weight: 600;
      letter-spacing: -0.03em;
      line-height: 1;
    }
    .list-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .list-group { display: grid; gap: 8px; }
    .list-group-title {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-dim);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .item {
      padding: 12px;
      border-radius: var(--radius);
      background: var(--bg-elevated);
      border: 1px solid var(--border);
      display: grid;
      gap: 4px;
    }
    .item-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 8px;
    }
    .item-title { font-weight: 550; font-size: 0.92rem; }
    .item-meta { color: var(--text-dim); font-size: 0.82rem; }
    .pill {
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: var(--radius-pill);
      background: var(--bg-soft);
      border: 1px solid var(--border);
      font-size: 0.7rem;
      color: var(--text-muted);
      white-space: nowrap;
    }
    .pill[data-tone="good"] { color: var(--success); border-color: var(--green-200); background: var(--green-50); }
    .pill[data-tone="warn"] { color: var(--warn); border-color: var(--amber-200); background: var(--amber-50); }
    .pill[data-tone="bad"] { color: var(--accent-red); border-color: var(--terracotta-200); background: var(--terracotta-50); }
    .cmd-grid {
      display: grid;
      grid-template-columns: 1.3fr 0.7fr;
      gap: 14px;
    }
    .cmd-box {
      display: grid;
      gap: 10px;
    }
    .cmd-box textarea {
      width: 100%;
      min-height: 80px;
      resize: vertical;
      padding: 12px;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      background: var(--bg-elevated);
      color: var(--text);
      outline: none;
      font-size: 0.9rem;
      line-height: 1.5;
    }
    .cmd-box textarea::placeholder { color: var(--text-dim); }
    .cmd-box textarea:focus {
      border-color: var(--border-focus);
      box-shadow: 0 0 0 3px rgba(212, 163, 75, 0.12);
    }
    .cmd-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .cmd-quick {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }
    .preview-box {
      padding: 12px;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      background: var(--bg-elevated);
      min-height: 80px;
      font-size: 0.85rem;
    }
    .preview-box[data-tone="muted"] { color: var(--text-dim); }
    .preview-box[data-tone="good"] { color: var(--success); }
    .preview-box[data-tone="warn"] { color: var(--warn); }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 14px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: var(--bg-soft);
      color: var(--text);
      font-size: 0.82rem;
      font-weight: 500;
      cursor: pointer;
      transition: background 120ms, border-color 120ms;
      white-space: nowrap;
    }
    .btn:hover { background: var(--bg-hover); border-color: var(--border-strong); }
    .btn:active { transform: scale(0.98); }
    .btn:focus-visible {
      outline: none;
      box-shadow: 0 0 0 3px rgba(212, 163, 75, 0.2);
    }
    .btn-primary {
      background: rgba(212, 163, 75, 0.15);
      border-color: rgba(212, 163, 75, 0.3);
      color: var(--accent-strong);
    }
    .btn-primary:hover { background: rgba(212, 163, 75, 0.22); }
    .btn-ghost {
      background: transparent;
      border-color: transparent;
      color: var(--text-muted);
    }
    .btn-ghost:hover { background: var(--bg-soft); color: var(--text); }
    .btn-danger {
      background: rgba(212, 120, 106, 0.12);
      border-color: rgba(212, 120, 106, 0.3);
      color: var(--accent-red);
    }
    .btn-danger:hover { background: rgba(212, 120, 106, 0.2); }
    .btn-sm { padding: 4px 10px; font-size: 0.75rem; }
    .btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .mini-chip {
      display: inline-flex;
      padding: 4px 10px;
      border-radius: var(--radius-pill);
      border: 1px solid var(--border);
      background: transparent;
      color: var(--text-dim);
      font-size: 0.75rem;
      cursor: pointer;
      transition: background 120ms, color 120ms;
    }
    .mini-chip:hover { background: var(--bg-soft); color: var(--text-muted); }
    .field {
      display: grid;
      gap: 4px;
    }
    .field-label {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-dim);
    }
    .field input, .field select {
      padding: 8px 10px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: var(--bg-elevated);
      color: var(--text);
      outline: none;
      font-size: 0.88rem;
    }
    .field input::placeholder { color: var(--text-dim); }
    .field input:focus, .field select:focus {
      border-color: var(--border-focus);
      box-shadow: 0 0 0 3px rgba(212, 163, 75, 0.12);
    }
    .field select { cursor: pointer; }
    .field-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .field-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .log {
      display: grid;
      gap: 6px;
      font-family: var(--font-mono);
      font-size: 0.75rem;
      color: var(--text-dim);
    }
    .log-line {
      border-left: 2px solid rgba(127, 176, 131, 0.35);
      padding-left: 10px;
    }
    .auth-panel { display: grid; gap: 14px; }
    .token-row { display: flex; gap: 6px; align-items: center; }
    .collapse-toggle {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      padding: 12px 16px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--bg-card);
      color: var(--text-muted);
      font-size: 0.82rem;
      font-weight: 500;
      cursor: pointer;
      transition: background 120ms;
    }
    .collapse-toggle:hover { background: var(--bg-hover); }
    .collapse-toggle::after {
      content: "\u25BC";
      font-size: 0.65rem;
      color: var(--text-dim);
      transition: transform 200ms;
    }
    .collapse-toggle[aria-expanded="true"]::after {
      transform: rotate(180deg);
    }
    .collapse-body {
      display: none;
      padding: 16px;
      border: 1px solid var(--border);
      border-top: none;
      border-radius: 0 0 var(--radius) var(--radius);
      background: var(--bg-card);
    }
    .collapse-body.open { display: grid; gap: 16px; }
    .collapse-group {
      display: grid;
      gap: 0;
    }
    .collapse-group:not(:first-child) { margin-top: 12px; }
    .subtle { color: var(--text-muted); font-size: 0.85rem; }
    .tiny { color: var(--text-dim); font-size: 0.72rem; }
    .hidden { display: none !important; }
    .stack { display: grid; gap: 10px; }
    .gap-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
    .dashboard-grid {
      display: grid;
      grid-template-columns: 1fr 360px;
      gap: 20px;
      align-items: start;
    }
    .main-col { display: grid; gap: 20px; }
    .side-col { display: grid; gap: 20px; }
    @media (max-width: 1024px) {
      .storyboard { grid-template-columns: 1fr; }
      .dashboard-grid { grid-template-columns: 1fr; }
      .side-col { display: grid; gap: 20px; }
      .metrics { grid-template-columns: repeat(2, 1fr); }
      .story-rail { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 768px) {
      .shell { padding: 16px 12px 32px; }
      .masthead {
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
      }
      .status-bar { width: 100%; }
      .cmd-grid { grid-template-columns: 1fr; }
      .list-grid { grid-template-columns: 1fr; }
      .field-row { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(2, 1fr); }
      .story-rail { grid-template-columns: 1fr; }
      .panel { padding: 14px; }
    }
    @media (max-width: 480px) {
      .metrics { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell" data-shell-root="true">
    <header class="masthead">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">S</div>
        <div class="brand-text">
          <h1>__APP_TITLE__</h1>
          <p class="lede">__APP_SUBTITLE__</p>
        </div>
      </div>
      <div class="status-bar">
        <span class="status-dot" data-tone="warn" id="runtime-pill">Loading</span>
        <span class="status-dot" data-tone="warn" id="household-pill">Not connected</span>
        <span class="status-dot" data-tone="warn" id="health-pill">Checking</span>
      </div>
    </header>

    <section class="storyboard" aria-labelledby="story-title">
      <div class="panel story-panel">
        <div class="story-panel-inner">
          <div class="story-kicker">Today</div>
          <h2 class="story-title" id="story-title">Loading your household story.</h2>
          <p class="story-copy" id="story-copy">We are turning pantry, shopping, and planning into one quick pass so the next move is obvious.</p>
          <div class="story-badges" id="story-badges">
            <span class="pill" data-tone="warn">Waiting for dashboard data</span>
          </div>
        </div>
      </div>
      <div class="story-rail" aria-label="Quick actions">
        <button class="story-tile" type="button" data-quick-command="What should I buy today?">
          <div class="story-tile-head">
            <div class="story-tile-title">Buy now</div>
            <span class="pill" id="story-buy-pill">—</span>
          </div>
          <div class="story-tile-note" id="story-buy-note">See the tightest restock gaps first.</div>
        </button>
        <button class="story-tile" type="button" data-quick-command="What should I use first?">
          <div class="story-tile-head">
            <div class="story-tile-title">Use first</div>
            <span class="pill" id="story-use-pill">—</span>
          </div>
          <div class="story-tile-note" id="story-use-note">Turn near-expiry items into dinner before they drift.</div>
        </button>
        <button class="story-tile" type="button" data-quick-command="What can I cook from what I have?">
          <div class="story-tile-head">
            <div class="story-tile-title">Cook tonight</div>
            <span class="pill" id="story-cook-pill">—</span>
          </div>
          <div class="story-tile-note" id="story-cook-note">Push today’s pantry into something easy.</div>
        </button>
        <button class="story-tile" type="button" data-quick-command="Show me the best deal and what is sold out.">
          <div class="story-tile-head">
            <div class="story-tile-title">Explore</div>
            <span class="pill" id="story-explore-pill">—</span>
          </div>
          <div class="story-tile-note" id="story-explore-note">Compare, search, and inspect the oddball signals.</div>
        </button>
      </div>
    </section>

    <div class="dashboard-grid">

      <div class="main-col">
        <section class="panel" aria-labelledby="cmd-title">
          <div class="panel-header">
            <h2 id="cmd-title">Command</h2>
            <span class="tiny" id="preview-mode">parse-only</span>
          </div>
          <div class="cmd-grid">
            <div class="cmd-box">
              <textarea id="command-input" rows="3" placeholder="Add milk and bread to the shopping list, then show me what is running low."></textarea>
              <div class="cmd-actions">
                <button class="btn btn-primary" id="preview-btn" type="button">Preview</button>
                <button class="btn" id="execute-btn" type="button">Execute</button>
                <button class="btn btn-ghost" id="clear-btn" type="button">Clear</button>
              </div>
              <div class="cmd-quick">
                <button class="mini-chip" type="button" data-quick-command="Add milk to the shopping list.">Milk</button>
                <button class="mini-chip" type="button" data-quick-command="Log bread as purchased.">Log purchase</button>
                <button class="mini-chip" type="button" data-quick-command="What should I buy today?">Ask</button>
                <button class="mini-chip" type="button" data-quick-command="Mark tomatoes as consumed.">Use up</button>
              </div>
            </div>
            <div>
              <div class="preview-box" id="preview-box" data-tone="muted">Start typing a command to see how the parser routes it.</div>
            </div>
          </div>
        </section>

        <section class="panel" aria-labelledby="dash-title">
          <div class="panel-header">
            <h2 id="dash-title">Household</h2>
            <span class="tiny" id="household-meta">Connect to see your data</span>
          </div>
          <div class="metrics" id="metric-grid">
            <div class="metric"><div class="label">Pantry</div><div class="value">—</div></div>
            <div class="metric"><div class="label">Use soon</div><div class="value">—</div></div>
            <div class="metric"><div class="label">Low items</div><div class="value">—</div></div>
            <div class="metric"><div class="label">Recent buys</div><div class="value">—</div></div>
          </div>
        </section>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
          <section class="panel" aria-labelledby="inv-title">
            <div class="panel-header">
              <h3 id="inv-title">Inventory</h3>
              <span class="panel-badge" id="decision-pill" data-tone="warn">idle</span>
            </div>
            <div class="stack">
              <div class="field-row">
                <label class="field">
                  <span class="field-label">Item</span>
                  <input id="inventory-canonical" autocomplete="off" placeholder="milk">
                </label>
                <label class="field">
                  <span class="field-label">Name</span>
                  <input id="inventory-display" autocomplete="off" placeholder="Whole milk">
                </label>
              </div>
              <div class="field-row">
                <label class="field">
                  <span class="field-label">Qty</span>
                  <input id="inventory-qty" autocomplete="off" placeholder="1">
                </label>
                <label class="field">
                  <span class="field-label">Unit</span>
                  <input id="inventory-unit" autocomplete="off" placeholder="L">
                </label>
              </div>
              <div class="field-row">
                <label class="field">
                  <span class="field-label">Location</span>
                  <input id="inventory-location" autocomplete="off" placeholder="fridge">
                </label>
                <label class="field">
                  <span class="field-label">Category</span>
                  <input id="inventory-category" autocomplete="off" placeholder="dairy">
                </label>
              </div>
              <div class="field-actions">
                <button class="btn btn-primary" id="inventory-add-btn" type="button">Add</button>
                <button class="btn btn-ghost" id="inventory-refresh-btn" type="button">Refresh</button>
              </div>
              <div class="preview-box" id="decision-box" data-tone="muted" style="min-height:auto;padding:10px;">Click an item to inspect why it was classified.</div>
              <div class="stack" id="inventory-list"></div>
            </div>
          </section>

          <section class="panel" aria-labelledby="shopping-list-title">
            <div class="panel-header">
              <h3 id="shopping-list-title">Shopping list</h3>
              <span class="panel-badge" id="shopping-pill">idle</span>
            </div>
            <div class="stack">
              <div class="field">
                <span class="field-label">Goal</span>
                <input id="shopping-goal" autocomplete="off" placeholder="Stock up for the week">
              </div>
              <div class="field">
                <span class="field-label">Items</span>
                <input id="shopping-items" autocomplete="off" placeholder="milk, bread, tomatoes">
              </div>
              <div class="field-actions">
                <button class="btn btn-primary" id="shopping-create-btn" type="button">Create</button>
                <button class="btn" id="shopping-complete-btn" type="button">Complete</button>
                <button class="btn" id="shopping-mark-purchased-btn" type="button">Mark purchased</button>
                <button class="btn btn-ghost" id="shopping-refresh-btn" type="button">Refresh</button>
              </div>
              <div class="tiny" id="shopping-goal-text">No shopping list loaded yet.</div>
              <div class="stack" id="shopping-list"></div>
            </div>
          </section>
        </div>

        <section class="panel" aria-labelledby="lists-title">
          <div class="panel-header">
            <h2 id="lists-title">Quick lists</h2>
            <span class="panel-badge" id="api-status" data-tone="warn">idle</span>
          </div>
          <div class="list-grid">
            <div class="list-group">
              <div class="list-group-title">Use soon <span class="pill" id="use-soon-count">0</span></div>
              <div class="stack" id="use-soon-list"></div>
            </div>
            <div class="list-group">
              <div class="list-group-title">Low inventory <span class="pill" id="low-count">0</span></div>
              <div class="stack" id="low-list"></div>
            </div>
            <div class="list-group">
              <div class="list-group-title">Recent purchases <span class="pill" id="recent-count">0</span></div>
              <div class="stack" id="recent-list"></div>
            </div>
            <div class="list-group">
              <div class="list-group-title">Recent commands</div>
              <div class="stack" id="history-list"></div>
            </div>
          </div>
          <div class="log" id="event-log" style="margin-top:14px;">
            <div class="log-line">Load the page to fetch public runtime metadata.</div>
          </div>
        </section>
      </div>

      <div class="side-col">
        <section class="panel" aria-labelledby="connect-title">
          <div class="panel-header">
            <h2 id="connect-title">Connect</h2>
          </div>
          <div class="auth-panel">
            <div class="field-row">
              <label class="field">
                <span class="field-label">Device ID</span>
                <input id="device-id" autocomplete="off" placeholder="shopstack-web">
              </label>
              <label class="field">
                <span class="field-label">Secret</span>
                <input id="device-secret" autocomplete="off" placeholder="paste or generate">
              </label>
            </div>
            <div class="field-row">
              <label class="field">
                <span class="field-label">Household</span>
                <input id="household-name" autocomplete="off" placeholder="Default Household">
              </label>
              <label class="field">
                <span class="field-label">ID (optional)</span>
                <input id="household-id" autocomplete="off" placeholder="hh_default">
              </label>
            </div>
            <div class="field-actions">
              <button class="btn btn-primary" id="register-btn" type="button">Register</button>
              <button class="btn" id="login-btn" type="button">Login</button>
            </div>
            <div class="token-row">
              <input id="token-input" autocomplete="off" placeholder="Paste a bearer token" style="flex:1;padding:8px 10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--bg-elevated);color:var(--text);outline:none;font-size:0.85rem;">
              <button class="btn" id="use-token-btn" type="button" style="flex-shrink:0;">Use</button>
              <button class="btn btn-ghost" id="forget-token-btn" type="button" style="flex-shrink:0;">Clear</button>
            </div>
            <div class="field-row">
              <label class="field">
                <span class="field-label">Switch household</span>
                <select id="household-select">
                  <option value="">Connect first</option>
                </select>
              </label>
              <div class="field-actions" style="align-self:end;">
                <button class="btn" id="switch-btn" type="button">Switch</button>
                <button class="btn btn-ghost" id="refresh-btn" type="button">Refresh</button>
              </div>
            </div>
          </div>
        </section>

        <section class="panel" aria-labelledby="search-title">
          <div class="panel-header">
            <h2 id="search-title">Search</h2>
          </div>
          <div class="stack">
            <div class="field-row">
              <label class="field">
                <span class="field-label">Query</span>
                <input id="search-query" autocomplete="off" placeholder="milk">
              </label>
              <label class="field">
                <span class="field-label">Voice</span>
                <input id="voice-text" autocomplete="off" placeholder="Add milk and bread">
              </label>
            </div>
            <div class="field-actions">
              <button class="btn btn-primary" id="search-global-btn" type="button">Global</button>
              <button class="btn" id="search-inventory-btn" type="button">Inventory</button>
              <button class="btn btn-ghost" id="voice-intent-btn" type="button">Voice</button>
            </div>
            <div class="item">
              <div class="item-row">
                <div class="item-title">Global results</div>
                <span class="pill" id="search-global-pill">idle</span>
              </div>
              <div class="stack" id="search-global-list"></div>
            </div>
            <div class="item">
              <div class="item-row">
                <div class="item-title">Inventory results</div>
                <span class="pill" id="search-inventory-pill">idle</span>
              </div>
              <div class="stack" id="search-inventory-list"></div>
            </div>
            <div class="preview-box" id="voice-box" data-tone="muted" style="min-height:auto;padding:10px;">Voice intent will appear here.</div>
          </div>
        </section>

        <section class="panel" aria-labelledby="intel-title">
          <div class="panel-header">
            <h2 id="intel-title">Intelligence</h2>
          </div>
          <div class="stack">
            <div class="field-row">
              <label class="field">
                <span class="field-label">Window (days)</span>
                <input id="recurring-window" autocomplete="off" type="number" min="0" max="30" value="7">
              </label>
              <label class="field">
                <span class="field-label">Meal plan (days)</span>
                <input id="mealplan-days" autocomplete="off" type="number" min="1" max="28" value="7">
              </label>
            </div>
            <div class="field-actions">
              <button class="btn btn-primary" id="recurring-btn" type="button">Recurring</button>
              <button class="btn" id="mealplan-btn" type="button">Meal plan</button>
              <button class="btn btn-ghost" id="intel-refresh-btn" type="button">Refresh</button>
            </div>
            <div class="item">
              <div class="item-row">
                <div class="item-title">Recurring plan</div>
                <span class="pill" id="recurring-pill">idle</span>
              </div>
              <div class="item-meta" id="recurring-summary">No recurring plan loaded.</div>
              <div class="stack" id="recurring-list"></div>
            </div>
            <div class="item">
              <div class="item-row">
                <div class="item-title">Meal plan</div>
                <span class="pill" id="mealplan-pill">idle</span>
              </div>
              <div class="item-meta" id="mealplan-summary">No meal plan loaded.</div>
              <div class="stack" id="mealplan-list"></div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <div style="margin-top:20px;">
      <button class="collapse-toggle" id="settings-toggle" type="button" aria-expanded="false" aria-controls="settings-body">
        Settings &amp; advanced
      </button>
      <div class="collapse-body" id="settings-body">
        <div class="collapse-group">
          <div class="panel" style="border-radius:var(--radius);">
            <div class="panel-header">
              <h3>Runtime</h3>
              <span class="panel-badge" id="runtime-diagnostics-pill">idle</span>
            </div>
            <div class="item-meta" id="runtime-diagnostics-summary">No runtime diagnostics loaded.</div>
            <div class="stack" id="runtime-diagnostics-list"></div>
            <div class="field-actions" style="margin-top:10px;">
              <button class="btn" id="runtime-refresh-btn" type="button">Refresh</button>
            </div>
          </div>

          <div class="panel" style="border-radius:var(--radius);">
            <div class="panel-header">
              <h3>Privacy</h3>
              <span class="panel-badge" id="privacy-pill">idle</span>
            </div>
            <div class="item-meta" id="privacy-summary">No retention summary loaded.</div>
            <div class="stack" id="privacy-list"></div>
            <div class="field-row" style="margin-top:10px;">
              <label class="field">
                <span class="field-label">Profile</span>
                <select id="privacy-profile">
                  <option value="balanced">Balanced</option>
                  <option value="strict">Strict</option>
                  <option value="shared">Shared</option>
                </select>
              </label>
              <div class="field-actions" style="align-self:end;">
                <button class="btn btn-primary" id="privacy-apply-profile-btn" type="button">Apply</button>
              </div>
            </div>
            <div class="tiny" id="privacy-profile-summary">Balanced defaults: 30-day traces, 90-day community pool, local locale persistence.</div>
            <div class="field-row" style="margin-top:10px;">
              <label class="field">
                <span class="field-label">Setting</span>
                <select id="privacy-key">
                  <option value="retention.trace_ttl_days">Trace TTL</option>
                  <option value="retention.community_pool_retention_days">Community pool</option>
                  <option value="retention.voice_memo_retention_days">Voice memos</option>
                  <option value="retention.sms_registry_retention_days">SMS registry</option>
                  <option value="retention.backup_retention_days">Backups</option>
                  <option value="retention.locale_persistence">Locale persistence</option>
                  <option value="retention.community_optin">Community opt-in</option>
                </select>
              </label>
              <label class="field">
                <span class="field-label">Value</span>
                <input id="privacy-value" autocomplete="off" placeholder="30, 0, or 1">
              </label>
            </div>
            <div class="field-row">
              <label class="field">
                <span class="field-label">Purge confirm</span>
                <input id="privacy-confirm" autocomplete="off" placeholder="PURGE">
              </label>
              <div class="field-actions" style="align-self:end;">
                <button class="btn btn-primary" id="privacy-update-btn" type="button">Update</button>
                <button class="btn btn-danger" id="privacy-purge-btn" type="button">Purge</button>
              </div>
            </div>
            <div class="field-actions" style="margin-top:10px;">
              <button class="btn" id="privacy-refresh-btn" type="button">Refresh</button>
              <button class="btn btn-ghost" id="undo-btn" type="button">Undo last</button>
            </div>
          </div>

          <div class="panel" style="border-radius:var(--radius);">
            <div class="panel-header">
              <h3>Corrections</h3>
              <span class="panel-badge" id="corrections-pill">idle</span>
            </div>
            <div class="item-meta" id="corrections-summary">No corrections loaded.</div>
            <div class="stack" id="corrections-list"></div>
            <div class="field-row" style="margin-top:10px;">
              <label class="field">
                <span class="field-label">Item</span>
                <input id="correction-canonical" autocomplete="off" placeholder="milk">
              </label>
              <label class="field">
                <span class="field-label">Was</span>
                <input id="correction-was-action" autocomplete="off" placeholder="buy">
              </label>
            </div>
            <div class="field-row">
              <label class="field">
                <span class="field-label">Should be</span>
                <input id="correction-should-action" autocomplete="off" placeholder="use_soon">
              </label>
              <label class="field">
                <span class="field-label">Reason</span>
                <input id="correction-reason" autocomplete="off" placeholder="We finish it faster">
              </label>
            </div>
            <div class="field-actions" style="margin-top:10px;">
              <button class="btn btn-primary" id="correction-create-btn" type="button">Record</button>
              <button class="btn btn-ghost" id="corrections-refresh-btn" type="button">Refresh</button>
            </div>
          </div>

          <div class="panel" style="border-radius:var(--radius);">
            <div class="panel-header">
              <h3>Traces</h3>
              <span class="panel-badge" id="trace-pill">idle</span>
            </div>
            <div class="item-meta" id="trace-summary">No traces loaded.</div>
            <div class="field-row">
              <label class="field">
                <span class="field-label">Search</span>
                <input id="trace-search" autocomplete="off" placeholder="milk">
              </label>
              <label class="field">
                <span class="field-label">Type</span>
                <input id="trace-type" autocomplete="off" placeholder="command">
              </label>
            </div>
            <div class="field-actions" style="margin-top:10px;">
              <button class="btn" id="trace-refresh-btn" type="button">Refresh</button>
            </div>
            <div class="stack" id="trace-list"></div>
            <div class="item">
              <div class="item-row">
                <div class="item-title">Detail</div>
                <span class="pill">redacted</span>
              </div>
              <div class="preview-box" id="trace-detail" data-tone="muted" style="min-height:auto;padding:10px;">Pick a trace to inspect.</div>
            </div>
            <div class="item">
              <div class="item-row">
                <div class="item-title">Export</div>
                <span class="panel-badge" id="trace-export-pill">idle</span>
              </div>
              <div class="preview-box" id="trace-export" data-tone="muted" style="min-height:auto;padding:10px;">Redacted JSONL export will appear here.</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div style="margin-top:24px; padding-top:16px; border-top:1px solid var(--border); display:flex; justify-content:space-between; align-items:center;flex-wrap:wrap;gap:8px;">
      <span class="tiny" id="runtime-detail"></span>
      <span class="tiny" id="household-detail"></span>
      <span class="tiny" id="health-detail"></span>
    </div>
  </div>

  <script>
  (function() {
    const API_BASE = "__API_BASE__";
    const STORAGE_KEY = "__AUTH_STORAGE_KEY__";
    const els = {
      runtimePill: document.getElementById('runtime-pill'),
      runtimeDetail: document.getElementById('runtime-detail'),
      householdPill: document.getElementById('household-pill'),
      householdDetail: document.getElementById('household-detail'),
      healthPill: document.getElementById('health-pill'),
      healthDetail: document.getElementById('health-detail'),
      commandInput: document.getElementById('command-input'),
      previewBtn: document.getElementById('preview-btn'),
      executeBtn: document.getElementById('execute-btn'),
      clearBtn: document.getElementById('clear-btn'),
      previewBox: document.getElementById('preview-box'),
      previewMode: document.getElementById('preview-mode'),
      storyTitle: document.getElementById('story-title'),
      storyCopy: document.getElementById('story-copy'),
      storyBadges: document.getElementById('story-badges'),
      storyBuyPill: document.getElementById('story-buy-pill'),
      storyUsePill: document.getElementById('story-use-pill'),
      storyCookPill: document.getElementById('story-cook-pill'),
      storyExplorePill: document.getElementById('story-explore-pill'),
      storyBuyNote: document.getElementById('story-buy-note'),
      storyUseNote: document.getElementById('story-use-note'),
      storyCookNote: document.getElementById('story-cook-note'),
      storyExploreNote: document.getElementById('story-explore-note'),
      deviceId: document.getElementById('device-id'),
      deviceSecret: document.getElementById('device-secret'),
      householdName: document.getElementById('household-name'),
      householdId: document.getElementById('household-id'),
      tokenInput: document.getElementById('token-input'),
      useTokenBtn: document.getElementById('use-token-btn'),
      forgetTokenBtn: document.getElementById('forget-token-btn'),
      registerBtn: document.getElementById('register-btn'),
      loginBtn: document.getElementById('login-btn'),
      householdSelect: document.getElementById('household-select'),
      switchBtn: document.getElementById('switch-btn'),
      refreshBtn: document.getElementById('refresh-btn'),
      metricGrid: document.getElementById('metric-grid'),
      householdMeta: document.getElementById('household-meta'),
      inventoryCanonical: document.getElementById('inventory-canonical'),
      inventoryDisplay: document.getElementById('inventory-display'),
      inventoryQty: document.getElementById('inventory-qty'),
      inventoryUnit: document.getElementById('inventory-unit'),
      inventoryLocation: document.getElementById('inventory-location'),
      inventoryCategory: document.getElementById('inventory-category'),
      inventoryAddBtn: document.getElementById('inventory-add-btn'),
      inventoryRefreshBtn: document.getElementById('inventory-refresh-btn'),
      inventoryList: document.getElementById('inventory-list'),
      decisionPill: document.getElementById('decision-pill'),
      decisionBox: document.getElementById('decision-box'),
      shoppingGoal: document.getElementById('shopping-goal'),
      shoppingItems: document.getElementById('shopping-items'),
      shoppingCreateBtn: document.getElementById('shopping-create-btn'),
      shoppingCompleteBtn: document.getElementById('shopping-complete-btn'),
      shoppingMarkPurchasedBtn: document.getElementById('shopping-mark-purchased-btn'),
      shoppingRefreshBtn: document.getElementById('shopping-refresh-btn'),
      shoppingListTitle: document.getElementById('shopping-list-title'),
      shoppingPill: document.getElementById('shopping-pill'),
      shoppingGoalText: document.getElementById('shopping-goal-text'),
      shoppingList: document.getElementById('shopping-list'),
      searchQuery: document.getElementById('search-query'),
      voiceText: document.getElementById('voice-text'),
      searchGlobalBtn: document.getElementById('search-global-btn'),
      searchInventoryBtn: document.getElementById('search-inventory-btn'),
      voiceIntentBtn: document.getElementById('voice-intent-btn'),
      searchGlobalPill: document.getElementById('search-global-pill'),
      searchInventoryPill: document.getElementById('search-inventory-pill'),
      searchGlobalList: document.getElementById('search-global-list'),
      searchInventoryList: document.getElementById('search-inventory-list'),
      voiceBox: document.getElementById('voice-box'),
      recurringBtn: document.getElementById('recurring-btn'),
      mealplanBtn: document.getElementById('mealplan-btn'),
      intelRefreshBtn: document.getElementById('intel-refresh-btn'),
      recurringPill: document.getElementById('recurring-pill'),
      recurringSummary: document.getElementById('recurring-summary'),
      recurringList: document.getElementById('recurring-list'),
      mealplanPill: document.getElementById('mealplan-pill'),
      mealplanSummary: document.getElementById('mealplan-summary'),
      mealplanList: document.getElementById('mealplan-list'),
      runtimeDiagnosticsPill: document.getElementById('runtime-diagnostics-pill'),
      runtimeDiagnosticsSummary: document.getElementById('runtime-diagnostics-summary'),
      runtimeDiagnosticsList: document.getElementById('runtime-diagnostics-list'),
      runtimeRefreshBtn: document.getElementById('runtime-refresh-btn'),
      privacyPill: document.getElementById('privacy-pill'),
      privacySummary: document.getElementById('privacy-summary'),
      privacyList: document.getElementById('privacy-list'),
      privacyProfile: document.getElementById('privacy-profile'),
      privacyProfileSummary: document.getElementById('privacy-profile-summary'),
      privacyApplyProfileBtn: document.getElementById('privacy-apply-profile-btn'),
      privacyKey: document.getElementById('privacy-key'),
      privacyValue: document.getElementById('privacy-value'),
      privacyConfirm: document.getElementById('privacy-confirm'),
      privacyUpdateBtn: document.getElementById('privacy-update-btn'),
      privacyPurgeBtn: document.getElementById('privacy-purge-btn'),
      privacyRefreshBtn: document.getElementById('privacy-refresh-btn'),
      undoBtn: document.getElementById('undo-btn'),
      correctionsPill: document.getElementById('corrections-pill'),
      correctionsSummary: document.getElementById('corrections-summary'),
      correctionsList: document.getElementById('corrections-list'),
      correctionCanonical: document.getElementById('correction-canonical'),
      correctionWasAction: document.getElementById('correction-was-action'),
      correctionShouldAction: document.getElementById('correction-should-action'),
      correctionReason: document.getElementById('correction-reason'),
      correctionCreateBtn: document.getElementById('correction-create-btn'),
      correctionsRefreshBtn: document.getElementById('corrections-refresh-btn'),
      traceSearch: document.getElementById('trace-search'),
      traceType: document.getElementById('trace-type'),
      traceRefreshBtn: document.getElementById('trace-refresh-btn'),
      tracePill: document.getElementById('trace-pill'),
      traceSummary: document.getElementById('trace-summary'),
      traceList: document.getElementById('trace-list'),
      traceDetail: document.getElementById('trace-detail'),
      traceExport: document.getElementById('trace-export'),
      traceExportPill: document.getElementById('trace-export-pill'),
      recurringWindow: document.getElementById('recurring-window'),
      mealplanDays: document.getElementById('mealplan-days'),
      historyList: document.getElementById('history-list'),
      useSoonCount: document.getElementById('use-soon-count'),
      lowCount: document.getElementById('low-count'),
      recentCount: document.getElementById('recent-count'),
      useSoonList: document.getElementById('use-soon-list'),
      lowList: document.getElementById('low-list'),
      recentList: document.getElementById('recent-list'),
      apiStatus: document.getElementById('api-status'),
      eventLog: document.getElementById('event-log'),
    };

    function esc(value) {
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function log(message, tone) {
      const line = document.createElement('div');
      line.className = 'log-line';
      line.textContent = message;
      if (tone === 'good') {
        line.style.borderLeftColor = 'var(--success)';
      } else if (tone === 'warn') {
        line.style.borderLeftColor = 'var(--warn)';
      } else if (tone === 'bad') {
        line.style.borderLeftColor = 'var(--accent-red)';
      }
      els.eventLog.prepend(line);
      while (els.eventLog.children.length > 8) {
        els.eventLog.lastElementChild && els.eventLog.lastElementChild.remove();
      }
    }

    function setPill(el, text, tone) {
      el.textContent = text;
      if (tone) {
        el.dataset.tone = tone;
      }
    }

    function readSession() {
      try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {};
      } catch (err) {
        return {};
      }
    }

    function saveSession(patch) {
      const current = readSession();
      const next = Object.assign({}, current, patch);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    }

    function clearSession() {
      localStorage.removeItem(STORAGE_KEY);
      return {};
    }

    function currentToken() {
      const session = readSession();
      return session.token || '';
    }

    function tokenHeaders() {
      const token = currentToken();
      return token ? { Authorization: `Bearer ${token}` } : {};
    }

    async function requestJson(path, options = {}, auth = false) {
      const headers = Object.assign({ Accept: 'application/json' }, options.headers || {});
      if (auth) {
        Object.assign(headers, tokenHeaders());
      }
      let body = options.body;
      if (body && typeof body === 'object' && !(body instanceof FormData) && !(body instanceof Blob)) {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(body);
      }
      const response = await fetch(`${API_BASE}${path}`, Object.assign({}, options, {
        headers,
        body,
      }));
      let payload = null;
      const text = await response.text();
      if (text) {
        try {
          payload = JSON.parse(text);
        } catch (err) {
          payload = { detail: text };
        }
      }
      if (!response.ok) {
        const message = payload && payload.detail && payload.detail.message
          ? payload.detail.message
          : payload && payload.message
            ? payload.message
            : `Request failed with ${response.status}`;
        const error = new Error(message);
        error.status = response.status;
        error.payload = payload;
        throw error;
      }
      return payload;
    }

    async function requestHealth() {
      const response = await fetch(`${API_BASE}/meta/health`, {
        headers: { Accept: 'application/json' },
      });
      const text = await response.text();
      let payload = null;
      if (text) {
        try {
          payload = JSON.parse(text);
        } catch (err) {
          payload = { detail: text };
        }
      }
      return { ok: response.ok, status: response.status, payload };
    }

    function renderPreview(data) {
      if (!data) {
        els.previewBox.dataset.tone = 'muted';
        els.previewBox.textContent = 'Start typing a command to see how the parser routes it.';
        els.previewMode.textContent = 'parse-only';
        return;
      }
      els.previewMode.textContent = data.route_kind || 'parse-only';
      const tone = data.would_mutate ? 'warn' : 'good';
      els.previewBox.dataset.tone = tone;
      els.previewBox.innerHTML = `
        <div class="item-row">
          <strong>${esc(data.intent && data.intent.action ? data.intent.action : 'unknown')}</strong>
          <span class="pill" data-tone="${tone}">${data.would_mutate ? 'mutating' : 'safe'}</span>
        </div>
        <div class="subtle" style="margin-top:8px;">${esc(data.summary || '')}</div>
        <div class="tiny" style="margin-top:10px;">Canonical: ${esc(data.intent && data.intent.canonical_name ? data.intent.canonical_name : '—')}</div>
      `;
    }

    function renderTodayStory(data) {
      if (!data) {
        if (els.storyTitle) {
          els.storyTitle.textContent = 'Loading your household story.';
        }
        if (els.storyCopy) {
          els.storyCopy.textContent = 'We are turning pantry, shopping, and planning into one quick pass so the next move is obvious.';
        }
        if (els.storyBadges) {
          els.storyBadges.innerHTML = '<span class="pill" data-tone="warn">Waiting for dashboard data</span>';
        }
        if (els.storyBuyPill) els.storyBuyPill.textContent = '—';
        if (els.storyUsePill) els.storyUsePill.textContent = '—';
        if (els.storyCookPill) els.storyCookPill.textContent = '—';
        if (els.storyExplorePill) els.storyExplorePill.textContent = '—';
        if (els.storyBuyNote) els.storyBuyNote.textContent = 'See the tightest restock gaps first.';
        if (els.storyUseNote) els.storyUseNote.textContent = 'Turn near-expiry items into dinner before they drift.';
        if (els.storyCookNote) els.storyCookNote.textContent = 'Push today’s pantry into something easy.';
        if (els.storyExploreNote) els.storyExploreNote.textContent = 'Compare, search, and inspect the oddball signals.';
        return;
      }

      const pantry = Number(data.pantry_count ?? 0);
      const useSoon = Number(data.use_soon_count ?? 0);
      const low = Number(data.low_items_count ?? 0);
      const recent = Number(data.recent_purchases_count ?? 0);
      const plural = (n) => `${n} item${n === 1 ? '' : 's'}`;
      const badges = [
        [plural(pantry), 'good'],
        [useSoon ? `${plural(useSoon)} to use first` : 'No use-first pressure', useSoon ? 'warn' : 'good'],
        [low ? `${plural(low)} to buy` : 'No urgent gaps', low ? 'warn' : 'good'],
        [recent ? `${plural(recent)} recently bought` : 'No recent buys', recent ? 'good' : 'warn'],
      ];
      let headline = 'The household is steady, so explore before you buy.';
      let story = `You have ${pantry} pantry ${pantry === 1 ? 'item' : 'items'} and room to browse.`;
      if (useSoon > 0) {
        headline = 'Use what you have before it slips.';
        story = `${useSoon} ${useSoon === 1 ? 'item is' : 'items are'} ready to use first, which makes tonight a good night to cook from home.`;
      } else if (low > 0) {
        headline = 'Restock the gaps without making a giant list.';
        story = `${low} ${low === 1 ? 'item is' : 'items are'} running low, so compare before you buy and keep the basket tight.`;
      } else if (recent > 0) {
        headline = 'The loop is calm, which is perfect for a playful pass.';
        story = `${recent} ${recent === 1 ? 'buy is' : 'buys are'} already logged, so the next move can be cook, compare, or just browse.`;
      }
      if (els.storyTitle) {
        els.storyTitle.textContent = headline;
      }
      if (els.storyCopy) {
        els.storyCopy.textContent = story;
      }
      if (els.storyBadges) {
        els.storyBadges.innerHTML = badges.map(([label, tone]) => `<span class="pill" data-tone="${tone}">${esc(label)}</span>`).join('');
      }
      if (els.storyBuyPill) {
        els.storyBuyPill.textContent = low ? plural(low) : 'steady';
        els.storyBuyPill.dataset.tone = low ? 'warn' : 'good';
      }
      if (els.storyUsePill) {
        els.storyUsePill.textContent = useSoon ? plural(useSoon) : 'calm';
        els.storyUsePill.dataset.tone = useSoon ? 'warn' : 'good';
      }
      if (els.storyCookPill) {
        els.storyCookPill.textContent = pantry ? plural(pantry) : 'open';
        els.storyCookPill.dataset.tone = pantry ? 'good' : 'warn';
      }
      if (els.storyExplorePill) {
        els.storyExplorePill.textContent = recent ? 'browse' : 'search';
        els.storyExplorePill.dataset.tone = 'good';
      }
      if (els.storyBuyNote) {
        els.storyBuyNote.textContent = low ? `Build the next basket from ${plural(low)}.` : 'No urgent restock pressure, so you can keep the basket slim.';
      }
      if (els.storyUseNote) {
        els.storyUseNote.textContent = useSoon ? `Use ${plural(useSoon)} first and keep the fridge honest.` : 'Nothing urgent needs to be eaten today.';
      }
      if (els.storyCookNote) {
        els.storyCookNote.textContent = pantry ? `Turn ${plural(pantry)} in the pantry into dinner or snacks.` : 'Open the recipe flow when you want a dinner idea.';
      }
      if (els.storyExploreNote) {
        els.storyExploreNote.textContent = recent ? `Recent buys are in the record; compare, search, and keep learning.` : 'Compare, search, and inspect the oddball signals.';
      }
    }

    function renderDashboard(data) {
      renderTodayStory(data);
      const metrics = [
        ['Pantry', data.pantry_count ?? 0],
        ['Use soon', data.use_soon_count ?? 0],
        ['Low items', data.low_items_count ?? 0],
        ['Recent buys', data.recent_purchases_count ?? 0],
      ];
      els.metricGrid.innerHTML = metrics.map(([label, value]) => `
        <div class="metric">
          <div class="label">${esc(label)}</div>
          <div class="value">${esc(value)}</div>
        </div>
      `).join('');
      els.useSoonCount.textContent = String((data.use_soon_count ?? 0));
      els.lowCount.textContent = String((data.low_items_count ?? 0));
      els.recentCount.textContent = String((data.recent_purchases_count ?? 0));

      const renderItem = (item) => {
        const name = item.display_name || item.canonical_name || item.title || item.value || 'Item';
        const metaParts = [];
        if (item.quantity !== undefined && item.quantity !== null) {
          metaParts.push(`${item.quantity} ${item.unit || ''}`.trim());
        }
        if (item.storage_location_name) {
          metaParts.push(item.storage_location_name);
        }
        if (item.estimated_use_by_date) {
          metaParts.push(`use by ${item.estimated_use_by_date}`);
        }
        return `
          <div class="item">
            <div class="item-row">
              <div class="item-title">${esc(name)}</div>
              <div class="pill">${esc(item.category || item.status || 'item')}</div>
            </div>
            <div class="item-meta">${esc(metaParts.filter(Boolean).join(' · ') || 'No extra details')}</div>
          </div>
        `;
      };

      const populate = (target, items, emptyLabel) => {
        if (!items || !items.length) {
          target.innerHTML = `<div class="item"><div class="item-title">${esc(emptyLabel)}</div><div class="item-meta">No entries right now.</div></div>`;
          return;
        }
        target.innerHTML = items.map(renderItem).join('');
      };

      populate(els.useSoonList, data.use_soon_items || [], 'Nothing urgent');
      populate(els.lowList, data.low_items || [], 'Nothing low');
      populate(els.recentList, data.recent_purchases || [], 'No recent buys');
      els.householdMeta.textContent = `Household ${data.household_id || 'unknown'} · snapshot ${data.timestamp || 'unknown'}`;
    }

    function renderHistory(data) {
      const items = (data && data.items) || [];
      if (!items.length) {
        els.historyList.innerHTML = `
          <div class="item">
            <div class="item-title">No commands yet</div>
            <div class="item-meta">Execute a command to populate household history.</div>
          </div>
        `;
        return;
      }
      els.historyList.innerHTML = items.map((item) => `
        <div class="item">
          <div class="item-row">
            <div class="item-title">${esc(item.action || 'command')}</div>
            <span class="pill" data-tone="${item.success ? 'good' : 'bad'}">${item.success ? 'success' : 'failed'}</span>
          </div>
          <div class="item-meta">${esc(item.original_text || '')}</div>
          <div class="tiny">${esc(item.summary || '')}</div>
        </div>
      `).join('');
    }

    function renderInventory(data) {
      const items = (data && data.items) || [];
      const total = data && typeof data.total === 'number' ? data.total : items.length;
      const hasMore = Boolean(data && data.has_more);
      if (!items.length) {
        els.inventoryList.innerHTML = `
          <div class="item">
            <div class="item-title">No inventory</div>
            <div class="item-meta">Add the first lot to seed the household pantry.</div>
          </div>
        `;
        return;
      }
      els.inventoryList.innerHTML = items.map((item) => `
        <div class="item">
          <div class="item-row">
            <div class="item-title">${esc(item.display_name || item.canonical_name || 'Item')}</div>
            <span class="pill">${esc(item.status || 'active')}</span>
          </div>
          <div class="item-meta">${esc((item.quantity ?? '1') + ' ' + (item.unit || 'unit'))} · ${esc(item.storage_location_name || item.storage_location_id || 'unplaced')}</div>
          <div class="tiny">${esc(item.category || 'uncategorized')} · ${esc(item.estimated_use_by_date || item.purchase_date || '')}</div>
          <div class="field-actions">
            <button class="btn btn-ghost" type="button" data-explain-name="${esc(item.canonical_name || '')}">Explain decision</button>
          </div>
        </div>
      `).join('') + `
        <div class="tiny">Showing ${esc(items.length)} of ${esc(total)}${hasMore ? ' (more available)' : ''}.</div>
      `;
      bindExplainButtons();
    }

    function renderShopping(data) {
      const items = (data && data.items) || [];
      const listId = data && data.list_id ? data.list_id : '';
      els.shoppingListTitle.textContent = listId ? `Active list: ${listId}` : 'Active list';
      els.shoppingGoalText.textContent = data && data.goal ? data.goal : (listId ? 'List loaded with no explicit goal.' : 'No shopping list loaded yet.');
      els.shoppingPill.textContent = data && data.is_active ? 'active' : 'idle';
      if (els.shoppingMarkPurchasedBtn) {
        els.shoppingMarkPurchasedBtn.disabled = !listId || !items.length;
      }
      if (!items.length) {
        els.shoppingList.innerHTML = `
          <div class="item">
            <div class="item-title">No shopping items</div>
            <div class="item-meta">Create a list from the composer above or from a command.</div>
          </div>
        `;
        return;
      }
      els.shoppingList.innerHTML = items.map((item) => `
        <div class="item">
          <div class="item-row">
            <label class="item-title" style="display:flex;align-items:center;gap:10px;cursor:pointer;">
              <input type="checkbox" data-shopping-item-id="${esc(item.item_id || item.list_item_id || '')}">
              <span>${esc(item.canonical_name || 'Item')}</span>
            </label>
            <span class="pill">${esc(item.priority || 'optional')}</span>
          </div>
          <div class="item-meta">${esc((item.requested_quantity ?? '1') + ' ' + (item.unit || 'unit'))} · ${esc(item.status || 'pending')}</div>
          <div class="tiny">${esc(item.reason || '')}</div>
        </div>
      `).join('');
    }

    function getSelectedShoppingItemIds() {
      return Array.from(document.querySelectorAll('[data-shopping-item-id]:checked'))
        .map((el) => el.getAttribute('data-shopping-item-id') || '')
        .filter(Boolean);
    }

    function renderSearchStatus(data, fallbackLabel) {
      if (!data) {
        return fallbackLabel || 'idle';
      }
      if (data.search_mode) {
        if (data.search_mode === 'inventory-semantic') {
          return data.semantic_active ? 'semantic' : 'text fallback';
        }
        if (data.search_mode === 'inventory-text') {
          return 'text fallback';
        }
        return data.search_mode;
      }
      return fallbackLabel || 'idle';
    }

    function renderSearchResults(target, data, emptyLabel) {
      const items = (data && data.results) || [];
      if (!items.length) {
        target.innerHTML = `
          <div class="item">
            <div class="item-title">${esc(emptyLabel)}</div>
            <div class="item-meta">No results yet.</div>
          </div>
        `;
        return;
      }
      target.innerHTML = items.map((item) => `
        <div class="item">
          <div class="item-row">
            <div class="item-title">${esc(item.title || 'Result')}</div>
            <span class="pill">${esc(item.kind || 'result')}</span>
          </div>
          <div class="item-meta">${esc(item.meta || '')}</div>
          <div class="tiny">Score: ${esc((item.score ?? 0).toFixed ? item.score.toFixed(2) : item.score)}</div>
          ${item.household_id ? `<div class="tiny">Household: ${esc(item.household_id)}</div>` : ''}
        </div>
      `).join('');
    }

    function renderVoiceIntent(data) {
      if (!data) {
        els.voiceBox.dataset.tone = 'muted';
        els.voiceBox.textContent = 'Voice intent will appear here.';
        return;
      }
      els.voiceBox.dataset.tone = data.action && data.action !== 'observe' ? 'good' : 'warn';
      els.voiceBox.innerHTML = `
        <div class="item-row">
          <strong>${esc(data.action || 'observe')}</strong>
          <span class="pill">${esc(data.language || 'en')}</span>
        </div>
        <div class="subtle" style="margin-top:8px;">${esc(data.translated_text || data.original_text || '')}</div>
        <div class="tiny" style="margin-top:10px;">Confidence: ${esc((data.confidence ?? 0).toFixed ? data.confidence.toFixed(2) : data.confidence)}</div>
      `;
    }

    function renderDecisionExplain(data) {
      if (!data) {
        els.decisionPill.textContent = 'idle';
        els.decisionBox.dataset.tone = 'muted';
        els.decisionBox.textContent = 'Click an inventory item or search result to inspect why it was classified.';
        return;
      }
      els.decisionPill.textContent = data.action || 'unknown';
      els.decisionPill.dataset.tone = data.action && data.action !== 'error' ? 'good' : 'bad';
      els.decisionBox.dataset.tone = data.action && data.action !== 'error' ? 'good' : 'bad';
      els.decisionBox.innerHTML = `
        <div class="item-row">
          <strong>${esc(data.canonical_name || 'item')}</strong>
          <span class="pill">${esc(data.confidence_label || data.freshness_label || 'explain')}</span>
        </div>
        <div class="subtle" style="margin-top:8px;">${esc(data.summary || '')}</div>
        <div class="tiny" style="margin-top:10px;">${esc(data.key_signal || '')}</div>
      `;
    }

    function renderRecurringPlan(data) {
      const items = (data && data.items) || [];
      els.recurringSummary.textContent = data && data.summary ? data.summary : 'No recurring plan loaded.';
      els.recurringPill.textContent = `${items.length || 0} items`;
      if (!items.length) {
        els.recurringList.innerHTML = `
          <div class="item">
            <div class="item-title">No recurring signals</div>
            <div class="item-meta">Nothing due in the current cadence window.</div>
          </div>
        `;
        return;
      }
      els.recurringList.innerHTML = items.map((item) => `
        <div class="item">
          <div class="item-row">
            <div class="item-title">${esc(item.display_name || item.canonical_name || 'Recurring item')}</div>
            <span class="pill">${esc(item.action || 'buy')}</span>
          </div>
          <div class="item-meta">${esc((item.priority ?? 0) + ' priority')} · ${esc(item.days_until_next ?? '—')} days</div>
          <div class="tiny">${esc((item.reasons || []).join(' · '))}</div>
        </div>
      `).join('');
    }

    function renderMealPlan(data) {
      const items = (data && data.items) || [];
      els.mealplanSummary.textContent = data && data.summary ? data.summary : 'No meal plan loaded.';
      els.mealplanPill.textContent = `${items.length || 0} days`;
      if (!items.length) {
        els.mealplanList.innerHTML = `
          <div class="item">
            <div class="item-title">No meal plan</div>
            <div class="item-meta">Load a plan to see the week.</div>
          </div>
        `;
        return;
      }
      els.mealplanList.innerHTML = items.map((item) => `
        <div class="item">
          <div class="item-row">
            <div class="item-title">${esc(item.date || 'Day')}</div>
            <span class="pill">${esc(item.confidence || 'low')}</span>
          </div>
          <div class="item-meta">${esc(item.recipe_name || 'No recipe selected')} · ${esc((item.cook_minutes ?? '—') + ' min')}</div>
          <div class="tiny">${esc(item.rationale || '')}</div>
        </div>
      `).join('');
    }

    function renderRuntimeDiagnostics(data) {
      if (!data) {
        els.runtimeDiagnosticsPill.textContent = 'idle';
        els.runtimeDiagnosticsSummary.textContent = 'No runtime diagnostics loaded.';
        els.runtimeDiagnosticsList.innerHTML = '';
        return;
      }
      const providers = Array.isArray(data.providers) ? data.providers : [];
      els.runtimeDiagnosticsPill.textContent = data.mode || 'unknown';
      els.runtimeDiagnosticsSummary.textContent = `${providers.length} provider${providers.length === 1 ? '' : 's'} · ${data.timestamp || ''}`;
      if (!providers.length) {
        els.runtimeDiagnosticsList.innerHTML = `
          <div class="item">
            <div class="item-title">No providers reported</div>
            <div class="item-meta">${esc(data.error || 'Runtime diagnostics were empty.')}</div>
          </div>
        `;
        return;
      }
      els.runtimeDiagnosticsList.innerHTML = providers.map((provider) => `
        <div class="item">
          <div class="item-row">
            <div class="item-title">${esc(provider.name || 'provider')}</div>
            <span class="pill" data-tone="${provider.available ? 'good' : 'warn'}">${esc(provider.backend || 'backend')}</span>
          </div>
          <div class="item-meta">${esc(provider.model_id || 'no model')} · ${provider.loaded ? 'loaded' : 'idle'} · ${provider.available ? 'available' : 'unavailable'}</div>
          <div class="tiny">Latency: ${esc(provider.last_latency_ms ?? '—')} ms</div>
        </div>
      `).join('');
    }

    function renderRetentionSummary(data) {
      const summary = data && data.summary ? data.summary : null;
      if (!summary) {
        els.privacyPill.textContent = 'idle';
        els.privacySummary.textContent = 'No retention summary loaded.';
        els.privacyList.innerHTML = '';
        renderPrivacyProfileHint(els.privacyProfile && els.privacyProfile.value ? els.privacyProfile.value : 'balanced');
        return;
      }
      els.privacyPill.textContent = 'loaded';
      els.privacySummary.textContent = 'Current privacy retention policy for this household.';
      renderPrivacyProfileHint(els.privacyProfile && els.privacyProfile.value ? els.privacyProfile.value : 'balanced');
      els.privacyList.innerHTML = [
        ['Trace TTL', `${summary.trace_ttl_days} days`],
        ['Trace max rows', summary.trace_max_rows],
        ['Community pool', `${summary.community_pool_retention_days} days`],
        ['Voice memos', `${summary.voice_memo_retention_days} days`],
        ['SMS registry', `${summary.sms_registry_retention_days} days`],
        ['Backups', `${summary.backup_retention_days} days`],
        ['Locale persistence', summary.locale_persistence ? 'on' : 'off'],
        ['Community opt-in', summary.community_optin ? 'on' : 'off'],
      ].map(([label, value]) => `
        <div class="item">
          <div class="item-row">
            <div class="item-title">${esc(label)}</div>
            <span class="pill">${esc(value)}</span>
          </div>
        </div>
      `).join('');
    }

    function privacyProfileConfig(profile) {
      const profiles = {
        balanced: {
          label: 'Balanced defaults',
          description: 'Balanced defaults keeps the current household defaults: 30-day traces, 90-day community pool, and local locale persistence.',
          settings: [
            ['retention.trace_ttl_days', '30'],
            ['retention.community_pool_retention_days', '90'],
            ['retention.voice_memo_retention_days', '7'],
            ['retention.sms_registry_retention_days', '0'],
            ['retention.backup_retention_days', '0'],
            ['retention.locale_persistence', '1'],
            ['retention.community_optin', '0'],
          ],
        },
        strict: {
          label: 'Strict privacy',
          description: 'Strict privacy shortens traces and voice memos, keeps community sharing off, and avoids persisting locale preferences.',
          settings: [
            ['retention.trace_ttl_days', '7'],
            ['retention.community_pool_retention_days', '30'],
            ['retention.voice_memo_retention_days', '3'],
            ['retention.sms_registry_retention_days', '0'],
            ['retention.backup_retention_days', '0'],
            ['retention.locale_persistence', '0'],
            ['retention.community_optin', '0'],
          ],
        },
        shared: {
          label: 'Household sharing',
          description: 'Household sharing keeps more memory for the home while opting into the community pool and preserving locale defaults.',
          settings: [
            ['retention.trace_ttl_days', '30'],
            ['retention.community_pool_retention_days', '90'],
            ['retention.voice_memo_retention_days', '7'],
            ['retention.sms_registry_retention_days', '0'],
            ['retention.backup_retention_days', '0'],
            ['retention.locale_persistence', '1'],
            ['retention.community_optin', '1'],
          ],
        },
      };
      return profiles[profile] || profiles.balanced;
    }

    function renderPrivacyProfileHint(profile) {
      const config = privacyProfileConfig(profile);
      if (els.privacyProfileSummary) {
        els.privacyProfileSummary.textContent = config.description;
      }
    }

    function parseBoundedInt(value, fallback, min, max) {
      const parsed = Number.parseInt(String(value ?? '').trim(), 10);
      if (!Number.isFinite(parsed)) {
        return fallback;
      }
      return Math.min(max, Math.max(min, parsed));
    }

    function renderCorrections(data) {
      const items = (data && data.items) || [];
      els.correctionsPill.textContent = `${items.length || 0} items`;
      els.correctionsSummary.textContent = data && data.summary ? data.summary : 'No corrections loaded.';
      if (!items.length) {
        els.correctionsList.innerHTML = `
          <div class="item">
            <div class="item-title">No corrections recorded</div>
            <div class="item-meta">Use this panel to tighten the feedback loop on decisions.</div>
          </div>
        `;
        return;
      }
      els.correctionsList.innerHTML = items.map((item) => `
        <div class="item">
          <div class="item-row">
            <div class="item-title">${esc(item.canonical_name || 'item')}</div>
            <span class="pill">${esc(item.accepted ? 'accepted' : 'pending')}</span>
          </div>
          <div class="item-meta">${esc(item.was_action || '—')} → ${esc(item.should_be_action || '—')} · ${esc(item.source || 'source')}</div>
          <div class="tiny">${esc(item.timestamp || '')}</div>
        </div>
      `).join('');
    }

    function renderTraces(data) {
      const items = (data && data.items) || [];
      els.tracePill.textContent = `${items.length || 0} items`;
      els.traceSummary.textContent = data && data.summary ? data.summary : 'No traces loaded.';
      if (!items.length) {
        els.traceList.innerHTML = `
          <div class="item">
            <div class="item-title">No traces recorded</div>
            <div class="item-meta">Command execution and feedback should populate this list.</div>
          </div>
        `;
        els.traceDetail.textContent = 'Pick a trace to inspect the payload.';
        els.traceExport.textContent = 'Redacted JSONL export will appear here.';
        els.traceExportPill.textContent = 'idle';
        return;
      }
      els.traceList.innerHTML = items.map((item) => `
        <div class="item">
          <div class="item-row">
            <div class="item-title">${esc(item.user_goal || item.input_type || 'trace')}</div>
            <span class="pill">${esc(item.action || item.input_type || 'trace')}</span>
          </div>
          <div class="item-meta">${esc(item.final_response || '')}</div>
          <div class="tiny">${esc(item.timestamp || '')} · ${esc(item.human_confirmation || 'unconfirmed')}</div>
          <div class="field-actions">
            <button class="btn btn-primary" type="button" data-trace-id="${esc(item.trace_id || '')}" data-trace-action="detail">View detail</button>
            <button class="btn btn-ghost" type="button" data-trace-id="${esc(item.trace_id || '')}" data-trace-action="export">Export</button>
          </div>
        </div>
      `).join('');
      bindTraceButtons();
      if (items[0] && items[0].trace_id) {
        refreshTraceDetail(items[0].trace_id);
      }
    }

    function renderTraceDetail(data) {
      if (!data || !data.trace) {
        els.traceDetail.dataset.tone = 'muted';
        els.traceDetail.textContent = 'Pick a trace to inspect the payload.';
        return;
      }
      const trace = data.trace;
      els.traceDetail.dataset.tone = 'good';
      els.traceDetail.innerHTML = `
        <div class="item-row">
          <strong>${esc(trace.user_goal || trace.input_type || 'trace')}</strong>
          <span class="pill">${esc(trace.action || trace.input_type || 'trace')}</span>
        </div>
        <div class="subtle" style="margin-top:8px;">${esc(trace.redacted_user_request || trace.final_response || '')}</div>
        <div class="tiny" style="margin-top:10px;">Decision: ${esc(JSON.stringify(trace.decision || {}))}</div>
        <div class="tiny">Tool calls: ${esc((trace.tool_call_count ?? (trace.proposed_tool_calls || []).length) || 0)}</div>
      `;
    }

    function renderTraceExport(data) {
      if (!data) {
        els.traceExportPill.textContent = 'idle';
        els.traceExport.dataset.tone = 'muted';
        els.traceExport.textContent = 'Redacted JSONL export will appear here.';
        return;
      }
      els.traceExportPill.textContent = data.redacted ? 'redacted' : 'raw';
      els.traceExport.dataset.tone = 'good';
      els.traceExport.innerHTML = `
        <div class="subtle" style="margin-bottom:8px;">Trace ${esc(data.trace_id || '')}</div>
        <pre style="white-space:pre-wrap;word-break:break-word;margin:0;">${esc(data.jsonl || '')}</pre>
      `;
    }

    function bindExplainButtons() {
      document.querySelectorAll('[data-explain-name]').forEach((button) => {
        if (button.dataset.bound === 'true') {
          return;
        }
        button.dataset.bound = 'true';
        button.addEventListener('click', () => {
          const name = button.getAttribute('data-explain-name') || '';
          if (name) {
            refreshDecisionExplain(name);
          }
        });
      });
    }

    function bindTraceButtons() {
      document.querySelectorAll('[data-trace-id]').forEach((button) => {
        if (button.dataset.bound === 'true') {
          return;
        }
        button.dataset.bound = 'true';
        button.addEventListener('click', () => {
          const traceId = button.getAttribute('data-trace-id') || '';
          const action = button.getAttribute('data-trace-action') || 'detail';
          if (traceId) {
            if (action === 'export') {
              refreshTraceExport(traceId);
            } else {
              refreshTraceDetail(traceId);
            }
          }
        });
      });
    }

    function renderHouseholds(data) {
      const items = (data && data.items) || [];
      const active = data && data.active_household_id ? data.active_household_id : '';
      els.householdSelect.innerHTML = '';
      if (!items.length) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'No households returned';
        els.householdSelect.appendChild(opt);
        return;
      }
      items.forEach((item) => {
        const opt = document.createElement('option');
        opt.value = item.household_id || '';
        opt.textContent = `${item.name || item.household_id || 'Household'}${item.is_active ? ' (active)' : ''}`;
        if (item.household_id === active) {
          opt.selected = true;
        }
        els.householdSelect.appendChild(opt);
      });
    }

    function setConnectedIdentity(householdId, householdName) {
      const shortId = householdId ? householdId.slice(0, 12) : '—';
      setPill(els.householdPill, householdName || shortId, 'good');
      els.householdDetail.textContent = householdId ? `Token scoped to ${householdId}.` : 'No household connected.';
    }

    function setDisconnectedIdentity() {
      setPill(els.householdPill, 'Not connected', 'warn');
      els.householdDetail.textContent = 'Sign in or register a device to unlock household-scoped data.';
      els.householdSelect.innerHTML = '<option value="">Connect first</option>';
      els.householdMeta.textContent = 'Waiting for a household-scoped token.';
      renderShopping({
        list_id: '',
        name: 'Shopping List',
        created_at: '',
        updated_at: '',
        goal: '',
        is_active: true,
        items: [],
      });
      renderDashboard({
        household_id: '',
        timestamp: '',
        pantry_count: 0,
        use_soon_count: 0,
        low_items_count: 0,
        recent_purchases_count: 0,
        use_soon_items: [],
        low_items: [],
        recent_purchases: [],
      });
      renderHistory({ items: [] });
      renderRetentionSummary(null);
      renderCorrections(null);
      renderTraces(null);
      if (els.searchGlobalList) {
        els.searchGlobalList.innerHTML = '';
      }
      if (els.searchInventoryList) {
        els.searchInventoryList.innerHTML = '';
      }
      if (els.searchGlobalPill) {
        setPill(els.searchGlobalPill, 'idle', 'warn');
      }
      if (els.searchInventoryPill) {
        setPill(els.searchInventoryPill, 'idle', 'warn');
      }
      if (els.privacyValue) {
        els.privacyValue.value = '';
      }
      if (els.privacyConfirm) {
        els.privacyConfirm.value = '';
      }
      if (els.privacyProfile) {
        els.privacyProfile.value = 'balanced';
      }
      if (els.recurringWindow) {
        els.recurringWindow.value = '7';
      }
      if (els.mealplanDays) {
        els.mealplanDays.value = '7';
      }
      renderTodayStory(null);
    }

    async function refreshPublicState() {
      try {
        setPill(els.runtimePill, 'Loading…', 'warn');
        const [whoami, health] = await Promise.all([
          requestJson('/meta/whoami'),
          requestHealth(),
        ]);
        setPill(els.runtimePill, whoami.runtime_mode || 'local_mock', 'good');
        els.runtimeDetail.textContent = `${whoami.app_name || 'shopstack'} · ${whoami.household_name || whoami.household_id || 'default household'}`;
        const healthPayload = health.payload || {};
        setPill(els.healthPill, healthPayload.status || 'unknown', healthPayload.status === 'ok' ? 'good' : 'warn');
        const tables = healthPayload.database && healthPayload.database.table_count !== undefined
          ? `${healthPayload.database.table_count} tables`
          : 'database status unknown';
        els.healthDetail.textContent = `${tables} · ${healthPayload.timestamp || ''}`;
        await refreshRuntimeDiagnostics();
        log(`Loaded public metadata: ${whoami.runtime_mode || 'local_mock'}.`, 'good');
      } catch (err) {
        setPill(els.runtimePill, 'Unavailable', 'bad');
        setPill(els.healthPill, 'Degraded', 'bad');
        els.runtimeDetail.textContent = err.message || 'Failed to load public metadata.';
        els.healthDetail.textContent = 'The backend is reachable, but the public metadata failed.';
        renderRuntimeDiagnostics(null);
        log(`Public metadata failed: ${err.message}`, 'bad');
      }
    }

    async function refreshPrivateState() {
      const token = currentToken();
      if (!token) {
        setDisconnectedIdentity();
        return;
      }
      try {
        const [dashboard, recent, households] = await Promise.all([
          requestJson('/dashboard/today', {}, true),
          requestJson('/command/recent?limit=8', {}, true),
          requestJson('/household', {}, true),
        ]);
        renderDashboard(dashboard);
        renderHistory(recent);
        renderHouseholds(households);
        setConnectedIdentity(dashboard.household_id || households.active_household_id || '', (households.items || []).find((h) => h.household_id === (dashboard.household_id || households.active_household_id || ''))?.name || '');
        setPill(els.apiStatus, 'synced', 'good');
        log(`Loaded household snapshot for ${dashboard.household_id || 'unknown'}.`, 'good');
      } catch (err) {
        if (err.status === 401) {
          clearSession();
          setDisconnectedIdentity();
          setPill(els.apiStatus, 'unauthorized', 'bad');
          log('Stored token was rejected; session cleared.', 'bad');
          return;
        }
        setPill(els.apiStatus, 'error', 'bad');
        log(`Private state failed: ${err.message}`, 'bad');
      }
    }

    async function refreshInventory() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before loading inventory.', 'warn');
        return;
      }
      try {
        const data = await requestJson('/inventory/lots?limit=12', {}, true);
        renderInventory(data);
        log(`Loaded ${data.items ? data.items.length : 0} inventory lots.`, 'good');
      } catch (err) {
        setPill(els.decisionPill, 'error', 'bad');
        log(`Inventory load failed: ${err.message}`, 'bad');
      }
    }

    async function refreshShopping() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before loading shopping.', 'warn');
        return;
      }
      try {
        const data = await requestJson('/shopping/active', {}, true);
        renderShopping(data);
        log('Loaded active shopping list.', 'good');
      } catch (err) {
        log(`Shopping load failed: ${err.message}`, 'bad');
      }
    }

    function _searchQuery() {
      return encodeURIComponent((els.searchQuery.value || '').trim());
    }

    async function refreshGlobalSearch() {
      const q = (els.searchQuery.value || '').trim();
      if (!q) {
        log('Enter a search query first.', 'warn');
        return;
      }
      try {
        const data = await requestJson(`/search/global?q=${encodeURIComponent(q)}`, {}, true);
        renderSearchResults(els.searchGlobalList, data, 'No global results');
        setPill(els.searchGlobalPill, renderSearchStatus(data, 'global'), 'good');
        log(`Global search completed for "${q}".`, 'good');
      } catch (err) {
        setPill(els.searchGlobalPill, 'error', 'bad');
        log(`Global search failed: ${err.message}`, 'bad');
      }
    }

    async function refreshInventorySearch() {
      const q = (els.searchQuery.value || '').trim();
      if (!q) {
        log('Enter a search query first.', 'warn');
        return;
      }
      try {
        const data = await requestJson(`/search/inventory?q=${encodeURIComponent(q)}`, {}, true);
        renderSearchResults(els.searchInventoryList, data, 'No inventory results');
        const inventoryLabel = data && data.search_mode ? renderSearchStatus(data, 'inventory') : 'inventory';
        setPill(els.searchInventoryPill, inventoryLabel, 'good');
        log(`Inventory search completed for "${q}".`, 'good');
      } catch (err) {
        setPill(els.searchInventoryPill, 'error', 'bad');
        log(`Inventory search failed: ${err.message}`, 'bad');
      }
    }

    async function parseVoiceIntent() {
      const text = (els.voiceText.value || '').trim();
      if (!text) {
        log('Enter a transcript first.', 'warn');
        return;
      }
      try {
        const data = await requestJson('/search/voice-intent', {
          method: 'POST',
          body: { text, language: 'en' },
        });
        renderVoiceIntent(data);
        log(`Parsed voice intent: ${data.action || 'observe'}.`, 'good');
      } catch (err) {
        log(`Voice intent parsing failed: ${err.message}`, 'bad');
      }
    }

    async function refreshRecurringPlan() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before loading intelligence.', 'warn');
        return;
      }
      try {
        const windowDays = parseBoundedInt(els.recurringWindow.value, 7, 0, 30);
        const data = await requestJson(`/intelligence/recurring?window=${windowDays}`, {}, true);
        renderRecurringPlan(data);
        log(`Loaded recurring plan for ${windowDays} days.`, 'good');
      } catch (err) {
        setPill(els.recurringPill, 'error', 'bad');
        log(`Recurring plan failed: ${err.message}`, 'bad');
      }
    }

    async function refreshMealPlan() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before loading intelligence.', 'warn');
        return;
      }
      try {
        const days = parseBoundedInt(els.mealplanDays.value, 7, 1, 28);
        const data = await requestJson(`/intelligence/mealplan?days=${days}`, {}, true);
        renderMealPlan(data);
        log(`Loaded meal plan for ${days} days.`, 'good');
      } catch (err) {
        setPill(els.mealplanPill, 'error', 'bad');
        log(`Meal plan failed: ${err.message}`, 'bad');
      }
    }

    async function refreshRuntimeDiagnostics() {
      try {
        const data = await requestJson('/meta/runtime');
        renderRuntimeDiagnostics(data);
        log('Loaded runtime diagnostics.', 'good');
      } catch (err) {
        renderRuntimeDiagnostics({
          mode: 'error',
          providers: [],
          error: err.message,
        });
        log(`Runtime diagnostics failed: ${err.message}`, 'bad');
      }
    }

    async function refreshRetentionSummary() {
      const token = currentToken();
      if (!token) {
        renderRetentionSummary(null);
        log('Connect a household before loading privacy settings.', 'warn');
        return;
      }
      try {
        const data = await requestJson('/account/privacy/retention-summary', {}, true);
        renderRetentionSummary(data);
        log('Loaded privacy retention summary.', 'good');
      } catch (err) {
        renderRetentionSummary(null);
        log(`Privacy summary failed: ${err.message}`, 'bad');
      }
    }

    async function updateRetentionSetting() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before updating privacy settings.', 'warn');
        return;
      }
      const key = (els.privacyKey.value || '').trim();
      const value = (els.privacyValue.value || '').trim();
      if (!key || !value) {
        log('Choose a retention setting and enter a value first.', 'warn');
        return;
      }
      try {
        const data = await requestJson('/account/privacy/update-retention', {
          method: 'POST',
          body: { key, value },
        }, true);
        log(data.success ? 'Updated privacy retention.' : 'Privacy retention update rejected.', data.success ? 'good' : 'warn');
        await refreshRetentionSummary();
      } catch (err) {
        log(`Privacy update failed: ${err.message}`, 'bad');
      }
    }

    async function applyPrivacyProfile() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before applying privacy profiles.', 'warn');
        return;
      }
      const config = privacyProfileConfig((els.privacyProfile && els.privacyProfile.value) || 'balanced');
      try {
        for (const [key, value] of config.settings) {
          const result = await requestJson('/account/privacy/update-retention', {
            method: 'POST',
            body: { key, value },
          }, true);
          if (!result.success) {
            log(`Privacy profile stopped on ${key}.`, 'warn');
            break;
          }
        }
        log(`Applied privacy profile: ${config.label}.`, 'good');
        await refreshRetentionSummary();
      } catch (err) {
        log(`Privacy profile apply failed: ${err.message}`, 'bad');
      }
    }

    async function purgePrivacyData() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before purging data.', 'warn');
        return;
      }
      const confirmation = (els.privacyConfirm.value || '').trim().toUpperCase();
      if (confirmation !== 'PURGE') {
        log('Type PURGE to confirm the privacy wipe.', 'warn');
        return;
      }
      try {
        const data = await requestJson('/account/privacy/purge', {
          method: 'POST',
          body: {},
        }, true);
        log(data.success ? 'Purged household-derived data.' : 'Privacy purge completed with warnings.', data.success ? 'good' : 'warn');
        els.privacyConfirm.value = '';
        await refreshAllHouseholdViews();
      } catch (err) {
        log(`Privacy purge failed: ${err.message}`, 'bad');
      }
    }

    async function refreshCorrections() {
      const token = currentToken();
      if (!token) {
        renderCorrections(null);
        log('Connect a household before loading corrections.', 'warn');
        return;
      }
      try {
        const data = await requestJson('/corrections?limit=8', {}, true);
        renderCorrections(data);
        log('Loaded recent corrections.', 'good');
      } catch (err) {
        renderCorrections(null);
        log(`Corrections load failed: ${err.message}`, 'bad');
      }
    }

    async function refreshTraces() {
      const token = currentToken();
      if (!token) {
        renderTraces(null);
        log('Connect a household before loading traces.', 'warn');
        return;
      }
      try {
        const search = (els.traceSearch.value || '').trim();
        const inputType = (els.traceType.value || '').trim();
        const q = new URLSearchParams();
        q.set('limit', '8');
        if (search) {
          q.set('search', search);
        }
        if (inputType) {
          q.set('input_type_filter', inputType);
        }
        const data = await requestJson(`/traces?${q.toString()}`, {}, true);
        renderTraces(data);
        log('Loaded recent traces.', 'good');
      } catch (err) {
        renderTraces(null);
        log(`Trace load failed: ${err.message}`, 'bad');
      }
    }

    async function refreshTraceDetail(traceId) {
      const token = currentToken();
      if (!token) {
        log('Connect a household before loading trace details.', 'warn');
        return;
      }
      try {
        const data = await requestJson(`/traces/${encodeURIComponent(traceId)}`, {}, true);
        renderTraceDetail(data);
        log(`Loaded trace ${traceId}.`, 'good');
      } catch (err) {
        renderTraceDetail(null);
        log(`Trace detail failed: ${err.message}`, 'bad');
      }
    }

    async function refreshTraceExport(traceId) {
      const token = currentToken();
      if (!token) {
        log('Connect a household before exporting traces.', 'warn');
        return;
      }
      try {
        const data = await requestJson(`/traces/${encodeURIComponent(traceId)}/export?redact=true`, {}, true);
        renderTraceExport(data);
        log(`Exported trace ${traceId}.`, 'good');
      } catch (err) {
        renderTraceExport(null);
        log(`Trace export failed: ${err.message}`, 'bad');
      }
    }

    async function createCorrection() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before recording corrections.', 'warn');
        return;
      }
      const canonical_name = (els.correctionCanonical.value || '').trim();
      const was_action = (els.correctionWasAction.value || '').trim();
      const should_be_action = (els.correctionShouldAction.value || '').trim();
      const reason = (els.correctionReason.value || '').trim();
      if (!canonical_name || !was_action || !should_be_action) {
        log('Fill canonical name, was action, and should-be action first.', 'warn');
        return;
      }
      try {
        const data = await requestJson('/corrections', {
          method: 'POST',
          body: {
            canonical_name,
            was_action,
            should_be_action,
            reason,
          },
        }, true);
        log(`Recorded correction for ${data.canonical_name}.`, 'good');
        await refreshCorrections();
        await refreshRetentionSummary();
      } catch (err) {
        log(`Correction create failed: ${err.message}`, 'bad');
      }
    }

    async function undoLastMutation() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before using undo.', 'warn');
        return;
      }
      try {
        const data = await requestJson('/account/undo', {
          method: 'POST',
          body: {},
        }, true);
        log(data.message || 'Undo completed.', data.success ? 'good' : 'warn');
        await refreshAllHouseholdViews();
      } catch (err) {
        log(`Undo failed: ${err.message}`, 'bad');
      }
    }

    async function refreshDecisionExplain(name) {
      const token = currentToken();
      if (!token) {
        log('Connect a household before requesting explanations.', 'warn');
        return;
      }
      try {
        const data = await requestJson(`/intelligence/decision/${encodeURIComponent(name)}/explain`, {}, true);
        renderDecisionExplain(data);
        log(`Explained decision for ${name}.`, 'good');
      } catch (err) {
        renderDecisionExplain({
          canonical_name: name,
          action: 'error',
          summary: err.message,
          key_signal: '',
          confidence_label: 'error',
        });
        log(`Decision explanation failed: ${err.message}`, 'bad');
      }
    }

    async function addInventoryLot() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before adding inventory.', 'warn');
        return;
      }
      const canonical_name = (els.inventoryCanonical.value || '').trim();
      if (!canonical_name) {
        log('Enter a canonical inventory name first.', 'warn');
        return;
      }
      const quantity = Number.parseFloat((els.inventoryQty.value || '1').trim() || '1');
      try {
        const data = await requestJson('/inventory/lots', {
          method: 'POST',
          body: {
            canonical_name,
            display_name: (els.inventoryDisplay.value || '').trim(),
            quantity: Number.isFinite(quantity) && quantity > 0 ? quantity : 1,
            unit: (els.inventoryUnit.value || 'unit').trim() || 'unit',
            storage_location_id: (els.inventoryLocation.value || '').trim(),
            category: (els.inventoryCategory.value || '').trim(),
          },
        }, true);
        log(`Added inventory lot ${data.display_name || data.canonical_name}.`, 'good');
        await refreshInventory();
        await refreshAllHouseholdViews();
      } catch (err) {
        log(`Inventory add failed: ${err.message}`, 'bad');
      }
    }

    function parseShoppingItems() {
      return (els.shoppingItems.value || '')
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((name) => ({
          canonical_name: name,
          priority: 'optional',
          reason: '',
        }));
    }

    async function createShoppingList() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before creating shopping lists.', 'warn');
        return;
      }
      const items = parseShoppingItems();
      try {
        const data = await requestJson('/shopping/lists', {
          method: 'POST',
          body: {
            goal: (els.shoppingGoal.value || '').trim(),
            items,
          },
        }, true);
        renderShopping(data);
        log(`Created shopping list ${data.list_id || ''}.`, 'good');
        await refreshAllHouseholdViews();
      } catch (err) {
        log(`Shopping create failed: ${err.message}`, 'bad');
      }
    }

    async function completeActiveShoppingList() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before completing shopping lists.', 'warn');
        return;
      }
      try {
        const active = await requestJson('/shopping/active', {}, true);
        if (!active.list_id) {
          log('No active shopping list to complete.', 'warn');
          return;
        }
        const data = await requestJson(`/shopping/lists/${encodeURIComponent(active.list_id)}/complete`, {
          method: 'POST',
          body: {},
        }, true);
        log(data.message || 'Completed active shopping list.', 'good');
        await refreshShopping();
        await refreshInventory();
        await refreshAllHouseholdViews();
      } catch (err) {
        log(`Shopping completion failed: ${err.message}`, 'bad');
      }
    }

    async function markSelectedShoppingItems() {
      const token = currentToken();
      if (!token) {
        log('Connect a household before marking shopping items purchased.', 'warn');
        return;
      }
      const itemIds = getSelectedShoppingItemIds();
      if (!itemIds.length) {
        log('Select one or more shopping items first.', 'warn');
        return;
      }
      try {
        const active = await requestJson('/shopping/active', {}, true);
        if (!active.list_id) {
          log('No active shopping list to update.', 'warn');
          return;
        }
        const data = await requestJson(`/shopping/lists/${encodeURIComponent(active.list_id)}/mark-purchased`, {
          method: 'POST',
          body: {
            item_ids: itemIds,
          },
        }, true);
        log(data.message || `Marked ${itemIds.length} shopping items purchased.`, data.success ? 'good' : 'warn');
        await refreshShopping();
        await refreshInventory();
        await refreshAllHouseholdViews();
      } catch (err) {
        log(`Mark purchased failed: ${err.message}`, 'bad');
      }
    }

    async function refreshAllHouseholdViews() {
      await Promise.allSettled([
        refreshPrivateState(),
        refreshInventory(),
        refreshShopping(),
        refreshRecurringPlan(),
        refreshMealPlan(),
        refreshRetentionSummary(),
        refreshCorrections(),
        refreshTraces(),
      ]);
    }

    let previewTimer = null;
    async function refreshPreview() {
      const text = els.commandInput.value.trim();
      if (!text) {
        renderPreview(null);
        return;
      }
      try {
        const data = await requestJson('/command/preview', {
          method: 'POST',
          body: { text },
        });
        renderPreview(data);
        log(`Previewed command: ${data.intent && data.intent.action ? data.intent.action : 'unknown'}.`, 'good');
      } catch (err) {
        renderPreview({
          route_kind: 'error',
          would_mutate: false,
          summary: err.message,
          intent: { action: 'error', canonical_name: '' },
        });
        log(`Preview failed: ${err.message}`, 'bad');
      }
    }

    async function executeCommand() {
      const text = els.commandInput.value.trim();
      if (!text) {
        renderPreview(null);
        return;
      }
      try {
        const result = await requestJson('/command/execute', {
          method: 'POST',
          body: { text },
        }, true);
        renderPreview({
          route_kind: 'mutate',
          would_mutate: true,
          summary: result.result && result.result.message ? result.result.message : 'Command executed.',
          intent: result.intent || { action: '', canonical_name: '' },
        });
        log(`Executed ${result.intent && result.intent.action ? result.intent.action : 'command'}.`, 'good');
        await refreshAllHouseholdViews();
      } catch (err) {
        if (err.status === 401) {
          clearSession();
          setDisconnectedIdentity();
        }
        log(`Execution failed: ${err.message}`, 'bad');
      }
    }

    async function registerDevice() {
      try {
        const payload = {
          device_id: els.deviceId.value.trim(),
          device_secret: els.deviceSecret.value.trim(),
          household_name: els.householdName.value.trim() || 'Default Household',
          household_id: els.householdId.value.trim() || null,
        };
        const result = await requestJson('/auth/register', {
          method: 'POST',
          body: payload,
        });
        saveSession({
          token: result.token,
          household_id: result.household_id,
          household_name: result.household_name,
          device_id: payload.device_id,
          device_secret: payload.device_secret,
        });
        els.tokenInput.value = result.token;
        setConnectedIdentity(result.household_id, result.household_name);
        log(`Registered device for ${result.household_name || result.household_id}.`, 'good');
        await refreshAllHouseholdViews();
      } catch (err) {
        log(`Register failed: ${err.message}`, 'bad');
      }
    }

    async function loginDevice() {
      try {
        const payload = {
          device_id: els.deviceId.value.trim(),
          device_secret: els.deviceSecret.value.trim(),
          requested_household_id: els.householdId.value.trim() || null,
        };
        const result = await requestJson('/auth/login', {
          method: 'POST',
          body: payload,
        });
        saveSession({
          token: result.token,
          household_id: result.household_id,
          household_name: result.household_name,
          device_id: payload.device_id,
          device_secret: payload.device_secret,
        });
        els.tokenInput.value = result.token;
        setConnectedIdentity(result.household_id, result.household_name);
        log(`Logged in to ${result.household_name || result.household_id}.`, 'good');
        await refreshAllHouseholdViews();
      } catch (err) {
        log(`Login failed: ${err.message}`, 'bad');
      }
    }

    async function useManualToken() {
      const token = els.tokenInput.value.trim();
      if (!token) {
        log('Paste a token first.', 'warn');
        return;
      }
      saveSession({ token });
      log('Loaded bearer token from the override field.', 'good');
      await refreshAllHouseholdViews();
    }

    function forgetToken() {
      clearSession();
      els.tokenInput.value = '';
      setDisconnectedIdentity();
      setPill(els.apiStatus, 'idle', 'warn');
      log('Session cleared from localStorage.', 'warn');
    }

    async function switchHousehold() {
      const householdId = els.householdSelect.value.trim();
      if (!householdId) {
        log('Choose a household first.', 'warn');
        return;
      }
      try {
        const result = await requestJson(`/household/${encodeURIComponent(householdId)}/switch`, {
          method: 'POST',
        }, true);
        saveSession({ token: result.token, household_id: result.household_id, household_name: result.household_name });
        els.tokenInput.value = result.token;
        setConnectedIdentity(result.household_id, result.household_name);
        log(`Switched to ${result.household_name || result.household_id}.`, 'good');
        await refreshAllHouseholdViews();
      } catch (err) {
        log(`Switch failed: ${err.message}`, 'bad');
      }
    }

    function hydrateSessionFromUrl() {
      const url = new URL(window.location.href);
      const token = url.searchParams.get('token');
      if (token) {
        saveSession({ token });
        els.tokenInput.value = token;
        url.searchParams.delete('token');
        window.history.replaceState({}, document.title, url.pathname + url.search + url.hash);
      }
    }

    function seedDefaults() {
      const session = readSession();
      els.deviceId.value = session.device_id || 'shopstack-web';
      els.deviceSecret.value = session.device_secret || '';
      els.householdName.value = session.household_name || 'Default Household';
      els.householdId.value = session.household_id || '';
      els.tokenInput.value = session.token || '';
      renderPrivacyProfileHint(els.privacyProfile && els.privacyProfile.value ? els.privacyProfile.value : 'balanced');
      if (!session.token) {
        setDisconnectedIdentity();
      }
    }

    els.previewBtn.addEventListener('click', refreshPreview);
    els.executeBtn.addEventListener('click', executeCommand);
    els.clearBtn.addEventListener('click', () => {
      els.commandInput.value = '';
      renderPreview(null);
    });
    els.commandInput.addEventListener('input', () => {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(refreshPreview, 220);
    });
    els.registerBtn.addEventListener('click', registerDevice);
    els.loginBtn.addEventListener('click', loginDevice);
    els.useTokenBtn.addEventListener('click', useManualToken);
    els.forgetTokenBtn.addEventListener('click', forgetToken);
    els.switchBtn.addEventListener('click', switchHousehold);
    els.refreshBtn.addEventListener('click', async () => {
      await refreshPublicState();
      await refreshAllHouseholdViews();
    });
    els.inventoryAddBtn.addEventListener('click', addInventoryLot);
    els.inventoryRefreshBtn.addEventListener('click', refreshInventory);
    els.shoppingCreateBtn.addEventListener('click', createShoppingList);
    els.shoppingCompleteBtn.addEventListener('click', completeActiveShoppingList);
    els.shoppingMarkPurchasedBtn.addEventListener('click', markSelectedShoppingItems);
    els.shoppingRefreshBtn.addEventListener('click', refreshShopping);
    els.searchGlobalBtn.addEventListener('click', refreshGlobalSearch);
    els.searchInventoryBtn.addEventListener('click', refreshInventorySearch);
    els.voiceIntentBtn.addEventListener('click', parseVoiceIntent);
    els.recurringBtn.addEventListener('click', refreshRecurringPlan);
    els.mealplanBtn.addEventListener('click', refreshMealPlan);
    els.intelRefreshBtn.addEventListener('click', refreshAllHouseholdViews);
    els.runtimeRefreshBtn.addEventListener('click', refreshRuntimeDiagnostics);
    els.privacyUpdateBtn.addEventListener('click', updateRetentionSetting);
    els.privacyApplyProfileBtn.addEventListener('click', applyPrivacyProfile);
    els.privacyPurgeBtn.addEventListener('click', purgePrivacyData);
    els.privacyRefreshBtn.addEventListener('click', refreshRetentionSummary);
    els.undoBtn.addEventListener('click', undoLastMutation);
    if (els.privacyProfile) {
      els.privacyProfile.addEventListener('change', () => {
        renderPrivacyProfileHint(els.privacyProfile.value || 'balanced');
      });
    }
    els.correctionCreateBtn.addEventListener('click', createCorrection);
    els.correctionsRefreshBtn.addEventListener('click', refreshCorrections);
    els.traceRefreshBtn.addEventListener('click', refreshTraces);

    document.querySelectorAll('[data-quick-command]').forEach((button) => {
      button.addEventListener('click', () => {
        els.commandInput.value = button.getAttribute('data-quick-command') || '';
        refreshPreview();
      });
    });

    hydrateSessionFromUrl();
    seedDefaults();
    refreshPublicState().then(() => {
      refreshAllHouseholdViews();
    });
    renderPreview(null);

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch((err) => {
        log(`Service worker registration failed: ${err.message}`, 'warn');
      });
    }

    window.ShopStackShell = {
      refreshPublicState,
      refreshPrivateState,
      refreshAllHouseholdViews,
      refreshInventory,
      refreshShopping,
      refreshGlobalSearch,
      refreshInventorySearch,
      parseVoiceIntent,
      refreshRecurringPlan,
      refreshMealPlan,
      refreshRuntimeDiagnostics,
      refreshRetentionSummary,
      refreshCorrections,
      refreshTraces,
      refreshTraceDetail,
      refreshTraceExport,
      createCorrection,
      undoLastMutation,
      refreshDecisionExplain,
      addInventoryLot,
      createShoppingList,
      completeActiveShoppingList,
      refreshPreview,
      executeCommand,
    };
  })();
  </script>
</body>
</html>
"""
    return (
        html
        .replace("__APP_TITLE__", escape("ShopStack"))
        .replace("__APP_SUBTITLE__", escape("Know what is at home, what to buy next, and what to skip."))
        .replace("__API_BASE__", _API_BASE)
        .replace("__AUTH_STORAGE_KEY__", _AUTH_STORAGE_KEY)
    )


@router.get("/", response_class=HTMLResponse, summary="ShopStack frontend shell")
def shell_root(request: Request) -> HTMLResponse:
    """Serve the real ShopStack frontend shell."""
    del request
    return HTMLResponse(
        render_frontend_shell_html(),
        headers={"Cache-Control": "no-store"},
    )


__all__ = ["render_frontend_shell_html", "router"]
