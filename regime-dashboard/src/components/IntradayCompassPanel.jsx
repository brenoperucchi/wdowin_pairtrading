import React, { useState, useRef, useEffect, useMemo, memo } from "react";

function fmtNum(v, decimals = 0, showSign = false) {
    if (v === undefined || v === null || Number.isNaN(Number(v))) return "—";
    const n = Number(v);
    const sign = showSign && n > 0 ? "+" : "";
    return sign + n.toLocaleString("pt-BR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function scoreColor(score) {
    const s = Number(score || 0);
    if (s >= 20) return "#00e87a";
    if (s <= -20) return "#ff3860";
    return "#f5a623";
}

function fmtDateShort(dStr) {
    if (!dStr || typeof dStr !== "string" || !dStr.includes("-")) return dStr || "";
    const [, m, d] = dStr.split("-");
    return `${d}/${m}`;
}

function fmtDateFull(dStr) {
    if (!dStr || typeof dStr !== "string" || !dStr.includes("-")) return dStr || "";
    const [y, m, d] = dStr.split("-");
    return `${d}/${m}/${y}`;
}

const WALLS_FLOW_6_IDS = ["WIN_DIV_WALL", "WDO_DIV_WALL"];
const WALLS_FLOW_6_SET = new Set(WALLS_FLOW_6_IDS);
const MT5_TOP6_IDS = ["EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07"];
const MT5_TOP6_SET = new Set(MT5_TOP6_IDS);

function isWallsFlowLocalhost() {
    if (typeof window === "undefined") return false;
    const port = String(window.location.port || "");
    const params = new URLSearchParams(window.location.search || "");
    if (params.get("mode") === "walls_flow") return true;
    if (params.get("mode") === "mt5") return false;
    return port === "5176";
}

function filterSignalsForHost(signalsLog = [], isWallsFlow = false) {
    if (!Array.isArray(signalsLog)) return [];
    if (isWallsFlow) {
        return signalsLog.filter((s) => s && WALLS_FLOW_6_SET.has(String(s.strategy_id || "")));
    }
    return signalsLog.filter((s) => s && MT5_TOP6_SET.has(String(s.strategy_id || "")));
}

const _M1_CHART_CACHE = {};
const _M1_CHART_INFLIGHT = {};
function fetchM1ChartByDate(dateKey, force = false) {
    const dk = String(dateKey || "").trim();
    const cacheKey = dk || "__LATEST__";
    if (!force && _M1_CHART_CACHE[cacheKey]) {
        return Promise.resolve(_M1_CHART_CACHE[cacheKey]);
    }
    if (!force && _M1_CHART_INFLIGHT[cacheKey]) {
        return _M1_CHART_INFLIGHT[cacheKey];
    }
    const url = dk
        ? `http://localhost:8080/api/compass/m1_series?date_str=${encodeURIComponent(dk)}`
        : "http://localhost:8080/api/compass/m1_series";
    const p = fetch(url)
        .then((r) => r.json())
        .then((data) => {
            delete _M1_CHART_INFLIGHT[cacheKey];
            if (data && data.ok) {
                _M1_CHART_CACHE[cacheKey] = data;
                if (data.date) _M1_CHART_CACHE[data.date] = data;
            }
            return data;
        })
        .catch((err) => {
            delete _M1_CHART_INFLIGHT[cacheKey];
            throw err;
        });
    _M1_CHART_INFLIGHT[cacheKey] = p;
    return p;
}

/* ══════════════════════════════════════════════════════════════════════════════
   1. GRÁFICO TRIPLO SINCRONIZADO ESTILO TRADINGVIEW ("FLUXO REAL + PINE GEX")
      - Visual Oficial TradingView Dark (#131722, grade #1e222d, Crosshair com tags de Preço/Hora)
      - Zoom no Scroll do Mouse + Pan Horizontal no Arraste + Zoom Vertical na Escala Y
      - Suporte nativo a M5 e M1 (com pré-carregamento em background para troca instantânea)
   ══════════════════════════════════════════════════════════════════════════════ */
function FluxoRealAsgChart({
    symKey,
    series: m5RawSeries,
    flowWindows: m5FlowWindows = [],
    signalsLog = [],
    asgHud = {},
    wallsRadar = {},
    allWalls = [],
    vwap,
    selectedSigId,
    onSelectSignal,
    showSignalsMarkers = true,
    wideMode = false,
    capitalDrawerInfo = null,
    sessionDate = "",
}) {
    const svgRef = useRef(null);
    const [chartTf, setChartTf] = useState("M5"); // "M5" | "M1"
    const [m1AssetData, setM1AssetData] = useState(null);
    const [m1Loading, setM1Loading] = useState(false);
    const [hoverPos, setHoverPos] = useState(null); // { idx, relX, relY }
    const [hoveredSigId, setHoveredSigId] = useState(null);
    const [rightGapPx, setRightGapPx] = useState(145);
    const [viewMode, setViewMode] = useState("HOJE"); // Padrão: Dia Todo fixo sem dar zoom indesejado
    const [visibleCount, setVisibleCount] = useState(120);
    const [panOffsetRight, setPanOffsetRight] = useState(0); // quantas barras deslocado do fim
    const [yZoomFactor, setYZoomFactor] = useState(1.0); // >1 abre mais o eixo Y para ver mais Walls do Pine
    const isWallsHost = isWallsFlowLocalhost();
    const [showMidleWalls, setShowMidleWalls] = useState(true);
    const [showNweLine, setShowNweLine] = useState(() => (isWallsFlowLocalhost() && symKey === "WIN")); // NWE30 ligada por padrão no WIN da 5176 (mostra TP1 Dinâmico)
    const [showWindowFlips, setShowWindowFlips] = useState(false); // Linhas verticais de virada de fluxo (toggle)
    const [showWallBattleLabels, setShowWallBattleLabels] = useState(false); // Escrita nos candles opcional (desativada na 5176)
    const [showSwingDivLines, setShowSwingDivLines] = useState(true); // Linhas de Divergência Topo/Fundo (F1->F2 / T1->T2) sincronizadas Preço x Fluxo
    const [wallColorMode, setWallColorMode] = useState("POLARIDADE"); // "POLARIDADE" (Smart Money) | "PINE" (#ffffff)
    const [candleColorMode, setCandleColorMode] = useState("TRADICIONAL"); // "TRADICIONAL" (padrão) | "JANELA" (fluxo Smart Money)
    const [flowSubMode, setFlowSubMode] = useState(() => (isWallsFlowLocalhost() ? "SWING_DIVERGENCIA" : "JANELA_ASG"));
    const [smWinVisualMode, setSmWinVisualMode] = useState("HIST_LINE"); // "HIST_LINE" (Histograma + Linha) | "LINE" (Só Linha) | "HIST" (Só Histograma)
    const [oscTf, setOscTf] = useState("5M");
    const [gexViewMode, setGexViewMode] = useState("OPCAO_1"); // Legado / reservado
    const [dragState, setDragState] = useState(null); // { type: 'PAN_P1' | 'PAN_P3' | 'YSCALE_P1' | 'YSCALE_P3' | 'SPLITTER', ... }
    const [priceYOffset, setPriceYOffset] = useState(0);
    const [priceAutoScale, setPriceAutoScale] = useState(true);
    const [flowYZoom, setFlowYZoom] = useState(1.0);
    const [flowYOffset, setFlowYOffset] = useState(0);
    const [flowAutoScale, setFlowAutoScale] = useState(true);
    const [flowPaneH, setFlowPaneH] = useState(() => (isWallsFlowLocalhost() ? 150 : 112));
    const [isChartFocused, setIsChartFocused] = useState(false);
    const [cursorZone, setCursorZone] = useState("PLOT"); // 'PLOT' | 'YAXIS' | 'SPLITTER'
    const tvMetricsRef = useRef(null);

    // Pré-carrega a série M1 em background assim que a data da sessão estiver disponível (troca M5 <-> M1 em 0ms)
    useEffect(() => {
        let cancelled = false;
        const dKey = String(sessionDate || "").trim();
        const cached = _M1_CHART_CACHE[dKey || "__LATEST__"];
        if (cached && cached[symKey]) {
            setM1AssetData(cached[symKey]);
        } else if (chartTf === "M1") {
            setM1Loading(true);
        }
        fetchM1ChartByDate(dKey)
            .then((data) => {
                if (cancelled) return;
                if (data && data.ok && data[symKey]) {
                    setM1AssetData(data[symKey]);
                }
                setM1Loading(false);
            })
            .catch(() => {
                if (!cancelled) setM1Loading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [sessionDate, symKey, chartTf]);

    const useM1Active = chartTf === "M1" && Array.isArray(m1AssetData?.m1_series) && m1AssetData.m1_series.length > 0;
    const rawSeries = useM1Active ? m1AssetData.m1_series : m5RawSeries;
    const flowWindows = useM1Active ? (m1AssetData.flow_windows || []) : m5FlowWindows;

    useEffect(() => {
        const svgEl = svgRef.current;
        if (!svgEl) return undefined;

        const handleWheelNative = (e) => {
            const m = tvMetricsRef.current;
            if (!m) return;
            const rect = svgEl.getBoundingClientRect();
            if (!(rect.width > 0 && rect.height > 0)) return;
            const relX = ((e.clientX - rect.left) / rect.width) * m.width;
            const relY = ((e.clientY - rect.top) / rect.height) * m.height;

            const onPriceAxis = relX > m.padL + m.plotW && relY >= m.p1Top && relY <= m.p1Bot;
            const onFlowAxis = relX > m.padL + m.plotW && relY >= m.p3Top && relY <= m.p3Bot;
            const onTimeAxis = relY > m.p3Bot;

            if (onPriceAxis) {
                e.preventDefault();
                setPriceAutoScale(false);
                setYZoomFactor((z) => +(Math.max(0.15, Math.min(6.0, z * (e.deltaY > 0 ? 1.14 : 0.88)))).toFixed(3));
                return;
            }
            if (onFlowAxis) {
                e.preventDefault();
                setFlowAutoScale(false);
                setFlowYZoom((z) => +(Math.max(0.15, Math.min(6.0, z * (e.deltaY > 0 ? 1.14 : 0.88)))).toFixed(3));
                return;
            }
            if (onTimeAxis || m.isChartFocused || e.ctrlKey || e.shiftKey || e.altKey) {
                e.preventDefault();
                const frac = Math.max(0, Math.min(1, (relX - (m.padL + m.innerPadL)) / Math.max(1, m.usableW)));
                const anchorBaseIdx = m.startSlice + frac * Math.max(1, m.effCount - 1);
                const rawNext = Math.round(m.effCount * (e.deltaY > 0 ? 1.16 : 0.86));
                const stepedNext = rawNext === m.effCount ? m.effCount + (e.deltaY > 0 ? 2 : -2) : rawNext;
                const nextCount = Math.max(12, Math.min(m.totalBase, stepedNext));
                const nextStart = Math.max(0, Math.min(m.totalBase - nextCount, Math.round(anchorBaseIdx - frac * Math.max(1, nextCount - 1))));
                const nextPanRight = Math.max(0, m.totalBase - (nextStart + nextCount));
                setViewMode("CUSTOM");
                setVisibleCount(nextCount);
                setPanOffsetRight(nextPanRight);
            }
        };

        const handleOutsideMouseDown = (e) => {
            if (svgEl && !svgEl.contains(e.target)) {
                setIsChartFocused(false);
            }
        };

        svgEl.addEventListener("wheel", handleWheelNative, { passive: false });
        window.addEventListener("mousedown", handleOutsideMouseDown);
        return () => {
            svgEl.removeEventListener("wheel", handleWheelNative);
            window.removeEventListener("mousedown", handleOutsideMouseDown);
        };
    }, [rawSeries?.length]);

    const getNweLine = (pt) => Number(isWallsHost ? (pt?.nwe30_line ?? pt?.nwe_line ?? 0) : (pt?.nwe_line ?? 0));
    const getNweUpper = (pt) => Number(isWallsHost ? (pt?.nwe30_upper ?? pt?.nwe_upper ?? 0) : (pt?.nwe_upper ?? 0));
    const getNweLower = (pt) => Number(isWallsHost ? (pt?.nwe30_lower ?? pt?.nwe_lower ?? 0) : (pt?.nwe_lower ?? 0));
    const getNweIsUp = (pt) => (isWallsHost ? (pt?.nwe30_is_up ?? pt?.nwe_is_up) : pt?.nwe_is_up);

    const dec = symKey === "WDO" ? 1 : 0;

    if (!rawSeries || rawSeries.length < 1) {
        return (
            <div style={{
                height: 540,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#7f96a8",
                fontSize: 13,
                background: "#0c1218",
                borderRadius: 10,
                border: "1px solid #1a2530",
            }}>
                Aguardando histórico M5 da sessão para plotar o Gráfico Fluxo Real + Pine GEX...
            </div>
        );
    }

    const indexedSeries = rawSeries.map((pt, i) => ({ ...pt, _origIdx: i }));
    const hasPrevDayWarmup = indexedSeries.some(pt => pt.is_prev_day) && indexedSeries.some(pt => !pt.is_prev_day);

    let baseSeries = indexedSeries;
    if (viewMode === "HOJE" && hasPrevDayWarmup) {
        baseSeries = indexedSeries.filter(pt => !pt.is_prev_day);
    }
    if (baseSeries.length < 1) baseSeries = indexedSeries;

    const totalBase = baseSeries.length;
    const effCount = (viewMode === "TUDO" || viewMode === "HOJE")
        ? totalBase
        : Math.max(14, Math.min(totalBase, visibleCount));
    const maxPan = Math.max(0, totalBase - effCount);
    const clampedPan = Math.max(0, Math.min(maxPan, panOffsetRight));
    const endSlice = totalBase - clampedPan;
    const startSlice = Math.max(0, endSlice - effCount);
    const series = baseSeries.slice(startSlice, endSlice);

    const width = wideMode ? 1240 : 900;
    const height = isWallsHost ? 590 : 544;
    const padL = 10;
    const padR = 118; // Eixo Y estilo TradingView à direita

    // Layout Dinâmico estilo TradingView em 2 Painéis Verticais Redimensionáveis:
    const bottomAxisH = 26;
    const splitterGap = 12;
    const clampedFlowH = Math.max(82, Math.min(height - 210, flowPaneH));
    const p1Top = 14;
    const p1H = Math.max(180, height - p1Top - bottomAxisH - splitterGap - clampedFlowH);
    const p1Bot = p1Top + p1H;
    const p2Top = 0, p2H = 0, p2Bot = 0; // Removido (Fluxo CVD)
    const pGexTop = 0, pGexH = 0, pGexBot = 0; // Removido (Hedge Makers GEX)
    const p3Top = p1Bot + splitterGap;
    const p3H = clampedFlowH;
    const p3Bot = p3Top + p3H;
    const splitterMidY = (p1Bot + p3Top) / 2;
    const plotW = width - padL - padR;

    const innerPadL = 16;
    const usableW = Math.max(180, plotW - innerPadL - rightGapPx);
    const n = series.length;
    const totalSlots = Math.max(n - 1, 14);
    const stepX = usableW / Math.max(1, totalSlots);
    const candleW = Math.max(useM1Active ? 1.4 : 3.2, Math.min(13.5, stepX * 0.72));
    const toX = (idx) => padL + innerPadL + (idx / Math.max(1, totalSlots)) * usableW;
    const firstTodayLocalIdx = series.findIndex((pt, i) => i > 0 && !pt.is_prev_day && series[i - 1]?.is_prev_day);

    // ── Escala Y Variável estilo TradingView do Painel 1 (Preço + Walls + Caixas de Trade) ──
    let minP = Infinity;
    let maxP = -Infinity;
    const visTodayTimes = new Set();
    series.forEach(pt => {
        const l = Number(pt.low || pt.close);
        const h = Number(pt.high || pt.close);
        if (l > 0 && l < minP) minP = l;
        if (h > 0 && h > maxP) maxP = h;
        if (!pt.is_prev_day && pt.time) visTodayTimes.add(pt.time);
        if (showNweLine && getNweLine(pt) > 0) {
            const nl = getNweLine(pt);
            const nu = getNweUpper(pt) || nl;
            const nlo = getNweLower(pt) || nl;
            if (nlo > 0 && nlo < minP) minP = nlo;
            if (nu > 0 && nu > maxP) maxP = nu;
        }
    });
    const hostSignalsLog = filterSignalsForHost(signalsLog, isWallsFlowLocalhost());
    if (showSignalsMarkers && hostSignalsLog.length > 0) {
        hostSignalsLog.forEach(s => {
            if (!s || s.is_prev_day || !visTodayTimes.has(s.time)) return;
            const sp = Number(s.stop_price || 0);
            const tp = Number(s.tp_price || 0);
            if (sp > 0) {
                if (sp < minP) minP = sp;
                if (sp > maxP) maxP = sp;
            }
            if (tp > 0) {
                if (tp < minP) minP = tp;
                if (tp > maxP) maxP = tp;
            }
        });
    }

    // Inclui automaticamente a MagicWall/MidWall imediata quando em modo Auto
    const sup0 = wallsRadar?.support_walls?.[0]?.price;
    const res0 = wallsRadar?.resistance_walls?.[0]?.price;
    const rngRaw = Math.max(1, maxP - minP);
    if (priceAutoScale) {
        if (sup0 && sup0 > 0 && (minP - sup0) <= rngRaw * 0.45) minP = Math.min(minP, sup0);
        if (res0 && res0 > 0 && (res0 - maxP) <= rngRaw * 0.45) maxP = Math.max(maxP, res0);
    }

    const baseMidP = (maxP + minP) / 2;
    const effPriceOffset = priceAutoScale ? 0 : priceYOffset;
    const halfSpan = Math.max(symKey === "WDO" ? 1.8 : 45, ((maxP - minP) / 2) * 1.15 * yZoomFactor);
    minP = (baseMidP + effPriceOffset) - halfSpan;
    maxP = (baseMidP + effPriceOffset) + halfSpan;
    const rangeP = Math.max(1e-6, maxP - minP);
    const toY1 = (p) => p1Top + p1H - ((Number(p) - minP) / rangeP) * p1H;
    const fromY1 = (y) => minP + ((p1Bot - y) / p1H) * rangeP;

    // Marcações regulares (ticks) da Escala de Preço estilo TradingView
    const priceAxisTicks = (() => {
        const rawStep = rangeP / Math.max(4, Math.round(p1H / 58));
        const niceSteps = symKey === "WDO"
            ? [0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100]
            : [25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000];
        const step = niceSteps.find(st => st >= rawStep) || Math.max(1, Math.ceil(rawStep));
        const firstTick = Math.ceil(minP / step) * step;
        const arr = [];
        for (let val = firstTick; val <= maxP + 1e-6 && arr.length < 18; val += step) {
            const y = toY1(val);
            if (y >= p1Top + 14 && y <= p1Bot - 14) {
                arr.push({ price: +val.toFixed(2), y });
            }
        }
        return arr;
    })();

    // ── Escala Y do Painel 2 (Fluxo Institucional CVD) ──
    let minF = Infinity;
    let maxF = -Infinity;
    series.forEach(pt => {
        const fo = Number(pt.flow_open ?? pt.cvd_inst ?? 0);
        const fc = Number(pt.flow_close ?? pt.cvd_inst ?? 0);
        minF = Math.min(minF, fo, fc);
        maxF = Math.max(maxF, fo, fc);
    });
    if (!Number.isFinite(minF) || !Number.isFinite(maxF) || maxF <= minF) {
        minF = -1000;
        maxF = 1000;
    }
    const padF = (maxF - minF) * 0.12 || 100;
    minF -= padF;
    maxF += padF;
    const rangeF = Math.max(1e-6, maxF - minF);
    const toY2 = (v) => p2Top + p2H - ((Number(v) - minF) / rangeF) * p2H;

    // ── Escala Y do Painel 3 (Opção 1: Hedge Acumulado dos Makers | Opção 3: Mapa de Atração / Ímã GEX) ──
    const getCumDealer = (pt) => Number(pt?.cum_dealer_hedge || 0);
    let minD = Infinity;
    let maxD = -Infinity;
    series.forEach(pt => {
        const dc = getCumDealer(pt);
        if (dc < minD) minD = dc;
        if (dc > maxD) maxD = dc;
    });
    if (!Number.isFinite(minD) || !Number.isFinite(maxD) || maxD <= minD) {
        minD = -1000;
        maxD = 1000;
    }
    const padD = (maxD - minD) * 0.14 || 100;
    minD -= padD;
    maxD += padD;
    const rangeD = Math.max(1e-6, maxD - minD);
    const toYGexCum = (v) => pGexTop + pGexH - ((Number(v) - minD) / rangeD) * pGexH;

    const getMagnetPct = (pt) => {
        if (pt?.gex_magnet_pct !== undefined && pt?.gex_magnet_pct !== null) {
            return Number(pt.gex_magnet_pct);
        }
        return Number(pt?.makers_pct_bar || 0) * 35;
    };
    let maxAbsMag = 25;
    series.forEach(pt => {
        const mv = Math.abs(getMagnetPct(pt));
        if (mv > maxAbsMag) maxAbsMag = mv;
    });
    maxAbsMag = Math.min(100, Math.max(25, maxAbsMag * 1.15));
    const yZeroGex = pGexTop + pGexH / 2;
    const toYGexMag = (mv) => yZeroGex - (Number(mv || 0) / maxAbsMag) * (pGexH * 0.42);

    // ── Escala Y do Painel 4 (Histograma Linha Zero -100 a +100 + Modos de Divergência Não-Varejo) ──
    let maxAbsH = 25;
    series.forEach(pt => {
        const hv = Math.abs(Number(pt.flow_hist || 0));
        if (hv > maxAbsH) maxAbsH = hv;
    });
    maxAbsH = Math.min(100, maxAbsH * 1.12);
    const yZero3 = p3Top + 14 + (p3H - 14) / 2;
    const halfH3 = (p3H - 22) * 0.44;
    const toY3 = (hv) => yZero3 - (Number(hv || 0) / maxAbsH) * halfH3;

    // ── Métricas Barra a Barra para os Modos de Divergência (Onda Efetiva 3-Motores / Cabo de Guerra / Oscilador / CVD 4-Players) ──
    const isWinSym = symKey === "WIN";
    let maxCaboVal = isWinSym ? 800 : 120;
    let maxOscPrice = isWinSym ? 150 : 3.5;
    let maxOscNr = isWinSym ? 1200 : 180;
    let minCvd4 = 0;
    let maxCvd4 = 0;
    let maxSwingWaveAbs = isWinSym ? 4000 : 500;

    let cumEffFallback = 0;
    let ema3Fallback = 0;
    let ema10Fallback = 0;

    const subPanelBars = series.map((pt, idx) => {
        const c = Number(pt.close || 0);
        const o = Number(pt.open ?? c);
        const h = Number(pt.high || c);
        const l = Number(pt.low || c);
        const rng = Math.max(h - l, isWinSym ? 5.0 : 0.5);
        const c1 = Number(series[Math.max(0, idx - 1)]?.close || c);
        const c2 = Number(series[Math.max(0, idx - 2)]?.close || c);
        const c3 = Number(series[Math.max(0, idx - 3)]?.close || c);
        const dpBar = (c - o) !== 0 ? (c - o) : (c - c1);
        const dp1 = c - c1;
        const dp2 = c - c2;
        const dp3 = c - c3;

        const ia5 = Number(pt.inst_aggr_delta ?? pt.inst_delta_bar ?? 0);
        const ip5 = Number(pt.inst_pass_delta ?? 0);
        const nr5 = ia5 + ip5;
        const r5 = Number(pt.ret_delta_bar ?? 0);
        const h5 = Number(pt.hft_delta_bar ?? 0);
        const rlpSh = Number(pt.rlp_share_pct ?? pt.rlp_pct ?? 28);
        const rlp5 = Number(pt.rlp_delta_bar ?? Math.round(-r5 * Math.max(0.32, Math.min(0.75, rlpSh / 100.0))));
        const lotImb = Number(pt.lot_imb || 1.0);

        // ── Matemática Agnóstica de Corretora (3 Motores do que realmente move o preço) ──
        const bv = Number(pt.buy_vol || 0);
        const sv = Number(pt.sell_vol || 0);
        const tv = bv + sv;
        const uw = Math.max(0, h - Math.max(o, c));
        const lw = Math.max(0, Math.min(o, c) - l);
        const closePos = (c - l) / rng;
        const wyckoffBuyAbs = sv * closePos * (0.8 + 1.4 * (lw / rng));
        const wyckoffSellAbs = bv * (1.0 - closePos) * (0.8 + 1.4 * (uw / rng));
        const wyckoffAbs = pt.wyckoff_abs_bar !== undefined
            ? Number(pt.wyckoff_abs_bar)
            : (wyckoffBuyAbs - wyckoffSellAbs);

        const abl = Number(pt.avg_buy_lot || 0);
        const asl = Number(pt.avg_sell_lot || 0);
        const lotAsym = (abl + asl) > 0 ? ((abl - asl) / (abl + asl)) : 0;
        const lotUrgency = pt.lot_urgency_bar !== undefined
            ? Number(pt.lot_urgency_bar)
            : (tv * lotAsym * 2.2);

        const smartInst = pt.smart_inst_bar !== undefined
            ? Number(pt.smart_inst_bar)
            : (0.55 * ia5 + 1.15 * ip5 - 0.85 * r5);

        const effForce = pt.effective_force_bar !== undefined
            ? Number(pt.effective_force_bar)
            : (0.45 * wyckoffAbs + 0.30 * lotUrgency + 0.25 * smartInst);

        if (idx === 0 || (pt && !pt.is_prev_day && series[idx - 1]?.is_prev_day)) {
            cumEffFallback = effForce;
            ema3Fallback = cumEffFallback;
            ema10Fallback = cumEffFallback;
        } else {
            cumEffFallback += effForce;
            ema3Fallback = 0.50 * cumEffFallback + 0.50 * ema3Fallback;
            ema10Fallback = (2.0 / 11.0) * cumEffFallback + (9.0 / 11.0) * ema10Fallback;
        }

        let ia10 = 0, ip10 = 0, r10 = 0;
        for (let k = Math.max(0, idx - 1); k <= idx; k++) {
            const pk = series[k] || {};
            ia10 += Number(pk.inst_aggr_delta ?? pk.inst_delta_bar ?? 0);
            ip10 += Number(pk.inst_pass_delta ?? 0);
            r10 += Number(pk.ret_delta_bar ?? 0);
        }
        const nr10 = ia10 + ip10;

        let ia15 = 0, ip15 = 0, r15 = 0;
        for (let k = Math.max(0, idx - 2); k <= idx; k++) {
            const pk = series[k] || {};
            ia15 += Number(pk.inst_aggr_delta ?? pk.inst_delta_bar ?? 0);
            ip15 += Number(pk.inst_pass_delta ?? 0);
            r15 += Number(pk.ret_delta_bar ?? 0);
        }
        const nr15 = ia15 + ip15;

        const dpOsc = oscTf === "5M" ? dpBar : (oscTf === "10M" ? dp2 : dp3);
        const nrOsc = oscTf === "5M" ? nr5 : (oscTf === "10M" ? nr10 : nr15);
        const rOsc = oscTf === "5M" ? r5 : (oscTf === "10M" ? r10 : r15);

        const posStack = (ia5 > 0 ? ia5 : 0) + (ip5 > 0 ? ip5 : 0);
        const negStack = (ia5 < 0 ? Math.abs(ia5) : 0) + (ip5 < 0 ? Math.abs(ip5) : 0);
        const barMax = Math.max(posStack, negStack, Math.abs(r5));
        if (barMax > maxCaboVal) maxCaboVal = barMax;
        if (Math.abs(dpOsc) > maxOscPrice) maxOscPrice = Math.abs(dpOsc);
        if (Math.max(Math.abs(nrOsc), Math.abs(rOsc)) > maxOscNr) maxOscNr = Math.max(Math.abs(nrOsc), Math.abs(rOsc));

        const cvdIa = Number(pt.cvd_inst_aggr ?? pt.cvd_inst ?? 0);
        const cvdIp = Number(pt.cvd_inst_pass ?? 0);
        const cvdRet = Number(pt.cvd_retail ?? 0);
        const cvdHft = Number(pt.cvd_hft ?? 0);
        const cvdRlp = Number(pt.cvd_rlp_delta ?? Math.round(-cvdRet * 0.42));
        minCvd4 = Math.min(minCvd4, cvdIa, cvdIp, cvdRet, cvdHft, cvdRlp);
        maxCvd4 = Math.max(maxCvd4, cvdIa, cvdIp, cvdRet, cvdHft, cvdRlp);

        // Classificação da Divergência / Assinatura na Barra M5
        const fomoBuyTrap = r5 > (isWinSym ? 450 : 65) && ip5 < (isWinSym ? -250 : -40) && ia5 <= 0;
        const fomoSellTrap = r5 < (isWinSym ? -450 : -65) && ip5 > (isWinSym ? 250 : 40) && ia5 >= 0;
        const bullDiv = !fomoBuyTrap && (
            ((dp1 <= 0 || c <= o) && (ip5 > (isWinSym ? 250 : 40) || nr5 > (isWinSym ? 650 : 90) || wyckoffAbs > (isWinSym ? 4000 : 450)))
            || (r5 < (isWinSym ? -300 : -45) && (ip5 >= (isWinSym ? 150 : 25) || ia5 > (isWinSym ? 350 : 50)))
            || (dp3 < (isWinSym ? -120 : -3.0) && nr15 > (isWinSym ? 900 : 140))
        );
        const bearDiv = !fomoSellTrap && (
            ((dp1 >= 0 || c >= o) && (ip5 < (isWinSym ? -250 : -40) || nr5 < (isWinSym ? -650 : -90) || wyckoffAbs < (isWinSym ? -4000 : -450)))
            || (r5 > (isWinSym ? 300 : 45) && (ip5 <= (isWinSym ? -150 : -25) || ia5 < (isWinSym ? -350 : -50)))
            || (dp3 > (isWinSym ? 120 : 3.0) && nr15 < (isWinSym ? -900 : -140))
        );
        const sweepBuy = ia5 > (isWinSym ? 1600 : 220) && nr5 > 0 && lotImb >= 1.03;
        const sweepSell = ia5 < (isWinSym ? -1600 : -220) && nr5 < 0 && lotImb <= 0.97;

        let divType = null;
        let divLabel = "⚪ Fluxo Alinhado";
        let divColor = "#7f96a8";
        let divShort = "";

        if (fomoBuyTrap) {
            divType = "TRAP_FOMO_BUY";
            divLabel = "⚠️ ARMADILHA FOMO COMPRA (Varejo Comprando Topo vs Inst Absorvendo na Venda)";
            divColor = "#ffd600";
            divShort = "⚠️FOMO";
        } else if (fomoSellTrap) {
            divType = "TRAP_FOMO_SELL";
            divLabel = "🪤 ARMADILHA VENDA VAREJO (Varejo Vendendo Fundo vs Inst Absorvendo na Compra)";
            divColor = "#00e87a";
            divShort = "🪤TRAP";
        } else if (bullDiv) {
            divType = "BULL_DIV";
            divLabel = "🟢 DIVERGÊNCIA COMPRA (Preço/Varejo Caindo vs Absorção Wyckoff / Não-Varejo Compradora)";
            divColor = "#00e87a";
            divShort = "🛡️DIV▲";
        } else if (bearDiv) {
            divType = "BEAR_DIV";
            divLabel = "🔴 DIVERGÊNCIA VENDA (Preço/Varejo Subindo vs Absorção Wyckoff / Distribuição Vendedora)";
            divColor = "#ff3860";
            divShort = "🛡️DIV▼";
        } else if (sweepBuy) {
            divType = "SWEEP_BUY";
            divLabel = "💥 SWEEP INSTITUCIONAL COMPRA (Tomada Agressiva Não-Varejo + Ticket Alto)";
            divColor = "#00d4ff";
            divShort = "💥SWP▲";
        } else if (sweepSell) {
            divType = "SWEEP_SELL";
            divLabel = "💥 SWEEP INSTITUCIONAL VENDA (Batida Agressiva Não-Varejo + Ticket Alto)";
            divColor = "#fb7185";
            divShort = "💥SWP▼";
        }

        return {
            idx, c, o, h, l, bv, sv, abl, asl,
            dp1, dp2, dp3, dpOsc, ia5, ip5, nr5, r5, h5, rlp5, ia15, ip15, nr15, r15, nrOsc, rOsc,
            wyckoffAbs, lotUrgency, smartInst, effForce,
            detrendedFallback: ema3Fallback - ema10Fallback,
            cvdIa, cvdIp, cvdRet, cvdHft, cvdRlp,
            divType, divLabel, divColor, divShort,
        };
    });

    // Segunda passagem para finalizar a Onda de Fluxo Efetivo de Swing (smartSwingWave)
    subPanelBars.forEach((sb, idx) => {
        const pt = series[idx] || {};
        let imp3 = 0;
        for (let k = Math.max(0, idx - 2); k <= idx; k++) {
            imp3 += subPanelBars[k].effForce;
        }
        const waveVal = pt.smart_swing_wave !== undefined
            ? Number(pt.smart_swing_wave)
            : (0.55 * imp3 + 0.45 * sb.detrendedFallback);
        sb.swingImpulse3b = pt.swing_impulse_3b !== undefined ? Number(pt.swing_impulse_3b) : imp3;
        sb.smartSwingWave = waveVal;
        const absWave = Math.max(Math.abs(waveVal), Math.abs(sb.effForce * 1.4));
        if (absWave > maxSwingWaveAbs) maxSwingWaveAbs = absWave;
    });

    // ── Detector Causal de Divergências de Topo e Fundo (F1 -> F2 e T1 -> T2) sincronizado na Janela Visível ──
    const swingDivergences = [];
    {
        const isWallsFlow = isWallsFlowLocalhost();
        const pTolDiv = isWinSym ? 50.0 : 1.5;
        const maxExtDiv = isWinSym ? 360.0 : 8.5;
        const wRadDiv = isWinSym ? 130.0 : 3.0;
        const wallPricesArr = [
            ...((Array.isArray(allWalls) ? allWalls : []).map(w => Number(w.price || 0))),
            ...((wallsRadar?.resistance_walls || []).map(w => Number(w.price || 0))),
            ...((wallsRadar?.support_walls || []).map(w => Number(w.price || 0))),
        ].filter(p => p > 0);

        const todayIdxByTime = {};
        series.forEach((pt, idxS) => {
            if (!pt?.is_prev_day && pt?.time) todayIdxByTime[String(pt.time)] = idxS;
        });

        const sniperTrades = isWallsFlow
            ? (hostSignalsLog || [])
                .filter(s => s && !s.is_prev_day && todayIdxByTime[String(s.time)] !== undefined)
                .map(s => ({
                    tradeIdx: todayIdxByTime[String(s.time)],
                    dir: s.direction === "COMPRA" ? 1 : -1,
                    time: String(s.time),
                    exitTime: String(s.exit_time || "23:59"),
                    brl: Number(s.brl_1c || 0),
                    isClosed: s.is_valid !== null && s.is_valid !== undefined && String(s.validation_status || "").toUpperCase() !== "EM_ANDAMENTO",
                }))
            : [];

        let dailyCapHitTime = null;
        let dailyRealizedSum = 0;
        if (isWallsFlow) {
            const capTarget = isWinSym ? 180.0 : 120.0;
            const allDayClosedSorted = (hostSignalsLog || [])
                .filter(s => s && !s.is_prev_day && s.is_valid !== null && s.is_valid !== undefined && String(s.validation_status || "").toUpperCase() !== "EM_ANDAMENTO")
                .map(s => ({ exitTime: String(s.exit_time || "23:59"), brl: Number(s.brl_1c || 0) }))
                .sort((a, b) => a.exitTime.localeCompare(b.exitTime));
            for (const ct of allDayClosedSorted) {
                dailyRealizedSum += ct.brl;
                if (dailyRealizedSum >= capTarget && !dailyCapHitTime) {
                    dailyCapHitTime = ct.exitTime;
                }
            }
        }

        const isInSniperHours = (tStr) => {
            if (!tStr) return false;
            if (isWinSym) {
                return tStr >= "09:05" && tStr <= "16:45" && !(tStr >= "12:00" && tStr <= "12:55");
            }
            return tStr >= "09:00" && tStr <= "17:00" && !(tStr >= "11:00" && tStr <= "11:55");
        };

        if (isWallsFlow) {
            subPanelBars.forEach((sb, idxS) => {
                const ptS = series[idxS];
                if (!ptS || ptS.is_prev_day) return;
                const tS = String(ptS.time || "");
                if (dailyCapHitTime && tS > dailyCapHitTime) {
                    sb.divType = null;
                    sb.divColor = "#00d4ff";
                    sb.divLabel = `🔒 Meta Diária Atingida (+R$ ${fmtNum(dailyRealizedSum, 0)}) · Novas entradas bloqueadas`;
                } else if (!isInSniperHours(tS)) {
                    sb.divType = null;
                    sb.divColor = "#6b8599";
                    sb.divLabel = `⏸️ Fora do Horário Operacional (${isWinSym ? "09:05–16:45 s/ 12h" : "09:00–17:00 s/ 11h NY"})`;
                } else if (sb.divType === "BULL_DIV" || sb.divType === "BEAR_DIV") {
                    // Evita exibir divergência de 1 barra no HUD se não for divergência F1->F2 / T1->T2 confirmada
                    sb.divType = null;
                    sb.divColor = "#7f96a8";
                    sb.divLabel = "⚪ Monitorando Fluxo na Wall";
                }
            });
        }

        let lastBullIdx = -12;
        let lastBearIdx = -12;

        for (let i = 4; i < subPanelBars.length; i++) {
            const pt = series[i];
            if (pt?.is_prev_day) continue;
            const sb = subPanelBars[i];
            const prevSb = subPanelBars[i - 1];
            const prev2Sb = subPanelBars[i - 2];

            const l2 = Math.min(sb.l, prevSb.l);
            const h2 = Math.max(sb.h, prevSb.h);
            const wLow2 = Math.min(sb.smartSwingWave, prevSb.smartSwingWave, prev2Sb.smartSwingWave);
            const wHigh2 = Math.max(sb.smartSwingWave, prevSb.smartSwingWave, prev2Sb.smartSwingWave);

            const isLocalBottom = (
                l2 <= Math.min(prev2Sb.l, subPanelBars[i - 3].l) + (isWinSym ? 20.0 : 0.5)
                && (sb.c >= sb.l + (sb.h - sb.l) * 0.35 || sb.c >= prevSb.c || sb.wyckoffAbs > 0)
                && (sb.effForce > 0 || sb.wyckoffAbs > 0 || sb.smartSwingWave > 0)
            );
            const isLocalTop = (
                h2 >= Math.max(prev2Sb.h, subPanelBars[i - 3].h) - (isWinSym ? 20.0 : 0.5)
                && (sb.c <= sb.h - (sb.h - sb.l) * 0.35 || sb.c <= prevSb.c || sb.wyckoffAbs < 0)
                && (sb.effForce < 0 || sb.wyckoffAbs < 0 || sb.smartSwingWave < 0)
            );

            // 1. Divergência de Fundo Compradora (F1 -> F2)
            if (isLocalBottom) {
                let bestP1 = null;
                const jStart = Math.max(1, i - 16);
                const jEnd = i - 3;
                for (let j = jStart; j <= jEnd; j++) {
                    if (series[j]?.is_prev_day) continue;
                    const lj = subPanelBars[j].l;
                    const lPrev = subPanelBars[Math.max(0, j - 1)].l;
                    const lNext = subPanelBars[Math.min(i - 1, j + 1)].l;
                    if (lj <= lPrev && lj <= lNext) {
                        const wj = Math.min(
                            subPanelBars[j].smartSwingWave,
                            subPanelBars[Math.max(0, j - 1)].smartSwingWave,
                            subPanelBars[Math.min(i - 1, j + 1)].smartSwingWave,
                        );
                        if (!bestP1 || lj < bestP1.price) {
                            bestP1 = { idx: j, price: lj, wave: wj, sv: subPanelBars[j].sv, time: series[j]?.time };
                        }
                    }
                }
                if (bestP1) {
                    const priceLowerOrDouble = (l2 >= bestP1.price - maxExtDiv) && (l2 <= bestP1.price + pTolDiv);
                    const waveHigherLow = (
                        wLow2 > bestP1.wave + Math.max(isWinSym ? 1500.0 : 180.0, Math.abs(bestP1.wave) * 0.18)
                        || (bestP1.wave < 0 && sb.smartSwingWave > 0)
                    );
                    const svExhausted = (sb.sv < bestP1.sv * 0.90) || (sb.wyckoffAbs > 0) || (sb.abl >= sb.asl);
                    if (priceLowerOrDouble && waveHigherLow && svExhausted) {
                        const nearW = wallPricesArr.some(wp => Math.abs(l2 - wp) <= wRadDiv || Math.abs(sb.c - wp) <= wRadDiv);
                        const driverTxt = sb.wyckoffAbs > Math.abs(sb.lotUrgency)
                            ? "Absorção Oculta Wyckoff na Pedra"
                            : (sb.lotUrgency > 0 ? "Urgência Lote Institucional" : "Exaustão Vendedora + Defesa Passiva");
                        if (i - lastBullIdx > 6) {
                            lastBullIdx = i;
                            const tCurr = String(series[i]?.time || "");
                            const matchedTrade = isWallsFlow && sniperTrades.some(t => t.dir === 1 && i <= t.tradeIdx && t.tradeIdx <= i + 3);
                            const isLivePending = isWallsFlow && !matchedTrade && (i >= subPanelBars.length - 3) && nearW && isInSniperHours(tCurr) && (!dailyCapHitTime || tCurr < dailyCapHitTime);
                            if (!isWallsFlow || matchedTrade || isLivePending) {
                                const divObj = {
                                    type: "BULL_DIV",
                                    prevIdx: bestP1.idx,
                                    prevTime: bestP1.time,
                                    prevPrice: bestP1.price,
                                    prevWave: bestP1.wave,
                                    currIdx: sb.l <= prevSb.l ? i : i - 1,
                                    currTime: series[i]?.time,
                                    currPrice: l2,
                                    currWave: Math.max(wLow2, sb.smartSwingWave),
                                    nearWall: nearW || matchedTrade,
                                    isPendingTrigger: Boolean(isLivePending),
                                    driver: driverTxt,
                                };
                                swingDivergences.push(divObj);
                                sb.swingDiv = divObj;
                                sb.divType = "BULL_DIV";
                                sb.divColor = "#00e87a";
                                sb.divLabel = `🟢 DIV. COMPRA DE FUNDO (${bestP1.time} ➔ ${series[i]?.time}): Preço ${fmtNum(bestP1.price, dec)} ➔ ${fmtNum(l2, dec)} ↘ | Fluxo Subiu ↗ (${driverTxt})`;
                            }
                        }
                    }
                }
            }

            // 2. Divergência de Topo Vendedora (T1 -> T2)
            if (isLocalTop) {
                let bestT1 = null;
                const jStart = Math.max(1, i - 16);
                const jEnd = i - 3;
                for (let j = jStart; j <= jEnd; j++) {
                    if (series[j]?.is_prev_day) continue;
                    const hj = subPanelBars[j].h;
                    const hPrev = subPanelBars[Math.max(0, j - 1)].h;
                    const hNext = subPanelBars[Math.min(i - 1, j + 1)].h;
                    if (hj >= hPrev && hj >= hNext) {
                        const wj = Math.max(
                            subPanelBars[j].smartSwingWave,
                            subPanelBars[Math.max(0, j - 1)].smartSwingWave,
                            subPanelBars[Math.min(i - 1, j + 1)].smartSwingWave,
                        );
                        if (!bestT1 || hj > bestT1.price) {
                            bestT1 = { idx: j, price: hj, wave: wj, bv: subPanelBars[j].bv, time: series[j]?.time };
                        }
                    }
                }
                if (bestT1) {
                    const priceHigherOrDouble = (h2 >= bestT1.price - pTolDiv) && (h2 <= bestT1.price + maxExtDiv);
                    const waveLowerHigh = (
                        wHigh2 < bestT1.wave - Math.max(isWinSym ? 1500.0 : 180.0, Math.abs(bestT1.wave) * 0.18)
                        || (bestT1.wave > 0 && sb.smartSwingWave < 0)
                    );
                    const bvExhausted = (sb.bv < bestT1.bv * 0.90) || (sb.wyckoffAbs < 0) || (sb.asl >= sb.abl);
                    if (priceHigherOrDouble && waveLowerHigh && bvExhausted) {
                        const nearW = wallPricesArr.some(wp => Math.abs(h2 - wp) <= wRadDiv || Math.abs(sb.c - wp) <= wRadDiv);
                        const driverTxt = sb.wyckoffAbs < -Math.abs(sb.lotUrgency)
                            ? "Absorção Vendedora Wyckoff no Topo"
                            : (sb.lotUrgency < 0 ? "Lote Vendedor Pesado" : "Exaustão Compradora + Oferta Passiva");
                        if (i - lastBearIdx > 6) {
                            lastBearIdx = i;
                            const tCurr = String(series[i]?.time || "");
                            const matchedTrade = isWallsFlow && sniperTrades.some(t => t.dir === -1 && i <= t.tradeIdx && t.tradeIdx <= i + 3);
                            const isLivePending = isWallsFlow && !matchedTrade && (i >= subPanelBars.length - 3) && nearW && isInSniperHours(tCurr) && (!dailyCapHitTime || tCurr < dailyCapHitTime);
                            if (!isWallsFlow || matchedTrade || isLivePending) {
                                const divObj = {
                                    type: "BEAR_DIV",
                                    prevIdx: bestT1.idx,
                                    prevTime: bestT1.time,
                                    prevPrice: bestT1.price,
                                    prevWave: bestT1.wave,
                                    currIdx: sb.h >= prevSb.h ? i : i - 1,
                                    currTime: series[i]?.time,
                                    currPrice: h2,
                                    currWave: Math.min(wHigh2, sb.smartSwingWave),
                                    nearWall: nearW || matchedTrade,
                                    isPendingTrigger: Boolean(isLivePending),
                                    driver: driverTxt,
                                };
                                swingDivergences.push(divObj);
                                sb.swingDiv = divObj;
                                sb.divType = "BEAR_DIV";
                                sb.divColor = "#ff3860";
                                sb.divLabel = `🔴 DIV. VENDA DE TOPO (${bestT1.time} ➔ ${series[i]?.time}): Preço ${fmtNum(bestT1.price, dec)} ➔ ${fmtNum(h2, dec)} ↗ | Fluxo Caiu ↘ (${driverTxt})`;
                            }
                        }
                    }
                }
            }
        }
    }

    maxCaboVal = Math.max(100, maxCaboVal * 1.10);
    maxSwingWaveAbs = Math.max(isWinSym ? 2500 : 300, maxSwingWaveAbs * 1.15);
    const toYCabo = (val) => yZero3 - (Number(val || 0) / maxCaboVal) * halfH3;

    // ── Escala Y Variável Dinâmica do Fluxo Smart Money (estilo TradingView: adapta às barras visíveis + zoom/pan livre) ──
    let rawMinWave = Infinity;
    let rawMaxWave = -Infinity;
    subPanelBars.forEach((sb) => {
        const wv = Number(sb.smartSwingWave || 0);
        if (wv < rawMinWave) rawMinWave = wv;
        if (wv > rawMaxWave) rawMaxWave = wv;
    });
    swingDivergences.forEach((dv) => {
        if (dv.prevWave < rawMinWave) rawMinWave = dv.prevWave;
        if (dv.prevWave > rawMaxWave) rawMaxWave = dv.prevWave;
        if (dv.currWave < rawMinWave) rawMinWave = dv.currWave;
        if (dv.currWave > rawMaxWave) rawMaxWave = dv.currWave;
    });
    if (!Number.isFinite(rawMinWave) || !Number.isFinite(rawMaxWave)) {
        rawMinWave = isWinSym ? -2000 : -250;
        rawMaxWave = isWinSym ? 2000 : 250;
    }
    const baseMidWave = (rawMaxWave + rawMinWave) / 2;
    const rawHalfWave = Math.max(isWinSym ? 350 : 50, (rawMaxWave - rawMinWave) / 2);
    const effFlowOffset = flowAutoScale ? 0 : flowYOffset;
    const effHalfWave = rawHalfWave * 1.20 * flowYZoom;
    const minWave = (baseMidWave + effFlowOffset) - effHalfWave;
    const maxWave = (baseMidWave + effFlowOffset) + effHalfWave;
    const rangeWave = Math.max(1e-6, maxWave - minWave);
    const flowPlotTop = p3Top + 17;
    const flowPlotBot = p3Bot - 6;
    const flowPlotH = Math.max(24, flowPlotBot - flowPlotTop);
    const toYSwingWave = (val) => flowPlotBot - ((Number(val || 0) - minWave) / rangeWave) * flowPlotH;
    const fromYSwingWave = (y) => minWave + ((flowPlotBot - y) / flowPlotH) * rangeWave;
    const yZeroWave = toYSwingWave(0);

    const flowAxisTicks = (() => {
        const rawStep = rangeWave / Math.max(3, Math.round(flowPlotH / 34));
        const pow10 = Math.pow(10, Math.floor(Math.log10(Math.max(1, rawStep))));
        const norm = rawStep / pow10;
        const mult = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
        const step = Math.max(10, mult * pow10);
        const firstT = Math.ceil(minWave / step) * step;
        const arr = [];
        for (let val = firstT; val <= maxWave + 1e-6 && arr.length < 10; val += step) {
            const y = toYSwingWave(val);
            if (y >= flowPlotTop + 4 && y <= flowPlotBot - 4) {
                arr.push({ val, y });
            }
        }
        return arr;
    })();

    tvMetricsRef.current = {
        width,
        height,
        padL,
        plotW,
        p1Top,
        p1Bot,
        p3Top,
        p3Bot,
        totalBase,
        effCount,
        startSlice,
        usableW,
        innerPadL,
        isChartFocused,
    };

    const toYOscP = (val) => yZero3 - (Number(val || 0) / (maxOscPrice * 1.12)) * halfH3;
    const toYOscNr = (val) => yZero3 - (Number(val || 0) / (maxOscNr * 1.12)) * halfH3;
    const spanCvd4 = Math.max(100, maxCvd4 - minCvd4);
    const cvd4MinPadded = minCvd4 - spanCvd4 * 0.10;
    const cvd4MaxPadded = maxCvd4 + spanCvd4 * 0.12;
    const toYCvd4 = (val) => (p3Bot - 4) - ((Number(val || 0) - cvd4MinPadded) / Math.max(1, cvd4MaxPadded - cvd4MinPadded)) * (p3H - 22);

    const lastPt = series[n - 1];
    const lastX = toX(n - 1);
    const lastY = toY1(lastPt.close);
    const hoverIdx = hoverPos ? hoverPos.idx : null;
    const inspectedPt = hoverIdx !== null && series[hoverIdx] ? series[hoverIdx] : lastPt;
    const inspectedSub = subPanelBars[hoverIdx !== null && subPanelBars[hoverIdx] ? hoverIdx : n - 1] || subPanelBars[0];

    // ── Paredes GEX vindas do `gex/docs/jumba_tradingview.pine` dentro da janela [minP, maxP] ──
    const rawWallsList = (Array.isArray(allWalls) && allWalls.length > 0)
        ? allWalls
        : [
            ...((wallsRadar?.resistance_walls || []).map((w) => ({ ...w, role: "RES" }))),
            ...((wallsRadar?.support_walls || []).map((w) => ({ ...w, role: "SUP" }))),
        ];

    const nearbyWalls = rawWallsList
        .filter(w => {
            const p = Number(w.price);
            if (!(p >= minP && p <= maxP)) return false;
            const isMid = String(w.type || "").toLowerCase().includes("mid") || String(w.label || "").toUpperCase() === "MIDLEWALL";
            if (isMid && !showMidleWalls) return false;
            return true;
        })
        .map(w => {
            const p = Number(w.price);
            const instB = Number(w.inst_buy_vol || 0);
            const instS = Number(w.inst_sell_vol || 0);
            const instTot = Number(w.inst_total_vol || (instB + instS) || 0);
            const instD = Number(w.inst_delta ?? w.session_inst_delta ?? (instB - instS));

            // Régua estatística de 3 Estágios calibrada nos 127 pregões históricos:
            // WDO: P25 = 3.000 L (Moderado) | P50 = 8.000 L (Forte)
            // WIN: P25 = 5.000 L (Moderado) | P50 = 12.000 L (Forte)
            const convictionMod = symKey === "WDO" ? 3000 : 5000;
            const convictionStrong = symKey === "WDO" ? 8000 : 12000;
            const absD = Math.abs(instD);

            let qualRole = "NEUTRAL";
            let smartBias = "NEUTRAL";
            let smartStage = "NEUTRO";

            if (instTot > 0 && absD >= convictionMod) {
                // Estágio 2 & 3: Posição Institucional Montada (Verde se Comprado, Vermelho se Vendido)
                // Preserva a cor mesmo se o preço furar temporariamente contra ("tomando calor")
                qualRole = instD > 0 ? "SUP" : "RES";
                smartBias = instD > 0 ? "BUY" : "SELL";
                smartStage = absD >= convictionStrong ? "FORTE" : "MODERADO";
            }

            // Lote de defesa consistente (fixo no lado do smart money, sem alternar por tick de preço)
            let defLots = Number(w.defense_lots || 0);
            if (smartBias === "BUY" && instB > 0) {
                defLots = instB;
            } else if (smartBias === "SELL" && instS > 0) {
                defLots = instS;
            } else if (defLots <= 0) {
                defLots = Math.max(instB, instS, Number(w.maker_hedge_lots || 0));
            }

            // Evolução Dinâmica da Wall ao longo dos candles visíveis de hoje (Múltiplas Marcações: Defendeu / Absorveu / Rompeu / Virou)
            const wType = String(w.type || "Wall");
            const isMid = wType.toLowerCase().includes("mid") || String(w.label || "").toUpperCase() === "MIDLEWALL";
            const zoneRad = symKey === "WDO" ? 2.5 : 55.0;
            const breakTol = symKey === "WDO" ? 1.0 : 25.0;
            const barInstTh = symKey === "WDO" ? 1000.0 : 2500.0;

            const dynamicEvents = [];
            let touchCount = 0;
            let brokenDir = 0;
            let lastEvIdx = -4;

            if (wType === "Wall" || wType === "MidWall" || isMid) {
                for (let idxM = 0; idxM < series.length; idxM++) {
                    const pt = series[idxM];
                    if (pt.is_prev_day) continue;
                    const c = Number(pt.close || 0);
                    const o = Number(pt.open ?? c);
                    const h = Number(pt.high ?? c);
                    const l = Number(pt.low ?? c);
                    if (!(l - zoneRad <= p && p <= h + zoneRad)) continue;

                    touchCount += 1;
                    if (idxM < 2 || (idxM - lastEvIdx) < 3) continue;

                    let prevSum = 0, prevCnt = 0;
                    for (let k = Math.max(0, idxM - 3); k < idxM; k++) {
                        prevSum += Number(series[k].close || c);
                        prevCnt += 1;
                    }
                    const prevAvg = prevCnt > 0 ? prevSum / prevCnt : c;
                    const prevSide = prevAvg >= p ? 1 : -1;

                    const rng = Math.max(h - l, symKey === "WDO" ? 0.5 : 5.0);
                    const bodyR = Math.abs(c - o) / rng;
                    const uWick = (h - Math.max(o, c)) / rng;
                    const lWick = (Math.min(o, c) - l) / rng;
                    const idB = Number(pt.inst_delta_bar || 0);
                    const rdB = Number(pt.ret_delta_bar || 0);
                    const cvdNow = Number(pt.cvd_inst || 0);
                    const cvdPrev = Number(series[Math.max(0, idxM - 3)]?.cvd_inst || 0);
                    const flow15m = cvdNow - cvdPrev;

                    if (prevSide === 1) {
                        if (c >= p - breakTol) {
                            if (lWick >= 0.28 || (c > o && idB > 0) || (idB >= barInstTh * 0.6 && rdB < 0)) {
                                const isFlip = brokenDir === 1;
                                dynamicEvents.push({
                                    idx: idxM,
                                    time: pt.time,
                                    type: isFlip ? "VIROU_SUP" : "DEFENDEU_COMPRA",
                                    label: isFlip ? "🔄 Virou Sup" : "🛡️ Defendeu",
                                    dir: 1,
                                    price: p,
                                });
                                lastEvIdx = idxM;
                            }
                        } else {
                            if (idB > 0 || (flow15m > 0 && rdB < 0)) {
                                dynamicEvents.push({
                                    idx: idxM,
                                    time: pt.time,
                                    type: "VIOLINADA_COMPRA",
                                    label: "🪤 Absorveu",
                                    dir: 1,
                                    price: p,
                                });
                                lastEvIdx = idxM;
                            } else if (bodyR >= 0.50 && (idB <= -barInstTh * 0.6 || flow15m < 0)) {
                                brokenDir = -1;
                                dynamicEvents.push({
                                    idx: idxM,
                                    time: pt.time,
                                    type: "ROMPEU_BAIXA",
                                    label: "💥 Rompeu",
                                    dir: -1,
                                    price: p,
                                });
                                lastEvIdx = idxM;
                            }
                        }
                    } else {
                        if (c <= p + breakTol) {
                            if (uWick >= 0.28 || (c < o && idB < 0) || (idB <= -barInstTh * 0.6 && rdB > 0)) {
                                const isFlip = brokenDir === -1;
                                dynamicEvents.push({
                                    idx: idxM,
                                    time: pt.time,
                                    type: isFlip ? "VIROU_RES" : "DEFENDEU_VENDA",
                                    label: isFlip ? "🔄 Virou Res" : "🛡️ Defendeu",
                                    dir: -1,
                                    price: p,
                                });
                                lastEvIdx = idxM;
                            }
                        } else {
                            if (idB < 0 || (flow15m < 0 && rdB > 0)) {
                                dynamicEvents.push({
                                    idx: idxM,
                                    time: pt.time,
                                    type: "VIOLINADA_VENDA",
                                    label: "🪤 Absorveu",
                                    dir: -1,
                                    price: p,
                                });
                                lastEvIdx = idxM;
                            } else if (bodyR >= 0.50 && (idB >= barInstTh * 0.6 || flow15m > 0)) {
                                brokenDir = 1;
                                dynamicEvents.push({
                                    idx: idxM,
                                    time: pt.time,
                                    type: "ROMPEU_ALTA",
                                    label: "💥 Rompeu",
                                    dir: 1,
                                    price: p,
                                });
                                lastEvIdx = idxM;
                            }
                        }
                    }
                }
            }

            const spotNow = Number(lastPt?.close || p);
            const lastEv = dynamicEvents.length > 0 ? dynamicEvents[dynamicEvents.length - 1].type : "";
            const trapMaxDist = symKey === "WDO" ? 3.5 : 120.0;
            const distFromWall = spotNow - p;
            const isNearWall = Math.abs(distFromWall) <= trapMaxDist;
            const isTakingHeat = isNearWall && (
                (smartBias === "BUY" && distFromWall < -breakTol)
                || (smartBias === "SELL" && distFromWall > breakTol)
            );
            // Se uma Wall Vendedora foi rompida para cima além da zona de violinada (>120 pts WIN / >3.5 pts WDO),
            // ou uma Wall Compradora foi rompida para baixo além da zona de violinada, os lotes contrários foram estopados e ela virou de papel!
            const brokeUpConfirmed = (distFromWall > trapMaxDist) && (smartBias === "SELL" || (smartBias === "NEUTRAL" && brokenDir === 1));
            const brokeDnConfirmed = (distFromWall < -trapMaxDist) && (smartBias === "BUY" || (smartBias === "NEUTRAL" && brokenDir === -1));

            let liveVerdict = "";
            let dynamicBias = smartBias;
            let isExhausted = false;
            let isTrap = false;

            if (touchCount >= 5 && smartStage === "NEUTRO" && isNearWall) {
                liveVerdict = `⚪ WALL GASTA (${touchCount}x)`;
                isExhausted = true;
            } else if (isNearWall && (lastEv === "VIOLINADA_COMPRA" || (isTakingHeat && smartBias === "BUY" && smartStage === "FORTE"))) {
                liveVerdict = "🪤 VIOLINADA (ABSORVENDO COMPRA)";
                dynamicBias = "BUY";
                isTrap = true;
            } else if (isNearWall && (lastEv === "VIOLINADA_VENDA" || (isTakingHeat && smartBias === "SELL" && smartStage === "FORTE"))) {
                liveVerdict = "🪤 VIOLINADA (ABSORVENDO VENDA)";
                dynamicBias = "SELL";
                isTrap = true;
            } else if (brokeUpConfirmed) {
                liveVerdict = "💥 ROMPERAM P/ ALTA (VIROU SUP)";
                dynamicBias = "BUY";
            } else if (brokeDnConfirmed) {
                liveVerdict = "💥 ROMPERAM P/ BAIXO (VIROU RES)";
                dynamicBias = "SELL";
            } else if (lastEv === "VIROU_SUP" && spotNow >= p - breakTol) {
                liveVerdict = "🔄 VIROU SUPORTE (DEFENDENDO)";
                dynamicBias = "BUY";
            } else if (lastEv === "VIROU_RES" && spotNow <= p + breakTol) {
                liveVerdict = "🔄 VIROU RESIST. (DEFENDENDO)";
                dynamicBias = "SELL";
            } else if (smartBias === "BUY" || lastEv === "DEFENDEU_COMPRA") {
                liveVerdict = "🛡️ VAI DEFENDER COMPRA";
                dynamicBias = "BUY";
            } else if (smartBias === "SELL" || lastEv === "DEFENDEU_VENDA") {
                liveVerdict = "🛡️ VAI DEFENDER VENDA";
                dynamicBias = "SELL";
            } else if (brokenDir === 1 && spotNow > p + breakTol) {
                liveVerdict = "💥 ROMPERAM P/ ALTA (VIROU SUP)";
                dynamicBias = "BUY";
            } else if (brokenDir === -1 && spotNow < p - breakTol) {
                liveVerdict = "💥 ROMPERAM P/ BAIXO (VIROU RES)";
                dynamicBias = "SELL";
            } else {
                liveVerdict = spotNow >= p ? "⚪ SUPORTE EM DISPUTA" : "⚪ RESIST. EM DISPUTA";
            }

            if (dynamicBias !== "NEUTRAL") {
                qualRole = dynamicBias === "BUY" ? "SUP" : "RES";
            }

            return {
                ...w,
                price: p,
                role: qualRole,
                smart_bias: dynamicBias,
                smart_stage: smartStage,
                defense_lots: defLots,
                inst_delta: instD,
                inst_total_vol: instTot,
                inst_buy_vol: instB,
                inst_sell_vol: instS,
                touch_count: touchCount,
                broken_dir: brokenDir,
                dynamic_events: dynamicEvents,
                live_verdict: liveVerdict,
                is_exhausted: isExhausted,
                is_trap: isTrap,
            };
        });

    const buyZone = asgHud?.buy_zone;
    const sellZone = asgHud?.sell_zone;
    const buyersPct = asgHud?.buyers_pct ?? 50;
    const sellersPct = asgHud?.sellers_pct ?? 50;

    // Sinais de entrada e Caixas de Posição (Entrada -> Breakeven -> Saída) sincronizados com signalsLog
    const plottedSignals = [];
    const sigsByTime = {};
    const todayIdxByTime = {};
    let lastTodayTime = null;
    series.forEach((pt, idx) => {
        if (!pt.is_prev_day && pt.time) {
            todayIdxByTime[pt.time] = idx;
            lastTodayTime = pt.time;
        }
    });

    if (hostSignalsLog.length > 0) {
        hostSignalsLog.forEach(s => {
            if (!s || s.is_prev_day) return;
            const k = s.time;
            if (!sigsByTime[k]) sigsByTime[k] = [];
            sigsByTime[k].push(s);
        });
    }
    series.forEach((pt, idx) => {
        if (pt.is_prev_day) return;
        const barSigs = sigsByTime[pt.time] || [];
        barSigs.forEach((sig, sSlot) => {
            const exTime = sig.exit_time || sig.time;
            let idxEnd = todayIdxByTime[exTime];
            if (idxEnd === undefined) {
                if (sig.validation_status === "EM_ANDAMENTO" || (lastTodayTime && exTime > lastTodayTime)) {
                    idxEnd = n - 1;
                } else {
                    idxEnd = Math.min(n - 1, idx + 3);
                }
            }
            if (idxEnd < idx) idxEnd = idx;

            let idxBe = null;
            if (sig.be_triggered && sig.be_time) {
                if (todayIdxByTime[sig.be_time] !== undefined) {
                    idxBe = todayIdxByTime[sig.be_time];
                } else if (lastTodayTime && sig.be_time > lastTodayTime) {
                    idxBe = n - 1;
                }
            }

            plottedSignals.push({
                ...sig,
                idx,
                idxStart: idx,
                idxEnd,
                idxBe,
                sSlot,
                x: toX(idx),
                y: toY1(sig.entry_price),
            });
        });
    });

    const timeTicks = [0, Math.floor(n * 0.2), Math.floor(n * 0.4), Math.floor(n * 0.6), Math.floor(n * 0.8), n - 1]
        .filter((v, i, a) => v >= 0 && v < n && a.indexOf(v) === i);

    return (
        <div style={{
            minWidth: 0,
            background: "#0c1218",
            borderRadius: 10,
            border: "1px solid #1a2530",
            padding: "10px 12px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
        }}>
            {/* ── Barra Superior Unificada com a Paleta do Dashboard ── */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{
                        fontSize: 11.5,
                        fontWeight: "bold",
                        color: "#ffffff",
                        letterSpacing: 0.8,
                        background: "#0c1218",
                        padding: "3px 8px",
                        borderRadius: 4,
                        border: "1px solid #1a2530",
                        borderLeft: "3px solid #00d4ff",
                    }}>
                        FLUXO REAL + PINE GEX ({symKey} · {useM1Active ? "M1" : "M5"})
                    </span>
                    {/* Seletor de Timeframe M5 / M1 */}
                    <div style={{ display: "inline-flex", alignItems: "center", gap: 3, background: "#080d12", padding: "2px 4px", borderRadius: 5, border: "1px solid #1a2530" }}>
                        {[
                            { id: "M5", label: "⏱️ M5", desc: "Gráfico de 5 Minutos (Padrão)" },
                            { id: "M1", label: m1Loading && chartTf === "M1" ? "⏳ M1..." : "⚡ M1", desc: "Gráfico de 1 Minuto (Microestrutura Fina + Fluxo Smart Money)" },
                        ].map((tfOpt) => {
                            const active = chartTf === tfOpt.id;
                            return (
                                <button
                                    key={tfOpt.id}
                                    onClick={() => {
                                        setChartTf(tfOpt.id);
                                        setHoverPos(null);
                                        setPanOffsetRight(0);
                                        if (tfOpt.id === "M1" && viewMode === "RECENTE") {
                                            setVisibleCount(120);
                                        } else if (tfOpt.id === "M5" && viewMode === "RECENTE") {
                                            setVisibleCount(48);
                                        }
                                    }}
                                    title={tfOpt.desc}
                                    style={{
                                        padding: "2px 7px",
                                        fontSize: 9.5,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: active ? "rgba(0, 212, 255, 0.18)" : "transparent",
                                        color: active ? "#00d4ff" : "#7f96a8",
                                        border: active ? "1px solid #00d4ff" : "1px solid transparent",
                                        borderRadius: 3.5,
                                        cursor: "pointer",
                                    }}
                                >
                                    {tfOpt.label}
                                </button>
                            );
                        })}
                    </div>
                    {isWallsHost ? (
                        <>
                            <span style={{ fontSize: 10, color: "#cbd5e1", fontWeight: "bold" }}>⬜ Barra Alta</span>
                            <span style={{ fontSize: 10, color: "#64748b", fontWeight: "bold" }}>⬛ Barra Baixa</span>
                            <span style={{ fontSize: 10, color: "#f1f5f9" }}>━ Wall</span>
                            <span style={{ fontSize: 10, color: "#94a3b8" }}>┅ MidWall</span>
                        </>
                    ) : candleColorMode === "TRADICIONAL" ? (
                        <>
                            <span style={{ fontSize: 10, color: "#00e87a", fontWeight: "bold" }}>🟩 Barra Alta</span>
                            <span style={{ fontSize: 10, color: "#ff3860", fontWeight: "bold" }}>🟥 Barra Baixa</span>
                        </>
                    ) : (
                        <>
                            <span style={{ fontSize: 10, color: "#00e87a", fontWeight: "bold" }}>🟩 Comprado (Smart Money)</span>
                            <span style={{ fontSize: 10, color: "#ff3860", fontWeight: "bold" }}>🟥 Vendido (Smart Money)</span>
                            <span style={{ fontSize: 10, color: "#7f96a8" }}>⬜ Pullback</span>
                        </>
                    )}
                </div>

                {/* Controles do Gráfico: Limpo e Focado em Divergências na 5176 | Completo na 5174 */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 3, background: "#0c1218", padding: "2px 6px", borderRadius: 5, border: "1px solid #1a2530" }}>
                        {!isWallsHost && (
                            <>
                                <button
                                    onClick={() => setCandleColorMode(m => (m === "TRADICIONAL" ? "JANELA" : "TRADICIONAL"))}
                                    title="Alternar cor das barras entre Modo Tradicional (Alta/Baixa - Padrão) ou Pintadas pelas Janelas de Fluxo Smart Money"
                                    style={{
                                        padding: "2px 6px",
                                        fontSize: 9,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: "#0c1218",
                                        color: candleColorMode === "TRADICIONAL" ? "#e2e8f0" : "#00d4ff",
                                        border: `1px solid ${candleColorMode === "TRADICIONAL" ? "rgba(226, 232, 240, 0.35)" : "rgba(0, 212, 255, 0.45)"}`,
                                        borderRadius: 4,
                                        cursor: "pointer",
                                    }}
                                >
                                    {candleColorMode === "TRADICIONAL" ? "🕯️ Barras: Tradicional" : "🎨 Barras: Janelas"}
                                </button>
                                <button
                                    onClick={() => setWallColorMode(m => (m === "PINE" ? "POLARIDADE" : "PINE"))}
                                    title="Alternar entre Posição Smart Money (3 Estágios Calibrados em 127 Pregões) ou Branco Neutro"
                                    style={{
                                        padding: "2px 6px",
                                        fontSize: 9,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: "#0c1218",
                                        color: wallColorMode === "PINE" ? "#ffffff" : "#00e87a",
                                        border: `1px solid ${wallColorMode === "PINE" ? "rgba(255, 255, 255, 0.45)" : "rgba(0, 232, 122, 0.45)"}`,
                                        borderRadius: 4,
                                        cursor: "pointer",
                                    }}
                                >
                                    {wallColorMode === "PINE" ? "⬜ Walls: Branco" : "🎯 Smart Money"}
                                </button>
                                <button
                                    onClick={() => setSmWinVisualMode(m => (m === "HIST_LINE" ? "LINE" : m === "LINE" ? "HIST" : "HIST_LINE"))}
                                    title="Alternar visualização da Janela de Fluxo Smart Money entre: Histograma + Linha (Padrão), Modo Linha ou Só Histograma"
                                    style={{
                                        padding: "2px 6px",
                                        fontSize: 9,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: "rgba(0, 212, 255, 0.10)",
                                        color: "#00d4ff",
                                        border: "1px solid rgba(0, 212, 255, 0.50)",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                    }}
                                >
                                    {smWinVisualMode === "HIST_LINE"
                                        ? "📊+📈 Fluxo: Hist + Linha"
                                        : smWinVisualMode === "LINE"
                                            ? "📈 Fluxo: Modo Linha"
                                            : "📊 Fluxo: Histograma"}
                                </button>
                            </>
                        )}
                        <button
                            onClick={() => setShowMidleWalls(v => !v)}
                            title="Exibir/Ocultar MIDLEWALL tracejada e suas Regiões de Compra/Venda"
                            style={{
                                padding: "2px 6px",
                                fontSize: 9,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                background: "#0c1218",
                                color: showMidleWalls ? "#7be3ff" : "#5a7288",
                                border: showMidleWalls ? "1px solid rgba(0, 212, 255, 0.4)" : "1px solid #1a2530",
                                borderRadius: 4,
                                cursor: "pointer",
                            }}
                        >
                            MidWalls
                        </button>
                        <button
                            onClick={() => setShowNweLine(v => !v)}
                            title={isWallsHost ? "Exibir/Ocultar Envelope Causal NWE30 (L=30, bw=3.0, mult=1.6 — Banda Oposta = TP1 Dinâmico do Lote 1 no WIN)" : "Exibir/Ocultar Média NWE Causal (Nadaraya-Watson h=8, L=40) e Banda ±1 MAE"}
                            style={{
                                padding: "2px 6px",
                                fontSize: 9,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                background: showNweLine ? "rgba(0, 212, 255, 0.12)" : "#0c1218",
                                color: showNweLine ? "#00d4ff" : "#5a7288",
                                border: showNweLine ? "1px solid rgba(0, 212, 255, 0.55)" : "1px solid #1a2530",
                                borderRadius: 4,
                                cursor: "pointer",
                            }}
                        >
                            {isWallsHost ? "〰️ Banda NWE30" : "〰️ Média NWE"}
                        </button>
                        {!isWallsHost && (
                            <>
                                <button
                                    onClick={() => setShowWindowFlips(v => !v)}
                                    title="Exibir/Ocultar Linhas Verticais Tracejadas de Virada da Janela de Fluxo"
                                    style={{
                                        padding: "2px 6px",
                                        fontSize: 9,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: "#0c1218",
                                        color: showWindowFlips ? "#ffd600" : "#5a7288",
                                        border: showWindowFlips ? "1px solid rgba(255, 214, 0, 0.55)" : "1px solid #1a2530",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                    }}
                                >
                                    ⚡ Viradas
                                </button>
                                <button
                                    onClick={() => setShowWallBattleLabels(v => !v)}
                                    title="Exibir/Ocultar escrita nos candles (🛡️ Defendeu / 🪤 Absorveu / 💥 Rompeu / 🔄 Virou)"
                                    style={{
                                        padding: "2px 6px",
                                        fontSize: 9,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: "#0c1218",
                                        color: showWallBattleLabels ? "#00e87a" : "#5a7288",
                                        border: showWallBattleLabels ? "1px solid rgba(0, 232, 122, 0.55)" : "1px solid #1a2530",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                    }}
                                >
                                    🛡️ Eventos Wall
                                </button>
                            </>
                        )}
                        {isWallsHost && (
                            <button
                                onClick={() => setShowSwingDivLines(v => !v)}
                                title="Exibir/Ocultar Linhas de Divergência de Topo e Fundo (F1 ➔ F2 / T1 ➔ T2) sincronizadas entre Preço e Fluxo"
                                style={{
                                    padding: "2px 6px",
                                    fontSize: 9,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    background: showSwingDivLines ? "rgba(0, 232, 122, 0.14)" : "#0c1218",
                                    color: showSwingDivLines ? "#00e87a" : "#5a7288",
                                    border: showSwingDivLines ? "1px solid rgba(0, 232, 122, 0.65)" : "1px solid #1a2530",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                }}
                            >
                                📐 Linhas Div. ({swingDivergences.length})
                            </button>
                        )}
                        {!isWallsHost && (
                            <>
                                <span style={{ color: "#1a2530", margin: "0 2px" }}>|</span>
                                <button
                                    onClick={() => setRightGapPx(g => Math.min(280, g + 35))}
                                    title="Chegar gráfico mais para a esquerda"
                                    style={{
                                        padding: "2px 6px",
                                        fontSize: 9,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: "#0c1218",
                                        color: "#00d4ff",
                                        border: "1px solid #1a2530",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                    }}
                                >
                                    ◀ Esq
                                </button>
                                <button
                                    onClick={() => setRightGapPx(g => Math.max(30, g - 35))}
                                    title="Chegar gráfico mais para a direita"
                                    style={{
                                        padding: "2px 6px",
                                        fontSize: 9,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: "#0c1218",
                                        color: "#9fb4c7",
                                        border: "1px solid #1a2530",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                    }}
                                >
                                    Dir ▶
                                </button>
                                <button
                                    onClick={() => setYZoomFactor(z => Math.min(4.0, +(z * 1.35).toFixed(2)))}
                                    title="Abrir escala vertical Y para enxergar mais MagicWalls e MidWalls acima e abaixo"
                                    style={{
                                        padding: "2px 6px",
                                        fontSize: 9,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: "#0c1218",
                                        color: "#00e87a",
                                        border: "1px solid #1a2530",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                    }}
                                >
                                    ↕ +Walls
                                </button>
                                <button
                                    onClick={() => setYZoomFactor(z => Math.max(0.5, +(z / 1.35).toFixed(2)))}
                                    title="Dar mais zoom vertical nos candles atuais"
                                    style={{
                                        padding: "2px 6px",
                                        fontSize: 9,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: "#0c1218",
                                        color: "#9fb4c7",
                                        border: "1px solid #1a2530",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                    }}
                                >
                                    ↕ −Zoom Y
                                </button>
                            </>
                        )}
                        {(!priceAutoScale || yZoomFactor !== 1.0 || !flowAutoScale || flowYZoom !== 1.0 || viewMode === "CUSTOM" || rightGapPx !== 145) && (
                            <button
                                onClick={() => {
                                    setPriceAutoScale(true);
                                    setYZoomFactor(1.0);
                                    setPriceYOffset(0);
                                    setFlowAutoScale(true);
                                    setFlowYZoom(1.0);
                                    setFlowYOffset(0);
                                    setRightGapPx(145);
                                    setPanOffsetRight(0);
                                    setViewMode("HOJE");
                                }}
                                title="Resetar escalas de Preço, Fluxo Smart Money e Zoom horizontal para Automático (igual duplo-clique no TV)"
                                style={{
                                    padding: "2px 7px",
                                    fontSize: 9,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    background: "rgba(0, 212, 255, 0.12)",
                                    color: "#00d4ff",
                                    border: "1px solid #00d4ff",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                }}
                            >
                                ↺ Auto Escala TV
                            </button>
                        )}
                        <span style={{ color: "#1a2530", margin: "0 2px" }}>|</span>
                        {[
                            { id: "HOJE", label: "Dia Todo", cnt: null },
                            ...(hasPrevDayWarmup ? [{ id: "TUDO", label: "Ontem + Hoje", cnt: null }] : []),
                            ...(useM1Active
                                ? [
                                    { id: "RECENTE", label: "Foco (120m)", cnt: 120 },
                                    { id: "ZOOM45", label: "Zoom (45m)", cnt: 45 },
                                ]
                                : [{ id: "RECENTE", label: "Foco (48b)", cnt: 48 }]),
                        ].map(opt => (
                            <button
                                key={opt.id}
                                onClick={() => {
                                    setViewMode(opt.id);
                                    setPanOffsetRight(0);
                                    if (opt.cnt) setVisibleCount(opt.cnt);
                                }}
                                style={{
                                    padding: "2px 6px",
                                    fontSize: 9,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    background: "#0c1218",
                                    color: viewMode === opt.id ? "#00d4ff" : "#7f96a8",
                                    border: viewMode === opt.id ? "1px solid #00d4ff88" : "1px solid transparent",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                }}
                            >
                                {opt.label}
                            </button>
                        ))}
                        {capitalDrawerInfo && (
                            <>
                                <span style={{ color: "#1a2530", margin: "0 2px" }}>|</span>
                                <button
                                    onClick={capitalDrawerInfo.onToggle}
                                    title={capitalDrawerInfo.isCollapsed
                                        ? "Expandir painel lateral de Capital das Operações do Dia e HUD"
                                        : "Recuar painel lateral de Capital para deixar o gráfico de Preço + Fluxo Smart Money maior na tela"}
                                    style={{
                                        padding: "2px 8px",
                                        fontSize: 9,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: capitalDrawerInfo.isCollapsed ? "rgba(0, 212, 255, 0.08)" : "#0c1218",
                                        color: capitalDrawerInfo.netBrl >= 0 ? "#00e87a" : "#ff3860",
                                        border: capitalDrawerInfo.isCollapsed ? "1px solid rgba(0, 212, 255, 0.45)" : "1px solid #1a2530",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                        display: "inline-flex",
                                        alignItems: "center",
                                        gap: 5,
                                    }}
                                >
                                    <span>💰 {capitalDrawerInfo.netBrl >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(capitalDrawerInfo.netBrl), 0)}</span>
                                    <span style={{ color: "#00d4ff", fontWeight: 900 }}>
                                        {capitalDrawerInfo.isCollapsed ? "◀ Capital" : "Recuar ▶"}
                                    </span>
                                </button>
                            </>
                        )}
                    </div>

                    {/* Inspetor OHLC enxuto */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 10, fontFamily: "monospace", background: "#0c1218", padding: "3px 9px", borderRadius: 5, border: "1px solid #1a2530" }}>
                        <span style={{ color: "#9fb4c7" }}>
                            🕒 {inspectedPt.is_prev_day ? `Ontem ${inspectedPt.time}` : inspectedPt.time}
                        </span>
                        <span style={{ color: "#6b8299" }}>
                            A:{fmtNum(inspectedPt.open, dec)} M:{fmtNum(inspectedPt.high, dec)} m:{fmtNum(inspectedPt.low, dec)}
                        </span>
                        <span style={{ color: "#ffffff", fontWeight: "bold" }}>
                            F:{fmtNum(inspectedPt.close, dec)}
                        </span>
                        {!isWallsHost && (
                            <>
                                <span style={{ color: (inspectedPt.window_dir || 0) > 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }} title="Direção da Janela Estrutural das 8 Estratégias">
                                    {(inspectedPt.window_dir || 0) > 0 ? "🟢 COMPRA" : "🔴 VENDA"}
                                </span>
                                <span style={{ color: "#00d4ff" }} title="Saldo da Onda de Fluxo Smart Money em Contratos/Lotes">
                                    Fluxo: {fmtNum(inspectedSub?.smartSwingWave ?? 0, 0, true)} L
                                </span>
                            </>
                        )}
                        {isWallsHost && (
                            <>
                                <span style={{ color: Number(inspectedPt.inst_aggr_delta ?? inspectedPt.inst_delta_bar ?? 0) + Number(inspectedPt.inst_pass_delta ?? 0) >= 0 ? "#00e87a" : "#ff6b8b", fontWeight: "bold" }} title="Saldo institucional total na barra M5 (Agressão + Absorção)">
                                    🏦Não-Var:{fmtNum(Number(inspectedPt.inst_aggr_delta ?? inspectedPt.inst_delta_bar ?? 0) + Number(inspectedPt.inst_pass_delta ?? 0), 0, true)}
                                </span>
                                <span style={{ color: Number(inspectedPt.ret_delta_bar ?? 0) >= 0 ? "#38bdf8" : "#f59e0b" }} title="Saldo Varejo Puro na barra M5">
                                    🧑‍💻Var:{fmtNum(inspectedPt.ret_delta_bar ?? 0, 0, true)}
                                </span>
                                {inspectedSub?.divType && (
                                    <span
                                        style={{
                                            color: inspectedSub.divColor,
                                            fontWeight: "bold",
                                            background: "rgba(5, 8, 13, 0.9)",
                                            border: `1px solid ${inspectedSub.divColor}77`,
                                            padding: "1px 6px",
                                            borderRadius: 4,
                                            fontSize: 9,
                                        }}
                                        title={inspectedSub.divLabel}
                                    >
                                        {inspectedSub.divLabel}
                                    </span>
                                )}
                            </>
                        )}
                        {showNweLine && getNweLine(inspectedPt) > 0 && (
                            <span style={{ color: isWallsHost ? "#94a3b8" : (getNweIsUp(inspectedPt) !== false ? "#00d4ff" : "#ff6b8b"), fontWeight: "bold" }}>
                                {isWallsHost ? "NWE30" : "NWE"}: {fmtNum(getNweLine(inspectedPt), dec)} {getNweIsUp(inspectedPt) !== false ? "↑" : "↓"}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* ── GRÁFICO PRINCIPAL INTERATIVO ESTILO TRADINGVIEW (#0c1218 / #1a2530) ── */}
            <svg
                ref={svgRef}
                viewBox={`0 0 ${width} ${height}`}
                style={{
                    width: "100%",
                    height: "auto",
                    minHeight: 440,
                    display: "block",
                    userSelect: "none",
                    cursor: dragState
                        ? (dragState.type === "SPLITTER"
                            ? "row-resize"
                            : (dragState.type === "YSCALE_P1" || dragState.type === "YSCALE_P3")
                                ? "ns-resize"
                                : "grabbing")
                        : cursorZone === "SPLITTER"
                            ? "row-resize"
                            : cursorZone === "YAXIS"
                                ? "ns-resize"
                                : "crosshair",
                    background: "#0c1218",
                    borderRadius: 6,
                    border: isChartFocused ? "1px solid rgba(0, 212, 255, 0.42)" : "1px solid #1a2530",
                    transition: "border-color 0.15s ease",
                }}
                onMouseDown={(e) => {
                    setIsChartFocused(true);
                    const rect = e.currentTarget.getBoundingClientRect();
                    const relX = ((e.clientX - rect.left) / rect.width) * width;
                    const relY = ((e.clientY - rect.top) / rect.height) * height;

                    if (Math.abs(relY - splitterMidY) <= 7 && relX <= padL + plotW) {
                        setDragState({
                            type: "SPLITTER",
                            startY: e.clientY,
                            rectH: rect.height,
                            startFlowH: clampedFlowH,
                        });
                    } else if (relX > padL + plotW) {
                        if (relY <= p1Bot) {
                            setPriceAutoScale(false);
                            setDragState({
                                type: "YSCALE_P1",
                                startY: e.clientY,
                                startYZoom: yZoomFactor,
                            });
                        } else if (relY >= p3Top && relY <= p3Bot) {
                            setFlowAutoScale(false);
                            setDragState({
                                type: "YSCALE_P3",
                                startY: e.clientY,
                                startYZoom: flowYZoom,
                            });
                        }
                    } else {
                        const isFlowPane = relY >= p3Top;
                        setDragState({
                            type: isFlowPane ? "PAN_P3" : "PAN_P1",
                            startX: e.clientX,
                            startY: e.clientY,
                            rectW: rect.width,
                            rectH: rect.height,
                            startPan: clampedPan,
                            startRightGap: rightGapPx,
                            startPriceOffset: priceAutoScale ? 0 : priceYOffset,
                            startFlowOffset: flowAutoScale ? 0 : flowYOffset,
                            startRangeP: rangeP,
                            startRangeWave: rangeWave,
                        });
                    }
                }}
                onMouseMove={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    const relX = ((e.clientX - rect.left) / rect.width) * width;
                    const relY = ((e.clientY - rect.top) / rect.height) * height;

                    if (!dragState) {
                        if (Math.abs(relY - splitterMidY) <= 7 && relX <= padL + plotW) {
                            if (cursorZone !== "SPLITTER") setCursorZone("SPLITTER");
                        } else if (relX > padL + plotW && relY >= p1Top && relY <= p3Bot) {
                            if (cursorZone !== "YAXIS") setCursorZone("YAXIS");
                        } else if (cursorZone !== "PLOT") {
                            setCursorZone("PLOT");
                        }
                    }

                    if (dragState) {
                        const dyPx = e.clientY - dragState.startY;
                        const dySvg = (dyPx / Math.max(1, dragState.rectH || rect.height)) * height;

                        if (dragState.type === "SPLITTER") {
                            const nextFlowH = Math.round(Math.max(82, Math.min(height - 210, dragState.startFlowH - dySvg)));
                            setFlowPaneH(nextFlowH);
                        } else if (dragState.type === "YSCALE_P1") {
                            const factor = Math.max(0.15, Math.min(6.0, dragState.startYZoom * Math.exp(dyPx * 0.0055)));
                            setYZoomFactor(+factor.toFixed(3));
                        } else if (dragState.type === "YSCALE_P3") {
                            const factor = Math.max(0.15, Math.min(6.0, dragState.startYZoom * Math.exp(dyPx * 0.0055)));
                            setFlowYZoom(+factor.toFixed(3));
                        } else if (dragState.type === "PAN_P1" || dragState.type === "PAN_P3") {
                            const dxPx = e.clientX - dragState.startX;
                            const dxSvg = (dxPx / Math.max(1, dragState.rectW || rect.width)) * width;

                            if (maxPan > 0) {
                                const barsDelta = Math.round((dxPx / Math.max(1, (dragState.rectW || rect.width) * 0.72)) * effCount);
                                const rawTargetPan = dragState.startPan + barsDelta;
                                if (rawTargetPan < 0) {
                                    setPanOffsetRight(0);
                                    const extraGap = Math.round(-rawTargetPan * stepX);
                                    setRightGapPx(Math.max(35, Math.min(480, dragState.startRightGap + extraGap)));
                                } else {
                                    setPanOffsetRight(Math.min(maxPan, rawTargetPan));
                                }
                            } else {
                                setRightGapPx(Math.max(35, Math.min(480, Math.round(dragState.startRightGap - dxSvg))));
                            }

                            if (dragState.type === "PAN_P1" && (!priceAutoScale || e.shiftKey)) {
                                if (e.shiftKey && priceAutoScale) setPriceAutoScale(false);
                                const nextOffP = dragState.startPriceOffset + (dySvg / Math.max(1, p1H)) * dragState.startRangeP;
                                setPriceYOffset(nextOffP);
                            } else if (dragState.type === "PAN_P3" && (!flowAutoScale || e.shiftKey)) {
                                if (e.shiftKey && flowAutoScale) setFlowAutoScale(false);
                                const nextOffW = dragState.startFlowOffset + (dySvg / Math.max(1, flowPlotH)) * dragState.startRangeWave;
                                setFlowYOffset(nextOffW);
                            }
                        }
                    }

                    const rawIdx = Math.round(((relX - (padL + innerPadL)) / usableW) * Math.max(1, totalSlots));
                    if (relX >= padL && relX <= padL + plotW) {
                        setHoverPos({
                            idx: Math.max(0, Math.min(n - 1, rawIdx)),
                            relX,
                            relY,
                        });
                    } else {
                        setHoverPos(null);
                    }
                }}
                onMouseUp={() => setDragState(null)}
                onMouseLeave={() => {
                    setDragState(null);
                    setHoverPos(null);
                    setCursorZone("PLOT");
                }}
                onDoubleClick={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    const relX = ((e.clientX - rect.left) / rect.width) * width;
                    const relY = ((e.clientY - rect.top) / rect.height) * height;
                    if (relX > padL + plotW && relY <= p1Bot) {
                        setPriceAutoScale(true);
                        setYZoomFactor(1.0);
                        setPriceYOffset(0);
                    } else if (relX > padL + plotW && relY >= p3Top) {
                        setFlowAutoScale(true);
                        setFlowYZoom(1.0);
                        setFlowYOffset(0);
                    } else {
                        setPriceAutoScale(true);
                        setYZoomFactor(1.0);
                        setPriceYOffset(0);
                        setFlowAutoScale(true);
                        setFlowYZoom(1.0);
                        setFlowYOffset(0);
                        setRightGapPx(145);
                        setPanOffsetRight(0);
                        setViewMode("HOJE");
                    }
                }}
            >
                <defs>
                    <clipPath id={`clip-p1-band-${symKey}`}>
                        <rect x="0" y={p1Top} width={width} height={p1H} />
                    </clipPath>
                    <clipPath id={`clip-p3-band-${symKey}`}>
                        <rect x="0" y={p3Top + 15} width={width} height={Math.max(10, p3H - 15)} />
                    </clipPath>
                </defs>

                {/* Fundos dos 2 Painéis Unificados com o Dashboard (#0c1218) */}
                <rect x={padL} y={p1Top} width={plotW} height={p1H} fill="#0c1218" />
                <rect x={padL} y={p3Top} width={plotW} height={p3H} fill="#0c1218" />

                {/* Grade Regular e Escala de Preço Dinâmica estilo TradingView (Painel 1) */}
                {priceAxisTicks.map((tk, tIdx) => {
                    const nearSpot = Math.abs(tk.y - lastY) < 13;
                    const nearWall = nearbyWalls.some((w) => Math.abs(toY1(w.price) - tk.y) < 11);
                    const nearAutoBtn = tk.y > p1Bot - 22;
                    return (
                        <g key={`tv-p1-tick-${tIdx}`}>
                            <line
                                x1={padL}
                                y1={tk.y}
                                x2={padL + plotW}
                                y2={tk.y}
                                stroke="#131d27"
                                strokeWidth="0.8"
                            />
                            {!nearSpot && !nearWall && !nearAutoBtn && (
                                <text
                                    x={padL + plotW + 6}
                                    y={tk.y + 3}
                                    fill="#51687c"
                                    fontSize="8"
                                    fontFamily="monospace"
                                >
                                    {fmtNum(tk.price, dec)}
                                </text>
                            )}
                        </g>
                    );
                })}

                {/* Divisórias Horizontais + Barra Splitter Redimensionável estilo TradingView (↕) */}
                <line x1={padL} y1={p1Bot} x2={width} y2={p1Bot} stroke={cursorZone === "SPLITTER" || dragState?.type === "SPLITTER" ? "#00d4ff88" : "#1a2530"} strokeWidth="1" />
                <line x1={padL} y1={p3Top} x2={width} y2={p3Top} stroke={cursorZone === "SPLITTER" || dragState?.type === "SPLITTER" ? "#00d4ff88" : "#1a2530"} strokeWidth="1" />
                <rect
                    x={padL}
                    y={p1Bot}
                    width={plotW}
                    height={splitterGap}
                    fill={cursorZone === "SPLITTER" || dragState?.type === "SPLITTER" ? "rgba(0, 212, 255, 0.08)" : "#080d12"}
                />
                <rect
                    x={padL + plotW / 2 - 18}
                    y={splitterMidY - 1.5}
                    width={36}
                    height={3}
                    rx="1.5"
                    fill={cursorZone === "SPLITTER" || dragState?.type === "SPLITTER" ? "#00d4ff" : "#243444"}
                />
                <line x1={padL} y1={p3Bot} x2={width} y2={p3Bot} stroke="#1a2530" strokeWidth="1" />
                <line x1={padL + plotW} y1={p1Top} x2={padL + plotW} y2={p3Bot} stroke="#1a2530" strokeWidth="1" />

                {/* Títulos Internos Discretos na Paleta do Dashboard */}
                <text x={padL + 8} y={p1Top + 13} fill="#5a7288" fontSize="8.5" fontWeight="bold" fontFamily="monospace">
                    1. {symKey} · {useM1Active ? "M1 (1 MINUTO)" : "M5"} · MAGIC GEX LEVELS &amp; MIDWALLS (jumba_tradingview.pine)
                </text>
                <text x={padL + 8} y={p3Top + 12} fill="#9fb4c7" fontSize="8.5" fontWeight="bold" fontFamily="monospace">
                    {flowSubMode === "SWING_DIVERGENCIA"
                        ? "2. FLUXO SMART MONEY"
                        : flowSubMode === "CABO_GUERRA"
                            ? "2. CABO DE GUERRA (NÃO-VAREJO vs VAREJO · M5) · 🟩🟥 Inst Agressor | 🟦🟧 Inst Passivo (Pedra) | 🟪 Barra Fina Varejo | ◆ Divergência"
                            : flowSubMode === "OSC_DIVERGENCIA"
                                ? `2. OSCILADOR DE DIVERGÊNCIA (${oscTf === "5M" ? "⚡ 5m VELA ATUAL / TOQUE WALL" : oscTf === "10M" ? "10m / 2 BARRAS" : "15m / 3 BARRAS"}) · ⬜ ΔPreço vs 🟢 Fluxo Não-Varejo · Áreas Sombreadas = Divergência`
                                : flowSubMode === "CVD_4PLAYERS"
                                    ? "2. CVD ACUMULADO 4-PLAYERS EM LOTES (SESSÃO) · 🟢 Inst Agressor | 🔵 Inst Passivo | 🟠 Varejo | 🟣 HFT | 🟡 RLP (Mesma Escala em Lotes)"
                                    : smWinVisualMode === "HIST_LINE"
                                        ? "2. JANELA DE FLUXO SMART MONEY (HISTOGRAMA + LINHA)"
                                        : smWinVisualMode === "LINE"
                                            ? "2. JANELA DE FLUXO SMART MONEY (MODO LINHA)"
                                            : "2. JANELA DE FLUXO SMART MONEY (HISTOGRAMA)"}
                </text>
                {flowSubMode === "JANELA_ASG" && (
                    <g onMouseDown={(e) => e.stopPropagation()}>
                        {[
                            { id: "HIST_LINE", label: "📊+📈 Hist+Linha", w: 78 },
                            { id: "LINE", label: "📈 Linha", w: 50 },
                            { id: "HIST", label: "📊 Hist", w: 46 },
                        ].map((mOpt, mIdx, arr) => {
                            const rightAnchor = padL + plotW - 6;
                            const totalBefore = arr.slice(mIdx).reduce((acc, it) => acc + it.w + 4, 0);
                            const xBtn = rightAnchor - totalBefore;
                            const active = smWinVisualMode === mOpt.id;
                            return (
                                <g
                                    key={`sm-vmode-${mOpt.id}`}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setSmWinVisualMode(mOpt.id);
                                    }}
                                    style={{ cursor: "pointer" }}
                                >
                                    <rect
                                        x={xBtn}
                                        y={p3Top + 2}
                                        width={mOpt.w}
                                        height={13}
                                        rx="2.5"
                                        fill={active ? "rgba(0, 212, 255, 0.18)" : "#080d12"}
                                        stroke={active ? "#00d4ff" : "#1f2d3b"}
                                        strokeWidth="0.85"
                                    />
                                    <text
                                        x={xBtn + mOpt.w / 2}
                                        y={p3Top + 11}
                                        fill={active ? "#00d4ff" : "#6b8599"}
                                        fontSize="7.4"
                                        fontWeight="bold"
                                        fontFamily="monospace"
                                        textAnchor="middle"
                                    >
                                        {mOpt.label}
                                    </text>
                                </g>
                            );
                        })}
                    </g>
                )}

                <g clipPath={`url(#clip-p1-band-${symKey})`}>

                {/* Regiões Sombreadas de Compra e Venda (MagicWall + MidWall) Diferenciadas por Defesa Institucional + Hedge Makers */}
                {(() => {
                    const zonesToRender = [];
                    const baseBandPts = rangeP * 0.032;

                    const nearestResP = Number(sellZone?.ref_price || 0);
                    const nearestSupP = Number(buyZone?.ref_price || 0);

                    nearbyWalls.forEach((w, idx) => {
                        const wType = String(w.type || "Wall");
                        const isMid = wType.toLowerCase().includes("mid") || String(w.label || "").toUpperCase() === "MIDLEWALL";
                        const isMainWall = wType === "Wall";
                        if (!isMainWall && !isMid) return;

                        const isNeutral = w.smart_bias === "NEUTRAL";
                        const isSell = w.smart_bias === "SELL";
                        const proxTol = symKey === "WDO" ? 1.5 : 35;
                        const isNearestActive = (nearestResP > 0 && Math.abs(w.price - nearestResP) <= proxTol)
                            || (nearestSupP > 0 && Math.abs(w.price - nearestSupP) <= proxTol);

                        const defLots = Number(w.defense_lots || 0);
                        const instTot = Number(w.inst_total_vol || 0);
                        const makerLots = Number(w.maker_hedge_lots || 0);
                        const powerPct = Number(w.wall_power_pct || (isMid ? 24 : (w.width || 1) * 28));
                        const tier = w.wall_tier || (
                            powerPct >= 45 ? "FORTE"
                                : (powerPct >= (isMid ? 20 : 25) || instTot > 0 || makerLots > 0) ? "MODERADA"
                                    : "FRACA"
                        );

                        if (tier === "FRACA" && !isNearestActive && isNeutral) return;

                        const isStrong = w.smart_stage === "FORTE"
                            || (tier === "FORTE" && (!isMid || defLots > 0 || isNearestActive));
                        const scaleFactor = isStrong ? (isMid ? 0.44 : 0.58) : (isMid ? 0.26 : 0.35);
                        const halfW = baseBandPts * scaleFactor;

                        zonesToRender.push({
                            key: `wall-zone-${idx}`,
                            topP: w.price + halfW,
                            botP: w.price - halfW,
                            isNeutral,
                            isSell,
                            isStrong,
                            isMid,
                        });
                    });

                    return zonesToRender.map((z) => {
                        if (z.topP < minP || z.botP > maxP) return null;
                        const yTop = Math.max(p1Top, toY1(Math.min(maxP, z.topP)));
                        const yBot = Math.min(p1Bot, toY1(Math.max(minP, z.botP)));
                        const hBand = Math.max(5, yBot - yTop);
                        const isWhiteWallMode = isWallsHost || wallColorMode === "PINE" || z.isNeutral;
                        const col = isWallsHost
                            ? (z.isMid ? "#8b9bb0" : "#f1f5f9")
                            : (isWhiteWallMode ? "#ffffff" : (z.isSell ? "#ff3860" : "#00e87a"));
                        const fillRgba = isWallsHost
                            ? (z.isMid
                                ? (z.isStrong ? "rgba(148, 163, 184, 0.04)" : "rgba(148, 163, 184, 0.02)")
                                : (z.isStrong ? "rgba(241, 245, 249, 0.055)" : "rgba(241, 245, 249, 0.032)"))
                            : (isWhiteWallMode
                                ? (z.isStrong ? "rgba(255, 255, 255, 0.06)" : (z.isMid ? "rgba(255, 255, 255, 0.025)" : "rgba(255, 255, 255, 0.04)"))
                                : (z.isSell
                                    ? (z.isStrong ? "rgba(255, 56, 96, 0.13)" : (z.isMid ? "rgba(255, 56, 96, 0.05)" : "rgba(255, 56, 96, 0.08)"))
                                    : (z.isStrong ? "rgba(0, 232, 122, 0.13)" : (z.isMid ? "rgba(0, 232, 122, 0.05)" : "rgba(0, 232, 122, 0.08)"))));
                        const borderDash = z.isMid ? "3,3" : "none";
                        return (
                            <g key={z.key}>
                                <rect x={padL} y={yTop} width={plotW} height={hBand} fill={fillRgba} />
                                {!isWallsHost && z.isStrong && !z.isNeutral && (
                                    <line
                                        x1={padL}
                                        y1={z.isSell ? yBot : yTop}
                                        x2={padL + plotW}
                                        y2={z.isSell ? yBot : yTop}
                                        stroke={col}
                                        strokeWidth="0.7"
                                        strokeDasharray={borderDash}
                                        strokeOpacity="0.35"
                                    />
                                )}
                            </g>
                        );
                    });
                })()}

                {/* ── LINHAS E LABELS OFICIAIS DO `jumba_tradingview.pine` + TRADUÇÃO DINÂMICA (Vai Defender / Violinada / Romperam / Virou) ── */}
                {nearbyWalls.map((w, i) => {
                    const yW = toY1(w.price);
                    const wType = String(w.type || "Wall");
                    const isMid = wType.toLowerCase().includes("mid") || String(w.label || "").toUpperCase() === "MIDLEWALL";
                    const isNeutral = w.smart_bias === "NEUTRAL" || Boolean(w.is_exhausted);
                    const isSell = w.smart_bias === "SELL";

                    const pineCol = wType === "GammaFlip" ? "#ffd600"
                        : wType === "MaxGamma" ? "#00b0ff"
                            : wType === "MinGamma" ? "#ff1744"
                                : isMid ? "#94a3b8" : "#ffffff";
                    const polCol = wType === "GammaFlip"
                        ? "#ffd600"
                        : w.is_exhausted
                            ? "#7f96a8"
                            : isNeutral
                                ? pineCol
                                : (isSell ? (isMid ? "#ff6b8b" : "#ff3860") : (isMid ? "#38ef94" : "#00e87a"));
                    const col = isWallsHost
                        ? (isMid ? "#8b9bb0" : "#f1f5f9")
                        : (wallColorMode === "PINE" ? pineCol : polCol);
                    const textCol = (!isWallsHost && wallColorMode !== "PINE" && w.is_trap) ? "#fbbf24" : col;

                    const isStrong = w.smart_stage === "FORTE" && !w.is_exhausted;
                    const strokeW = isMid
                        ? (isStrong ? 1.35 : 1.05)
                        : Math.max(1.2, Math.min(3.0, Number(w.width || 1) * (isStrong ? 0.95 : 0.85)));
                    const isDashed = w.style === "dashed" || isMid || Boolean(w.is_exhausted);
                    const hideRightAxisTag = Math.abs(yW - lastY) < 12;

                    const instD = Number(w.inst_delta || 0);
                    const absD = Math.abs(instD);
                    const instTot = Number(w.inst_total_vol || 0);
                    const signD = instD > 0 ? "+" : "-";
                    const deltaShort = absD >= 1000
                        ? `Δ${signD}${(absD / 1000).toFixed(absD >= 10000 ? 0 : 1)}k`
                        : absD > 0
                            ? `Δ${signD}${fmtNum(absD, 0)}`
                            : "";
                    const dirArrow = instD > 0 ? " ▲" : (instD < 0 ? " ▼" : "");
                    const deltaCol = wallColorMode === "PINE"
                        ? pineCol
                        : (instD > 0 ? "#00e87a" : (instD < 0 ? "#ff6b8b" : col));

                    const shortTag = isMid ? "Mid" : (wType === "Wall" ? "MW" : wType);
                    const pVerdict = isWallsHost && w.player_verdict && w.player_verdict !== "⏳ Aguardando Toque na Wall"
                        ? w.player_verdict
                        : "";
                    const verdictStr = (wType === "Wall" || wType === "MidWall" || isMid)
                        ? (pVerdict || w.live_verdict || "")
                        : "";
                    const rightInnerLabel = verdictStr
                        ? `${shortTag} · ${verdictStr}`
                        : shortTag;
                    const hasDeltaInfo = (absD > 0 || instTot > 0) && Boolean(deltaShort);
                    const instAggrW = Number(w.inst_aggr_delta ?? instD);
                    const instPassW = Number(w.inst_pass_delta ?? 0);
                    const retDeltaW = Number(w.ret_delta ?? 0);
                    const hftChurnW = Number(w.hft_churn_pct ?? 0);
                    const rlpShareW = Number(w.rlp_share_pct ?? w.rlp_pct ?? 0);
                    const hftDeltaW = Number(w.hft_delta ?? 0);
                    const rlpDeltaW = Number(w.rlp_delta ?? Math.round(-retDeltaW * (rlpShareW / 100.0)));
                    const fmtShortK = (val) => {
                        const av = Math.abs(Number(val || 0));
                        const sg = Number(val || 0) >= 0 ? "+" : "-";
                        return av >= 1000 ? `${sg}${(av / 1000).toFixed(av >= 10000 ? 0 : 1)}k` : `${sg}${Math.round(av)}`;
                    };
                    const profit4PlayerSub = isWallsHost && (Math.abs(instAggrW) > 0 || Math.abs(instPassW) > 0 || Math.abs(retDeltaW) > 0 || Math.abs(hftDeltaW) > 0)
                        ? `🏦Agr:${fmtShortK(instAggrW)} Pas:${fmtShortK(instPassW)} · 🧑‍💻Var:${fmtShortK(retDeltaW)} · ⚡HFT:${fmtShortK(hftDeltaW)} · 🔄RLP:${fmtShortK(rlpDeltaW)}`
                        : "";
                    const profit4PlayerHoverExtra = isWallsHost && profit4PlayerSub
                        ? ` (Giro Bruto: ⚡HFT ${Math.round(hftChurnW)}% | 🔄RLP ${Math.round(rlpShareW)}%)`
                        : "";
                    const belowLineDeltaText = profit4PlayerSub
                        ? (hideRightAxisTag ? `${fmtNum(w.price, dec)} · ${profit4PlayerSub}` : profit4PlayerSub)
                        : hasDeltaInfo
                            ? (hideRightAxisTag ? `${fmtNum(w.price, dec)} · ${deltaShort}${dirArrow}` : `${deltaShort}${dirArrow}`)
                            : (hideRightAxisTag ? `${fmtNum(w.price, dec)}` : "");
                    const topBrokersTitle = isWallsHost && Array.isArray(w.top_wall_brokers) && w.top_wall_brokers.length > 0
                        ? ` | Top Players na Wall: ${w.top_wall_brokers.map(tb => `${tb.broker} (${tb.net >= 0 ? "+" : ""}${Math.round(tb.net)})`).join(", ")}`
                        : "";

                    return (
                        <g key={`pine-wall-${i}`}>
                            <title>{`${w.label || wType} @ ${fmtNum(w.price, dec)}`}</title>
                            <line
                                x1={padL}
                                y1={yW}
                                x2={padL + plotW}
                                y2={yW}
                                stroke={col}
                                strokeWidth={strokeW}
                                strokeDasharray={isDashed ? "5,4" : "none"}
                                opacity={isNeutral ? (isMid ? "0.45" : "0.68") : (isMid ? "0.80" : "0.95")}
                            />
                            {/* Camadas de escrita acima/abaixo da Wall desativadas na 5176 (apenas linhas limpas + preço na escala direita) */}
                            {!isWallsHost && (
                                <>
                                    <text
                                        x={padL + plotW - 6}
                                        y={yW - 3.5}
                                        textAnchor="end"
                                        fill={textCol}
                                        fontSize={isMid ? "7.2" : "7.8"}
                                        fontWeight="bold"
                                        fontFamily="monospace"
                                        opacity={isNeutral ? "0.68" : "0.96"}
                                    >
                                        {rightInnerLabel}
                                    </text>
                                    {belowLineDeltaText && (
                                        <text
                                            x={padL + plotW - 6}
                                            y={yW + 9.5}
                                            textAnchor="end"
                                            fill={hasDeltaInfo ? deltaCol : col}
                                            fontSize={isMid ? "7.3" : "7.8"}
                                            fontWeight="bold"
                                            fontFamily="monospace"
                                            opacity="0.98"
                                        >
                                            {belowLineDeltaText}
                                        </text>
                                    )}
                                </>
                            )}
                            {/* Etiqueta de Preço no Eixo Y Direito */}
                            {!hideRightAxisTag && (
                                <g>
                                    <rect
                                        x={padL + plotW + 2}
                                        y={yW - 7}
                                        width={padR - 8}
                                        height={14}
                                        rx="2"
                                        fill="#0c1218"
                                        stroke={col}
                                        strokeWidth={isMid ? "0.65" : "0.9"}
                                        strokeDasharray={isMid ? "3,2" : "none"}
                                    />
                                    <text
                                        x={padL + plotW + 5}
                                        y={yW + 3.5}
                                        fill={col}
                                        fontSize={isMid ? "7.3" : "7.8"}
                                        fontWeight="bold"
                                        fontFamily="monospace"
                                    >
                                        {fmtNum(w.price, dec)}
                                    </text>
                                </g>
                            )}
                        </g>
                    );
                })}

                {/* Divisória Vertical indicando o início do Pregão de Hoje (quando há barras de warm-up do dia anterior) */}
                {firstTodayLocalIdx > 0 && (
                    <g>
                        <line
                            x1={toX(firstTodayLocalIdx) - stepX * 0.45}
                            y1={p1Top}
                            x2={toX(firstTodayLocalIdx) - stepX * 0.45}
                            y2={p3Bot}
                            stroke="#00d4ff"
                            strokeWidth="1.3"
                            strokeDasharray="4,3"
                            strokeOpacity="0.85"
                        />
                        <rect
                            x={toX(firstTodayLocalIdx) - stepX * 0.45 + 3}
                            y={p1Top + 4}
                            width={68}
                            height={13}
                            rx="3"
                            fill="#0c1218"
                            stroke="#00d4ff"
                            strokeWidth="1"
                        />
                        <text
                            x={toX(firstTodayLocalIdx) - stepX * 0.45 + 7}
                            y={p1Top + 13}
                            fill="#00d4ff"
                            fontSize="7.5"
                            fontWeight="bold"
                            fontFamily="monospace"
                        >
                            HOJE {series[firstTodayLocalIdx]?.time}
                        </text>
                    </g>
                )}

                {/* Marcadores e Linhas de Virada da Janela de Fluxo (Sincronizados com o cruzamento real da Linha Zero) */}
                {(() => {
                    const flips = [];
                    let prevPos = null;
                    subPanelBars.forEach((sb, idx) => {
                        const wv = Number(sb.smartSwingWave || 0);
                        const isPos = wv >= 0;
                        if (prevPos !== null && isPos !== prevPos) {
                            flips.push({ idx, isBuy: isPos, time: series[idx]?.time });
                        }
                        prevPos = isPos;
                    });

                    return flips.map((fl, fIdx) => {
                        const xStart = toX(fl.idx);
                        return (
                            <g key={`flip-cross-${fIdx}`}>
                                {showWindowFlips && (
                                    <line
                                        x1={xStart}
                                        y1={p1Top}
                                        x2={xStart}
                                        y2={p3Bot}
                                        stroke="#ffd600"
                                        strokeWidth="1.0"
                                        strokeDasharray="4,3"
                                        strokeOpacity="0.55"
                                    />
                                )}
                                {!isWallsHost && flowSubMode === "JANELA_ASG" && yZeroWave >= flowPlotTop && yZeroWave <= flowPlotBot && (
                                    <circle cx={xStart} cy={yZeroWave} r="2.6" fill="#f5d061" stroke="#0c1218" strokeWidth="0.8" opacity="0.9" />
                                )}
                            </g>
                        );
                    });
                })()}

                {/* ── FUNDO SUAVE DO ENVELOPE NWE (NWE30 NA 5176 | NWE40 NA 5174) ── */}
                {showNweLine && (() => {
                    const validNwePts = series
                        .map((pt, idx) => ({ pt, idx, nu: getNweUpper(pt), nl: getNweLower(pt) }))
                        .filter(({ nu, nl }) => nu > 0 && nl > 0);
                    if (validNwePts.length < 2) return null;
                    const upperPoly = validNwePts
                        .map(({ nu, idx }) => `${toX(idx).toFixed(1)},${Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(nu))).toFixed(1)}`)
                        .join(" ");
                    const lowerRev = [...validNwePts]
                        .reverse()
                        .map(({ nl, idx }) => `${toX(idx).toFixed(1)},${Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(nl))).toFixed(1)}`)
                        .join(" ");
                    return (
                        <g pointerEvents="none">
                            <polygon
                                points={`${upperPoly} ${lowerRev}`}
                                fill={isWallsHost ? "#94a3b8" : "#00e87a"}
                                fillOpacity={isWallsHost ? "0.03" : "0.025"}
                            />
                        </g>
                    );
                })()}

                {/* ── FUNDO DAS CAIXAS DE OPERAÇÃO ATRÁS DOS CANDLES (ISOLA CONTRASTE DAS WALLS) ── */}
                {showSignalsMarkers && plottedSignals.map((sig) => {
                    const isBuy = sig.dir_num > 0;
                    const clampY = (yVal) => Math.max(p1Top + 3, Math.min(p1Bot - 3, yVal));

                    const entryP = Number(sig.entry_price || 0);
                    if (!(entryP > 0)) return null;
                    const hasFixedTp = String(sig.tp_tag || "") !== "VIRADA ASG" && Number(sig.tp_price) > 0;
                    const defaultSlPts = symKey === "WDO" ? 10.0 : 300.0;
                    const defaultTpPts = symKey === "WDO" ? 10.0 : 350.0;
                    const stopP = Number(sig.stop_price || (entryP - sig.dir_num * defaultSlPts));
                    const tpP = Number(sig.tp_price || (entryP + sig.dir_num * defaultTpPts));
                    const exitP = Number(sig.exit_price || (entryP + sig.dir_num * Number(sig.realized_pts || 0)));
                    const beStopP = sig.be_stop_price != null ? Number(sig.be_stop_price) : entryP;

                    const x1 = toX(sig.idxStart);
                    const rawX2 = toX(sig.idxEnd);
                    const x2 = Math.max(x1 + Math.max(18, stepX * 1.2), rawX2);
                    const boxW = Math.max(2, x2 - x1);
                    const hasBeStep = Boolean(
                        sig.be_triggered
                        && sig.idxBe !== null
                        && sig.idxBe >= sig.idxStart
                        && sig.idxBe <= sig.idxEnd
                    );
                    const xBe = hasBeStep
                        ? Math.min(x2 - 4, Math.max(x1 + Math.max(6, stepX * 0.5), toX(sig.idxBe)))
                        : null;

                    const yEntry = clampY(toY1(entryP));
                    const yStop = clampY(toY1(stopP));
                    const effectiveTpP = isBuy ? Math.max(tpP, exitP > entryP ? exitP : tpP) : Math.min(tpP, exitP < entryP ? exitP : tpP);
                    const yTpBox = clampY(toY1(effectiveTpP));
                    const yBeStop = clampY(toY1(beStopP));

                    const tpTop = Math.min(yEntry, yTpBox);
                    const tpH = Math.max(2, Math.abs(yTpBox - yEntry));
                    const slTop = Math.min(yEntry, yStop);
                    const slH = Math.max(2, Math.abs(yStop - yEntry));
                    const fullBoxTop = hasFixedTp
                        ? Math.min(tpTop, slTop)
                        : (hasBeStep ? Math.min(slTop, yBeStop) : slTop);
                    const fullBoxBot = hasFixedTp
                        ? Math.max(tpTop + tpH, slTop + slH)
                        : (hasBeStep ? Math.max(slTop + slH, yBeStop) : slTop + slH);

                    const isPositiveBe = isBuy ? (beStopP >= entryP) : (beStopP <= entryP);
                    const postBeTpTop = isPositiveBe ? Math.min(yBeStop, yTpBox) : tpTop;
                    const postBeTpH = isPositiveBe ? Math.max(2, Math.abs(yTpBox - yBeStop)) : tpH;
                    const postBeSlTop = Math.min(yEntry, yBeStop);
                    const postBeSlH = Math.max(2, Math.abs(yBeStop - yEntry));

                    return (
                        <g key={`tv-box-bg-${sig.id}`} pointerEvents="none">
                            {/* Máscara Escura de Contraste (isola a caixa do trade das faixas verdes/vermelhas das Walls) */}
                            <rect
                                x={x1}
                                y={fullBoxTop}
                                width={boxW}
                                height={Math.max(4, fullBoxBot - fullBoxTop)}
                                fill="#05080d"
                                fillOpacity="0.82"
                                rx="1.5"
                            />
                            {/* Zona de Ganho / Alvo em Ciano-Teal (Apenas em WIN_1 e WDO_1 que possuem TP fixo) */}
                            {hasFixedTp && (
                                hasBeStep && xBe !== null ? (
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
                                            fillOpacity="0.24"
                                        />
                                    </>
                                ) : (
                                    <rect
                                        x={x1}
                                        y={tpTop}
                                        width={boxW}
                                        height={tpH}
                                        fill="#089981"
                                        fillOpacity="0.28"
                                    />
                                )
                            )}
                            {/* Zona de Risco / Stop Loss Inicial + Redução Estrutural pós-BE */}
                            {hasBeStep && xBe !== null ? (
                                <>
                                    <rect
                                        x={x1}
                                        y={slTop}
                                        width={Math.max(1, xBe - x1)}
                                        height={slH}
                                        fill="#e11d48"
                                        fillOpacity="0.32"
                                    />
                                    <rect
                                        x={xBe}
                                        y={slTop}
                                        width={Math.max(1, x2 - xBe)}
                                        height={slH}
                                        fill="#e11d48"
                                        fillOpacity="0.08"
                                    />
                                    {!isPositiveBe && (
                                        <rect
                                            x={xBe}
                                            y={postBeSlTop}
                                            width={Math.max(1, x2 - xBe)}
                                            height={postBeSlH}
                                            fill="#e11d48"
                                            fillOpacity="0.24"
                                        />
                                    )}
                                </>
                            ) : (
                                <rect
                                    x={x1}
                                    y={slTop}
                                    width={boxW}
                                    height={slH}
                                    fill="#e11d48"
                                    fillOpacity="0.28"
                                />
                            )}
                            <line x1={x1} y1={fullBoxTop} x2={x1} y2={fullBoxBot} stroke="#94a3b8" strokeWidth="0.8" strokeOpacity="0.45" />
                            <line x1={x2} y1={fullBoxTop} x2={x2} y2={fullBoxBot} stroke="#94a3b8" strokeWidth="0.8" strokeOpacity="0.45" />
                        </g>
                    );
                })}

                {/* ── CANDLES DO PREÇO (MODO TRADICIONAL PADRÃO OU PINTADOS PELA JANELA A.S.G) ── */}
                {series.map((pt, idx) => {
                    const x = toX(idx);
                    const yH = toY1(pt.high || pt.close);
                    const yL = toY1(pt.low || pt.close);
                    const yO = toY1(pt.open || pt.close);
                    const yC = toY1(pt.close);

                    const oVal = Number(pt.open ?? pt.close);
                    const cVal = Number(pt.close);
                    const cState = pt.candle_state ?? (pt.window_dir || 0);
                    const isBullCandle = cVal >= oVal;
                    const fillCol = isWallsHost
                        ? (isBullCandle ? "#cbd5e1" : "#475569")
                        : (candleColorMode === "TRADICIONAL"
                            ? (isBullCandle ? "#00e87a" : "#ff3860")
                            : (cState > 0 ? "#00e87a" : cState < 0 ? "#ff3860" : "#7f96a8"));
                    const wickCol = isWallsHost
                        ? (isBullCandle ? "#cbd5e1" : "#64748b")
                        : fillCol;
                    const bodyTop = Math.min(yO, yC);
                    const bodyH = Math.max(2.0, Math.abs(yC - yO));

                    return (
                        <g key={`p-candle-${idx}`}>
                            <line x1={x} y1={yH} x2={x} y2={yL} stroke={wickCol} strokeWidth="1.2" strokeOpacity="0.9" />
                            <rect
                                x={x - candleW / 2}
                                y={bodyTop}
                                width={candleW}
                                height={bodyH}
                                fill={fillCol}
                                stroke={isWallsHost && !isBullCandle ? "#64748b" : "none"}
                                strokeWidth={isWallsHost && !isBullCandle ? "0.65" : "0"}
                                rx="0.8"
                            />
                        </g>
                    );
                })}

                {/* ── CAMADA A: MÚLTIPLAS MARCAÇÕES DINÂMICAS DAS BATALHAS NA WALL AO LONGO DOS CANDLES (DESATIVADO NA 5176 PARA LEITURA LIMPA) ── */}
                {!isWallsHost && showWallBattleLabels && (() => {
                    const seenByCandle = new Set();
                    const markers = [];

                    nearbyWalls.forEach((w) => {
                        if (!Array.isArray(w.dynamic_events) || w.dynamic_events.length === 0) return;
                        const wType = String(w.type || "Wall");
                        const isMid = wType.toLowerCase().includes("mid") || String(w.label || "").toUpperCase() === "MIDLEWALL";
                        // Prioriza todas as MagicWalls principais e MidWalls com participação institucional
                        if (isMid && Number(w.inst_total_vol || 0) <= 0 && w.smart_bias === "NEUTRAL") return;

                        // Mantém até as 4 batalhas mais recentes daquela Wall visíveis para leitura dinâmica limpa
                        const evSlice = w.dynamic_events.slice(-4);
                        evSlice.forEach((ev) => {
                            const dedupKey = `${ev.idx}_${ev.dir}`;
                            if (seenByCandle.has(dedupKey)) return;
                            seenByCandle.add(dedupKey);
                            markers.push({
                                ...ev,
                                wallPrice: w.price,
                                isMid,
                            });
                        });
                    });

                    return markers.map((mk, mIdx) => {
                        const pt = series[mk.idx];
                        if (!pt) return null;
                        const x = toX(mk.idx);
                        const yWall = toY1(mk.wallPrice);
                        if (yWall < p1Top + 8 || yWall > p1Bot - 8) return null;

                        const isTrap = mk.type.startsWith("VIOLINADA");
                        const isBreak = mk.type.startsWith("ROMPEU");
                        const isBuyDir = mk.dir > 0;
                        const col = isTrap
                            ? "#fbbf24"
                            : (isBreak
                                ? (isBuyDir ? "#00e5ff" : "#ff4081")
                                : (isBuyDir ? "#00e87a" : "#ff3860"));

                        const yH = toY1(pt.high || pt.close);
                        const yL = toY1(pt.low || pt.close);
                        const rawBadgeY = isBuyDir
                            ? Math.min(p1Bot - 13, Math.max(yWall + 4, yL + 3))
                            : Math.max(p1Top + 3, Math.min(yWall - 15, yH - 14));

                        const txt = mk.label || "🛡️ Defendeu";
                        const boxW = Math.max(44, txt.length * 4.3 + 6);
                        const boxX = Math.max(padL + 2, Math.min(padL + plotW - boxW - 4, x - boxW / 2));

                        return (
                            <g key={`wall-dyn-ev-${mIdx}`} pointerEvents="none">
                                <circle
                                    cx={x}
                                    cy={yWall}
                                    r={mk.isMid ? "2.3" : "2.9"}
                                    fill={col}
                                    stroke="#060a0f"
                                    strokeWidth="1"
                                />
                                <line
                                    x1={x}
                                    y1={yWall}
                                    x2={x}
                                    y2={isBuyDir ? rawBadgeY : rawBadgeY + 11}
                                    stroke={col}
                                    strokeWidth="0.8"
                                    strokeDasharray="2,1"
                                    strokeOpacity="0.75"
                                />
                                <rect
                                    x={boxX}
                                    y={rawBadgeY}
                                    width={boxW}
                                    height={11}
                                    rx="2.5"
                                    fill="#070c12"
                                    fillOpacity="0.90"
                                    stroke={col}
                                    strokeWidth="0.75"
                                />
                                <text
                                    x={boxX + boxW / 2}
                                    y={rawBadgeY + 8}
                                    textAnchor="middle"
                                    fill={col}
                                    fontSize="6.7"
                                    fontWeight="bold"
                                    fontFamily="monospace"
                                >
                                    {txt}
                                </text>
                            </g>
                        );
                    });
                })()}

                {/* ── ENVELOPE COMPLETO DA MÉDIA NWE (NWE30 NA 5176 | NWE40 NA 5174: UPPER, CENTER, LOWER) ── */}
                {showNweLine && (() => {
                    const segments = [];
                    for (let i = 1; i < series.length; i++) {
                        const prev = series[i - 1];
                        const curr = series[i];
                        const pLine = getNweLine(prev);
                        const cLine = getNweLine(curr);
                        if (!(pLine > 0 && cLine > 0)) continue;
                        const pU = getNweUpper(prev);
                        const cU = getNweUpper(curr);
                        const pL = getNweLower(prev);
                        const cL = getNweLower(curr);
                        const cIsUp = getNweIsUp(curr);
                        const x1 = toX(i - 1);
                        const x2 = toX(i);
                        const yC1 = Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(pLine)));
                        const yC2 = Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(cLine)));
                        const yU1 = pU > 0 ? Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(pU))) : null;
                        const yU2 = cU > 0 ? Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(cU))) : null;
                        const yL1 = pL > 0 ? Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(pL))) : null;
                        const yL2 = cL > 0 ? Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(cL))) : null;
                        const isUp = cIsUp !== undefined ? Boolean(cIsUp) : (cLine >= pLine);
                        segments.push({ x1, x2, yC1, yC2, yU1, yU2, yL1, yL2, isUp, key: `nwe-seg-${i}` });
                    }
                    const lastNwe = getNweLine(lastPt);
                    const lastNweUp = getNweIsUp(lastPt) !== false;
                    const lastNweCol = isWallsHost ? "#94a3b8" : (lastNweUp ? "#00e87a" : "#ff3860");
                    const rawNweY = lastNwe > 0 ? Math.max(p1Top + 10, Math.min(p1Bot - 10, toY1(lastNwe))) : null;
                    const badgeNweY = rawNweY !== null
                        ? (Math.abs(rawNweY - lastY) < 17 ? (rawNweY < lastY ? Math.max(p1Top + 9, lastY - 18) : Math.min(p1Bot - 9, lastY + 18)) : rawNweY)
                        : null;

                    return (
                        <g pointerEvents="none">
                            {segments.map(seg => {
                                const col = isWallsHost ? "#94a3b8" : (seg.isUp ? "#00e87a" : "#ff3860");
                                const bandCol = isWallsHost ? "#64748b" : col;
                                return (
                                    <g key={seg.key}>
                                        {seg.yU1 !== null && seg.yU2 !== null && (
                                            <line
                                                x1={seg.x1}
                                                y1={seg.yU1}
                                                x2={seg.x2}
                                                y2={seg.yU2}
                                                stroke={bandCol}
                                                strokeWidth={isWallsHost ? "1.15" : "1.45"}
                                                strokeLinecap="round"
                                                opacity={isWallsHost ? "0.60" : "0.88"}
                                            />
                                        )}
                                        <line
                                            x1={seg.x1}
                                            y1={seg.yC1}
                                            x2={seg.x2}
                                            y2={seg.yC2}
                                            stroke={col}
                                            strokeWidth={isWallsHost ? "1.40" : "1.85"}
                                            strokeLinecap="round"
                                            opacity={isWallsHost ? "0.68" : "0.96"}
                                        />
                                        {seg.yL1 !== null && seg.yL2 !== null && (
                                            <line
                                                x1={seg.x1}
                                                y1={seg.yL1}
                                                x2={seg.x2}
                                                y2={seg.yL2}
                                                stroke={bandCol}
                                                strokeWidth={isWallsHost ? "1.15" : "1.45"}
                                                strokeLinecap="round"
                                                opacity={isWallsHost ? "0.60" : "0.88"}
                                            />
                                        )}
                                    </g>
                                );
                            })}
                            {rawNweY !== null && badgeNweY !== null && (
                                <g>
                                    <rect
                                        x={padL + plotW + 1}
                                        y={badgeNweY - 7.5}
                                        width={padR - 5}
                                        height={15}
                                        rx="3"
                                        fill="#0c1218"
                                        stroke={lastNweCol}
                                        strokeWidth="1"
                                    />
                                    <text
                                        x={padL + plotW + 6}
                                        y={badgeNweY + 3}
                                        fill={lastNweCol}
                                        fontSize="8.2"
                                        fontWeight="bold"
                                        fontFamily="monospace"
                                    >
                                        {isWallsHost ? "NWE30" : "NWE"} {fmtNum(lastNwe, dec)} {lastNweUp ? "↑" : "↓"}
                                    </text>
                                </g>
                            )}
                        </g>
                    );
                })()}

                {/* ── LINHAS DE DIVERGÊNCIA TOPO/FUNDO NO GRÁFICO DE PREÇO (F1 ➔ F2 ↘ / T1 ➔ T2 ↗) SINCRONIZADAS COM A ONDA DE FLUXO ── */}
                {isWallsFlowLocalhost() && showSwingDivLines && swingDivergences.map((dv, dIdx) => {
                    const isBull = dv.type === "BULL_DIV";
                    const x1 = toX(dv.prevIdx);
                    const x2 = toX(dv.currIdx);
                    const rawY1 = toY1(dv.prevPrice);
                    const rawY2 = toY1(dv.currPrice);
                    const y1 = isBull
                        ? Math.max(p1Top + 18, Math.min(p1Bot - 16, rawY1 + 5))
                        : Math.max(p1Top + 18, Math.min(p1Bot - 16, rawY1 - 5));
                    const y2 = isBull
                        ? Math.max(p1Top + 18, Math.min(p1Bot - 16, rawY2 + 5))
                        : Math.max(p1Top + 18, Math.min(p1Bot - 16, rawY2 - 5));
                    const col = dv.isPendingTrigger ? "#ffd600" : (isBull ? "#00e87a" : "#ff3860");
                    const badgeTxt = dv.isPendingTrigger
                        ? (isBull ? "⏳ DIV. COMPRA NA WALL · Aguard. Gatilho" : "⏳ DIV. VENDA NA WALL · Aguard. Gatilho")
                        : (isBull
                            ? (dv.nearWall ? "🟢 DIV. COMPRA NA WALL · Fluxo ↑" : "🟢 DIV. COMPRA · Fluxo ↑")
                            : (dv.nearWall ? "🔴 DIV. VENDA NA WALL · Fluxo ↓" : "🔴 DIV. VENDA · Fluxo ↓"));
                    const badgeW = Math.max(92, badgeTxt.length * 4.4 + 8);
                    const badgeX = Math.max(padL + 4, Math.min(padL + plotW - badgeW - 4, x2 - badgeW / 2));
                    const badgeY = isBull
                        ? Math.min(p1Bot - 14, y2 + 5)
                        : Math.max(p1Top + 14, y2 - 17);
                    const fmtW = (v) => {
                        const av = Math.abs(Number(v || 0));
                        const sg = Number(v || 0) >= 0 ? "+" : "-";
                        return av >= 1000 ? `${sg}${(av / 1000).toFixed(1)}k` : `${sg}${Math.round(av)}`;
                    };
                    const tipStr = isBull
                        ? `🟢 DIVERGÊNCIA DE FUNDO (${dv.prevTime} ➔ ${dv.currTime}) | Preço fez fundo menor/duplo (${fmtNum(dv.prevPrice, dec)} ➔ ${fmtNum(dv.currPrice, dec)} ↘), mas Onda de Fluxo subiu (${fmtW(dv.prevWave)} ➔ ${fmtW(dv.currWave)} ↗) | Motor: ${dv.driver}`
                        : `🔴 DIVERGÊNCIA DE TOPO (${dv.prevTime} ➔ ${dv.currTime}) | Preço fez topo maior/duplo (${fmtNum(dv.prevPrice, dec)} ➔ ${fmtNum(dv.currPrice, dec)} ↗), mas Onda de Fluxo caiu (${fmtW(dv.prevWave)} ➔ ${fmtW(dv.currWave)} ↘) | Motor: ${dv.driver}`;

                    return (
                        <g key={`p1-swing-div-${dIdx}`}>
                            <title>{tipStr}</title>
                            {/* Conector Vertical Sutil entre Preço (F2/T2) e o Sub-Painel de Fluxo */}
                            <line
                                x1={x2}
                                y1={y2}
                                x2={x2}
                                y2={p1Bot}
                                stroke={col}
                                strokeWidth="0.85"
                                strokeDasharray="2,3"
                                opacity="0.45"
                            />
                            {/* Sombra / Glow da Linha de Divergência */}
                            <line
                                x1={x1}
                                y1={y1}
                                x2={x2}
                                y2={y2}
                                stroke="#05080d"
                                strokeWidth="3.2"
                                opacity="0.75"
                            />
                            {/* Linha Conectora F1 -> F2 ou T1 -> T2 no Preço */}
                            <line
                                x1={x1}
                                y1={y1}
                                x2={x2}
                                y2={y2}
                                stroke={col}
                                strokeWidth="1.9"
                                strokeDasharray="4,2"
                            />
                            <circle cx={x1} cy={y1} r="2.8" fill="#05080d" stroke={col} strokeWidth="1.4" />
                            <circle cx={x2} cy={y2} r="3.4" fill={col} stroke="#05080d" strokeWidth="1.1" />
                            <text
                                x={x1}
                                y={isBull ? y1 + 9 : y1 - 4}
                                fill={col}
                                fontSize="6.8"
                                fontWeight="bold"
                                fontFamily="monospace"
                                textAnchor="middle"
                            >
                                {isBull ? "F1" : "T1"}
                            </text>
                            <rect
                                x={badgeX}
                                y={badgeY}
                                width={badgeW}
                                height={12.5}
                                rx="3"
                                fill="#05080d"
                                fillOpacity="0.93"
                                stroke={col}
                                strokeWidth="1.0"
                            />
                            <text
                                x={badgeX + badgeW / 2}
                                y={badgeY + 8.8}
                                fill={col}
                                fontSize="7.0"
                                fontWeight="bold"
                                fontFamily="monospace"
                                textAnchor="middle"
                            >
                                {badgeTxt}
                            </text>
                        </g>
                    );
                })}

                {/* Linha de Preço Spot Atual + Badge Oficial na Escala Direita (#00d4ff) */}
                <g>
                    <line x1={padL} y1={lastY} x2={padL + plotW} y2={lastY} stroke="#00d4ff" strokeWidth="1" strokeDasharray="3,3" opacity="0.85" />
                    <rect x={padL + plotW + 1} y={lastY - 10} width={padR - 5} height={20} rx="3" fill="#00d4ff" />
                    <text x={padL + plotW + 7} y={lastY + 4} fill="#04080e" fontSize="10.5" fontWeight="bold" fontFamily="monospace">
                        {fmtNum(lastPt.close, dec)} {(lastPt.window_dir || 0) > 0 ? "▲" : "▼"}
                    </text>
                </g>

                {/* ── LINHAS DAS OPERAÇÕES NO PRIMEIRO PLANO (ACIMA DOS CANDLES E DA NWE) ── */}
                {showSignalsMarkers && plottedSignals.map((sig) => {
                    const isBuy = sig.dir_num > 0;
                    const clampY = (yVal) => Math.max(p1Top + 3, Math.min(p1Bot - 3, yVal));

                    const entryP = Number(sig.entry_price || 0);
                    if (!(entryP > 0)) return null;
                    const hasFixedTp = String(sig.tp_tag || "") !== "VIRADA ASG" && Number(sig.tp_price) > 0;
                    const defaultSlPts = symKey === "WDO" ? 10.0 : 300.0;
                    const defaultTpPts = symKey === "WDO" ? 10.0 : 350.0;
                    const stopP = Number(sig.stop_price || (entryP - sig.dir_num * defaultSlPts));
                    const tpP = Number(sig.tp_price || (entryP + sig.dir_num * defaultTpPts));
                    const exitP = Number(sig.exit_price || (entryP + sig.dir_num * Number(sig.realized_pts || 0)));
                    const beStopP = sig.be_stop_price != null ? Number(sig.be_stop_price) : entryP;
                    const beTrigP = sig.be_trigger_price != null ? Number(sig.be_trigger_price) : exitP;

                    const x1 = toX(sig.idxStart);
                    const rawX2 = toX(sig.idxEnd);
                    const x2 = Math.max(x1 + Math.max(18, stepX * 1.2), rawX2);
                    const hasBeStep = Boolean(
                        sig.be_triggered
                        && sig.idxBe !== null
                        && sig.idxBe >= sig.idxStart
                        && sig.idxBe <= sig.idxEnd
                    );
                    const xBe = hasBeStep
                        ? Math.min(x2 - 4, Math.max(x1 + Math.max(6, stepX * 0.5), toX(sig.idxBe)))
                        : null;

                    const yEntry = clampY(toY1(entryP));
                    const yStop = clampY(toY1(stopP));
                    const effectiveTpP = isBuy ? Math.max(tpP, exitP > entryP ? exitP : tpP) : Math.min(tpP, exitP < entryP ? exitP : tpP);
                    const yTpBox = clampY(toY1(effectiveTpP));
                    const yTpProj = clampY(toY1(tpP));
                    const yExit = clampY(toY1(exitP));
                    const yBeStop = clampY(toY1(beStopP));
                    const yBeTrig = clampY(toY1(beTrigP));

                    const tpTop = Math.min(yEntry, yTpBox);
                    const tpH = Math.max(2, Math.abs(yTpBox - yEntry));
                    const slTop = Math.min(yEntry, yStop);
                    const slH = Math.max(2, Math.abs(yStop - yEntry));
                    const fullBoxTop = hasFixedTp
                        ? Math.min(tpTop, slTop)
                        : (hasBeStep ? Math.min(slTop, yBeStop, yBeTrig) : slTop);
                    const fullBoxBot = hasFixedTp
                        ? Math.max(tpTop + tpH, slTop + slH)
                        : (hasBeStep ? Math.max(slTop + slH, yBeStop, yBeTrig) : slTop + slH);

                    const realizedPts = Number(sig.realized_pts || 0);
                    const isWinExit = realizedPts >= 0;
                    const isOpenTrade = sig.validation_status === "EM_ANDAMENTO";

                    const tp1P = Number(sig.tp1_price || 0);
                    const yTp1Proj = tp1P > 0 ? clampY(toY1(tp1P)) : null;

                    return (
                        <g key={`tv-box-fg-${sig.id}`} pointerEvents="none">
                            {/* Linha do Alvo Principal (TP2 750p no WIN_DIV_WALL ou TP MidWall no WDO_DIV_WALL) */}
                            {hasFixedTp && (
                                <line
                                    x1={x1}
                                    y1={yTpProj}
                                    x2={x2}
                                    y2={yTpProj}
                                    stroke="#2dd4bf"
                                    strokeWidth="1.2"
                                    strokeOpacity="0.95"
                                />
                            )}
                            {/* Linha Intermediária Tracejada do TP1 (NWE30 Banda Oposta Dinâmico do Lote 1 no WIN_DIV_WALL) */}
                            {yTp1Proj !== null && Math.abs(yTp1Proj - yTpProj) > 2 && (
                                <line
                                    x1={x1}
                                    y1={yTp1Proj}
                                    x2={x2}
                                    y2={yTp1Proj}
                                    stroke="#38bdf8"
                                    strokeWidth="1.15"
                                    strokeDasharray="3,2"
                                    strokeOpacity="0.92"
                                />
                            )}

                            {/* Linha do Stop Loss Inicial + Degrau do Breakeven */}
                            {hasBeStep && xBe !== null ? (
                                <>
                                    <line
                                        x1={xBe}
                                        y1={fullBoxTop}
                                        x2={xBe}
                                        y2={fullBoxBot}
                                        stroke="#fbbf24"
                                        strokeWidth="0.9"
                                        strokeDasharray="2,2"
                                        strokeOpacity="0.60"
                                    />
                                    <line
                                        x1={x1}
                                        y1={yStop}
                                        x2={xBe}
                                        y2={yStop}
                                        stroke="#fb7185"
                                        strokeWidth="1.25"
                                        strokeOpacity="0.95"
                                    />
                                    <line
                                        x1={xBe}
                                        y1={yStop}
                                        x2={x2}
                                        y2={yStop}
                                        stroke="#fb7185"
                                        strokeWidth="0.8"
                                        strokeDasharray="2,3"
                                        strokeOpacity="0.45"
                                    />
                                    <line
                                        x1={xBe}
                                        y1={yStop}
                                        x2={xBe}
                                        y2={yBeStop}
                                        stroke="#fbbf24"
                                        strokeWidth="1.25"
                                        strokeDasharray="2,2"
                                        strokeOpacity="0.95"
                                    />
                                    <line
                                        x1={xBe}
                                        y1={yBeStop}
                                        x2={x2}
                                        y2={yBeStop}
                                        stroke="#fbbf24"
                                        strokeWidth="1.35"
                                        strokeOpacity="0.98"
                                    />
                                    <circle cx={xBe} cy={yBeStop} r="2.4" fill="#fbbf24" stroke="#05080d" strokeWidth="0.8" />
                                </>
                            ) : (
                                <line
                                    x1={x1}
                                    y1={yStop}
                                    x2={x2}
                                    y2={yStop}
                                    stroke="#fb7185"
                                    strokeWidth="1.25"
                                    strokeOpacity="0.95"
                                />
                            )}

                            {/* Linha de Entrada Branca Nítida + Trajetória Tracejada (Entrada -> BE -> Saída) */}
                            <line
                                x1={x1}
                                y1={yEntry}
                                x2={x2}
                                y2={yEntry}
                                stroke="#f8fafc"
                                strokeWidth="1.25"
                                strokeOpacity="0.92"
                            />
                            {hasBeStep && xBe !== null ? (
                                <>
                                    <line
                                        x1={x1}
                                        y1={yEntry}
                                        x2={xBe}
                                        y2={yBeTrig}
                                        stroke="#e2e8f0"
                                        strokeWidth="1.05"
                                        strokeDasharray="3,3"
                                        strokeOpacity="0.80"
                                    />
                                    <line
                                        x1={xBe}
                                        y1={yBeTrig}
                                        x2={x2}
                                        y2={yExit}
                                        stroke="#e2e8f0"
                                        strokeWidth="1.05"
                                        strokeDasharray="3,3"
                                        strokeOpacity="0.65"
                                    />
                                </>
                            ) : (
                                <line
                                    x1={x1}
                                    y1={yEntry}
                                    x2={x2}
                                    y2={yExit}
                                    stroke="#e2e8f0"
                                    strokeWidth="1.05"
                                    strokeDasharray="3,3"
                                    strokeOpacity="0.78"
                                />
                            )}

                            {/* Pontos de Entrada e Saída em Primeiro Plano (Sem Pílulas de Texto sobre a Caixa) */}
                            <circle cx={x1} cy={yEntry} r="2.4" fill="#ffffff" stroke="#05080d" strokeWidth="0.9" />
                            {!isOpenTrade && (
                                <circle
                                    cx={x2}
                                    cy={yExit}
                                    r="2.7"
                                    fill={isWinExit ? "#2dd4bf" : "#fb7185"}
                                    stroke="#05080d"
                                    strokeWidth="1.0"
                                />
                            )}
                        </g>
                    );
                })}

                {/* Marcadores dos Sinais Emitidos (▲ COMPRA / ▼ VENDA; Nome do Setup só aparece no Hover ou Clique) */}
                {showSignalsMarkers && plottedSignals.map((sig) => {
                    const isBuy = sig.dir_num > 0;
                    const sid = String(sig.strategy_id || "");
                    const isWallsFlow = isWallsFlowLocalhost();
                    const shortMap = isWallsFlow ? {
                        WIN_DIV_WALL: "🎯 WIN Div · 2L Mix",
                        WDO_DIV_WALL: "🎯 WDO Div · 1L MidWall",
                    } : {
                        EST_01: "EST-01 PinBar",
                        EST_04: "EST-04 WDO-Alinh",
                        EST_07: "EST-07 Clímax",
                        EST_13: "EST-13 SG Scalp",
                        EST_14: "EST-14 SG Mom",
                        EST_15: "EST-15 SG Z30",
                        EST_16: "EST-16 SG Spring",
                        WDO_02: "WDO-02 Scalper",
                        WDO_07: "WDO-07 Absorção",
                        WDO_09: "WDO-09 Cluster",
                        WDO_10: "WDO-10 Lunch",
                        WDO_11: "WDO-02 Scalper",
                        WDO_S2: "WDO-10 Lunch",
                    };
                    const colorMap = {
                        WIN_DIV_WALL: "#00e87a",
                        WDO_DIV_WALL: "#ffd600",
                        EST_01: "#38bdf8",
                        EST_04: "#00d4ff",
                        EST_07: "#38bdf8",
                        EST_13: "#34d399",
                        EST_14: "#00e87a",
                        EST_15: "#22d3ee",
                        EST_16: "#818cf8",
                        WIN_E2: "#a78bfa",
                        WDO_02: "#f59e0b",
                        WDO_07: "#fbbf24",
                        WDO_09: "#ffd600",
                        WDO_10: "#f97316",
                        WDO_11: "#f59e0b",
                        WDO_S2: "#f97316",
                    };
                    const tagLabel = shortMap[sid] || sig.strategy_short || sid || (isBuy ? "COMPRA" : "VENDA");
                    const stratCol = colorMap[sid] || (isBuy ? "#00e87a" : "#ff3860");
                    const col = isBuy ? "#00e87a" : "#ff3860";
                    const isSelected = selectedSigId === sig.id;
                    const isHovered = hoveredSigId === sig.id;
                    const showLabel = isSelected || isHovered;
                    const x = sig.x;
                    const slotShift = (sig.sSlot || 0) * 10;
                    const y = sig.y + (isBuy ? slotShift : -slotShift);
                    const triPoints = isBuy
                        ? `${x},${y + 5} ${x - 4.8},${y + 13} ${x + 4.8},${y + 13}`
                        : `${x},${y - 5} ${x - 4.8},${y - 13} ${x + 4.8},${y - 13}`;
                    const ptsVal = Number(sig.realized_pts || 0);
                    const ptsTxt = sig.validation_status === "EM_ANDAMENTO"
                        ? "⏳"
                        : `${ptsVal >= 0 ? "+" : ""}${fmtNum(ptsVal, dec)}p`;
                    const pillText = `${tagLabel} (${ptsTxt})`;
                    const pillW = Math.max(66, pillText.length * 4.7 + 8);
                    const pillX = Math.max(padL + 2, Math.min(padL + plotW - pillW - 2, x - pillW / 2));
                    const pillY = isBuy
                        ? Math.min(p1Bot - 15, y + 15)
                        : Math.max(p1Top + 2, y - 28);
                    const beInfo = sig.be_triggered && sig.be_time
                        ? ` | BE acionado às ${sig.be_time} (Stop → ${fmtNum(sig.be_stop_price, dec)})`
                        : "";
                    const exitInfo = sig.exit_time && sig.validation_status !== "EM_ANDAMENTO"
                        ? ` | Saída às ${sig.exit_time} @ ${fmtNum(sig.exit_price, dec)}`
                        : "";

                    return (
                        <g
                            key={sig.id}
                            onMouseEnter={() => setHoveredSigId(sig.id)}
                            onMouseLeave={() => setHoveredSigId(prev => (prev === sig.id ? null : prev))}
                            onClick={(e) => {
                                e.stopPropagation();
                                if (onSelectSignal) onSelectSignal(isSelected ? null : sig.id);
                            }}
                            style={{ cursor: "pointer" }}
                        >
                            <title>{`${sig.time} · ${tagLabel} (${sid}) | Entrada @ ${fmtNum(sig.entry_price, dec)} | Stop @ ${fmtNum(sig.stop_price, dec)}${beInfo}${exitInfo} → ${sig.validation_label || ""}`}</title>
                            {/* Área de toque maior invisível para facilitar o hover e clique no marcador */}
                            <circle
                                cx={x}
                                cy={isBuy ? y + 9 : y - 9}
                                r="9"
                                fill="transparent"
                            />
                            <polygon
                                points={triPoints}
                                fill={col}
                                fillOpacity="0.95"
                                stroke={showLabel ? "#ffffff" : stratCol}
                                strokeWidth={showLabel ? "1.6" : "1.1"}
                            />
                            {showLabel && (
                                <>
                                    <rect
                                        x={pillX}
                                        y={pillY}
                                        width={pillW}
                                        height={13}
                                        rx="3"
                                        fill="#05080d"
                                        fillOpacity="0.95"
                                        stroke={isSelected ? "#ffffff" : stratCol}
                                        strokeWidth={isSelected ? "1.3" : "1.0"}
                                    />
                                    <text
                                        x={pillX + pillW / 2}
                                        y={pillY + 9.2}
                                        fill={stratCol}
                                        fontSize="7.5"
                                        fontWeight="bold"
                                        fontFamily="monospace"
                                        textAnchor="middle"
                                    >
                                        {pillText}
                                    </text>
                                </>
                            )}
                        </g>
                    );
                })}
                </g>

                {/* Botão 'A' (Auto Escala) estilo TradingView no canto inferior direito do Eixo de Preço */}
                {(() => {
                    const isPAuto = priceAutoScale && yZoomFactor === 1.0 && priceYOffset === 0;
                    return (
                        <g
                            onMouseDown={(e) => e.stopPropagation()}
                            onClick={(e) => {
                                e.stopPropagation();
                                if (isPAuto) {
                                    setPriceAutoScale(false);
                                } else {
                                    setPriceAutoScale(true);
                                    setYZoomFactor(1.0);
                                    setPriceYOffset(0);
                                }
                            }}
                            style={{ cursor: "pointer" }}
                        >
                            <title>{isPAuto ? "Escala de Preço Automática ligada (clique para modo livre 2D ou arraste a escala Y)" : "Clique para voltar a escala de Preço ao modo Automático (A)"}</title>
                            <rect
                                x={width - 21}
                                y={p1Bot - 16}
                                width={16}
                                height={13}
                                rx="2.5"
                                fill={isPAuto ? "rgba(0, 212, 255, 0.22)" : "#0c1218"}
                                stroke={isPAuto ? "#00d4ff" : "#334155"}
                                strokeWidth="0.9"
                            />
                            <text
                                x={width - 13}
                                y={p1Bot - 6.8}
                                fill={isPAuto ? "#00d4ff" : "#7f96a8"}
                                fontSize="8"
                                fontWeight="bold"
                                fontFamily="monospace"
                                textAnchor="middle"
                            >
                                A
                            </text>
                        </g>
                    );
                })()}

                {/* ══════════════════════════════════════════════════════════════════════
                   PAINEL 2 (BASE): FLUXO SMART MONEY (ESCALA VARIÁVEL ESTILO TRADINGVIEW + F1➔F2 / T1➔T2)
                   ══════════════════════════════════════════════════════════════════════ */}
                {flowSubMode === "SWING_DIVERGENCIA" && (() => {
                    const wavePts = subPanelBars.map((sb) => `${toX(sb.idx).toFixed(1)},${toYSwingWave(sb.smartSwingWave).toFixed(1)}`).join(" ");
                    const lastSb = subPanelBars[subPanelBars.length - 1] || {};
                    const lastWaveY = toYSwingWave(lastSb.smartSwingWave || 0);
                    const isFAuto = flowAutoScale && flowYZoom === 1.0 && flowYOffset === 0;
                    const fmtW = (v) => {
                        const num = Number(v || 0);
                        if (Math.abs(num) < 0.5) return "0";
                        const av = Math.abs(num);
                        const sg = num > 0 ? "+" : "-";
                        return av >= 1000 ? `${sg}${(av / 1000).toFixed(1)}k` : `${sg}${Math.round(av)}`;
                    };

                    return (
                        <g>
                            {/* Grade e Marcações Dinâmicas da Escala Variável do Fluxo Smart Money */}
                            {flowAxisTicks.map((tk, fIdx) => {
                                const isZeroTick = Math.abs(tk.val) < 1e-3;
                                const nearCur = Math.abs(tk.y - lastWaveY) < 11 && lastWaveY >= flowPlotTop && lastWaveY <= flowPlotBot;
                                const nearAuto = tk.y > p3Bot - 19;
                                return (
                                    <g key={`tv-f-tick-${fIdx}`}>
                                        <line
                                            x1={padL}
                                            y1={tk.y}
                                            x2={padL + plotW}
                                            y2={tk.y}
                                            stroke={isZeroTick ? "#243444" : "#131d27"}
                                            strokeWidth={isZeroTick ? "1.1" : "0.8"}
                                            strokeDasharray={isZeroTick ? "3,3" : "none"}
                                        />
                                        {!nearCur && !nearAuto && (
                                            <text
                                                x={padL + plotW + 6}
                                                y={tk.y + 3}
                                                fill={isZeroTick ? "#8ca5b8" : "#51687c"}
                                                fontSize="7.8"
                                                fontWeight={isZeroTick ? "bold" : "normal"}
                                                fontFamily="monospace"
                                            >
                                                {isZeroTick ? "ZERO" : fmtW(tk.val)}
                                            </text>
                                        )}
                                    </g>
                                );
                            })}

                            {/* Garante Linha ZERO tracejada caso 0 esteja visível mas não tenha caído num múltiplo exato */}
                            {yZeroWave >= flowPlotTop && yZeroWave <= flowPlotBot && !flowAxisTicks.some(t => Math.abs(t.val) < 1e-3) && (
                                <g>
                                    <line x1={padL} y1={yZeroWave} x2={padL + plotW} y2={yZeroWave} stroke="#243444" strokeWidth="1.1" strokeDasharray="3,3" />
                                    {Math.abs(yZeroWave - lastWaveY) >= 11 && (
                                        <text x={padL + plotW + 6} y={yZeroWave + 3} fill="#8ca5b8" fontSize="7.8" fontWeight="bold" fontFamily="monospace">
                                            ZERO
                                        </text>
                                    )}
                                </g>
                            )}

                            <g clipPath={`url(#clip-p3-band-${symKey})`}>
                                {/* Linha Azul Limpa do Fluxo Smart Money (Escala Variável) */}
                                <polyline
                                    fill="none"
                                    stroke="#00d4ff"
                                    strokeWidth="2.15"
                                    strokeLinejoin="round"
                                    strokeLinecap="round"
                                    points={wavePts}
                                    opacity="0.96"
                                />

                                {/* Linhas de Divergência Sincronizadas na Onda de Fluxo (F1 ➔ F2 ↗ e T1 ➔ T2 ↘) */}
                                {swingDivergences.map((dv, dIdx) => {
                                    const isBull = dv.type === "BULL_DIV";
                                    const x1 = toX(dv.prevIdx);
                                    const x2 = toX(dv.currIdx);
                                    const y1 = toYSwingWave(dv.prevWave);
                                    const y2 = toYSwingWave(dv.currWave);
                                    const col = dv.isPendingTrigger ? "#ffd600" : (isBull ? "#00e87a" : "#ff3860");
                                    const midX = (x1 + x2) / 2;
                                    const midY = (y1 + y2) / 2;
                                    const lbl = isBull
                                        ? `F1➔F2 ↗ (${fmtW(dv.currWave)})`
                                        : `T1➔T2 ↘ (${fmtW(dv.currWave)})`;

                                    return (
                                        <g key={`p2-swing-div-${dIdx}`}>
                                            <line
                                                x1={x2}
                                                y1={p3Top + 15}
                                                x2={x2}
                                                y2={y2}
                                                stroke={col}
                                                strokeWidth="0.85"
                                                strokeDasharray="2,3"
                                                opacity="0.50"
                                            />
                                            <line
                                                x1={x1}
                                                y1={y1}
                                                x2={x2}
                                                y2={y2}
                                                stroke="#05080d"
                                                strokeWidth="3.4"
                                                opacity="0.85"
                                            />
                                            <line
                                                x1={x1}
                                                y1={y1}
                                                x2={x2}
                                                y2={y2}
                                                stroke={col}
                                                strokeWidth="2.2"
                                            />
                                            <circle cx={x1} cy={y1} r="2.8" fill="#05080d" stroke={col} strokeWidth="1.5" />
                                            <circle cx={x2} cy={y2} r="3.5" fill={col} stroke="#05080d" strokeWidth="1.1" />
                                            <text
                                                x={midX}
                                                y={isBull ? Math.min(p3Bot - 4, midY + 11) : Math.max(p3Top + 24, midY - 5)}
                                                fill={col}
                                                fontSize="7.2"
                                                fontWeight="bold"
                                                fontFamily="monospace"
                                                textAnchor="middle"
                                            >
                                                {lbl}
                                            </text>
                                        </g>
                                    );
                                })}

                                {/* Badge estilo TradingView do Valor Atual da Onda na Escala Direita */}
                                {(() => {
                                    const clampedTagY = Math.max(flowPlotTop + 7, Math.min(flowPlotBot - 7, lastWaveY));
                                    return (
                                        <g>
                                            <line x1={lastX} y1={clampedTagY} x2={padL + plotW} y2={clampedTagY} stroke="#00d4ff" strokeWidth="0.85" strokeDasharray="2,3" opacity="0.65" />
                                            <rect x={padL + plotW + 2} y={clampedTagY - 7.5} width={padR - 26} height={15} rx="2.5" fill="rgba(0, 212, 255, 0.16)" stroke="#00d4ff" strokeWidth="0.9" />
                                            <text x={padL + plotW + 6} y={clampedTagY + 3} fill="#00d4ff" fontSize="8.2" fontWeight="bold" fontFamily="monospace">
                                                {fmtW(lastSb.smartSwingWave)}
                                            </text>
                                        </g>
                                    );
                                })()}
                            </g>

                            {/* Botão 'A' (Auto Escala) estilo TradingView no canto inferior direito do Eixo do Fluxo */}
                            <g
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    if (isFAuto) {
                                        setFlowAutoScale(false);
                                    } else {
                                        setFlowAutoScale(true);
                                        setFlowYZoom(1.0);
                                        setFlowYOffset(0);
                                    }
                                }}
                                style={{ cursor: "pointer" }}
                            >
                                <title>{isFAuto ? "Escala de Fluxo Smart Money Automática ligada (clique para modo livre 2D ou arraste a escala Y)" : "Clique para voltar a escala do Fluxo Smart Money ao modo Automático (A)"}</title>
                                <rect
                                    x={width - 21}
                                    y={p3Bot - 16}
                                    width={16}
                                    height={13}
                                    rx="2.5"
                                    fill={isFAuto ? "rgba(0, 212, 255, 0.22)" : "#0c1218"}
                                    stroke={isFAuto ? "#00d4ff" : "#334155"}
                                    strokeWidth="0.9"
                                />
                                <text
                                    x={width - 13}
                                    y={p3Bot - 6.8}
                                    fill={isFAuto ? "#00d4ff" : "#7f96a8"}
                                    fontSize="8"
                                    fontWeight="bold"
                                    fontFamily="monospace"
                                    textAnchor="middle"
                                >
                                    A
                                </text>
                            </g>
                        </g>
                    );
                })()}

                {/* MODO 1: CABO DE GUERRA (NÃO-VAREJO: INST AGRESSOR + INST PASSIVO vs VAREJO + DIAMANTES DE DIVERGÊNCIA) */}
                {flowSubMode === "CABO_GUERRA" && (
                    <g>
                        <line x1={padL} y1={yZero3} x2={padL + plotW} y2={yZero3} stroke="#243444" strokeWidth="1.0" />
                        <text x={padL + plotW + 5} y={yZero3 + 3} fill="#6b8599" fontSize="8" fontWeight="bold" fontFamily="monospace">
                            ZERO
                        </text>
                        <text x={padL + plotW + 5} y={p3Top + 25} fill="#00e87a" fontSize="7.5" fontFamily="monospace">
                            +{fmtNum(maxCaboVal, 0)}L
                        </text>
                        <text x={padL + plotW + 5} y={p3Bot - 5} fill="#ff3860" fontSize="7.5" fontFamily="monospace">
                            -{fmtNum(maxCaboVal, 0)}L
                        </text>

                        {subPanelBars.map((sb) => {
                            const x = toX(sb.idx);
                            const ia = sb.ia5;
                            const ip = sb.ip5;
                            const ret = sb.r5;

                            // Empilhamento positivo e negativo do Não-Varejo (Agressor + Passivo)
                            let posCursor = yZero3;
                            let negCursor = yZero3;

                            const iaH = Math.abs(yZero3 - toYCabo(Math.abs(ia)));
                            const ipH = Math.abs(yZero3 - toYCabo(Math.abs(ip)));
                            const retH = Math.abs(yZero3 - toYCabo(Math.abs(ret)));

                            let iaY = yZero3;
                            if (ia >= 0) {
                                iaY = posCursor - iaH;
                                posCursor = iaY;
                            } else {
                                iaY = negCursor;
                                negCursor += iaH;
                            }

                            let ipY = yZero3;
                            if (ip >= 0) {
                                ipY = posCursor - ipH;
                                posCursor = ipY;
                            } else {
                                ipY = negCursor;
                                negCursor += ipH;
                            }

                            const retY = ret >= 0 ? yZero3 - retH : yZero3;
                            const isBullDiv = sb.divType === "BULL_DIV" || sb.divType === "TRAP_FOMO_SELL" || sb.divType === "SWEEP_BUY";
                            const isBearDiv = sb.divType === "BEAR_DIV" || sb.divType === "TRAP_FOMO_BUY" || sb.divType === "SWEEP_SELL";
                            const markerY = isBullDiv
                                ? Math.max(p3Top + 21, posCursor - 5)
                                : Math.min(p3Bot - 4, negCursor + 5);

                            return (
                                <g key={`cabo-${sb.idx}`}>
                                    <title>{`${series[sb.idx]?.time} | 🏦 Inst Agressor: ${fmtNum(ia, 0, true)}L | 🛡️ Inst Passivo (Pedra): ${fmtNum(ip, 0, true)}L | 🧑‍💻 Varejo: ${fmtNum(ret, 0, true)}L | ${sb.divLabel}`}</title>
                                    {/* Camada 1: Agressão Institucional (Verde / Vermelho) */}
                                    {iaH >= 0.8 && (
                                        <rect
                                            x={x - candleW * 0.48}
                                            y={iaY}
                                            width={candleW * 0.96}
                                            height={Math.max(1.2, iaH)}
                                            fill={ia >= 0 ? "#00e87a" : "#ff3860"}
                                            opacity="0.88"
                                            rx="0.5"
                                        />
                                    )}
                                    {/* Camada 2: Absorção Passiva Institucional na Pedra (Ciano Compra / Âmbar Venda) */}
                                    {ipH >= 0.8 && (
                                        <rect
                                            x={x - candleW * 0.48}
                                            y={ipY}
                                            width={candleW * 0.96}
                                            height={Math.max(1.2, ipH)}
                                            fill={ip >= 0 ? "#00d4ff" : "#f59e0b"}
                                            opacity="0.92"
                                            rx="0.5"
                                        />
                                    )}
                                    {/* Camada 3: Barra Fina Central do Varejo (Roxo Claro / Azul) para enxergar o Cabo de Guerra */}
                                    {retH >= 0.8 && (
                                        <rect
                                            x={x - candleW * 0.16}
                                            y={retY}
                                            width={Math.max(1.5, candleW * 0.32)}
                                            height={Math.max(1.2, retH)}
                                            fill={ret >= 0 ? "#e879f9" : "#a855f7"}
                                            opacity="0.95"
                                        />
                                    )}
                                    {/* Diamante de Divergência */}
                                    {(isBullDiv || isBearDiv) && (
                                        <polygon
                                            points={`${x},${markerY - 3.2} ${x + 3.0},${markerY} ${x},${markerY + 3.2} ${x - 3.0},${markerY}`}
                                            fill={sb.divColor}
                                            stroke="#05080d"
                                            strokeWidth="0.7"
                                        />
                                    )}
                                </g>
                            );
                        })}
                    </g>
                )}

                {/* MODO 2: OSCILADOR DE DIVERGÊNCIA (PREÇO vs FLUXO NÃO-VAREJO EM 5m VELA ATUAL / 10m / 15m + ÁREAS SOMBREADAS) */}
                {flowSubMode === "OSC_DIVERGENCIA" && (() => {
                    const pricePts = subPanelBars.map((sb) => `${toX(sb.idx).toFixed(1)},${toYOscP(sb.dpOsc).toFixed(1)}`).join(" ");
                    const nrPts = subPanelBars.map((sb) => `${toX(sb.idx).toFixed(1)},${toYOscNr(sb.nrOsc).toFixed(1)}`).join(" ");
                    const retPts = subPanelBars.map((sb) => `${toX(sb.idx).toFixed(1)},${toYOscNr(sb.rOsc).toFixed(1)}`).join(" ");
                    const lastSb = subPanelBars[subPanelBars.length - 1] || {};

                    return (
                        <g>
                            <line x1={padL} y1={yZero3} x2={padL + plotW} y2={yZero3} stroke="#243444" strokeWidth="1.0" strokeDasharray="3,3" />
                            <text x={padL + plotW + 5} y={yZero3 + 3} fill="#6b8599" fontSize="8" fontFamily="monospace">
                                ZERO
                            </text>

                            {/* Polígonos Sombreados entre Preço e Não-Varejo quando estão em lados opostos (Divergência Pura) */}
                            {subPanelBars.map((sb, i) => {
                                if (i === 0) return null;
                                const prev = subPanelBars[i - 1];
                                const x1 = toX(i - 1);
                                const x2 = toX(i);
                                const yp1 = toYOscP(prev.dpOsc);
                                const yp2 = toYOscP(sb.dpOsc);
                                const yn1 = toYOscNr(prev.nrOsc);
                                const yn2 = toYOscNr(sb.nrOsc);

                                const bullDivSeg = (sb.dpOsc <= 0 && sb.nrOsc > 0) || (prev.dpOsc <= 0 && prev.nrOsc > 0);
                                const bearDivSeg = (sb.dpOsc >= 0 && sb.nrOsc < 0) || (prev.dpOsc >= 0 && prev.nrOsc < 0);
                                if (!bullDivSeg && !bearDivSeg) return null;

                                return (
                                    <polygon
                                        key={`osc-poly-${i}`}
                                        points={`${x1.toFixed(1)},${yp1.toFixed(1)} ${x2.toFixed(1)},${yp2.toFixed(1)} ${x2.toFixed(1)},${yn2.toFixed(1)} ${x1.toFixed(1)},${yn1.toFixed(1)}`}
                                        fill={bullDivSeg ? "rgba(0, 232, 122, 0.25)" : "rgba(255, 56, 96, 0.25)"}
                                    />
                                );
                            })}

                            {/* Curva Varejo (Roxo Pontilhado) */}
                            <polyline fill="none" stroke="#a78bfa" strokeWidth="1.15" strokeDasharray="2,2" opacity="0.75" points={retPts} />
                            {/* Curva Preço (Branco Tracejado) */}
                            <polyline fill="none" stroke="#e2e8f0" strokeWidth="1.5" strokeDasharray="4,3" opacity="0.92" points={pricePts} />
                            {/* Curva Fluxo Não-Varejo (Verde Esmeralda Sólida) */}
                            <polyline fill="none" stroke="#00e87a" strokeWidth="2.2" points={nrPts} />

                            {/* Etiquetas na escala direita */}
                            <text x={padL + plotW + 5} y={Math.max(p3Top + 22, Math.min(p3Bot - 6, toYOscNr(lastSb.nrOsc || 0)))} fill="#00e87a" fontSize="8" fontWeight="bold" fontFamily="monospace">
                                NR:{fmtNum(lastSb.nrOsc, 0, true)}
                            </text>
                            <text x={padL + plotW + 5} y={Math.max(p3Top + 22, Math.min(p3Bot - 6, toYOscP(lastSb.dpOsc || 0)))} fill="#e2e8f0" fontSize="8" fontFamily="monospace">
                                ΔP:{fmtNum(lastSb.dpOsc, dec, true)}
                            </text>
                        </g>
                    );
                })()}

                {/* MODO 3: CVD ACUMULADO 4-PLAYERS EM LOTES (INST AGRESSOR, INST PASSIVO, VAREJO, HFT, RLP) */}
                {flowSubMode === "CVD_4PLAYERS" && (() => {
                    const yZ = toYCvd4(0);
                    const ptsIa = subPanelBars.map((sb) => `${toX(sb.idx).toFixed(1)},${toYCvd4(sb.cvdIa).toFixed(1)}`).join(" ");
                    const ptsIp = subPanelBars.map((sb) => `${toX(sb.idx).toFixed(1)},${toYCvd4(sb.cvdIp).toFixed(1)}`).join(" ");
                    const ptsRet = subPanelBars.map((sb) => `${toX(sb.idx).toFixed(1)},${toYCvd4(sb.cvdRet).toFixed(1)}`).join(" ");
                    const ptsHft = subPanelBars.map((sb) => `${toX(sb.idx).toFixed(1)},${toYCvd4(sb.cvdHft).toFixed(1)}`).join(" ");
                    const ptsRlp = subPanelBars.map((sb) => `${toX(sb.idx).toFixed(1)},${toYCvd4(sb.cvdRlp).toFixed(1)}`).join(" ");
                    const lastSb = subPanelBars[subPanelBars.length - 1] || {};
                    const fmtK = (v) => {
                        const av = Math.abs(Number(v || 0));
                        const sg = Number(v || 0) >= 0 ? "+" : "-";
                        return av >= 1000 ? `${sg}${(av / 1000).toFixed(1)}k` : `${sg}${Math.round(av)}`;
                    };

                    return (
                        <g>
                            {yZ >= p3Top + 14 && yZ <= p3Bot && (
                                <line x1={padL} y1={yZ} x2={padL + plotW} y2={yZ} stroke="#243444" strokeWidth="1" strokeDasharray="3,3" />
                            )}
                            <polyline fill="none" stroke="#eab308" strokeWidth="1.25" strokeDasharray="2,2" opacity="0.85" points={ptsRlp} />
                            <polyline fill="none" stroke="#a78bfa" strokeWidth="1.35" strokeDasharray="3,2" opacity="0.88" points={ptsHft} />
                            <polyline fill="none" stroke="#f59e0b" strokeWidth="1.45" strokeDasharray="4,2" opacity="0.90" points={ptsRet} />
                            <polyline fill="none" stroke="#00d4ff" strokeWidth="1.85" points={ptsIp} />
                            <polyline fill="none" stroke="#00e87a" strokeWidth="2.15" points={ptsIa} />

                            <text x={padL + plotW + 4} y={p3Top + 25} fill="#00e87a" fontSize="7.5" fontWeight="bold" fontFamily="monospace">
                                🏦Agr {fmtK(lastSb.cvdIa)}
                            </text>
                            <text x={padL + plotW + 4} y={p3Top + 39} fill="#00d4ff" fontSize="7.5" fontWeight="bold" fontFamily="monospace">
                                🛡️Pas {fmtK(lastSb.cvdIp)}
                            </text>
                            <text x={padL + plotW + 4} y={p3Top + 53} fill="#f59e0b" fontSize="7.5" fontFamily="monospace">
                                🧑‍💻Var {fmtK(lastSb.cvdRet)}
                            </text>
                            <text x={padL + plotW + 4} y={p3Top + 67} fill="#a78bfa" fontSize="7.5" fontFamily="monospace">
                                ⚡HFT {fmtK(lastSb.cvdHft)}
                            </text>
                            <text x={padL + plotW + 4} y={p3Top + 81} fill="#eab308" fontSize="7.5" fontFamily="monospace">
                                🔄RLP {fmtK(lastSb.cvdRlp)}
                            </text>
                        </g>
                    );
                })()}

                {/* MODO 4: JANELA DE FLUXO SMART MONEY (HISTOGRAMA + LINHA DE LOTES DA 5176 UNIFICADOS NA MESMA ESCALA E LINHA ZERO) */}
                {flowSubMode === "JANELA_ASG" && (() => {
                    const showHistBars = smWinVisualMode === "HIST_LINE" || smWinVisualMode === "HIST";
                    const showLineWave = smWinVisualMode === "HIST_LINE" || smWinVisualMode === "LINE";
                    const wavePts = subPanelBars.map((sb) => `${toX(sb.idx).toFixed(1)},${toYSwingWave(sb.smartSwingWave).toFixed(1)}`).join(" ");
                    const lastSb = subPanelBars[subPanelBars.length - 1] || {};
                    const lastWaveY = toYSwingWave(lastSb.smartSwingWave || 0);
                    const yZeroClamped = Math.max(flowPlotTop, Math.min(flowPlotBot, yZeroWave));
                    const isFAuto = flowAutoScale && flowYZoom === 1.0 && flowYOffset === 0;
                    const fmtW = (v) => {
                        const num = Number(v || 0);
                        if (Math.abs(num) < 0.5) return "0";
                        const av = Math.abs(num);
                        const sg = num > 0 ? "+" : "-";
                        return av >= 1000 ? `${sg}${(av / 1000).toFixed(1)}k` : `${sg}${Math.round(av)}`;
                    };

                    return (
                        <g>
                            {/* Grade e Marcações Dinâmicas da Escala Variável em Contratos/Lotes (mesma escala da 5176 para Histograma e Linha) */}
                            {flowAxisTicks.map((tk, fIdx) => {
                                const isZeroTick = Math.abs(tk.val) < 1e-3;
                                const nearCur = Math.abs(tk.y - lastWaveY) < 11 && lastWaveY >= flowPlotTop && lastWaveY <= flowPlotBot;
                                const nearAuto = tk.y > p3Bot - 19;
                                return (
                                    <g key={`tv-sm-tick-${fIdx}`}>
                                        <line
                                            x1={padL}
                                            y1={tk.y}
                                            x2={padL + plotW}
                                            y2={tk.y}
                                            stroke={isZeroTick ? "#243444" : "#131d27"}
                                            strokeWidth={isZeroTick ? "1.1" : "0.8"}
                                            strokeDasharray={isZeroTick ? "3,3" : "none"}
                                        />
                                        {!nearCur && !nearAuto && (
                                            <text
                                                x={padL + plotW + 6}
                                                y={tk.y + 3}
                                                fill={isZeroTick ? "#8ca5b8" : "#51687c"}
                                                fontSize="7.8"
                                                fontWeight={isZeroTick ? "bold" : "normal"}
                                                fontFamily="monospace"
                                            >
                                                {isZeroTick ? "ZERO" : fmtW(tk.val)}
                                            </text>
                                        )}
                                    </g>
                                );
                            })}
                            {yZeroWave >= flowPlotTop && yZeroWave <= flowPlotBot && !flowAxisTicks.some(t => Math.abs(t.val) < 1e-3) && (
                                <g>
                                    <line x1={padL} y1={yZeroWave} x2={padL + plotW} y2={yZeroWave} stroke="#243444" strokeWidth="1.1" strokeDasharray="3,3" />
                                    {Math.abs(yZeroWave - lastWaveY) >= 11 && (
                                        <text x={padL + plotW + 6} y={yZeroWave + 3} fill="#8ca5b8" fontSize="7.8" fontWeight="bold" fontFamily="monospace">
                                            ZERO
                                        </text>
                                    )}
                                </g>
                            )}

                            <g clipPath={`url(#clip-p3-band-${symKey})`}>
                                {/* Camada 1: Histograma da Onda de Fluxo Smart Money em Contratos/Lotes (100% sincronizado com a Linha Azul e com o ZERO dinâmico) */}
                                {showHistBars && subPanelBars.map((sb, idx) => {
                                    const x = toX(idx);
                                    const wv = Number(sb.smartSwingWave || 0);
                                    const yH = toYSwingWave(wv);
                                    const isPos = wv >= 0;
                                    const col = isPos ? "#00e87a" : "#ff3860";
                                    const barTop = Math.min(yH, yZeroClamped);
                                    const barH = Math.max(1.2, Math.abs(yZeroClamped - yH));

                                    return (
                                        <rect
                                            key={`h-bar-${idx}`}
                                            x={x - candleW / 2}
                                            y={barTop}
                                            width={candleW}
                                            height={barH}
                                            fill={col}
                                            opacity={showLineWave ? "0.38" : "0.88"}
                                            rx="0.5"
                                        />
                                    );
                                })}

                                {/* Camada 2: Mesma Linha Azul de Fluxo Smart Money em Contratos/Lotes da 5176 (`smartSwingWave`) */}
                                {showLineWave && subPanelBars.length >= 2 && (
                                    <g>
                                        {smWinVisualMode === "HIST_LINE" && (
                                            <polyline
                                                fill="none"
                                                stroke="#060a0f"
                                                strokeWidth="3.4"
                                                strokeLinejoin="round"
                                                strokeLinecap="round"
                                                points={wavePts}
                                                opacity="0.80"
                                            />
                                        )}
                                        <polyline
                                            fill="none"
                                            stroke="#00d4ff"
                                            strokeWidth="2.15"
                                            strokeLinejoin="round"
                                            strokeLinecap="round"
                                            points={wavePts}
                                            opacity="0.96"
                                        />
                                    </g>
                                )}

                                {/* Badge estilo TradingView do Valor Atual em Contratos/Lotes na Escala Direita (idêntico à 5176) */}
                                {subPanelBars.length > 0 && (() => {
                                    const clampedTagY = Math.max(flowPlotTop + 7, Math.min(flowPlotBot - 7, lastWaveY));
                                    return (
                                        <g>
                                            <line x1={lastX} y1={clampedTagY} x2={padL + plotW} y2={clampedTagY} stroke="#00d4ff" strokeWidth="0.85" strokeDasharray="2,3" opacity="0.65" />
                                            <rect x={padL + plotW + 2} y={clampedTagY - 7.5} width={padR - 26} height={15} rx="2.5" fill="rgba(0, 212, 255, 0.16)" stroke="#00d4ff" strokeWidth="0.9" />
                                            <text x={padL + plotW + 6} y={clampedTagY + 3} fill="#00d4ff" fontSize="8.2" fontWeight="bold" fontFamily="monospace">
                                                {fmtW(lastSb.smartSwingWave)}
                                            </text>
                                        </g>
                                    );
                                })()}
                            </g>

                            {/* Botão 'A' (Auto Escala) estilo TradingView no canto inferior direito do Eixo do Fluxo */}
                            <g
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    if (isFAuto) {
                                        setFlowAutoScale(false);
                                    } else {
                                        setFlowAutoScale(true);
                                        setFlowYZoom(1.0);
                                        setFlowYOffset(0);
                                    }
                                }}
                                style={{ cursor: "pointer" }}
                            >
                                <title>{isFAuto ? "Escala de Fluxo Smart Money Automática ligada (clique para modo livre 2D ou arraste a escala Y)" : "Clique para voltar a escala do Fluxo Smart Money ao modo Automático (A)"}</title>
                                <rect
                                    x={width - 21}
                                    y={p3Bot - 16}
                                    width={16}
                                    height={13}
                                    rx="2.5"
                                    fill={isFAuto ? "rgba(0, 212, 255, 0.22)" : "#0c1218"}
                                    stroke={isFAuto ? "#00d4ff" : "#334155"}
                                    strokeWidth="0.9"
                                />
                                <text
                                    x={width - 13}
                                    y={p3Bot - 6.8}
                                    fill={isFAuto ? "#00d4ff" : "#7f96a8"}
                                    fontSize="8"
                                    fontWeight="bold"
                                    fontFamily="monospace"
                                    textAnchor="middle"
                                >
                                    A
                                </text>
                            </g>
                        </g>
                    );
                })()}

                {/* Eixo de Tempo no Rodapé Unificado com o Dashboard */}
                {timeTicks.map((tIdx) => (
                    <text
                        key={`t-${tIdx}`}
                        x={toX(tIdx)}
                        y={height - 7}
                        textAnchor="middle"
                        fill="#7f96a8"
                        fontSize="9.5"
                        fontFamily="monospace"
                    >
                        {series[tIdx]?.is_prev_day ? `Ont ${series[tIdx]?.time}` : series[tIdx]?.time}
                    </text>
                ))}

                {/* ── CROSSHAIR INTERATIVO DUPLO DOURADO (#c8a444 IGUAL AO INDEXCHART/ZSCORECHART) ── */}
                {hoverPos && series[hoverPos.idx] && (
                    <g>
                        {/* Linha Vertical do Crosshair */}
                        <line
                            x1={toX(hoverPos.idx)}
                            y1={p1Top}
                            x2={toX(hoverPos.idx)}
                            y2={p3Bot}
                            stroke="#c8a444"
                            strokeWidth="1"
                            strokeDasharray="4,4"
                            strokeOpacity="0.85"
                        />
                        {/* Badge de Hora no Eixo X Inferior */}
                        <rect
                            x={toX(hoverPos.idx) - 28}
                            y={p3Bot + 2}
                            width={56}
                            height={18}
                            rx="3"
                            fill="#1b1810"
                            stroke="#c8a444"
                            strokeWidth="0.9"
                        />
                        <text
                            x={toX(hoverPos.idx)}
                            y={p3Bot + 14}
                            textAnchor="middle"
                            fill="#f5d061"
                            fontSize="9"
                            fontWeight="bold"
                            fontFamily="monospace"
                        >
                            {series[hoverPos.idx]?.time}
                        </text>

                        {/* Linha Horizontal do Crosshair + Badge de Valor no Eixo Y Direito (Preço ou Fluxo Smart Money) */}
                        {hoverPos.relY >= p1Top && hoverPos.relY <= p1Bot && (
                            <>
                                <line
                                    x1={padL}
                                    y1={hoverPos.relY}
                                    x2={padL + plotW}
                                    y2={hoverPos.relY}
                                    stroke="#c8a444"
                                    strokeWidth="1"
                                    strokeDasharray="4,4"
                                    strokeOpacity="0.85"
                                />
                                <rect
                                    x={padL + plotW + 2}
                                    y={hoverPos.relY - 9}
                                    width={padR - 26}
                                    height={18}
                                    rx="3"
                                    fill="#1b1810"
                                    stroke="#c8a444"
                                    strokeWidth="0.9"
                                />
                                <text
                                    x={padL + plotW + 7}
                                    y={hoverPos.relY + 3.5}
                                    fill="#f5d061"
                                    fontSize="9.5"
                                    fontWeight="bold"
                                    fontFamily="monospace"
                                >
                                    {fmtNum(fromY1(hoverPos.relY), dec)}
                                </text>
                            </>
                        )}
                        {(flowSubMode === "SWING_DIVERGENCIA" || (flowSubMode === "JANELA_ASG" && smWinVisualMode !== "HIST")) && hoverPos.relY >= flowPlotTop && hoverPos.relY <= flowPlotBot && (() => {
                            const wVal = fromYSwingWave(hoverPos.relY);
                            const absW = Math.abs(wVal);
                            const sgW = wVal >= 0 ? "+" : "-";
                            const crossLbl = absW >= 1000 ? `${sgW}${(absW / 1000).toFixed(1)}k` : `${sgW}${Math.round(absW)}`;
                            return (
                                <>
                                    <line
                                        x1={padL}
                                        y1={hoverPos.relY}
                                        x2={padL + plotW}
                                        y2={hoverPos.relY}
                                        stroke="#c8a444"
                                        strokeWidth="1"
                                        strokeDasharray="4,4"
                                        strokeOpacity="0.85"
                                    />
                                    <rect
                                        x={padL + plotW + 2}
                                        y={hoverPos.relY - 9}
                                        width={padR - 26}
                                        height={18}
                                        rx="3"
                                        fill="#1b1810"
                                        stroke="#c8a444"
                                        strokeWidth="0.9"
                                    />
                                    <text
                                        x={padL + plotW + 7}
                                        y={hoverPos.relY + 3.5}
                                        fill="#f5d061"
                                        fontSize="9"
                                        fontWeight="bold"
                                        fontFamily="monospace"
                                    >
                                        {crossLbl}
                                    </text>
                                </>
                            );
                        })()}
                    </g>
                )}
            </svg>
        </div>
    );
}

/* ══════════════════════════════════════════════════════════════════════════════
   2. BARRA COMPACTA DE RESUMO DO DIA (SEM REDUNDÂNCIAS DE VELA 3D / ALVOS 1-2-3)
   ══════════════════════════════════════════════════════════════════════════════ */
function AsgCockpitHud({ symKey, payload, asgHud = {}, scorecard = {}, onToggleHistory, showHistory, onCollapseDrawer }) {
    const winDir = Number(asgHud.window_dir || 0);
    const makersPct = Number(asgHud.makers_pct || 0);
    const winCol = winDir >= 0 ? "#00e87a" : "#ff3860";
    const isWallsHost = isWallsFlowLocalhost();
    const dec = symKey === "WDO" ? 1 : 0;
    const tot = payload?.session_totals || {};
    const radar = payload?.walls_radar || {};
    const sup0 = radar.support_walls?.[0] || null;
    const res0 = radar.resistance_walls?.[0] || null;
    const series = payload?.caminho_a?.m5_dealer_vs_flow_series || [];
    const lastBar = series.length > 0 ? series[series.length - 1] : {};
    const sessInstAggr = Number(tot.inst_aggr_delta ?? lastBar.cvd_inst_aggr ?? tot.inst_delta ?? 0);
    const sessInstPass = Number(tot.inst_pass_delta ?? lastBar.cvd_inst_pass ?? 0);
    const sessRetDelta = Number(tot.retail_delta ?? lastBar.cvd_retail ?? 0);
    const sessHftDelta = Number(tot.hft_delta ?? lastBar.cvd_hft ?? 0);
    const sessHftChurn = Number(tot.hft_churn_pct ?? lastBar.hft_churn_pct ?? 0);
    const sessRlpPct = Number(tot.rlp_pct ?? lastBar.rlp_pct ?? 0);
    const sessRlpDelta = Number(tot.rlp_delta ?? lastBar.cvd_rlp_delta ?? Math.round(-sessRetDelta * (sessRlpPct / 100.0)));

    return (
        <div style={{
            display: "flex",
            flexDirection: "column",
            gap: 8,
            background: "#0c1218",
            border: "1px solid #1a2530",
            borderRadius: 10,
            padding: "10px 14px",
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{
                        fontSize: 9.5,
                        fontWeight: "bold",
                        color: winCol,
                        background: "#0c1218",
                        padding: "3px 8px",
                        borderRadius: 4,
                        border: `1px solid ${winCol}55`,
                        fontFamily: "monospace",
                    }}>
                        {winDir >= 0 ? "🟢 JANELA COMPRADA" : "🔴 JANELA VENDIDA"} · desde {asgHud.window_start_time || "09:00"}
                    </span>
                    <span style={{
                        fontSize: 9.5,
                        fontWeight: "bold",
                        color: makersPct >= 0 ? "#00e87a" : "#ff3860",
                        fontFamily: "monospace",
                    }}>
                        Makers GEX: {makersPct >= 0 ? "+" : ""}{fmtNum(makersPct, 1)}%
                    </span>
                    {isWallsHost && (
                        <span style={{
                            fontSize: 8.5,
                            fontFamily: "monospace",
                            color: "#00d4ff",
                            background: "rgba(0, 212, 255, 0.08)",
                            border: "1px solid rgba(0, 212, 255, 0.35)",
                            padding: "2px 6px",
                            borderRadius: 4,
                        }}>
                            🔬 Profit 4-Players
                        </span>
                    )}
                </div>
                {onCollapseDrawer && (
                    <button
                        onClick={onCollapseDrawer}
                        title="Recuar painel lateral para ampliar o gráfico de Preço + Fluxo Smart Money"
                        style={{
                            padding: "3px 8px",
                            fontSize: 8.5,
                            fontFamily: "monospace",
                            fontWeight: "bold",
                            background: "rgba(0, 212, 255, 0.08)",
                            border: "1px solid rgba(0, 212, 255, 0.38)",
                            color: "#00d4ff",
                            borderRadius: 4,
                            cursor: "pointer",
                        }}
                    >
                        Recuar Lateral ▶
                    </button>
                )}
            </div>

            {isWallsHost && (
                <div style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    background: "#080d12",
                    border: "1px solid #162433",
                    borderRadius: 7,
                    padding: "7px 9px",
                    fontFamily: "monospace",
                }}>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 5, fontSize: 8.5 }}>
                        <div style={{ background: "#0c1218", padding: "4px 6px", borderRadius: 4, border: "1px solid #16222d" }}>
                            <div style={{ color: "#6b8599", fontSize: 7.5 }}>🏦 INST (AGR / PAS)</div>
                            <div style={{ fontWeight: "bold", color: sessInstAggr >= 0 ? "#00e87a" : "#ff6b8b" }}>
                                {fmtNum(sessInstAggr, 0, true)}L <span style={{ color: sessInstPass >= 0 ? "#38ef94" : "#fb7185", fontSize: 8 }}>/ {fmtNum(sessInstPass, 0, true)}L</span>
                            </div>
                        </div>
                        <div style={{ background: "#0c1218", padding: "4px 6px", borderRadius: 4, border: "1px solid #16222d" }}>
                            <div style={{ color: "#6b8599", fontSize: 7.5 }}>🧑‍💻 VAREJO PURO</div>
                            <div style={{ fontWeight: "bold", color: sessRetDelta >= 0 ? "#38bdf8" : "#f59e0b" }}>
                                {fmtNum(sessRetDelta, 0, true)}L
                            </div>
                        </div>
                        <div style={{ background: "#0c1218", padding: "4px 6px", borderRadius: 4, border: "1px solid #16222d" }} title={`Saldo Líquido HFT na Sessão em Lotes | Giro Bruto HFT: ${fmtNum(sessHftChurn, 1)}% do volume`}>
                            <div style={{ color: "#6b8599", fontSize: 7.5 }}>⚡ HFT (SALDO LOTE)</div>
                            <div style={{ fontWeight: "bold", color: sessHftDelta >= 0 ? "#c084fc" : "#a78bfa" }}>
                                {fmtNum(sessHftDelta, 0, true)}L <span style={{ color: "#6b8599", fontSize: 7.2, fontWeight: "normal" }}>({fmtNum(sessHftChurn, 0)}% giro)</span>
                            </div>
                        </div>
                        <div style={{ background: "#0c1218", padding: "4px 6px", borderRadius: 4, border: "1px solid #16222d" }} title={`Saldo Líquido Provedor RLP contra Varejo em Lotes | Participação RLP: ${fmtNum(sessRlpPct, 1)}% do volume`}>
                            <div style={{ color: "#6b8599", fontSize: 7.5 }}>🔄 RLP (SALDO LOTE)</div>
                            <div style={{ fontWeight: "bold", color: sessRlpDelta >= 0 ? "#fbbf24" : "#f97316" }}>
                                {fmtNum(sessRlpDelta, 0, true)}L <span style={{ color: "#6b8599", fontSize: 7.2, fontWeight: "normal" }}>({fmtNum(sessRlpPct, 0)}% vol)</span>
                            </div>
                        </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, flexWrap: "wrap", fontSize: 8.3, borderTop: "1px solid #13202c", paddingTop: 5, color: "#9fb4c4" }}>
                        {symKey === "WIN" ? (
                            <>
                                <span>🎯 <strong style={{ color: "#00e87a" }}>WIN 2L Mix:</strong> L1 TP NWE30 Din · L2 TP 750p</span>
                                <span>SL 240p/260p · BE +180p → +20p</span>
                            </>
                        ) : (
                            <>
                                <span>🎯 <strong style={{ color: "#ffd600" }}>WDO 1L MidWalls:</strong> TP MidWall GEX</span>
                                <span>SL ~10p · BE Escudo Wall</span>
                            </>
                        )}
                    </div>
                </div>
            )}

            <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                borderTop: "1px solid #16222d",
                paddingTop: 8,
            }}>
                <div style={{ fontSize: 10, color: "#9fb4c4" }}>
                    🎯 Assertividade Hoje:{" "}
                    <strong style={{ color: "#00e87a" }}>
                        {fmtNum(scorecard.win_rate_pct, 0)}% ({scorecard.valid_signals || 0}✅ / {scorecard.invalid_signals || 0}❌)
                    </strong>
                </div>
                <button
                    onClick={onToggleHistory}
                    style={{
                        padding: "5px 10px",
                        fontSize: 9,
                        fontFamily: "monospace",
                        fontWeight: "bold",
                        background: "#0c1218",
                        border: "1px solid #00d4ff55",
                        color: "#00d4ff",
                        borderRadius: 5,
                        cursor: "pointer",
                    }}
                >
                    {showHistory ? "▲ Ocultar Tabela" : "📋 Ver Sinais do Dia"}
                </button>
            </div>
        </div>
    );
}

/* ══════════════════════════════════════════════════════════════════════════════
   3. GRÁFICO DE CAPITAL DAS OPERAÇÕES DO DIA (CANTO INFERIOR DIREITO)
      - Evolução acumulada em R$ e Pontos dos sinais/operações emitidos na sessão
      - Seletor de lote (1, 5, 10 contratos) + inspeção interativa de cada trade
   ══════════════════════════════════════════════════════════════════════════════ */
function DailyOperationsEquityChart({ symKey, signalsLog = [], scorecard = {}, selectedSigId, onSelectSignal, onCollapseDrawer }) {
    const [contracts, setContracts] = useState(1);
    const [hoverTradeIdx, setHoverTradeIdx] = useState(null);

    const dec = symKey === "WDO" ? 1 : 0;
    // WIN = R$ 0,20 por ponto por contrato | WDO = R$ 10,00 por ponto por contrato
    const brlPerPt = symKey === "WDO" ? 10.0 : 0.20;
    const targetRef = Number(scorecard.target_ref_pts || (symKey === "WDO" ? 10.0 : 250));
    const stopRef = Number(scorecard.stop_ref_pts || (symKey === "WDO" ? 10.0 : 250));
    const useBe = scorecard.use_be_protection !== undefined ? Boolean(scorecard.use_be_protection) : (symKey === "WDO");
    const beTrigger = Number(scorecard.be_trigger_pts || (symKey === "WDO" ? 3.5 : 150));
    const beLock = Number(scorecard.be_lock_pts || (symKey === "WDO" ? 1.0 : 50));
    const timeStopMin = Number(scorecard.time_stop_min || (symKey === "WDO" ? 120 : 40));
    const methodLabel = scorecard.methodology_label || (symKey === "WDO" ? "WDO Pullback + WDO Next Wall + WDO Lunch" : "WIN Rejeição + WIN Rompimento + WIN Next Wall");
    const isWdoHybrid = symKey === "WDO" && (String(methodLabel).toLowerCase().includes("fluxo") || String(methodLabel).includes("Pullback") || String(methodLabel).includes("Lunch") || String(methodLabel).includes("WDO-09") || String(methodLabel).includes("WDO_1"));
    const isWinHybrid = symKey === "WIN" && (String(methodLabel).toLowerCase().includes("fluxo") || String(methodLabel).includes("Rejeição") || String(methodLabel).includes("Price Action") || String(methodLabel).includes("EST-01") || String(methodLabel).includes("WIN_1"));

    // Ordenar sinais em ordem cronológica (09:00 -> atual)
    const chronoSignals = [...signalsLog].reverse();

    let cumPts = 0;
    let peakPts = 0;
    let maxDrawdownPts = 0;
    let peakBrlDay = 0;
    let maxDrawdownBrlDay = 0;
    let grossGainPts = 0;
    let grossLossPts = 0;

    const equityPoints = [
        {
            idx: 0,
            id: null,
            time: "09:00",
            label: "Início",
            tradePts: 0,
            tradeBrl: 0,
            cumPts: 0,
            cumBrl: 0,
            isGain: true,
            dirLabel: "—",
        },
    ];

    chronoSignals.forEach((sig, i) => {
        let tradePts = 0;
        const st = String(sig.validation_status || "");
        if (st === "EM_ANDAMENTO") {
            // Operação aberta (barra fechada confirmada, aguardando Alvo/Stop/30m): não altera capital realizado até encerrar
            tradePts = 0;
        } else if (sig.realized_pts !== undefined && sig.realized_pts !== null) {
            tradePts = Number(sig.realized_pts);
        } else if (st === "VALIDO_ALVO") {
            tradePts = targetRef;
        } else if (st === "INVALIDO_STOP") {
            tradePts = -stopRef;
        } else if (st === "VALIDO_FAVORAVEL") {
            tradePts = Number(sig.pnl_30m ?? sig.pnl_15m ?? Math.round(targetRef * 0.45));
        } else if (st === "INVALIDO_CONTRA") {
            tradePts = Number(sig.pnl_30m ?? sig.pnl_15m ?? -Math.round(stopRef * 0.5));
        }

        if (st !== "EM_ANDAMENTO") {
            if (tradePts >= 0) grossGainPts += tradePts;
            else grossLossPts += Math.abs(tradePts);
        }

        cumPts += tradePts;
        if (cumPts > peakPts) peakPts = cumPts;
        const dd = peakPts - cumPts;
        if (dd > maxDrawdownPts) maxDrawdownPts = dd;

        const tradeBrl = st === "EM_ANDAMENTO"
            ? 0
            : (sig.brl_1c !== undefined && sig.brl_1c !== null
                ? Number(sig.brl_1c) * contracts
                : tradePts * brlPerPt * contracts);
        const prevCumBrl = equityPoints[equityPoints.length - 1]?.cumBrl || 0;
        const cumBrl = prevCumBrl + tradeBrl;
        if (cumBrl > peakBrlDay) peakBrlDay = cumBrl;
        if (peakBrlDay - cumBrl > maxDrawdownBrlDay) maxDrawdownBrlDay = peakBrlDay - cumBrl;

        equityPoints.push({
            idx: i + 1,
            id: sig.id,
            time: sig.time,
            entryPrice: sig.entry_price,
            dirLabel: (sig.dir_num || 0) > 0 ? "▲ COMPRA" : "▼ VENDA",
            tradePts,
            tradeBrl,
            cumPts,
            cumBrl,
            isGain: tradePts >= 0,
            isOpen: st === "EM_ANDAMENTO",
            statusLabel: sig.validation_label || "Em andamento",
        });
    });

    const totalBrl = equityPoints[equityPoints.length - 1]?.cumBrl || 0;
    const isNetPos = totalBrl >= 0;
    const curveColor = isNetPos ? "#00e87a" : "#ff3860";
    const profitFactor = grossLossPts > 0 ? (grossGainPts / grossLossPts) : (grossGainPts > 0 ? 9.9 : 1.0);

    const w = 400;
    const h = 160;
    const padL = 10;
    const padR = 54;
    const padT = 12;
    const padB = 18;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    let minBrl = 0;
    let maxBrl = 0;
    equityPoints.forEach(p => {
        if (p.cumBrl < minBrl) minBrl = p.cumBrl;
        if (p.cumBrl > maxBrl) maxBrl = p.cumBrl;
    });
    const spanBrl = Math.max(50, maxBrl - minBrl);
    minBrl -= spanBrl * 0.12;
    maxBrl += spanBrl * 0.12;
    const rangeBrl = Math.max(1e-6, maxBrl - minBrl);

    const eqInnerPadL = 8;
    const eqRightGap = 34;
    const eqUsableW = Math.max(120, plotW - eqInnerPadL - eqRightGap);
    const toX = (i) => padL + eqInnerPadL + (i / Math.max(1, equityPoints.length - 1)) * eqUsableW;
    const toY = (v) => padT + plotH - ((v - minBrl) / rangeBrl) * plotH;
    const yZero = toY(0);

    const polyPts = equityPoints.map((p, i) => `${toX(i).toFixed(1)},${toY(p.cumBrl).toFixed(1)}`).join(" ");
    const areaPts = `${toX(0).toFixed(1)},${yZero.toFixed(1)} ${polyPts} ${toX(equityPoints.length - 1).toFixed(1)},${yZero.toFixed(1)}`;

    const inspected = hoverTradeIdx !== null && equityPoints[hoverTradeIdx]
        ? equityPoints[hoverTradeIdx]
        : equityPoints[equityPoints.length - 1];

    return (
        <div style={{
            flex: 1,
            background: "#0c1218",
            border: "1px solid #1a2530",
            borderRadius: 10,
            padding: "12px 14px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            gap: 10,
        }}>
            {/* Cabeçalho + Seletor de Contratos */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 10.5, fontWeight: "bold", color: "#ffffff", letterSpacing: 0.8 }}>
                        💰 CAPITAL DAS OPERAÇÕES DO DIA
                    </span>
                    <span style={{
                        fontSize: 7.5,
                        fontFamily: "monospace",
                        color: "#00e87a",
                        background: "#0c1218",
                        border: "1px solid rgba(0, 232, 122, 0.35)",
                        padding: "1px 5px",
                        borderRadius: 4,
                        fontWeight: "bold",
                    }}>
                        🔒 BARRA FECHADA
                    </span>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                    {(isWallsFlowLocalhost()
                        ? [1, 2, 5]
                        : (symKey === "WDO" ? [1, 2, 5] : [1, 5, 10])
                    ).map(c => {
                        const btnLbl = isWallsFlowLocalhost()
                            ? (symKey === "WIN" ? `${c}x (${c * 2}L)` : `${c}x (${c}L)`)
                            : `${c} Contr.`;
                        return (
                            <button
                                key={c}
                                onClick={() => setContracts(c)}
                                style={{
                                    padding: "2px 7px",
                                    fontSize: 8.5,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                    background: contracts === c ? "#00d4ff" : "#0c1218",
                                    color: contracts === c ? "#04080e" : "#8ca5b5",
                                    border: contracts === c ? "1px solid #00d4ff" : "1px solid #1a2530",
                                }}
                            >
                                {btnLbl}
                            </button>
                        );
                    })}
                    {onCollapseDrawer && (
                        <button
                            onClick={onCollapseDrawer}
                            title="Recuar gráfico de capital para ampliar o gráfico de Preço e Fluxo Smart Money"
                            style={{
                                padding: "2px 7px",
                                fontSize: 8.5,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                borderRadius: 4,
                                cursor: "pointer",
                                background: "rgba(0, 212, 255, 0.10)",
                                color: "#00d4ff",
                                border: "1px solid rgba(0, 212, 255, 0.45)",
                                marginLeft: 2,
                            }}
                        >
                            Recuar ▶
                        </button>
                    )}
                </div>
            </div>

            {/* Faixa de KPIs Financeiros do Dia */}
            <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 0.9fr", gap: 6 }}>
                <div style={{ background: "#0c1218", border: `1px solid ${curveColor}44`, borderRadius: 7, padding: "5px 8px" }}>
                    <div style={{ fontSize: 7.5, color: "#7f96a8", fontWeight: "bold" }}>
                        SALDO ACUMULADO ({isWallsFlowLocalhost() ? (symKey === "WIN" ? `${contracts * 2}L` : `${contracts}L`) : `${contracts}c`})
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 900, color: curveColor, fontFamily: "monospace" }}>
                        {totalBrl >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(totalBrl), 0)}
                        <span style={{ fontSize: 9.5, color: "#9fb4c4", fontWeight: "normal", marginLeft: 5 }}>
                            ({fmtNum(cumPts, dec, true)}p)
                        </span>
                    </div>
                </div>
                <div style={{ background: "#0c1218", border: "1px solid #1a2530", borderRadius: 7, padding: "5px 8px" }}>
                    <div style={{ fontSize: 7.5, color: "#7f96a8", fontWeight: "bold" }}>FATOR DE LUCRO</div>
                    <div style={{ fontSize: 13, fontWeight: "bold", color: profitFactor >= 1.5 ? "#00e87a" : "#f5a623", fontFamily: "monospace" }}>
                        {fmtNum(profitFactor, 2)}x
                        <span style={{ fontSize: 8.5, color: "#7f96a8", marginLeft: 4 }}>
                            ({chronoSignals.length} ops)
                        </span>
                    </div>
                </div>
                <div style={{ background: "#0c1218", border: "1px solid #1a2530", borderRadius: 7, padding: "5px 8px" }}>
                    <div style={{ fontSize: 7.5, color: "#7f96a8", fontWeight: "bold" }}>DRAWDOWN MÁX</div>
                    <div style={{ fontSize: 12.5, fontWeight: "bold", color: "#ff6b8b", fontFamily: "monospace" }}>
                        -R$ {fmtNum(maxDrawdownBrlDay, 0)}
                    </div>
                </div>
            </div>

            {/* Gráfico SVG da Curva de Capital Intraday */}
            <svg
                viewBox={`0 0 ${w} ${h}`}
                style={{ width: "100%", height: "auto", display: "block", background: "#0c1218", borderRadius: 7, border: "1px solid #1a2530", cursor: "crosshair" }}
                onMouseLeave={() => setHoverTradeIdx(null)}
            >
                <defs>
                    <linearGradient id={`eq-grad-${symKey}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={curveColor} stopOpacity="0.32" />
                        <stop offset="100%" stopColor={curveColor} stopOpacity="0.02" />
                    </linearGradient>
                </defs>

                {/* Linha Zero (Break-even R$ 0) */}
                <line x1={padL} y1={yZero} x2={padL + plotW} y2={yZero} stroke="#2a3f54" strokeWidth="1" strokeDasharray="3,3" />
                <text x={padL + plotW + 4} y={yZero + 3} fill="#6c8496" fontSize="8" fontFamily="monospace">
                    R$ 0
                </text>

                {/* Área Preenchida e Linha da Curva de Capital */}
                <polygon points={areaPts} fill={`url(#eq-grad-${symKey})`} />
                <polyline fill="none" stroke={curveColor} strokeWidth="2.2" points={polyPts} />

                {/* Pontos de Cada Operação do Dia */}
                {equityPoints.map((pt, i) => {
                    const cx = toX(i);
                    const cy = toY(pt.cumBrl);
                    const isSel = pt.id && selectedSigId === pt.id;
                    const dotCol = i === 0 ? "#00d4ff" : pt.isOpen ? "#ffd600" : pt.isGain ? "#00e87a" : "#ff3860";
                    return (
                        <g
                            key={`eq-pt-${i}`}
                            onMouseEnter={() => setHoverTradeIdx(i)}
                            onClick={() => pt.id && onSelectSignal && onSelectSignal(pt.id)}
                            style={{ cursor: pt.id ? "pointer" : "default" }}
                        >
                            <circle
                                cx={cx}
                                cy={cy}
                                r={isSel ? "5" : i === equityPoints.length - 1 ? "4" : "3"}
                                fill={dotCol}
                                stroke="#05080d"
                                strokeWidth="1.2"
                            />
                        </g>
                    );
                })}

                {/* Etiqueta do Saldo Atual na Direita */}
                {(() => {
                    const lastEq = equityPoints[equityPoints.length - 1];
                    const xLast = toX(equityPoints.length - 1);
                    const yLast = toY(lastEq.cumBrl);
                    return (
                        <g>
                            <line x1={xLast + 4} y1={yLast} x2={padL + plotW} y2={yLast} stroke={curveColor} strokeWidth="1" strokeDasharray="2,2" opacity="0.75" />
                            <rect x={padL + plotW + 2} y={yLast - 8} width={padR - 4} height={15} rx="3" fill="#0c1218" stroke={curveColor} strokeWidth="1" />
                            <text x={padL + plotW + 5} y={yLast + 3} fill={curveColor} fontSize="8.5" fontWeight="bold" fontFamily="monospace">
                                {lastEq.cumBrl >= 0 ? "+" : ""}{fmtNum(lastEq.cumBrl, 0)}
                            </text>
                        </g>
                    );
                })()}

                {/* Eixo de Tempo no Rodapé */}
                <text x={padL + 2} y={h - 4} fill="#6b8599" fontSize="8" fontFamily="monospace">09:00</text>
                {equityPoints.length > 2 && (
                    <text x={padL + plotW / 2 - 14} y={h - 4} fill="#6b8599" fontSize="8" fontFamily="monospace">
                        {equityPoints[Math.floor(equityPoints.length / 2)]?.time}
                    </text>
                )}
                <text x={padL + plotW - 26} y={h - 4} fill="#6b8599" fontSize="8" fontFamily="monospace">
                    {equityPoints[equityPoints.length - 1]?.time}
                </text>
            </svg>

            {/* Barra de Inspeção da Operação Selecionada / Última Operação */}
            <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: 9,
                fontFamily: "monospace",
                background: "#0c1218",
                padding: "5px 8px",
                borderRadius: 5,
                border: "1px solid #1a2530",
            }}>
                <span style={{ color: "#8ca5b5" }}>
                    🕒 {inspected.time} · <strong style={{ color: inspected.isOpen ? "#ffd600" : (inspected.isGain ? "#00e87a" : "#ff3860") }}>{inspected.dirLabel}</strong>
                </span>
                <span style={{ color: inspected.isOpen ? "#ffd600" : (inspected.tradeBrl >= 0 ? "#00e87a" : "#ff6b8b"), fontWeight: "bold" }}>
                    {inspected.isOpen
                        ? "⏳ EM ABERTO (Aguardando Alvo/Stop)"
                        : `Trade: ${inspected.tradeBrl >= 0 ? "+" : ""}R$ ${fmtNum(inspected.tradeBrl, 0)} (${fmtNum(inspected.tradePts, dec, true)}p)`}
                </span>
            </div>

            {/* Lista Compacta das Operações do Dia */}
            <div style={{
                display: "flex",
                flexDirection: "column",
                gap: 4,
                maxHeight: 165,
                overflowY: "auto",
                borderTop: "1px solid #16222d",
                paddingTop: 6,
            }}>
                {signalsLog.length === 0 ? (
                    <div style={{ fontSize: 9, color: "#5a7288", textAlign: "center", padding: "12px 0", fontFamily: "monospace" }}>
                        Nenhuma operação encerrada/aberta hoje até o momento.
                    </div>
                ) : (
                    signalsLog.slice(0, 8).map((sig) => {
                        const isBuy = (sig.dir_num || 0) > 0;
                        const st = String(sig.validation_status || "");
                        const isOpen = st === "EM_ANDAMENTO";
                        const pts = Number(sig.realized_pts || 0);
                        const brl = sig.brl_1c !== undefined && sig.brl_1c !== null
                            ? Number(sig.brl_1c) * contracts
                            : pts * brlPerPt * contracts;
                        const isSel = selectedSigId === sig.id;
                        const isWallsFlow = isWallsFlowLocalhost();
                        const shortMap = isWallsFlow ? {
                            WIN_DIV_WALL: "🎯 WIN Div · 2L Mix",
                            WDO_DIV_WALL: "🎯 WDO Div · 1L MidWall",
                        } : {
                            EST_01: "EST-01 PinBar",
                            EST_04: "EST-04 WDO-Alinh",
                            EST_07: "EST-07 Clímax",
                            EST_13: "EST-13 SG Scalp",
                            EST_14: "EST-14 SG Mom",
                            EST_15: "EST-15 SG Z30",
                            EST_16: "EST-16 Div NR",
                            WDO_01: "WDO-01 Scalper NY",
                            WDO_02: "WDO-02 Scalper",
                            WDO_05: "WDO-05 Cluster",
                            WDO_07: "WDO-07 Absorção",
                            WDO_09: "WDO-09 Defesa NR",
                            WDO_10: "WDO-10 Lunch",
                            WDO_11: "WDO-01 Scalper NY",
                            WDO_S2: "WDO-01 Scalper NY",
                        };
                        const sName = shortMap[sig.strategy_id] || sig.strategy_short || sig.type || "Setup";
                        return (
                            <div
                                key={sig.id}
                                onClick={() => onSelectSignal && onSelectSignal(isSel ? null : sig.id)}
                                style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    fontSize: 8.8,
                                    fontFamily: "monospace",
                                    padding: "4px 7px",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                    background: isSel ? "rgba(0, 212, 255, 0.12)" : "#090e13",
                                    border: isSel ? "1px solid #00d4ff66" : "1px solid #141e28",
                                }}
                            >
                                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                    <span style={{ color: "#9fb4c7", fontWeight: "bold" }}>{sig.time}</span>
                                    <span style={{ color: isBuy ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                        {isBuy ? "▲" : "▼"}
                                    </span>
                                    <span style={{ color: "#d0dde8" }}>{sName}</span>
                                    <span style={{ color: "#6b8299" }}>@{fmtNum(sig.entry_price, dec)}</span>
                                </div>
                                <span style={{
                                    fontWeight: "bold",
                                    color: isOpen ? "#ffd600" : (pts >= 0 ? "#00e87a" : "#ff6b8b"),
                                }}>
                                    {isOpen ? "⏳ ABERTO" : `${brl >= 0 ? "+" : ""}R$ ${fmtNum(brl, 0)} (${pts >= 0 ? "+" : ""}${fmtNum(pts, dec)}p)`}
                                </span>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
}

/* ── CURVA DE CAPITAL DA CARTEIRA COMBINADA (WIN + WDO JUNTOS NO DIA) ── */
function CombinedPortfolioDayCard({ winPayload, wdoPayload }) {
    const [winContracts, setWinContracts] = useState(1);
    const [wdoContracts, setWdoContracts] = useState(1);
    const isWallsFlow = isWallsFlowLocalhost();

    const winSigs = [...filterSignalsForHost(winPayload?.caminho_a?.signals_log || [], isWallsFlow)].reverse();
    const wdoSigs = [...filterSignalsForHost(wdoPayload?.caminho_a?.signals_log || [], isWallsFlow)].reverse();

    const merged = [
        ...winSigs.map(s => ({ ...s, asset: "WIN", contracts: winContracts, brlMult: 0.20 * winContracts })),
        ...wdoSigs.map(s => ({ ...s, asset: "WDO", contracts: wdoContracts, brlMult: 10.0 * wdoContracts })),
    ].sort((a, b) => String(a.time || "").localeCompare(String(b.time || "")));

    let cumBrl = 0;
    let peakBrl = 0;
    let maxDdBrl = 0;
    let winBrl = 0;
    let wdoBrl = 0;
    let gainBrl = 0;
    let lossBrl = 0;

    const eqPts = [{ time: "09:00", cumBrl: 0, asset: "—", tradeBrl: 0 }];
    merged.forEach((s) => {
        const st = String(s.validation_status || "");
        const pts = st === "EM_ANDAMENTO" ? 0 : Number(s.realized_pts || 0);
        const tBrl = st === "EM_ANDAMENTO"
            ? 0
            : (s.brl_1c !== undefined && s.brl_1c !== null
                ? Number(s.brl_1c) * s.contracts
                : pts * s.brlMult);
        if (st !== "EM_ANDAMENTO") {
            if (tBrl >= 0) gainBrl += tBrl;
            else lossBrl += Math.abs(tBrl);
            if (s.asset === "WIN") winBrl += tBrl;
            else wdoBrl += tBrl;
        }
        cumBrl += tBrl;
        if (cumBrl > peakBrl) peakBrl = cumBrl;
        if (peakBrl - cumBrl > maxDdBrl) maxDdBrl = peakBrl - cumBrl;
        eqPts.push({
            time: s.time,
            cumBrl,
            asset: s.asset,
            tradeBrl: tBrl,
            type: s.type,
        });
    });

    const isPos = cumBrl >= 0;
    const col = isPos ? "#00e87a" : "#ff3860";
    const pf = lossBrl > 0 ? (gainBrl / lossBrl) : (gainBrl > 0 ? 9.9 : 1.0);

    const w = 900, h = 92, padL = 14, padR = 70, padT = 10, padB = 18;
    const plotW = w - padL - padR, plotH = h - padT - padB;
    let minV = 0, maxV = 0;
    eqPts.forEach(p => {
        if (p.cumBrl < minV) minV = p.cumBrl;
        if (p.cumBrl > maxV) maxV = p.cumBrl;
    });
    const span = Math.max(100, maxV - minV);
    minV -= span * 0.12;
    maxV += span * 0.12;
    const rng = Math.max(1e-6, maxV - minV);
    const toX = (i) => padL + (i / Math.max(1, eqPts.length - 1)) * plotW;
    const toY = (v) => padT + plotH - ((v - minV) / rng) * plotH;
    const yZero = toY(0);
    const poly = eqPts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.cumBrl).toFixed(1)}`).join(" ");
    const area = `${toX(0).toFixed(1)},${yZero.toFixed(1)} ${poly} ${toX(eqPts.length - 1).toFixed(1)},${yZero.toFixed(1)}`;

    return (
        <div style={{
            background: "#0c1218",
            border: "1px solid #1a2530",
            borderRadius: 10,
            padding: "10px 16px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 12, fontWeight: "bold", color: "#ffffff", letterSpacing: 0.8 }}>
                        ⚖️ CARTEIRA COMBINADA DO DIA (ÍNDICE WIN + DÓLAR WDO JUNTOS)
                    </span>
                    <span style={{ fontSize: 9.5, color: "#00e87a", background: "#0c1218", border: "1px solid #00e87a44", padding: "2px 8px", borderRadius: 4, fontFamily: "monospace", fontWeight: "bold" }}>
                        {isWallsFlow
                            ? "🎯 SNIPER DIVERGÊNCIA NA WALL (BASE 2c WIN + 1c WDO): s/ 12h WIN & 11h WDO · Meta +R$ 180 / +R$ 120 · corrigido (causal) · WR 67% · PF 1,95 · Ret/DD 14,2 · 10/11 M+"
                            : "⭐ TOP 8 ELITE M5 C/ FLUXO (PROPOSTA A): 5 WIN (EST-04/07/13/14/15) + 3 WDO (WDO-01/05/07) · 11/11 M+ · Ret/DD 28,24x"}
                    </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: "monospace", fontSize: 10 }}>
                    <span style={{ color: "#00d4ff" }}>
                        WIN ({isWallsFlow ? `${winContracts * 2}c` : `${winContracts}c`}): <strong>{winBrl >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(winBrl), 0)}</strong>
                    </span>
                    <span style={{ color: "#c8a444" }}>
                        WDO ({wdoContracts}c): <strong>{wdoBrl >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(wdoBrl), 0)}</strong>
                    </span>
                    <span style={{ color: col, fontSize: 13, fontWeight: 900, background: "#0c1218", padding: "3px 10px", borderRadius: 6, border: `1px solid ${col}55` }}>
                        TOTAL: {cumBrl >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(cumBrl), 0)} ({merged.length} ops | PF {fmtNum(pf, 2)}x | DD -R$ {fmtNum(maxDdBrl, 0)})
                    </span>
                </div>
            </div>
            <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "auto", display: "block", background: "#0c1218", borderRadius: 7, border: "1px solid #1a2530" }}>
                <line x1={padL} y1={yZero} x2={padL + plotW} y2={yZero} stroke="#2a3f54" strokeWidth="1" strokeDasharray="3,3" />
                <polygon points={area} fill={col} fillOpacity="0.16" />
                <polyline fill="none" stroke={col} strokeWidth="2.4" points={poly} />
                {eqPts.map((p, i) => (
                    <circle
                        key={`comb-pt-${i}`}
                        cx={toX(i)}
                        cy={toY(p.cumBrl)}
                        r={i === eqPts.length - 1 ? "4" : "3"}
                        fill={i === 0 ? "#00d4ff" : p.asset === "WIN" ? "#00d4ff" : "#ffd700"}
                        stroke="#05080d"
                        strokeWidth="1"
                    >
                        <title>{`${p.time} · ${p.asset} (${p.type || "Início"}) → Acumulado: R$ ${fmtNum(p.cumBrl, 0)}`}</title>
                    </circle>
                ))}
                <text x={padL + plotW + 6} y={toY(cumBrl) + 3} fill={col} fontSize="9.5" fontWeight="bold" fontFamily="monospace">
                    {cumBrl >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(cumBrl), 0)}
                </text>
            </svg>
        </div>
    );
}

/* ── CURVA DE CAPITAL AUDITADA (MODO 5174 PROPOSTA A ⭐ TOP 8 ELITE M5 vs MODO 5176 PROPOSTA B ⭐ 6 WALLS V2) ── */
const MT5_STRAT_META = [
    {
        id: "EST_04", asset: "WIN", code: "EST-04", shortLabel: "💎 EST-04 Pullback", name: "EST-04 · WIN Pullback WDO", short: "EST-04",
        color: "#22d3ee", strokeW: 1.9, dec: 0,
        subRule: "TP MidWall · BE 2-Estágios Wall (15p->45p) · 15_NR_IGNITION_DIV (Ret/DD 5,71x)",
    },
    {
        id: "EST_07", asset: "WIN", code: "EST-07", shortLabel: "💠 EST-07 Rompimento", name: "EST-07 · WIN Ignição Wall", short: "EST-07",
        color: "#00d4ff", strokeW: 1.9, dec: 0,
        subRule: "TP MidWall · BE Escudo Wall (15p) · NWE Dual Slope · 16_NR_DIV_ABS_OR_AGGR (Ret/DD 8,60x)",
    },
    {
        id: "EST_13", asset: "WIN", code: "EST-13", shortLabel: "⚡ EST-13 Longa (35% B1)", name: "EST-13 · WIN SmartGrid Longa (35% B1 · TP 360p)", short: "EST-13",
        color: "#38bdf8", strokeW: 1.9, dec: 0,
        subRule: "Limite 35% B1 · TP Estendido 360p · NextWall 1+2L (BE 145p) · 11_PROFIT_WALL_SHIELD (Ret/DD 8,22x)",
    },
    {
        id: "EST_14", asset: "WIN", code: "EST-14", shortLabel: "🍀 EST-14 Média (50% B1)", name: "EST-14 · WIN SmartGrid Média (50% B1 · TP 280p)", short: "EST-14",
        color: "#34d399", strokeW: 2.0, dec: 0,
        subRule: "Limite 50% B1 · TP Intermediário 280p · NextWall 1+2L (BE 130p) · 12_NR_WALL_TRAP_DIV (Ret/DD 7,27x)",
    },
    {
        id: "EST_15", asset: "WIN", code: "EST-15", shortLabel: "🎯 EST-15 Curta (55% B1)", name: "EST-15 · WIN SmartGrid Curta (55% B1 · TP 210p)", short: "EST-15",
        color: "#10b981", strokeW: 1.9, dec: 0,
        subRule: "Limite 55% B1 · TP Encurtado 210p · NextWall 1+2L (BE 110p) · 14_NR_BREAKOUT_SQUEEZE (Ret/DD 6,66x)",
    },
    {
        id: "WDO_01", asset: "WDO", code: "WDO-01", shortLabel: "🟠 WDO-01 Curta NY (6–8p)", name: "WDO-01 · WDO Scalper Curto NY (TP 6.0p–8.0p)", short: "WDO-01",
        color: "#f59e0b", strokeW: 1.9, dec: 1,
        subRule: "TP Curto 6.0p–8.0p · SL 9.5p + BE Escudo Wall (1.0p) · 13_NR_PRICE_ABS_DIV (Ret/DD 9,35x)",
    },
    {
        id: "WDO_05", asset: "WDO", code: "WDO-05", shortLabel: "🟣 WDO-05 Média Limite (7–9.5p)", name: "WDO-05 · WDO Cluster Limit Wall (TP 7.0p–9.5p)", short: "WDO-05",
        color: "#a78bfa", strokeW: 2.0, dec: 1,
        subRule: "Limite B1±0.5p · TP 7.0p–9.5p · SL 10.0p + BE Escudo Wall (1.0p) · 13_NR_PRICE_ABS_DIV (Ret/DD 8,93x)",
    },
    {
        id: "WDO_07", asset: "WDO", code: "WDO-07", shortLabel: "🟡 WDO-07 Longa NY (11p)", name: "WDO-07 · WDO Absorção Longa NY (TP 11.0p)", short: "WDO-07",
        color: "#ffd600", strokeW: 1.9, dec: 1,
        subRule: "TP Estendido até 11.0p · SL 11.5p + BE Escudo Wall (1.0p) · 12_NR_WALL_TRAP_DIV (Ret/DD 8,73x)",
    },
];

const WALLS_FLOW_STRAT_META = [
    {
        id: "WIN_DIV_WALL", asset: "WIN", code: "WIN-2L-MIX", shortLabel: "🇧🇷 WIN Sniper · 2c Mix (NWE30 + 750p)", name: "WIN_DIV_WALL · 🇧🇷 WIN Sniper F1➔F2 / T1➔T2 · 2 Contratos Mix", short: "WIN 2c Mix",
        color: "#00e87a", strokeW: 2.3, dec: 0,
        subRule: "Sniper F1➔F2/T1➔T2 c/ sobreposição · s/ 12h · Meta +R$ 180/dia · 2c (NWE30 Din + 750p) · WR 74,2% · PF 2,71",
    },
    {
        id: "WDO_DIV_WALL", asset: "WDO", code: "WDO-1L-MID", shortLabel: "💵 WDO Sniper · 1c MidWalls", name: "WDO_DIV_WALL · 💵 WDO Sniper F1➔F2 / T1➔T2 · 1 Contrato MidWall", short: "WDO 1c Mid",
        color: "#ffd600", strokeW: 2.2, dec: 1,
        subRule: "Sniper F1➔F2/T1➔T2 c/ sobreposição · s/ 11h NY/PTAX · Meta +R$ 120/dia · 1c MidWall · WR 67,8% · PF 2,36",
    },
];

const MT5_PRESET_IDS = ["EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07"];

const Portfolio4SistematicasPanel = memo(function Portfolio4SistematicasPanel({ portfolioData, winPayload, wdoPayload, onSelectDate }) {
    const isWallsFlow = isWallsFlowLocalhost();
    const ALL_11_STRAT_META = isWallsFlow ? WALLS_FLOW_STRAT_META : MT5_STRAT_META;
    const STRAT_META_BY_ID = Object.fromEntries(ALL_11_STRAT_META.map((m) => [m.id, m]));
    if (!isWallsFlow) {
        STRAT_META_BY_ID.WDO_11 = STRAT_META_BY_ID.WDO_01;
        STRAT_META_BY_ID.WDO_S2 = STRAT_META_BY_ID.WDO_01;
    }
    const PRESET_TOP6_IDS = isWallsFlow ? WALLS_FLOW_6_IDS : MT5_PRESET_IDS;

    const [winContracts, setWinContracts] = useState(1);
    const [wdoContracts, setWdoContracts] = useState(1);
    const [rangeMode, setRangeMode] = useState("ALL"); // "ALL" | "60D" | "30D"
    const [hoverIdx, setHoverIdx] = useState(null);
    const [pinnedIdx, setPinnedIdx] = useState(null);
    const [tradeHistTab, setTradeHistTab] = useState("ALL"); // "ALL" | "DAY"
    const [stratFilter, setStratFilter] = useState("ALL");
    const [maxHistRows, setMaxHistRows] = useState(120);
    const [visibleCurves, setVisibleCurves] = useState(() => {
        const init = { PORTFOLIO: true };
        [...MT5_STRAT_META, ...WALLS_FLOW_STRAT_META].forEach((m) => {
            init[m.id] = true;
        });
        return init;
    });

    const toggleCurve = (key) => {
        setVisibleCurves((prev) => ({ ...prev, [key]: !prev[key] }));
    };

    const winMult = 0.20 * winContracts; // R$ por ponto WIN
    const wdoMult = 10.0 * wdoContracts; // R$ por ponto WDO
    const allDays = Array.isArray(portfolioData?.days) ? portfolioData.days : [];
    const summary1c = portfolioData?.summary_1c || {};
    const liveDays = portfolioData?.live_days || [];

    // Estratégias ativas para compor o Portfólio Dinâmico
    const activeStratIds = ALL_11_STRAT_META.filter((m) => visibleCurves[m.id]).map((m) => m.id);
    const effectivePortIds = activeStratIds.length > 0 ? activeStratIds : PRESET_TOP6_IDS;
    const effectivePortKey = effectivePortIds.join(",");

    const {
        fullSeries,
        byMonth,
        cumById,
        mddById,
        kpiById,
        cPort,
        mddPort,
        portOps,
        portWr,
        portPf,
        portRetDd,
        totalMonthsCount,
        posMonthsCount,
        curveConfigs,
        allHistoricalTrades,
    } = useMemo(() => {
        const _cumById = { PORTFOLIO: 0 };
        const _pkById = { PORTFOLIO: 0 };
        const _mddById = { PORTFOLIO: 0 };
        ALL_11_STRAT_META.forEach((m) => {
            _cumById[m.id] = 0;
            _pkById[m.id] = 0;
            _mddById[m.id] = 0;
        });

        const originPt = {
            idx: 0,
            date: portfolioData?.start_date || "2026-05-11",
            month: "Início",
            is_live: false,
            isOrigin: true,
            d_PORT: 0,
            PORTFOLIO: 0,
            dd_PORT: 0,
            ops_total: 0,
            trades: [],
            open_trades: [],
        };
        ALL_11_STRAT_META.forEach((m) => {
            originPt[`d_${m.id}`] = 0;
            originPt[m.id] = 0;
        });

        const _fullSeries = [originPt];
        const _byMonth = {};

        allDays.forEach((d, i) => {
            const dayTrades = d.trades || [];
            let dPort = 0;
            let opsDay = 0;
            const ptObj = {
                idx: i + 1,
                date: d.date,
                month: d.month,
                is_live: Boolean(d.is_live),
                trades: dayTrades,
                open_trades: d.open_trades || [],
            };

            const mKey = d.is_live ? `${d.month} (Live)` : d.month;
            if (!_byMonth[mKey]) {
                _byMonth[mKey] = {
                    month: mKey,
                    is_live: Boolean(d.is_live),
                    WIN_SUM: 0,
                    WDO_SUM: 0,
                    PORTFOLIO: 0,
                    ops: 0,
                };
                ALL_11_STRAT_META.forEach((m) => { _byMonth[mKey][m.id] = 0; });
            }

            ALL_11_STRAT_META.forEach((m) => {
                const sid = m.id;
                const mult = m.asset === "WIN" ? winMult : wdoMult;
                let ptsDay = d[`${sid}_pts`];
                let opsStrat = d[`${sid}_ops`];
                if (ptsDay === undefined || opsStrat === undefined) {
                    const sTrades = dayTrades.filter((t) => t.strategy_id === sid || (sid === "WDO_02" && t.strategy_id === "WDO_11") || (sid === "WDO_10" && t.strategy_id === "WDO_S2"));
                    ptsDay = sTrades.reduce((acc, t) => acc + Number(t.pts || 0), 0);
                    opsStrat = sTrades.length;
                }
                ptsDay = Number(ptsDay || 0);
                opsStrat = Number(opsStrat || 0);
                const brlDay = ptsDay * mult;

                _cumById[sid] += brlDay;
                if (_cumById[sid] > _pkById[sid]) _pkById[sid] = _cumById[sid];
                if (_pkById[sid] - _cumById[sid] > _mddById[sid]) _mddById[sid] = _pkById[sid] - _cumById[sid];

                ptObj[`d_${sid}`] = brlDay;
                ptObj[`${sid}_pts`] = ptsDay;
                ptObj[`${sid}_ops`] = opsStrat;
                ptObj[sid] = _cumById[sid];

                _byMonth[mKey][sid] += brlDay;

                if (effectivePortIds.includes(sid)) {
                    dPort += brlDay;
                    opsDay += opsStrat;
                    if (m.asset === "WIN") _byMonth[mKey].WIN_SUM += brlDay;
                    else _byMonth[mKey].WDO_SUM += brlDay;
                }
            });

            _cumById.PORTFOLIO += dPort;
            if (_cumById.PORTFOLIO > _pkById.PORTFOLIO) _pkById.PORTFOLIO = _cumById.PORTFOLIO;
            if (_pkById.PORTFOLIO - _cumById.PORTFOLIO > _mddById.PORTFOLIO) _mddById.PORTFOLIO = _pkById.PORTFOLIO - _cumById.PORTFOLIO;

            _byMonth[mKey].PORTFOLIO += dPort;
            _byMonth[mKey].ops += opsDay;

            ptObj.d_PORT = dPort;
            ptObj.ops_total = opsDay;
            ptObj.PORTFOLIO = _cumById.PORTFOLIO;
            ptObj.dd_PORT = _cumById.PORTFOLIO - _pkById.PORTFOLIO;

            _fullSeries.push(ptObj);
        });

        const buildCurveKpi = (sid, multContracts, totBrl, maxDdBrl) => {
            const base = summary1c[sid] || {};
            let ops = Number(base.ops || 0);
            let wins = Number(base.wins ?? Math.round(ops * Number(base.wr_pct || 0) / 100));
            let gWin = Number(base.gross_win_1c || 0) * multContracts;
            let gLoss = Number(base.gross_loss_1c || 0) * multContracts;
            let totPts = Number(base.tot_pts || 0);

            liveDays.forEach((ld) => {
                (ld.trades || []).forEach((tr) => {
                    if (tr.strategy_id === sid && tr.status === "FECHADA") {
                        ops += 1;
                        const brl = Number(tr.brl_1c || 0) * multContracts;
                        totPts += Number(tr.pts || 0);
                        if (brl > 0) {
                            wins += 1;
                            gWin += brl;
                        } else if (brl < 0) {
                            gLoss += Math.abs(brl);
                        }
                    }
                });
            });

            const wr = ops > 0 ? (wins / ops) * 100 : 0;
            const pf = gLoss > 0 ? gWin / gLoss : Number(base.pf || 1.0);
            const exactMaxDd = maxDdBrl > 0 ? maxDdBrl : Number(base.max_dd_brl_1c || 0) * multContracts;
            const retDd = exactMaxDd > 0 ? totBrl / exactMaxDd : 99.9;
            return { ops, wins, wr, pf, gWin, gLoss, totPts, totBrl, maxDdBrl: exactMaxDd, retDd };
        };

        const _kpiById = {};
        ALL_11_STRAT_META.forEach((m) => {
            const multC = m.asset === "WIN" ? winContracts : wdoContracts;
            _kpiById[m.id] = buildCurveKpi(m.id, multC, _cumById[m.id], _mddById[m.id]);
        });

        const _cPort = _cumById.PORTFOLIO;
        const _mddPort = _mddById.PORTFOLIO;
        const _portOps = effectivePortIds.reduce((acc, sid) => acc + _kpiById[sid].ops, 0);
        const _portWins = effectivePortIds.reduce((acc, sid) => acc + _kpiById[sid].wins, 0);
        const _portGWin = effectivePortIds.reduce((acc, sid) => acc + _kpiById[sid].gWin, 0);
        const _portGLoss = effectivePortIds.reduce((acc, sid) => acc + _kpiById[sid].gLoss, 0);
        const _portWr = _portOps > 0 ? (_portWins / _portOps) * 100 : 0;
        const _portPf = _portGLoss > 0 ? _portGWin / _portGLoss : 1.5;
        const _portRetDd = _mddPort > 0 ? _cPort / _mddPort : 99.9;
        const _totalMonthsCount = Object.keys(_byMonth).length;
        const _posMonthsCount = Object.values(_byMonth).filter((m) => m.PORTFOLIO > 0).length;

        const _curveConfigs = [
            {
                key: "PORTFOLIO",
                shortLabel: `🏆 PORTFÓLIO (${effectivePortIds.length} ATIVAS)`,
                title: `🏆 PORTFÓLIO COMBINADO (${effectivePortIds.length} ESTRATÉGIAS ATIVAS)`,
                subRule: `WIN (${isWallsFlow ? 2 * winContracts : winContracts}c) + WDO (${wdoContracts}c) · ${_posMonthsCount}/${_totalMonthsCount} Meses Positivos · Ret/DD ${fmtNum(_portRetDd, 2)}x`,
                color: "#00e87a",
                strokeW: 2.9,
                kpi: {
                    ops: _portOps,
                    wr: _portWr,
                    pf: _portPf,
                    totBrl: _cPort,
                    totPts: null,
                    maxDdBrl: _mddPort,
                    retDd: _portRetDd,
                },
            },
            ...ALL_11_STRAT_META.map((m) => ({
                key: m.id,
                shortLabel: m.shortLabel,
                title: m.name,
                subRule: m.subRule,
                color: m.color,
                strokeW: m.strokeW,
                kpi: _kpiById[m.id],
                dec: m.dec,
            })),
        ];

        const _allHistoricalTrades = [];
        for (let di = _fullSeries.length - 1; di >= 1; di--) {
            const dayObj = _fullSeries[di];
            const dayOpen = (dayObj.open_trades || []).filter((tr) => PRESET_TOP6_IDS.includes(tr.strategy_id));
            const dayClosed = (dayObj.trades || []).filter((tr) => PRESET_TOP6_IDS.includes(tr.strategy_id));
            dayOpen.forEach((tr) => _allHistoricalTrades.push({ ...tr, date: tr.date || dayObj.date }));
            for (let ti = dayClosed.length - 1; ti >= 0; ti--) {
                const tr = dayClosed[ti];
                _allHistoricalTrades.push({ ...tr, date: tr.date || dayObj.date });
            }
        }

        return {
            fullSeries: _fullSeries,
            byMonth: _byMonth,
            cumById: _cumById,
            mddById: _mddById,
            kpiById: _kpiById,
            cPort: _cPort,
            mddPort: _mddPort,
            portOps: _portOps,
            portWr: _portWr,
            portPf: _portPf,
            portRetDd: _portRetDd,
            totalMonthsCount: _totalMonthsCount,
            posMonthsCount: _posMonthsCount,
            curveConfigs: _curveConfigs,
            allHistoricalTrades: _allHistoricalTrades,
        };
    }, [portfolioData, winContracts, wdoContracts, effectivePortKey, isWallsFlow]);

    if (!portfolioData || !portfolioData.ok || allDays.length === 0) {
        return null;
    }

    const visibleSeries = rangeMode === "30D"
        ? fullSeries.slice(-31)
        : rangeMode === "60D"
            ? fullSeries.slice(-61)
            : fullSeries;

    // Dimensões do SVG Principal (Curvas de Capital + Subwater Drawdown)
    const w = 1180;
    const hEq = 250;
    const hDd = 66;
    const h = hEq + hDd + 28;
    const padL = 62;
    const padR = 96;
    const padT = 18;
    const plotW = w - padL - padR;
    const plotHEq = hEq - padT - 12;
    const ddTop = hEq + 8;
    const plotHDd = hDd - 14;

    let minEq = 0;
    let maxEq = 500;
    let minDd = -200;

    visibleSeries.forEach((pt) => {
        curveConfigs.forEach((cfg) => {
            if (visibleCurves[cfg.key]) {
                const v = Number(pt[cfg.key] || 0);
                if (v < minEq) minEq = v;
                if (v > maxEq) maxEq = v;
            }
        });
        if (pt.dd_PORT < minDd) minDd = pt.dd_PORT;
    });

    const spanEq = Math.max(500, maxEq - minEq);
    minEq -= spanEq * 0.08;
    maxEq += spanEq * 0.10;
    const rangeEq = Math.max(1, maxEq - minEq);

    const nPts = visibleSeries.length;
    const toX = (i) => padL + (i / Math.max(1, nPts - 1)) * plotW;
    const toYEq = (v) => padT + plotHEq - ((v - minEq) / rangeEq) * plotHEq;
    const yZeroEq = toYEq(0);

    const rangeDd = Math.max(100, Math.abs(minDd) * 1.15);
    const toYDd = (v) => ddTop + ((0 - v) / rangeDd) * plotHDd; // v <= 0

    // Marcações de meses e início do Live Trading
    const monthTicks = [];
    let prevM = "";
    let firstLiveIdx = -1;
    visibleSeries.forEach((pt, i) => {
        if (i > 0 && pt.month && pt.month !== prevM && !pt.is_live) {
            monthTicks.push({ idx: i, label: pt.month });
            prevM = pt.month;
        }
        if (pt.is_live && firstLiveIdx === -1) {
            firstLiveIdx = i;
        }
    });

    // Grade horizontal Y do gráfico de capital
    const ySteps = 5;
    const yGridVals = [];
    for (let s = 0; s <= ySteps; s++) {
        yGridVals.push(minEq + (rangeEq * s) / ySteps);
    }

    const activeIdx = hoverIdx !== null
        ? hoverIdx
        : pinnedIdx !== null
            ? pinnedIdx
            : visibleSeries.length - 1;
    const inspectedPt = visibleSeries[Math.min(visibleSeries.length - 1, Math.max(0, activeIdx))] || visibleSeries[visibleSeries.length - 1];

    // Sinais ao vivo do dia atual
    const latestLiveDay = liveDays.length > 0 ? liveDays[liveDays.length - 1] : null;
    const liveOpenTrades = latestLiveDay?.open_trades || [];
    const liveClosedTrades = latestLiveDay?.trades || [];

    return (
        <div style={{
            background: "#0c1218",
            border: "1px solid #1a2530",
            borderRadius: 10,
            padding: "14px 16px",
            display: "flex",
            flexDirection: "column",
            gap: 12,
            marginTop: 4,
        }}>
            {/* 1. CABEÇALHO + SELETORES DE CONTRATOS E PERÍODO */}
            <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 10,
                borderBottom: "1px solid #1a2530",
                paddingBottom: 10,
            }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 13, fontWeight: 900, color: "#ffffff", letterSpacing: 0.7 }}>
                            {isWallsFlow
                                ? "🎯 PORTFÓLIO SNIPER · DIVERGÊNCIA F1➔F2 / T1➔T2 NA WALL (BASE: 2c WIN MIX + 1c WDO MIDWALL · s/ 12h WIN & 11h WDO · META DIÁRIA · WR 70% · PF 2,49)"
                                : "📈 PORTFÓLIO TOP 8 ELITE M5 C/ FLUXO · PROPOSTA A ⭐ (5 WIN + 3 WDO · 11/11 M+ · Ret/DD 28,24x)"}
                        </span>
                        <span style={{
                            fontSize: 9,
                            fontFamily: "monospace",
                            fontWeight: "bold",
                            color: "#00e87a",
                            background: "rgba(0, 232, 122, 0.10)",
                            border: "1px solid rgba(0, 232, 122, 0.40)",
                            padding: "2px 8px",
                            borderRadius: 4,
                        }}>
                            ✅ {portfolioData.total_bt_sessions || 123} Pregões BT ({fmtDateShort(portfolioData.start_date)} a {fmtDateShort(portfolioData.last_bt_date)}) + 🟢 Live ({fmtDateShort(portfolioData.live_start_date)}+)
                        </span>
                    </div>
                    <span style={{ fontSize: 9.5, color: "#7f96a8" }}>
                        Carteira Campeã ({effectivePortIds.length} estratégias ativas): <strong style={{ color: "#00e87a" }}>+R$ {fmtNum(cPort, 0)}</strong> líquido de custos B3 (R$ 2/ctr WIN e R$ 5/ctr WDO) ·{" "}
                        <strong>{portOps} trades</strong> (~{fmtNum(portOps / Math.max(1, fullSeries.length - 1), 1)} ops/dia) ·{" "}
                        <strong>{posMonthsCount}/{totalMonthsCount} meses positivos</strong> · Max DD <strong>-R$ {fmtNum(mddPort, 0)}</strong> ·{" "}
                        <strong style={{ color: "#00d4ff" }}>Ret/DD = {fmtNum(portRetDd, 2)}x</strong>.
                    </span>
                </div>

                {/* Controles de Lote WIN / WDO e Janela Temporal */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <button
                        onClick={() => toggleCurve("PORTFOLIO")}
                        style={{
                            padding: "3px 8px",
                            fontSize: 8.5,
                            fontFamily: "monospace",
                            fontWeight: "bold",
                            borderRadius: 4,
                            cursor: "pointer",
                            background: visibleCurves.PORTFOLIO ? "#00e87a" : "#0c1218",
                            color: visibleCurves.PORTFOLIO ? "#04080e" : "#8ca5b5",
                            border: visibleCurves.PORTFOLIO ? "1px solid #00e87a" : "1px solid #1a2530",
                        }}
                    >
                        🏆 Curva Portfólio ({visibleCurves.PORTFOLIO ? "ON" : "OFF"})
                    </button>

                    {/* Preset Escala Base */}
                    <div style={{ display: "flex", gap: 4, background: "#05080d", padding: "3px 5px", borderRadius: 6, border: "1px solid #1a2530" }}>
                        <button
                            onClick={() => { setWinContracts(1); setWdoContracts(1); }}
                            style={{
                                padding: "3px 7px",
                                fontSize: 8.5,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                borderRadius: 4,
                                cursor: "pointer",
                                background: winContracts === 1 && wdoContracts === 1 ? "#00d4ff" : "#0c1218",
                                color: winContracts === 1 && wdoContracts === 1 ? "#04080e" : "#8ca5b5",
                                border: "1px solid #1a2530",
                            }}
                        >
                            {isWallsFlow ? "🎯 Opção 2 Base (2L WIN + 1L WDO)" : "Base 1 WIN : 1 WDO"}
                        </button>
                        <button
                            onClick={() => isWallsFlow ? (setWinContracts(2), setWdoContracts(2)) : (setWinContracts(2), setWdoContracts(1))}
                            style={{
                                padding: "3px 7px",
                                fontSize: 8.5,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                borderRadius: 4,
                                cursor: "pointer",
                                background: (isWallsFlow ? (winContracts === 2 && wdoContracts === 2) : (winContracts === 2 && wdoContracts === 1)) ? "#00e87a" : "#0c1218",
                                color: (isWallsFlow ? (winContracts === 2 && wdoContracts === 2) : (winContracts === 2 && wdoContracts === 1)) ? "#04080e" : "#8ca5b5",
                                border: "1px solid #1a2530",
                            }}
                        >
                            {isWallsFlow ? "⚡ Escala 2x (4L WIN + 2L WDO)" : "⚖️ 2 WIN : 1 WDO"}
                        </button>
                    </div>

                    {/* Contratos WIN */}
                    <div style={{ display: "flex", alignItems: "center", gap: 4, background: "#05080d", padding: "3px 6px", borderRadius: 6, border: "1px solid #1a2530" }}>
                        <span style={{ fontSize: 8.5, color: "#00d4ff", fontWeight: "bold", fontFamily: "monospace" }}>WIN:</span>
                        {[1, 2, 4, 5, 10].map((c) => (
                            <button
                                key={`winc-${c}`}
                                onClick={() => setWinContracts(c)}
                                style={{
                                    padding: "2px 6px",
                                    fontSize: 8.5,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                    background: winContracts === c ? "#00d4ff" : "#0c1218",
                                    color: winContracts === c ? "#04080e" : "#8ca5b5",
                                    border: winContracts === c ? "1px solid #00d4ff" : "1px solid #1a2530",
                                }}
                            >
                                {isWallsFlow ? `${c}x(${c * 2}L)` : `${c}c`}
                            </button>
                        ))}
                    </div>

                    {/* Contratos WDO */}
                    <div style={{ display: "flex", alignItems: "center", gap: 4, background: "#05080d", padding: "3px 6px", borderRadius: 6, border: "1px solid #1a2530" }}>
                        <span style={{ fontSize: 8.5, color: "#ffd600", fontWeight: "bold", fontFamily: "monospace" }}>WDO:</span>
                        {[1, 2, 5].map((c) => (
                            <button
                                key={`wdoc-${c}`}
                                onClick={() => setWdoContracts(c)}
                                style={{
                                    padding: "2px 6px",
                                    fontSize: 8.5,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                    background: wdoContracts === c ? "#ffd600" : "#0c1218",
                                    color: wdoContracts === c ? "#04080e" : "#8ca5b5",
                                    border: wdoContracts === c ? "1px solid #ffd600" : "1px solid #1a2530",
                                }}
                            >
                                {isWallsFlow ? `${c}x(${c}L)` : `${c}c`}
                            </button>
                        ))}
                    </div>

                    {/* Período */}
                    <div style={{ display: "flex", gap: 4, background: "#05080d", padding: "3px 5px", borderRadius: 6, border: "1px solid #1a2530" }}>
                        {[
                            { id: "ALL", label: "Completo + Live" },
                            { id: "60D", label: "60d + Live" },
                            { id: "30D", label: "30d + Live" },
                        ].map((rm) => (
                            <button
                                key={rm.id}
                                onClick={() => { setRangeMode(rm.id); setHoverIdx(null); setPinnedIdx(null); }}
                                style={{
                                    padding: "2px 7px",
                                    fontSize: 8.5,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                    background: rangeMode === rm.id ? "#1a2530" : "transparent",
                                    color: rangeMode === rm.id ? "#ffffff" : "#7f96a8",
                                    border: rangeMode === rm.id ? "1px solid #2d4256" : "1px solid transparent",
                                }}
                            >
                                {rm.label}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* 2. SCORECARD INTERATIVO DAS ESTRATÉGIAS CAMPEÃS (CLIQUE PARA ATIVAR/DESATIVAR) */}
            <div style={{
                display: "grid",
                gridTemplateColumns: isWallsFlow ? "repeat(2, 1fr)" : "repeat(4, 1fr)",
                gap: 8,
            }}>
                {curveConfigs.filter((cfg) => cfg.key !== "PORTFOLIO").map((cfg) => {
                    const isOn = visibleCurves[cfg.key];
                    const k = cfg.kpi;
                    return (
                        <div
                            key={cfg.key}
                            onClick={() => toggleCurve(cfg.key)}
                            title="Clique para exibir/ocultar esta curva no gráfico"
                            style={{
                                background: "#05080d",
                                border: isOn ? `1.5px solid ${cfg.color}88` : "1px solid #1a2530",
                                borderRadius: 8,
                                padding: "7px 8px",
                                cursor: "pointer",
                                opacity: isOn ? 1 : 0.45,
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                gap: 4,
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 3 }}>
                                <span style={{ fontSize: 9, fontWeight: 900, color: cfg.color, letterSpacing: 0.2 }}>
                                    {cfg.shortLabel}
                                </span>
                                <span style={{
                                    fontSize: 7,
                                    fontFamily: "monospace",
                                    padding: "1px 4px",
                                    borderRadius: 3,
                                    background: isOn ? `${cfg.color}22` : "#0c1218",
                                    color: isOn ? cfg.color : "#6c8496",
                                    border: `1px solid ${cfg.color}44`,
                                }}>
                                    {isOn ? "ON" : "OFF"}
                                </span>
                            </div>

                            <div style={{ fontSize: 13.5, fontWeight: 900, color: k.totBrl >= 0 ? cfg.color : "#ff3860", fontFamily: "monospace" }}>
                                {k.totBrl >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(k.totBrl), 0)}
                                {k.totPts !== null && (
                                    <span style={{ fontSize: 8, color: "#8ca5b5", fontWeight: "normal", marginLeft: 4 }}>
                                        ({fmtNum(k.totPts, cfg.dec || 0, true)}p)
                                    </span>
                                )}
                            </div>

                            <div style={{
                                display: "grid",
                                gridTemplateColumns: "repeat(4, 1fr)",
                                gap: 3,
                                fontFamily: "monospace",
                                fontSize: 8,
                                borderTop: "1px solid #141e28",
                                paddingTop: 4,
                            }}>
                                <div>
                                    <div style={{ fontSize: 6.5, color: "#6c8496" }}>WR ({k.ops})</div>
                                    <div style={{ fontWeight: "bold", color: "#e6edf3" }}>{fmtNum(k.wr, 1)}%</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: 6.5, color: "#6c8496" }}>PF</div>
                                    <div style={{ fontWeight: "bold", color: k.pf >= 1.5 ? "#00e87a" : "#ffd600" }}>{fmtNum(k.pf, 2)}x</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: 6.5, color: "#6c8496" }}>MAX DD</div>
                                    <div style={{ fontWeight: "bold", color: "#ff6b8b" }}>-R$ {fmtNum(k.maxDdBrl, 0)}</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: 6.5, color: "#6c8496" }}>RET/DD</div>
                                    <div style={{ fontWeight: "bold", color: "#00d4ff" }}>{fmtNum(k.retDd, 2)}x</div>
                                </div>
                            </div>

                            <div style={{ fontSize: 7, color: "#6c8496", lineHeight: 1.2 }}>
                                {cfg.subRule}
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* 3. GRÁFICO PRINCIPAL SVG (CURVAS DAS 6 ESTRATÉGIAS + PORTFÓLIO + MARCO LIVE TRADING + SUBWATER DD) */}
            <div style={{ position: "relative" }}>
                <svg
                    viewBox={`0 0 ${w} ${h}`}
                    style={{
                        width: "100%",
                        height: "auto",
                        display: "block",
                        background: "#05080d",
                        borderRadius: 8,
                        border: "1px solid #1a2530",
                        cursor: "crosshair",
                    }}
                    onMouseMove={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        const relX = ((e.clientX - rect.left) / rect.width) * w;
                        const ratio = (relX - padL) / plotW;
                        const idx = Math.round(ratio * (nPts - 1));
                        if (idx >= 0 && idx < nPts) {
                            setHoverIdx((prev) => (prev === idx ? prev : idx));
                        }
                    }}
                    onMouseLeave={() => setHoverIdx(null)}
                    onClick={() => {
                        if (hoverIdx !== null) {
                            setPinnedIdx(pinnedIdx === hoverIdx ? null : hoverIdx);
                        }
                    }}
                >
                    <defs>
                        <linearGradient id="port4-grad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#00e87a" stopOpacity="0.22" />
                            <stop offset="100%" stopColor="#00e87a" stopOpacity="0.01" />
                        </linearGradient>
                        <linearGradient id="dd4-grad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#ff3860" stopOpacity="0.06" />
                            <stop offset="100%" stopColor="#ff3860" stopOpacity="0.32" />
                        </linearGradient>
                    </defs>

                    {/* Faixa de Fundo do Live Trading (a partir de firstLiveIdx) */}
                    {firstLiveIdx > 0 && (() => {
                        const xLive = toX(firstLiveIdx) - Math.max(3, plotW / Math.max(20, nPts) * 0.45);
                        return (
                            <g>
                                <rect
                                    x={xLive}
                                    y={padT}
                                    width={Math.max(8, padL + plotW - xLive + 6)}
                                    height={plotHEq + plotHDd + 16}
                                    fill="rgba(0, 232, 122, 0.05)"
                                />
                                <line
                                    x1={xLive}
                                    y1={padT}
                                    x2={xLive}
                                    y2={ddTop + plotHDd}
                                    stroke="#00e87a"
                                    strokeWidth="1.5"
                                    strokeDasharray="4,3"
                                />
                                <rect
                                    x={Math.min(padL + plotW - 148, Math.max(padL + 10, xLive - 144))}
                                    y={padT + 3}
                                    width="140"
                                    height="15"
                                    rx="3"
                                    fill="#0c1218"
                                    stroke="#00e87a"
                                    strokeWidth="1"
                                />
                                <text
                                    x={Math.min(padL + plotW - 78, Math.max(padL + 80, xLive - 74))}
                                    y={padT + 13}
                                    fill="#00e87a"
                                    fontSize="8"
                                    fontWeight="bold"
                                    fontFamily="monospace"
                                    textAnchor="middle"
                                >
                                    🟢 LIVE TRADING ({fmtDateShort(portfolioData.live_start_date)})
                                </text>
                            </g>
                        );
                    })()}

                    {/* Linhas Horizontais de Grade (R$) */}
                    {yGridVals.map((yv, gi) => {
                        const yy = toYEq(yv);
                        return (
                            <g key={`yg-${gi}`}>
                                <line x1={padL} y1={yy} x2={padL + plotW} y2={yy} stroke="#111a24" strokeWidth="1" />
                                <text x={padL - 6} y={yy + 3} fill="#6c8496" fontSize="8.5" fontFamily="monospace" textAnchor="end">
                                    {yv >= 0 ? "+" : "-"}R${fmtNum(Math.abs(yv), 0)}
                                </text>
                            </g>
                        );
                    })}

                    {/* Linha Zero (R$ 0) */}
                    <line x1={padL} y1={yZeroEq} x2={padL + plotW} y2={yZeroEq} stroke="#2a3f54" strokeWidth="1.2" strokeDasharray="3,3" />

                    {/* Divisórias Mensais */}
                    {monthTicks.map((mt, mi) => {
                        const xx = toX(mt.idx);
                        return (
                            <g key={`mt-${mi}`}>
                                <line x1={xx} y1={padT} x2={xx} y2={ddTop + plotHDd} stroke="#15202b" strokeWidth="1" strokeDasharray="2,3" />
                                <text x={xx + 4} y={hEq - 2} fill="#6c8496" fontSize="8" fontFamily="monospace" fontWeight="bold">
                                    {mt.label}
                                </text>
                            </g>
                        );
                    })}

                    {/* Área Sombreada do Portfólio Completo */}
                    {visibleCurves.PORTFOLIO && (() => {
                        const ptsStr = visibleSeries.map((pt, i) => `${toX(i).toFixed(1)},${toYEq(pt.PORTFOLIO).toFixed(1)}`).join(" ");
                        const areaStr = `${toX(0).toFixed(1)},${yZeroEq.toFixed(1)} ${ptsStr} ${toX(nPts - 1).toFixed(1)},${yZeroEq.toFixed(1)}`;
                        return <polygon points={areaStr} fill="url(#port4-grad)" />;
                    })()}

                    {/* As 7 Curvas de Capital (6 Estratégias + Portfólio) */}
                    {[...curveConfigs].reverse().map((cfg) => {
                        if (!visibleCurves[cfg.key]) return null;
                        const ptsStr = visibleSeries.map((pt, i) => `${toX(i).toFixed(1)},${toYEq(pt[cfg.key]).toFixed(1)}`).join(" ");
                        const lastPt = visibleSeries[nPts - 1];
                        const yEnd = toYEq(lastPt[cfg.key]);
                        return (
                            <g key={`curve-${cfg.key}`}>
                                <polyline
                                    fill="none"
                                    stroke={cfg.color}
                                    strokeWidth={cfg.strokeW}
                                    points={ptsStr}
                                />
                                {/* Ponto Destacado no Pregão Live */}
                                {visibleSeries.map((pt, i) => (
                                    pt.is_live ? (
                                        <circle
                                            key={`live-dot-${cfg.key}-${i}`}
                                            cx={toX(i)}
                                            cy={toYEq(pt[cfg.key])}
                                            r={cfg.key === "PORTFOLIO" ? "4.5" : "3.2"}
                                            fill={cfg.color}
                                            stroke="#05080d"
                                            strokeWidth="1.2"
                                        />
                                    ) : null
                                ))}
                                {/* Etiqueta de Saldo Final na Direita */}
                                <text
                                    x={padL + plotW + 5}
                                    y={yEnd + 3}
                                    fill={cfg.color}
                                    fontSize={cfg.key === "PORTFOLIO" ? "9.5" : "8"}
                                    fontWeight="bold"
                                    fontFamily="monospace"
                                >
                                    {lastPt[cfg.key] >= 0 ? "+" : "-"}R${fmtNum(Math.abs(lastPt[cfg.key]), 0)}
                                </text>
                            </g>
                        );
                    })}

                    {/* Separador do Painel Subwater Drawdown */}
                    <line x1={padL} y1={ddTop} x2={padL + plotW} y2={ddTop} stroke="#1a2530" strokeWidth="1" />
                    <text x={padL + 6} y={ddTop + 11} fill="#6c8496" fontSize="7.5" fontFamily="monospace" fontWeight="bold">
                        DRAWDOWN SUBWATER DO PORTFÓLIO (MÁX: -R$ {fmtNum(mddPort, 0)})
                    </text>

                    {/* Curva Subwater Drawdown do Portfólio */}
                    {(() => {
                        const ddPts = visibleSeries.map((pt, i) => `${toX(i).toFixed(1)},${toYDd(pt.dd_PORT).toFixed(1)}`).join(" ");
                        const ddArea = `${toX(0).toFixed(1)},${ddTop.toFixed(1)} ${ddPts} ${toX(nPts - 1).toFixed(1)},${ddTop.toFixed(1)}`;
                        return (
                            <g>
                                <polygon points={ddArea} fill="url(#dd4-grad)" />
                                <polyline fill="none" stroke="#ff3860" strokeWidth="1.4" points={ddPts} />
                            </g>
                        );
                    })()}

                    {/* Crosshair do Pregão Selecionado / Hover */}
                    {inspectedPt && (() => {
                        const ix = toX(visibleSeries.indexOf(inspectedPt));
                        return (
                            <g>
                                <line x1={ix} y1={padT} x2={ix} y2={ddTop + plotHDd} stroke="#8ca5b5" strokeWidth="1" strokeDasharray="2,2" />
                                {curveConfigs.map((cfg) => (
                                    visibleCurves[cfg.key] ? (
                                        <circle
                                            key={`hov-${cfg.key}`}
                                            cx={ix}
                                            cy={toYEq(inspectedPt[cfg.key])}
                                            r="3.8"
                                            fill={cfg.color}
                                            stroke="#05080d"
                                            strokeWidth="1.2"
                                        />
                                    ) : null
                                ))}
                            </g>
                        );
                    })()}
                </svg>

                {/* Barra de Inspeção do Pregão sob o Cursor */}
                {inspectedPt && (
                    <div style={{
                        marginTop: 6,
                        background: "#05080d",
                        border: inspectedPt.is_live ? "1px solid #00e87a66" : "1px solid #1a2530",
                        borderRadius: 7,
                        padding: "6px 12px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        flexWrap: "wrap",
                        gap: 8,
                        fontFamily: "monospace",
                        fontSize: 9.5,
                    }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                            <span style={{
                                fontWeight: "bold",
                                color: inspectedPt.is_live ? "#00e87a" : "#ffffff",
                                background: inspectedPt.is_live ? "rgba(0,232,122,0.14)" : "#0c1218",
                                padding: "2px 7px",
                                borderRadius: 4,
                                border: "1px solid #1a2530",
                            }}>
                                {inspectedPt.is_live ? `🟢 LIVE TRADING · ${fmtDateFull(inspectedPt.date)}` : `📅 BT AUDITADO · ${fmtDateFull(inspectedPt.date)}`}
                            </span>
                            <span style={{ color: "#8ca5b5" }}>
                                Dia: <strong style={{ color: inspectedPt.d_PORT >= 0 ? "#00e87a" : "#ff3860" }}>
                                    {inspectedPt.d_PORT >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(inspectedPt.d_PORT), 0)}
                                </strong> ({inspectedPt.ops_total} ops)
                            </span>
                            {onSelectDate && !inspectedPt.isOrigin && (
                                <button
                                    onClick={() => onSelectDate(inspectedPt.is_live ? "" : inspectedPt.date)}
                                    style={{
                                        padding: "2px 8px",
                                        fontSize: 8.5,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        background: "#0c1218",
                                        color: "#00d4ff",
                                        border: "1px solid #00d4ff55",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                    }}
                                >
                                    🔍 Abrir Pregão no Gráfico Acima
                                </button>
                            )}
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                            <span style={{ color: "#00e87a", fontWeight: "bold" }}>
                                🏆 Portfólio: {inspectedPt.PORTFOLIO >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(inspectedPt.PORTFOLIO), 0)}
                            </span>
                            {ALL_11_STRAT_META.filter((m) => visibleCurves[m.id]).map((m) => {
                                const val = Number(inspectedPt[m.id] || 0);
                                return (
                                    <span key={`insp-${m.id}`} style={{ color: m.color }}>
                                        {m.short}: {val >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(val), 0)}
                                    </span>
                                );
                            })}
                        </div>
                    </div>
                )}
            </div>

            {/* 4. RODAPÉ DUPLO: TABELA MENSAL AUDITADA (ESQUERDA) + HISTÓRICO COMPLETO DE TODOS OS TRADES & MONITOR (DIREITA) */}
            <div style={{ display: "grid", gridTemplateColumns: "1.22fr 1.0fr", gap: 12 }}>
                {/* Esquerda: Matriz Mensal das Estratégias Ativas + Portfólio */}
                <div style={{
                    background: "#05080d",
                    border: "1px solid #1a2530",
                    borderRadius: 8,
                    padding: "10px 12px",
                    overflowX: "auto",
                }}>
                    <div style={{ fontSize: 10, fontWeight: "bold", color: "#ffffff", marginBottom: 8, letterSpacing: 0.5 }}>
                        🗓️ RESULTADO MENSAL AUDITADO POR ESTRATÉGIA ATIVA ({effectivePortIds.length} ATIVAS · WIN {winContracts}c · WDO {wdoContracts}c)
                    </div>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "monospace", fontSize: 8.2 }}>
                        <thead>
                            <tr style={{ color: "#6c8496", borderBottom: "1px solid #1a2530", textAlign: "right" }}>
                                <th style={{ textAlign: "left", padding: "4px" }}>MÊS</th>
                                {effectivePortIds.map((sid) => {
                                    const sm = STRAT_META_BY_ID[sid];
                                    return (
                                        <th key={`mh-${sid}`} style={{ padding: "4px 3px", color: sm?.color || "#8ca5b5" }}>
                                            {sm?.short || sid}
                                        </th>
                                    );
                                })}
                                <th style={{ padding: "4px", color: "#00e87a" }}>🏆 PORTFÓLIO</th>
                            </tr>
                        </thead>
                        <tbody>
                            {Object.values(byMonth).map((m) => (
                                <tr
                                    key={m.month}
                                    style={{
                                        borderBottom: "1px solid #111a24",
                                        textAlign: "right",
                                        background: m.is_live ? "rgba(0, 232, 122, 0.06)" : "transparent",
                                    }}
                                >
                                    <td style={{ textAlign: "left", padding: "4px", fontWeight: "bold", color: m.is_live ? "#00e87a" : "#e6edf3" }}>
                                        {m.is_live ? `🟢 ${m.month}` : m.month}
                                    </td>
                                    {effectivePortIds.map((sid) => {
                                        const sm = STRAT_META_BY_ID[sid];
                                        const v = Number(m[sid] || 0);
                                        return (
                                            <td key={`mc-${m.month}-${sid}`} style={{ padding: "4px 3px", color: v >= 0 ? (sm?.color || "#00e87a") : "#ff6b8b" }}>
                                                {v >= 0 ? "+" : "-"}R${fmtNum(Math.abs(v), 0)}
                                            </td>
                                        );
                                    })}
                                    <td style={{ padding: "4px", fontWeight: 900, color: m.PORTFOLIO >= 0 ? "#00e87a" : "#ff3860" }}>
                                        {m.PORTFOLIO >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(m.PORTFOLIO), 0)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Direita: Histórico Completo de Todos os Trades + Trades do Pregão Inspecionado */}
                <div style={{
                    background: "#05080d",
                    border: "1px solid #1a2530",
                    borderRadius: 8,
                    padding: "10px 12px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                        <span style={{ fontSize: 10, fontWeight: "bold", color: "#00e87a", letterSpacing: 0.5 }}>
                            📋 HISTÓRICO AUDITADO DAS {ALL_11_STRAT_META.length} CAMPEÃS ({allHistoricalTrades.length} OPS) & LIVE
                        </span>
                        <div style={{ display: "flex", gap: 4 }}>
                            <button
                                onClick={() => setTradeHistTab("ALL")}
                                style={{
                                    padding: "2px 8px",
                                    fontSize: 8,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                    background: tradeHistTab === "ALL" ? "#00e87a" : "#0c1218",
                                    color: tradeHistTab === "ALL" ? "#04080e" : "#8ca5b5",
                                    border: tradeHistTab === "ALL" ? "1px solid #00e87a" : "1px solid #1a2530",
                                }}
                            >
                                📋 Todas ({allHistoricalTrades.length})
                            </button>
                            <button
                                onClick={() => setTradeHistTab("DAY")}
                                style={{
                                    padding: "2px 8px",
                                    fontSize: 8,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                    background: tradeHistTab === "DAY" ? "#00d4ff" : "#0c1218",
                                    color: tradeHistTab === "DAY" ? "#04080e" : "#8ca5b5",
                                    border: tradeHistTab === "DAY" ? "1px solid #00d4ff" : "1px solid #1a2530",
                                }}
                            >
                                📅 Pregão {fmtDateShort(inspectedPt?.date)} ({((inspectedPt?.trades || []).filter((tr) => PRESET_TOP6_IDS.includes(tr.strategy_id)).length) + ((inspectedPt?.open_trades || []).filter((tr) => PRESET_TOP6_IDS.includes(tr.strategy_id)).length)})
                            </button>
                        </div>
                    </div>

                    {/* Filtro Rápido por Estratégia */}
                    <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                        {[
                            { id: "ALL", label: `Todas (${ALL_11_STRAT_META.length})`, col: "#00e87a" },
                            ...ALL_11_STRAT_META.map((m) => ({ id: m.id, label: m.short, col: m.color })),
                        ].map((sf) => {
                            const active = stratFilter === sf.id;
                            return (
                                <button
                                    key={sf.id}
                                    onClick={() => setStratFilter(sf.id)}
                                    style={{
                                        padding: "2px 5px",
                                        fontSize: 7.5,
                                        fontFamily: "monospace",
                                        fontWeight: "bold",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                        background: active ? `${sf.col}22` : "#0c1218",
                                        color: active ? sf.col : "#7f96a8",
                                        border: active ? `1px solid ${sf.col}` : "1px solid #1a2530",
                                    }}
                                >
                                    {sf.label}
                                </button>
                            );
                        })}
                    </div>

                    {(() => {
                        const dayTrades = (inspectedPt && (inspectedPt.trades?.length > 0 || inspectedPt.open_trades?.length > 0))
                            ? [...(inspectedPt.open_trades || []), ...(inspectedPt.trades || [])].filter((tr) => PRESET_TOP6_IDS.includes(tr.strategy_id))
                            : [...liveOpenTrades, ...liveClosedTrades].filter((tr) => PRESET_TOP6_IDS.includes(tr.strategy_id));
                        const rawList = tradeHistTab === "DAY" ? dayTrades : allHistoricalTrades;
                        const tradesToShow = stratFilter === "ALL"
                            ? rawList.filter((tr) => effectivePortIds.includes(tr.strategy_id))
                            : rawList.filter((tr) => tr.strategy_id === stratFilter);

                        if (tradesToShow.length === 0) {
                            return (
                                <div style={{
                                    padding: "14px 10px",
                                    background: "#0c1218",
                                    borderRadius: 6,
                                    border: "1px dashed #1a2530",
                                    color: "#7f96a8",
                                    fontSize: 9,
                                    fontFamily: "monospace",
                                    textAlign: "center",
                                }}>
                                    Nenhuma operação encontrada para este filtro no pregão selecionado.
                                </div>
                            );
                        }

                        const visibleTradesToShow = tradesToShow.slice(0, maxHistRows);
                        const remainingCount = Math.max(0, tradesToShow.length - visibleTradesToShow.length);

                        return (
                            <div style={{ maxHeight: 195, overflowY: "auto", border: "1px solid #111a24", borderRadius: 6 }}>
                                <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "monospace", fontSize: 8.2 }}>
                                    <thead style={{ position: "sticky", top: 0, background: "#091017", zIndex: 1 }}>
                                        <tr style={{ color: "#6c8496", borderBottom: "1px solid #1a2530", textAlign: "right" }}>
                                            <th style={{ textAlign: "left", padding: "4px" }}>DATA / HORA</th>
                                            <th style={{ textAlign: "left", padding: "4px" }}>ESTRATÉGIA</th>
                                            <th style={{ textAlign: "center", padding: "4px" }}>LADO</th>
                                            <th style={{ padding: "4px" }}>ENTRADA</th>
                                            <th style={{ padding: "4px" }}>PTS</th>
                                            <th style={{ padding: "4px" }}>RESULTADO R$</th>
                                            <th style={{ textAlign: "left", padding: "4px 6px" }}>DESFECHO</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {visibleTradesToShow.map((tr, ti) => {
                                            const mult = tr.asset === "WIN" ? winContracts : wdoContracts;
                                            const brlVal = Number(tr.brl_1c || 0) * mult;
                                            const isOpen = tr.status === "ABERTA";
                                            const sm = STRAT_META_BY_ID[tr.strategy_id];
                                            const sCol = sm?.color || "#a78bfa";
                                            const sName = sm?.shortLabel || tr.strategy_id;
                                            return (
                                                <tr
                                                    key={`tr-${ti}`}
                                                    onClick={() => onSelectDate && tr.date && onSelectDate(tr.date)}
                                                    title="Clique para abrir este pregão e ver a marcação no gráfico acima"
                                                    style={{ borderBottom: "1px solid #111a24", textAlign: "right", cursor: "pointer" }}
                                                >
                                                    <td style={{ textAlign: "left", padding: "3px 4px", color: "#9fb4c4" }}>
                                                        {fmtDateShort(tr.date)} {tr.time}
                                                    </td>
                                                    <td style={{ textAlign: "left", padding: "3px 4px", color: sCol, fontWeight: "bold" }}>
                                                        {sName}
                                                    </td>
                                                    <td style={{ textAlign: "center", padding: "3px 4px", color: tr.direction === "COMPRA" ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                                        {tr.direction}
                                                    </td>
                                                    <td style={{ padding: "3px 4px", color: "#e6edf3" }}>
                                                        {fmtNum(tr.entry_price, tr.asset === "WDO" ? 1 : 0)}
                                                    </td>
                                                    <td style={{ padding: "3px 4px", color: isOpen ? "#ffd600" : (tr.pts >= 0 ? "#00e87a" : "#ff6b8b") }}>
                                                        {fmtNum(tr.pts, tr.asset === "WDO" ? 1 : 0, true)}p
                                                    </td>
                                                    <td style={{ padding: "3px 4px", fontWeight: "bold", color: isOpen ? "#ffd600" : (brlVal >= 0 ? "#00e87a" : "#ff3860") }}>
                                                        {isOpen ? "⏳ ABERTA" : `${brlVal >= 0 ? "+" : "-"}R$ ${fmtNum(Math.abs(brlVal), 0)}`}
                                                    </td>
                                                    <td style={{ textAlign: "left", padding: "3px 6px", color: "#8ca5b5", fontSize: 8 }}>
                                                        {tr.label || (isOpen ? "⏳ EM ABERTO" : "FECHADA")}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                                {remainingCount > 0 && (
                                    <div style={{ padding: "6px", textAlign: "center", background: "#091017", borderTop: "1px solid #1a2530" }}>
                                        <button
                                            onClick={() => setMaxHistRows((prev) => prev + 250)}
                                            style={{
                                                padding: "3px 10px",
                                                fontSize: 8.5,
                                                fontFamily: "monospace",
                                                fontWeight: "bold",
                                                background: "#0c1218",
                                                color: "#00d4ff",
                                                border: "1px solid #00d4ff55",
                                                borderRadius: 4,
                                                cursor: "pointer",
                                            }}
                                        >
                                            Mostrar mais (+250 de {remainingCount} restantes)
                                        </button>
                                    </div>
                                )}
                            </div>
                        );
                    })()}
                </div>
            </div>

            {/* 5. GRÁFICO E MATRIZ DE CORRELAÇÃO DIÁRIA DAS 6 CAMPEÃS */}
            {(() => {
                const sessionPts = fullSeries.slice(1);
                if (sessionPts.length < 5) return null;

                const idsForCorr = effectivePortIds;
                const stratMeta = idsForCorr.map((sid) => {
                    const m = STRAT_META_BY_ID[sid];
                    return { id: sid, dKey: `d_${sid}`, asset: m.asset, name: m.shortLabel, short: m.short, col: m.color };
                });

                const calcPearson = (arrA, arrB) => {
                    const n = arrA.length;
                    if (n < 2) return 0;
                    let sumA = 0, sumB = 0;
                    for (let i = 0; i < n; i++) {
                        sumA += arrA[i];
                        sumB += arrB[i];
                    }
                    const meanA = sumA / n;
                    const meanB = sumB / n;
                    let num = 0, denA = 0, denB = 0;
                    for (let i = 0; i < n; i++) {
                        const da = arrA[i] - meanA;
                        const db = arrB[i] - meanB;
                        num += da * db;
                        denA += da * da;
                        denB += db * db;
                    }
                    const den = Math.sqrt(denA * denB);
                    return den > 1e-9 ? num / den : 0;
                };

                const vectors = {};
                stratMeta.forEach((sm) => {
                    vectors[sm.id] = sessionPts.map((p) => Number(p[sm.dKey] || 0));
                });

                const winDailyVec = sessionPts.map((p) =>
                    stratMeta.filter((s) => s.asset === "WIN").reduce((acc, s) => acc + Number(p[s.dKey] || 0), 0)
                );
                const dolDailyVec = sessionPts.map((p) =>
                    stratMeta.filter((s) => s.asset === "WDO").reduce((acc, s) => acc + Number(p[s.dKey] || 0), 0)
                );
                const corrWinDol = calcPearson(winDailyVec, dolDailyVec);

                const corrMatrix = {};
                const pairsList = [];
                for (let i = 0; i < stratMeta.length; i++) {
                    const a = stratMeta[i];
                    corrMatrix[a.id] = {};
                    for (let j = 0; j < stratMeta.length; j++) {
                        const b = stratMeta[j];
                        const r = i === j ? 1.0 : calcPearson(vectors[a.id], vectors[b.id]);
                        corrMatrix[a.id][b.id] = r;
                        if (j > i) {
                            pairsList.push({
                                key: `${a.id}_${b.id}`,
                                label: `${a.short} × ${b.short}`,
                                fullLabel: `${a.name} × ${b.name}`,
                                colA: a.col,
                                colB: b.col,
                                corr: r,
                            });
                        }
                    }
                }

                pairsList.sort((x, y) => x.corr - y.corr);
                const totalPairs = pairsList.length;
                const avgPairCorr = pairsList.reduce((acc, p) => acc + p.corr, 0) / Math.max(1, totalPairs);
                const negPairsCount = pairsList.filter((p) => p.corr < 0).length;
                const lowCorrPairsCount = pairsList.filter((p) => p.corr <= 0.18).length;

                const getCellStyle = (r, isDiag) => {
                    if (isDiag) {
                        return {
                            bg: "rgba(255, 255, 255, 0.07)",
                            border: "1px solid #2a3f54",
                            text: "#8ca5b5",
                        };
                    }
                    if (r < -0.02) {
                        const alpha = Math.min(0.42, 0.14 + Math.abs(r) * 1.4);
                        return {
                            bg: `rgba(0, 212, 255, ${alpha.toFixed(2)})`,
                            border: "1px solid rgba(0, 212, 255, 0.45)",
                            text: "#67e8f9",
                        };
                    }
                    if (r <= 0.18) {
                        const alpha = Math.min(0.32, 0.10 + Math.abs(r) * 0.8);
                        return {
                            bg: `rgba(0, 232, 122, ${alpha.toFixed(2)})`,
                            border: "1px solid rgba(0, 232, 122, 0.35)",
                            text: "#00e87a",
                        };
                    }
                    if (r <= 0.45) {
                        return {
                            bg: "rgba(255, 214, 0, 0.18)",
                            border: "1px solid rgba(255, 214, 0, 0.40)",
                            text: "#ffd600",
                        };
                    }
                    return {
                        bg: "rgba(255, 107, 139, 0.22)",
                        border: "1px solid rgba(255, 107, 139, 0.45)",
                        text: "#ff6b8b",
                    };
                };

                if (isWallsFlow) {
                    return (
                        <div style={{
                            background: "#05080d",
                            border: "1px solid #1a2530",
                            borderRadius: 8,
                            padding: "9px 14px",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            flexWrap: "wrap",
                            gap: 10,
                            fontFamily: "monospace",
                            fontSize: 9,
                        }}>
                            <span style={{ color: "#ffffff", fontWeight: "bold" }}>
                                ⚖️ SINERGIA & DESCORRELAÇÃO DIÁRIA ({sessionPts.length} PREGÕES)
                            </span>
                            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                                <span style={{ color: "#9fb4c4" }}>
                                    Correlação Pearson <strong style={{ color: "#00e87a" }}>WIN 2L Mix × WDO 1L MidWalls</strong>:{" "}
                                    <strong style={{ color: corrWinDol <= 0.15 ? "#00e87a" : "#00d4ff" }}>
                                        r = {corrWinDol >= 0 ? "+" : ""}{fmtNum(corrWinDol, 2)} (Independentes)
                                    </strong>
                                </span>
                                <span style={{ color: "#6c8496" }}>
                                    Efeito Diversificação: DD cai p/ <strong style={{ color: "#00e87a" }}>-R$ {fmtNum(mddPort, 0)}</strong> ➔ Ret/DD <strong style={{ color: "#00d4ff" }}>{fmtNum(portRetDd, 2)}x</strong>
                                </span>
                            </div>
                        </div>
                    );
                }

                return (
                    <div style={{
                        background: "#05080d",
                        border: "1px solid #1a2530",
                        borderRadius: 8,
                        padding: "12px 14px",
                        display: "flex",
                        flexDirection: "column",
                        gap: 10,
                    }}>
                        {/* Cabeçalho + KPIs de Descorrelação */}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                <span style={{ fontSize: 10.5, fontWeight: "bold", color: "#ffffff", letterSpacing: 0.6 }}>
                                    🧩 MATRIZ & GRÁFICO DE CORRELAÇÃO DIÁRIA DAS {stratMeta.length} CAMPEÃS ({totalPairs} PARES · {sessionPts.length} PREGÕES)
                                </span>
                            </div>

                            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontFamily: "monospace", fontSize: 8.5 }}>
                                <span style={{ background: "#0c1218", border: "1px solid #1a2530", padding: "3px 8px", borderRadius: 5, color: "#9fb4c4" }}>
                                    Bloco WIN × Bloco WDO:{" "}
                                    <strong style={{ color: "#00e87a" }}>
                                        {corrWinDol >= 0 ? "+" : ""}{fmtNum(corrWinDol, 2)} (Independentes)
                                    </strong>
                                </span>
                                <span style={{ background: "#0c1218", border: "1px solid #1a2530", padding: "3px 8px", borderRadius: 5, color: "#9fb4c4" }}>
                                    Correlação Média ({totalPairs} Pares):{" "}
                                    <strong style={{ color: "#00d4ff" }}>
                                        {avgPairCorr >= 0 ? "+" : ""}{fmtNum(avgPairCorr, 2)}
                                    </strong>
                                </span>
                                <span style={{ background: "#0c1218", border: "1px solid #1a2530", padding: "3px 8px", borderRadius: 5, color: "#9fb4c4" }}>
                                    Pares c/ Hedge Negativo:{" "}
                                    <strong style={{ color: "#67e8f9" }}>
                                        {negPairsCount} de {totalPairs} pares
                                    </strong>
                                </span>
                            </div>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "1.18fr 1.04fr", gap: 14, alignItems: "stretch" }}>
                            {/* Esquerda: Heatmap de Correlação de Pearson */}
                            <div style={{
                                background: "#0c1218",
                                border: "1px solid #141e28",
                                borderRadius: 7,
                                padding: "8px 10px",
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                gap: 8,
                                overflowX: "auto",
                            }}>
                                <div style={{ fontSize: 8.5, color: "#8ca5b5", fontWeight: "bold", fontFamily: "monospace" }}>
                                    🔥 MAPA DE CALOR (CORRELAÇÃO DE PEARSON -1,00 A +1,00)
                                </div>
                                <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 2, fontFamily: "monospace", fontSize: 8.2 }}>
                                    <thead>
                                        <tr>
                                            <th style={{ textAlign: "left", padding: "3px 4px", color: "#6c8496", fontSize: 7.2 }}>ESTRATÉGIA</th>
                                            {stratMeta.map((sm) => (
                                                <th key={`ch-${sm.id}`} style={{ textAlign: "center", padding: "3px 2px", color: sm.col, fontSize: 7.2 }}>
                                                    {sm.short}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {stratMeta.map((rowSm, ri) => (
                                            <tr key={`cr-${rowSm.id}`}>
                                                <td style={{ padding: "3px 4px", color: rowSm.col, fontWeight: "bold", whiteSpace: "nowrap", fontSize: 7.6 }}>
                                                    {rowSm.name}
                                                </td>
                                                {stratMeta.map((colSm, ci) => {
                                                    const r = corrMatrix[rowSm.id][colSm.id];
                                                    const isDiag = ri === ci;
                                                    const st = getCellStyle(r, isDiag);
                                                    return (
                                                        <td
                                                            key={`cc-${rowSm.id}-${colSm.id}`}
                                                            title={`${rowSm.name} × ${colSm.name}: Correlação = ${r >= 0 ? "+" : ""}${fmtNum(r, 2)}`}
                                                            style={{
                                                                textAlign: "center",
                                                                padding: "6px 3px",
                                                                borderRadius: 4,
                                                                background: st.bg,
                                                                border: st.border,
                                                                color: st.text,
                                                                fontWeight: isDiag ? "normal" : "bold",
                                                                fontSize: 8.5,
                                                            }}
                                                        >
                                                            {isDiag ? "1,00" : `${r >= 0 ? "+" : ""}${fmtNum(r, 2)}`}
                                                        </td>
                                                    );
                                                })}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 7.5, color: "#6c8496", fontFamily: "monospace", paddingTop: 2 }}>
                                    <span>💠 &lt; 0,00: Hedge Natural (Inversa)</span>
                                    <span>🟢 0,00 a +0,18: Descorrelacionadas (Ideal)</span>
                                    <span>🔴 &gt; +0,50: Alta Sinergia Direcional</span>
                                </div>
                            </div>

                            {/* Direita: Gráfico de Barras Divergentes dos Pares (Menor -> Maior Correlação) */}
                            <div style={{
                                background: "#0c1218",
                                border: "1px solid #141e28",
                                borderRadius: 7,
                                padding: "8px 10px",
                                display: "flex",
                                flexDirection: "column",
                                gap: 5,
                            }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 8.5, color: "#8ca5b5", fontWeight: "bold", fontFamily: "monospace" }}>
                                    <span>📊 RANKING DOS {totalPairs} PARES (DA MENOR À MAIOR CORRELAÇÃO)</span>
                                    <span style={{ fontSize: 7.5, color: "#00e87a" }}>{lowCorrPairsCount} de {totalPairs} pares ≤ +0,18!</span>
                                </div>

                                <div style={{ display: "flex", flexDirection: "column", gap: 3.5, maxHeight: 240, overflowY: "auto", paddingRight: 2 }}>
                                    {pairsList.map((pr) => {
                                        const isNeg = pr.corr < 0;
                                        const isHigh = pr.corr > 0.45;
                                        const barColor = isNeg ? "#00d4ff" : isHigh ? "#ff6b8b" : "#00e87a";
                                        const zeroPct = 24;
                                        const widthPct = pr.corr < 0
                                            ? Math.min(zeroPct, (Math.abs(pr.corr) / 0.25) * zeroPct)
                                            : Math.min(100 - zeroPct, (pr.corr / 0.80) * (100 - zeroPct));
                                        const leftPct = pr.corr < 0 ? (zeroPct - widthPct) : zeroPct;

                                        return (
                                            <div
                                                key={pr.key}
                                                style={{
                                                    display: "grid",
                                                    gridTemplateColumns: "1.25fr 1.75fr 44px",
                                                    alignItems: "center",
                                                    gap: 6,
                                                    fontFamily: "monospace",
                                                    fontSize: 7.8,
                                                }}
                                            >
                                                <div style={{ color: "#c9d8e4", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={pr.fullLabel}>
                                                    {pr.label}
                                                </div>
                                                <div style={{
                                                    position: "relative",
                                                    height: 9,
                                                    background: "#05080d",
                                                    borderRadius: 3,
                                                    border: "1px solid #182430",
                                                    overflow: "hidden",
                                                }}>
                                                    <div style={{
                                                        position: "absolute",
                                                        left: `${zeroPct}%`,
                                                        top: 0,
                                                        bottom: 0,
                                                        width: 1,
                                                        background: "#4a6070",
                                                        zIndex: 2,
                                                    }} />
                                                    <div style={{
                                                        position: "absolute",
                                                        left: `${leftPct.toFixed(1)}%`,
                                                        width: `${Math.max(1.5, widthPct).toFixed(1)}%`,
                                                        top: 1,
                                                        bottom: 1,
                                                        background: barColor,
                                                        borderRadius: 2,
                                                        opacity: 0.85,
                                                    }} />
                                                </div>
                                                <div style={{
                                                    textAlign: "right",
                                                    fontWeight: "bold",
                                                    color: barColor,
                                                }}>
                                                    {pr.corr >= 0 ? "+" : ""}{fmtNum(pr.corr, 2)}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        </div>
                    </div>
                );
            })()}
        </div>
    );
}, (prev, next) => prev.portfolioData === next.portfolioData);

/* ── COMPONENTE DO COCKPIT DE 1 ATIVO (ESQUERDA: FLUXO REAL | DIREITA: A.S.G HUD + CURVA DE CAPITAL) ── */
function SingleAssetCockpitView({ symKey, payload }) {
    const [selectedSigId, setSelectedSigId] = useState(null);
    const [showHistory, setShowHistory] = useState(false);
    const [isCapitalCollapsed, setIsCapitalCollapsed] = useState(() => isWallsFlowLocalhost());

    if (!payload) return null;

    const dec = symKey === "WDO" ? 1 : 0;
    const ca = payload.caminho_a || {};
    const rawSc = ca.signals_scorecard || {};
    const isWallsFlow = isWallsFlowLocalhost();
    const signalsLog = filterSignalsForHost(ca.signals_log || [], isWallsFlow);
    const closedSigs = signalsLog.filter((s) => s && s.is_valid !== null && s.is_valid !== undefined);
    const validSigs = closedSigs.filter((s) => s.is_valid === true);
    const invalidSigs = closedSigs.filter((s) => s.is_valid === false);
    const sc = {
        ...rawSc,
        total_signals: signalsLog.length,
        closed_signals: closedSigs.length,
        valid_signals: validSigs.length,
        invalid_signals: invalidSigs.length,
        open_signals: signalsLog.length - closedSigs.length,
        win_rate_pct: closedSigs.length > 0 ? Math.round((validSigs.length / closedSigs.length) * 1000) / 10 : 0,
    };
    const series = ca.m5_dealer_vs_flow_series || [];
    const flowWindows = ca.flow_windows || [];
    const asgHud = ca.asg_hud || {};
    const radar = payload.walls_radar || {};
    const allWalls = payload.all_walls || [];

    // Resumo rápido do Capital do Dia (lote base 1x: 2L no WIN / 1L no WDO na 5176) para a barra retrátil
    const brlPerPt = symKey === "WDO" ? 10.0 : 0.20;
    const targetRef = Number(sc.target_ref_pts || (symKey === "WDO" ? 10.0 : 250));
    const stopRef = Number(sc.stop_ref_pts || (symKey === "WDO" ? 10.0 : 250));
    let dayNetPts = 0;
    let dayNetBrl = 0;
    signalsLog.forEach((sig) => {
        if (!sig) return;
        const st = String(sig.validation_status || "");
        if (st === "EM_ANDAMENTO") return;
        let tPts = 0;
        if (sig.realized_pts !== undefined && sig.realized_pts !== null) tPts = Number(sig.realized_pts);
        else if (st === "VALIDO_ALVO") tPts = targetRef;
        else if (st === "INVALIDO_STOP") tPts = -stopRef;
        else if (st === "VALIDO_FAVORAVEL") tPts = Number(sig.pnl_30m ?? sig.pnl_15m ?? Math.round(targetRef * 0.45));
        else if (st === "INVALIDO_CONTRA") tPts = Number(sig.pnl_30m ?? sig.pnl_15m ?? -Math.round(stopRef * 0.5));
        dayNetPts += tPts;
        dayNetBrl += (sig.brl_1c !== undefined && sig.brl_1c !== null) ? Number(sig.brl_1c) : (tPts * brlPerPt);
    });
    const drawerCollapsedActive = isWallsFlow && isCapitalCollapsed;
    const lotBaseTag = isWallsFlow ? (symKey === "WIN" ? "2L" : "1L") : "1c";
    const netCol = dayNetBrl >= 0 ? "#00e87a" : "#ff3860";

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{
                display: "grid",
                gridTemplateColumns: drawerCollapsedActive ? "minmax(0, 1fr) 44px" : "2.1fr 1fr",
                gap: drawerCollapsedActive ? 10 : 14,
                alignItems: "stretch",
            }}>
                {/* Esquerda (68% padrão | ~97% modo expandido): Gráfico Preço + Fluxo Smart Money */}
                <FluxoRealAsgChart
                    symKey={symKey}
                    series={series}
                    flowWindows={flowWindows}
                    signalsLog={signalsLog}
                    asgHud={asgHud}
                    wallsRadar={radar}
                    allWalls={allWalls}
                    vwap={payload.vwap}
                    selectedSigId={selectedSigId}
                    wideMode={drawerCollapsedActive}
                    sessionDate={payload.session_date || ca.ref_date || ""}
                    capitalDrawerInfo={isWallsFlow ? {
                        isCollapsed: isCapitalCollapsed,
                        netBrl: dayNetBrl,
                        netPts: dayNetPts,
                        onToggle: () => setIsCapitalCollapsed((v) => !v),
                    } : null}
                    onSelectSignal={(id) => {
                        setSelectedSigId(id);
                        if (id) setShowHistory(true);
                    }}
                />

                {/* Direita: Gaveta Retrátil (44px quando recuada na 5176 | 32% quando aberta) */}
                {drawerCollapsedActive ? (
                    <div
                        onClick={() => setIsCapitalCollapsed(false)}
                        title={`Clique para expandir o Gráfico de Capital e HUD do ${symKey} (${dayNetBrl >= 0 ? "+" : "-"}R$ ${fmtNum(Math.abs(dayNetBrl), 0)} hoje)`}
                        style={{
                            background: "#0c1218",
                            border: "1px solid #1a2530",
                            borderLeft: `2px solid ${netCol}88`,
                            borderRadius: 10,
                            padding: "10px 4px",
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            justifyContent: "space-between",
                            cursor: "pointer",
                            userSelect: "none",
                            transition: "border-color 0.15s ease, background 0.15s ease",
                        }}
                    >
                        <div style={{
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            gap: 4,
                            padding: "4px 5px",
                            borderRadius: 6,
                            background: "rgba(0, 212, 255, 0.10)",
                            border: "1px solid rgba(0, 212, 255, 0.40)",
                            color: "#00d4ff",
                            fontSize: 10,
                            fontFamily: "monospace",
                            fontWeight: 900,
                        }}>
                            <span>◀</span>
                            <span style={{ fontSize: 11 }}>💰</span>
                        </div>

                        <div style={{
                            writingMode: "vertical-rl",
                            transform: "rotate(180deg)",
                            display: "flex",
                            alignItems: "center",
                            gap: 10,
                            fontFamily: "monospace",
                            fontSize: 10.5,
                            letterSpacing: 0.6,
                            whiteSpace: "nowrap",
                            padding: "8px 0",
                        }}>
                            <span style={{ color: "#94a3b8", fontWeight: "bold" }}>
                                CAPITAL {symKey} ({lotBaseTag})
                            </span>
                            <span style={{ color: netCol, fontWeight: 900, fontSize: 12 }}>
                                {dayNetBrl >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(dayNetBrl), 0)} ({fmtNum(dayNetPts, dec, true)}p)
                            </span>
                            <span style={{ color: "#cbd5e1", fontSize: 9.5 }}>
                                {sc.valid_signals || 0}✅ / {sc.invalid_signals || 0}❌ ({fmtNum(sc.win_rate_pct, 0)}%)
                            </span>
                            <span style={{ color: "#00d4ff", fontSize: 9, fontWeight: "bold" }}>
                                ◀ Expandir Capital
                            </span>
                        </div>

                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                setShowHistory((s) => !s);
                            }}
                            title={showHistory ? "Ocultar tabela de sinais do dia" : "Ver tabela de sinais do dia"}
                            style={{
                                padding: "5px 6px",
                                fontSize: 10,
                                fontFamily: "monospace",
                                background: showHistory ? "rgba(0, 212, 255, 0.18)" : "#080d12",
                                border: "1px solid #00d4ff55",
                                color: "#00d4ff",
                                borderRadius: 5,
                                cursor: "pointer",
                            }}
                        >
                            📋
                        </button>
                    </div>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 12, justifyContent: "space-between" }}>
                        <AsgCockpitHud
                            symKey={symKey}
                            payload={payload}
                            asgHud={asgHud}
                            scorecard={sc}
                            showHistory={showHistory}
                            onToggleHistory={() => setShowHistory(s => !s)}
                            onCollapseDrawer={isWallsFlow ? () => setIsCapitalCollapsed(true) : undefined}
                        />
                        <DailyOperationsEquityChart
                            symKey={symKey}
                            signalsLog={signalsLog}
                            scorecard={sc}
                            selectedSigId={selectedSigId}
                            onCollapseDrawer={isWallsFlow ? () => setIsCapitalCollapsed(true) : undefined}
                            onSelectSignal={(id) => {
                                setSelectedSigId(id);
                                if (id) setShowHistory(true);
                            }}
                        />
                    </div>
                )}
            </div>

            {/* Tabela Retrátil de Janelas e Sinais (só aparece se o usuário clicar em "Ver Sinais do Dia") */}
            {showHistory && (
                <div style={{
                    background: "#0c1218",
                    border: "1px solid #1a2530",
                    borderRadius: 8,
                    padding: "10px 14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 10.5, fontWeight: "bold", color: "#c8a444" }}>
                            📋 HISTÓRICO DE SINAIS E JANELAS DE HOJE ({signalsLog.length} sinais emitidos)
                        </span>
                        <button
                            onClick={() => setShowHistory(false)}
                            style={{ background: "transparent", border: "none", color: "#8ca5b5", cursor: "pointer", fontSize: 11 }}
                        >
                            ✕ Fechar
                        </button>
                    </div>
                    <div style={{ maxHeight: 210, overflowY: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 9.5 }}>
                            <thead>
                                <tr style={{ color: "#6b8599", borderBottom: "1px solid #18293a", textAlign: "right" }}>
                                    <th style={{ textAlign: "left", padding: "5px 6px" }}>HORA</th>
                                    <th style={{ textAlign: "left", padding: "5px 6px" }}>DIREÇÃO</th>
                                    <th style={{ padding: "5px 6px" }}>PREÇO</th>
                                    <th style={{ textAlign: "left", padding: "5px 6px" }}>GATILHO</th>
                                    <th style={{ padding: "5px 6px", color: "#00e87a" }}>MÁX A FAVOR</th>
                                    <th style={{ padding: "5px 6px", color: "#ff6b8b" }}>MÁX CONTRA</th>
                                    <th style={{ textAlign: "right", padding: "5px 6px" }}>RESULTADO</th>
                                </tr>
                            </thead>
                            <tbody>
                                {signalsLog.map((sig) => {
                                    const isBuy = sig.dir_num > 0;
                                    const vColor = sig.is_valid === true ? "#00e87a" : sig.is_valid === false ? "#ff3860" : "#f5a623";
                                    return (
                                        <tr
                                            key={sig.id}
                                            onClick={() => setSelectedSigId(sig.id)}
                                            style={{
                                                borderBottom: "1px solid #111c27",
                                                textAlign: "right",
                                                cursor: "pointer",
                                                background: selectedSigId === sig.id ? "rgba(0, 212, 255, 0.12)" : "transparent",
                                            }}
                                        >
                                            <td style={{ textAlign: "left", padding: "5px 6px", fontWeight: "bold", color: "#ffffff" }}>{sig.time}</td>
                                            <td style={{ textAlign: "left", padding: "5px 6px", fontWeight: "bold", color: isBuy ? "#00e87a" : "#ff3860" }}>
                                                {isBuy ? "▲ COMPRA" : "▼ VENDA"}
                                            </td>
                                            <td style={{ padding: "5px 6px", color: "#e6edf3", fontWeight: "bold" }}>{fmtNum(sig.entry_price, dec)}</td>
                                            <td style={{ textAlign: "left", padding: "5px 6px", color: "#c8a444" }}>{sig.type}</td>
                                            <td style={{ padding: "5px 6px", color: "#00e87a", fontWeight: "bold" }}>+{fmtNum(sig.mfe_30m, dec)}p</td>
                                            <td style={{ padding: "5px 6px", color: "#ff6b8b" }}>{fmtNum(sig.mae_30m, dec)}p</td>
                                            <td style={{ padding: "5px 6px", fontWeight: "bold", color: vColor }}>{sig.validation_label}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}

/* ── GRÁFICO COMPACTO AUXILIAR PARA O MODO RAIO-X ───────────────────────────── */
function MiniSvgChart({ series, keys, colors, labels, height = 115 }) {
    if (!series || series.length < 2) {
        return (
            <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#4a6070", fontSize: 10, background: "#0c1218", borderRadius: 6, border: "1px solid #1a2530" }}>
                Aguardando barras M5 da sessão...
            </div>
        );
    }

    const width = 560;
    const padL = 8;
    const padR = 8;
    const padT = 12;
    const padB = 18;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;

    let minVal = 0;
    let maxVal = 0;
    keys.forEach(k => {
        series.forEach(pt => {
            const v = Number(pt[k] || 0);
            if (v < minVal) minVal = v;
            if (v > maxVal) maxVal = v;
        });
    });
    if (maxVal === minVal) {
        maxVal += 1;
        minVal -= 1;
    }
    const range = maxVal - minVal;
    const yZero = padT + plotH - ((0 - minVal) / range) * plotH;

    const makePoints = (k) =>
        series
            .map((pt, idx) => {
                const x = padL + (idx / Math.max(1, series.length - 1)) * plotW;
                const v = Number(pt[k] || 0);
                const y = padT + plotH - ((v - minVal) / range) * plotH;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            })
            .join(" ");

    const firstTime = series[0]?.time || "";
    const midTime = series[Math.floor(series.length / 2)]?.time || "";
    const lastTime = series[series.length - 1]?.time || "";

    return (
        <div style={{ background: "#0c1218", borderRadius: 6, border: "1px solid #1a2530", padding: "6px 8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, flexWrap: "wrap", gap: 8 }}>
                <div style={{ display: "flex", gap: 10 }}>
                    {keys.map((k, idx) => {
                        const lastV = Number(series[series.length - 1]?.[k] || 0);
                        return (
                            <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 9 }}>
                                <span style={{ width: 8, height: 3, background: colors[idx], display: "inline-block", borderRadius: 1 }} />
                                <span style={{ color: "#7f96a8" }}>{labels[idx]}:</span>
                                <span style={{ color: colors[idx], fontWeight: "bold" }}>{fmtNum(lastV, 0, true)}</span>
                            </span>
                        );
                    })}
                </div>
                <span style={{ fontSize: 8, color: "#4a6070" }}>{series.length} barras M5</span>
            </div>
            <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: height, display: "block" }}>
                <line x1={padL} y1={yZero} x2={width - padR} y2={yZero} stroke="#1f3140" strokeDasharray="3,3" strokeWidth="1" />
                {keys.map((k, idx) => (
                    <polyline
                        key={k}
                        fill="none"
                        stroke={colors[idx]}
                        strokeWidth={idx === 0 ? "2.2" : "1.5"}
                        points={makePoints(k)}
                    />
                ))}
                <text x={padL + 2} y={height - 3} fill="#4a6070" fontSize="9" fontFamily="monospace">{firstTime}</text>
                <text x={width / 2 - 14} y={height - 3} fill="#4a6070" fontSize="9" fontFamily="monospace">{midTime}</text>
                <text x={width - padR - 28} y={height - 3} fill="#4a6070" fontSize="9" fontFamily="monospace">{lastTime}</text>
            </svg>
        </div>
    );
}

/* ── CARD DETALHADO DE RAIO-X (CORRETORAS PROFIT, JANELAS E ESCADA DE WALLS) ── */
function RaioXAssetCard({ symKey, payload }) {
    if (!payload) return null;
    const dec = symKey === "WDO" ? 1 : 0;
    const ca = payload.caminho_a || {};
    const comp = payload.flow_compass || {};
    const wins = comp.windows || {};
    const tot = payload.session_totals || {};
    const radar = payload.walls_radar || {};
    const supWalls = radar.support_walls || [];
    const resWalls = [...(radar.resistance_walls || [])].reverse();

    return (
        <div style={{
            flex: 1,
            minWidth: 460,
            background: "#0c1218",
            border: "1px solid #1a2530",
            borderRadius: 8,
            padding: 12,
            display: "flex",
            flexDirection: "column",
            gap: 10,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #162433", paddingBottom: 8 }}>
                <span style={{ fontSize: 13, fontWeight: "bold", color: symKey === "WIN" ? "#00d4ff" : "#c8a444" }}>
                    🔬 RAIO-X DE MICROESTRUTURA · {symKey} ({payload.active_contract})
                </span>
                <span style={{ fontSize: 9, color: "#00e87a", background: "rgba(0,232,122,0.12)", padding: "2px 8px", borderRadius: 4, border: "1px solid #00e87a44" }}>
                    {payload.source}
                </span>
            </div>

            {/* Tabela de Janelas Temporais (1m, 5m, 15m, 60m, Sessão) */}
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 9 }}>
                <thead>
                    <tr style={{ color: "#5c7487", borderBottom: "1px solid #16232f", textAlign: "right" }}>
                        <th style={{ textAlign: "left", padding: "4px" }}>JANELA</th>
                        <th style={{ padding: "4px" }}>DELTA TOTAL</th>
                        <th style={{ padding: "4px" }}>LOTE GRANDE ({symKey === "WIN" ? "≥50L" : "≥20L"})</th>
                        <th style={{ padding: "4px" }}>VAREJO</th>
                        <th style={{ padding: "4px" }}>DESEQUILÍBRIO</th>
                        <th style={{ textAlign: "right", padding: "4px" }}>ABSORÇÃO</th>
                    </tr>
                </thead>
                <tbody>
                    {["1m", "5m", "15m", "60m"].map(wk => {
                        const w = wins[wk] || {};
                        return (
                            <tr key={wk} style={{ borderBottom: "1px solid #111b24", textAlign: "right" }}>
                                <td style={{ textAlign: "left", padding: "4px", fontWeight: "bold", color: "#9fb4c4" }}>{wk}</td>
                                <td style={{ padding: "4px", color: w.delta >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>{fmtNum(w.delta, 0, true)}</td>
                                <td style={{ padding: "4px", color: w.inst_delta >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                                <td style={{ padding: "4px", color: w.ret_delta >= 0 ? "#00d4ff" : "#f5a623" }}>{fmtNum(w.ret_delta, 0, true)}</td>
                                <td style={{ padding: "4px", color: "#b1c4d4" }}>{fmtNum(w.imbalance_pct, 1, true)}%</td>
                                <td style={{ padding: "4px", fontSize: 8.5, color: String(w.absorption_state || "").includes("ABSORCAO") ? "#c8a444" : "#566d7e" }}>
                                    {w.absorption_state || "NEUTRO"}
                                </td>
                            </tr>
                        );
                    })}
                    <tr style={{ textAlign: "right", background: "#0c1218", fontWeight: "bold" }}>
                        <td style={{ textAlign: "left", padding: "5px 4px", color: "#c8a444" }}>SESSÃO</td>
                        <td style={{ padding: "5px 4px", color: tot.total_delta >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(tot.total_delta, 0, true)}</td>
                        <td style={{ padding: "5px 4px", color: tot.inst_delta >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(tot.inst_delta, 0, true)}</td>
                        <td style={{ padding: "5px 4px", color: tot.retail_delta >= 0 ? "#00d4ff" : "#f5a623" }}>{fmtNum(tot.retail_delta, 0, true)}</td>
                        <td style={{ padding: "5px 4px", color: "#b1c4d4" }}>RLP: {fmtNum(tot.rlp_vol, 0)}L</td>
                        <td style={{ padding: "5px 4px", fontSize: 8.5, color: "#8ca5b5" }}>{fmtNum(tot.total_deals, 0)} negócios</td>
                    </tr>
                </tbody>
            </table>

            {/* Top Compradores vs Top Vendedores no Profit */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div style={{ background: "#0c1218", padding: "7px 9px", borderRadius: 5, border: "1px solid #1a2530" }}>
                    <div style={{ fontSize: 8.5, color: "#00e87a", fontWeight: "bold", marginBottom: 4 }}>🏦 TOP COMPRADORES LÍQUIDOS (PROFIT)</div>
                    {(payload.top_buyers || []).slice(0, 5).map(b => (
                        <div key={b.broker} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, padding: "2px 0", borderBottom: "1px solid #1a2530" }}>
                            <span style={{ color: b.is_institutional ? "#ffffff" : "#8ca5b5", fontWeight: b.is_institutional ? "bold" : "normal" }}>
                                {b.broker} {b.is_institutional ? "🏦" : ""}
                            </span>
                            <span style={{ color: "#00e87a", fontFamily: "monospace" }}>
                                +{fmtNum(b.net, 0)} <span style={{ color: "#657d8f", fontSize: 8 }}>(Agr:{fmtNum((b.aggr_buy || 0) - (b.aggr_sell || 0), 0, true)} | Pas:{fmtNum((b.passive_buy || 0) - (b.passive_sell || 0), 0, true)})</span>
                            </span>
                        </div>
                    ))}
                </div>
                <div style={{ background: "#0c1218", padding: "7px 9px", borderRadius: 5, border: "1px solid #1a2530" }}>
                    <div style={{ fontSize: 8.5, color: "#ff3860", fontWeight: "bold", marginBottom: 4 }}>🏦 TOP VENDEDORES LÍQUIDOS (PROFIT)</div>
                    {(payload.top_sellers || []).slice(0, 5).map(b => (
                        <div key={b.broker} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, padding: "2px 0", borderBottom: "1px solid #1a2530" }}>
                            <span style={{ color: b.is_institutional ? "#ffffff" : "#8ca5b5", fontWeight: b.is_institutional ? "bold" : "normal" }}>
                                {b.broker} {b.is_institutional ? "🏦" : ""}
                            </span>
                            <span style={{ color: "#ff3860", fontFamily: "monospace" }}>
                                {fmtNum(b.net, 0)} <span style={{ color: "#657d8f", fontSize: 8 }}>(Agr:{fmtNum((b.aggr_buy || 0) - (b.aggr_sell || 0), 0, true)} | Pas:{fmtNum((b.passive_buy || 0) - (b.passive_sell || 0), 0, true)})</span>
                            </span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Escada Completa de 6 MagicWalls Próximas */}
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 8.5 }}>
                <thead>
                    <tr style={{ color: "#5c7487", borderBottom: "1px solid #16232f", textAlign: "right" }}>
                        <th style={{ textAlign: "left", padding: "3px 4px" }}>PAREDE</th>
                        <th style={{ padding: "3px 4px" }}>PREÇO</th>
                        <th style={{ padding: "3px 4px" }}>DIST.</th>
                        {isWallsFlowLocalhost() ? (
                            <>
                                <th style={{ padding: "3px 4px" }}>🏦 INST (AGR / PAS)</th>
                                <th style={{ padding: "3px 4px" }}>🧑‍💻 VAR</th>
                                <th style={{ padding: "3px 4px" }}>⚡HFT / 🔄RLP</th>
                                <th style={{ textAlign: "right", padding: "3px 4px" }}>ASSINATURA PROFIT 4-PLAYERS</th>
                            </>
                        ) : (
                            <>
                                <th style={{ padding: "3px 4px" }}>GEX</th>
                                <th style={{ padding: "3px 4px" }}>DELTA INST NA LINHA</th>
                                <th style={{ padding: "3px 4px" }}>STATUS</th>
                            </>
                        )}
                    </tr>
                </thead>
                <tbody>
                    {resWalls.map((w, i) => {
                        const topB = Array.isArray(w.top_wall_brokers) && w.top_wall_brokers.length > 0
                            ? w.top_wall_brokers.slice(0, 2).map(b => `${b.broker}(${b.net >= 0 ? "+" : ""}${Math.round(b.net)})`).join(" ")
                            : "";
                        return (
                            <tr key={`r-${i}`} style={{ borderBottom: "1px solid #111b24", textAlign: "right" }}>
                                <td style={{ textAlign: "left", padding: "3px 4px", color: "#ff6b8b", fontWeight: "bold" }}>▲ RES · {w.type}</td>
                                <td style={{ padding: "3px 4px", color: "#e6edf3", fontWeight: "bold" }}>{fmtNum(w.price, dec)}</td>
                                <td style={{ padding: "3px 4px", color: "#8ca5b5" }}>{fmtNum(w.dist_pts, dec, true)}p</td>
                                {isWallsFlowLocalhost() ? (
                                    <>
                                        <td style={{ padding: "3px 4px", color: (w.inst_aggr_delta ?? w.inst_delta ?? 0) >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                            {fmtNum(w.inst_aggr_delta ?? w.inst_delta ?? 0, 0, true)} / <span style={{ color: (w.inst_pass_delta ?? 0) >= 0 ? "#38ef94" : "#fb7185" }}>{fmtNum(w.inst_pass_delta ?? 0, 0, true)}</span>
                                        </td>
                                        <td style={{ padding: "3px 4px", color: (w.ret_delta ?? 0) >= 0 ? "#38bdf8" : "#f59e0b" }}>{fmtNum(w.ret_delta ?? 0, 0, true)}</td>
                                        <td style={{ padding: "3px 4px", color: "#a78bfa" }} title={`Giro Bruto HFT: ${fmtNum(w.hft_churn_pct ?? 0, 0)}% | Participação RLP: ${fmtNum(w.rlp_share_pct ?? w.rlp_pct ?? 0, 0)}%`}>
                                            {fmtNum(w.hft_delta ?? 0, 0, true)} / <span style={{ color: "#fbbf24" }}>{fmtNum(w.rlp_delta ?? Math.round(-Number(w.ret_delta ?? 0) * (Number(w.rlp_share_pct ?? w.rlp_pct ?? 0) / 100.0)), 0, true)}</span>
                                        </td>
                                        <td style={{ padding: "3px 4px", color: "#9fb4c4", fontSize: 8 }}>
                                            {w.player_verdict || w.status} {topB ? <span style={{ color: "#c8a444" }}>({topB})</span> : null}
                                        </td>
                                    </>
                                ) : (
                                    <>
                                        <td style={{ padding: "3px 4px", color: "#00d4ff" }}>{w.gex_formatted || "—"}</td>
                                        <td style={{ padding: "3px 4px", color: (w.inst_delta || 0) >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                                        <td style={{ padding: "3px 4px", color: "#9fb4c4" }}>{w.status}</td>
                                    </>
                                )}
                            </tr>
                        );
                    })}
                    <tr style={{ background: "rgba(0, 212, 255, 0.12)", textAlign: "center", fontWeight: "bold" }}>
                        <td colSpan={isWallsFlowLocalhost() ? 7 : 6} style={{ padding: "4px", color: "#00d4ff" }}>
                            ◄ PREÇO SPOT ATUAL: {fmtNum(payload.last_price, dec)} (VWAP: {fmtNum(payload.vwap, dec)}) ►
                        </td>
                    </tr>
                    {supWalls.map((w, i) => {
                        const topB = Array.isArray(w.top_wall_brokers) && w.top_wall_brokers.length > 0
                            ? w.top_wall_brokers.slice(0, 2).map(b => `${b.broker}(${b.net >= 0 ? "+" : ""}${Math.round(b.net)})`).join(" ")
                            : "";
                        return (
                            <tr key={`s-${i}`} style={{ borderBottom: "1px solid #111b24", textAlign: "right" }}>
                                <td style={{ textAlign: "left", padding: "3px 4px", color: "#00e87a", fontWeight: "bold" }}>▼ SUP · {w.type}</td>
                                <td style={{ padding: "3px 4px", color: "#e6edf3", fontWeight: "bold" }}>{fmtNum(w.price, dec)}</td>
                                <td style={{ padding: "3px 4px", color: "#8ca5b5" }}>{fmtNum(w.dist_pts, dec, true)}p</td>
                                {isWallsFlowLocalhost() ? (
                                    <>
                                        <td style={{ padding: "3px 4px", color: (w.inst_aggr_delta ?? w.inst_delta ?? 0) >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                            {fmtNum(w.inst_aggr_delta ?? w.inst_delta ?? 0, 0, true)} / <span style={{ color: (w.inst_pass_delta ?? 0) >= 0 ? "#38ef94" : "#fb7185" }}>{fmtNum(w.inst_pass_delta ?? 0, 0, true)}</span>
                                        </td>
                                        <td style={{ padding: "3px 4px", color: (w.ret_delta ?? 0) >= 0 ? "#38bdf8" : "#f59e0b" }}>{fmtNum(w.ret_delta ?? 0, 0, true)}</td>
                                        <td style={{ padding: "3px 4px", color: "#a78bfa" }} title={`Giro Bruto HFT: ${fmtNum(w.hft_churn_pct ?? 0, 0)}% | Participação RLP: ${fmtNum(w.rlp_share_pct ?? w.rlp_pct ?? 0, 0)}%`}>
                                            {fmtNum(w.hft_delta ?? 0, 0, true)} / <span style={{ color: "#fbbf24" }}>{fmtNum(w.rlp_delta ?? Math.round(-Number(w.ret_delta ?? 0) * (Number(w.rlp_share_pct ?? w.rlp_pct ?? 0) / 100.0)), 0, true)}</span>
                                        </td>
                                        <td style={{ padding: "3px 4px", color: "#9fb4c4", fontSize: 8 }}>
                                            {w.player_verdict || w.status} {topB ? <span style={{ color: "#c8a444" }}>({topB})</span> : null}
                                        </td>
                                    </>
                                ) : (
                                    <>
                                        <td style={{ padding: "3px 4px", color: "#00d4ff" }}>{w.gex_formatted || "—"}</td>
                                        <td style={{ padding: "3px 4px", color: (w.inst_delta || 0) >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                                        <td style={{ padding: "3px 4px", color: "#9fb4c4" }}>{w.status}</td>
                                    </>
                                )}
                            </tr>
                        );
                    })}
                </tbody>
            </table>

            {/* Gráfico CVD Institucional vs Varejo vs Dealers (ou 4-Players em Lotes no 5176) */}
            <MiniSvgChart
                series={ca.m5_dealer_vs_flow_series || []}
                keys={isWallsFlowLocalhost()
                    ? ["cvd_inst_aggr", "cvd_inst_pass", "cvd_retail", "cvd_hft", "cvd_rlp_delta"]
                    : ["cvd_inst", "cum_dealer_hedge", "cvd_retail"]}
                colors={isWallsFlowLocalhost()
                    ? ["#00e87a", "#38ef94", "#38bdf8", "#a78bfa", "#fbbf24"]
                    : ["#00e87a", "#c8a444", "#00d4ff"]}
                labels={isWallsFlowLocalhost()
                    ? ["🏦 CVD Inst Agressor (L)", "🛡️ CVD Inst Passivo (L)", "🧑‍💻 CVD Varejo (L)", "⚡ CVD HFT (L)", "🔄 CVD RLP (L)"]
                    : ["CVD Institucional", "Hedge Acum. Dealers (GEX)", "CVD Varejo"]}
                height={110}
            />
        </div>
    );
}

/* ── COMPONENTE PRINCIPAL EXPORTADO ────────────────────────────────────────── */
function IntradayCompassPanel({ compassData, mode = "COCKPIT", onChangeMode, selectedDate = "", onSelectDate }) {
    const [selectedAsset, setSelectedAsset] = useState(() => (isWallsFlowLocalhost() ? "DUAL" : "WIN")); // "WIN" | "WDO" | "DUAL"

    if (!compassData || !compassData.WIN) {
        return (
            <div style={{
                background: "#0c1218",
                border: "1px solid #1a2530",
                borderRadius: 8,
                padding: 20,
                color: "#8ca5b5",
                fontSize: 12,
                textAlign: "center",
            }}>
                Inicializando Cockpit Operacional (Fluxo Real + A.S.G HUD + Radar Pro)...
            </div>
        );
    }

    const winP = compassData.WIN;
    const wdoP = compassData.WDO;
    const cb = compassData.caminho_b || winP?.caminho_b || {};
    const optComp = cb.options_compass || {};
    const volSurf = cb.volatility_surface || {};
    const bova = cb.bova11 || {};

    const availableDates = compassData.available_dates || [];
    const todayDateStr = availableDates[0] || "";
    const yesterdayDateStr = availableDates.length > 1 ? availableDates[1] : "2026-10-27";
    const activeDate = selectedDate || "";
    const isHistView = Boolean(activeDate && activeDate !== todayDateStr) || Boolean(compassData.is_historical);

    const fmtDateShort = (dStr) => {
        if (!dStr || !dStr.includes("-")) return dStr;
        const [, m, d] = dStr.split("-");
        return `${d}/${m}`;
    };
    const fmtDateFull = (dStr) => {
        if (!dStr || !dStr.includes("-")) return dStr;
        const [y, m, d] = dStr.split("-");
        return `${d}/${m}/${y}`;
    };

    const handleDatePick = (dStr) => {
        if (onSelectDate) {
            onSelectDate(dStr === todayDateStr ? "" : dStr);
        }
    };

    // Cartão Seletor de Ativo no Topo com Semáforo Instantâneo (COMPRA / VENDA / NEUTRALIZADO)
    const renderAssetSelectorButton = (symKey, p) => {
        if (!p) return null;
        const isSel = selectedAsset === symKey;
        const dec = symKey === "WDO" ? 1 : 0;
        const ca = p.caminho_a || {};
        const hud = ca.asg_hud || {};
        const cmd = hud.command || "NEUTRALIZADO";
        const cmdColor = cmd === "COMPRA" ? "#00e87a" : cmd === "VENDA" ? "#ff3860" : "#00d4ff";
        const accent = symKey === "WIN" ? "#00d4ff" : "#c8a444";

        return (
            <div
                key={symKey}
                onClick={() => setSelectedAsset(symKey)}
                style={{
                    flex: 1,
                    minWidth: 280,
                    background: "#0c1218",
                    border: isSel ? `2px solid ${accent}` : "1px solid #1a2530",
                    borderRadius: 10,
                    padding: "9px 14px",
                    cursor: "pointer",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 10,
                    transition: "all 0.2s ease",
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{
                        fontSize: 12,
                        fontWeight: "bold",
                        color: isSel ? "#05080d" : accent,
                        background: isSel ? accent : "#0c1218",
                        border: `1px solid ${accent}`,
                        padding: "4px 10px",
                        borderRadius: 5,
                    }}>
                        {symKey === "WIN" ? "🇧🇷 ÍNDICE" : "💵 DÓLAR"} · {p.active_contract}
                    </span>
                    <div>
                        <div style={{ fontSize: 19, fontWeight: "bold", color: "#ffffff", lineHeight: 1.1 }}>
                            {fmtNum(p.last_price, dec)}
                        </div>
                        <div style={{ fontSize: 8.5, color: "#7f96a8" }}>
                            VWAP: {fmtNum(p.vwap, dec)}
                        </div>
                    </div>
                </div>

                {/* Semáforo Gigante Direto na Aba do Ativo */}
                <div style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    background: "#0c1218",
                    border: `1.5px solid ${cmdColor}`,
                    padding: "5px 12px",
                    borderRadius: 7,
                }}>
                    <span style={{ fontSize: 14, fontWeight: 900, color: cmdColor }}>
                        {cmd === "COMPRA" ? "▲ COMPRAR" : cmd === "VENDA" ? "▼ VENDER" : "❖ NEUTRO"}
                    </span>
                </div>
            </div>
        );
    };

    const isWallsFlowHost = isWallsFlowLocalhost();

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* ── FAIXA IDENTIFICADORA DO LOCALHOST (5174 MT5 vs 5176 FLUXO NAS WALLS) ── */}
            <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 8,
                background: isWallsFlowHost ? "rgba(0, 232, 122, 0.08)" : "rgba(0, 212, 255, 0.07)",
                border: isWallsFlowHost ? "1px solid rgba(0, 232, 122, 0.40)" : "1px solid rgba(0, 212, 255, 0.35)",
                borderRadius: 8,
                padding: "6px 14px",
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{
                        fontSize: 10,
                        fontFamily: "monospace",
                        fontWeight: 900,
                        color: isWallsFlowHost ? "#00e87a" : "#00d4ff",
                        background: "#05080d",
                        padding: "3px 9px",
                        borderRadius: 4,
                        border: isWallsFlowHost ? "1px solid #00e87a66" : "1px solid #00d4ff66",
                    }}>
                        {isWallsFlowHost
                            ? "🎯 LOCALHOST 5176 · SNIPER DIVERGÊNCIA F1➔F2 / T1➔T2 NA WALL (BASE: 2c WIN MIX + 1c WDO MIDWALL)"
                            : "🤖 LOCALHOST 5174 · PROPOSTA A ⭐ (TOP 8 ELITE M5 C/ FLUXO: 5 WIN + 3 WDO)"}
                    </span>
                    <span style={{ fontSize: 9.5, color: "#c9d8e4", fontFamily: "monospace" }}>
                        {isWallsFlowHost
                            ? "Carteira Sniper Base: 🇧🇷 WIN 2c Mix [s/ 12h · Meta +R$ 180] (+R$ 3.281 · WR 69,9% · PF 1,87) + 💵 WDO 1c MidWall [s/ 11h NY · Meta +R$ 120] (+R$ 4.155 · WR 65,2% · PF 2,02) ➔ Total +R$ 7.436 · DD R$ 524 · Ret/DD 14,2 (10/11 M+) · corrigido (causal)"
                            : "Setups Ativos: EST-04 [15_NR_IGN] · EST-07 [16_NR_DIV] · EST-13 [11_SHIELD] · EST-14/WDO-07 [12_NR_TRAP] · EST-15 [14_NR_SQUEEZE] · WDO-01/05 [13_NR_ABS] (+R$ 33.046 · DD R$ 1.170 · Ret/DD 28,24x)"}
                    </span>
                </div>
                <a
                    href={isWallsFlowHost ? "http://localhost:5174" : "http://localhost:5176"}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                        fontSize: 9,
                        fontFamily: "monospace",
                        fontWeight: "bold",
                        color: isWallsFlowHost ? "#00d4ff" : "#00e87a",
                        background: "#05080d",
                        border: isWallsFlowHost ? "1px solid #00d4ff66" : "1px solid #00e87a66",
                        padding: "4px 10px",
                        borderRadius: 5,
                        textDecoration: "none",
                    }}
                >
                    {isWallsFlowHost
                        ? "↗ Abrir Localhost 5174 (Operações via MT5)"
                        : "↗ Abrir Localhost 5176 (Divergência na Wall · Opção 2)"}
                </a>
            </div>

            {/* ── SELETOR RÁPIDO DE ATIVO E DE PREGÃO NO TOPO (WINZ26 vs WDOX26 | HOJE vs ONTEM) ── */}
            {mode === "COCKPIT" && (
                <div style={{ display: "flex", gap: 10, alignItems: "stretch", flexWrap: "wrap" }}>
                    {renderAssetSelectorButton("WIN", winP)}
                    {renderAssetSelectorButton("WDO", wdoP)}
                    <button
                        onClick={() => setSelectedAsset(selectedAsset === "DUAL" ? "WIN" : "DUAL")}
                        style={{
                            padding: "0 14px",
                            fontSize: 10,
                            fontFamily: "monospace",
                            fontWeight: "bold",
                            background: "#0c1218",
                            border: selectedAsset === "DUAL" ? "2px solid #00e87a" : "1px solid #1a2530",
                            color: selectedAsset === "DUAL" ? "#00e87a" : "#8ca5b5",
                            borderRadius: 10,
                            cursor: "pointer",
                        }}
                    >
                        ⚖️ {selectedAsset === "DUAL" ? "Visão Dupla Ativa" : "Ver WIN + WDO Juntos"}
                    </button>

                    {/* Seletor de Pregão: HOJE (AO VIVO) | ONTEM | Outros Dias */}
                    <div style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        background: "#0c1218",
                        border: isHistView ? "2px solid #d4af37" : "1px solid #1a2530",
                        borderRadius: 10,
                        padding: "6px 10px",
                    }}>
                        <span style={{ fontSize: 9, color: "#7f96a8", fontWeight: "bold", letterSpacing: 0.5 }}>
                            📅 PREGÃO:
                        </span>
                        <button
                            onClick={() => handleDatePick("")}
                            style={{
                                padding: "5px 10px",
                                fontSize: 9.5,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                borderRadius: 6,
                                cursor: "pointer",
                                border: !isHistView ? "1.5px solid #00e87a" : "1px solid #1a2530",
                                background: "#0c1218",
                                color: !isHistView ? "#00e87a" : "#8ca5b5",
                            }}
                        >
                            🟢 HOJE {todayDateStr ? `(${fmtDateShort(todayDateStr)})` : ""}
                        </button>
                        {yesterdayDateStr && (
                            <button
                                onClick={() => handleDatePick(yesterdayDateStr)}
                                style={{
                                    padding: "5px 10px",
                                    fontSize: 9.5,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    borderRadius: 6,
                                    cursor: "pointer",
                                    border: activeDate === yesterdayDateStr ? "1.5px solid #d4af37" : "1px solid #1a2530",
                                    background: "#0c1218",
                                    color: activeDate === yesterdayDateStr ? "#ffd700" : "#c8a444",
                                }}
                            >
                                ⏪ ONTEM ({fmtDateShort(yesterdayDateStr)})
                            </button>
                        )}
                        {availableDates.length > 2 && (
                            <select
                                value={activeDate || todayDateStr}
                                onChange={(e) => handleDatePick(e.target.value)}
                                style={{
                                    padding: "4px 8px",
                                    fontSize: 9.5,
                                    fontFamily: "monospace",
                                    background: "#0c1218",
                                    border: "1px solid #1a2530",
                                    borderRadius: 6,
                                    color: "#9fb4c4",
                                    cursor: "pointer",
                                    outline: "none",
                                }}
                            >
                                {availableDates.map((d, idx) => (
                                    <option key={d} value={d}>
                                        {idx === 0 ? `Hoje (${fmtDateShort(d)})` : idx === 1 ? `Ontem (${fmtDateShort(d)})` : fmtDateFull(d)}
                                    </option>
                                ))}
                            </select>
                        )}
                    </div>
                </div>
            )}

            {/* Banner quando estiver visualizando o dia anterior ou histórico */}
            {isHistView && (
                <div style={{
                    background: "rgba(212, 175, 55, 0.12)",
                    border: "1px solid rgba(212, 175, 55, 0.45)",
                    borderRadius: 8,
                    padding: "6px 14px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: 8,
                }}>
                    <span style={{ fontSize: 10, color: "#ffd700", fontWeight: "bold" }}>
                        ⏪ MODO REPLAY HISTÓRICO · Pregão Completo de {fmtDateFull(compassData.selected_date || activeDate)} (09:00 às 18:30 · Walls GEX + Fluxo M5 + Operações)
                    </span>
                    <button
                        onClick={() => handleDatePick("")}
                        style={{
                            padding: "4px 12px",
                            fontSize: 9.5,
                            fontFamily: "monospace",
                            fontWeight: "bold",
                            background: "rgba(0, 232, 122, 0.18)",
                            border: "1px solid #00e87a",
                            borderRadius: 6,
                            color: "#00e87a",
                            cursor: "pointer",
                        }}
                    >
                        🟢 VOLTAR PARA HOJE (AO VIVO)
                    </button>
                </div>
            )}

            {/* ── MODO 1: COCKPIT OPERACIONAL (FLUXO REAL + A.S.G HUD) ──────────── */}
            {mode === "COCKPIT" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    {selectedAsset === "DUAL" ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                            <CombinedPortfolioDayCard winPayload={winP} wdoPayload={wdoP} />
                            <SingleAssetCockpitView symKey="WIN" payload={winP} />
                            <SingleAssetCockpitView symKey="WDO" payload={wdoP} />
                        </div>
                    ) : (
                        <SingleAssetCockpitView
                            symKey={selectedAsset}
                            payload={selectedAsset === "WIN" ? winP : wdoP}
                        />
                    )}
                    <Portfolio4SistematicasPanel
                        portfolioData={compassData?.portfolio_4_sistematicas}
                        winPayload={winP}
                        wdoPayload={wdoP}
                        onSelectDate={handleDatePick}
                    />
                </div>
            )}

            {/* ── MODO 2: RAIO-X DE DADOS (TABELAS COMPLETAS PROFIT + GRADE OPÇÕES) ── */}
            {mode === "RAIO_X" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                        <RaioXAssetCard symKey="WIN" payload={winP} />
                        <RaioXAssetCard symKey="WDO" payload={wdoP} />
                    </div>

                    {/* Grade Completa de Opções BOVA11 */}
                    {cb && cb.ok && (
                        <div style={{
                            background: "#0c1218",
                            border: "1px solid #1a2530",
                            borderRadius: 8,
                            padding: 12,
                            display: "flex",
                            flexDirection: "column",
                            gap: 10,
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, borderBottom: "1px solid #16232f", paddingBottom: 8 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                    <span style={{
                                        fontSize: 11,
                                        fontWeight: "bold",
                                        color: "#00e87a",
                                        background: "rgba(0,232,122,0.12)",
                                        border: "1px solid #00e87a44",
                                        padding: "3px 8px",
                                        borderRadius: 4,
                                    }}>
                                        🎯 RADAR AO VIVO DA GRADE DE OPÇÕES (BOVA11 → WIN)
                                    </span>
                                    <span style={{ fontSize: 11, color: "#e6edf3", fontWeight: "bold" }}>
                                        BOVA11 Spot: R$ {fmtNum(bova.spot, 2)} ({fmtNum(bova.change_pct, 2, true)}%)
                                    </span>
                                    <span style={{ fontSize: 9, color: "#7f96a8" }}>
                                        Fator WIN/BOVA11: <strong>{fmtNum(bova.win_ibov_ratio, 1)}x</strong> · {optComp.monitored_series_count} séries líquidas
                                    </span>
                                </div>
                                <span style={{
                                    fontSize: 10,
                                    fontWeight: "bold",
                                    padding: "2px 8px",
                                    borderRadius: 4,
                                    background: `${scoreColor(optComp.score)}1a`,
                                    border: `1px solid ${scoreColor(optComp.score)}66`,
                                    color: scoreColor(optComp.score),
                                }}>
                                    Score Opções: {fmtNum(optComp.score, 1, true)} · {optComp.verdict}
                                </span>
                            </div>

                            <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8 }}>
                                <div style={{ background: "#0c1218", padding: "6px 8px", borderRadius: 5, border: "1px solid #1a2530" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>IV ATM (NO DINHEIRO)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#00d4ff" }}>{fmtNum(volSurf.atm_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "#0c1218", padding: "6px 8px", borderRadius: 5, border: "1px solid #1a2530" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>IV PUT 25Δ (OTM)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#ff6b8b" }}>{fmtNum(volSurf.put_25d_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "#0c1218", padding: "6px 8px", borderRadius: 5, border: "1px solid #1a2530" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>IV CALL 25Δ (OTM)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#00e87a" }}>{fmtNum(volSurf.call_25d_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "#0c1218", padding: "6px 8px", borderRadius: 5, border: "1px solid #1a2530" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>SKEW 25Δ (PUT − CALL)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#c8a444" }}>{fmtNum(volSurf.skew_25d_pct, 2, true)}%</div>
                                </div>
                                <div style={{ background: "#0c1218", padding: "6px 8px", borderRadius: 5, border: "1px solid #1a2530" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>PCR VOLUME TOTAL</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#e6edf3" }}>{fmtNum(optComp.pcr_total_volume, 2)}</div>
                                </div>
                                <div style={{ background: "#0c1218", padding: "6px 8px", borderRadius: 5, border: "1px solid #1a2530" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>PCR COMPRA AGRESSIVA</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: (optComp.pcr_aggressive_buy || 0) > 1.15 ? "#ff3860" : "#00e87a" }}>
                                        {fmtNum(optComp.pcr_aggressive_buy, 2)}
                                    </div>
                                </div>
                            </div>

                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 8.5 }}>
                                <thead>
                                    <tr style={{ color: "#5c7487", borderBottom: "1px solid #16232f", textAlign: "right" }}>
                                        <th style={{ textAlign: "left", padding: "4px" }}>SÉRIE</th>
                                        <th style={{ textAlign: "center", padding: "4px" }}>TIPO</th>
                                        <th style={{ padding: "4px" }}>STRIKE BOVA</th>
                                        <th style={{ padding: "4px", color: "#00d4ff" }}>≈ STRIKE WIN</th>
                                        <th style={{ padding: "4px" }}>BID / ASK</th>
                                        <th style={{ padding: "4px" }}>IV%</th>
                                        <th style={{ padding: "4px" }}>DELTA (Δ)</th>
                                        <th style={{ padding: "4px" }}>NEGÓCIOS</th>
                                        <th style={{ padding: "4px" }}>SALDO AGRESSÃO</th>
                                        <th style={{ padding: "4px" }}>FLUXO DELTA EQUIV.</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(cb.most_active_options || []).slice(0, 12).map(row => {
                                        const isCall = row.type === "CALL";
                                        const isBullImpact = (row.delta_equiv_flow || 0) > 0;
                                        return (
                                            <tr key={row.symbol} style={{ borderBottom: "1px solid #111b24", textAlign: "right" }}>
                                                <td style={{ textAlign: "left", padding: "4px", fontWeight: "bold", color: "#e6edf3" }}>{row.symbol}</td>
                                                <td style={{ textAlign: "center", padding: "4px", color: isCall ? "#00d4ff" : "#ff6b8b", fontWeight: "bold" }}>{row.type}</td>
                                                <td style={{ padding: "4px", color: "#b1c4d4" }}>R$ {fmtNum(row.strike_bova, 1)}</td>
                                                <td style={{ padding: "4px", color: "#00d4ff", fontWeight: "bold" }}>{fmtNum(row.equiv_win_strike, 0)}</td>
                                                <td style={{ padding: "4px", color: "#8ca5b5" }}>{fmtNum(row.bid, 2)} / {fmtNum(row.ask, 2)}</td>
                                                <td style={{ padding: "4px", color: "#c8a444" }}>{fmtNum(row.iv_pct, 1)}%</td>
                                                <td style={{ padding: "4px", color: "#b1c4d4" }}>{fmtNum(row.delta, 2, true)}</td>
                                                <td style={{ padding: "4px", color: "#8ca5b5" }}>{fmtNum(row.deals, 0)}</td>
                                                <td style={{ padding: "4px", color: row.net_aggr_vol >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                                    {fmtNum(row.net_aggr_vol, 0, true)} ({fmtNum(row.imbalance_pct, 1, true)}%)
                                                </td>
                                                <td style={{ padding: "4px", color: isBullImpact ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                                    {fmtNum(row.delta_equiv_flow, 0, true)}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default memo(IntradayCompassPanel);
