import { useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import { createChart, LineSeries, LineStyle, CrosshairMode } from "lightweight-charts";

const Y_AXIS_WIDTH = 38;

const FlowScoreChart = forwardRef(({ history = [], smoothing = 3, onSmoothingChange }, ref) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRefs = useRef({});

    useImperativeHandle(ref, () => ({
        getChart: () => chartRef.current,
        getMainSeries: () => seriesRefs.current.flowSeries,
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
                vertLine: { color: "#c8a444", width: 1, style: LineStyle.Solid, labelBackgroundColor: "#c8a444" },
                horzLine: { visible: true, labelVisible: true, labelBackgroundColor: "#c8a444" },
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

        const flowSeries = chart.addSeries(LineSeries, {
            color: "#f5a623",
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
        flowSeries.createPriceLine({
            price: 0,
            color: "#21262d",
            lineWidth: 1.0,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: "0",
        });

        flowSeries.createPriceLine({
            price: 40,
            color: "rgba(0,232,122,0.3)",
            lineWidth: 1.0,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "+40 COMPRA",
        });

        flowSeries.createPriceLine({
            price: -40,
            color: "rgba(255,56,96,0.3)",
            lineWidth: 1.0,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "-40 VENDA",
        });

        seriesRefs.current = { flowSeries };

        return () => {
            chart.remove();
        };
    }, []);

    useEffect(() => {
        if (!chartRef.current || !history || history.length === 0) return;

        const { flowSeries } = seriesRefs.current;

        // Ensure we filter out duplicates and sort by timestamp
        const formattedData = history.map(d => ({
            time: d.time,
            value: d.value,
            color: d.color
        }));

        const sortedData = formattedData
            .sort((a, b) => a.time - b.time)
            .filter((v, i, arr) => i === 0 || v.time > arr[i - 1].time);

        flowSeries.setData(sortedData);

    }, [history]);

    return (
        <div style={{ background: "#0c1218", borderRadius: "0 0 8px 8px", paddingBottom: 6, position: "relative" }}>
            <div style={{
                display: "flex", alignItems: "center", gap: 14, padding: "6px 12px 2px",
                paddingLeft: Y_AXIS_WIDTH,
                borderTop: "1px solid #1a2530", flexWrap: "wrap",
            }}>
                <span style={{ fontSize: 9, fontWeight: "bold", color: "#6f8a9c", letterSpacing: 2 }}>FLOW SCORE SINTÉTICO (WIN) (M5)</span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, background: "#00e87a", borderRadius: "50%" }} />
                    <span style={{ fontSize: 9, color: "#00e87a" }}>Compra (&gt;= 40)</span>
                </span>
                <span style={{ display: "inline-block", width: 1, height: 12, background: "#1c2e3a" }} />
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, background: "#ff3860", borderRadius: "50%" }} />
                    <span style={{ fontSize: 9, color: "#ff3860" }}>Venda (&lt;= -40)</span>
                </span>
                <span style={{ display: "inline-block", width: 1, height: 12, background: "#1c2e3a" }} />
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, background: "#f5a623", borderRadius: "50%" }} />
                    <span style={{ fontSize: 9, color: "#f5a623" }}>Neutro</span>
                </span>
                <span style={{ display: "inline-block", width: 1, height: 12, background: "#1c2e3a" }} />
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 8, color: "#6f8a9c", fontWeight: "bold", letterSpacing: 1 }}>SUAVIZAÇÃO:</span>
                    <div style={{ display: "flex", gap: 3 }}>
                        {[1, 3, 5, 10].map(val => (
                            <button
                                key={val}
                                onClick={() => onSmoothingChange && onSmoothingChange(val)}
                                style={{
                                    background: smoothing === val ? "#c8a444" : "rgba(200, 164, 68, 0.1)",
                                    border: `1px solid ${smoothing === val ? "#c8a444" : "rgba(200, 164, 68, 0.25)"}`,
                                    color: smoothing === val ? "#0c1218" : "#c8a444",
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
            <div ref={chartContainerRef} style={{ width: "100%", height: "220px", paddingLeft: Y_AXIS_WIDTH }} />
            {(!history || history.length === 0) && (
                <div style={{ position: "absolute", top: 25, left: 0, right: 0, bottom: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "#0c1218bb", zIndex: 10 }}>
                    <span style={{ color: "#4a6070", fontSize: 12, letterSpacing: 1 }}>AGUARDANDO DADOS DE FLUXO REAL-TIME</span>
                </div>
            )}
        </div>
    );
});

FlowScoreChart.displayName = "FlowScoreChart";
export default FlowScoreChart;
