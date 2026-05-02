import { useMemo } from "react";
import { ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, ReferenceLine, Tooltip } from "recharts";

// Shared chart margins for X-axis alignment across all 3 charts
const CHART_MARGIN = { top: 8, right: 12, bottom: 0, left: 0 };
const Y_AXIS_WIDTH = 38;
const Z_CLAMP = 5; // Truncate Z values beyond ±5

export default function ZScoreChart({ history, sigColor = "#00e87a", currentZ = 0, useV2 = false, hideXAxis = false }) {
    const chartData = useMemo(() => {
        if (!history || history.length === 0) return [];
        return history.map(d => {
            let z = d.z ?? d.z_raw_wdo ?? null;
            let z_di = d.z_di ?? d.z_raw_di ?? null;
            // Guard against NaN/Infinity and clamp to ±5
            if (z != null && !isFinite(z)) z = null;
            if (z_di != null && !isFinite(z_di)) z_di = null;
            if (z != null) z = Math.max(-Z_CLAMP, Math.min(Z_CLAMP, z));
            if (z_di != null) z_di = Math.max(-Z_CLAMP, Math.min(Z_CLAMP, z_di));
            return { bar_time: d.bar_time, z, z_di };
        });
    }, [history]);

    if (chartData.length === 0) {
        return (
            <div style={{ width: "100%", height: 200, background: "#0c1218", borderRadius: "8px 8px 0 0", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#4a6070", fontSize: 12, letterSpacing: 1 }}>AGUARDANDO ABERTURA DO MERCADO (09:00)</span>
            </div>
        );
    }

    return (
        <div style={{ width: "100%", background: "#0c1218", borderRadius: "8px 8px 0 0" }}>
            {/* Legend */}
            <div style={{
                display: "flex", alignItems: "center", gap: 16,
                padding: "6px 12px 0px", paddingLeft: Y_AXIS_WIDTH,
            }}>
                <span style={{ fontSize: 9, fontWeight: "bold", color: "#6f8a9c", letterSpacing: 2 }}>Z-SCORE</span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 14, height: 2, background: "#c8a444", borderRadius: 1 }} />
                    <span style={{ fontSize: 9, color: "#c8a444" }}>WDO</span>
                </span>
                {useV2 && (
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <span style={{ display: "inline-block", width: 14, height: 2, background: "#8a6dff", borderRadius: 1, borderTop: "1px dashed #8a6dff" }} />
                        <span style={{ fontSize: 9, color: "#8a6dff" }}>DI</span>
                    </span>
                )}
            </div>

            {/* Chart */}
            <div style={{ width: "100%", height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData} margin={CHART_MARGIN} syncId="pair-trading">
                        <defs>
                            <linearGradient id="zFillPos" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="#ff3860" stopOpacity={0.12} />
                                <stop offset="50%" stopColor="#ff3860" stopOpacity={0} />
                            </linearGradient>
                            <linearGradient id="zFillNeg" x1="0" y1="1" x2="0" y2="0">
                                <stop offset="0%" stopColor="#00e87a" stopOpacity={0.12} />
                                <stop offset="50%" stopColor="#00e87a" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1a2530" vertical={false} />
                        <XAxis dataKey="bar_time" hide={true} padding={{ left: 0, right: 0 }} />
                        <YAxis
                            tick={{ fontSize: 9, fill: "#4a6070" }}
                            tickLine={false} axisLine={false}
                            domain={[-Z_CLAMP, Z_CLAMP]}
                            ticks={[-5, -4, -2, -1.4, -1.2, 0, 1.2, 1.4, 2, 4, 5]}
                            width={Y_AXIS_WIDTH}
                        />
                        <Tooltip
                            contentStyle={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 6, fontSize: 10, fontFamily: "monospace", padding: "6px 10px" }}
                            labelStyle={{ color: "#6f8a9c", marginBottom: 4 }}
                            formatter={(v, name) => {
                                if (v == null) return [null, null];
                                const label = name === "z" ? "Z WDO" : name === "z_di" ? "Z DI" : name;
                                return [v.toFixed(3), label];
                            }}
                        />

                        {/* Zone shading: anomalia (|z|≥4) */}
                        <ReferenceLine y={4} stroke="#ff386044" strokeDasharray="2 4" strokeWidth={0.5} />
                        <ReferenceLine y={-4} stroke="#ff386044" strokeDasharray="2 4" strokeWidth={0.5} />

                        {/* Entry zones ±1.4 */}
                        <ReferenceLine y={1.4} stroke="#ff386088" strokeDasharray="6 3" strokeWidth={0.8}
                            label={{ value: "VENDA 1.4", position: "right", fill: "#ff386088", fontSize: 8 }} />
                        <ReferenceLine y={-1.4} stroke="#00e87a88" strokeDasharray="6 3" strokeWidth={0.8}
                            label={{ value: "COMPRA -1.4", position: "right", fill: "#00e87a88", fontSize: 8 }} />

                        {/* Attention zones ±1.2 */}
                        <ReferenceLine y={1.2} stroke="#f5a62344" strokeDasharray="4 4" strokeWidth={0.5} />
                        <ReferenceLine y={-1.2} stroke="#f5a62344" strokeDasharray="4 4" strokeWidth={0.5} />

                        {/* Zero line — center */}
                        <ReferenceLine y={0} stroke="#3a5060" strokeWidth={1} />

                        {/* WDO Z-Score line */}
                        <Line type="monotone" dataKey="z" name="z" stroke="#c8a444" strokeWidth={1.8} dot={false} connectNulls={false} isAnimationActive={false} />

                        {/* DI Z-Score line (dashed) */}
                        {useV2 && (
                            <Line type="monotone" dataKey="z_di" name="z_di" stroke="#8a6dff" strokeWidth={1.2} dot={false} connectNulls={false} isAnimationActive={false} strokeDasharray="4 2" />
                        )}
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
