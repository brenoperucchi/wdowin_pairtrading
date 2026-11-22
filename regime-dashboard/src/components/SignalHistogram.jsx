import { useEffect, useRef, useState, useMemo, forwardRef, useImperativeHandle } from "react";
import { createChart, CandlestickSeries, LineStyle, CrosshairMode } from "lightweight-charts";

const CHART_MARGIN = { top: 0, right: 12, bottom: 0, left: 0 };
const Y_AXIS_WIDTH = 38;

const Z_WDO_ENT = 1.4;
const Z_DI_ENT = 2.2;
const Z_CONS_WDO = 1.8;
const Z_CONS_DI = 2.2;
const Z_ATT = 1.2;

// Paleta de duas intensidades:
// 1. Cor clara / translúcida: primeira condição (Z-Score atingido, mas NWE ainda não alinhada)
// 2. Cor marcante / vermelho escuro: setup completo (Z-Score + NWE alinhada ou operação em execução)
const COLOR_SELL_COMPLETE = "#e5484d";
const COLOR_SELL_INITIAL  = "rgba(229, 72, 77, 0.35)";
const COLOR_BUY_COMPLETE  = "#4cc38a";
const COLOR_BUY_INITIAL   = "rgba(76, 195, 138, 0.35)";

function getBarStratColor(d, stratKey, trades = []) {
    if (!d || !d.bar_time) return "transparent";

    // 1. Se houver trade ativo desta estratégia nesta barra -> Setup Completo confirmado em execução
    const activeTrade = (trades || []).find((t) => 
        (t.strat === stratKey || t.strategy_id === stratKey) &&
        d.bar_time >= t.entry_time && 
        d.bar_time <= (t.exit_time || t.entry_time)
    );
    if (activeTrade) {
        const isBuy = activeTrade.dir === "BUY" || activeTrade.direction === "COMPRA" || activeTrade.dir_num === 1;
        return isBuy ? COLOR_BUY_COMPLETE : COLOR_SELL_COMPLETE;
    }

    // 2. Dados de NWE e preço da barra para verificar alinhamento contra-tendência
    const winPx = d.win_price != null ? Number(d.win_price) : (d.win != null ? Number(d.win) : null);
    const isNweUp = Boolean(d.isUp ?? d.is_up);
    const nu = d.nweUpper != null ? Number(d.nweUpper) : null;
    const nl = d.nweLower != null ? Number(d.nweLower) : null;
    const bw = (nu != null && nl != null) ? (nu - nl) : 0;

    // Zonas de proximidade NWE (15% para WDO e CONS, 10% para DI)
    const npu_15 = d.nweProxUpper != null ? Number(d.nweProxUpper) : (nu != null && bw > 0 ? nu - bw * 0.15 : null);
    const npl_15 = d.nweProxLower != null ? Number(d.nweProxLower) : (nl != null && bw > 0 ? nl + bw * 0.15 : null);
    const npu_10 = nu != null && bw > 0 ? nu - bw * 0.10 : npu_15;
    const npl_10 = nl != null && bw > 0 ? nl + bw * 0.10 : npl_15;

    const zw = d.z ?? d.z_raw_wdo ?? null;
    const zd = d.z_di ?? d.z_raw_di ?? null;

    if (stratKey === "WDO_NWE") {
        const sig = d.sig_wdo ?? 0;
        const isZSell = sig > 0 || (zw != null && zw >= Z_WDO_ENT);
        const isZBuy = sig < 0 || (zw != null && zw <= -Z_WDO_ENT);
        if (isZSell) {
            const isNweAligned = sig > 0 || (isNweUp && winPx != null && npu_15 != null && winPx >= npu_15);
            return isNweAligned ? COLOR_SELL_COMPLETE : COLOR_SELL_INITIAL;
        }
        if (isZBuy) {
            const isNweAligned = sig < 0 || (!isNweUp && winPx != null && npl_15 != null && winPx <= npl_15);
            return isNweAligned ? COLOR_BUY_COMPLETE : COLOR_BUY_INITIAL;
        }
    } else if (stratKey === "DI_NWE") {
        const sig = d.sig_di ?? 0;
        const isZSell = sig > 0 || (zd != null && zd >= Z_DI_ENT);
        const isZBuy = sig < 0 || (zd != null && zd <= -Z_DI_ENT);
        if (isZSell) {
            const isNweAligned = sig > 0 || (isNweUp && winPx != null && npu_10 != null && winPx >= npu_10);
            return isNweAligned ? COLOR_SELL_COMPLETE : COLOR_SELL_INITIAL;
        }
        if (isZBuy) {
            const isNweAligned = sig < 0 || (!isNweUp && winPx != null && npl_10 != null && winPx <= npl_10);
            return isNweAligned ? COLOR_BUY_COMPLETE : COLOR_BUY_INITIAL;
        }
    } else if (stratKey === "CONS") {
        const sig = d.sig_cons ?? (
            (d.cons_wdo_sig && d.cons_di_sig && Math.sign(d.cons_wdo_sig) === Math.sign(d.cons_di_sig))
                ? d.cons_wdo_sig : 0
        );
        const isZSell = sig > 0 || (zw != null && zd != null && ((zw >= Z_CONS_WDO && zd >= Z_ATT) || (zd >= Z_DI_ENT && zw >= Z_ATT)));
        const isZBuy = sig < 0 || (zw != null && zd != null && ((zw <= -Z_CONS_WDO && zd <= -Z_ATT) || (zd <= -Z_DI_ENT && zw <= -Z_ATT)));
        if (isZSell) {
            const isNweAligned = sig > 0 || (isNweUp && winPx != null && npu_15 != null && winPx >= npu_15);
            return isNweAligned ? COLOR_SELL_COMPLETE : COLOR_SELL_INITIAL;
        }
        if (isZBuy) {
            const isNweAligned = sig < 0 || (!isNweUp && winPx != null && npl_15 != null && winPx <= npl_15);
            return isNweAligned ? COLOR_BUY_COMPLETE : COLOR_BUY_INITIAL;
        }
    }

    return "transparent";
}

