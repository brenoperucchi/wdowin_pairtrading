import { useMemo, useState, memo } from "react";
import { FORCE_WALLS_FLOW } from "../apiBase";

// Operações vêm do próprio dashboard: compassData.portfolio_4_sistematicas (/api/compass/etapa1)
const STRATS_MT5 = {
    EST_01: { code: "EST-01", name: "WIN Rejeição Wall" },
    EST_04: { code: "EST-04", name: "WIN Pullback WDO" },
    EST_07: { code: "EST-07", name: "WIN Rompimento Wall" },
    EST_13: { code: "EST-13", name: "WIN SmartGrid Longa (35% B1 · TP 360p)" },
    EST_14: { code: "EST-14", name: "WIN SmartGrid Média (50% B1 · TP 280p)" },
    EST_15: { code: "EST-15", name: "WIN SmartGrid Curta (55% B1 · TP 210p)" },
    EST_16: { code: "EST-16", name: "WIN SmartGrid Spring" },
    WIN_E2: { code: "WIN-E2", name: "WIN Wall Gasta" },
    WDO_01: { code: "WDO-01", name: "WDO Scalper Curto NY (TP 6–8p)" },
    WDO_02: { code: "WDO-02", name: "WDO Scalper Core" },
    WDO_05: { code: "WDO-05", name: "WDO Cluster Limit Wall (TP 7–9.5p)" },
    WDO_07: { code: "WDO-07", name: "WDO Absorção Longa Wall (TP 11p)" },
    WDO_09: { code: "WDO-09", name: "WDO Cluster NWE" },
    WDO_10: { code: "WDO-10", name: "WDO Lunch Reversão" },
    WDO_11: { code: "WDO-01", name: "WDO Scalper Curto NY (TP 6–8p)" },
    WDO_S2: { code: "WDO-01", name: "WDO Scalper Curto NY (TP 6–8p)" },
};
const STRATS_WALLS_FLOW = {
    WIN_DIV_WALL: { code: "WIN 2c Sniper", name: "Sniper · 2c Mix (NWE30+750p · s/ 12h · Meta +R$180)" },
    WDO_DIV_WALL: { code: "WDO 1c Sniper", name: "Sniper · 1c (s/ 11h NY · Meta +R$120)" },
    ESP_DIV_V22_WIN: { code: "WIN 2c Especialista", name: "Especialista de Divergência · 2c (10:00–15:55 · SL 200 · BE 180→20)" },
    C1a_BRK_WIN: { code: "WIN 1c Brk C1a", name: "BRK_F1F2 Conv · 1c (s/ 11h · SL 280 / TP 280 · 24b)" },
    V1a_DIV_WDO: { code: "WDO 1c Div V1a", name: "V3.2 Wall z=3,5 · 1c (s/ 11h · SL 14 / ProxWall [4..22])" },
    SYM_DIV_WIN: { code: "WIN 1c Simétrica", name: "SYM_TOP1 V3.2 · 1c (s/ 11h · SL 280 / TP 240)" },
    SYM_DIV_WDO: { code: "WDO 1c Simétrica", name: "SYM_TOP1 V3.2 · 1c (s/ 11h · SL 14 / ProxWall [3,5..20])" },
};
const MT5_TOP6_SET = new Set(["EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07"]);
const WALLS_FLOW_6_SET = new Set([
    "WIN_DIV_WALL",
    "WDO_DIV_WALL",
    "ESP_DIV_V22_WIN",
    "C1a_BRK_WIN",
    "V1a_DIV_WDO",
    "SYM_DIV_WIN",
    "SYM_DIV_WDO",
]);
const COST_PER_CTR = { WIN: 2.0, WDO: 5.0 };

function isWallsFlowLocalhost() {
    if (FORCE_WALLS_FLOW) return true;
    if (typeof window === "undefined") return false;
    const port = String(window.location.port || "");
    const params = new URLSearchParams(window.location.search || "");
    if (params.get("mode") === "walls_flow") return true;
    if (params.get("mode") === "mt5") return false;
    return port === "5176";
}

