import { useEffect, useRef, useState, useMemo, forwardRef, useImperativeHandle } from "react";
import { createChart, CandlestickSeries, LineStyle, CrosshairMode } from "lightweight-charts";

const CHART_MARGIN = { top: 0, right: 12, bottom: 0, left: 0 };
const Y_AXIS_WIDTH = 38;

const Z_ENT = 1.4;
const Z_ATT = 1.2;

function getBarColor(z) {
    if (z == null || z === 0) return "#1e2a36";
    if (z <= -Z_ENT) return "#00e87a";
    if (z <= -Z_ATT) return "#00e87a88";
    if (z >= Z_ENT)  return "#ff3860";
    if (z >= Z_ATT)  return "#ff386088";
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

            const wdoZ = d.z_raw_wdo ?? d.z ?? 0;
            const diZ = d.z_raw_di ?? d.z_di ?? 0;
            const consWdo = d.z_unfiltered_wdo ?? d.z ?? 0;
            const consDi = d.z_unfiltered_di ?? d.z_di ?? 0;

            const wCol = getBarColor(wdoZ);
            const dCol = getBarColor(diZ);
            const cCol = getConsensusColor(consWdo, consDi);

            // Use Candlestick data format to draw solid non-overlapping blocks
            wdoData.push({ time: t, open: 2.1, high: 2.9, low: 2.1, close: 2.9, color: wCol, borderColor: wCol, wickColor: wCol });
            diData.push({ time: t, open: 1.1, high: 1.9, low: 1.1, close: 1.9, color: dCol, borderColor: dCol, wickColor: dCol });
            consData.push({ time: t, open: 0.1, high: 0.9, low: 0.1, close: 0.9, color: cCol, borderColor: cCol, wickColor: cCol });
        });

        const sortData = (arr) => arr.sort((a,b) => a.time - b.time).filter((v,i,a) => i===0 || v.time > a[i-1].time);

        wdoSeries.setData(sortData(wdoData));
        diSeries.setData(sortData(diData));
        consSeries.setData(sortData(consData));

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
