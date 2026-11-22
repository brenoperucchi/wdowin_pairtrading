import { useEffect, useRef, useState, useImperativeHandle, forwardRef, useMemo, useCallback } from "react";
import { createChart, LineSeries, AreaSeries, CandlestickSeries, LineStyle, CrosshairMode } from "lightweight-charts";
import { simulateDayStatArbTradesJs, STATARB_STRAT_META } from "../utils/statArbDayTrades";

const Y_AXIS_WIDTH = 38;

function timeStrToTimestamp(timeStr) {
    if (!timeStr) return 0;
    const [h, m] = timeStr.split(":").map(Number);
    return Math.floor(new Date(Date.UTC(2025, 0, 1, h, m)).getTime() / 1000);
}

const IndexChart = forwardRef(({ history, walls = [], tradeEngine = null, dayTrades: propDayTrades = null, isViewingHistory = false, hideXAxis = false }, ref) => {
    const chartContainerRef = useRef(null);
    const chartRef = useRef(null);
    const seriesRefs = useRef({});
    const [showCenterLine, setShowCenterLine] = useState(true);
    const [showCandles, setShowCandles] = useState(true);
    const [showTradeBoxes, setShowTradeBoxes] = useState(true);
    const [hoveredBoxId, setHoveredBoxId] = useState(null);
    const [selectedBoxId, setSelectedBoxId] = useState(null);
    const [overlayBoxes, setOverlayBoxes] = useState([]);
    const [plotSize, setPlotSize] = useState({ w: 0, h: 340 });

    useImperativeHandle(ref, () => ({
        getChart: () => chartRef.current,
        getMainSeries: () => seriesRefs.current.winCandleSeries || seriesRefs.current.winSeries,
    }));

    // Compute day trades (from backend if live and available, or via deterministic JS simulation)
    const computedDayTrades = useMemo(() => {
        if (Array.isArray(propDayTrades) && propDayTrades.length > 0) {
            return propDayTrades;
        }
        return simulateDayStatArbTradesJs(history, walls, !isViewingHistory);
    }, [history, walls, propDayTrades, isViewingHistory]);

    // Group trades that share the exact same entry_time, exit_time, direction, entry_price, and exit_price
    // so overlapping strategies (e.g. CONS + WDO_NWE at 09:05) render as one crisp TradingView box
    const groupedTradeBoxes = useMemo(() => {
        const map = new Map();
        computedDayTrades.forEach((tr) => {
            const key = `${tr.entry_time}_${tr.exit_time}_${tr.direction}_${tr.entry_price}_${tr.exit_price}`;
            if (!map.has(key)) {
                map.set(key, {
                    ...tr,
                    strategies: [tr.strategy_id],
                });
            } else {
                const existing = map.get(key);
                if (!existing.strategies.includes(tr.strategy_id)) {
                    existing.strategies.push(tr.strategy_id);
                }
            }
        });
        return Array.from(map.values());
    }, [computedDayTrades]);

    // Map bar_time -> candle high/low for triangle positioning
    const barHighLowByTime = useMemo(() => {
        const m = {};
        if (Array.isArray(history)) {
            history.forEach((b) => {
                if (b && b.bar_time && b.win_price != null) {
                    const px = Number(b.win_price);
                    m[b.bar_time] = {
                        high: Number(b.win_high ?? px),
                        low: Number(b.win_low ?? px),
                        close: px,
                    };
                }
            });
        }
        return m;
    }, [history]);

    const recomputeOverlayCoordinates = useCallback(() => {
        const chart = chartRef.current;
        const mainSeries = seriesRefs.current.winCandleSeries || seriesRefs.current.winSeries;
        const container = chartContainerRef.current;
        if (!chart || !mainSeries || !container) return;

        const rect = container.getBoundingClientRect();
        const rightAxisW = 62;
        const plotW = Math.max(100, rect.width - Y_AXIS_WIDTH - rightAxisW);
        const plotH = Math.max(100, rect.height - (hideXAxis ? 4 : 24));
        setPlotSize({ w: plotW, h: plotH });

        if (!groupedTradeBoxes || groupedTradeBoxes.length === 0) {
            setOverlayBoxes([]);
            return;
        }

        const ts = chart.timeScale();
        const clampY = (y) => Math.max(4, Math.min(plotH - 4, y));

        // Estimate 1-bar width in pixels
        const t0 = timeStrToTimestamp("09:00");
        const t1 = timeStrToTimestamp("09:05");
        const cx0 = ts.timeToCoordinate(t0);
        const cx1 = ts.timeToCoordinate(t1);
        const stepX = (cx0 != null && cx1 != null && cx1 > cx0) ? (cx1 - cx0) : 10;

        const boxes = [];
        groupedTradeBoxes.forEach((tr, idx) => {
            const tStart = timeStrToTimestamp(tr.entry_time);
            const tEnd = timeStrToTimestamp(tr.exit_time || tr.entry_time);
            const rawX1 = ts.timeToCoordinate(tStart);
            const rawX2 = ts.timeToCoordinate(tEnd);
            if (rawX1 == null) return;

            const x1 = rawX1;
            const x2 = Math.max(x1 + Math.max(18, stepX * 1.3), rawX2 != null ? rawX2 : x1 + stepX * 2);

            const isBuy = tr.dir_num > 0 || tr.direction === "COMPRA";
            const entryP = Number(tr.entry_price);
            const stopP = Number(tr.stop_price);
            const exitP = Number(tr.exit_price);
            const rawTpP = Number(tr.tp_price);

            // Keep TP box proportional on screen (like Tab 1) when Wall TP is > 450 pts away
            const visualTpP = isBuy
                ? (tr.pts > 0 && tr.exit_reason === "ALVO Z-REV" ? Math.max(exitP, entryP + 250) : Math.min(rawTpP, entryP + 420))
                : (tr.pts > 0 && tr.exit_reason === "ALVO Z-REV" ? Math.min(exitP, entryP - 250) : Math.max(rawTpP, entryP - 420));

            const yEntryRaw = mainSeries.priceToCoordinate(entryP);
            const yStopRaw = mainSeries.priceToCoordinate(stopP);
            const yTpRaw = mainSeries.priceToCoordinate(visualTpP);
            const yExitRaw = mainSeries.priceToCoordinate(exitP);
            if (yEntryRaw == null || yStopRaw == null || yTpRaw == null || yExitRaw == null) return;

            const yEntry = clampY(yEntryRaw);
            const yStop = clampY(yStopRaw);
            const yTpBox = clampY(yTpRaw);
            const yExit = clampY(yExitRaw);

            let hasBeStep = false;
            let xBe = null;
            let yBeStop = yEntry;
            let yBeTrig = yExit;
            if (tr.be_triggered && tr.be_time && tr.be_stop_price != null) {
                const tBe = timeStrToTimestamp(tr.be_time);
                const rawXBe = ts.timeToCoordinate(tBe);
                const rawYBeStop = mainSeries.priceToCoordinate(Number(tr.be_stop_price));
                const rawYBeTrig = mainSeries.priceToCoordinate(Number(tr.be_trigger_price || exitP));
                if (rawXBe != null && rawYBeStop != null) {
                    hasBeStep = true;
                    xBe = Math.min(x2 - 4, Math.max(x1 + Math.max(6, stepX * 0.5), rawXBe));
                    yBeStop = clampY(rawYBeStop);
                    if (rawYBeTrig != null) yBeTrig = clampY(rawYBeTrig);
                }
            }

            // Candle high/low at entry for triangle placement
            const barHL = barHighLowByTime[tr.entry_time] || { high: entryP, low: entryP };
            const yCandleExtremeRaw = mainSeries.priceToCoordinate(isBuy ? barHL.low : barHL.high);
            const yTriBase = yCandleExtremeRaw != null ? clampY(yCandleExtremeRaw) : yEntry;

            const stratLabels = tr.strategies.map((s) => STATARB_STRAT_META[s]?.short || s).join(" + ");
            const primaryMeta = STATARB_STRAT_META[tr.strategies[0]] || { color: "#4cc38a" };

            boxes.push({
                ...tr,
                boxKey: `${tr.id}_${idx}`,
                stratLabels,
                stratColor: primaryMeta.color,
                isBuy,
                x1,
                x2,
                boxW: Math.max(4, x2 - x1),
                yEntry,
                yStop,
                yTpBox,
                yExit,
                hasBeStep,
                xBe,
                yBeStop,
                yBeTrig,
                yTriBase,
            });
        });

        setOverlayBoxes(boxes);
    }, [groupedTradeBoxes, barHighLowByTime, hideXAxis]);

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
                horzLine: { visible: true, color: "#2a3346", width: 1, style: LineStyle.Dashed, labelVisible: true, labelBackgroundColor: "#1b212e" },
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
                scaleMargins: { top: 0.12, bottom: 0.12 },
                minimumWidth: 68,
            },
            autoSize: true,
        });
        chartRef.current = chart;

        // 1. Upper Band Area
        const nweUpper = chart.addSeries(AreaSeries, {
            lineColor: "rgba(229, 72, 77, 0.48)",
            lineWidth: 1,
            lineStyle: LineStyle.Solid,
            topColor: "rgba(229, 72, 77, 0.12)",
            bottomColor: "rgba(229, 72, 77, 0.12)",
            crosshairMarkerVisible: false,
            priceLineVisible: false,
            lastValueVisible: false,
        });

        // 2. Sell Zone Bottom
        const sellZoneBot = chart.addSeries(AreaSeries, {
            lineColor: "rgba(229, 72, 77, 0.28)",
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            topColor: "#0e1118",
            bottomColor: "#0e1118",
            crosshairMarkerVisible: false,
            priceLineVisible: false,
            lastValueVisible: false,
        });

        // 3. Buy Zone Top
        const buyZoneTop = chart.addSeries(AreaSeries, {
            lineColor: "rgba(76, 195, 138, 0.28)",
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            topColor: "rgba(76, 195, 138, 0.12)",
            bottomColor: "rgba(76, 195, 138, 0.12)",
            crosshairMarkerVisible: false,
            priceLineVisible: false,
            lastValueVisible: false,
        });

        // 4. Lower Band Area
        const nweLower = chart.addSeries(AreaSeries, {
            lineColor: "rgba(76, 195, 138, 0.48)",
            lineWidth: 1,
            lineStyle: LineStyle.Solid,
            topColor: "#0e1118",
            bottomColor: "#0e1118",
            crosshairMarkerVisible: false,
            priceLineVisible: false,
            lastValueVisible: false,
        });

        // 5. Center line
        const nweSeries = chart.addSeries(LineSeries, {
            color: "#d4a259",
            lineWidth: 2,
            crosshairMarkerVisible: false,
            priceLineVisible: false,
            lastValueVisible: false,
        });

        // 6. Candlestick series (M5 WIN OHLC — Ink Azul)
        const winCandleSeries = chart.addSeries(CandlestickSeries, {
            upColor: "#4cc38a",
            downColor: "#e5484d",
            borderUpColor: "#4cc38a",
            borderDownColor: "#e5484d",
            wickUpColor: "#4cc38a",
            wickDownColor: "#e5484d",
            priceLineVisible: true,
        });

        // 7. Line series (optional toggle)
        const winSeries = chart.addSeries(LineSeries, {
            color: "#eef0f5",
            lineWidth: 2,
            crosshairMarkerVisible: true,
            priceLineVisible: false,
            visible: false,
        });

        seriesRefs.current = { winCandleSeries, winSeries, nweSeries, nweUpper, sellZoneBot, buyZoneTop, nweLower };

        const handleRangeChange = () => {
            requestAnimationFrame(recomputeOverlayCoordinates);
        };
        chart.timeScale().subscribeVisibleTimeRangeChange(handleRangeChange);
        chart.timeScale().subscribeVisibleLogicalRangeChange(handleRangeChange);

        const ro = new ResizeObserver(() => {
            requestAnimationFrame(recomputeOverlayCoordinates);
        });
        ro.observe(chartContainerRef.current);

        return () => {
            ro.disconnect();
            chart.remove();
        };
    }, [hideXAxis]);

    // Keep recompute bound to latest state
    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;
        const handler = () => requestAnimationFrame(recomputeOverlayCoordinates);
        chart.timeScale().subscribeVisibleTimeRangeChange(handler);
        chart.timeScale().subscribeVisibleLogicalRangeChange(handler);
        recomputeOverlayCoordinates();
        return () => {
            try {
                chart.timeScale().unsubscribeVisibleTimeRangeChange(handler);
                chart.timeScale().unsubscribeVisibleLogicalRangeChange(handler);
            } catch (e) {}
        };
    }, [recomputeOverlayCoordinates]);

    // Update series visibility when toggling Candles vs Line
    useEffect(() => {
        const { winCandleSeries, winSeries } = seriesRefs.current;
        if (!winCandleSeries || !winSeries) return;
        winCandleSeries.applyOptions({ visible: showCandles });
        winSeries.applyOptions({ visible: !showCandles });
    }, [showCandles]);

    useEffect(() => {
        if (!chartRef.current || !history || history.length === 0) return;

        const { winCandleSeries, winSeries, nweSeries, nweUpper, sellZoneBot, buyZoneTop, nweLower } = seriesRefs.current;

        const candleData = [];
        const winData = [];
        const nweData = [];
        const upperData = [];
        const sellZoneData = [];
        const buyZoneData = [];
        const lowerData = [];

        let prevClose = null;
        history.forEach((d) => {
            if (!d.bar_time) return;
            const t = timeStrToTimestamp(d.bar_time);
            if (t === 0) return;

            if (d.win_price != null && isFinite(d.win_price)) {
                const c = Number(d.win_price);
                const o = Number(d.win_open ?? prevClose ?? c);
                const h = Math.max(o, c, Number(d.win_high ?? c));
                const l = Math.min(o, c, Number(d.win_low ?? c));
                prevClose = c;
                candleData.push({ time: t, open: o, high: h, low: l, close: c });
                winData.push({ time: t, value: c });
            } else {
                candleData.push({ time: t });
                winData.push({ time: t });
            }

            if (d.nweUpper != null && isFinite(d.nweUpper) && d.nweLower != null && isFinite(d.nweLower)) {
                upperData.push({ time: t, value: d.nweUpper });
                lowerData.push({ time: t, value: d.nweLower });

                const bw = d.nweUpper - d.nweLower;
                sellZoneData.push({ time: t, value: d.nweProxUpper ?? (d.nweUpper - bw * 0.15) });
                buyZoneData.push({ time: t, value: d.nweProxLower ?? (d.nweLower + bw * 0.15) });
            } else {
                upperData.push({ time: t });
                lowerData.push({ time: t });
                sellZoneData.push({ time: t });
                buyZoneData.push({ time: t });
            }

            const isUp = d.isUp ?? d.is_up;
            if (d.nwe != null && isFinite(d.nwe) && showCenterLine) {
                nweData.push({
                    time: t,
                    value: d.nwe,
                    color: isUp ? "#4cc38a" : "#e5484d",
                });
            } else {
                nweData.push({ time: t });
            }
        });

        const sortData = (arr) => arr.sort((a, b) => a.time - b.time).filter((v, i, a) => i === 0 || v.time > a[i - 1].time);

        winCandleSeries.setData(sortData(candleData));
        winSeries.setData(sortData(winData));
        nweUpper.setData(sortData(upperData));
        sellZoneBot.setData(sortData(sellZoneData));
        buyZoneTop.setData(sortData(buyZoneData));
        nweLower.setData(sortData(lowerData));
        nweSeries.setData(sortData(nweData));

        requestAnimationFrame(recomputeOverlayCoordinates);
    }, [history, showCenterLine, recomputeOverlayCoordinates]);

    // Handle Dynamic GEX Walls
    useEffect(() => {
        const mainSeries = seriesRefs.current.winCandleSeries || seriesRefs.current.winSeries;
        if (!mainSeries) return;

        if (seriesRefs.current.dynamicWalls) {
            seriesRefs.current.dynamicWalls.forEach((line) => {
                try { mainSeries.removePriceLine(line); } catch (e) {}
            });
        }

        const newLines = [];
        const wallList = walls.walls || walls;

        if (Array.isArray(wallList)) {
            wallList.forEach((w) => {
                if (!w || !Number.isFinite(Number(w.price))) return;
                let lineStyle = LineStyle.Solid;
                let axisLabel = true;
                let title = "";

                if (w.type === "MidWall") {
                    lineStyle = LineStyle.Dashed;
                    axisLabel = true;
                } else if (w.type === "MaxGamma") {
                    title = "MAX \u0393";
                } else if (w.type === "MinGamma") {
                    title = "MIN \u0393";
                } else if (w.type === "GammaFlip") {
                    title = "\u0393 FLIP";
                }

                const line = mainSeries.createPriceLine({
                    price: Number(w.price),
                    color: w.color || "#ffffff",
                    lineWidth: w.width || 1,
                    lineStyle,
                    axisLabelVisible: axisLabel,
                    title,
                });
                newLines.push(line);
            });
        }

        seriesRefs.current.dynamicWalls = newLines;
    }, [walls]);

    const openTradesCount = computedDayTrades.filter((t) => t.status === "ABERTA").length;
    const closedTradesCount = computedDayTrades.filter((t) => t.status === "FECHADA").length;
    const dayTotalPts = computedDayTrades.reduce((acc, t) => acc + Number(t.pts || 0), 0);

    return (
        <div style={{ background: "#0e1118", borderRadius: hideXAxis ? "0" : "0 0 10px 10px", border: "1px solid var(--mw-hairline)", borderTop: "none", paddingBottom: 4, position: "relative" }}>
            {/* Top Controls & Day Trades Summary Bar */}
            <div style={{
                display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "8px 14px 6px",
                paddingLeft: Y_AXIS_WIDTH,
                borderTop: "1px solid var(--mw-hairline)", flexWrap: "wrap",
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span className="mw-mono" style={{ fontSize: 11, fontWeight: 600, color: "var(--mw-text-2)" }}>Preço WINFUT (M5)</span>

                    {/* Toggle Candles vs Linha */}
                    <div className="mw-track">
                        <button
                            type="button"
                            className="mw-btn mw-mono"
                            data-active={showCandles ? "true" : "false"}
                            onClick={() => setShowCandles(true)}
                            style={{ height: 22, padding: "0 8px", fontSize: 10.5 }}
                        >
                            Candles
                        </button>
                        <button
                            type="button"
                            className="mw-btn mw-mono"
                            data-active={!showCandles ? "true" : "false"}
                            onClick={() => setShowCandles(false)}
                            style={{ height: 22, padding: "0 8px", fontSize: 10.5 }}
                        >
                            Linha
                        </button>
                    </div>

                    <span style={{ display: "inline-block", width: 1, height: 14, background: "var(--mw-hairline-strong)" }} />

                    <label className="mw-mono" style={{
                        fontSize: 11, display: "flex", alignItems: "center", gap: 5, cursor: "pointer",
                        color: showCenterLine ? "#d4a259" : "var(--mw-text-3)",
                    }}>
                        <input type="checkbox" checked={showCenterLine} onChange={() => setShowCenterLine(!showCenterLine)}
                            style={{ cursor: "pointer", accentColor: "#d4a259" }} />
                        Linha central NWE
                    </label>

                    <label className="mw-mono" style={{
                        fontSize: 11, display: "flex", alignItems: "center", gap: 5, cursor: "pointer",
                        color: showTradeBoxes ? "#38bdf8" : "var(--mw-text-3)",
                    }}>
                        <input type="checkbox" checked={showTradeBoxes} onChange={() => setShowTradeBoxes(!showTradeBoxes)}
                            style={{ cursor: "pointer", accentColor: "#38bdf8" }} />
                        Caixas de trade ({groupedTradeBoxes.length})
                    </label>
                </div>

                {/* Resumo Rápido das Operações do Dia no Topo do Gráfico */}
                <div className="mw-mono" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 10.5 }}>
                    {computedDayTrades.length === 0 ? (
                        <span style={{ color: "var(--mw-text-3)" }}>Nenhuma operação disparada neste pregão até o momento</span>
                    ) : (
                        <>
                            {computedDayTrades.map((tr) => {
                                const isOpen = tr.status === "ABERTA";
                                const isPos = tr.pts >= 0;
                                const meta = STATARB_STRAT_META[tr.strategy_id] || { short: tr.strategy_id, color: "#4cc38a" };
                                return (
                                    <span
                                        key={tr.id}
                                        onClick={() => setSelectedBoxId((prev) => (prev === tr.id ? null : tr.id))}
                                        style={{
                                            display: "inline-flex", alignItems: "center", gap: 5,
                                            padding: "2px 8px", borderRadius: 5, cursor: "pointer",
                                            background: isOpen ? "rgba(212, 162, 89, 0.12)" : (isPos ? "rgba(76, 195, 138, 0.10)" : "rgba(229, 72, 77, 0.10)"),
                                            border: `1px solid ${isOpen ? "rgba(212, 162, 89, 0.4)" : (isPos ? "rgba(76, 195, 138, 0.35)" : "rgba(229, 72, 77, 0.35)")}`,
                                        }}
                                        title="Clique para destacar a caixa desta operação no gráfico"
                                    >
                                        <strong style={{ color: meta.color, fontWeight: 600 }}>{meta.short}</strong>
                                        <span style={{ color: tr.direction === "COMPRA" ? "#4cc38a" : "#e5484d", fontWeight: 600 }}>
                                            {tr.direction === "COMPRA" ? "C" : "V"} @ {tr.entry_price}
                                        </span>
                                        <span style={{ color: "var(--mw-text-3)" }}>({tr.entry_time}→{tr.exit_time})</span>
                                        <strong style={{ color: isOpen ? "#d4a259" : (isPos ? "#4cc38a" : "#e5484d"), fontWeight: 600 }}>
                                            {isOpen ? `Aberta ${tr.pts >= 0 ? "+" : ""}${tr.pts}p` : `${tr.pts >= 0 ? "+" : ""}${tr.pts}p (${tr.exit_reason})`}
                                        </strong>
                                    </span>
                                );
                            })}
                            <span style={{
                                padding: "2px 8px", borderRadius: 5, fontWeight: 600,
                                background: "var(--mw-chrome)", border: "1px solid var(--mw-hairline)",
                                color: dayTotalPts >= 0 ? "#4cc38a" : "#e5484d",
                                whiteSpace: "nowrap",
                            }}>
                                Dia ({closedTradesCount} fech / {openTradesCount} ab): {dayTotalPts >= 0 ? "+" : ""}{dayTotalPts} pts ({dayTotalPts >= 0 ? "+" : "−"}R$ {Math.abs(Math.round(dayTotalPts * 0.4))})
                            </span>
                        </>
                    )}
                </div>
            </div>

            {/* Chart + Synchronized TradingView Position Boxes SVG Overlay */}
            <div style={{ position: "relative", width: "100%", height: "340px" }}>
                <div ref={chartContainerRef} style={{ width: "100%", height: "340px", paddingLeft: Y_AXIS_WIDTH }} />

                {showTradeBoxes && overlayBoxes.length > 0 && (
                    <svg
                        width={plotSize.w}
                        height={plotSize.h}
                        style={{
                            position: "absolute",
                            top: 0,
                            left: Y_AXIS_WIDTH,
                            pointerEvents: "none",
                            zIndex: 6,
                            overflow: "hidden",
                        }}
                    >
                        {overlayBoxes.map((box) => {
                            const {
                                boxKey, id, stratLabels, stratColor, isBuy,
                                x1, x2, boxW, yEntry, yStop, yTpBox, yExit,
                                hasBeStep, xBe, yBeStop, yBeTrig, yTriBase,
                                entry_time, exit_time, entry_price, exit_price, stop_price, tp_price,
                                pts, brl_2c, exit_reason, status, be_triggered, be_time, be_stop_price,
                            } = box;

                            const tpTop = Math.min(yEntry, yTpBox);
                            const tpH = Math.max(3, Math.abs(yTpBox - yEntry));
                            const slTop = Math.min(yEntry, yStop);
                            const slH = Math.max(3, Math.abs(yStop - yEntry));
                            const fullTop = Math.min(tpTop, slTop);
                            const fullBot = Math.max(tpTop + tpH, slTop + slH);

                            const postBeTpTop = hasBeStep ? Math.min(yBeStop, yTpBox) : tpTop;
                            const postBeTpH = hasBeStep ? Math.max(3, Math.abs(yTpBox - yBeStop)) : tpH;
                            const postBeSlTop = Math.min(yEntry, yBeStop);
                            const postBeSlH = Math.max(2, Math.abs(yBeStop - yEntry));

                            const isWinExit = pts >= 0;
                            const isOpenTrade = status === "ABERTA";
                            const isHovered = hoveredBoxId === boxKey || selectedBoxId === id;

                            const triY = isBuy ? Math.min(plotSize.h - 16, yTriBase + 4) : Math.max(16, yTriBase - 4);
                            const triPoints = isBuy
                                ? `${x1},${triY + 2} ${x1 - 5.5},${triY + 11} ${x1 + 5.5},${triY + 11}`
                                : `${x1},${triY - 2} ${x1 - 5.5},${triY - 11} ${x1 + 5.5},${triY - 11}`;

                            const pillTxt = `${stratLabels} · ${isBuy ? "C" : "V"} @ ${entry_price} → ${exit_price} (${pts >= 0 ? "+" : ""}${pts}p · ${exit_reason})`;
                            const pillW = Math.max(140, pillTxt.length * 5.2 + 12);
                            const pillX = Math.max(4, Math.min(plotSize.w - pillW - 4, (x1 + x2) / 2 - pillW / 2));
                            const pillY = isBuy ? Math.min(plotSize.h - 20, fullBot + 6) : Math.max(4, fullTop - 20);

                            return (
                                <g key={boxKey}>
                                    {/* Dark Contrast Backing (identical to Tab 1) */}
                                    <rect
                                        x={x1}
                                        y={fullTop}
                                        width={boxW}
                                        height={Math.max(4, fullBot - fullTop)}
                                        fill="#0a0c12"
                                        fillOpacity="0.72"
                                        rx="1.5"
                                    />

                                    {/* Gain / Target Zone in Teal (#089981) */}
                                    {hasBeStep && xBe !== null ? (
                                        <>
                                            <rect
                                                x={x1}
                                                y={tpTop}
                                                width={Math.max(1, xBe - x1)}
                                                height={tpH}
                                                fill="#089981"
                                                fillOpacity="0.34"
                                            />
                                            <rect
                                                x={xBe}
                                                y={postBeTpTop}
                                                width={Math.max(1, x2 - xBe)}
                                                height={postBeTpH}
                                                fill="#089981"
                                                fillOpacity="0.25"
                                            />
                                        </>
                                    ) : (
                                        <rect
                                            x={x1}
                                            y={tpTop}
                                            width={boxW}
                                            height={tpH}
                                            fill="#089981"
                                            fillOpacity="0.30"
                                        />
                                    )}

                                    {/* Risk / Stop Zone in Crimson (#f23645) + Break-Even Step */}
                                    {hasBeStep && xBe !== null ? (
                                        <>
                                            <rect
                                                x={x1}
                                                y={slTop}
                                                width={Math.max(1, xBe - x1)}
                                                height={slH}
                                                fill="#f23645"
                                                fillOpacity="0.28"
                                            />
                                            <rect
                                                x={xBe}
                                                y={postBeSlTop}
                                                width={Math.max(1, x2 - xBe)}
                                                height={postBeSlH}
                                                fill="#fbbf24"
                                                fillOpacity="0.18"
                                            />
                                        </>
                                    ) : (
                                        <rect
                                            x={x1}
                                            y={slTop}
                                            width={boxW}
                                            height={slH}
                                            fill="#f23645"
                                            fillOpacity="0.28"
                                        />
                                    )}

                                    {/* Side Vertical Borders of the Position Box */}
                                    <line x1={x1} y1={fullTop} x2={x1} y2={fullBot} stroke="#64748b" strokeWidth="0.9" strokeOpacity="0.55" />
                                    <line x1={x2} y1={fullTop} x2={x2} y2={fullBot} stroke="#64748b" strokeWidth="0.9" strokeOpacity="0.55" />

                                    {/* Top/Bottom Target Border (#2dd4bf) */}
                                    <line x1={x1} y1={yTpBox} x2={x2} y2={yTpBox} stroke="#2dd4bf" strokeWidth="1.4" strokeOpacity="0.95" />

                                    {/* Stop Loss Border (#fb7185) + Break-Even Step (#fbbf24) */}
                                    {hasBeStep && xBe !== null ? (
                                        <>
                                            <line x1={x1} y1={yStop} x2={xBe} y2={yStop} stroke="#fb7185" strokeWidth="1.4" strokeOpacity="0.95" />
                                            <line x1={xBe} y1={yStop} x2={x2} y2={yStop} stroke="#fb7185" strokeWidth="0.9" strokeDasharray="2,3" strokeOpacity="0.45" />
                                            <line x1={xBe} y1={yStop} x2={xBe} y2={yBeStop} stroke="#fbbf24" strokeWidth="1.3" strokeDasharray="2,2" strokeOpacity="0.95" />
                                            <line x1={xBe} y1={yBeStop} x2={x2} y2={yBeStop} stroke="#fbbf24" strokeWidth="1.4" strokeOpacity="0.98" />
                                            <circle cx={xBe} cy={yBeStop} r="2.6" fill="#d4a259" stroke="#0a0c12" strokeWidth="0.9" />
                                        </>
                                    ) : (
                                        <line x1={x1} y1={yStop} x2={x2} y2={yStop} stroke="#fb7185" strokeWidth="1.4" strokeOpacity="0.95" />
                                    )}

                                    {/* Crisp White Entry Line + Dashed Diagonal Trajectory Line */}
                                    <line x1={x1} y1={yEntry} x2={x2} y2={yEntry} stroke="#f8fafc" strokeWidth="1.4" strokeOpacity="0.95" />
                                    {hasBeStep && xBe !== null ? (
                                        <>
                                            <line x1={x1} y1={yEntry} x2={xBe} y2={yBeTrig} stroke="#e2e8f0" strokeWidth="1.15" strokeDasharray="3,3" strokeOpacity="0.85" />
                                            <line x1={xBe} y1={yBeTrig} x2={x2} y2={yExit} stroke="#e2e8f0" strokeWidth="1.15" strokeDasharray="3,3" strokeOpacity="0.75" />
                                        </>
                                    ) : (
                                        <line x1={x1} y1={yEntry} x2={x2} y2={yExit} stroke="#e2e8f0" strokeWidth="1.15" strokeDasharray="3,3" strokeOpacity="0.85" />
                                    )}

                                    {/* Entry Circle & Exit Circle (Exactly as in Tab 1 photo) */}
                                    <circle cx={x1} cy={yEntry} r="3.1" fill="#eef0f5" stroke="#0a0c12" strokeWidth="1.1" />
                                    <circle
                                        cx={x2}
                                        cy={yExit}
                                        r="3.4"
                                        fill={isOpenTrade ? "#d4a259" : (isWinExit ? "#4cc38a" : "#e5484d")}
                                        stroke="#0a0c12"
                                        strokeWidth="1.1"
                                    />

                                    {/* Interactive Entry Triangle Marker + Hover/Click Pill */}
                                    <g
                                        style={{ pointerEvents: "auto", cursor: "pointer" }}
                                        onMouseEnter={() => setHoveredBoxId(boxKey)}
                                        onMouseLeave={() => setHoveredBoxId((prev) => (prev === boxKey ? null : prev))}
                                        onClick={() => setSelectedBoxId((prev) => (prev === id ? null : id))}
                                    >
                                        <title>
                                            {`${stratLabels} | ${isBuy ? "COMPRA" : "VENDA"} às ${entry_time} @ ${entry_price} | Stop Inicial: ${stop_price} | Alvo Wall: ${tp_price}${be_triggered ? ` | BE às ${be_time} → ${be_stop_price}` : ""} | Saída às ${exit_time} @ ${exit_price} (${pts >= 0 ? "+" : ""}${pts} pts / R$ ${brl_2c >= 0 ? "+" : ""}${brl_2c}) · ${exit_reason}`}
                                        </title>
                                        <circle cx={x1} cy={isBuy ? triY + 6 : triY - 6} r="10" fill="transparent" />
                                        <polygon
                                            points={triPoints}
                                            fill={isBuy ? "#4cc38a" : "#e5484d"}
                                            stroke={isHovered ? "#eef0f5" : stratColor}
                                            strokeWidth={isHovered ? "1.6" : "1.1"}
                                        />
                                    </g>

                                    {isHovered && (
                                        <g pointerEvents="none">
                                            <rect
                                                x={pillX}
                                                y={pillY}
                                                width={pillW}
                                                height={16}
                                                rx="3.5"
                                                fill="#0a0c12"
                                                fillOpacity="0.95"
                                                stroke={isWinExit ? "#4cc38a" : "#e5484d"}
                                                strokeWidth="1.1"
                                            />
                                            <text
                                                x={pillX + pillW / 2}
                                                y={pillY + 11}
                                                fill="#eef0f5"
                                                fontSize="8.5"
                                                fontWeight="600"
                                                fontFamily="'IBM Plex Mono', monospace"
                                                textAnchor="middle"
                                            >
                                                {pillTxt}
                                            </text>
                                        </g>
                                    )}
                                </g>
                            );
                        })}
                    </svg>
                )}
            </div>

            {(!history || history.length === 0) && (
                <div style={{ position: "absolute", top: 25, left: 0, right: 0, bottom: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(14,17,24,0.82)", zIndex: 10 }}>
                    <span style={{ color: "var(--mw-muted)", fontSize: 12 }}>Aguardando abertura do mercado</span>
                </div>
            )}
        </div>
    );
});

IndexChart.displayName = "IndexChart";
export default IndexChart;
