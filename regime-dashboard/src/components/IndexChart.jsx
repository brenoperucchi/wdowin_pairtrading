import { useMemo, useState } from "react";
import { ResponsiveContainer, ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";

// ── NWE (Nadaraya-Watson Envelope) calculation ──────────────────────────────
// MUST match core/signals.py calc_nwe_with_bands exactly (causal, lookback-only)
export const BANDWIDTH = 8;
export const LOOKBACK = 95;
export const MULT_MAE = 3;
const PROX_PCT = 0.10; // Proximity Multiplier: 10% of envelope width

export function calcNWE(prices, bandwidth = BANDWIDTH, multMAE = MULT_MAE, lookback = LOOKBACK) {
    if (!prices || prices.length === 0) return [];
    const n = prices.length;
    const h = Math.max(bandwidth, 1);
    const h2 = 2 * h * h;

    // Pass 1: Causal NWE (lookback-only, NO future data)
    const nweLine = new Array(n);
    for (let t = 0; t < n; t++) {
        const lb = Math.min(t, lookback);
        if (lb === 0) {
            nweLine[t] = prices[t];
            continue;
        }
        let sumW = 0, sumWY = 0;
        for (let k = 0; k <= lb; k++) {
            const w = Math.exp(-(k * k) / h2);
            sumW += w;
            sumWY += w * prices[t - k];
        }
        nweLine[t] = sumW > 0 ? sumWY / sumW : prices[t];
    }

    // Pass 2: Rolling MAE per bar (lookback window)
    const maeArr = new Array(n).fill(0);
    for (let t = 0; t < n; t++) {
        const lb = Math.min(t, lookback);
        if (lb === 0) continue;
        let sumErr = 0;
        for (let k = 0; k <= lb; k++) {
            sumErr += Math.abs(prices[t - k] - nweLine[t - k]);
        }
        maeArr[t] = (sumErr / (lb + 1)) * multMAE;
    }

    // Build output objects
    const result = new Array(n);
    for (let t = 0; t < n; t++) {
        const v = nweLine[t];
        const envW = maeArr[t];
        const upper = v + envW;
        const lower = v - envW;
        const isUp = t > 0 ? v >= nweLine[t - 1] : true;
        result[t] = {
            nwe: v,
            nweUpper: upper,
            nweLower: lower,
            nweProxUpper: upper - (2 * envW) * PROX_PCT,
            nweProxLower: lower + (2 * envW) * PROX_PCT,
            isUp: isUp,
            is_up: isUp,
        };
    }

    return result;
}

// ── Shared margins — MUST match ZScoreChart and SignalHistogram ─────────────
const CHART_MARGIN = { top: 4, right: 12, bottom: 0, left: 0 };
const Y_AXIS_WIDTH = 38;

export default function IndexChart({ history }) {
    const [showCenterLine, setShowCenterLine] = useState(true);

    const chartData = useMemo(() => {
        if (!history || history.length === 0) return [];
        const raw = history.map(d => ({
            bar_time: d.bar_time,
            win_price: (d.win_price != null && isFinite(d.win_price)) ? d.win_price : null,
            nwe: (d.nwe != null && isFinite(d.nwe)) ? d.nwe : null,
            nweUpper: (d.nweUpper != null && isFinite(d.nweUpper)) ? d.nweUpper : null,
            nweLower: (d.nweLower != null && isFinite(d.nweLower)) ? d.nweLower : null,
            nweProxUpper: (d.nweProxUpper != null && isFinite(d.nweProxUpper)) ? d.nweProxUpper : null,
            nweProxLower: (d.nweProxLower != null && isFinite(d.nweProxLower)) ? d.nweProxLower : null,
            isUp: d.isUp ?? d.is_up ?? null,
        }));

        // Split NWE into up/down segments for color change
        return raw.map((d, i) => {
            if (d.nwe == null) return { ...d, nwe_up: null, nwe_down: null };
            const prev = i > 0 ? raw[i - 1] : null;
            const isUp = d.isUp;
            const wasUp = prev?.isUp;
            const isTransition = prev != null && prev.nwe != null && isUp !== wasUp;

            return {
                ...d,
                nwe_up: (isUp || isTransition) ? d.nwe : null,
                nwe_down: (!isUp || isTransition) ? d.nwe : null,
            };
        });
    }, [history]);

    // Compute domain from actual data — filter out any non-finite values
    const prices = chartData.filter(d => d.win_price != null).map(d => d.win_price);
    const uppers = chartData.filter(d => d.nweUpper != null).map(d => d.nweUpper);
    const lowers = chartData.filter(d => d.nweLower != null).map(d => d.nweLower);
    const allVals = [...prices, ...uppers, ...lowers].filter(v => isFinite(v));
    const yMin = allVals.length > 0 ? Math.floor(Math.min(...allVals) - 50) : 128000;
    const yMax = allVals.length > 0 ? Math.ceil(Math.max(...allVals) + 50) : 133000;

    if (!history || history.length === 0 || chartData.length === 0) {
        return (
            <div style={{ width: "100%", height: 340, background: "#0c1218", borderRadius: "0 0 8px 8px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#4a6070", fontSize: 12, letterSpacing: 1 }}>AGUARDANDO ABERTURA DO MERCADO</span>
            </div>
        );
    }

    return (
        <div style={{ background: "#0c1218", borderRadius: "0 0 8px 8px", paddingBottom: 4 }}>
            {/* Legend + Filter controls */}
            <div style={{
                display: "flex", alignItems: "center", gap: 14, padding: "6px 12px 2px",
                paddingLeft: Y_AXIS_WIDTH,
                borderTop: "1px solid #1a2530", flexWrap: "wrap",
            }}>
                <span style={{ fontSize: 9, fontWeight: "bold", color: "#6f8a9c", letterSpacing: 2 }}>PREÇO</span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 14, height: 2, background: "#ffffff", borderRadius: 1 }} />
                    <span style={{ fontSize: 9, color: "#ffffff" }}>WIN</span>
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 14, height: 2, background: "#00e87a", borderRadius: 1 }} />
                    <span style={{ fontSize: 9, color: "#00e87a" }}>NWE↑</span>
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 14, height: 2, background: "#ff3860", borderRadius: 1 }} />
                    <span style={{ fontSize: 9, color: "#ff3860" }}>NWE↓</span>
                </span>
                <span style={{ display: "inline-block", width: 1, height: 12, background: "#1c2e3a" }} />
                <label style={{
                    fontSize: 10, display: "flex", alignItems: "center", gap: 5, cursor: "pointer",
                    color: showCenterLine ? "#c8a444" : "#4a6070", transition: "color 0.2s",
                }}>
                    <input type="checkbox" checked={showCenterLine} onChange={() => setShowCenterLine(!showCenterLine)}
                        style={{ cursor: "pointer", accentColor: "#c8a444" }} />
                    Linha Central
                </label>
            </div>

            {/* Chart */}
            <div style={{ width: "100%", height: 340 }}>
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData} margin={CHART_MARGIN} syncId="pair-trading">
                        <defs>
                            {/* Proximity zone fill — upper */}
                            <linearGradient id="proxFillUpper" x1="0" y1="1" x2="0" y2="0">
                                <stop offset="0%" stopColor="#ff3860" stopOpacity={0} />
                                <stop offset="100%" stopColor="#ff3860" stopOpacity={0.12} />
                            </linearGradient>
                            {/* Proximity zone fill — lower */}
                            <linearGradient id="proxFillLower" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="#00e87a" stopOpacity={0} />
                                <stop offset="100%" stopColor="#00e87a" stopOpacity={0.12} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1a2530" vertical={false} />
                        <XAxis dataKey="bar_time" hide={true} padding={{ left: 0, right: 0 }} />
                        <YAxis
                            tick={{ fontSize: 9, fill: "#4a6070" }}
                            tickLine={false} axisLine={false}
                            domain={[yMin, yMax]}
                            tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v}
                            width={Y_AXIS_WIDTH}
                        />
                        <Tooltip
                            contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 6, fontSize: 10, fontFamily: "monospace", padding: "6px 10px" }}
                            labelStyle={{ color: "#6f8a9c", marginBottom: 4 }}
                            formatter={(v, name) => {
                                if (v == null || typeof v !== "number") return [null, null];
                                const labels = { win_price: "WIN", nwe_up: "NWE ↑", nwe_down: "NWE ↓" };
                                if (!labels[name]) return [null, null];
                                return [v.toLocaleString("pt-BR", { minimumFractionDigits: 0 }), labels[name]];
                            }}
                        />

                        {/* Outer envelope lines — hidden from tooltip */}
                        <Line type="monotone" dataKey="nweUpper" stroke="#ff386066" strokeWidth={0.8} strokeDasharray="6 3" dot={false} connectNulls={false} isAnimationActive={false} tooltipType="none" />
                        <Line type="monotone" dataKey="nweLower" stroke="#00e87a66" strokeWidth={0.8} strokeDasharray="6 3" dot={false} connectNulls={false} isAnimationActive={false} tooltipType="none" />

                        {/* Proximity bands (10% inward from envelope edges) — hidden from tooltip */}
                        <Line type="monotone" dataKey="nweProxUpper" stroke="#ff386044" strokeWidth={0.6} strokeDasharray="2 4" dot={false} connectNulls={false} isAnimationActive={false} tooltipType="none" />
                        <Line type="monotone" dataKey="nweProxLower" stroke="#00e87a44" strokeWidth={0.6} strokeDasharray="2 4" dot={false} connectNulls={false} isAnimationActive={false} tooltipType="none" />

                        {/* NWE center line — split by slope direction */}
                        {showCenterLine && (
                            <Line type="monotone" dataKey="nwe_up" stroke="#00e87a" strokeWidth={1.8} dot={false} connectNulls={false} isAnimationActive={false} />
                        )}
                        {showCenterLine && (
                            <Line type="monotone" dataKey="nwe_down" stroke="#ff3860" strokeWidth={1.8} dot={false} connectNulls={false} isAnimationActive={false} />
                        )}

                        {/* WIN price — always on top */}
                        <Line type="monotone" dataKey="win_price" stroke="#ffffff" strokeWidth={1.8} dot={false} connectNulls={false} isAnimationActive={false} />
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
