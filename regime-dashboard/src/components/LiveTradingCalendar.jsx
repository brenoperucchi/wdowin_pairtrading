import { useMemo, useState } from "react";

// Operações vêm do próprio dashboard: compassData.portfolio_4_sistematicas (/api/compass/etapa1)
const STRATS = {
    EST_01: { code: "EST-01", name: "WIN Rejeição" },
    EST_07: { code: "EST-07", name: "WIN Rompimento" },
    EST_13: { code: "EST-13", name: "WIN Next Wall" },
    WDO_09: { code: "WDO-09", name: "WDO Pullback" },
    WDO_11: { code: "WDO-11", name: "WDO Next Wall" },
    WDO_S2: { code: "WDO-S2", name: "WDO Lunch" },
};
const COST_PER_CTR = { WIN: 2.0, WDO: 5.0 }; // custo estimado do projeto (R$/contrato)

const C = {
    bg: "#0c1218", card: "#111c24", cardHi: "#14222c", border: "#1c2e3a", dim: "#3a5060", txt: "#cdd8de",
    mute: "#5a7080", green: "#00e87a", red: "#ff3860", blue: "#3aa0ff", gold: "#c8a444", win: "#3aa0ff", wdo: "#c8a444",
};
const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex"];
const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

const brl = (v, dec = 0) => {
    const n = Number(v || 0);
    const s = Math.abs(n).toLocaleString("pt-BR", { minimumFractionDigits: dec, maximumFractionDigits: dec });
    return `${n < 0 ? "−" : n > 0 ? "+" : ""}R$ ${s}`;
};
const pnlColor = (v) => (v > 0.001 ? C.green : v < -0.001 ? C.red : C.mute);
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function stats(trades, key) {
    const n = trades.length;
    let gw = 0, gl = 0, w = 0, l = 0, lots = 0;
    for (const t of trades) {
        const v = t[key];
        lots += t.lots;
        if (v > 0.001) { w++; gw += v; } else if (v < -0.001) { l++; gl += -v; }
    }
    return {
        n, w, l, lots, net: gw - gl,
        wr: n ? (100 * w) / n : 0,
        pf: gl > 0 ? gw / gl : gw > 0 ? Infinity : 0,
    };
}
const fmtPf = (pf) => (pf === Infinity ? "∞" : pf.toFixed(2));

