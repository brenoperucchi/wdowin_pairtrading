import { useMemo } from "react";
import { ResponsiveContainer, ComposedChart, Bar, Cell, XAxis, YAxis, Tooltip, ReferenceLine, Customized } from "recharts";

const STRAT_COLORS = {
    CONS_BASE: "#00d4ff",
    WDO_NWE: "#c8a444",
    DI_NWE: "#8a6dff",
};

const MARKER_ROW_GAP = 10;
const MARKER_BOTTOM_OFFSET = 5;

function TradeMarkersLayer({ xAxisMap, yAxisMap, trades }) {
    if (!trades?.length || !xAxisMap?.[0] || !yAxisMap?.[0]) return null;

    const xScale = xAxisMap[0].scale;
    const yAxis = yAxisMap[0];
    const yBottom = yAxis.y + yAxis.height;
    const bw = xScale.bandwidth ? xScale.bandwidth() : 0;

    const elements = [];
    const occupiedRowsByBar = new Map();

    const getMarkerY = (barTime, preferredRow) => {
        const occupiedRows = occupiedRowsByBar.get(barTime) ?? new Set();
        let row = preferredRow;

        while (occupiedRows.has(row)) row += 1;

        occupiedRows.add(row);
        occupiedRowsByBar.set(barTime, occupiedRows);

        return yBottom - MARKER_BOTTOM_OFFSET - row * MARKER_ROW_GAP;
    };

    trades.forEach((trade, i) => {
        const color = STRAT_COLORS[trade.strategy] ?? "#888";
        const isBuy = trade.direction === "BUY";

        if (trade.bar_time_in) {
            const xRaw = xScale(trade.bar_time_in);
            if (xRaw != null && !isNaN(xRaw)) {
                const cx = xRaw + bw / 2;
                const y = getMarkerY(trade.bar_time_in, 0);
                const label = `${trade.strategy} ${trade.direction} · Z: ${trade.z_in != null ? trade.z_in.toFixed(2) : "—"} · Entrada`;
                elements.push(
                    <text key={`entry-${i}`} x={cx} y={y} textAnchor="middle" dominantBaseline="middle" fontSize={9} fill={color}>
                        {isBuy ? "▲" : "▼"}
                        <title>{label}</title>
                    </text>
                );
            }
        }

        if (trade.bar_time_out) {
            const xRaw = xScale(trade.bar_time_out);
            if (xRaw != null && !isNaN(xRaw)) {
                const cx = xRaw + bw / 2;
                const y = getMarkerY(trade.bar_time_out, 1);
                const pnl = trade.pnl_brl != null ? ` · PnL: R$${Number(trade.pnl_brl).toFixed(0)}` : "";
                const label = `${trade.strategy} ${trade.direction} · Saída: ${trade.exit_reason ?? "—"}${pnl}`;
                elements.push(
                    <text key={`exit-${i}`} x={cx} y={y} textAnchor="middle" dominantBaseline="middle" fontSize={9} fill={color}>
                        ■
                        <title>{label}</title>
                    </text>
                );
            }
        }
    });

    return <g>{elements}</g>;
}

// Shared margins to align X-axis with other charts
const CHART_MARGIN = { top: 0, right: 12, bottom: 0, left: 0 };
const Y_AXIS_WIDTH = 38;

const Z_ENT = 1.4;
const Z_ATT = 1.2;

function getBarColor(z) {
    if (z == null || z === 0) return "#1e2a36";
    if (z <= -Z_ENT) return "#00e87a";           // COMPRA forte
    if (z <= -Z_ATT) return "#00e87a88";          // ATENÇÃO compra
    if (z >= Z_ENT)  return "#ff3860";            // VENDA forte
    if (z >= Z_ATT)  return "#ff386088";          // ATENÇÃO venda
    return "#1e2a36";
}

