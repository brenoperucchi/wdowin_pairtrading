import { useEffect, useRef, useMemo, forwardRef, useImperativeHandle } from "react";
import { createChart, LineSeries, LineStyle, CrosshairMode } from "lightweight-charts";

const CHART_MARGIN = { top: 8, right: 12, bottom: 0, left: 0 };
const Y_AXIS_WIDTH = 38;
const Z_CLAMP = 5;

function timeStrToTimestamp(timeStr) {
    if (!timeStr) return 0;
    const [h, m] = timeStr.split(':').map(Number);
    return Math.floor(new Date(Date.UTC(2025, 0, 1, h, m)).getTime() / 1000);
}

const ZScoreChart = forwardRef(({ history, sigColor = "#4cc38a", currentZ = 0, useV2 = false, hideXAxis = false }, ref) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRefs = useRef({});

    useImperativeHandle(ref, () => ({
        getChart: () => chartRef.current,
        getMainSeries: () => seriesRefs.current.zSeries,
    }));

    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: "solid", color: "#0e1118" },
                textColor: "#848da2",
                fontSize: 10,
            },
            localization: {
                timeFormatter: (time) => {
                    const d = new Date(time * 1000);
                    return String(d.getUTCHours()).padStart(2, "0") + ":" + String(d.getUTCMinutes()).padStart(2, "0");
                },
            },
            grid: {
                vertLines: { visible: false },
                horzLines: { visible: false },
            },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: { color: "#d4a259", width: 1, style: LineStyle.Solid, labelBackgroundColor: "#1b212e" },
                horzLine: { visible: false, labelVisible: true, labelBackgroundColor: "#1b212e" },
            },
            timeScale: {
                visible: !hideXAxis,
                timeVisible: true,
                secondsVisible: false,
                tickMarkFormatter: (time) => {
                    const d = new Date(time * 1000);
                    return String(d.getUTCHours()).padStart(2, "0") + ":" + String(d.getUTCMinutes()).padStart(2, "0");
                },
            },
            rightPriceScale: {
                borderColor: "#1b212e",
                autoScale: true,
                minimumWidth: 68,
            },
            autoSize: true,
        });
        chartRef.current = chart;

        const zSeries = chart.addSeries(LineSeries, {
            color: "#d4a259",
            lineWidth: 2,
            crosshairMarkerVisible: true,
            priceLineVisible: false,
            autoscaleInfoProvider: () => ({
                priceRange: {
                    minValue: -Z_CLAMP,
                    maxValue: Z_CLAMP,
                },
            }),
        });
        const diSeries = chart.addSeries(LineSeries, { color: "#a78bfa", lineWidth: 1, lineStyle: LineStyle.Dashed, crosshairMarkerVisible: false, priceLineVisible: false });

        // Reference lines
        const lines = [
            { price: 4, color: "rgba(229, 72, 77, 0.16)", style: LineStyle.Dashed, width: 1 },
            { price: -4, color: "rgba(229, 72, 77, 0.16)", style: LineStyle.Dashed, width: 1 },
            { price: 2.2, color: "rgba(167, 139, 250, 0.2)", style: LineStyle.Dotted, width: 1 },
            { price: -2.2, color: "rgba(167, 139, 250, 0.2)", style: LineStyle.Dotted, width: 1 },
            { price: 1.4, color: "rgba(229, 72, 77, 0.24)", style: LineStyle.Dotted, width: 1 },
            { price: -1.4, color: "rgba(76, 195, 138, 0.24)", style: LineStyle.Dotted, width: 1 },
            { price: 0, color: "#2a3346", style: LineStyle.Solid, width: 1 },
        ];

        lines.forEach(l => {
            zSeries.createPriceLine({
                price: l.price,
                color: l.color,
                lineWidth: l.width,
                lineStyle: l.style,
                axisLabelVisible: false,
                title: "",
            });
        });

        seriesRefs.current = { zSeries, diSeries };

        return () => {
            chart.remove();
        };
    }, [hideXAxis]);

    useEffect(() => {
        if (!chartRef.current || !history || history.length === 0) return;

        const { zSeries, diSeries } = seriesRefs.current;
        const zData = [];
        const diData = [];

        history.forEach(d => {
            if (!d.bar_time) return;
            const t = timeStrToTimestamp(d.bar_time);
            if (t === 0) return;

            let z = d.z ?? d.z_raw_wdo ?? null;
            let z_di = d.z_di ?? d.z_raw_di ?? null;
            
            if (z != null && isFinite(z)) zData.push({ time: t, value: Math.max(-Z_CLAMP, Math.min(Z_CLAMP, z)) });
            else zData.push({ time: t }); // whitespace

            if (useV2) {
                if (z_di != null && isFinite(z_di)) diData.push({ time: t, value: Math.max(-Z_CLAMP, Math.min(Z_CLAMP, z_di)) });
                else diData.push({ time: t }); // whitespace
            }
        });

        const sortData = (arr) => arr.sort((a,b) => a.time - b.time).filter((v,i,a) => i===0 || v.time > a[i-1].time);

        zSeries.setData(sortData(zData));
        if (useV2) diSeries.setData(sortData(diData));
        try { chartRef.current.timeScale().fitContent(); } catch (e) {}

    }, [history, useV2]);

    return (
        <div style={{ width: "100%", background: "#0e1118", border: "1px solid var(--mw-hairline)", borderBottom: "none", position: "relative" }}>
            <div className="mw-mono" style={{
                display: "flex", alignItems: "center", gap: 16,
                padding: "8px 14px 2px", paddingLeft: Y_AXIS_WIDTH, flexWrap: "wrap",
            }}>
                <span style={{ fontSize: 10.5, fontWeight: 600, color: "var(--mw-text-2)" }}>Z-Spread Kalman (WINFUT)</span>
                <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ display: "inline-block", width: 12, height: 2, background: "#d4a259", borderRadius: 1 }} />
                    <span style={{ fontSize: 10.5, color: "#d4a259" }}>WDOFUT (±1.4)</span>
                </span>
                {useV2 && (
                    <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                        <span style={{ display: "inline-block", width: 12, height: 2, borderTop: "1.5px dashed #a78bfa" }} />
                        <span style={{ fontSize: 10.5, color: "#a78bfa" }}>DIFUT (±2.2 · Cons 1.6/2.2 c/ ±1.2)</span>
                    </span>
                )}
            </div>
            <div ref={chartContainerRef} style={{ width: "100%", height: "200px", paddingLeft: Y_AXIS_WIDTH }} />
            {(!history || history.length === 0) && (
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(14, 17, 24, 0.85)", zIndex: 10 }}>
                    <span className="mw-mono" style={{ color: "var(--mw-text-3)", fontSize: 12 }}>Aguardando abertura do mercado (09:00)</span>
                </div>
            )}
        </div>
    );
});
ZScoreChart.displayName = 'ZScoreChart';
export default ZScoreChart;
