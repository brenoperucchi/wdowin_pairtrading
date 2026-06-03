import { useEffect, useRef, useState, useImperativeHandle, forwardRef } from "react";
import { createChart, LineSeries, AreaSeries, LineStyle, CrosshairMode } from "lightweight-charts";

const CHART_MARGIN = { top: 4, right: 12, bottom: 0, left: 0 };
const Y_AXIS_WIDTH = 38;

function timeStrToTimestamp(timeStr) {
    if (!timeStr) return 0;
    const [h, m] = timeStr.split(':').map(Number);
    // Use a fixed date to keep it consistent
    return Math.floor(new Date(Date.UTC(2025, 0, 1, h, m)).getTime() / 1000);
}

const IndexChart = forwardRef(({ history, walls = [], hideXAxis = false }, ref) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRefs = useRef({});
    const [showCenterLine, setShowCenterLine] = useState(true);

    useImperativeHandle(ref, () => ({
        getChart: () => chartRef.current,
        getMainSeries: () => seriesRefs.current.winSeries,
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
                scaleMargins: { top: 0.1, bottom: 0.1 },
                minimumWidth: 60,
            },
            autoSize: true,
        });
        chartRef.current = chart;

        // Create Series in proper z-index order (bottom to top)
        // 1. Upper Band Area (red shadow down to 0)
        const nweUpper = chart.addSeries(AreaSeries, { 
            lineColor: "rgba(255,56,96,0.5)", 
            lineWidth: 1, 
            lineStyle: LineStyle.Solid, 
            topColor: "rgba(255,56,96,0.15)", 
            bottomColor: "rgba(255,56,96,0.15)", 
            crosshairMarkerVisible: false, 
            priceLineVisible: false 
        });
        
        // 2. Sell Zone Bottom (mask red shadow with background, leaving 10% red band)
        const sellZoneBot = chart.addSeries(AreaSeries, { 
            lineColor: "rgba(255,56,96,0.3)", 
            lineWidth: 1, 
            lineStyle: LineStyle.Dashed, 
            topColor: "#0c1218", 
            bottomColor: "#0c1218", 
            crosshairMarkerVisible: false, 
            priceLineVisible: false 
        });

        // 3. Buy Zone Top (green shadow down to 0)
        const buyZoneTop = chart.addSeries(AreaSeries, { 
            lineColor: "rgba(0,232,122,0.3)", 
            lineWidth: 1, 
            lineStyle: LineStyle.Dashed, 
            topColor: "rgba(0,232,122,0.15)", 
            bottomColor: "rgba(0,232,122,0.15)", 
            crosshairMarkerVisible: false, 
            priceLineVisible: false 
        });

        // 4. Lower Band Area (mask green shadow with background, leaving 10% green band)
        const nweLower = chart.addSeries(AreaSeries, { 
            lineColor: "rgba(0,232,122,0.5)", 
            lineWidth: 1, 
            lineStyle: LineStyle.Solid, 
            topColor: "#0c1218", 
            bottomColor: "#0c1218", 
            crosshairMarkerVisible: false, 
            priceLineVisible: false 
        });

        // 5. Center line
        const nweSeries = chart.addSeries(LineSeries, { color: "#c8a444", lineWidth: 2, crosshairMarkerVisible: false, priceLineVisible: false });
        
        // 6. Price line (top most)
        const winSeries = chart.addSeries(LineSeries, { color: "#ffffff", lineWidth: 2, crosshairMarkerVisible: true, priceLineVisible: false });
        
        seriesRefs.current = { winSeries, nweSeries, nweUpper, sellZoneBot, buyZoneTop, nweLower };
        
        return () => {
            chart.remove();
        };
    }, [hideXAxis]);

    useEffect(() => {
        if (!chartRef.current || !history || history.length === 0) return;

        const { winSeries, nweSeries, nweUpper, sellZoneBot, buyZoneTop, nweLower } = seriesRefs.current;

        const winData = [];
        const nweData = [];
        const upperData = [];
        const sellZoneData = [];
        const buyZoneData = [];
        const lowerData = [];

        history.forEach((d, i) => {
            if (!d.bar_time) return;
            const t = timeStrToTimestamp(d.bar_time);
            if (t === 0) return;

            if (d.win_price != null && isFinite(d.win_price)) winData.push({ time: t, value: d.win_price });
            else winData.push({ time: t }); // whitespace

            if (d.nweUpper != null && isFinite(d.nweUpper) && d.nweLower != null && isFinite(d.nweLower)) {
                upperData.push({ time: t, value: d.nweUpper });
                lowerData.push({ time: t, value: d.nweLower });
                
                // 10% Band tolerance zone
                const bw = d.nweUpper - d.nweLower;
                sellZoneData.push({ time: t, value: d.nweUpper - bw * 0.10 });
                buyZoneData.push({ time: t, value: d.nweLower + bw * 0.10 });
            } else {
                upperData.push({ time: t });
                lowerData.push({ time: t });
                sellZoneData.push({ time: t });
                buyZoneData.push({ time: t });
            }

            const isUp = d.isUp ?? d.is_up;

            if (d.nwe != null && isFinite(d.nwe)) {
                if (showCenterLine) {
                    nweData.push({ 
                        time: t, 
                        value: d.nwe, 
                        color: isUp ? "#00e87a" : "#ff3860" 
                    });
                } else {
                    nweData.push({ time: t }); // explicitly push whitespace
                }
            } else {
                nweData.push({ time: t }); // whitespace
            }
        });

        // Ensure unique time sorting (lightweight charts throws error if not strictly increasing)
        const sortData = (arr) => arr.sort((a,b) => a.time - b.time).filter((v,i,a) => i===0 || v.time > a[i-1].time);

        winSeries.setData(sortData(winData));
        nweUpper.setData(sortData(upperData));
        sellZoneBot.setData(sortData(sellZoneData));
        buyZoneTop.setData(sortData(buyZoneData));
        nweLower.setData(sortData(lowerData));
        nweSeries.setData(sortData(nweData));

    }, [history, showCenterLine]);

    // Handle Dynamic GEX Walls from Firebase
    useEffect(() => {
        const { winSeries } = seriesRefs.current;
        if (!winSeries) return;

        // Cleanup old lines
        if (seriesRefs.current.dynamicWalls) {
            seriesRefs.current.dynamicWalls.forEach(line => winSeries.removePriceLine(line));
        }

        const newLines = [];
        const wallList = walls.walls || walls;
        
        if (Array.isArray(wallList)) {
            wallList.forEach(w => {
                // Map type to visual style
                let lineStyle = LineStyle.Solid;
                let axisLabel = true;
                let title = '';

                if (w.type === 'MidWall') {
                    lineStyle = LineStyle.Dashed;
                    axisLabel = false;
                } else if (w.type === 'Wall') {
                    title = '';
                } else if (w.type === 'MaxGamma') {
                    title = 'MAX \u0393';
                } else if (w.type === 'MinGamma') {
                    title = 'MIN \u0393';
                } else if (w.type === 'GammaFlip') {
                    title = '\u0393 FLIP';
                }

                const line = winSeries.createPriceLine({
                    price: w.price,
                    color: w.color,
                    lineWidth: w.width,
                    lineStyle,
                    axisLabelVisible: axisLabel,
                    title,
                });
                newLines.push(line);
            });
        }

        seriesRefs.current.dynamicWalls = newLines;

    }, [walls]);

    return (
        <div style={{ background: "#0c1218", borderRadius: hideXAxis ? "0" : "0 0 8px 8px", paddingBottom: 4, position: "relative" }}>
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
            <div ref={chartContainerRef} style={{ width: "100%", height: "340px", paddingLeft: Y_AXIS_WIDTH }} />
            {(!history || history.length === 0) && (
                <div style={{ position: "absolute", top: 25, left: 0, right: 0, bottom: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "#0c1218bb", zIndex: 10 }}>
                    <span style={{ color: "#4a6070", fontSize: 12, letterSpacing: 1 }}>AGUARDANDO ABERTURA DO MERCADO</span>
                </div>
            )}
        </div>
    );
});
IndexChart.displayName = 'IndexChart';
export default IndexChart;