function getLabelColor(barColor) {
    if (!barColor || barColor === "transparent") return "#848da2";
    if (barColor === COLOR_SELL_COMPLETE) return "#e5484d";
    if (barColor === COLOR_SELL_INITIAL) return "#e57373";
    if (barColor === COLOR_BUY_COMPLETE) return "#4cc38a";
    if (barColor === COLOR_BUY_INITIAL) return "#6ee7b7";
    return barColor;
}

function timeStrToTimestamp(timeStr) {
    if (!timeStr) return 0;
    const [h, m] = timeStr.split(':').map(Number);
    return Math.floor(new Date(Date.UTC(2025, 0, 1, h, m)).getTime() / 1000);
}

const SignalHistogram = forwardRef(({ data, trades = [] }, ref) => {
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
                    const wc = getBarStratColor(d, "WDO_NWE", trades);
                    const dc = getBarStratColor(d, "DI_NWE", trades);
                    const cc = getBarStratColor(d, "CONS", trades);
                    if (wc !== "transparent") wdoColor = getLabelColor(wc);
                    if (dc !== "transparent") diColor = getLabelColor(dc);
                    if (cc !== "transparent") consColor = getLabelColor(cc);
                    break;
                }
            }
        }
        return { wdoColor, diColor, consColor };
    }, [data, trades]);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: "solid", color: "#0e1118" },
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
            upColor: 'transparent', downColor: 'transparent', borderVisible: false, wickVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false 
        });
        const diSeries = chart.addSeries(CandlestickSeries, { 
            upColor: 'transparent', downColor: 'transparent', borderVisible: false, wickVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false 
        });
        const consSeries = chart.addSeries(CandlestickSeries, { 
            upColor: 'transparent', downColor: 'transparent', borderVisible: false, wickVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false 
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

            const wCol = getBarStratColor(d, "WDO_NWE", trades);
            const dCol = getBarStratColor(d, "DI_NWE", trades);
            const cCol = getBarStratColor(d, "CONS", trades);

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

    }, [data, trades]);

    return (
        <div style={{ width: "100%", height: 80, background: "#0e1118", borderLeft: "1px solid var(--mw-hairline)", borderRight: "1px solid var(--mw-hairline)", position: "relative" }}>
            {/* Fixed labels matching Y-axis spacing */}
            <div className="mw-mono" style={{
                position: "absolute", top: 0, left: 2, bottom: 0,
                width: Y_AXIS_WIDTH - 2, display: "flex", flexDirection: "column",
                justifyContent: "space-around", alignItems: "flex-end",
                paddingRight: 4, zIndex: 10, pointerEvents: "none"
            }}>
                <span style={{ fontSize: 7.5, color: activeColors.wdoColor, fontWeight: activeColors.wdoColor !== "#848da2" ? 600 : 400 }}>WDO NWE</span>
                <span style={{ fontSize: 7.5, color: activeColors.diColor, fontWeight: activeColors.diColor !== "#848da2" ? 600 : 400 }}>DI NWE</span>
                <span style={{ fontSize: 7.5, color: activeColors.consColor, fontWeight: activeColors.consColor !== "#848da2" ? 600 : 400 }}>WDO DI</span>
            </div>

            {/* Legenda sutil das intensidades */}
            <div className="mw-mono" style={{
                position: "absolute", top: 3, right: 14,
                display: "flex", alignItems: "center", gap: 10,
                fontSize: 9, color: "var(--mw-text-3)",
                pointerEvents: "none", zIndex: 10, background: "rgba(14, 17, 24, 0.88)",
                padding: "2px 8px", borderRadius: 5, border: "1px solid var(--mw-hairline)"
            }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 6, height: 6, borderRadius: 1, background: "rgba(229, 72, 77, 0.35)", border: "1px solid rgba(229, 72, 77, 0.55)" }} />
                    <span>Gatilho Z</span>
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 6, height: 6, borderRadius: 1, background: "#e5484d", border: "1px solid #e5484d" }} />
                    <span style={{ color: "var(--mw-text-2)" }}>Setup completo + NWE</span>
                </span>
            </div>

            {/* Chart Area */}
            <div style={{ width: "100%", height: "80px", paddingLeft: Y_AXIS_WIDTH }} ref={chartContainerRef} />
            {(!data || data.length === 0) && (
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(14, 17, 24, 0.85)", zIndex: 10 }}>
                    <span className="mw-mono" style={{ color: "var(--mw-text-3)", fontSize: 12 }}>Aguardando abertura do mercado</span>
                </div>
            )}
        </div>
    );
});

SignalHistogram.displayName = 'SignalHistogram';
export default SignalHistogram;