function getConsensusColor(zw, zd) {
    const sb = (zw <= -Z_ENT && zd <= -Z_ATT) || (zd <= -Z_ENT && zw <= -Z_ATT);
    const ss = (zw >= Z_ENT && zd >= Z_ATT) || (zd >= Z_ENT && zw >= Z_ATT);
    if (sb) return "#00e87a";
    if (ss) return "#ff3860";
    const att_b = (zw <= -Z_ATT && zd <= -Z_ATT);
    const att_s = (zw >= Z_ATT && zd >= Z_ATT);
    if (att_b) return "#00e87a44";
    if (att_s) return "#ff386044";
    return "#1e2a36";
}

export default function SignalHistogram({ data, trades }) {
    const bars = useMemo(() => {
        if (!data || data.length === 0) return [];
        return data.map(d => {
            const wdo = d.z_raw_wdo ?? d.z ?? null;
            const di = d.z_raw_di ?? d.z_di ?? null;
            // Consensus uses RAW z-scores (no NWE filter, matching CONS_BASE in trade engine)
            const consWdo = d.z_unfiltered_wdo ?? d.z ?? null;
            const consDi = d.z_unfiltered_di ?? d.z_di ?? null;
            
            const hasData = d.z != null;

            return {
                bar_time: d.bar_time,
                wdo_z: wdo ?? 0,
                di_z: di ?? 0,
                cons_wdo_z: consWdo ?? 0,
                cons_di_z: consDi ?? 0,
                wdo_nwe: hasData ? 1 : 0,
                di_nwe: hasData ? 1 : 0,
                wdo_di: hasData ? 1 : 0,
            };
        });
    }, [data]);

    const activeColors = useMemo(() => {
        let wdoColor = "#5a7a90";
        let diColor = "#5a7a90";
        let consColor = "#5a7a90";
        if (data && data.length > 0) {
            for (let i = data.length - 1; i >= 0; i--) {
                if (data[i].z != null) {
                    const wdo = data[i].sig_wdo ?? 0;
                    const di = data[i].sig_di ?? 0;
                    const cWdo = data[i].cons_wdo_sig ?? 0;
                    const cDi = data[i].cons_di_sig ?? 0;
                    
                    wdoColor = wdo < 0 ? "#00e87a" : wdo > 0 ? "#ff3860" : "#5a7a90";
                    diColor = di < 0 ? "#00e87a" : di > 0 ? "#ff3860" : "#5a7a90";
                    
                    const buyCount = [cWdo, cDi].filter(v => v < 0).length;
                    const sellCount = [cWdo, cDi].filter(v => v > 0).length;
                    consColor = buyCount >= 2 ? "#00e87a" : sellCount >= 2 ? "#ff3860" : "#5a7a90";
                    
                    break;
                }
            }
        }
        return { wdoColor, diColor, consColor };
    }, [data]);

    if (bars.length === 0) {
        return (
            <div style={{ width: "100%", height: 80, background: "#0c1218", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#4a6070", fontSize: 12, letterSpacing: 1 }}>AGUARDANDO ABERTURA DO MERCADO</span>
            </div>
        );
    }

    return (
        <div style={{ width: "100%", height: 80, background: "#0c1218", position: "relative" }}>
            {/* Fixed labels */}
            <div style={{
                position: "absolute", top: 0, left: 2, bottom: 0,
                width: Y_AXIS_WIDTH - 2, display: "flex", flexDirection: "column",
                justifyContent: "space-around", alignItems: "flex-end",
                paddingRight: 4, zIndex: 10, pointerEvents: "none"
            }}>
                <span style={{ fontSize: 7, color: activeColors.wdoColor, fontFamily: "monospace", fontWeight: activeColors.wdoColor !== "#5a7a90" ? "bold" : "normal" }}>WDO NWE</span>
                <span style={{ fontSize: 7, color: activeColors.diColor, fontFamily: "monospace", fontWeight: activeColors.diColor !== "#5a7a90" ? "bold" : "normal" }}>DI NWE</span>
                <span style={{ fontSize: 7, color: activeColors.consColor, fontFamily: "monospace", fontWeight: activeColors.consColor !== "#5a7a90" ? "bold" : "normal" }}>WDO DI</span>
            </div>

            <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={bars} margin={CHART_MARGIN} syncId="pair-trading" barGap={0} barCategoryGap={0}>
                    <XAxis dataKey="bar_time" hide={true} padding={{ left: 0, right: 0 }} />
                    <YAxis domain={[0, 3]} hide={false} axisLine={false} tickLine={false} tick={false} width={Y_AXIS_WIDTH} />
                    <Tooltip
                        cursor={{ stroke: "rgba(255,255,255,0.1)", strokeWidth: 1 }}
                        content={({ active, payload, label }) => {
                            if (active && payload && payload.length) {
                                const p = payload[0].payload;
                                const wColor = p.wdo_z <= -Z_ENT ? "#00e87a" : p.wdo_z >= Z_ENT ? "#ff3860" : "#5a7a90";
                                const dColor = p.di_z <= -Z_ENT ? "#00e87a" : p.di_z >= Z_ENT ? "#ff3860" : "#5a7a90";
                                
                                const cw = p.cons_wdo_z, cd = p.cons_di_z;
                                const sb = (cw <= -Z_ENT && cd <= -Z_ATT) || (cd <= -Z_ENT && cw <= -Z_ATT);
                                const ss = (cw >= Z_ENT && cd >= Z_ATT) || (cd >= Z_ENT && cw >= Z_ATT);
                                const cColor = sb ? "#00e87a" : ss ? "#ff3860" : "#5a7a90";
                                const consStatus = sb ? "COMPRA" : ss ? "VENDA" : "—";
                                
                                return (
                                    <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 6, fontSize: 10, fontFamily: "monospace", padding: "8px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
                                        <div style={{ color: "#6f8a9c", borderBottom: "1px solid #21262d", paddingBottom: 4, marginBottom: 2 }}>{label}</div>
                                        <div style={{ color: wColor, fontWeight: wColor !== "#5a7a90" ? "bold" : "normal" }}>WDO NWE Z : {p.wdo_z.toFixed(3)}</div>
                                        <div style={{ color: dColor, fontWeight: dColor !== "#5a7a90" ? "bold" : "normal" }}>DI NWE Z  : {p.di_z.toFixed(3)}</div>
                                        <div style={{ color: cColor, fontWeight: cColor !== "#5a7a90" ? "bold" : "normal" }}>Consenso (W:{cw.toFixed(2)} D:{cd.toFixed(2)}) : {consStatus}</div>
                                    </div>
                                );
                            }
                            return null;
                        }}
                    />
                    <ReferenceLine y={1} stroke="#1a2530" strokeWidth={1} />
                    <ReferenceLine y={2} stroke="#1a2530" strokeWidth={1} />
                    {/* Bottom: WDO DI (consensus) — y: 0 to 1 */}
                    <Bar dataKey="wdo_di" stackId="hist" isAnimationActive={false}>
                        {bars.map((entry, index) => (
                            <Cell key={`cons-${index}`} fill={getConsensusColor(entry.cons_wdo_z, entry.cons_di_z)} />
                        ))}
                    </Bar>
                    {/* Middle: DI NWE — y: 1 to 2 */}
                    <Bar dataKey="di_nwe" stackId="hist" isAnimationActive={false}>
                        {bars.map((entry, index) => (
                            <Cell key={`di-${index}`} fill={getBarColor(entry.di_z)} />
                        ))}
                    </Bar>
                    {/* Top: WDO NWE — y: 2 to 3 */}
                    <Bar dataKey="wdo_nwe" stackId="hist" isAnimationActive={false}>
                        {bars.map((entry, index) => (
                            <Cell key={`wdo-${index}`} fill={getBarColor(entry.wdo_z)} />
                        ))}
                    </Bar>
                    <Customized component={TradeMarkersLayer} trades={trades} />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
}
