from __future__ import annotations

CSS = """
:root {
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
  --text-faint: #8A7B6A;
  --accent: #176B49;
  --accent-hover: #10563A;
  --accent-soft: #E8F3EC;
  --green: #176B49;
  --red: #A63F31;
  --amber: #A76012;
  --blue: #315F9B;
  --focus: #2E7DFF;
  --shadow: 0 14px 32px rgba(75, 50, 24, 0.10);
  --radius: 18px; --radius-sm: 10px;
  --font-display: Charter, "Iowan Old Style", Georgia, serif;
  --font-body: "Avenir Next", "Segoe UI", ui-sans-serif, system-ui, sans-serif;
}
.gradio-container { background: var(--bg) !important; color: var(--text) !important; font-family: var(--font-body); max-width: 1280px !important; margin: 0 auto; line-height: 1.45; }
.app-header { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; padding:18px 0 20px; border-bottom:1px solid var(--border); margin-bottom:20px; }
.brand-title { font-family: var(--font-display); font-size:32px; line-height:1; font-weight:800; letter-spacing:-0.035em; margin:0; color:var(--text); }
.brand-subtitle { margin-top:8px; font-size:15px; color:var(--text-muted); }
.env-badge { display:inline-flex; align-items:center; border-radius:999px; padding:4px 11px; background:#F7E5C7; color:#9B5C14; font-size:12px; font-weight:800; letter-spacing:0.08em; text-transform:uppercase; }
.version-label { color:var(--text-faint); font-size:11px; text-align:right; margin-bottom:4px; }
.tabs { border: none !important; }
.tab-nav, .tabs [role="tablist"] { background: transparent !important; border-bottom: 1px solid var(--border-strong) !important; padding: 0 !important; gap: 6px !important; }
.tab-nav button, .tabs button[role="tab"], button[role="tab"] { background: transparent !important; border: none !important; color: var(--text-muted) !important; font-size: 14px !important; font-weight: 650 !important; padding: 10px 16px 12px !important; border-radius: var(--radius-sm) var(--radius-sm) 0 0 !important; transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease; opacity: 1 !important; }
.tab-nav button.selected, .tabs button[aria-selected="true"], button[role="tab"][aria-selected="true"] { background: var(--accent-soft) !important; color: var(--accent) !important; box-shadow: inset 0 -3px 0 var(--accent); }
.tab-nav button:hover, .tabs button[role="tab"]:hover, button[role="tab"]:hover { background: var(--bg-input) !important; color: var(--text) !important; }
.gr-box { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }
.gr-text-input, .gr-number-input, .gr-dropdown, textarea { background: var(--bg-input) !important; border: 1px solid var(--border) !important; border-radius: var(--radius-sm) !important; color: var(--text) !important; }
.gr-text-input:focus, .gr-number-input:focus, textarea:focus { border-color: var(--focus) !important; box-shadow: 0 0 0 3px rgba(46,125,255,0.18) !important; }
.gr-button { background: var(--accent) !important; border: none !important; border-radius: var(--radius-sm) !important; color: #fff !important; font-weight: 500 !important; padding: 8px 20px !important; transition: all 0.15s !important; }
.gr-button:hover { background: var(--accent-hover) !important; transform: translateY(-1px); }
.gr-button.secondary { background: var(--bg-input) !important; border: 1px solid var(--border-strong) !important; color: var(--text) !important; }
.gr-button.secondary:hover { background: var(--border) !important; }
h1, h2, h3 { color: var(--text) !important; font-family: var(--font-display); font-weight: 800 !important; letter-spacing: -0.025em !important; margin: 0 0 8px 0 !important; }
h2 { font-size: 30px !important; line-height: 1.12 !important; }
h3 { font-size: 18px !important; line-height: 1.2 !important; }
label, .gr-form-label { color: var(--text) !important; font-size: 13px !important; font-weight: 500 !important; letter-spacing: 0.2px !important; }
.gr-dataframe { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }
.gr-dataframe table { font-size: 13px !important; }
.gr-dataframe th { background: var(--bg-input) !important; color: var(--text-muted) !important; border-bottom: 1px solid var(--border) !important; padding: 10px 12px !important; }
.gr-dataframe td { border-bottom: 1px solid var(--border) !important; padding: 8px 12px !important; color: var(--text) !important; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 100px; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.045em; }
.badge-green { background: rgba(23,107,73,0.14); color: var(--green); }
.badge-red { background: rgba(166,63,49,0.14); color: var(--red); }
.badge-amber { background: rgba(167,96,18,0.16); color: var(--amber); }
.badge-blue { background: rgba(49,95,155,0.14); color: var(--blue); }
.badge-gray { background: rgba(95,81,68,0.14); color: var(--text-muted); }
.home-card { background: var(--bg-card-strong); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow); color: var(--text); }
.hero-panel { position: relative; overflow: hidden; margin-bottom: 12px; padding: 24px; background: linear-gradient(135deg, #FFFFFF 0%, #FFF7EA 55%, #F3F7EE 100%); }
.hero-panel::after { content:""; position:absolute; right:-46px; top:-58px; width:170px; height:170px; border-radius:999px; background:rgba(23,107,73,0.10); border:1px solid rgba(23,107,73,0.12); }
.hero-panel h2 { max-width: 760px; }
.hero-copy { position: relative; z-index:1; color: var(--text-muted); font-size: 16px; margin: 8px 0 0; max-width: 780px; }
.stat-card { background: var(--bg-card-strong); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; text-align: center; box-shadow: 0 8px 22px rgba(75, 50, 24, 0.07); color: var(--text); }
.stat-value { font-size: 34px; font-weight: 700; color: var(--text); line-height: 1; }
.metric-card { background: var(--bg-card-strong); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px; text-align: left; min-height: 110px; box-shadow: 0 8px 22px rgba(75, 50, 24, 0.06); color: var(--text); }
.metric-card:hover { border-color: var(--border-strong); transform: translateY(-1px); transition: border-color 0.15s ease, transform 0.15s ease; }
.metric-label, .stat-label { font-size: 12px; color: var(--text-muted); margin-top: 6px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 750; }
.metric-value { font-family: var(--font-display); font-size: 42px; line-height: 1; font-weight: 850; color: var(--text); margin-top: 12px; letter-spacing:-0.035em; }
.metric-hint { color: var(--text-muted); font-size: 12px; margin-top: 8px; }
.action-row { display: flex; gap: 8px; flex-wrap: wrap; }
.action-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin: 0 0 14px 0; }
.action-tile { appearance:none; border:1px solid var(--border); border-radius:var(--radius); background:var(--bg-card-strong); color:var(--text); text-align:left; padding:16px; cursor:pointer; box-shadow:0 8px 22px rgba(75,50,24,0.06); transition:transform 0.15s ease, border-color 0.15s ease, background 0.15s ease; }
.action-tile:hover { transform:translateY(-1px); border-color:var(--border-strong); background:var(--bg-input); }
.action-tile:focus-visible { outline:3px solid rgba(46,125,255,0.22); outline-offset:2px; }
.action-tile-label { display:block; font-family:var(--font-display); font-weight:850; font-size:19px; letter-spacing:-0.02em; }
.action-tile-subtitle { display:block; color:var(--text-muted); font-size:12px; margin-top:5px; line-height:1.35; }
.action-tile-primary { background:var(--accent); border-color:var(--accent); color:#fff; }
.action-tile-primary .action-tile-subtitle { color:rgba(255,255,255,0.78); }
.action-tile-primary:hover { background:var(--accent-hover); border-color:var(--accent-hover); }
.item-row { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border); align-items: center; }
.item-card { margin-bottom: 10px; }
.chip { display: inline-block; border: 1px solid var(--border); border-radius: 999px; padding: 5px 10px; font-size: 11px; background: #fff; color: var(--text); }
.muted { color: var(--text-muted); }
.section-kicker { font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.12em; font-weight:800; margin-bottom:10px; }
.workflow-rail { text-align:left; padding:16px 18px; margin: 6px 0 18px; }
.workflow-steps { display:flex; flex-wrap:wrap; gap:10px 12px; align-items:center; }
.workflow-step { display:inline-flex; align-items:center; gap:7px; color:var(--text-muted); font-size:12px; font-weight:800; letter-spacing:0.02em; text-transform:uppercase; }
.workflow-step::before { content:""; width:9px; height:9px; border-radius:999px; border:2px solid currentColor; box-sizing:border-box; }
.workflow-step.is-complete { color:var(--green); }
.workflow-step.is-complete::before { background:currentColor; }
.workflow-step.is-pending { color:var(--text-muted); }
.workflow-arrow { color:var(--border-strong); font-weight:800; }
.tab-nav { overflow: visible !important; flex-wrap: wrap !important; }
@media (max-width: 768px) {
  .gradio-container { max-width: 100% !important; padding: 0 8px !important; }
  .app-header { align-items:flex-start; flex-direction:column; }
  .brand-title { font-size:28px; }
  .tab-nav button, .tabs button[role="tab"], button[role="tab"] { font-size: 12px !important; padding: 8px 10px !important; }
  .gr-box, .home-card, .stat-card { border-radius: 12px !important; padding: 12px !important; }
  .gr-text-input, .gr-number-input, input, textarea, select { font-size: 16px !important; }
  .gr-button { padding: 10px 16px !important; font-size: 14px !important; min-height: 44px; }
  .gr-dataframe { font-size: 11px !important; overflow-x: auto !important; display: block !important; }
  .gr-dataframe table { min-width: 600px; }
  .gr-dataframe th, .gr-dataframe td { padding: 6px 8px !important; white-space: nowrap; }
  .stat-value, .metric-value { font-size: 30px !important; }
  div[style*="display:grid"] { grid-template-columns: 1fr !important; }
  .action-row { flex-direction: column !important; }
  .item-row { flex-direction: column !important; align-items: flex-start !important; gap: 4px !important; }
}
@media (max-width: 480px) {
  .tab-nav { display: flex !important; flex-wrap: wrap !important; gap: 2px !important; }
  .tab-nav button, .tabs button[role="tab"], button[role="tab"] { flex: 1 0 auto !important; min-width: 0 !important; padding: 7px 6px !important; font-size: 11px !important; }
  .gr-button { width: 100% !important; }
}
"""