function Kpi({ label, value, sub, color }) {
    return (
        <div style={{ flex: 1, minWidth: 130, background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 14px" }}>
            <div style={{ fontSize: 8, color: C.dim, letterSpacing: 1.5, fontWeight: "bold", marginBottom: 6 }}>{label}</div>
            <div style={{ fontSize: 18, fontWeight: "bold", color: color || C.txt }}>{value}</div>
            {sub && <div style={{ fontSize: 9, color: C.mute, marginTop: 4 }}>{sub}</div>}
        </div>
    );
}

function Toggle({ options, value, onChange }) {
    return (
        <div style={{ display: "flex", background: C.bg, border: `1px solid ${C.border}`, borderRadius: 999, padding: 2 }}>
            {options.map(([v, label]) => (
                <button key={v} onClick={() => onChange(v)} style={{
                    border: "none", cursor: "pointer", borderRadius: 999, padding: "4px 12px", fontSize: 9, fontWeight: "bold",
                    letterSpacing: 1, background: value === v ? C.blue : "transparent", color: value === v ? "#fff" : C.mute,
                }}>{label}</button>
            ))}
        </div>
    );
}

export default function LiveTradingCalendar({ portfolioData, onSelectDate }) {
    const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
    const [asset, setAsset] = useState("ALL");        // ALL | WIN | WDO
    const [scope, setScope] = useState("LIVE");       // LIVE (só pregões live) | ALL (BT auditado + live)
    const [pnlKey, setPnlKey] = useState("pnl");      // pnl (bruto) | pnl_est_cost (c/ custo estimado)
    const [winCtr, setWinCtr] = useState(2);          // mesmo padrão do painel de portfólio (WIN 2 / WDO 1)
    const [wdoCtr, setWdoCtr] = useState(1);
    const [selDay, setSelDay] = useState(ymd(new Date()));

    const ok = Boolean(portfolioData?.ok && Array.isArray(portfolioData.days));
    const liveStart = portfolioData?.live_start_date || "";

    // Normaliza as operações contabilizadas pelo dashboard (portfolio_4_sistematicas)
    const { allTrades, openTrades } = useMemo(() => {
        const closed = [], open = [];
        if (!ok) return { allTrades: closed, openTrades: open };
        portfolioData.days.forEach((d) => {
            const isLive = Boolean(d.is_live);
            const norm = (tr, i) => {
                const lots = tr.asset === "WIN" ? winCtr : wdoCtr;
                const gross = Number(tr.brl_1c || 0) * lots;
                const meta = STRATS[tr.strategy_id] || { code: tr.strategy_id, name: tr.type || tr.strategy_id };
                return {
                    id: `${d.date}-${tr.strategy_id}-${tr.time}-${i}`,
                    date: tr.date || d.date, is_live: isLive, robot: meta.code, name: meta.name, asset: tr.asset,
                    side: tr.direction === "COMPRA" ? 1 : -1, lots, t_in: tr.time, t_out: tr.exit_time,
                    px_in: tr.entry_price, px_out: tr.exit_price, pts: tr.pts, reason: tr.label || tr.status,
                    pnl: gross, pnl_est_cost: gross - (COST_PER_CTR[tr.asset] || 0) * lots,
                };
            };
            (d.trades || []).forEach((tr, i) => closed.push(norm(tr, i)));
            if (isLive) (d.open_trades || []).forEach((tr, i) => open.push(norm(tr, i)));
        });
        return { allTrades: closed, openTrades: open };
    }, [ok, portfolioData, winCtr, wdoCtr]);

    const trades = useMemo(() => allTrades.filter((t) =>
        (asset === "ALL" || t.asset === asset) && (scope === "ALL" || t.is_live)
    ), [allTrades, asset, scope]);

    const byDay = useMemo(() => {
        const m = {};
        for (const t of trades) (m[t.date] ||= []).push(t);
        return m;
    }, [trades]);

    // ── Grade do mês (seg–sex) ────────────────────────────────────────────────
    const weeks = useMemo(() => {
        const y = month.getFullYear(), mo = month.getMonth();
        const first = new Date(y, mo, 1);
        const start = new Date(first);
        const dow = (first.getDay() + 6) % 7; // 0 = seg
        start.setDate(first.getDate() - dow);
        const out = [];
        const cur = new Date(start);
        while (true) {
            const wk = [];
            for (let i = 0; i < 7; i++) {
                if (i < 5) wk.push(new Date(cur));
                cur.setDate(cur.getDate() + 1);
            }
            if (wk.some((d) => d.getMonth() === mo)) out.push(wk);
            if (cur.getMonth() !== mo && cur > first) break;
        }
        return out;
    }, [month]);

    const monthKey = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}`;
    const monthTrades = useMemo(() => trades.filter((t) => t.date.startsWith(monthKey)), [trades, monthKey]);
    const ms = stats(monthTrades, pnlKey);

    const dayRows = useMemo(() => {
        const days = {};
        for (const t of monthTrades) days[t.date] = (days[t.date] || 0) + t[pnlKey];
        const keys = Object.keys(days).sort();
        let cum = 0, peak = 0, dd = 0;
        for (const k of keys) { cum += days[k]; peak = Math.max(peak, cum); dd = Math.max(dd, peak - cum); }
        const vals = keys.map((k) => days[k]);
        return {
            n: keys.length, pos: vals.filter((v) => v > 0.001).length,
            best: keys.length ? Math.max(...vals) : 0, worst: keys.length ? Math.min(...vals) : 0, dd,
            bestDay: keys.find((k) => days[k] === Math.max(...vals)), worstDay: keys.find((k) => days[k] === Math.min(...vals)),
        };
    }, [monthTrades, pnlKey]);

    const winNet = stats(monthTrades.filter((t) => t.asset === "WIN"), pnlKey).net;
    const wdoNet = stats(monthTrades.filter((t) => t.asset === "WDO"), pnlKey).net;

    const openPos = openTrades.filter((p) => asset === "ALL" || p.asset === asset);

    const selTrades = useMemo(() => byDay[selDay] || [], [byDay, selDay]);
    const selRobots = useMemo(() => {
        const m = {};
        for (const t of selTrades) (m[t.robot] ||= []).push(t);
        return Object.entries(m).map(([robot, ts]) => ({ robot, asset: ts[0].asset, name: ts[0].name, ...stats(ts, pnlKey) }))
            .sort((a, b) => b.net - a.net);
    }, [selTrades, pnlKey]);

    const monthRobots = useMemo(() => {
        const m = {};
        for (const t of monthTrades) (m[t.robot] ||= []).push(t);
        return Object.entries(m).map(([robot, ts]) => ({
            robot, asset: ts[0].asset, name: ts[0].name,
            days: new Set(ts.map((x) => x.date)).size, ...stats(ts, pnlKey),
        })).sort((a, b) => b.net - a.net);
    }, [monthTrades, pnlKey]);

    const todayStr = ymd(new Date());
    const shiftMonth = (k) => setMonth(new Date(month.getFullYear(), month.getMonth() + k, 1));

    return (
        <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 10, padding: 16, marginTop: 12 }}>
            {/* Cabeçalho */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 10, borderBottom: `1px solid ${C.border}`, paddingBottom: 10, marginBottom: 12 }}>
                <div>
                    <div style={{ fontSize: 12, fontWeight: "bold", color: C.txt, letterSpacing: 2 }}>📅 CALENDÁRIO DO LIVE TRADING</div>
                    <div style={{ fontSize: 9, color: C.mute, marginTop: 3 }}>
                        Resultado diário e robôs que operaram · mesmas operações do Portfólio das 6 Estratégias c/ Fluxo
                        {liveStart && <> · 🟢 live desde {liveStart.split("-").reverse().join("/")}</>}
                        {!ok && <span style={{ color: C.red }}> · aguardando dados do /api/compass/etapa1</span>}
                    </div>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                    <Toggle options={[["ALL", "WIN+WDO"], ["WIN", "WIN"], ["WDO", "WDO"]]} value={asset} onChange={setAsset} />
                    <Toggle options={[["LIVE", "SÓ LIVE"], ["ALL", "BT + LIVE"]]} value={scope} onChange={setScope} />
                    <Toggle options={[["pnl", "BRUTO"], ["pnl_est_cost", "C/ CUSTO EST."]]} value={pnlKey} onChange={setPnlKey} />
                    {[["WIN", winCtr, setWinCtr, C.win], ["WDO", wdoCtr, setWdoCtr, C.wdo]].map(([lbl, v, setV, col]) => (
                        <label key={lbl} style={{ fontSize: 9, color: col, fontWeight: "bold", display: "flex", alignItems: "center", gap: 4 }}>
                            {lbl}
                            <select value={v} onChange={(e) => setV(Number(e.target.value))}
                                style={{ background: C.bg, color: C.txt, border: `1px solid ${C.border}`, borderRadius: 6, fontSize: 9, padding: "2px 4px" }}>
                                {[1, 2, 3, 4, 5, 10].map((n) => <option key={n} value={n}>{n} ctr</option>)}
                            </select>
                        </label>
                    ))}
                </div>
            </div>

            {/* KPIs do mês */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                <Kpi label="RESULTADO DO MÊS" value={brl(ms.net)} color={pnlColor(ms.net)}
                    sub={<><span style={{ color: C.win }}>WIN {brl(winNet)}</span> · <span style={{ color: C.wdo }}>WDO {brl(wdoNet)}</span></>} />
                <Kpi label="TRADES / CONTRATOS" value={`${ms.n} / ${ms.lots}`} sub={`${ms.w} ganhos · ${ms.l} perdas`} />
                <Kpi label="WIN RATE · PF" value={`${ms.wr.toFixed(0)}% · ${fmtPf(ms.pf)}`} color={ms.pf >= 1 ? C.green : ms.n ? C.red : C.txt} />
                <Kpi label="DIAS POSITIVOS" value={`${dayRows.pos} / ${dayRows.n}`} sub={dayRows.n ? `${((100 * dayRows.pos) / dayRows.n).toFixed(0)}% dos dias operados` : "—"} />
                <Kpi label="MELHOR · PIOR DIA" value={<><span style={{ color: pnlColor(dayRows.best) }}>{brl(dayRows.best)}</span> <span style={{ color: C.dim }}>·</span> <span style={{ color: pnlColor(dayRows.worst) }}>{brl(dayRows.worst)}</span></>}
                    sub={dayRows.n ? `${dayRows.bestDay?.slice(8)} · ${dayRows.worstDay?.slice(8)}` : "—"} />
                <Kpi label="DRAWDOWN DO MÊS" value={dayRows.dd > 0 ? `R$ ${dayRows.dd.toFixed(0)}` : "R$ 0"} color={dayRows.dd > 0 ? C.red : C.txt} sub="pico→vale do acumulado diário" />
                <Kpi label="EM ABERTO AGORA" value={openPos.length ? `${openPos.length} posição${openPos.length > 1 ? "ões" : ""}` : "—"} color={openPos.length ? "#ffd600" : C.txt}
                    sub={openPos.length ? openPos.map((p) => `${p.robot} ${p.side > 0 ? "C" : "V"} ${p.px_in}`).join(" · ") : "sem posições"} />
            </div>

            {/* Navegação */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ display: "flex", gap: 6 }}>
                    {[["‹", -1], ["›", 1]].map(([s, k]) => (
                        <button key={s} onClick={() => shiftMonth(k)} style={{ background: C.card, color: C.txt, border: `1px solid ${C.border}`, borderRadius: 6, width: 30, height: 26, cursor: "pointer" }}>{s}</button>
                    ))}
                    <button onClick={() => { const d = new Date(); setMonth(new Date(d.getFullYear(), d.getMonth(), 1)); setSelDay(todayStr); }}
                        style={{ background: C.card, color: C.mute, border: `1px solid ${C.border}`, borderRadius: 6, padding: "0 10px", height: 26, cursor: "pointer", fontSize: 9 }}>HOJE</button>
                </div>
                <div style={{ fontSize: 14, fontWeight: "bold", color: C.txt, textTransform: "capitalize" }}>{MONTHS[month.getMonth()]} de {month.getFullYear()}</div>
                <div style={{ fontSize: 9, color: C.mute }}>{ms.w} ganhos · {ms.l} perdas</div>
            </div>

            {/* Grade */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr) 1.15fr", gap: 6 }}>
                {WEEKDAYS.map((w) => <div key={w} style={{ fontSize: 9, color: C.dim, fontWeight: "bold", padding: "0 4px" }}>{w}</div>)}
                <div style={{ fontSize: 9, color: C.dim, fontWeight: "bold", padding: "0 4px" }}>Semana</div>
                {weeks.map((wk, wi) => {
                    const wkTrades = wk.flatMap((d) => (d.getMonth() === month.getMonth() ? byDay[ymd(d)] || [] : []));
                    const ws = stats(wkTrades, pnlKey);
                    return [
                        ...wk.map((d) => {
                            const k = ymd(d);
                            const inMonth = d.getMonth() === month.getMonth();
                            const ts = byDay[k] || [];
                            const s = stats(ts, pnlKey);
                            const robots = new Set(ts.map((t) => t.robot));
                            const isSel = k === selDay, isToday = k === todayStr;
                            const isLiveDay = liveStart && k >= liveStart;
                            const tint = !inMonth || !s.n ? C.card : s.net > 0.001 ? "rgba(0,232,122,0.08)" : s.net < -0.001 ? "rgba(255,56,96,0.08)" : C.card;
                            return (
                                <div key={k} onClick={() => inMonth && setSelDay(k)} style={{
                                    background: tint, opacity: inMonth ? 1 : 0.3, minHeight: 74, borderRadius: 8, padding: "6px 8px",
                                    border: `1px solid ${isSel ? C.blue : s.n ? (s.net >= 0 ? "rgba(0,232,122,0.35)" : "rgba(255,56,96,0.35)") : C.border}`,
                                    cursor: inMonth ? "pointer" : "default", display: "flex", flexDirection: "column", justifyContent: "space-between",
                                }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                        <span style={{
                                            fontSize: 10, fontWeight: "bold", color: isToday ? "#fff" : C.txt,
                                            background: isToday ? C.blue : "transparent", borderRadius: 999, padding: isToday ? "1px 6px" : 0,
                                        }}>{d.getDate()}</span>
                                        {s.n > 0 ? <span style={{ fontSize: 8, color: C.mute }}>{robots.size} robô{robots.size > 1 ? "s" : ""}</span>
                                            : (inMonth && scope === "ALL" && isLiveDay ? <span style={{ fontSize: 8, color: C.green }}>live</span> : null)}
                                        {s.n > 0 && scope === "ALL" && <span title={isLiveDay ? "Live trading" : "Backtest auditado"} style={{ fontSize: 7, color: isLiveDay ? C.green : C.dim }}>{isLiveDay ? "● LIVE" : "BT"}</span>}
                                    </div>
                                    <div style={{ textAlign: "center", fontSize: 13, fontWeight: "bold", color: s.n ? pnlColor(s.net) : C.dim }}>
                                        {s.n ? brl(s.net) : "—"}
                                    </div>
                                    <div style={{ fontSize: 8, color: C.mute, textAlign: "center" }}>
                                        {s.n ? `${s.n} trade${s.n > 1 ? "s" : ""} · ${s.w}W/${s.l}L` : inMonth ? "sem trades" : ""}
                                    </div>
                                </div>
                            );
                        }),
                        <div key={`w${wi}`} style={{ background: C.cardHi, border: `1px solid ${C.border}`, borderRadius: 8, padding: "6px 10px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                            <div style={{ fontSize: 9, color: C.mute, fontWeight: "bold" }}>Semana {wi + 1}</div>
                            <div style={{ fontSize: 14, fontWeight: "bold", color: ws.n ? pnlColor(ws.net) : C.dim }}>{ws.n ? brl(ws.net) : "R$ 0"}</div>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 8, color: C.mute }}>
                                <span>{ws.n} trades</span>
                                <span style={{ border: `1px solid ${C.border}`, borderRadius: 999, padding: "1px 6px", color: C.blue }}>{ws.wr.toFixed(0)}% WR · PF {fmtPf(ws.pf)}</span>
                            </div>
                        </div>,
                    ];
                })}
            </div>

            {/* Detalhe do dia + ranking do mês */}
            <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 12, marginTop: 14 }}>
                <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, padding: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                        <span style={{ fontSize: 10, fontWeight: "bold", color: C.txt, letterSpacing: 1 }}>
                            ROBÔS QUE OPERARAM · {selDay.split("-").reverse().join("/")}
                        </span>
                        <span style={{ fontSize: 11, fontWeight: "bold", color: pnlColor(stats(selTrades, pnlKey).net) }}>{brl(stats(selTrades, pnlKey).net, 2)}</span>
                    </div>
                    {selRobots.length === 0 ? (
                        <div style={{ fontSize: 10, color: C.mute, padding: "12px 0" }}>Nenhum trade fechado neste dia.</div>
                    ) : (
                        <>
                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
                                <thead><tr style={{ color: C.dim, fontSize: 8, textAlign: "left" }}>
                                    <th>ROBÔ</th><th>ESTRATÉGIA</th><th style={{ textAlign: "right" }}>TRADES</th><th style={{ textAlign: "right" }}>W/L</th><th style={{ textAlign: "right" }}>CTR</th><th style={{ textAlign: "right" }}>RESULTADO</th>
                                </tr></thead>
                                <tbody>{selRobots.map((r) => (
                                    <tr key={r.robot} style={{ borderTop: `1px solid ${C.border}` }}>
                                        <td style={{ padding: "4px 0", fontWeight: "bold", color: r.asset === "WIN" ? C.win : C.wdo }}>{r.robot}</td>
                                        <td style={{ color: C.mute }}>{r.name}</td>
                                        <td style={{ textAlign: "right", color: C.txt }}>{r.n}</td>
                                        <td style={{ textAlign: "right", color: C.mute }}>{r.w}/{r.l}</td>
                                        <td style={{ textAlign: "right", color: C.mute }}>{r.lots}</td>
                                        <td style={{ textAlign: "right", fontWeight: "bold", color: pnlColor(r.net) }}>{brl(r.net, 2)}</td>
                                    </tr>
                                ))}</tbody>
                            </table>
                            <div style={{ fontSize: 8, color: C.dim, letterSpacing: 1, margin: "12px 0 4px" }}>TRADES DO DIA</div>
                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 9 }}>
                                <thead><tr style={{ color: C.dim, fontSize: 8, textAlign: "left" }}>
                                    <th>ENTRADA</th><th>SAÍDA</th><th>ROBÔ</th><th>LADO</th><th style={{ textAlign: "right" }}>CTR</th><th style={{ textAlign: "right" }}>PREÇO E→S</th><th style={{ textAlign: "right" }}>PTS</th><th>DESFECHO</th><th style={{ textAlign: "right" }}>R$</th>
                                </tr></thead>
                                <tbody>{[...selTrades].sort((a, b) => String(a.t_in).localeCompare(String(b.t_in))).map((t) => (
                                    <tr key={t.id} onClick={() => onSelectDate && onSelectDate(t.date)} title="Abrir este pregão no gráfico"
                                        style={{ borderTop: `1px solid ${C.border}`, color: C.mute, cursor: onSelectDate ? "pointer" : "default" }}>
                                        <td style={{ padding: "3px 0" }}>{t.t_in}</td>
                                        <td>{t.t_out}</td>
                                        <td style={{ color: t.asset === "WIN" ? C.win : C.wdo, fontWeight: "bold" }}>{t.robot}</td>
                                        <td style={{ color: t.side > 0 ? C.green : C.red }}>{t.side > 0 ? "COMPRA" : "VENDA"}</td>
                                        <td style={{ textAlign: "right" }}>{t.lots}</td>
                                        <td style={{ textAlign: "right" }}>{t.px_in} → {t.px_out}</td>
                                        <td style={{ textAlign: "right", color: pnlColor(t.pts) }}>{t.pts > 0 ? "+" : ""}{t.pts}</td>
                                        <td style={{ fontSize: 8 }}>{t.reason}</td>
                                        <td style={{ textAlign: "right", fontWeight: "bold", color: pnlColor(t[pnlKey]) }}>{brl(t[pnlKey], 2)}</td>
                                    </tr>
                                ))}</tbody>
                            </table>
                        </>
                    )}
                </div>

                <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, padding: 12 }}>
                    <div style={{ fontSize: 10, fontWeight: "bold", color: C.txt, letterSpacing: 1, marginBottom: 8, textTransform: "uppercase" }}>
                        Ranking dos robôs · {MONTHS[month.getMonth()]}
                    </div>
                    {monthRobots.length === 0 ? (
                        <div style={{ fontSize: 10, color: C.mute, padding: "12px 0" }}>Sem trades no mês.</div>
                    ) : (
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
                            <thead><tr style={{ color: C.dim, fontSize: 8, textAlign: "left" }}>
                                <th>ROBÔ</th><th style={{ textAlign: "right" }}>DIAS</th><th style={{ textAlign: "right" }}>TRADES</th><th style={{ textAlign: "right" }}>WR</th><th style={{ textAlign: "right" }}>PF</th><th style={{ textAlign: "right" }}>RESULTADO</th>
                            </tr></thead>
                            <tbody>{monthRobots.map((r) => (
                                <tr key={r.robot} style={{ borderTop: `1px solid ${C.border}` }}>
                                    <td style={{ padding: "4px 0", fontWeight: "bold", color: r.asset === "WIN" ? C.win : C.wdo }} title={r.name}>{r.robot} <span style={{ color: C.mute, fontWeight: "normal", fontSize: 8 }}>{r.name}</span></td>
                                    <td style={{ textAlign: "right", color: C.mute }}>{r.days}</td>
                                    <td style={{ textAlign: "right", color: C.txt }}>{r.n}</td>
                                    <td style={{ textAlign: "right", color: C.mute }}>{r.wr.toFixed(0)}%</td>
                                    <td style={{ textAlign: "right", color: r.pf >= 1 ? C.green : C.red }}>{fmtPf(r.pf)}</td>
                                    <td style={{ textAlign: "right", fontWeight: "bold", color: pnlColor(r.net) }}>{brl(r.net)}</td>
                                </tr>
                            ))}</tbody>
                        </table>
                    )}
                    <div style={{ fontSize: 8, color: C.dim, marginTop: 10, lineHeight: 1.5 }}>
                        BRUTO = resultado das operações contabilizadas no dashboard (sem comissão), com {winCtr} ctr WIN e {wdoCtr} ctr WDO. C/ CUSTO EST. = desconta R$ {COST_PER_CTR.WIN}/ctr no WIN e R$ {COST_PER_CTR.WDO}/ctr no WDO, igual aos backtests alinhados. Clique num trade para abrir o pregão no gráfico.
                    </div>
                </div>
            </div>
        </div>
    );
}

