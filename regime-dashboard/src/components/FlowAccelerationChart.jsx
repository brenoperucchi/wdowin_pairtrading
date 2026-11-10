import { useState, useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import { createChart, LineSeries, LineStyle, CrosshairMode } from "lightweight-charts";

const Y_AXIS_WIDTH = 38;

const FlowAccelerationChart = forwardRef(({ history = [], smoothing = 3, onSmoothingChange }, ref) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRefs = useRef({});

    useImperativeHandle(ref, () => ({
        getChart: () => chartRef.current,
        getMainSeries: () => seriesRefs.current.iafSeries,
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
                priceFormatter: (price) => {
                    return Math.round(price).toString();
                }
            },
            grid: {
                vertLines: { visible: false },
                horzLines: { visible: false },
            },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: { color: "#ffcc00", width: 1, style: LineStyle.Solid, labelBackgroundColor: "#ffcc00" },
                horzLine: { visible: true, labelVisible: true, labelBackgroundColor: "#ffcc00" },
            },
            timeScale: {
                visible: true,
                timeVisible: true,
                secondsVisible: false,
                tickMarkFormatter: (time) => {
                    const d = new Date(time * 1000);
                    return String(d.getUTCHours()).padStart(2, "0") + ":" + String(d.getUTCMinutes()).padStart(2, "0");
                },
            },
            rightPriceScale: {
                borderColor: "#1a2530",
                scaleMargins: { top: 0.1, bottom: 0.1 },
                minimumWidth: 60,
                autoScale: true,
            },
            autoSize: true,
        });
        chartRef.current = chart;

        const iafSeries = chart.addSeries(LineSeries, {
            color: "#ffcc00",
            lineWidth: 2.5,
            crosshairMarkerVisible: true,
            priceLineVisible: false,
            autoscaleInfoProvider: () => ({
                priceRange: {
                    minValue: -105,
                    maxValue: 105,
                },
            }),
        });

        // Reference lines
        iafSeries.createPriceLine({
            price: 0,
            color: "#21262d",
            lineWidth: 1.0,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: "0",
        });

        iafSeries.createPriceLine({
            price: 40,
            color: "rgba(0,232,122,0.3)",
            lineWidth: 1.0,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "+40 COMPRA",
        });

        iafSeries.createPriceLine({
            price: -40,
            color: "rgba(255,56,96,0.3)",
            lineWidth: 1.0,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "-40 VENDA",
        });

        seriesRefs.current = { iafSeries };

        return () => {
            chart.remove();
        };
    }, []);

    useEffect(() => {
        const { iafSeries } = seriesRefs.current;
        if (!iafSeries) return;

        // Apply SMA smoothing if periods > 1
        let plotData = [...history];
        if (smoothing > 1 && history.length > 0) {
            const smoothed = [];
            for (let i = 0; i < history.length; i++) {
                const start = Math.max(0, i - smoothing + 1);
                const slice = history.slice(start, i + 1).filter(d => d.value !== null && d.value !== undefined);
                if (slice.length > 0) {
                    const sum = slice.reduce((acc, curr) => acc + curr.value, 0);
                    smoothed.push({
                        ...history[i],
                        value: sum / slice.length
                    });
                } else {
                    smoothed.push(history[i]);
                }
            }
            plotData = smoothed;
        }

        // Format data to ensure it's sorted by time and matches lightweight-charts spec
        const formattedData = plotData
            .filter(d => d.time !== undefined && d.time !== null)
            .map(d => ({
                time: Number(d.time),
                value: d.value !== null ? Number(d.value) : undefined,
            }))
            .sort((a, b) => a.time - b.time);

        // Remove duplicates if any
        const uniqueData = [];
        const seenTimes = new Set();
        for (const item of formattedData) {
            if (!seenTimes.has(item.time)) {
                seenTimes.add(item.time);
                uniqueData.push(item);
            }
        }

        iafSeries.setData(uniqueData);
        try { chartRef.current.timeScale().fitContent(); } catch (e) {}
    }, [history, smoothing]);

    return (
        <div style={{
            background: "#0c1218",
            border: "1px solid #1a2530",
            borderRadius: 6,
            overflow: "hidden",
            marginBottom: 8,
            display: "flex",
            flexDirection: "column",
        }}>
            <div style={{
                background: "#0e1620",
                borderBottom: "1px solid #16222f",
                padding: "8px 12px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 8,
            }}>
                <span style={{ fontSize: 10, fontWeight: "bold", color: "#8ca5b5", letterSpacing: 1.5, display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "#ffcc00" }} />
                    ÍNDICE DE ACELERAÇÃO DO FLUXO (IAF) (WIN) (M5)
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 8, color: "#4a6070", fontWeight: "bold" }}>SUAVIZAÇÃO:</span>
                        <div style={{ display: "flex", gap: 3 }}>
                            {[1, 3, 5, 10].map(val => (
                                <button
                                    key={val}
                                    onClick={() => onSmoothingChange && onSmoothingChange(val)}
                                    style={{
                                        background: smoothing === val ? "#ffcc00" : "rgba(255, 204, 0, 0.1)",
                                        border: `1px solid ${smoothing === val ? "#ffcc00" : "rgba(255, 204, 0, 0.25)"}`,
                                        color: smoothing === val ? "#0c1218" : "#ffcc00",
                                        fontSize: 8,
                                        fontWeight: "bold",
                                        padding: "2px 6px",
                                        borderRadius: 3,
                                        cursor: "pointer",
                                        transition: "all 0.2s",
                                    }}
                                >
                                    {val === 1 ? "OFF" : `${val} M5`}
                                </button>
                            ))}
                        </div>
                    </span>
                </div>
            </div>
            
            <div ref={chartContainerRef} style={{ height: 110, width: "100%", position: "relative" }} />
        </div>
    );
});

FlowAccelerationChart.displayName = "FlowAccelerationChart";
export default FlowAccelerationChart;
