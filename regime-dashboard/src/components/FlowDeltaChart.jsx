import { useEffect, useRef, useMemo, forwardRef, useImperativeHandle } from "react";
import { createChart, LineSeries, LineStyle, CrosshairMode } from "lightweight-charts";

const CHART_MARGIN = { top: 4, right: 12, bottom: 0, left: 0 };
const Y_AXIS_WIDTH = 38;

function timeStrToTimestamp(timeStr) {
    if (!timeStr) return 0;
    const [h, m] = timeStr.split(':').map(Number);
    return Math.floor(new Date(Date.UTC(2025, 0, 1, h, m)).getTime() / 1000);
}

function findFlowSnapshotForTime(flowHistory, targetTime) {
    if (!flowHistory || flowHistory.length === 0) return null;
    let bestSnap = null;
    for (let i = flowHistory.length - 1; i >= 0; i--) {
        const snap = flowHistory[i];
        if (snap.time <= targetTime) {
            bestSnap = snap;
            break;
        }
    }
    return bestSnap || flowHistory[0];
}

const FlowDeltaChart = forwardRef(({ history = [], flowData = null, classifications = {}, activeSymbol = "WIN$N", flowMode = "net", hideXAxis = true }, ref) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRefs = useRef({});

    useImperativeHandle(ref, () => ({
        getChart: () => chartRef.current,
        getMainSeries: () => seriesRefs.current.deltaSeries,
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
                horzLine: { visible: true, labelVisible: true, labelBackgroundColor: "#c8a444" },
            },
            timeScale: {
                visible: !hideXAxis,
                timeVisible: !hideXAxis,
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

        const deltaSeries = chart.addSeries(LineSeries, {
            color: "#c8a444",
            lineWidth: 2.5,
            crosshairMarkerVisible: true,
            priceLineVisible: false,
        });

        const smartSeries = chart.addSeries(LineSeries, {
            color: "#8a6dff",
            lineWidth: 1.5,
            lineStyle: LineStyle.Dashed,
            crosshairMarkerVisible: false,
            priceLineVisible: false,
        });

        const dummySeries = chart.addSeries(LineSeries, {
            color: "#00d4ff",
            lineWidth: 1.5,
            lineStyle: LineStyle.Dashed,
            crosshairMarkerVisible: false,
            priceLineVisible: false,
        });

        // Zero line
        deltaSeries.createPriceLine({
            price: 0,
            color: "#21262d",
            lineWidth: 1.0,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: "0",
        });

        seriesRefs.current = { deltaSeries, smartSeries, dummySeries };

        return () => {
            chart.remove();
        };
    }, [hideXAxis]);

    useEffect(() => {
        if (!chartRef.current || !history || history.length === 0) return;

        const { deltaSeries, smartSeries, dummySeries } = seriesRefs.current;
        const deltaData = [];
        const smartData = [];
        const dummyData = [];

        const symbol = activeSymbol ? (activeSymbol.includes("WDO") ? "WDO" : "WIN") : "WIN";
        const flowHistory = flowData?.history || [];

        history.forEach(s => {
            if (!s.bar_time) return;
            const t = timeStrToTimestamp(s.bar_time);
            if (t === 0) return;

            const snap = findFlowSnapshotForTime(flowHistory, s.bar_time);
            let smartSum = 0;
            let dummySum = 0;
            let netSum = 0;

            if (snap) {
                const snapFlow = snap[symbol] || {};
                Object.keys(snapFlow).forEach(b => {
                    const brokerVal = snapFlow[b];
                    let val = 0;
                    if (brokerVal !== undefined && brokerVal !== null) {
                        if (typeof brokerVal === 'object') {
                            const net = brokerVal.net || 0;
                            const buy = brokerVal.buy || 0;
                            const sell = brokerVal.sell || 0;
                            if (flowMode === 'agg') val = buy - sell;
                            else if (flowMode === 'abs') val = net - (buy - sell);
                            else val = net;
                        } else {
                            if (flowMode === 'agg') val = brokerVal;
                            else if (flowMode === 'abs') val = 0;
                            else val = brokerVal;
                        }
                    }

                    const classification = classifications[b] || "none";
                    if (classification === "smart") {
                        smartSum += val;
                        netSum -= val; // smart is -1 weight
                    } else if (classification === "dummy") {
                        dummySum += val;
                        netSum += val; // dummy is +1 weight
                    }
                });
            }

            deltaData.push({ time: t, value: netSum });
            smartData.push({ time: t, value: smartSum });
            dummyData.push({ time: t, value: dummySum });
        });

        const sortData = (arr) => arr.sort((a, b) => a.time - b.time).filter((v, i, a) => i === 0 || v.time > a[i - 1].time);

        deltaSeries.setData(sortData(deltaData));
        smartSeries.setData(sortData(smartData));
        dummySeries.setData(sortData(dummyData));

    }, [history, flowData, classifications, activeSymbol, flowMode]);

    return (
        <div style={{ width: "100%", background: "#0c1218", position: "relative" }}>
            <div style={{
                display: "flex", alignItems: "center", gap: 16,
                padding: "6px 12px 0px", paddingLeft: Y_AXIS_WIDTH,
                borderTop: "1px solid #1a2530", flexWrap: "wrap"
            }}>
                <span style={{ fontSize: 9, fontWeight: "bold", color: "#6f8a9c", letterSpacing: 2 }}>FLOW DELTA E CATEGORIAS</span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 8, height: 2, background: "#c8a444" }} />
                    <span style={{ fontSize: 8, color: "#c8a444" }}>NET DELTA (DUMMY - SMART)</span>
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 8, height: 2, borderBottom: "1px dashed #8a6dff" }} />
                    <span style={{ fontSize: 8, color: "#8a6dff" }}>SMART MONEY (INSTITUCIONAL)</span>
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 8, height: 2, borderBottom: "1px dashed #00d4ff" }} />
                    <span style={{ fontSize: 8, color: "#00d4ff" }}>DUMMY MONEY (VAREJO)</span>
                </span>
            </div>
            <div ref={chartContainerRef} style={{ width: "100%", height: "130px", paddingLeft: Y_AXIS_WIDTH }} />
        </div>
    );
});

FlowDeltaChart.displayName = "FlowDeltaChart";
export default FlowDeltaChart;