const C = {
    chrome: "var(--mw-chrome)",
    bg: "var(--mw-bg)",
    card: "var(--mw-card)",
    raised: "var(--mw-raised)",
    border: "var(--mw-hairline)",
    borderStrong: "var(--mw-hairline-strong)",
    txt1: "var(--mw-text-1)",
    txt2: "var(--mw-text-2)",
    txt3: "var(--mw-text-3)",
    pos: "var(--mw-pos)",
    posBg: "var(--mw-pos-bg)",
    neg: "var(--mw-neg)",
    negBg: "var(--mw-neg-bg)",
    accent: "var(--mw-accent)",
    accentInk: "var(--mw-accent-ink)",
    flip: "var(--mw-flip)",
};

const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex"];
const MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

const brl = (v, dec = 0) => {
    const n = Number(v || 0);
    const s = Math.abs(n).toLocaleString("pt-BR", { minimumFractionDigits: dec, maximumFractionDigits: dec });
    return `${n < 0 ? "−" : n > 0 ? "+" : ""}R$ ${s}`;
};
const pnlColor = (v) => (v > 0.001 ? C.pos : v < -0.001 ? C.neg : C.txt3);
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
        <div style={{
            background: C.bg,
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            padding: "12px 14px",
            display: "flex",
            flexDirection: "column",
            gap: 4,
            minWidth: 0,
        }}>
            <div style={{ fontSize: 11, color: C.txt3, fontWeight: 500, whiteSpace: "nowrap" }}>{label}</div>
            <div className="mw-mono" style={{ fontSize: 17, fontWeight: 600, color: color || C.txt1, whiteSpace: "nowrap", lineHeight: 1.2 }}>
                {value}
            </div>
            {sub && (
                <div className="mw-mono" style={{ fontSize: 11, color: C.txt3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {sub}
                </div>
            )}
        </div>
    );
}

function Toggle({ options, value, onChange }) {
    return (
        <div className="mw-track">
            {options.map(([v, label]) => (
                <button
                    key={v}
                    type="button"
                    className="mw-btn"
                    data-active={value === v ? "true" : "false"}
                    onClick={() => onChange(v)}
                >
                    {label}
                </button>
            ))}
        </div>
    );
}

