"""FastAPI frontend shell for ShopStack.

This is the real user-facing entrypoint for the app while Gradio
remains available under ``/gradio`` as a compatibility surface.
The shell is intentionally API-driven: it pulls state from the v1
HTTP contract instead of reaching into UI internals.
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
  <meta name="theme-color" content="#111614">
  <style>
    :root {
      --bg: #0f1412;
      --bg-elevated: rgba(21, 28, 25, 0.92);
      --bg-card: rgba(24, 32, 28, 0.96);
      --bg-soft: rgba(40, 52, 46, 0.72);
      --text: #f2ece2;
      --text-muted: #c8bfaf;
      --text-dim: #9f9587;
      --accent: #7fc98d;
      --accent-strong: #b3e6b2;
      --accent-warm: #d0a35c;
      --border: rgba(255, 255, 255, 0.12);
      --border-strong: rgba(255, 255, 255, 0.2);
      --shadow: 0 24px 72px rgba(0, 0, 0, 0.42);
      --radius-xl: 30px;
      --radius-lg: 22px;
      --radius-md: 16px;
      --radius-sm: 12px;
      --font-display: "Charter", "Iowan Old Style", "Palatino Linotype", Georgia, serif;
      --font-body: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
      --font-mono: "SF Mono", "Fira Code", "Cascadia Code", ui-monospace, monospace;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; background: var(--bg); color: var(--text); }
    body {
      font-family: var(--font-body);
      line-height: 1.45;
      background:
        radial-gradient(circle at top left, rgba(127, 201, 141, 0.18), transparent 26%),
        radial-gradient(circle at 80% 10%, rgba(208, 163, 92, 0.14), transparent 22%),
        linear-gradient(180deg, #101612 0%, #0b0f0e 100%);
      min-height: 100vh;
      overflow-x: hidden;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: radial-gradient(circle at center, black 35%, transparent 90%);
      opacity: 0.5;
    }
    a { color: inherit; }
    button, input, select, textarea {
      font: inherit;
    }
    .shell {
      position: relative;
      z-index: 1;
      max-width: 1440px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }
    .masthead {
      display: grid;
      grid-template-columns: 1.25fr 0.75fr;
      gap: 20px;
      align-items: end;
      margin-bottom: 22px;
    }
    .brand {
      padding: 10px 0 0;
    }
    .eyebrow {
      margin: 0 0 10px;
      text-transform: uppercase;
      letter-spacing: 0.24em;
      color: var(--accent-strong);
      font-size: 0.72rem;
      font-weight: 700;
    }
    h1 {
      margin: 0;
      font-family: var(--font-display);
      font-size: clamp(3rem, 7vw, 5.4rem);
      line-height: 0.95;
      letter-spacing: -0.05em;
      text-wrap: balance;
    }
    .lede {
      max-width: 62ch;
      margin: 16px 0 0;
      color: var(--text-muted);
      font-size: 1.02rem;
    }
    .status-rail {
      justify-self: end;
      width: min(100%, 420px);
      display: grid;
      gap: 10px;
    }
    .rail-card, .panel {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }
    .rail-card {
      padding: 16px 18px;
    }
    .rail-label {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      color: var(--text-dim);
      margin-bottom: 8px;
    }
    .rail-value {
      font-size: 1rem;
      font-weight: 650;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
      font-size: 0.8rem;
    }
    .pill[data-tone="good"] { border-color: rgba(127, 201, 141, 0.35); color: var(--accent-strong); }
    .pill[data-tone="warn"] { border-color: rgba(208, 163, 92, 0.38); color: #f2cf8e; }
    .pill[data-tone="bad"] { border-color: rgba(207, 95, 95, 0.4); color: #f4a8a8; }
    .grid {
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 18px;
      align-items: start;
    }
    .panel {
      padding: 22px;
    }
    .panel h2 {
      margin: 0 0 10px;
      font-family: var(--font-display);
      font-size: 1.75rem;
      letter-spacing: -0.03em;
    }
    .panel-subtitle {
      margin: 0 0 18px;
      color: var(--text-muted);
      max-width: 70ch;
    }
    .hero {
      display: grid;
      gap: 18px;
    }
    .hero-top {
      display: grid;
      grid-template-columns: 1.3fr 0.7fr;
      gap: 16px;
    }
    .command-card {
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
      padding: 18px;
    }
    .command-field {
      display: grid;
      gap: 12px;
    }
    .command-field textarea,
    .auth-field input,
    .auth-field select {
      width: 100%;
      color: var(--text);
      background: rgba(8, 12, 11, 0.7);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: var(--radius-md);
      padding: 14px 15px;
      outline: none;
    }
    .command-field textarea::placeholder,
    .auth-field input::placeholder {
      color: var(--text-dim);
    }
    .command-field textarea:focus,
    .auth-field input:focus,
    .auth-field select:focus,
    button:focus-visible {
      border-color: rgba(179, 230, 178, 0.75);
      box-shadow: 0 0 0 4px rgba(127, 201, 141, 0.16);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .button {
      appearance: none;
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 11px 15px;
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      cursor: pointer;
      transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
    }
    .button:hover { transform: translateY(-1px); border-color: var(--border-strong); }
    .button.primary {
      background: linear-gradient(180deg, rgba(127, 201, 141, 0.22), rgba(127, 201, 141, 0.12));
      border-color: rgba(127, 201, 141, 0.38);
      color: var(--accent-strong);
      font-weight: 700;
    }
    .button.ghost {
      color: var(--text-muted);
    }
    .quick-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .mini-chip {
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(255,255,255,0.03);
      color: var(--text-muted);
      padding: 8px 11px;
      cursor: pointer;
    }
    .two-col {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }
    .card-list {
      display: grid;
      gap: 12px;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .metric {
      padding: 14px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.03);
    }
    .metric .label {
      font-size: 0.72rem;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--text-dim);
      margin-bottom: 8px;
    }
    .metric .value {
      font-family: var(--font-display);
      font-size: 2rem;
      letter-spacing: -0.04em;
    }
    .subtle {
      color: var(--text-muted);
      font-size: 0.92rem;
    }
    .section-title {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }
    .section-title h3 {
      margin: 0;
      font-size: 0.86rem;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--text-dim);
    }
    .stack {
      display: grid;
      gap: 12px;
    }
    .item {
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: rgba(255,255,255,0.03);
      padding: 14px;
      display: grid;
      gap: 8px;
    }
    .item-row {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: baseline;
    }
    .item-title {
      font-weight: 650;
    }
    .item-meta {
      color: var(--text-dim);
      font-size: 0.88rem;
    }
    .preview {
      border-radius: var(--radius-lg);
      border: 1px solid var(--border);
      padding: 14px;
      background: rgba(255,255,255,0.03);
      min-height: 96px;
    }
    .preview[data-tone="muted"] { color: var(--text-dim); }
    .preview[data-tone="good"] { color: var(--accent-strong); }
    .preview[data-tone="warn"] { color: #f2cf8e; }
    .tiny {
      color: var(--text-dim);
      font-size: 0.78rem;
    }
    .form-grid {
      display: grid;
      gap: 10px;
    }
    .auth-field {
      display: grid;
      gap: 8px;
    }
    .auth-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .auth-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 4px;
    }
    .log {
      display: grid;
      gap: 10px;
      font-family: var(--font-mono);
      font-size: 0.8rem;
      color: var(--text-muted);
    }
    .log-line {
      border-left: 2px solid rgba(127, 201, 141, 0.4);
      padding-left: 12px;
    }
    .auth-shell {
      display: grid;
      gap: 12px;
    }
    .signature {
      margin-top: 8px;
      color: var(--text-dim);
      font-size: 0.8rem;
    }
    .hidden { display: none !important; }
    @media (max-width: 1120px) {
      .masthead, .grid, .hero-top, .metric-grid, .two-col, .auth-row {
        grid-template-columns: 1fr;
      }
      .status-rail { justify-self: stretch; width: 100%; }
    }
    @media (max-width: 720px) {
      .shell { padding: 18px 12px 34px; }
      .panel { padding: 16px; border-radius: 20px; }
      h1 { font-size: clamp(2.4rem, 10vw, 3.4rem); }
      .actions, .quick-actions, .auth-actions { gap: 8px; }
    }
  </style>
</head>
<body>
  <div class="shell" data-shell-root="true">
    <header class="masthead">
      <div class="brand">
        <p class="eyebrow">FastAPI backend + API-first frontend</p>
        <h1>__APP_TITLE__</h1>
        <p class="lede">__APP_SUBTITLE__</p>
        <div class="signature">Legacy compatibility workspace: <code>/gradio</code></div>
      </div>
      <div class="status-rail">
        <div class="rail-card">
          <div class="rail-label">Runtime</div>
          <div class="rail-value"><span class="pill" id="runtime-pill" data-tone="warn">Loading runtime…</span><span id="runtime-detail" class="subtle">Fetching public metadata.</span></div>
        </div>
        <div class="rail-card">
          <div class="rail-label">Household</div>
          <div class="rail-value"><span class="pill" id="household-pill">Not connected</span><span id="household-detail" class="subtle">Sign in or register a device to unlock household-scoped data.</span></div>
        </div>
        <div class="rail-card">
          <div class="rail-label">Health</div>
          <div class="rail-value"><span class="pill" id="health-pill" data-tone="warn">Checking…</span><span id="health-detail" class="subtle">PWA shell + API readiness.</span></div>
        </div>
      </div>
    </header>

    <main class="grid">
      <section class="panel hero" aria-labelledby="command-title">
        <div>
          <h2 id="command-title">Command surface</h2>
          <p class="panel-subtitle">Type a request, preview the parser result, then execute against the household-scoped backend. This replaces the old “demo-only” interaction path with a real API contract.</p>
        </div>
        <div class="hero-top">
          <div class="command-card">
            <div class="command-field">
              <textarea id="command-input" rows="4" placeholder="Add milk and bread to the shopping list, then show me what is running low."></textarea>
              <div class="actions">
                <button class="button primary" id="preview-btn" type="button">Preview</button>
                <button class="button" id="execute-btn" type="button">Execute</button>
                <button class="button ghost" id="clear-btn" type="button">Clear</button>
              </div>
              <div class="quick-actions" aria-label="Quick commands">
                <button class="mini-chip" type="button" data-quick-command="Add milk to the shopping list.">Milk</button>
                <button class="mini-chip" type="button" data-quick-command="Log bread as purchased.">Log purchase</button>
                <button class="mini-chip" type="button" data-quick-command="What should I buy today?">Ask</button>
                <button class="mini-chip" type="button" data-quick-command="Mark tomatoes as consumed.">Use up</button>
              </div>
            </div>
          </div>
          <div class="command-card">
            <div class="section-title">
              <h3>Preview</h3>
              <span class="tiny" id="preview-mode">parse-only</span>
            </div>
            <div class="preview" id="preview-box" data-tone="muted">Start typing a command to see how the parser routes it.</div>
            <div class="tiny" style="margin-top:10px;">
              Contract: <code>/api/v1/command/preview</code> → <code>/api/v1/command/execute</code> ·
              History: <code>/api/v1/command/recent</code>
            </div>
          </div>
        </div>
      </section>

      <aside class="panel auth-shell" aria-labelledby="connect-title">
        <div>
          <h2 id="connect-title">Connect a household</h2>
          <p class="panel-subtitle">Register a device, log back in, or paste an existing bearer token to drive the household-scoped API.</p>
        </div>
        <div class="form-grid">
          <div class="auth-row">
            <label class="auth-field">
              <span class="tiny">Device ID</span>
              <input id="device-id" autocomplete="off" placeholder="shopstack-web">
            </label>
            <label class="auth-field">
              <span class="tiny">Device secret</span>
              <input id="device-secret" autocomplete="off" placeholder="paste or generate a long secret">
            </label>
          </div>
          <div class="auth-row">
            <label class="auth-field">
              <span class="tiny">Household name</span>
              <input id="household-name" autocomplete="off" placeholder="Default Household">
            </label>
            <label class="auth-field">
              <span class="tiny">Household ID (optional)</span>
              <input id="household-id" autocomplete="off" placeholder="hh_default">
            </label>
          </div>
          <div class="auth-actions">
            <button class="button primary" id="register-btn" type="button">Register</button>
            <button class="button" id="login-btn" type="button">Login</button>
          </div>
          <label class="auth-field">
            <span class="tiny">Bearer token override</span>
            <input id="token-input" autocomplete="off" placeholder="Paste an existing token here">
          </label>
          <div class="auth-actions">
            <button class="button" id="use-token-btn" type="button">Use token</button>
            <button class="button ghost" id="forget-token-btn" type="button">Forget session</button>
          </div>
          <div class="auth-field">
            <span class="tiny">Known households</span>
            <select id="household-select">
              <option value="">Connect first</option>
            </select>
          </div>
          <div class="auth-actions">
            <button class="button" id="switch-btn" type="button">Switch household</button>
            <button class="button ghost" id="refresh-btn" type="button">Refresh data</button>
          </div>
          <div class="tiny">
            Auth: <code>/api/v1/auth/register</code>, <code>/api/v1/auth/login</code> ·
            Household: <code>/api/v1/household</code>
          </div>
        </div>
      </aside>

      <section class="panel" aria-labelledby="dashboard-title">
        <div class="section-title">
          <h3 id="dashboard-title">Household snapshot</h3>
          <span class="tiny">From <code>/api/v1/dashboard/today</code></span>
        </div>
        <div class="metric-grid" id="metric-grid">
          <div class="metric"><div class="label">Pantry</div><div class="value">—</div></div>
          <div class="metric"><div class="label">Use soon</div><div class="value">—</div></div>
          <div class="metric"><div class="label">Low items</div><div class="value">—</div></div>
          <div class="metric"><div class="label">Recent buys</div><div class="value">—</div></div>
        </div>
        <div class="signature" id="household-meta">Waiting for a household-scoped token.</div>
      </section>

      <section class="panel" aria-labelledby="history-title">
        <div class="section-title">
          <h3 id="history-title">Recent commands</h3>
          <span class="tiny">Trace-backed history</span>
        </div>
        <div class="stack" id="history-list">
          <div class="item">
            <div class="item-title">No commands yet</div>
            <div class="item-meta">Execute a command to populate household history.</div>
          </div>
        </div>
      </section>

      <section class="panel" aria-labelledby="lists-title">
        <div class="section-title">
          <h3 id="lists-title">Useful lists</h3>
          <span class="tiny">Use soon, low items, and recent purchases</span>
        </div>
        <div class="two-col">
          <div class="stack">
            <div class="item">
              <div class="item-row"><div class="item-title">Use soon</div><div class="pill" id="use-soon-count">0</div></div>
              <div class="stack" id="use-soon-list"></div>
            </div>
            <div class="item">
              <div class="item-row"><div class="item-title">Low inventory</div><div class="pill" id="low-count">0</div></div>
              <div class="stack" id="low-list"></div>
            </div>
          </div>
          <div class="stack">
            <div class="item">
              <div class="item-row"><div class="item-title">Recent purchases</div><div class="pill" id="recent-count">0</div></div>
              <div class="stack" id="recent-list"></div>
            </div>
            <div class="item">
              <div class="item-row"><div class="item-title">API trace</div><div class="pill" id="api-status" data-tone="warn">idle</div></div>
              <div class="log" id="event-log">
                <div class="log-line">Load the page to fetch public runtime metadata.</div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
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
        line.style.borderLeftColor = 'rgba(127, 201, 141, 0.8)';
      } else if (tone === 'warn') {
        line.style.borderLeftColor = 'rgba(208, 163, 92, 0.85)';
      } else if (tone === 'bad') {
        line.style.borderLeftColor = 'rgba(207, 95, 95, 0.9)';
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

    function renderDashboard(data) {
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
        log(`Loaded public metadata: ${whoami.runtime_mode || 'local_mock'}.`, 'good');
      } catch (err) {
        setPill(els.runtimePill, 'Unavailable', 'bad');
        setPill(els.healthPill, 'Degraded', 'bad');
        els.runtimeDetail.textContent = err.message || 'Failed to load public metadata.';
        els.healthDetail.textContent = 'The backend is reachable, but the public metadata failed.';
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
        await refreshPrivateState();
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
        await refreshPrivateState();
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
        await refreshPrivateState();
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
      await refreshPrivateState();
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
        await refreshPrivateState();
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
      await refreshPrivateState();
    });

    document.querySelectorAll('[data-quick-command]').forEach((button) => {
      button.addEventListener('click', () => {
        els.commandInput.value = button.getAttribute('data-quick-command') || '';
        refreshPreview();
      });
    });

    hydrateSessionFromUrl();
    seedDefaults();
    refreshPublicState().then(() => {
      refreshPrivateState();
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


__all__ = ["router", "render_frontend_shell_html"]
