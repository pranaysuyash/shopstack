from __future__ import annotations

CSS = """
:root {
  --bg: #FFF8ED;
  --bg-card: #FFFFFF;
  --bg-warm: #FFF3DA;
  --bg-input: #FFF3DA;
  --border: #E8DCCB;
  --text: #201A14;
  --text-dim: #75685A;
  --accent: #6D5BD0;
  --accent-hover: #5c4bc5;
  --green: #1F8A5B;
  --red: #C94A3A;
  --amber: #D98A1F;
  --blue: #3F6FB5;
  --radius: 20px; --radius-sm: 12px;
}
.gradio-container { background: var(--bg) !important; color: var(--text) !important; font-family: Inter, ui-sans-serif, system-ui, sans-serif; max-width: 1280px !important; margin: 0 auto; }
.tabs { border: none !important; }
.tab-nav { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; padding: 4px !important; gap: 2px !important; }
.tab-nav button { background: transparent !important; border: none !important; color: var(--text-dim) !important; font-size: 13px !important; padding: 8px 14px !important; border-radius: var(--radius-sm) !important; transition: all 0.15s; }
.tab-nav button.selected { background: var(--accent) !important; color: #fff !important; }
.tab-nav button:hover { background: var(--bg-input) !important; color: var(--text) !important; }
.gr-box { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }
.gr-text-input, .gr-number-input, .gr-dropdown, textarea { background: var(--bg-input) !important; border: 1px solid var(--border) !important; border-radius: var(--radius-sm) !important; color: var(--text) !important; }
.gr-text-input:focus, .gr-number-input:focus, textarea:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 2px rgba(108,92,231,0.2) !important; }
.gr-button { background: var(--accent) !important; border: none !important; border-radius: var(--radius-sm) !important; color: #fff !important; font-weight: 500 !important; padding: 8px 20px !important; transition: all 0.15s !important; }
.gr-button:hover { background: var(--accent-hover) !important; transform: translateY(-1px); }
.gr-button.secondary { background: var(--bg-input) !important; border: 1px solid var(--border) !important; }
.gr-button.secondary:hover { background: var(--border) !important; }
h1, h2, h3 { color: var(--text) !important; font-weight: 600 !important; margin: 0 0 8px 0 !important; }
label, .gr-form-label { color: var(--text) !important; font-size: 13px !important; font-weight: 500 !important; letter-spacing: 0.2px !important; }
.gr-dataframe { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }
.gr-dataframe table { font-size: 13px !important; }
.gr-dataframe th { background: var(--bg-input) !important; color: var(--text-dim) !important; border-bottom: 1px solid var(--border) !important; padding: 10px 12px !important; }
.gr-dataframe td { border-bottom: 1px solid var(--border) !important; padding: 8px 12px !important; color: var(--text) !important; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 100px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
.badge-green { background: rgba(31,138,91,0.12); color: var(--green); }
.badge-red { background: rgba(201,74,58,0.12); color: var(--red); }
.badge-amber { background: rgba(217,138,31,0.12); color: var(--amber); }
.badge-blue { background: rgba(63,111,181,0.12); color: var(--blue); }
.badge-gray { background: rgba(117,104,90,0.12); color: var(--text-dim); }
.home-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; box-shadow: 0 6px 20px rgba(80, 50, 20, 0.06); }
.stat-card { background: var(--bg-warm); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; text-align: center; }
.stat-value { font-size: 34px; font-weight: 700; color: var(--text); line-height: 1; }
.metric-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; text-align: left; }
.stat-label { font-size: 12px; color: var(--text-dim); margin-top: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.action-row { display: flex; gap: 8px; flex-wrap: wrap; }
.item-row { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border); align-items: center; }
.item-card { margin-bottom: 10px; }
.chip { display: inline-block; border: 1px solid var(--border); border-radius: 999px; padding: 5px 10px; font-size: 11px; background: #fff; color: var(--text); }
.tab-nav { overflow: visible !important; flex-wrap: wrap !important; }
@media (max-width: 768px) {
  .gradio-container { max-width: 100% !important; padding: 0 8px !important; }
  .tab-nav button { font-size: 11px !important; padding: 6px 8px !important; }
  .gr-box, .home-card, .stat-card { border-radius: 12px !important; padding: 12px !important; }
  .gr-text-input, .gr-number-input, input, textarea, select { font-size: 16px !important; }
  .gr-button { padding: 10px 16px !important; font-size: 14px !important; min-height: 44px; }
  .gr-dataframe { font-size: 11px !important; overflow-x: auto !important; display: block !important; }
  .gr-dataframe table { min-width: 600px; }
  .gr-dataframe th, .gr-dataframe td { padding: 6px 8px !important; white-space: nowrap; }
  .stat-value { font-size: 24px !important; }
  div[style*="display:grid"] { grid-template-columns: 1fr !important; }
  .action-row { flex-direction: column !important; }
  .item-row { flex-direction: column !important; align-items: flex-start !important; gap: 4px !important; }
}
@media (max-width: 480px) {
  .tab-nav { display: flex !important; flex-wrap: wrap !important; gap: 2px !important; }
  .tab-nav button { flex: 1 0 auto !important; min-width: 0 !important; padding: 6px 6px !important; font-size: 10px !important; }
  .gr-button { width: 100% !important; }
}
"""
