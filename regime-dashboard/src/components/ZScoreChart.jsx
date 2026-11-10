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

const ZScoreChart = forwardRef(({ history, sigColor = "#00e87a", currentZ = 0, useV2 = false, hideXAxis = false }, ref) => {
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
                background: { type: "solid", color: "#0c1218" },
                textColor: "#4a6070",
                fontSize: 9,
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
                vertLine: { color: "#c8a444", width: 1, style: LineStyle.Solid, labelBackgroundColor: "#c8a444" },
                horzLine: { visible: false, labelVisible: true, labelBackgroundColor: "#c8a444" },
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
                borderColor: "#1a2530",
                autoScale: true,
                minimumWidth: 60,
            },
            autoSize: true,
        });
        chartRef.current = chart;

        const zSeries = chart.addSeries(LineSeries, {
            color: "#c8a444",
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
        const diSeries = chart.addSeries(LineSeries, { color: "#8a6dff", lineWidth: 1, lineStyle: LineStyle.Dashed, crosshairMarkerVisible: false, priceLineVisible: false });

        // Reference lines (Z=±2.2 DI Gatilho, Z=±1.4 WDO Gatilho, Z=±1.2 Consenso/Atenção, Z=±4.0 Anomalia)
        const lines = [
            { price: 4, color: "#ff386044", style: LineStyle.Dashed, width: 1, title: "ANOM" },
            { price: -4, color: "#ff386044", style: LineStyle.Dashed, width: 1, title: "ANOM" },
            { price: 2.2, color: "#8a6dffaa", style: LineStyle.Dotted, width: 1, title: "DI +2.2" },
            { price: -2.2, color: "#8a6dffaa", style: LineStyle.Dotted, width: 1, title: "DI -2.2" },
            { price: 1.4, color: "#ff3860aa", style: LineStyle.Dotted, width: 1, title: "WDO +1.4" },
            { price: -1.4, color: "#00e87aaa", style: LineStyle.Dotted, width: 1, title: "WDO -1.4" },
            { price: 1.2, color: "#f5a62366", style: LineStyle.Dotted, width: 1, title: "CONS +1.2" },
            { price: -1.2, color: "#f5a62366", style: LineStyle.Dotted, width: 1, title: "CONS -1.2" },
            { price: 0, color: "#3a5060", style: LineStyle.Solid, width: 1 },
        ];


        lines.forEach(l => {
            zSeries.createPriceLine({
                price: l.price,
                color: l.color,
                lineWidth: l.width,
                lineStyle: l.style,
                axisLabelVisible: !!l.title,
                title: l.title || "",
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
        <div style={{ width: "100%", background: "#0c1218", borderRadius: "8px 8px 0 0", position: "relative" }}>
            <div style={{
                display: "flex", alignItems: "center", gap: 16,
                padding: "6px 12px 0px", paddingLeft: Y_AXIS_WIDTH,
            }}>
                <span style={{ fontSize: 9, fontWeight: "bold", color: "#6f8a9c", letterSpacing: 2 }}>Z-SPREAD KALMAN (WINFUT)</span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 14, height: 2, background: "#c8a444", borderRadius: 1 }} />
                    <span style={{ fontSize: 9, color: "#c8a444" }}>WDOFUT (±1.4)</span>
                </span>
                {useV2 && (
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <span style={{ display: "inline-block", width: 14, height: 2, background: "#8a6dff", borderRadius: 1, borderTop: "1px dashed #8a6dff" }} />
                        <span style={{ fontSize: 9, color: "#8a6dff" }}>DIFUT (±2.2 · CONS 1.6/2.2 c/ ±1.2)</span>
                    </span>
                )}


            </div>
            <div ref={chartContainerRef} style={{ width: "100%", height: "200px", paddingLeft: Y_AXIS_WIDTH }} />
            {(!history || history.length === 0) && (
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "#0c1218bb", borderRadius: "8px 8px 0 0", zIndex: 10 }}>
                    <span style={{ color: "#4a6070", fontSize: 12, letterSpacing: 1 }}>AGUARDANDO ABERTURA DO MERCADO (09:00)</span>
                </div>
            )}
        </div>
    );
});
ZScoreChart.displayName = 'ZScoreChart';
export default ZScoreChart;
