import { useEffect, useRef, useState, useMemo, forwardRef, useImperativeHandle } from "react";
import { createChart, CandlestickSeries, LineStyle, CrosshairMode } from "lightweight-charts";

const CHART_MARGIN = { top: 0, right: 12, bottom: 0, left: 0 };
const Y_AXIS_WIDTH = 38;

const Z_WDO_ENT = 1.4;
const Z_DI_ENT = 2.2;
const Z_CONS_WDO = 1.8;
const Z_CONS_DI = 2.2;
const Z_ATT = 1.2;

function getWdoColor(d) {
    if (!d) return "transparent";
    const sig = d.sig_wdo ?? 0;
    const zw = d.z ?? d.z_raw_wdo ?? null;
    if (sig < 0 || (zw != null && zw <= -Z_WDO_ENT)) return "#00e87a";
    if (sig > 0 || (zw != null && zw >= Z_WDO_ENT)) return "#ff3860";
    return "transparent";
}

function getDiColor(d) {
    if (!d) return "transparent";
    const sig = d.sig_di ?? 0;
    const zd = d.z_di ?? d.z_raw_di ?? null;
    if (sig < 0 || (zd != null && zd <= -Z_DI_ENT)) return "#00e87a";
    if (sig > 0 || (zd != null && zd >= Z_DI_ENT)) return "#ff3860";
    return "transparent";
}

function getConsColor(d) {
    if (!d) return "transparent";
    const sig = d.sig_cons ?? (
        (d.cons_wdo_sig && d.cons_di_sig && Math.sign(d.cons_wdo_sig) === Math.sign(d.cons_di_sig))
            ? d.cons_wdo_sig : 0
    );
    const zw = d.z ?? d.z_raw_wdo ?? null;
    const zd = d.z_di ?? d.z_raw_di ?? null;
    if (sig < 0 || (zw != null && zd != null && ((zw <= -Z_CONS_WDO && zd <= -Z_ATT) || (zd <= -Z_DI_ENT && zw <= -Z_ATT)))) {
        return "#00e87a";
    }
    if (sig > 0 || (zw != null && zd != null && ((zw >= Z_CONS_WDO && zd >= Z_ATT) || (zd >= Z_DI_ENT && zw >= Z_ATT)))) {
        return "#ff3860";
    }
    return "transparent";
}

function timeStrToTimestamp(timeStr) {
    if (!timeStr) return 0;
    const [h, m] = timeStr.split(':').map(Number);
    return Math.floor(new Date(Date.UTC(2025, 0, 1, h, m)).getTime() / 1000);
}

const SignalHistogram = forwardRef(({ data }, ref) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRefs = useRef({});

    useImperativeHandle(ref, () => ({
        getChart: () => chartRef.current,
        getMainSeries: () => seriesRefs.current.wdoSeries,
    }));

    const activeColors = useMemo(() => {
        let wdoColor = "#5a7a90";
        let diColor = "#5a7a90";
        let consColor = "#5a7a90";
        if (data && data.length > 0) {
            for (let i = data.length - 1; i >= 0; i--) {
                const d = data[i];
                if (d && (d.z != null || d.z_raw_wdo != null)) {
                    const wc = getWdoColor(d);
                    const dc = getDiColor(d);
                    const cc = getConsColor(d);
                    if (wc !== "transparent") wdoColor = wc;
                    if (dc !== "transparent") diColor = dc;
                    if (cc !== "transparent") consColor = cc;
                    break;
                }
            }
        }
        return { wdoColor, diColor, consColor };
    }, [data]);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: "solid", color: "#0c1218" },
                textColor: "transparent", // Hide right axis text
            },
            grid: {
                vertLines: { visible: false },
                horzLines: { visible: false },
            },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: { color: "#c8a444", width: 1, style: LineStyle.Solid, labelVisible: false },
                horzLine: { visible: false, labelVisible: false },
            },
            timeScale: {
                visible: false, // hide time scale, syncing via App.jsx
            },
            rightPriceScale: {
                borderColor: "transparent",
                scaleMargins: { top: 0, bottom: 0 },
                autoScale: false,
                minimumWidth: 60,
            },
            autoSize: true,
            handleScroll: false,
            handleScale: false,
        });
        chartRef.current = chart;

        // Custom price scale fixed from 0 to 3 to simulate 3 stacked rows
        chart.priceScale('right').applyOptions({
            autoScale: false,
            minValue: 0,
            maxValue: 3,
        });

        const wdoSeries = chart.addSeries(CandlestickSeries, { 
            upColor: '#1e2a36', downColor: '#1e2a36', borderVisible: false, wickVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false 
        });
        const diSeries = chart.addSeries(CandlestickSeries, { 
            upColor: '#1e2a36', downColor: '#1e2a36', borderVisible: false, wickVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false 
        });
        const consSeries = chart.addSeries(CandlestickSeries, { 
            upColor: '#1e2a36', downColor: '#1e2a36', borderVisible: false, wickVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false 
        });

        // Add reference lines between layers
        wdoSeries.createPriceLine({ price: 1, color: '#1a2530', lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: false });
        wdoSeries.createPriceLine({ price: 2, color: '#1a2530', lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: false });

        seriesRefs.current = { wdoSeries, diSeries, consSeries };

        return () => {
            chart.remove();
        };
    }, []);

    useEffect(() => {
        if (!chartRef.current || !data || data.length === 0) return;

        const { wdoSeries, diSeries, consSeries } = seriesRefs.current;

        const wdoData = [];
        const diData = [];
        const consData = [];

        data.forEach(d => {
            if (!d.bar_time) return;
            const t = timeStrToTimestamp(d.bar_time);
            if (t === 0) return;

            const wCol = getWdoColor(d);
            const dCol = getDiColor(d);
            const cCol = getConsColor(d);

            // Use Candlestick data format to draw solid non-overlapping blocks
            wdoData.push({ time: t, open: 2.1, high: 2.9, low: 2.1, close: 2.9, color: wCol, borderColor: wCol, wickColor: wCol });
            diData.push({ time: t, open: 1.1, high: 1.9, low: 1.1, close: 1.9, color: dCol, borderColor: dCol, wickColor: dCol });
            consData.push({ time: t, open: 0.1, high: 0.9, low: 0.1, close: 0.9, color: cCol, borderColor: cCol, wickColor: cCol });
        });

        const sortData = (arr) => arr.sort((a,b) => a.time - b.time).filter((v,i,a) => i===0 || v.time > a[i-1].time);

        wdoSeries.setData(sortData(wdoData));
        diSeries.setData(sortData(diData));
        consSeries.setData(sortData(consData));
        try { chartRef.current.timeScale().fitContent(); } catch (e) {}

    }, [data]);

    return (
        <div style={{ width: "100%", height: 80, background: "#0c1218", position: "relative" }}>
            {/* Fixed labels matching Y-axis spacing */}
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
            {/* Chart Area */}
            <div style={{ width: "100%", height: "80px", paddingLeft: Y_AXIS_WIDTH }} ref={chartContainerRef} />
            {(!data || data.length === 0) && (
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "#0c1218bb", zIndex: 10 }}>
                    <span style={{ color: "#4a6070", fontSize: 12, letterSpacing: 1 }}>AGUARDANDO ABERTURA DO MERCADO</span>
                </div>
            )}
        </div>
    );
});

SignalHistogram.displayName = 'SignalHistogram';
export default SignalHistogram;
