"""Geração de relatório HTML interativo (dark Plotly.js) para a Bateria dos 24 Robôs Não Utilizados."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_html_report(payload: dict[str, Any], out_path: Path) -> Path:
    data_json = json.dumps(payload, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Bateria de Validação & Inclusão — 24 Robôs Não Utilizados</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {{
    --bg: #0b1120; --card: #111827; --card2: #162033; --border: #1f2d45;
    --text: #e2e8f0; --muted: #94a3b8; --green: #22c55e; --yellow: #f59e0b;
    --red: #ef4444; --blue: #38bdf8; --purple: #a78bfa;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: Inter, -apple-system, Segoe UI, Roboto, sans-serif; background: var(--bg); color: var(--text); }}
  .wrap {{ max-width: 1460px; margin: 0 auto; padding: 22px 24px 48px; }}
  h1 {{ margin: 0 0 6px; font-size: 24px; letter-spacing: -0.02em; }}
  .sub {{ color: var(--muted); font-size: 13px; margin-bottom: 18px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 18px; }}
  .kpi {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }}
  .kpi .lbl {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
  .kpi .val {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
  .kpi .subv {{ font-size: 12px; color: var(--muted); margin-top: 3px; }}
  .tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }}
  .tab {{ background: var(--card); color: var(--muted); border: 1px solid var(--border); border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: 13px; font-weight: 600; }}
  .tab.active {{ background: #1d4ed8; color: #fff; border-color: #2563eb; }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 16px; }}
  .card h2 {{ margin: 0 0 10px; font-size: 16px; }}
  .grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(520px, 1fr)); gap: 16px; }}
  .tbl-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }}
  th {{ color: var(--muted); font-weight: 600; background: var(--card2); position: sticky; top: 0; }}
  th:first-child, td:first-child, th.left, td.left {{ text-align: left; }}
  tr:hover td {{ background: rgba(56, 189, 248, 0.06); }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }}
  .b-ok {{ background: rgba(34,197,94,0.16); color: #4ade80; border: 1px solid rgba(34,197,94,0.35); }}
  .b-res {{ background: rgba(245,158,11,0.16); color: #fbbf24; border: 1px solid rgba(245,158,11,0.35); }}
  .b-no {{ background: rgba(239,68,68,0.16); color: #f87171; border: 1px solid rgba(239,68,68,0.35); }}
  .pos {{ color: #4ade80; font-weight: 600; }}
  .neg {{ color: #f87171; font-weight: 600; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11.5px; color: #cbd5e1; }}
  .filters {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; align-items: center; }}
  select {{ background: var(--card2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 12.5px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Bateria de Validação &amp; Inclusão — 24 Robôs Não Utilizados</h1>
  <div class="sub">Base ao vivo: Conta 2004051 (Top 8: EST-04, 07, 13, 14, 15 + WDO-01, 05, 07) · Treino IS: 02/01–31/07/2026 (145d) · Validação Cega OOS: 01/08–06/11/2026 (67d) · Custos B3 reais</div>

  <div class="kpis" id="kpis"></div>

  <div class="tabs">
    <button class="tab active" onclick="openTab('t_bat', this)">1. Bateria 24 Robôs</button>
    <button class="tab" onclick="openTab('t_diff', this)">2. Antes vs Depois</button>
    <button class="tab" onclick="openTab('t_marg', this)">3. Inclusão 1-a-1 no Top 8</button>
    <button class="tab" onclick="openTab('t_step', this)">4. Expansão Stepwise &amp; Equity</button>
  </div>

  <div id="t_bat" class="panel active">
    <div class="card">
      <h2>Ranking dos 24 Robôs Não Utilizados (Seleção 100% IS → Validação Cega OOS + 5 Gates)</h2>
      <div class="filters">
        <label>Ativo: <select id="fAsset" onchange="renderBatTable()"><option value="ALL">Todos</option><option value="WIN">WIN</option><option value="WDO">WDO</option></select></label>
        <label>Veredito: <select id="fVerd" onchange="renderBatTable()"><option value="ALL">Todos</option><option value="APROVADO">APROVADO</option><option value="RESERVA">RESERVA</option><option value="REPROVADO">REPROVADO</option></select></label>
      </div>
      <div class="tbl-wrap"><table id="tblBat"></table></div>
    </div>
  </div>

  <div id="t_diff" class="panel">
    <div class="grid2">
      <div class="card"><h2>Ret/DD: Original vs Ajustado (IS → Full 2026)</h2><div id="chDiffRetDD" style="height:460px"></div></div>
      <div class="card"><h2>Validação Cega OOS (Ago–Nov): Lucro Líquido Ajustado</h2><div id="chOosNet" style="height:460px"></div></div>
    </div>
  </div>

  <div id="t_marg" class="panel">
    <div class="card">
      <h2>Impacto Marginal 1-a-1 sobre Top 8 (Motor M1 Real · Stop Live G850 + W400 + D550)</h2>
      <div class="tbl-wrap"><table id="tblMarg"></table></div>
    </div>
    <div class="grid2">
      <div class="card"><h2>Correlação com Top 8 vs Ganho de Ret/DD (Stop Live)</h2><div id="chScatter" style="height:400px"></div></div>
      <div class="card"><h2>PnL dos Candidatos nos 15 Piores Dias do Top 8</h2><div id="chWorst15" style="height:400px"></div></div>
    </div>
  </div>

  <div id="t_step" class="panel">
    <div class="card">
      <h2>Expansão Forward Stepwise (Aprovados · Guiada no IS → Validada no OOS Cego · Stop Live G850/W400/D550)</h2>
      <div class="tbl-wrap"><table id="tblStep"></table></div>
    </div>
    <div class="grid2">
      <div class="card"><h2>Ret/DD Full vs OOS Cego por Nº de Robôs</h2><div id="chStepMetric" style="height:380px"></div></div>
      <div class="card"><h2>Curvas de Equity M1 (Base Top 8 vs Melhor Expansão)</h2><div id="chEquity" style="height:380px"></div></div>
    </div>
  </div>
</div>

<script>
const DATA = {data_json};
const fmtBRL = (v, s=false) => {{
  const sign = s && v > 0 ? '+' : (v < 0 ? '-' : '');
  return sign + 'R$ ' + Math.abs(Math.round(v)).toLocaleString('pt-BR');
}};
const badge = v => v === 'APROVADO' ? '<span class="badge b-ok">APROVADO</span>' : (v === 'RESERVA' ? '<span class="badge b-res">RESERVA</span>' : '<span class="badge b-no">REPROVADO</span>');
const gatePills = g => [['IS','G1_IS'],['OOS','G2_OOS_BLIND'],['2Sem','G3_BOTH_HALVES'],['Mes','G4_MONTHLY'],['Str','G5_COST_STRESS']]
  .map(([lbl,k]) => `<span style="color:${{g[k]?'#4ade80':'#f87171'}};margin-right:5px">${{g[k]?'✓':'✗'}}${{lbl}}</span>`).join('');

function openTab(id, btn) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
  setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
}}

// KPIs
const bat = DATA.battery;
const nAp = bat.filter(r => r.best_is.verdict === 'APROVADO').length;
const nRes = bat.filter(r => r.best_is.verdict === 'RESERVA').length;
const nBaseAp = bat.filter(r => r.baseline.verdict === 'APROVADO').length;
const baseStop = DATA.inclusion.base_eval.stop_live_850;
const steps = DATA.inclusion.greedy_approved_stop;
const bestStep = steps.reduce((a, b) => (b.stop_live_850.ret_dd > a.stop_live_850.ret_dd ? b : a), steps[0]);

document.getElementById('kpis').innerHTML = [
  ['Robôs Testados', `${{bat.length}}`, '11 WIN + 13 WDO fora do Top 8'],
  ['Aprovados (5/5 Gates)', `<span class="pos">${{nAp}}</span>`, `Antes dos ajustes: ${{nBaseAp}} | Reservas: ${{nRes}}`],
  ['Base Top 8 (Stop Live)', `${{baseStop.ret_dd.toFixed(2)}}x`, `${{fmtBRL(baseStop.ret, true)}} | DD ${{fmtBRL(baseStop.max_dd)}} | OOS ${{baseStop.oos_chron.ret_dd.toFixed(2)}}x`],
  ['Melhor Stepwise (Stop Live)', `<span class="pos">${{bestStep.stop_live_850.ret_dd.toFixed(2)}}x</span> (${{bestStep.n_robots}} robôs)`, `${{fmtBRL(bestStep.stop_live_850.ret, true)}} | DD ${{fmtBRL(bestStep.stop_live_850.max_dd)}} | OOS ${{bestStep.stop_live_850.oos_chron.ret_dd.toFixed(2)}}x`],
].map(([l,v,s]) => `<div class="kpi"><div class="lbl">${{l}}</div><div class="val">${{v}}</div><div class="subv">${{s}}</div></div>`).join('');

function renderBatTable() {{
  const fa = document.getElementById('fAsset').value;
  const fv = document.getElementById('fVerd').value;
  const ord = {{APROVADO:0, RESERVA:1, REPROVADO:2}};
  const rows = bat
    .filter(r => (fa==='ALL' || r.asset===fa) && (fv==='ALL' || r.best_is.verdict===fv))
    .sort((a,b) => (ord[a.best_is.verdict]-ord[b.best_is.verdict]) || (b.best_is.gates_passed-a.best_is.gates_passed) || (b.best_is.full.ret_dd-a.best_is.full.ret_dd));

  let h = `<thead><tr>
    <th>Robô</th><th class="left">Veredito</th><th class="left">5 Gates</th><th class="left">Ajuste (100% IS)</th>
    <th>Base Ret/DD</th><th>Ajust. Ret/DD</th><th>Líq. 2026</th><th>DD Dia</th><th>PF</th><th>Trades</th>
    <th>IS Ret/DD</th><th>OOS Cego</th><th>OOS PF</th><th>Stress PF</th><th>Meses+</th><th>Platô IS</th>
  </tr></thead><tbody>`;
  for (const r of rows) {{
    const b = r.baseline, o = r.best_is;
    h += `<tr>
      <td><b>${{r.code}}</b> <span class="mono">${{r.asset}} ${{r.tf}}</span></td>
      <td class="left">${{badge(o.verdict)}}</td>
      <td class="left">${{gatePills(o.gates)}}</td>
      <td class="left mono">${{o.label}}</td>
      <td>${{b.full.ret_dd.toFixed(2)}}x</td>
      <td class="${{o.full.ret_dd >= b.full.ret_dd ? 'pos':'neg'}}">${{o.full.ret_dd.toFixed(2)}}x</td>
      <td class="${{o.full.net>=0?'pos':'neg'}}">${{fmtBRL(o.full.net, true)}}</td>
      <td>${{fmtBRL(o.full.dd_day)}}</td>
      <td>${{o.full.pf.toFixed(2)}}</td>
      <td>${{o.full.trades}}</td>
      <td>${{o.is.ret_dd.toFixed(2)}}x</td>
      <td class="${{o.oos.net>=0?'pos':'neg'}}">${{fmtBRL(o.oos.net, true)}}</td>
      <td>${{o.oos.pf.toFixed(2)}}</td>
      <td>${{o.stress.pf.toFixed(2)}}</td>
      <td>${{o.full.pos_months}}/${{o.full.total_months}}</td>
      <td>${{r.plateau_pct.toFixed(0)}}%</td>
    </tr>`;
  }}
  document.getElementById('tblBat').innerHTML = h + '</tbody>';
}}
renderBatTable();

// Charts Tab 2
const layoutBase = {{ paper_bgcolor:'#111827', plot_bgcolor:'#0b1120', font:{{color:'#e2e8f0', size:11}}, margin:{{t:20,r:20,b:85,l:55}}, xaxis:{{gridcolor:'#1f2d45'}}, yaxis:{{gridcolor:'#1f2d45'}} }};
const sortedByRetDD = [...bat].sort((a,b) => b.best_is.full.ret_dd - a.best_is.full.ret_dd);
Plotly.newPlot('chDiffRetDD', [
  {{ x: sortedByRetDD.map(r=>r.code), y: sortedByRetDD.map(r=>r.baseline.full.ret_dd), name:'Original', type:'bar', marker:{{color:'#475569'}} }},
  {{ x: sortedByRetDD.map(r=>r.code), y: sortedByRetDD.map(r=>r.best_is.full.ret_dd), name:'Ajustado (IS)', type:'bar', marker:{{color: sortedByRetDD.map(r=>r.best_is.verdict==='APROVADO'?'#22c55e':(r.best_is.verdict==='RESERVA'?'#f59e0b':'#ef4444'))}} }},
], {{...layoutBase, barmode:'group', yaxis:{{title:'Ret/DD 2026', gridcolor:'#1f2d45'}}}}, {{responsive:true}});

const sortedByOos = [...bat].sort((a,b) => b.best_is.oos.net - a.best_is.oos.net);
Plotly.newPlot('chOosNet', [
  {{ x: sortedByOos.map(r=>r.code), y: sortedByOos.map(r=>r.best_is.oos.net), type:'bar',
     marker:{{color: sortedByOos.map(r=>r.best_is.verdict==='APROVADO'?'#22c55e':(r.best_is.verdict==='RESERVA'?'#f59e0b':'#ef4444'))}} }}
], {{...layoutBase, yaxis:{{title:'Líquido OOS Cego Ago–Nov (R$)', gridcolor:'#1f2d45'}}}}, {{responsive:true}});

// Tab 3 Marginal
const marg = DATA.inclusion.marginal;
let mh = `<thead><tr>
  <th>Candidato</th><th class="left">Veredito</th><th class="left">Ajuste</th><th>Corr Top8</th><th>Corr Ativo</th>
  <th>PnL Piores 15d</th><th>ΔRet (Stop)</th><th>ΔDD (Stop)</th><th>Ret/DD (Stop)</th><th>ΔRet/DD</th><th>ΔOOS Ret/DD</th><th>Ret/DD (Sem Stop)</th>
</tr></thead><tbody>`;
for (const m of marg) {{
  const s = m.stop_live_850, n = m.no_stop;
  mh += `<tr>
    <td><b>${{m.key}}</b> <span class="mono">${{m.asset}}</span></td>
    <td class="left">${{badge(m.verdict)}}</td>
    <td class="left mono">${{m.label}}</td>
    <td>${{m.corr_all.toFixed(2)}}</td>
    <td>${{m.corr_asset.toFixed(2)}}</td>
    <td class="${{m.pnl_on_top8_worst15>=0?'pos':'neg'}}">${{fmtBRL(m.pnl_on_top8_worst15, true)}}</td>
    <td class="${{s.d_ret>=0?'pos':'neg'}}">${{fmtBRL(s.d_ret, true)}}</td>
    <td class="${{s.d_dd<=0?'pos':'neg'}}">${{fmtBRL(s.d_dd, true)}}</td>
    <td><b>${{s.ret_dd.toFixed(2)}}x</b></td>
    <td class="${{s.d_ret_dd>=0?'pos':'neg'}}">${{s.d_ret_dd>=0?'+':''}}${{s.d_ret_dd.toFixed(2)}}x</td>
    <td class="${{s.d_oos_ret_dd>=0?'pos':'neg'}}">${{s.d_oos_ret_dd>=0?'+':''}}${{s.d_oos_ret_dd.toFixed(2)}}x</td>
    <td>${{n.ret_dd.toFixed(2)}}x (${{n.d_ret_dd>=0?'+':''}}${{n.d_ret_dd.toFixed(2)}}x)</td>
  </tr>`;
}}
document.getElementById('tblMarg').innerHTML = mh + '</tbody>';

if (marg.length) {{
  Plotly.newPlot('chScatter', [{{
    x: marg.map(m=>m.corr_all), y: marg.map(m=>m.stop_live_850.d_ret_dd), text: marg.map(m=>m.key),
    mode:'markers+text', textposition:'top center',
    marker:{{size:11, color: marg.map(m=>m.verdict==='APROVADO'?'#22c55e':'#f59e0b')}}
  }}], {{...layoutBase, xaxis:{{title:'Correlação Diária com Top 8', gridcolor:'#1f2d45'}}, yaxis:{{title:'Δ Ret/DD (Stop Live)', gridcolor:'#1f2d45'}}}}, {{responsive:true}});

  Plotly.newPlot('chWorst15', [{{
    x: marg.map(m=>m.key), y: marg.map(m=>m.pnl_on_top8_worst15), type:'bar',
    marker:{{color: marg.map(m=>m.pnl_on_top8_worst15>=0?'#22c55e':'#ef4444')}}
  }}], {{...layoutBase, yaxis:{{title:'PnL nos 15 Piores Dias do Top 8 (R$)', gridcolor:'#1f2d45'}}}}, {{responsive:true}});
}}

// Tab 4 Stepwise
let sh = `<thead><tr>
  <th>Passo</th><th>Nº Robôs</th><th class="left">Adicionado</th><th class="left">Ajuste</th>
  <th>Retorno 2026</th><th>Max DD</th><th>Ret/DD</th><th>Sharpe</th><th>IS Ret/DD</th><th>OOS Cego Ret/DD</th><th>OOS Cego Líq.</th><th>Cortados</th>
</tr></thead><tbody>`;
for (const s of steps) {{
  const m = s.stop_live_850;
  sh += `<tr>
    <td>${{s.step}}</td><td><b>${{s.n_robots}}</b></td><td class="left"><b>${{s.added}}</b></td><td class="left mono">${{s.added_label}}</td>
    <td class="pos">${{fmtBRL(m.ret, true)}}</td><td>${{fmtBRL(m.max_dd)}}</td><td><b>${{m.ret_dd.toFixed(2)}}x</b></td>
    <td>${{m.sharpe.toFixed(2)}}</td><td>${{m.is_chron.ret_dd.toFixed(2)}}x</td>
    <td class="pos"><b>${{m.oos_chron.ret_dd.toFixed(2)}}x</b></td><td>${{fmtBRL(m.oos_chron.ret, true)}}</td><td>${{m.stopped}}</td>
  </tr>`;
}}
document.getElementById('tblStep').innerHTML = sh + '</tbody>';

Plotly.newPlot('chStepMetric', [
  {{ x: steps.map(s=>s.n_robots), y: steps.map(s=>s.stop_live_850.ret_dd), name:'Ret/DD Full 2026', mode:'lines+markers', line:{{color:'#38bdf8', width:3}} }},
  {{ x: steps.map(s=>s.n_robots), y: steps.map(s=>s.stop_live_850.is_chron.ret_dd), name:'IS (Jan–Jul)', mode:'lines+markers', line:{{color:'#a78bfa', dash:'dot'}} }},
  {{ x: steps.map(s=>s.n_robots), y: steps.map(s=>s.stop_live_850.oos_chron.ret_dd), name:'OOS Cego (Ago–Nov)', mode:'lines+markers', line:{{color:'#22c55e', width:3}} }},
], {{...layoutBase, xaxis:{{title:'Número de Robôs', dtick:1, gridcolor:'#1f2d45'}}, yaxis:{{title:'Ret/DD', gridcolor:'#1f2d45'}}}}, {{responsive:true}});

const eqTraces = [
  {{ x: steps[0].curve_stop_live_850.map(c=>c.date), y: steps[0].curve_stop_live_850.map(c=>c.equity), name:`Base Top 8 (${{steps[0].stop_live_850.ret_dd.toFixed(2)}}x)`, mode:'lines', line:{{color:'#94a3b8', width:2}} }},
];
if (bestStep.step > 0) {{
  eqTraces.push({{ x: bestStep.curve_stop_live_850.map(c=>c.date), y: bestStep.curve_stop_live_850.map(c=>c.equity), name:`Melhor Stepwise ${{bestStep.n_robots}} Robôs (${{bestStep.stop_live_850.ret_dd.toFixed(2)}}x)`, mode:'lines', line:{{color:'#22c55e', width:3}} }});
}}
Plotly.newPlot('chEquity', eqTraces, {{
  ...layoutBase,
  shapes:[{{type:'line', x0:'2026-08-01', x1:'2026-08-01', y0:0, y1:1, yref:'paper', line:{{color:'#f59e0b', dash:'dash', width:1.5}}}}],
  annotations:[{{x:'2026-08-01', y:0.96, yref:'paper', text:'OOS Cego →', showarrow:false, font:{{color:'#f59e0b', size:11}}, xanchor:'left'}}],
  yaxis:{{title:'Equity Acumulado (R$)', gridcolor:'#1f2d45'}}
}}, {{responsive:true}});
</script>
</body>
</html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