function LiveTradingCalendar({ portfolioData, onSelectDate }) {
    const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
    const [asset, setAsset] = useState("ALL");
    const [scope, setScope] = useState("ALL");
    const [pnlKey, setPnlKey] = useState("pnl_est_cost");
    const [winCtr, setWinCtr] = useState(1);
    const [wdoCtr, setWdoCtr] = useState(1);
    const [selDay, setSelDay] = useState(ymd(new Date()));

    const ok = Boolean(portfolioData?.ok && Array.isArray(portfolioData.days));
    const liveStart = portfolioData?.live_start_date || "";
    const isWallsFlow = isWallsFlowLocalhost();
    const ACTIVE_SET = isWallsFlow ? WALLS_FLOW_6_SET : MT5_TOP6_SET;
    const STRATS = isWallsFlow ? STRATS_WALLS_FLOW : STRATS_MT5;

    const { allTrades, openTrades } = useMemo(() => {
        const closed = [], open = [];
        if (!ok) return { allTrades: closed, openTrades: open };
        portfolioData.days.forEach((d) => {
            const isLive = Boolean(d.is_live);
            const norm = (tr, i) => {
                const mult = tr.asset === "WIN" ? winCtr : wdoCtr;
                const baseLots = Number(tr.contracts || 1);
                const lots = baseLots * mult;
                const netBrl = Number(tr.brl_1c || 0) * mult;
                const grossBrl = tr.brl_1c_nocost !== undefined
                    ? Number(tr.brl_1c_nocost) * mult
                    : netBrl + (COST_PER_CTR[tr.asset] || 0) * lots;
                const meta = STRATS[tr.strategy_id] || STRATS_MT5[tr.strategy_id] || { code: tr.strategy_id, name: tr.type || tr.strategy_id };
                return {
                    id: `${d.date}-${tr.strategy_id}-${tr.time}-${i}`,
                    strategy_id: tr.strategy_id,
                    date: tr.date || d.date, is_live: isLive, robot: meta.code, name: meta.name, asset: tr.asset,
                    side: tr.direction === "COMPRA" ? 1 : -1, lots, t_in: tr.time, t_out: tr.exit_time,
                    px_in: tr.entry_price, px_out: tr.exit_price, pts: tr.pts, reason: tr.label || tr.status,
                    pnl: grossBrl, pnl_est_cost: netBrl,
                };
            };
            (d.trades || []).filter((tr) => tr.in_base !== false && ACTIVE_SET.has(tr.strategy_id)).forEach((tr, i) => closed.push(norm(tr, i)));
            if (isLive) (d.open_trades || []).filter((tr) => ACTIVE_SET.has(tr.strategy_id)).forEach((tr, i) => open.push(norm(tr, i)));
        });
        return { allTrades: closed, openTrades: open };
    }, [ok, portfolioData, winCtr, wdoCtr, isWallsFlow]);

    const trades = useMemo(() => allTrades.filter((t) =>
        (asset === "ALL" || t.asset === asset)
        && (scope === "ALL" || t.is_live)
    ), [allTrades, asset, scope]);

    const byDay = useMemo(() => {
        const m = {};
        for (const t of trades) (m[t.date] ||= []).push(t);
        return m;
    }, [trades]);

    const weeks = useMemo(() => {
        const y = month.getFullYear(), mo = month.getMonth();
        const first = new Date(y, mo, 1);
        const start = new Date(first);
        const dow = (first.getDay() + 6) % 7;
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

    const effectiveSelDay = useMemo(() => {
        if (byDay[selDay]?.length) return selDay;
        const allDates = Object.keys(byDay).sort();
        return allDates.length ? allDates[allDates.length - 1] : selDay;
    }, [byDay, selDay]);

    const selTrades = useMemo(() => byDay[effectiveSelDay] || [], [byDay, effectiveSelDay]);
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
        <section className="mw-card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Cabeçalho */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 12, borderBottom: `1px solid ${C.border}`, paddingBottom: 14 }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <h2 style={{ fontSize: 15, fontWeight: 600, color: C.txt1 }}>
                        {isWallsFlow
                            ? "Calendário auditado · Carteira 5176 (7 estratégias)"
                            : "Calendário auditado · 8 robôs com filtro de fluxo"}
                    </h2>
                    <div className="mw-mono" style={{ fontSize: 12, color: C.txt3 }}>
                        {isWallsFlow
                            ? "Snipers, Especialista, C1a, V1a e Simétricas (WIN + WDO) · líquido B3"
                            : "5 estratégias WIN + 3 estratégias WDO · líquido B3"}
                        {liveStart && (
                            <span style={{ color: C.pos }}> · Live desde {liveStart.split("-").reverse().join("/")}</span>
                        )}
                        {!ok && <span style={{ color: C.neg }}> · Aguardando dados do servidor</span>}
                    </div>
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                    <Toggle options={[["ALL", "WIN + WDO"], ["WIN", "WIN"], ["WDO", "WDO"]]} value={asset} onChange={setAsset} />
                    <Toggle options={[["ALL", "BT + Live"], ["LIVE", "Só Live"]]} value={scope} onChange={setScope} />
                    <Toggle options={[["pnl_est_cost", "Líquido B3"], ["pnl", "Bruto"]]} value={pnlKey} onChange={setPnlKey} />
                    {[["WIN", winCtr, setWinCtr], ["WDO", wdoCtr, setWdoCtr]].map(([lbl, v, setV]) => (
                        <label key={lbl} className="mw-mono" style={{ fontSize: 11, color: C.txt2, display: "inline-flex", alignItems: "center", gap: 6 }}>
                            <span>{lbl}</span>
                            <select
                                className="mw-select"
                                value={v}
                                onChange={(e) => setV(Number(e.target.value))}
                                style={{ height: 28, padding: "0 24px 0 8px", fontSize: 11 }}
                            >
                                {[1, 2, 3, 4, 5, 10].map((n) => <option key={n} value={n}>{n}x</option>)}
                            </select>
                        </label>
                    ))}
                </div>
            </div>

            {/* KPIs do mês */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(175px, 1fr))", gap: 10 }}>
                <Kpi
                    label="Resultado do mês"
                    value={brl(ms.net)}
                    color={pnlColor(ms.net)}
                    sub={`WIN ${brl(winNet)} · WDO ${brl(wdoNet)}`}
                />
                <Kpi
                    label="Trades / contratos"
                    value={`${ms.n} / ${ms.lots}`}
                    sub={`${ms.w} ganhos · ${ms.l} perdas`}
                />
                <Kpi
                    label="Win rate · PF"
                    value={`${ms.wr.toFixed(0)}% · ${fmtPf(ms.pf)}`}
                    color={ms.pf >= 1 ? C.pos : ms.n ? C.neg : C.txt1}
                />
                <Kpi
                    label="Dias positivos"
                    value={`${dayRows.pos} / ${dayRows.n}`}
                    sub={dayRows.n ? `${((100 * dayRows.pos) / dayRows.n).toFixed(0)}% dos pregões` : "—"}
                />
                <Kpi
                    label="Melhor · pior dia"
                    value={
                        <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                            <span style={{ color: pnlColor(dayRows.best) }}>{brl(dayRows.best)}</span>
                            <span style={{ color: C.txt3 }}>·</span>
                            <span style={{ color: pnlColor(dayRows.worst) }}>{brl(dayRows.worst)}</span>
                        </span>
                    }
                    sub={dayRows.n ? `Dias ${dayRows.bestDay?.slice(8)} e ${dayRows.worstDay?.slice(8)}` : "—"}
                />
                <Kpi
                    label="Drawdown do mês"
                    value={dayRows.dd > 0 ? `−R$ ${dayRows.dd.toFixed(0)}` : "R$ 0"}
                    color={dayRows.dd > 0 ? C.neg : C.txt1}
                    sub="Pico ao vale diário"
                />
                <Kpi
                    label="Em aberto agora"
                    value={openPos.length ? `${openPos.length} posição${openPos.length > 1 ? "ões" : ""}` : "—"}
                    color={openPos.length ? C.flip : C.txt2}
                    sub={openPos.length ? openPos.map((p) => `${p.robot} ${p.side > 0 ? "C" : "V"} ${p.px_in}`).join(" · ") : "Sem posições"}
                />
            </div>

            {/* Navegação do mês */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                <div className="mw-track">
                    <button type="button" className="mw-btn" onClick={() => shiftMonth(-1)} aria-label="Mês anterior">‹</button>
                    <button
                        type="button"
                        className="mw-btn"
                        onClick={() => { const d = new Date(); setMonth(new Date(d.getFullYear(), d.getMonth(), 1)); setSelDay(todayStr); }}
                    >
                        Hoje
                    </button>
                    <button type="button" className="mw-btn" onClick={() => shiftMonth(1)} aria-label="Próximo mês">›</button>
                </div>
                <div style={{ fontSize: 15, fontWeight: 500, color: C.txt1 }}>
                    {MONTHS[month.getMonth()]} de {month.getFullYear()}
                </div>
                <div className="mw-mono" style={{ fontSize: 12, color: C.txt3 }}>
                    {ms.w} ganhos · {ms.l} perdas
                </div>
            </div>

            {/* Grade do mês */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr)) minmax(150px, 1.15fr)", gap: 8 }}>
                {WEEKDAYS.map((w) => (
                    <div key={w} style={{ fontSize: 11, color: C.txt3, fontWeight: 500, padding: "0 4px" }}>{w}</div>
                ))}
                <div style={{ fontSize: 11, color: C.txt3, fontWeight: 500, padding: "0 4px" }}>Semana</div>
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
                            const isSel = k === effectiveSelDay, isToday = k === todayStr;
                            const isLiveDay = liveStart && k >= liveStart;
                            const tint = !inMonth || !s.n
                                ? C.bg
                                : s.net > 0.001
                                    ? "rgba(76, 195, 138, 0.07)"
                                    : s.net < -0.001
                                        ? "rgba(229, 72, 77, 0.07)"
                                        : C.bg;
                            return (
                                <div
                                    key={k}
                                    onClick={() => inMonth && setSelDay(k)}
                                    style={{
                                        background: tint,
                                        opacity: inMonth ? 1 : 0.3,
                                        minHeight: 78,
                                        borderRadius: 8,
                                        padding: "8px 10px",
                                        border: `1px solid ${isSel ? C.accent : s.n ? (s.net >= 0 ? "rgba(76, 195, 138, 0.24)" : "rgba(229, 72, 77, 0.24)") : C.border}`,
                                        cursor: inMonth ? "pointer" : "default",
                                        display: "flex",
                                        flexDirection: "column",
                                        justifyContent: "space-between",
                                        transition: "border-color 140ms var(--mw-ease)",
                                    }}
                                >
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 4 }}>
                                        <span className="mw-mono" style={{
                                            fontSize: 11,
                                            fontWeight: isToday ? 600 : 500,
                                            color: isToday ? "var(--mw-accent-on)" : C.txt2,
                                            background: isToday ? C.accent : "transparent",
                                            borderRadius: 4,
                                            padding: isToday ? "1px 6px" : 0,
                                        }}>
                                            {d.getDate()}
                                        </span>
                                        <div className="mw-mono" style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: C.txt3 }}>
                                            {s.n > 0 && <span>{robots.size} robô{robots.size > 1 ? "s" : ""}</span>}
                                            {s.n > 0 && scope === "ALL" && (
                                                <span style={{ color: isLiveDay ? C.pos : C.txt3 }}>
                                                    {isLiveDay ? "Live" : "BT"}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="mw-mono" style={{ textAlign: "center", fontSize: 14, fontWeight: 600, color: s.n ? pnlColor(s.net) : C.txt3, whiteSpace: "nowrap" }}>
                                        {s.n ? brl(s.net) : "—"}
                                    </div>
                                    <div className="mw-mono" style={{ fontSize: 10, color: C.txt3, textAlign: "center", whiteSpace: "nowrap" }}>
                                        {s.n ? `${s.n} tr · ${s.w}W/${s.l}L` : inMonth ? "Sem trades" : ""}
                                    </div>
                                </div>
                            );
                        }),
                        <div key={`w${wi}`} style={{
                            background: C.raised,
                            border: `1px solid ${C.border}`,
                            borderRadius: 8,
                            padding: "8px 12px",
                            display: "flex",
                            flexDirection: "column",
                            justifyContent: "space-between",
                        }}>
                            <div style={{ fontSize: 11, color: C.txt3, fontWeight: 500 }}>Semana {wi + 1}</div>
                            <div className="mw-mono" style={{ fontSize: 15, fontWeight: 600, color: ws.n ? pnlColor(ws.net) : C.txt3, whiteSpace: "nowrap" }}>
                                {ws.n ? brl(ws.net) : "R$ 0"}
                            </div>
                            <div className="mw-mono" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 10, color: C.txt3, gap: 4 }}>
                                <span>{ws.n} tr</span>
                                <span style={{ color: C.txt2 }}>{ws.wr.toFixed(0)}% · PF {fmtPf(ws.pf)}</span>
                            </div>
                        </div>,
                    ];
                })}
            </div>

            {/* Detalhe do dia + ranking do mês */}
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.45fr) minmax(0, 1fr)", gap: 16 }}>
                <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: 16, overflowX: "auto" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                        <span style={{ fontSize: 13, fontWeight: 500, color: C.txt1 }}>
                            Robôs que operaram · <span className="mw-mono">{effectiveSelDay.split("-").reverse().join("/")}</span>
                        </span>
                        <span className="mw-mono" style={{ fontSize: 13, fontWeight: 600, color: pnlColor(stats(selTrades, pnlKey).net), whiteSpace: "nowrap" }}>
                            {brl(stats(selTrades, pnlKey).net, 2)}
                        </span>
                    </div>
                    {selRobots.length === 0 ? (
                        <div style={{ fontSize: 12, color: C.txt3, padding: "12px 0" }}>Nenhum trade fechado neste dia.</div>
                    ) : (
                        <>
                            <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
                                <thead>
                                    <tr style={{ color: C.txt3, fontSize: 11, textAlign: "left", borderBottom: `1px solid ${C.border}` }}>
                                        <th style={{ padding: "6px 8px 6px 0", fontWeight: 500 }}>Robô</th>
                                        <th style={{ padding: "6px 8px", fontWeight: 500 }}>Estratégia</th>
                                        <th style={{ padding: "6px 8px", textAlign: "right", fontWeight: 500 }}>Tr</th>
                                        <th style={{ padding: "6px 8px", textAlign: "right", fontWeight: 500 }}>W/L</th>
                                        <th style={{ padding: "6px 8px", textAlign: "right", fontWeight: 500 }}>Ctr</th>
                                        <th style={{ padding: "6px 0 6px 8px", textAlign: "right", fontWeight: 500 }}>Resultado</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {selRobots.map((r) => (
                                        <tr key={r.robot} style={{ borderTop: `1px solid ${C.border}` }}>
                                            <td style={{ padding: "6px 8px 6px 0", fontWeight: 500, color: r.asset === "WIN" ? C.accentInk : C.flip, whiteSpace: "nowrap" }}>{r.robot}</td>
                                            <td style={{ padding: "6px 8px", color: C.txt2, fontFamily: "var(--sans)", fontSize: 11.5 }}>{r.name}</td>
                                            <td style={{ padding: "6px 8px", textAlign: "right", color: C.txt1 }}>{r.n}</td>
                                            <td style={{ padding: "6px 8px", textAlign: "right", color: C.txt3 }}>{r.w}/{r.l}</td>
                                            <td style={{ padding: "6px 8px", textAlign: "right", color: C.txt3 }}>{r.lots}</td>
                                            <td style={{ padding: "6px 0 6px 8px", textAlign: "right", fontWeight: 600, color: pnlColor(r.net), whiteSpace: "nowrap" }}>{brl(r.net, 2)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>

                            <div style={{ fontSize: 12, fontWeight: 500, color: C.txt2, margin: "16px 0 8px" }}>Trades do dia</div>
                            <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                                <thead>
                                    <tr style={{ color: C.txt3, fontSize: 10.5, textAlign: "left", borderBottom: `1px solid ${C.border}` }}>
                                        <th style={{ padding: "5px 6px 5px 0", fontWeight: 500 }}>Entrada</th>
                                        <th style={{ padding: "5px 6px", fontWeight: 500 }}>Saída</th>
                                        <th style={{ padding: "5px 6px", fontWeight: 500 }}>Robô</th>
                                        <th style={{ padding: "5px 6px", fontWeight: 500 }}>Lado</th>
                                        <th style={{ padding: "5px 6px", textAlign: "right", fontWeight: 500 }}>Ctr</th>
                                        <th style={{ padding: "5px 6px", textAlign: "right", fontWeight: 500 }}>Preço</th>
                                        <th style={{ padding: "5px 6px", textAlign: "right", fontWeight: 500 }}>Pts</th>
                                        <th style={{ padding: "5px 6px", fontWeight: 500 }}>Desfecho</th>
                                        <th style={{ padding: "5px 0 5px 6px", textAlign: "right", fontWeight: 500 }}>Resultado</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {[...selTrades].sort((a, b) => String(a.t_in).localeCompare(String(b.t_in))).map((t) => (
                                        <tr
                                            key={t.id}
                                            onClick={() => onSelectDate && onSelectDate(t.date)}
                                            title="Abrir este pregão no gráfico"
                                            style={{ borderTop: `1px solid ${C.border}`, color: C.txt2, cursor: onSelectDate ? "pointer" : "default" }}
                                        >
                                            <td style={{ padding: "5px 6px 5px 0", whiteSpace: "nowrap" }}>{t.t_in}</td>
                                            <td style={{ padding: "5px 6px", whiteSpace: "nowrap" }}>{t.t_out}</td>
                                            <td style={{ padding: "5px 6px", color: t.asset === "WIN" ? C.accentInk : C.flip, fontWeight: 500, whiteSpace: "nowrap" }}>{t.robot}</td>
                                            <td style={{ padding: "5px 6px", color: t.side > 0 ? C.pos : C.neg, whiteSpace: "nowrap" }}>{t.side > 0 ? "Compra" : "Venda"}</td>
                                            <td style={{ padding: "5px 6px", textAlign: "right" }}>{t.lots}</td>
                                            <td style={{ padding: "5px 6px", textAlign: "right", whiteSpace: "nowrap" }}>{t.px_in} → {t.px_out}</td>
                                            <td style={{ padding: "5px 6px", textAlign: "right", color: pnlColor(t.pts), whiteSpace: "nowrap" }}>{t.pts > 0 ? "+" : ""}{t.pts}</td>
                                            <td style={{ padding: "5px 6px", color: C.txt3, fontSize: 10.5 }}>{t.reason}</td>
                                            <td style={{ padding: "5px 0 5px 6px", textAlign: "right", fontWeight: 600, color: pnlColor(t[pnlKey]), whiteSpace: "nowrap" }}>{brl(t[pnlKey], 2)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </>
                    )}
                </div>

                <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: 16, overflowX: "auto" }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: C.txt1, marginBottom: 12 }}>
                        Ranking dos robôs · {MONTHS[month.getMonth()]}
                    </div>
                    {monthRobots.length === 0 ? (
                        <div style={{ fontSize: 12, color: C.txt3, padding: "12px 0" }}>Sem trades no mês.</div>
                    ) : (
                        <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
                            <thead>
                                <tr style={{ color: C.txt3, fontSize: 11, textAlign: "left", borderBottom: `1px solid ${C.border}` }}>
                                    <th style={{ padding: "6px 8px 6px 0", fontWeight: 500 }}>Robô</th>
                                    <th style={{ padding: "6px 6px", textAlign: "right", fontWeight: 500 }}>Dias</th>
                                    <th style={{ padding: "6px 6px", textAlign: "right", fontWeight: 500 }}>Tr</th>
                                    <th style={{ padding: "6px 6px", textAlign: "right", fontWeight: 500 }}>WR</th>
                                    <th style={{ padding: "6px 6px", textAlign: "right", fontWeight: 500 }}>PF</th>
                                    <th style={{ padding: "6px 0 6px 8px", textAlign: "right", fontWeight: 500 }}>Resultado</th>
                                </tr>
                            </thead>
                            <tbody>
                                {monthRobots.map((r) => (
                                    <tr key={r.robot} style={{ borderTop: `1px solid ${C.border}` }}>
                                        <td style={{ padding: "6px 8px 6px 0", fontWeight: 500, color: r.asset === "WIN" ? C.accentInk : C.flip, whiteSpace: "nowrap" }} title={r.name}>
                                            {r.robot}
                                        </td>
                                        <td style={{ padding: "6px 6px", textAlign: "right", color: C.txt3 }}>{r.days}</td>
                                        <td style={{ padding: "6px 6px", textAlign: "right", color: C.txt1 }}>{r.n}</td>
                                        <td style={{ padding: "6px 6px", textAlign: "right", color: C.txt2 }}>{r.wr.toFixed(0)}%</td>
                                        <td style={{ padding: "6px 6px", textAlign: "right", color: r.pf >= 1 ? C.pos : C.neg }}>{fmtPf(r.pf)}</td>
                                        <td style={{ padding: "6px 0 6px 8px", textAlign: "right", fontWeight: 600, color: pnlColor(r.net), whiteSpace: "nowrap" }}>{brl(r.net)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                    <div style={{ fontSize: 11, color: C.txt3, marginTop: 12, lineHeight: 1.55 }}>
                        Bruto = resultado sem comissão ({winCtr}x WIN e {wdoCtr}x WDO). Líquido B3 desconta R$ {COST_PER_CTR.WIN}/ctr no WIN e R$ {COST_PER_CTR.WDO}/ctr no WDO. Clique em qualquer trade para abrir o pregão no gráfico.
                    </div>
                </div>
            </div>
        </section>
    );
}

export default memo(LiveTradingCalendar);
