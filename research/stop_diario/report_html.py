"""Gerador de relatório HTML interativo self-contained (Plotly.js) para Stop Diário Máximo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Simulador & Gerência de Stop Diário Máximo — Jumba Quant</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {
    --bg: #070b11;
    --bg-card: #0f1724;
    --bg-card-2: #131e30;
    --bg-hover: #1a2840;
    --border: #1e2d45;
    --txt: #e2e8f0;
    --txt-sec: #94a3b8;
    --txt-mut: #64748b;
    --cyan: #00e5ff;
    --green: #00e87a;
    --red: #ff3860;
    --gold: #fbbf24;
    --blue: #3aa0ff;
    --mono: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace;
    --sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--txt);
    font-family: var(--sans);
    font-size: 13px;
    line-height: 1.5;
    padding: 18px 24px 48px;
  }
  .topbar {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 14px;
    padding: 14px 18px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 16px;
  }
  .title-block h1 {
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.05em;
    color: #f8fafc;
  }
  .title-block .sub {
    font-size: 11px;
    color: var(--txt-sec);
    margin-top: 2px;
  }
  .preset-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .pill-btn {
    padding: 7px 14px;
    font-size: 11px;
    font-family: var(--mono);
    font-weight: 600;
    border-radius: 7px;
    border: 1px solid var(--border);
    background: #0b111c;
    color: var(--txt-sec);
    cursor: pointer;
    transition: all .15s;
  }
  .pill-btn:hover { border-color: var(--cyan); color: var(--txt); }
  .pill-btn.active {
    background: rgba(0,229,255,0.14);
    border-color: var(--cyan);
    color: var(--cyan);
    box-shadow: 0 0 12px rgba(0,229,255,0.12);
  }
  .tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 18px;
  }
  .tab-btn {
    padding: 10px 16px;
    font-size: 12px;
    font-family: var(--mono);
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--txt-mut);
    cursor: pointer;
    white-space: nowrap;
  }
  .tab-btn:hover { color: var(--txt); }
  .tab-btn.active {
    color: var(--cyan);
    border-bottom-color: var(--cyan);
    font-weight: 700;
  }
  .grid-6 { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; }
  .grid-4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
  @media (max-width: 1150px) { .grid-6, .grid-4 { grid-template-columns: repeat(2, 1fr); } }
  @media (max-width: 820px) { .grid-3, .grid-2 { grid-template-columns: 1fr; } }
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 14px;
  }
  .kpi {
    background: var(--bg-card-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
  }
  .kpi-title {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--txt-mut);
    margin-bottom: 6px;
  }
  .kpi-val {
    font-family: var(--mono);
    font-size: 20px;
    font-weight: 700;
  }
  .kpi-sub {
    font-size: 11px;
    color: var(--txt-sec);
    margin-top: 4px;
  }
  .card-title {
    font-size: 11px;
    font-family: var(--mono);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--txt-sec);
    margin-bottom: 10px;
    font-weight: 700;
  }
  .kv-row {
    display: flex;
    justify-content: space-between;
    font-family: var(--mono);
    font-size: 12px;
    padding: 4px 0;
    border-bottom: 1px solid rgba(255,255,255,0.03);
  }
  .kv-row:last-child { border-bottom: none; }
  .kv-row span:first-child { color: var(--txt-sec); }
  .banner {
    padding: 12px 16px;
    border-radius: 8px;
    margin-bottom: 14px;
    font-size: 12px;
    border-left: 4px solid var(--gold);
    background: rgba(251,191,36,0.06);
  }
  .banner.ok {
    border-left-color: var(--green);
    background: rgba(0,232,122,0.06);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-family: var(--mono);
    font-size: 11px;
  }
  th, td {
    padding: 7px 8px;
    border-bottom: 1px solid var(--border);
    text-align: right;
    white-space: nowrap;
  }
  th:first-child, td:first-child,
  th.left, td.left { text-align: left; }
  th {
    color: var(--txt-mut);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    background: #0b111c;
    position: sticky;
    top: 0;
  }
  th.sortable { cursor: pointer; }
  th.sortable:hover { color: var(--cyan); }
  tr:hover td { background: rgba(255,255,255,0.02); }
  tr.hl-cons td { background: rgba(0,229,255,0.09); }
  tr.hl-prof td { background: rgba(251,191,36,0.09); }
  .scroll-table { max-height: 460px; overflow: auto; }
  .rec-bar-row {
    display: flex;
    align-items: center;
    gap: 10px;
    font-family: var(--mono);
    font-size: 11px;
    padding: 7px 10px;
    background: var(--bg-card-2);
    border: 1px solid var(--border);
    border-radius: 7px;
    margin-bottom: 6px;
  }
  .rec-bar-row.stop-hit { border-color: var(--cyan); box-shadow: inset 0 0 0 1px rgba(0,229,255,0.25); }
  .rec-track { flex: 1; height: 11px; background: #070b11; border-radius: 6px; overflow: hidden; }
  .rec-fill { height: 100%; border-radius: 6px; }
  .badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 9px;
    font-weight: 700;
    font-family: var(--mono);
  }
  .badge-stop { background: rgba(0,229,255,0.18); color: var(--cyan); border: 1px solid rgba(0,229,255,0.4); }
  .badge-win { background: rgba(58,160,255,0.16); color: var(--blue); }
  .badge-wdo { background: rgba(251,191,36,0.16); color: var(--gold); }
  pre {
    background: #070b11;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    font-family: var(--mono);
    font-size: 11px;
    color: #cbd5e1;
    overflow-x: auto;
  }
  .c-cyan { color: var(--cyan) !important; }
  .c-green { color: var(--green) !important; }
  .c-red { color: var(--red) !important; }
  .c-gold { color: var(--gold) !important; }
  .c-mut { color: var(--txt-mut) !important; }
  .c-blue { color: var(--blue) !important; }
</style>
</head>
<body>

<div class="topbar">
  <div class="title-block">
    <h1>SIMULADOR & GERÊNCIA DE STOP DIÁRIO MÁXIMO — JUMBA QUANT</h1>
    <div class="sub" id="subtitleText">Carregando base MT5 Strategy Tester 2026 + Barras M1 Reais...</div>
  </div>
  <div class="preset-bar" id="presetBar"></div>
</div>

<div class="tabs" id="tabBar"></div>
<div id="content"></div>

<script>
const REPORT_DATA = __REPORT_DATA_JSON__;

const TABS = [
  { id: 'overview', label: 'Visão Geral' },
  { id: 'sweep', label: 'Stop Ótimo (Sweep & Combo)' },
  { id: 'recovery', label: 'Recuperação (MAE)' },
  { id: 'walkforward', label: 'Walk-Forward' },
  { id: 'montecarlo', label: 'Monte Carlo' },
  { id: 'robots', label: 'Por Robô (MAE/MFE)' },
  { id: 'ea', label: 'EA Monitor & MT5' },
];

let state = {
  pid: REPORT_DATA.default_preset,
  tab: 'overview',
  sweepScope: 'global_m1',
  recScope: 'global',
  robotSort: { key: 'total_profit', dir: -1 },
  selectedRobot: null,
};

const fmt = (n, d = 2) => Number(n ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtBRL = (n, d = 0) => {
  const v = Number(n ?? 0);
  const s = Math.abs(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
  return `${v < -0.001 ? '-' : ''}R$ ${s}`;
};
const fmtBRLSigned = (n, d = 0) => {
  const v = Number(n ?? 0);
  const s = Math.abs(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
  return `${v < -0.001 ? '-' : v > 0.001 ? '+' : ''}R$ ${s}`;
};
const fmtPct = (n, d = 1) => `${fmt(n, d)}%`;

function curData() {
  return REPORT_DATA.presets[state.pid];
}

function renderTopbar() {
  const d = curData();
  document.getElementById('subtitleText').textContent =
    `${d.subtitle} · ${d.period_start} → ${d.period_end} (${d.total_days} pregões: ${d.oos_days} OOS + ${d.is_days} IS) · Custo B3 líquido`;

  const pb = document.getElementById('presetBar');
  pb.innerHTML = Object.values(REPORT_DATA.presets).map(p =>
    `<button class="pill-btn ${state.pid === p.portfolio_id ? 'active' : ''}" onclick="setPid('${p.portfolio_id}')">${p.label}</button>`
  ).join('');

  const tb = document.getElementById('tabBar');
  tb.innerHTML = TABS.map(t =>
    `<button class="tab-btn ${state.tab === t.id ? 'active' : ''}" onclick="setTab('${t.id}')">${t.label}</button>`
  ).join('');
}

window.setPid = (pid) => {
  state.pid = pid;
  state.selectedRobot = null;
  renderAll();
};
window.setTab = (tab) => {
  state.tab = tab;
  renderAll();
};
window.setSweepScope = (sc) => {
  state.sweepScope = sc;
  renderContent();
};
window.setRecScope = (sc) => {
  state.recScope = sc;
  renderContent();
};
window.sortRobots = (k) => {
  if (state.robotSort.key === k) state.robotSort.dir *= -1;
  else state.robotSort = { key: k, dir: -1 };
  renderContent();
};
window.selectRobot = (id) => {
  const d = curData();
  state.selectedRobot = d.robots.find(r => r.id === id) || null;
  renderContent();
};

function kpiHtml(title, value, sub, cls = '') {
  return `<div class="kpi">
    <div class="kpi-title">${title}</div>
    <div class="kpi-val ${cls}">${value}</div>
    ${sub ? `<div class="kpi-sub">${sub}</div>` : ''}
  </div>`;
}

function renderOverview(d) {
  const b = d.baseline;
  const f1 = d.final_ret_dd;
  const f2 = d.final_profit;
  const fc = d.final_combo;
  const rs = d.robust_stops;
  const cb = rs.combo_best_ret_dd || {};
  const maeG = d.portfolio.mae_daily_m1;
  const maeC = d.portfolio.mae_daily_closed;
  const maeW = d.portfolio.mae_win_m1;
  const maeD = d.portfolio.mae_wdo_m1;

  const stopVal = rs.primary_used;
  const recBanner = d.stop_recommended
    ? `<div class="banner ok"><strong class="c-green">STOP DIÁRIO RECOMENDADO:</strong> O limite global de <strong>${fmtBRL(stopVal)}</strong> eleva o Ret/DD de <strong>${fmt(b.ret_dd)}x</strong> para <strong>${fmt(f1.ret_dd)}x</strong> com lucro de <strong>${fmtBRLSigned(f1.ret)}</strong> (parando apenas ${f1.stopped} de ${d.total_days} pregões). O Combo Multi-Escopo (${cb.stop_global ? 'G ' + fmtBRL(cb.stop_global) + ' · ' : ''}WIN ${fmtBRL(cb.stop_win)} · WDO ${fmtBRL(cb.stop_wdo)}) eleva o Ret/DD para <strong>${fmt(fc.ret_dd)}x</strong> reduzindo o DD diário para <strong>${fmtBRL(fc.max_dd)}</strong>.</div>`
    : `<div class="banner"><strong class="c-gold">AVISO:</strong> Nenhum stop diário único melhorou o Ret/DD acima do piso de 80% do MAE médio. O valor <strong>${fmtBRL(stopVal)}</strong> serve como proteção de cauda.</div>`;

  const scenarioCard = (title, borderClr, tag, sim, cfgStr) => `
    <div class="card" style="border-color:${borderClr};border-width:2px;margin-bottom:0">
      <div class="card-title" style="color:${borderClr}">${title}</div>
      <div style="font-size:11px;color:var(--txt-mut);font-family:var(--mono);margin-bottom:8px">${cfgStr}</div>
      <div class="kv-row"><span>Lucro Total</span><span class="${sim.ret >= b.ret ? 'c-green' : 'c-gold'}">${fmtBRLSigned(sim.ret)}</span></div>
      <div class="kv-row"><span>Max DD Diário</span><span class="c-red">${fmtBRL(sim.max_dd)}</span></div>
      <div class="kv-row"><span>Max DD Intraday M1</span><span class="c-red">${fmtBRL(sim.max_dd_intraday)}</span></div>
      <div class="kv-row"><span>Ret / DD</span><span class="c-cyan">${fmt(sim.ret_dd)}x</span></div>
      <div class="kv-row"><span>Sharpe Anual</span><span>${fmt(sim.sharpe)}</span></div>
      <div class="kv-row"><span>Pior Dia</span><span class="c-red">${fmtBRLSigned(sim.worst_day)}</span></div>
      <div class="kv-row"><span>Dias Parados</span><span>${sim.stopped}d (${fmtPct(sim.stopped_pct)})</span></div>
      <div class="kv-row"><span>OOS (Jan–Mai)</span><span class="c-blue">${fmtBRLSigned(sim.oos.ret)} (${fmt(sim.oos.ret_dd)}x)</span></div>
      <div class="kv-row"><span>IS (Mai–Nov)</span><span class="c-green">${fmtBRLSigned(sim.is.ret)} (${fmt(sim.is.ret_dd)}x)</span></div>
    </div>`;

  const html = `
    <div class="grid-6" style="margin-bottom:14px">
      ${kpiHtml('Robôs / Trades', `${d.portfolio.total_robots} · ${d.portfolio.total_trades.toLocaleString('pt-BR')}`, `${d.portfolio.win_robots} WIN + ${d.portfolio.wdo_robots} WDO`, 'c-cyan')}
      ${kpiHtml('Lucro Líquido (Sem Stop)', fmtBRLSigned(b.ret), `Bruto ${fmtBRLSigned(d.portfolio.total_profit_gross)}`, 'c-green')}
      ${kpiHtml('Max DD Base (Dia / M1)', fmtBRL(b.max_dd), `Intraday M1: ${fmtBRL(b.max_dd_intraday)}`, 'c-red')}
      ${kpiHtml('Stop Ret/DD Ótimo ★', fmtBRL(rs.primary_used), `Ret/DD: ${fmt(b.ret_dd)}x → ${fmt(f1.ret_dd)}x`, 'c-cyan')}
      ${kpiHtml('Stop Máx Lucro 💰', fmtBRL(rs.global_profit || rs.primary_used), `Lucro: ${fmtBRLSigned(f2.ret)}`, 'c-gold')}
      ${kpiHtml('Combo Multi-Escopo ⚡', `${fmt(fc.ret_dd)}x`, `DD: ${fmtBRL(fc.max_dd)} · ${fc.stopped}d`, 'c-green')}
    </div>

    ${recBanner}

    <div class="card">
      <div class="card-title">Excursão Adversa Diária (MAE Real M1 vs Trades Fechados)</div>
      <div class="grid-4">
        ${kpiHtml('Global M1 Médio / P90', `${fmtBRL(maeG.mean)} / ${fmtBRL(maeG.p90)}`, `σ=${fmtBRL(maeG.std)} · Máx ${fmtBRL(maeG.max)}`, 'c-gold')}
        ${kpiHtml('Global Fechado Médio / Máx', `${fmtBRL(maeC.mean)} / ${fmtBRL(maeC.max)}`, `Subestima risco intrabar se não usar M1`, 'c-mut')}
        ${kpiHtml('WIN Isolado M1 (Méd / P90)', `${fmtBRL(maeW.mean)} / ${fmtBRL(maeW.p90)}`, `Máx: ${fmtBRL(maeW.max)} · Sugestão: ${fmtBRL(rs.win_isolated_ret_dd || rs.win_isolated_tail)}`, 'c-blue')}
        ${kpiHtml('WDO Isolado M1 (Méd / P90)', `${fmtBRL(maeD.mean)} / ${fmtBRL(maeD.p90)}`, `Máx: ${fmtBRL(maeD.max)} · Cauda: ${fmtBRL(rs.wdo_isolated_tail)}`, 'c-gold')}
      </div>
    </div>

    <div class="grid-4" style="margin-bottom:14px">
      ${scenarioCard('Sem Stop (Baseline)', '#475569', 'base', b, 'Sem trava diária')}
      ${scenarioCard('Stop Global Ret/DD ★', '#00e5ff', 'rdd', f1, `Global = ${fmtBRL(rs.primary_used)}`)}
      ${scenarioCard('Stop Global Máx Lucro 💰', '#fbbf24', 'prof', f2, `Global = ${fmtBRL(rs.global_profit || rs.primary_used)}`)}
      ${scenarioCard('Combo Multi-Escopo ⚡', '#00e87a', 'combo', fc, `G ${fmtBRL(cb.stop_global || 0)} · WIN ${fmtBRL(cb.stop_win || 0)} · WDO ${fmtBRL(cb.stop_wdo || 0)}`)}
    </div>

    <div class="card">
      <div id="equityPlot" style="width:100%;height:430px"></div>
    </div>

    <div class="card">
      <div class="card-title">Resumo por Ativo (Isolado)</div>
      <div class="grid-2">
        ${d.asset_summary.map(a => `
          <div class="kpi">
            <div class="kpi-title">${a.asset} (${a.robots} robôs · ${a.trades.toLocaleString('pt-BR')} trades · ${a.lots.toLocaleString('pt-BR')} lotes)</div>
            <div class="kv-row"><span>Lucro Líquido</span><span class="c-green">${fmtBRLSigned(a.profit)}</span></div>
            <div class="kv-row"><span>Max DD Diário</span><span class="c-red">${fmtBRL(a.max_dd)}</span></div>
            <div class="kv-row"><span>Ret/DD Isolado</span><span class="c-cyan">${fmt(a.ret_dd)}x</span></div>
            <div class="kv-row"><span>MAE M1 Médio / Máx</span><span class="c-gold">${fmtBRL(a.mae_avg)} / ${fmtBRL(a.mae_max)}</span></div>
            <div class="kv-row"><span>Stop Ret/DD / Cauda</span><span>${a.stop_conserv > 0 ? fmtBRL(a.stop_conserv) : 'N/Rec'} / ${fmtBRL(a.tail_guard_stop)}</span></div>
          </div>`).join('')}
      </div>
    </div>`;

  document.getElementById('content').innerHTML = html;

  // Plot Equity + Underwater Drawdown
  const dates = b.curve.map(p => p.date);
  const stoppedPts = f1.curve.filter(p => p.stopped);
  const traces = [
    { x: dates, y: b.curve.map(p => p.equity), name: `Sem Stop (${fmt(b.ret_dd)}x)`, type: 'scatter', mode: 'lines', line: { color: '#64748b', width: 2, dash: 'dot' } },
    { x: dates, y: f1.curve.map(p => p.equity), name: `Stop ${fmtBRL(rs.primary_used)} (${fmt(f1.ret_dd)}x)`, type: 'scatter', mode: 'lines', line: { color: '#00e5ff', width: 2.5 } },
    { x: dates, y: fc.curve.map(p => p.equity), name: `Combo Multi-Escopo (${fmt(fc.ret_dd)}x)`, type: 'scatter', mode: 'lines', line: { color: '#00e87a', width: 2 } },
    { x: stoppedPts.map(p => p.date), y: stoppedPts.map(p => p.equity), name: `Stop Global Disparado (${stoppedPts.length}d)`, type: 'scatter', mode: 'markers', marker: { color: '#ff3860', size: 7, symbol: 'triangle-down' } },
    { x: dates, y: b.curve.map(p => -p.dd), name: 'DD Base', type: 'scatter', mode: 'lines', yaxis: 'y2', line: { color: 'rgba(148,163,184,0.45)', width: 1.2, dash: 'dot' } },
    { x: dates, y: fc.curve.map(p => -p.dd), name: 'DD Combo', type: 'scatter', mode: 'lines', yaxis: 'y2', fill: 'tozeroy', fillcolor: 'rgba(0,232,122,0.10)', line: { color: '#00e87a', width: 1.2 } },
  ];
  Plotly.newPlot('equityPlot', traces, {
    title: { text: 'Curva de Capital & Drawdown Diário (2026: OOS Jan–Mai + IS Mai–Nov)', font: { family: 'JetBrains Mono', size: 13, color: '#e2e8f0' } },
    paper_bgcolor: '#0f1724', plot_bgcolor: '#070b11',
    font: { family: 'JetBrains Mono', color: '#94a3b8', size: 11 },
    xaxis: { gridcolor: 'rgba(255,255,255,0.04)' },
    yaxis: { title: 'Capital Acumulado (R$)', domain: [0.28, 1.0], gridcolor: 'rgba(255,255,255,0.04)' },
    yaxis2: { title: 'DD (R$)', domain: [0.0, 0.22], gridcolor: 'rgba(255,255,255,0.04)' },
    shapes: [{ type: 'line', x0: '2026-05-06', x1: '2026-05-06', y0: 0, y1: 1, yref: 'paper', line: { color: '#fbbf24', width: 1, dash: 'dash' } }],
    annotations: [{ x: '2026-05-06', y: 1, yref: 'paper', text: 'Fim OOS | Início IS', showarrow: false, font: { color: '#fbbf24', size: 10 }, yanchor: 'bottom' }],
    legend: { orientation: 'h', y: -0.14 },
    margin: { l: 65, r: 20, t: 42, b: 55 },
    hovermode: 'x unified',
  }, { responsive: true });
}

function renderSweep(d) {
  const scopes = [
    ['global_m1', 'Global M1 (Real)'],
    ['global_closed', 'Global Fechado (Trades)'],
    ['win_isolated', 'WIN Isolado (M1)'],
    ['win_portfolio', 'WIN no Portfólio (M1)'],
    ['wdo_isolated', 'WDO Isolado (M1)'],
    ['wdo_portfolio', 'WDO no Portfólio (M1)'],
  ];
  const rows = d.sweeps[state.sweepScope] || [];
  const rs = d.robust_stops;
  const hlCons = state.sweepScope === 'global_m1' ? rs.primary_used
    : state.sweepScope === 'global_closed' ? rs.global_closed_ret_dd
    : state.sweepScope.startsWith('win') ? (rs.win_isolated_ret_dd || rs.win_isolated_tail)
    : (rs.wdo_isolated_ret_dd || rs.wdo_isolated_tail);
  const hlProf = state.sweepScope === 'global_m1' ? rs.global_profit : 0;

  const mat = d.combined.matrix_2d || [];
  const wCands = [...new Set(mat.map(m => m.stop_win))].sort((a, b) => a - b);
  const dCands = [...new Set(mat.map(m => m.stop_wdo))].sort((a, b) => a - b);

  const topCombos = d.combined.top_by_ret_dd || [];
  const topProf = d.combined.top_by_ret || [];

  const html = `
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px">
      ${scopes.map(([id, lbl]) => `<button class="pill-btn ${state.sweepScope === id ? 'active' : ''}" onclick="setSweepScope('${id}')">${lbl}</button>`).join('')}
    </div>

    <div class="grid-2">
      <div class="card"><div id="sweepPlotMain" style="width:100%;height:340px"></div></div>
      <div class="card"><div id="sweepPlotRecov" style="width:100%;height:340px"></div></div>
    </div>

    <div class="grid-2">
      <div class="card"><div id="comboHeatmap" style="width:100%;height:360px"></div></div>
      <div class="card">
        <div class="card-title">Top 12 Combos Multi-Escopo (Global + WIN + WDO) por Ret/DD</div>
        <div class="scroll-table" style="max-height:320px">
          <table>
            <thead><tr><th class="left">Global</th><th>WIN</th><th>WDO</th><th>Lucro</th><th>Max DD</th><th>Ret/DD</th><th>Pior Dia</th><th>Parados (G/W/D)</th><th>OOS Ret/DD</th></tr></thead>
            <tbody>
              ${topCombos.slice(0, 12).map(c => `<tr>
                <td class="left c-cyan">${c.stop_global ? fmtBRL(c.stop_global) : 'Off'}</td>
                <td class="c-blue">${c.stop_win ? fmtBRL(c.stop_win) : 'Off'}</td>
                <td class="c-gold">${c.stop_wdo ? fmtBRL(c.stop_wdo) : 'Off'}</td>
                <td class="c-green">${fmtBRLSigned(c.ret)}</td>
                <td class="c-red">${fmtBRL(c.max_dd)}</td>
                <td class="c-cyan">${fmt(c.ret_dd)}x</td>
                <td class="c-red">${fmtBRLSigned(c.worst_day)}</td>
                <td>${c.stopped}d (${c.stopped_global}/${c.stopped_win}/${c.stopped_wdo})</td>
                <td>${fmt(c.oos_ret_dd)}x</td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Top 10 Combos Multi-Escopo por Máximo Lucro (c/ controle de DD)</div>
      <div class="scroll-table" style="max-height:260px">
        <table>
          <thead><tr><th class="left">Global</th><th>WIN</th><th>WDO</th><th>Lucro</th><th>Max DD</th><th>Ret/DD</th><th>Sharpe</th><th>Pior Dia</th><th>Parados</th><th>OOS Lucro</th></tr></thead>
          <tbody>
            ${topProf.slice(0, 10).map(c => `<tr>
              <td class="left c-cyan">${c.stop_global ? fmtBRL(c.stop_global) : 'Off'}</td>
              <td class="c-blue">${c.stop_win ? fmtBRL(c.stop_win) : 'Off'}</td>
              <td class="c-gold">${c.stop_wdo ? fmtBRL(c.stop_wdo) : 'Off'}</td>
              <td class="c-green">${fmtBRLSigned(c.ret)}</td>
              <td class="c-red">${fmtBRL(c.max_dd)}</td>
              <td class="c-cyan">${fmt(c.ret_dd)}x</td>
              <td>${fmt(c.sharpe)}</td>
              <td class="c-red">${fmtBRLSigned(c.worst_day)}</td>
              <td>${c.stopped}d</td>
              <td class="c-blue">${fmtBRLSigned(c.oos_ret)}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Tabela Completa do Sweep — ${scopes.find(s => s[0] === state.sweepScope)[1]}</div>
      <div class="scroll-table">
        <table>
          <thead><tr>
            <th class="left">Stop</th><th>Lucro</th><th>Max DD</th><th>DD M1</th><th>Ret/DD</th><th>Sharpe</th>
            <th>Win% Dias</th><th>Parados</th><th>Recup%</th><th>R$ Salvo</th><th>R$ Perdido</th><th>Net Líq.</th><th>Pior Dia</th><th>OOS Ret/DD</th>
          </tr></thead>
          <tbody>
            ${rows.map(r => {
              const isC = r.stop === hlCons;
              const isP = r.stop === hlProf;
              const cls = isC ? 'hl-cons' : isP ? 'hl-prof' : '';
              const tag = isC ? ' ★' : isP ? ' 💰' : '';
              return `<tr class="${cls}">
                <td class="left ${isC ? 'c-cyan' : isP ? 'c-gold' : ''}">${fmtBRL(r.stop)}${tag}</td>
                <td class="c-green">${fmtBRLSigned(r.ret)}</td>
                <td class="c-red">${fmtBRL(r.max_dd)}</td>
                <td class="c-red">${fmtBRL(r.max_dd_intraday)}</td>
                <td class="c-cyan">${fmt(r.ret_dd)}x</td>
                <td>${fmt(r.sharpe)}</td>
                <td>${fmtPct(r.win_rate)}</td>
                <td>${r.stopped}d (${fmtPct(r.stopped_pct)})</td>
                <td class="c-gold">${fmtPct(r.recovery_rate)}</td>
                <td class="c-green">${fmtBRL(r.saved)}</td>
                <td class="c-red">${fmtBRL(r.missed)}</td>
                <td class="${r.net >= 0 ? 'c-green' : 'c-red'}">${fmtBRLSigned(r.net)}</td>
                <td class="c-red">${fmtBRLSigned(r.worst_day)}</td>
                <td>${fmt(r.oos_ret_dd)}x</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>
    </div>`;

  document.getElementById('content').innerHTML = html;

  Plotly.newPlot('sweepPlotMain', [
    { x: rows.map(r => r.stop), y: rows.map(r => r.ret_dd), name: 'Ret/DD', type: 'scatter', mode: 'lines+markers', marker: { size: 4 }, line: { color: '#00e5ff', width: 2 } },
    { x: rows.map(r => r.stop), y: rows.map(r => r.ret), name: 'Lucro (R$)', type: 'scatter', mode: 'lines', yaxis: 'y2', line: { color: '#00e87a', width: 1.8, dash: 'dot' } },
  ], {
    title: { text: 'Sweep: Ret/DD & Lucro vs Stop (R$)', font: { family: 'JetBrains Mono', size: 12, color: '#e2e8f0' } },
    paper_bgcolor: '#0f1724', plot_bgcolor: '#070b11', font: { family: 'JetBrains Mono', color: '#94a3b8', size: 10 },
    xaxis: { title: 'Stop (R$)', gridcolor: 'rgba(255,255,255,0.04)' },
    yaxis: { title: 'Ret/DD', gridcolor: 'rgba(255,255,255,0.04)' },
    yaxis2: { title: 'Lucro (R$)', overlaying: 'y', side: 'right', gridcolor: 'transparent' },
    legend: { orientation: 'h', y: -0.22 }, margin: { l: 55, r: 55, t: 38, b: 55 }, hovermode: 'x unified',
  }, { responsive: true });

  const recRows = rows.filter(r => r.stopped > 0);
  Plotly.newPlot('sweepPlotRecov', [
    { x: recRows.map(r => r.stop), y: recRows.map(r => r.recovery_rate), name: 'Recuperação %', type: 'scatter', mode: 'lines+markers', fill: 'tozeroy', fillcolor: 'rgba(251,191,36,0.08)', line: { color: '#fbbf24', width: 2 }, marker: { size: 4 } },
    { x: recRows.map(r => r.stop), y: recRows.map(r => r.stopped_pct), name: '% Dias Parados', type: 'scatter', mode: 'lines', line: { color: '#ff3860', width: 1.5, dash: 'dot' } },
  ], {
    title: { text: 'Dias Parados que Teriam Recuperado (%)', font: { family: 'JetBrains Mono', size: 12, color: '#e2e8f0' } },
    paper_bgcolor: '#0f1724', plot_bgcolor: '#070b11', font: { family: 'JetBrains Mono', color: '#94a3b8', size: 10 },
    xaxis: { title: 'Stop (R$)', gridcolor: 'rgba(255,255,255,0.04)' },
    yaxis: { title: '%', range: [0, 100], gridcolor: 'rgba(255,255,255,0.04)' },
    legend: { orientation: 'h', y: -0.22 }, margin: { l: 50, r: 20, t: 38, b: 55 }, hovermode: 'x unified',
  }, { responsive: true });

  const zGrid = dCands.map(dv => wCands.map(wv => {
    const found = mat.find(m => m.stop_win === wv && m.stop_wdo === dv);
    return found ? found.ret_dd : null;
  }));
  Plotly.newPlot('comboHeatmap', [{
    z: zGrid,
    x: wCands.map(v => v === 0 ? 'Sem WIN' : fmtBRL(v)),
    y: dCands.map(v => v === 0 ? 'Sem WDO' : fmtBRL(v)),
    type: 'heatmap',
    colorscale: [[0, '#1e293b'], [0.4, '#0369a1'], [0.75, '#00e5ff'], [1, '#00e87a']],
    text: zGrid.map(row => row.map(v => v !== null ? fmt(v, 1) + 'x' : '')),
    texttemplate: '%{text}',
    hovertemplate: 'WIN %{x} · WDO %{y}<br>Ret/DD: %{z:.2f}x<extra></extra>',
  }], {
    title: { text: 'Heatmap 2D: Ret/DD (Stop WIN × Stop WDO)', font: { family: 'JetBrains Mono', size: 12, color: '#e2e8f0' } },
    paper_bgcolor: '#0f1724', plot_bgcolor: '#070b11', font: { family: 'JetBrains Mono', color: '#94a3b8', size: 10 },
    xaxis: { title: 'Stop WIN' }, yaxis: { title: 'Stop WDO' },
    margin: { l: 75, r: 20, t: 38, b: 55 },
  }, { responsive: true });
}

function renderRecovery(d) {
  const rs = d.robust_stops;
  const activeStop = state.recScope === 'global' ? rs.primary_used
    : state.recScope === 'win' ? (rs.win_isolated_ret_dd || rs.win_isolated_tail)
    : (rs.wdo_isolated_ret_dd || rs.wdo_isolated_tail);
  const bands = d.recovery[state.recScope] || [];

  document.getElementById('content').innerHTML = `
    <div style="display:flex;gap:8px;margin-bottom:14px">
      <button class="pill-btn ${state.recScope === 'global' ? 'active' : ''}" onclick="setRecScope('global')">Global (WIN+WDO)</button>
      <button class="pill-btn ${state.recScope === 'win' ? 'active' : ''}" onclick="setRecScope('win')">WIN Isolado</button>
      <button class="pill-btn ${state.recScope === 'wdo' ? 'active' : ''}" onclick="setRecScope('wdo')">WDO Isolado</button>
    </div>
    <div class="card">
      <div class="card-title">Quando a carteira/ativo cai X intraday (M1), em quantos % dos dias recupera (fecha &ge; 0)?</div>
      ${bands.map(r => {
        const hit = activeStop > 0 && r.lo <= activeStop && r.hi > activeStop;
        const barClr = r.recov_pct > 50 ? '#00e87a' : r.recov_pct > 30 ? '#fbbf24' : '#ff3860';
        const txtCls = r.recov_pct > 50 ? 'c-green' : r.recov_pct > 30 ? 'c-gold' : 'c-red';
        return `<div class="rec-bar-row ${hit ? 'stop-hit' : ''}">
          <span style="width:125px;color:var(--txt-sec)">${fmtBRL(r.lo)} – ${fmtBRL(r.hi)}</span>
          <span style="width:45px;color:var(--txt-mut)">${r.days}d</span>
          <div class="rec-track"><div class="rec-fill" style="width:${Math.min(100, r.recov_pct)}%;background:${barClr}"></div></div>
          <span style="width:55px;text-align:right" class="${txtCls}">${fmtPct(r.recov_pct, 0)}</span>
          <span style="width:125px;text-align:right" class="${r.expected >= 0 ? 'c-green' : 'c-red'}">E[P&L] ${fmtBRLSigned(r.expected)}</span>
          ${hit ? '<span class="badge badge-stop">STOP</span>' : '<span style="width:42px"></span>'}
        </div>`;
      }).join('')}
    </div>`;
}

function renderWalkForward(d) {
  const wf = d.walk_forward;
  const folds = wf.folds || [];
  const pos = folds.filter(f => f.improvement > 0).length;
  const imps = folds.map(f => f.improvement * 100).sort((a, b) => a - b);
  const medImp = imps.length ? imps[Math.floor(imps.length / 2)] : 0;

  document.getElementById('content').innerHTML = `
    <div class="grid-4" style="margin-bottom:14px">
      ${kpiHtml('Folds Rolling', `${folds.length}`, `${wf.train_window}d treino → ${wf.test_window}d teste`, 'c-cyan')}
      ${kpiHtml('Stop Mediano OOS', fmtBRL(wf.robust_stop_ret_dd), `Máx Lucro Mediano: ${fmtBRL(wf.robust_stop_profit)}`, 'c-gold')}
      ${kpiHtml('Folds Positivos', `${pos} / ${folds.length}`, folds.length ? fmtPct(pos / folds.length * 100) : '0%', 'c-green')}
      ${kpiHtml('Melhoria Mediana Ret/DD', `${medImp >= 0 ? '+' : ''}${fmtPct(medImp)}`, 'OOS rolling fora da amostra', medImp >= 0 ? 'c-green' : 'c-red')}
    </div>

    <div class="card">
      <div class="card-title">Validação Cruzada Canônica (Jan–Mai OOS vs Mai–Nov IS)</div>
      <table>
        <thead><tr><th class="left">Experimento</th><th>Stop Calibrado</th><th>Lucro Base</th><th>DD Base</th><th>Ret/DD Base</th><th>Lucro c/ Stop</th><th>DD c/ Stop</th><th>Ret/DD c/ Stop</th><th>Dias Parados</th></tr></thead>
        <tbody>
          ${(wf.canonical_splits || []).map(sp => `<tr>
            <td class="left">${sp.label}</td>
            <td class="c-cyan">${fmtBRL(sp.stop_calibrated)}</td>
            <td>${fmtBRLSigned(sp.base_ret)}</td>
            <td class="c-red">${fmtBRL(sp.base_dd)}</td>
            <td>${fmt(sp.base_ret_dd)}x</td>
            <td class="c-green">${fmtBRLSigned(sp.stop_ret)}</td>
            <td class="c-red">${fmtBRL(sp.stop_dd)}</td>
            <td class="${sp.stop_ret_dd >= sp.base_ret_dd ? 'c-green' : 'c-gold'}">${fmt(sp.stop_ret_dd)}x</td>
            <td>${sp.stopped}d</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>

    <div class="card">
      <div class="card-title">Folds Walk-Forward Rolling</div>
      <table>
        <thead><tr><th class="left">Fold</th><th class="left">Janela Treino</th><th class="left">Janela Teste OOS</th><th>Stop Ótimo</th><th>Ret/DD OOS</th><th>Ret/DD Base</th><th>Melhoria</th><th>Lucro OOS</th><th>Base OOS</th><th>Parado</th></tr></thead>
        <tbody>
          ${folds.map(f => `<tr style="opacity:${f.improvement <= 0 ? 0.6 : 1}">
            <td class="left">F${f.fold}</td>
            <td class="left c-mut">${f.train_period}</td>
            <td class="left">${f.test_period}</td>
            <td class="c-cyan">${fmtBRL(f.optimal_stop_ret_dd)}</td>
            <td>${fmt(f.oos_ret_dd)}x</td>
            <td class="c-mut">${fmt(f.base_ret_dd)}x</td>
            <td class="${f.improvement > 0 ? 'c-green' : 'c-red'}">${f.improvement > 0 ? '+' : ''}${fmtPct(f.improvement * 100)}</td>
            <td>${fmtBRLSigned(f.oos_ret)}</td>
            <td class="c-mut">${fmtBRLSigned(f.base_ret)}</td>
            <td>${f.oos_stopped}d</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function renderMonteCarlo(d) {
  const renderBlock = (title, mc) => `
    <div class="card">
      <div class="card-title">${title} — ${mc.n.toLocaleString('pt-BR')} Simulações (Stop ${fmtBRL(mc.stop_value)})</div>
      <div class="grid-3" style="margin-bottom:12px">
        ${kpiHtml('Vence em Ret/DD', fmtPct(mc.wins_rdd / mc.n * 100), `${mc.wins_rdd} de ${mc.n}`, 'c-green')}
        ${kpiHtml('Reduz Max DD', fmtPct(mc.wins_dd / mc.n * 100), `${mc.wins_dd} de ${mc.n}`, 'c-cyan')}
        ${kpiHtml('Aumenta Lucro', fmtPct(mc.wins_ret / mc.n * 100), `${mc.wins_ret} de ${mc.n}`, mc.wins_ret / mc.n >= 0.5 ? 'c-green' : 'c-gold')}
      </div>
      <table>
        <thead><tr><th class="left">Métrica</th><th>Com Stop</th><th>Sem Stop</th><th>Variação</th></tr></thead>
        <tbody>
          <tr><td class="left">Ret/DD Médio</td><td class="c-cyan">${fmt(mc.avg_rdd_stop)}x</td><td class="c-mut">${fmt(mc.avg_rdd_no)}x</td><td class="${mc.avg_rdd_stop >= mc.avg_rdd_no ? 'c-green' : 'c-red'}">${fmtPct((mc.avg_rdd_stop / (mc.avg_rdd_no || 1) - 1) * 100)}</td></tr>
          <tr><td class="left">Max DD Médio</td><td class="c-cyan">${fmtBRL(mc.avg_dd_stop)}</td><td class="c-mut">${fmtBRL(mc.avg_dd_no)}</td><td class="${mc.avg_dd_stop <= mc.avg_dd_no ? 'c-green' : 'c-red'}">${fmtPct((mc.avg_dd_stop / (mc.avg_dd_no || 1) - 1) * 100)}</td></tr>
          <tr><td class="left">Max DD Cauda (P95)</td><td class="c-cyan">${fmtBRL(mc.p95_dd_stop)}</td><td class="c-mut">${fmtBRL(mc.p95_dd_no)}</td><td class="${mc.p95_dd_stop <= mc.p95_dd_no ? 'c-green' : 'c-red'}">${fmtPct((mc.p95_dd_stop / (mc.p95_dd_no || 1) - 1) * 100)}</td></tr>
        </tbody>
      </table>
    </div>`;

  document.getElementById('content').innerHTML =
    renderBlock('Bootstrap Diário IID (1 dia)', d.monte_carlo.iid) +
    renderBlock('Block Bootstrap (Blocos de 5 pregões — preserva clustering de volatilidade)', d.monte_carlo.block_5d);
}

function renderRobots(d) {
  const { key, dir } = state.robotSort;
  const sorted = [...d.robots].sort((a, b) => {
    const getVal = (obj) => {
      if (key === 'mae_p90') return obj.mae.p90;
      if (key === 'mfe_mean') return obj.mfe.mean;
      if (key === 'worst_day') return obj.daily.worst;
      return obj[key] ?? 0;
    };
    const va = getVal(a), vb = getVal(b);
    if (typeof va === 'string') return va.localeCompare(vb) * dir;
    return (va - vb) * dir;
  });

  const cols = [
    ['id', 'Robô'], ['asset', 'Ativo'], ['magic', 'Magic'], ['total_trades', 'Trades'],
    ['total_profit', 'Lucro'], ['win_rate', 'WR%'], ['pf', 'PF'], ['payoff', 'Payoff'],
    ['mae_p90', 'MAE P90'], ['mfe_mean', 'MFE Méd'], ['mfe_eff', 'Eff%'],
    ['optimal_trade_stop', 'Stop/Trade'], ['worst_day', 'Pior Dia'], ['suggested_daily_stop', 'Stop/Dia'], ['worst_15_share_pct', '% Piores 15d'],
  ];

  const sb = state.selectedRobot;
  const detailHtml = sb ? `
    <div class="card" style="border-color:var(--cyan)">
      <div class="card-title c-cyan">Detalhe Individual — ${sb.id} (${sb.desc} · Magic ${sb.magic})</div>
      <div class="grid-4" style="margin-bottom:12px">
        ${kpiHtml('Lucro Líquido', fmtBRLSigned(sb.total_profit), `${sb.total_trades} trades · ${sb.total_lots} lotes`, sb.total_profit >= 0 ? 'c-green' : 'c-red')}
        ${kpiHtml('Win Rate / PF', `${fmtPct(sb.win_rate)} / ${fmt(sb.pf)}`, `Payoff: ${fmt(sb.payoff)}`, 'c-cyan')}
        ${kpiHtml('Expectância / Trade', fmtBRLSigned(sb.expectancy, 2), `Gain Méd ${fmtBRL(sb.avg_win)} · Loss Méd ${fmtBRL(sb.avg_loss)}`, sb.expectancy >= 0 ? 'c-green' : 'c-red')}
        ${kpiHtml('Stop Diário Sugerido', fmtBRL(sb.suggested_daily_stop), `Pior Dia: ${fmtBRLSigned(sb.daily.worst)} · 15p: ${fmtPct(sb.worst_15_share_pct)}`, 'c-gold')}
      </div>
      <div class="grid-2">
        <div class="kpi">
          <div class="kpi-title">MAE por Trade (Barras M1 Reais)</div>
          <div class="kv-row"><span>Média / σ</span><span class="c-gold">${fmtBRL(sb.mae.mean)} / ${fmtBRL(sb.mae.std)}</span></div>
          <div class="kv-row"><span>P50 / P75</span><span>${fmtBRL(sb.mae.p50)} / ${fmtBRL(sb.mae.p75)}</span></div>
          <div class="kv-row"><span>P90 / P95 / Máx</span><span class="c-red">${fmtBRL(sb.mae.p90)} / ${fmtBRL(sb.mae.p95)} / ${fmtBRL(sb.mae.max)}</span></div>
          <div class="kv-row"><span>Stop Ótimo por Trade (P90+0.5σ)</span><span class="c-cyan">${fmtBRL(sb.optimal_trade_stop)}</span></div>
        </div>
        <div class="kpi">
          <div class="kpi-title">MFE & Distribuição Diária</div>
          <div class="kv-row"><span>MFE Médio / P90</span><span class="c-green">${fmtBRL(sb.mfe.mean)} / ${fmtBRL(sb.mfe.p90)}</span></div>
          <div class="kv-row"><span>Eficiência MFE</span><span>${fmtPct(sb.mfe_eff)}</span></div>
          <div class="kv-row"><span>Média Diária / σ</span><span>${fmtBRLSigned(sb.daily.mean)} / ${fmtBRL(sb.daily.std)}</span></div>
          <div class="kv-row"><span>Melhor Dia / Pior Dia</span><span>${fmtBRLSigned(sb.daily.best)} / ${fmtBRLSigned(sb.daily.worst)}</span></div>
        </div>
      </div>
    </div>` : '';

  document.getElementById('content').innerHTML = `
    <div class="card">
      <div class="card-title">Desempenho & Excursão por Robô (clique na coluna p/ ordenar · clique na linha p/ detalhes)</div>
      <div class="scroll-table">
        <table>
          <thead><tr>
            ${cols.map(([k, l]) => `<th class="sortable ${k === 'id' ? 'left' : ''}" onclick="sortRobots('${k}')">${l} ${key === k ? (dir > 0 ? '↑' : '↓') : ''}</th>`).join('')}
          </tr></thead>
          <tbody>
            ${sorted.map(r => `
              <tr style="cursor:pointer;${sb && sb.id === r.id ? 'background:rgba(0,229,255,0.08)' : ''}" onclick="selectRobot('${r.id}')">
                <td class="left c-cyan">${r.id}</td>
                <td><span class="badge ${r.asset === 'WIN' ? 'badge-win' : 'badge-wdo'}">${r.asset}</span></td>
                <td class="c-mut">${r.magic}</td>
                <td>${r.total_trades}</td>
                <td class="${r.total_profit >= 0 ? 'c-green' : 'c-red'}">${fmtBRLSigned(r.total_profit)}</td>
                <td>${fmtPct(r.win_rate)}</td>
                <td>${fmt(r.pf)}</td>
                <td>${fmt(r.payoff)}</td>
                <td class="c-gold">${fmtBRL(r.mae.p90)}</td>
                <td class="c-blue">${fmtBRL(r.mfe.mean)}</td>
                <td>${fmtPct(r.mfe_eff)}</td>
                <td class="c-red">${fmtBRL(r.optimal_trade_stop)}</td>
                <td class="c-red">${fmtBRLSigned(r.daily.worst)}</td>
                <td class="c-gold">${fmtBRL(r.suggested_daily_stop)}</td>
                <td>${fmtPct(r.worst_15_share_pct)}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>
    ${detailHtml}
    <div class="card"><div id="worstContribPlot" style="width:100%;height:300px"></div></div>`;

  const byShare = [...d.robots].sort((a, b) => b.worst_15_share_pct - a.worst_15_share_pct);
  Plotly.newPlot('worstContribPlot', [{
    x: byShare.map(r => r.id),
    y: byShare.map(r => r.worst_15_share_pct),
    type: 'bar',
    marker: { color: byShare.map(r => r.asset === 'WIN' ? '#3aa0ff' : '#fbbf24') },
    text: byShare.map(r => `${fmtPct(r.worst_15_share_pct)} (${fmtBRLSigned(r.worst_15_pnl)})`),
    textposition: 'outside',
  }], {
    title: { text: 'Contribuição (%) nos 15 Piores Pregões da Carteira', font: { family: 'JetBrains Mono', size: 12, color: '#e2e8f0' } },
    paper_bgcolor: '#0f1724', plot_bgcolor: '#070b11', font: { family: 'JetBrains Mono', color: '#94a3b8', size: 10 },
    yaxis: { title: '% das Perdas nos 15 Piores Dias', gridcolor: 'rgba(255,255,255,0.04)' },
    margin: { l: 55, r: 20, t: 38, b: 45 },
  }, { responsive: true });
}

function renderEA(d) {
  const rs = d.robust_stops;
  const cb = rs.combo_best_ret_dd || {};
  const b = d.baseline;
  const f1 = d.final_ret_dd;
  const fc = d.final_combo;
  const wfa = d.walk_forward;
  const posF = (wfa.folds || []).filter(f => f.improvement > 0).length;
  const mc = d.monte_carlo.iid;

  document.getElementById('content').innerHTML = `
    <div class="card">
      <div class="card-title c-cyan">Jumba_Portfolio_Live_Monitor.mq5 (v4.00) + Jumba_SafetyGuard.mqh</div>
      <p style="font-size:12px;color:var(--txt-sec);margin-bottom:14px">
        Monitora P&L fechado do dia + flutuante em tempo real a cada <strong>1 segundo</strong> (e a cada evento <code>OnTradeTransaction</code>),
        separando <strong>Global (WIN+WDO)</strong>, <strong>WIN</strong> e <strong>WDO</strong>. Ao atingir qualquer limite fora da janela de leilão,
        fecha as posições abertas preservando o Magic original, cancela ordens pendentes e grava a trava baseada em data (<code>YYYYMMDD</code>)
        que bloqueia novas aberturas em todos os EAs Jumba e reseta automaticamente na virada de pregão.
      </p>
      <div class="grid-4" style="margin-bottom:14px">
        ${kpiHtml('Global Recomendado ★', fmtBRL(rs.primary_used), `Ret/DD ${fmt(b.ret_dd)}x → ${fmt(f1.ret_dd)}x`, 'c-cyan')}
        ${kpiHtml('Combo Multi-Escopo ⚡', `W ${fmtBRL(cb.stop_win || 0)} · D ${fmtBRL(cb.stop_wdo || 0)}`, `Ret/DD ${fmt(fc.ret_dd)}x · DD ${fmtBRL(fc.max_dd)}`, 'c-green')}
        ${kpiHtml('Checagem Live', '1 seg + TradeTx', 'Warning amarelo em 70%', 'c-gold')}
        ${kpiHtml('Robôs Protegidos', `${d.portfolio.total_robots} EAs`, 'Magics 88000..88016 + 89000..89016', 'c-blue')}
      </div>

      <div class="card-title">Presets de Inputs Prontos para o Monitor (${d.label})</div>
      <table>
        <thead><tr><th class="left">Perfil</th><th>InpMaxDailyLossGlobal</th><th>InpMaxDailyLossWin</th><th>InpMaxDailyLossWdo</th><th>Lucro 2026</th><th>Max DD</th><th>Ret/DD</th></tr></thead>
        <tbody>
          <tr>
            <td class="left c-cyan">Conservador Global ★</td>
            <td>${Number(rs.primary_used).toFixed(1)}</td><td>0.0</td><td>0.0</td>
            <td class="c-green">${fmtBRLSigned(f1.ret)}</td><td class="c-red">${fmtBRL(f1.max_dd)}</td><td class="c-cyan">${fmt(f1.ret_dd)}x</td>
          </tr>
          <tr>
            <td class="left c-gold">Máx Lucro Global 💰</td>
            <td>${Number(rs.global_profit || rs.primary_used).toFixed(1)}</td><td>0.0</td><td>0.0</td>
            <td class="c-green">${fmtBRLSigned(d.final_profit.ret)}</td><td class="c-red">${fmtBRL(d.final_profit.max_dd)}</td><td class="c-gold">${fmt(d.final_profit.ret_dd)}x</td>
          </tr>
          <tr>
            <td class="left c-green">Combo Multi-Escopo ⚡</td>
            <td>${Number(cb.stop_global || 0).toFixed(1)}</td><td>${Number(cb.stop_win || 0).toFixed(1)}</td><td>${Number(cb.stop_wdo || 0).toFixed(1)}</td>
            <td class="c-green">${fmtBRLSigned(fc.ret)}</td><td class="c-red">${fmtBRL(fc.max_dd)}</td><td class="c-green">${fmt(fc.ret_dd)}x</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-title">Arquitetura de Travas Compartilhadas (MT5 Terminal)</div>
        <pre>GlobalVariables gravadas com TodayKey() (YYYYMMDD):
  JUMBA_DAILY_STOP_GLOBAL = ${new Date().toISOString().slice(0,10).replaceAll('-','')}  -> bloqueia WIN + WDO
  JUMBA_DAILY_STOP_WIN    = ${new Date().toISOString().slice(0,10).replaceAll('-','')}  -> bloqueia só WIN (88000..88016)
  JUMBA_DAILY_STOP_WDO    = ${new Date().toISOString().slice(0,10).replaceAll('-','')}  -> bloqueia só WDO (89000..89016)

Integração automática em todos os EAs Jumba:
  - Jumba_SafetyGuard.mqh :: AllowOrder(vol, reduces_only)
      bloqueia aberturas quando IsDailyStopActive() == true,
      mas libera ordens de fechamento (reduces_only = true).
  - Jumba_GEX_NWE_Core.mqh & Jumba_WDO_GEX_NWE_Core.mqh
      forçam encerramento dos slots virtuais + pendentes
      no primeiro tick após o disparo.</pre>
      </div>
      <div class="card">
        <div class="card-title">Justificativa Estatística (${d.label})</div>
        <div class="kv-row"><span>Stop Global Ret/DD</span><span class="c-cyan">${fmtBRL(rs.primary_used)}</span></div>
        <div class="kv-row"><span>Walk-Forward Rolling</span><span class="c-green">${posF}/${(wfa.folds || []).length} folds positivos OOS</span></div>
        <div class="kv-row"><span>Monte Carlo IID (Ret/DD)</span><span class="c-green">Vence em ${fmtPct(mc.wins_rdd / mc.n * 100)} (${mc.wins_rdd}/${mc.n})</span></div>
        <div class="kv-row"><span>Monte Carlo Block 5d (Ret/DD)</span><span class="c-green">Vence em ${fmtPct(d.monte_carlo.block_5d.wins_rdd / d.monte_carlo.block_5d.n * 100)}</span></div>
        <div class="kv-row"><span>Impacto Global Ret/DD</span><span class="c-cyan">${fmt(b.ret_dd)}x → ${fmt(f1.ret_dd)}x</span></div>
        <div class="kv-row"><span>Impacto Combo Ret/DD</span><span class="c-green">${fmt(b.ret_dd)}x → ${fmt(fc.ret_dd)}x (DD ${fmtPct((1 - fc.max_dd / b.max_dd) * 100)})</span></div>
      </div>
    </div>`;
}

function renderContent() {
  const d = curData();
  if (state.tab === 'overview') renderOverview(d);
  else if (state.tab === 'sweep') renderSweep(d);
  else if (state.tab === 'recovery') renderRecovery(d);
  else if (state.tab === 'walkforward') renderWalkForward(d);
  else if (state.tab === 'montecarlo') renderMonteCarlo(d);
  else if (state.tab === 'robots') renderRobots(d);
  else if (state.tab === 'ea') renderEA(d);
}

function renderAll() {
  renderTopbar();
  renderContent();
}

renderAll();
</script>
</body>
</html>
"""


def generate_html_report(
    results_by_preset: dict[str, dict[str, Any]],
    out_path: str | Path,
    default_preset: str = "proposta_b_11",
) -> Path:
    """Gera o dashboard HTML interativo self-contained com todos os presets simulados."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if default_preset not in results_by_preset:
        default_preset = next(iter(results_by_preset))

    payload = {
        "default_preset": default_preset,
        "presets": results_by_preset,
    }
    json_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Evitar fechamento acidental de tag <script> dentro do JSON
    json_str = json_str.replace("</", "<\\/")
    html = _HTML_TEMPLATE.replace("__REPORT_DATA_JSON__", json_str)
    out_path.write_text(html, encoding="utf-8")
    return out_path
