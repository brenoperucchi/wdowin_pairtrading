import React, { useState, useRef } from "react";

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

/* ══════════════════════════════════════════════════════════════════════════════
   1. GRÁFICO TRIPLO SINCRONIZADO ESTILO TRADINGVIEW ("FLUXO REAL + PINE GEX")
      - Visual Oficial TradingView Dark (#131722, grade #1e222d, Crosshair com tags de Preço/Hora)
      - Zoom no Scroll do Mouse + Pan Horizontal no Arraste + Zoom Vertical na Escala Y
      - Walls carregadas diretamente de `gex/docs/jumba_tradingview.pine`:
        * MAGICWALL * / ** / *** (#00e676 sólida, espessura 1/2/3)
        * MIDLEWALL (#90a4ae tracejada, espessura 1)
        * GAMMA FLIP (Pivot) (#ffd600 sólida)
        * MAX GAMMA (Teto) (#00b0ff) / MIN GAMMA (Piso) (#ff1744)
      - Painel 1 (Topo): Preço M5 pintado pelo Fluxo A.S.G + Pine Walls + Regiões de Defesa + Setas ▲/▼
      - Painel 2 (Meio): Fluxo Institucional CVD em bolinhas graduadas por peso do lote
      - Painel 3 (Base): Histograma Linha Zero + Linhas Douradas de Virada de Janela
   ══════════════════════════════════════════════════════════════════════════════ */
function FluxoRealAsgChart({
    symKey,
    series: rawSeries,
    flowWindows = [],
    asgHud = {},
    wallsRadar = {},
    allWalls = [],
    vwap,
    selectedSigId,
    onSelectSignal,
    showSignalsMarkers = true,
}) {
    const svgRef = useRef(null);
    const [hoverPos, setHoverPos] = useState(null); // { idx, relX, relY }
    const [rightGapPx, setRightGapPx] = useState(145);
    const [viewMode, setViewMode] = useState("RECENTE"); // "RECENTE" | "HOJE" | "TUDO" | "CUSTOM"
    const [visibleCount, setVisibleCount] = useState(48);
    const [panOffsetRight, setPanOffsetRight] = useState(0); // quantas barras deslocado do fim
    const [yZoomFactor, setYZoomFactor] = useState(1.0); // >1 abre mais o eixo Y para ver mais Walls do Pine
    const [showMidleWalls, setShowMidleWalls] = useState(true);
    const [wallColorMode, setWallColorMode] = useState("PINE"); // "PINE" (#00e676 original) | "POLARIDADE"
    const [dragState, setDragState] = useState(null); // { type: 'PAN' | 'YSCALE', startX, startY, startPan, startYZoom }

    const dec = symKey === "WDO" ? 1 : 0;

    if (!rawSeries || rawSeries.length < 1) {
        return (
            <div style={{
                height: 540,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#787b86",
                fontSize: 13,
                background: "#131722",
                borderRadius: 10,
                border: "1px solid #2a2e39",
            }}>
                Aguardando histórico M5 da sessão para plotar o Gráfico TradingView Fluxo Real + Pine GEX...
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
    const effCount = viewMode === "TUDO"
        ? totalBase
        : Math.max(14, Math.min(totalBase, visibleCount));
    const maxPan = Math.max(0, totalBase - effCount);
    const clampedPan = Math.max(0, Math.min(maxPan, panOffsetRight));
    const endSlice = totalBase - clampedPan;
    const startSlice = Math.max(0, endSlice - effCount);
    const series = baseSeries.slice(startSlice, endSlice);

    const width = 900;
    const height = 500;
    const padL = 10;
    const padR = 118; // Eixo Y estilo TradingView à direita

    // 3 Painéis Verticais Sincronizados estilo TradingView:
    // Painel 1 (Preço + Pine GEX Walls): Y de 14 até 322 (altura 308)
    // Painel 2 (Fluxo CVD Institucional): Y de 330 até 396 (altura 66)
    // Painel 3 (Janelas de Fluxo A.S.G): Y de 404 até 474 (altura 70)
    const p1Top = 14, p1H = 308, p1Bot = p1Top + p1H;
    const p2Top = 330, p2H = 66, p2Bot = p2Top + p2H;
    const p3Top = 404, p3H = 70, p3Bot = p3Top + p3H;
    const plotW = width - padL - padR;

    const innerPadL = 16;
    const usableW = Math.max(180, plotW - innerPadL - rightGapPx);
    const n = series.length;
    const totalSlots = Math.max(n - 1, 20);
    const stepX = usableW / Math.max(1, totalSlots);
    const candleW = Math.max(3.2, Math.min(10.5, stepX * 0.70));
    const toX = (idx) => padL + innerPadL + (idx / Math.max(1, totalSlots)) * usableW;
    const firstTodayLocalIdx = series.findIndex((pt, i) => i > 0 && !pt.is_prev_day && series[i - 1]?.is_prev_day);

    // ── Escala Y do Painel 1 (Preço + Walls do jumba_tradingview.pine) ──
    let minP = Infinity;
    let maxP = -Infinity;
    series.forEach(pt => {
        const l = Number(pt.low || pt.close);
        const h = Number(pt.high || pt.close);
        if (l > 0 && l < minP) minP = l;
        if (h > 0 && h > maxP) maxP = h;
    });

    // Inclui automaticamente a MagicWall/MidWall imediata de suporte e resistência na janela inicial
    const sup0 = wallsRadar?.support_walls?.[0]?.price;
    const res0 = wallsRadar?.resistance_walls?.[0]?.price;
    const rngRaw = Math.max(1, maxP - minP);
    if (sup0 && sup0 > 0 && (minP - sup0) <= rngRaw * 0.45) minP = Math.min(minP, sup0);
    if (res0 && res0 > 0 && (res0 - maxP) <= rngRaw * 0.45) maxP = Math.max(maxP, res0);

    const midP = (maxP + minP) / 2;
    const halfSpan = Math.max(symKey === "WDO" ? 6 : 180, ((maxP - minP) / 2) * 1.15 * yZoomFactor);
    minP = midP - halfSpan;
    maxP = midP + halfSpan;
    const rangeP = Math.max(1e-6, maxP - minP);
    const toY1 = (p) => p1Top + p1H - ((Number(p) - minP) / rangeP) * p1H;
    const fromY1 = (y) => minP + ((p1Bot - y) / p1H) * rangeP;

    // Grade horizontal estilo TradingView (6 níveis de preço no Painel 1)
    const priceGridLevels = [0.12, 0.28, 0.44, 0.60, 0.76, 0.90].map(f => minP + rangeP * f);

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

    // ── Escala Y do Painel 3 (Histograma Linha Zero -100 a +100) ──
    let maxAbsH = 25;
    series.forEach(pt => {
        const hv = Math.abs(Number(pt.flow_hist || 0));
        if (hv > maxAbsH) maxAbsH = hv;
    });
    maxAbsH = Math.min(100, maxAbsH * 1.12);
    const yZero3 = p3Top + p3H / 2;
    const toY3 = (hv) => yZero3 - (Number(hv || 0) / maxAbsH) * (p3H * 0.44);

    const lastPt = series[n - 1];
    const lastX = toX(n - 1);
    const lastY = toY1(lastPt.close);
    const hoverIdx = hoverPos ? hoverPos.idx : null;
    const inspectedPt = hoverIdx !== null && series[hoverIdx] ? series[hoverIdx] : lastPt;

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
        .map(w => ({
            ...w,
            price: Number(w.price),
            role: w.role || (Number(w.price) > Number(lastPt.close || 0) ? "RES" : "SUP"),
        }));

    const buyZone = asgHud?.buy_zone;
    const sellZone = asgHud?.sell_zone;
    const buyersPct = asgHud?.buyers_pct ?? 50;
    const sellersPct = asgHud?.sellers_pct ?? 50;

    // Sinais de entrada (▲ / ▼)
    const plottedSignals = [];
    series.forEach((pt, idx) => {
        if (pt.signal) {
            plottedSignals.push({
                ...pt.signal,
                idx,
                x: toX(idx),
                y: toY1(pt.signal.entry_price),
            });
        }
    });

    const timeTicks = [0, Math.floor(n * 0.2), Math.floor(n * 0.4), Math.floor(n * 0.6), Math.floor(n * 0.8), n - 1]
        .filter((v, i, a) => v >= 0 && v < n && a.indexOf(v) === i);

    return (
        <div style={{
            minWidth: 0,
            background: "#000000",
            borderRadius: 10,
            border: "1px solid #18293a",
            padding: "10px 12px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
            boxShadow: "0 8px 28px rgba(0,0,0,0.65)",
        }}>
            {/* ── Barra Superior Estilo TradingView ── */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{
                        fontSize: 11.5,
                        fontWeight: "bold",
                        color: "#ffffff",
                        letterSpacing: 0.8,
                        background: "linear-gradient(90deg, #00d4ff22, transparent)",
                        padding: "3px 8px",
                        borderRadius: 4,
                        borderLeft: "3px solid #00d4ff",
                    }}>
                        FLUXO REAL + PINE GEX ({symKey} · M5)
                    </span>
                    <span style={{ fontSize: 10, color: "#00e87a", fontWeight: "bold" }}>🟩 Comprado</span>
                    <span style={{ fontSize: 10, color: "#ff3860", fontWeight: "bold" }}>🟥 Vendido</span>
                    <span style={{ fontSize: 10, color: "#9598a1" }}>⬜ Pullback</span>
                </div>

                {/* Controles TradingView: Cores Pine, MidWalls, Legendas, Recuo e Zoom */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 3, background: "#080d14", padding: "2px 6px", borderRadius: 5, border: "1px solid #18293a" }}>
                        <button
                            onClick={() => setWallColorMode(m => (m === "PINE" ? "POLARIDADE" : "PINE"))}
                            title="Alternar entre cores originais do jumba_tradingview.pine (#00e676) ou Polaridade Suporte/Resistência"
                            style={{
                                padding: "2px 6px",
                                fontSize: 9,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                background: wallColorMode === "PINE" ? "rgba(0, 230, 118, 0.18)" : "rgba(242, 54, 69, 0.18)",
                                color: wallColorMode === "PINE" ? "#00e676" : "#ff6b8b",
                                border: `1px solid ${wallColorMode === "PINE" ? "#00e67666" : "#ff6b8b66"}`,
                                borderRadius: 4,
                                cursor: "pointer",
                            }}
                        >
                            {wallColorMode === "PINE" ? "🌲 Pine Original" : "⚡ Polaridade"}
                        </button>
                        <button
                            onClick={() => setShowMidleWalls(v => !v)}
                            title="Exibir/Ocultar MIDLEWALL tracejada do jumba_tradingview.pine"
                            style={{
                                padding: "2px 6px",
                                fontSize: 9,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                background: showMidleWalls ? "rgba(144, 164, 174, 0.2)" : "transparent",
                                color: showMidleWalls ? "#cfd8dc" : "#6b7c8c",
                                border: showMidleWalls ? "1px solid #90a4ae66" : "1px solid transparent",
                                borderRadius: 4,
                                cursor: "pointer",
                            }}
                        >
                            MidWalls
                        </button>
                        <span style={{ color: "#363c4e", margin: "0 2px" }}>|</span>
                        <button
                            onClick={() => setRightGapPx(g => Math.min(280, g + 35))}
                            title="Chegar gráfico mais para a esquerda"
                            style={{
                                padding: "2px 6px",
                                fontSize: 9,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                background: "#2a2e39",
                                color: "#00d4ff",
                                border: "1px solid #00d4ff55",
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
                                background: "#2a2e39",
                                color: "#b2b5be",
                                border: "1px solid #363c4e",
                                borderRadius: 4,
                                cursor: "pointer",
                            }}
                        >
                            Dir ▶
                        </button>
                        <button
                            onClick={() => setYZoomFactor(z => Math.min(4.0, +(z * 1.35).toFixed(2)))}
                            title="Abrir escala vertical Y para enxergar mais MagicWalls acima e abaixo"
                            style={{
                                padding: "2px 6px",
                                fontSize: 9,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                background: "#2a2e39",
                                color: "#00e676",
                                border: "1px solid #00e67655",
                                borderRadius: 4,
                                cursor: "pointer",
                            }}
                        >
                            ↕ −Zoom Y
                        </button>
                        {yZoomFactor !== 1.0 && (
                            <button
                                onClick={() => setYZoomFactor(1.0)}
                                title="Resetar escala vertical Y"
                                style={{
                                    padding: "2px 6px",
                                    fontSize: 9,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    background: "#2962ff33",
                                    color: "#82b1ff",
                                    border: "1px solid #2962ff",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                }}
                            >
                                Auto Y
                            </button>
                        )}
                        <span style={{ color: "#363c4e", margin: "0 2px" }}>|</span>
                        {[
                            { id: "RECENTE", label: "Foco (48b)" },
                            ...(hasPrevDayWarmup ? [{ id: "HOJE", label: "Só Hoje" }] : []),
                            { id: "TUDO", label: "Dia Todo" },
                        ].map(opt => (
                            <button
                                key={opt.id}
                                onClick={() => {
                                    setViewMode(opt.id);
                                    setPanOffsetRight(0);
                                    if (opt.id === "RECENTE") setVisibleCount(48);
                                }}
                                style={{
                                    padding: "2px 6px",
                                    fontSize: 9,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    background: viewMode === opt.id ? "rgba(41, 98, 255, 0.28)" : "transparent",
                                    color: viewMode === opt.id ? "#82b1ff" : "#787b86",
                                    border: viewMode === opt.id ? "1px solid #2962ff" : "1px solid transparent",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                }}
                            >
                                {opt.label}
                            </button>
                        ))}
                    </div>

                    {/* Inspetor OHLC + CVD + Histograma estilo TradingView */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 10, fontFamily: "monospace", background: "#080d14", padding: "3px 9px", borderRadius: 5, border: "1px solid #18293a" }}>
                        <span style={{ color: "#9598a1" }}>
                            🕒 {inspectedPt.is_prev_day ? `Ontem ${inspectedPt.time}` : inspectedPt.time}
                        </span>
                        <span style={{ color: "#787b86" }}>
                            A:{fmtNum(inspectedPt.open, dec)} M:{fmtNum(inspectedPt.high, dec)} m:{fmtNum(inspectedPt.low, dec)}
                        </span>
                        <span style={{ color: "#ffffff", fontWeight: "bold" }}>
                            F:{fmtNum(inspectedPt.close, dec)}
                        </span>
                        <span style={{ color: (inspectedPt.window_dir || 0) > 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                            {(inspectedPt.window_dir || 0) > 0 ? "🟢 COMPRA" : "🔴 VENDA"}
                        </span>
                        <span style={{ color: "#00d4ff" }}>
                            Hist: {fmtNum(inspectedPt.flow_hist, 1, true)}
                        </span>
                    </div>
                </div>
            </div>

            {/* ── GRÁFICO PRINCIPAL COM FUNDO PRETO PURO E SEM GRIDS (ZOOM NO SCROLL E PAN NO ARRASTE) ── */}
            <svg
                ref={svgRef}
                viewBox={`0 0 ${width} ${height}`}
                style={{
                    width: "100%",
                    height: "auto",
                    minHeight: 440,
                    display: "block",
                    userSelect: "none",
                    cursor: dragState ? (dragState.type === "YSCALE" ? "ns-resize" : "grabbing") : "crosshair",
                    background: "#000000",
                    borderRadius: 6,
                    border: "1px solid #14202e",
                }}
                onWheel={(e) => {
                    e.preventDefault();
                    const delta = e.deltaY > 0 ? 6 : -6;
                    setViewMode("CUSTOM");
                    setVisibleCount(c => Math.max(16, Math.min(totalBase, c + delta)));
                }}
                onMouseDown={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    const relX = ((e.clientX - rect.left) / rect.width) * width;
                    if (relX > padL + plotW) {
                        setDragState({
                            type: "YSCALE",
                            startY: e.clientY,
                            startYZoom: yZoomFactor,
                        });
                    } else {
                        setDragState({
                            type: "PAN",
                            startX: e.clientX,
                            startPan: clampedPan,
                        });
                    }
                }}
                onMouseMove={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    const relX = ((e.clientX - rect.left) / rect.width) * width;
                    const relY = ((e.clientY - rect.top) / rect.height) * height;

                    if (dragState) {
                        if (dragState.type === "PAN") {
                            const dxPx = e.clientX - dragState.startX;
                            const barsDelta = Math.round((dxPx / Math.max(1, rect.width * 0.7)) * effCount);
                            setPanOffsetRight(Math.max(0, Math.min(maxPan, dragState.startPan + barsDelta)));
                        } else if (dragState.type === "YSCALE") {
                            const dyPx = e.clientY - dragState.startY;
                            const factor = Math.max(0.4, Math.min(4.5, dragState.startYZoom * (1 + dyPx * 0.005)));
                            setYZoomFactor(+factor.toFixed(2));
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
                }}
                onDoubleClick={() => {
                    setYZoomFactor(1.0);
                    setPanOffsetRight(0);
                    setVisibleCount(48);
                    setViewMode("RECENTE");
                }}
            >
                {/* Fundos dos 3 Painéis em Preto Puro (#000000) sem linhas de grade */}
                <rect x={padL} y={p1Top} width={plotW} height={p1H} fill="#000000" />
                <rect x={padL} y={p2Top} width={plotW} height={p2H} fill="#000000" />
                <rect x={padL} y={p3Top} width={plotW} height={p3H} fill="#000000" />

                {/* Divisórias Horizontais Discretas dos 3 Painéis e Eixo Y Direito */}
                <line x1={padL} y1={p1Bot} x2={width} y2={p1Bot} stroke="#14202e" strokeWidth="1" />
                <line x1={padL} y1={p2Bot} x2={width} y2={p2Bot} stroke="#14202e" strokeWidth="1" />
                <line x1={padL} y1={p3Bot} x2={width} y2={p3Bot} stroke="#14202e" strokeWidth="1" />
                <line x1={padL + plotW} y1={p1Top} x2={padL + plotW} y2={p3Bot} stroke="#14202e" strokeWidth="1" />

                {/* Títulos Internos Discretos Estilo Marca d'Água TradingView */}
                <text x={padL + 8} y={p1Top + 13} fill="#787b86" fontSize="8.5" fontWeight="bold" fontFamily="monospace">
                    1. {symKey} · M5 · MAGIC GEX LEVELS (jumba_tradingview.pine)
                </text>
                <text x={padL + 8} y={p2Top + 11} fill="#787b86" fontSize="7.2" fontWeight="bold" fontFamily="monospace">
                    2. FLUXO INSTITUCIONAL CVD (Cor mais escura = Maior Lote)
                </text>
                <text x={padL + 8} y={p3Top + 11} fill="#787b86" fontSize="7.2" fontWeight="bold" fontFamily="monospace">
                    3. JANELAS DE FLUXO A.S.G (Histograma Linha Zero)
                </text>

                {/* Regiões Sombreadas de Compra e Venda Diferenciadas por Defesa Institucional + Hedge Makers */}
                {(() => {
                    const zonesToRender = [];
                    const baseBandPts = rangeP * 0.032;

                    const nearestResP = Number(sellZone?.ref_price || 0);
                    const nearestSupP = Number(buyZone?.ref_price || 0);

                    nearbyWalls.forEach((w, idx) => {
                        const isMainWall = String(w.type || "") === "Wall";
                        if (!isMainWall) return;

                        const isRes = w.price > lastPt.close;
                        const isNearestActive = (isRes && nearestResP > 0 && Math.abs(w.price - nearestResP) < 5)
                            || (!isRes && nearestSupP > 0 && Math.abs(w.price - nearestSupP) < 5);

                        const defLots = Number(w.defense_lots || 0);
                        const instTot = Number(w.inst_total_vol || 0);
                        const makerLots = Number(w.maker_hedge_lots || 0);
                        const powerPct = Number(w.wall_power_pct || (w.width || 1) * 28);
                        const tier = w.wall_tier || (powerPct >= 52 ? "FORTE" : (powerPct >= 26 || instTot > 0) ? "MODERADA" : "FRACA");

                        if (tier === "FRACA" && !isNearestActive) return;

                        const isStrong = tier === "FORTE" || (isNearestActive && (instTot > 0 || powerPct >= 40));
                        const scaleFactor = isStrong ? 0.58 : 0.34;
                        const halfW = baseBandPts * scaleFactor;

                        const roleTitle = isRes
                            ? (isStrong ? "🔥 REGIÃO DE VENDA FORTE" : "Região de Venda")
                            : (isStrong ? "🛡️ REGIÃO DE COMPRA FORTE" : "Região de Compra");

                        const detailsParts = [];
                        if (defLots > 0) {
                            detailsParts.push(`Defesa Inst: ${fmtNum(defLots, 0)}L`);
                        } else if (instTot > 0) {
                            detailsParts.push(`Fluxo Inst: ${fmtNum(instTot, 0)}L`);
                        }
                        if (makerLots > 0) {
                            detailsParts.push(`Hedge Makers: ${fmtNum(makerLots, 0)}L`);
                        }
                        const fullLabel = detailsParts.length > 0
                            ? `${roleTitle} · ${detailsParts.join(" | ")}`
                            : `${roleTitle} (${w.label || "MagicWall"})`;

                        zonesToRender.push({
                            key: `wall-zone-${idx}`,
                            topP: w.price + halfW,
                            botP: w.price - halfW,
                            isSell: isRes,
                            isStrong,
                            label: fullLabel,
                        });
                    });

                    return zonesToRender.map((z) => {
                        if (z.topP < minP || z.botP > maxP) return null;
                        const yTop = Math.max(p1Top, toY1(Math.min(maxP, z.topP)));
                        const yBot = Math.min(p1Bot, toY1(Math.max(minP, z.botP)));
                        const hBand = Math.max(5, yBot - yTop);
                        const col = z.isSell ? "#f23645" : "#089981";
                        const fillRgba = z.isSell
                            ? (z.isStrong ? "rgba(242, 54, 69, 0.18)" : "rgba(242, 54, 69, 0.08)")
                            : (z.isStrong ? "rgba(8, 153, 129, 0.18)" : "rgba(8, 153, 129, 0.08)");
                        return (
                            <g key={z.key}>
                                <rect x={padL} y={yTop} width={plotW} height={hBand} fill={fillRgba} />
                                {z.isStrong && (
                                    <rect x={padL} y={yTop} width={4} height={hBand} fill={col} />
                                )}
                                <text
                                    x={padL + 9}
                                    y={yTop + Math.min(11, hBand - 2)}
                                    fill={z.isSell ? "#ff8da3" : "#66ffcc"}
                                    fontSize="7.8"
                                    fontWeight="bold"
                                    fontFamily="monospace"
                                    opacity="0.88"
                                >
                                    {z.label}
                                </text>
                            </g>
                        );
                    });
                })()}

                {/* ── LINHAS E LABELS OFICIAIS DO `jumba_tradingview.pine` (bar_index + 12) ── */}
                {nearbyWalls.map((w, i) => {
                    const yW = toY1(w.price);
                    const wType = String(w.type || "Wall");
                    const isMid = wType.toLowerCase().includes("mid") || String(w.label || "").toUpperCase() === "MIDLEWALL";
                    const isRes = w.role === "RES";

                    // Cor exata do `jumba_tradingview.pine` (#00e676, #90a4ae, #ffd600, #00b0ff, #ff1744)
                    const pineCol = w.color || (
                        wType === "GammaFlip" ? "#ffd600"
                            : wType === "MaxGamma" ? "#00b0ff"
                                : wType === "MinGamma" ? "#ff1744"
                                    : isMid ? "#90a4ae" : "#00e676"
                    );
                    const polCol = isMid ? "#90a4ae" : (wType === "GammaFlip" ? "#ffd600" : (isRes ? "#f23645" : "#089981"));
                    const col = wallColorMode === "PINE" ? pineCol : polCol;

                    const strokeW = isMid ? 1.0 : Math.max(1.2, Math.min(3.0, Number(w.width || 1) * 0.85));
                    const isDashed = w.style === "dashed" || isMid;
                    const hideRightAxisTag = Math.abs(yW - lastY) < 12;

                    return (
                        <g key={`pine-wall-${i}`}>
                            <line
                                x1={padL}
                                y1={yW}
                                x2={padL + plotW}
                                y2={yW}
                                stroke={col}
                                strokeWidth={strokeW}
                                strokeDasharray={isDashed ? "5,4" : "none"}
                                opacity={isMid ? "0.55" : "0.90"}
                            />
                            {/* Etiqueta de Preço no Eixo Y Direito estilo TradingView */}
                            {!hideRightAxisTag && !isMid && (
                                <g>
                                    <rect
                                        x={padL + plotW + 2}
                                        y={yW - 7}
                                        width={padR - 8}
                                        height={14}
                                        rx="2"
                                        fill="#1e222d"
                                        stroke={col}
                                        strokeWidth="0.9"
                                    />
                                    <text
                                        x={padL + plotW + 6}
                                        y={yW + 3}
                                        fill={col}
                                        fontSize="8.5"
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
                            stroke="#2962ff"
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
                            fill="#1e222d"
                            stroke="#2962ff"
                            strokeWidth="1"
                        />
                        <text
                            x={toX(firstTodayLocalIdx) - stepX * 0.45 + 7}
                            y={p1Top + 13}
                            fill="#82b1ff"
                            fontSize="7.5"
                            fontWeight="bold"
                            fontFamily="monospace"
                        >
                            HOJE {series[firstTodayLocalIdx]?.time}
                        </text>
                    </g>
                )}

                {/* Linhas Verticais Douradas marcando a virada de cada Janela de Fluxo */}
                {flowWindows.map((fw, idx) => {
                    if (!fw || fw.start_idx <= 0) return null;
                    const localStartIdx = series.findIndex(pt => pt._origIdx === fw.start_idx);
                    if (localStartIdx <= 0) return null;
                    const xStart = toX(localStartIdx);
                    return (
                        <g key={fw.id || `fw-v-${idx}`}>
                            <line
                                x1={xStart}
                                y1={p1Top}
                                x2={xStart}
                                y2={p3Bot}
                                stroke="#d4af37"
                                strokeWidth="1.1"
                                strokeOpacity="0.72"
                            />
                            <circle cx={xStart} cy={yZero3} r="2.8" fill="#ffd700" />
                        </g>
                    );
                })}

                {/* ── CANDLES DO PREÇO PINTADOS PELO FLUXO (VERDE / VERMELHO / CINZA) ── */}
                {series.map((pt, idx) => {
                    const x = toX(idx);
                    const yH = toY1(pt.high || pt.close);
                    const yL = toY1(pt.low || pt.close);
                    const yO = toY1(pt.open || pt.close);
                    const yC = toY1(pt.close);

                    const cState = pt.candle_state ?? (pt.window_dir || 0);
                    const fillCol = cState > 0 ? "#00e87a" : cState < 0 ? "#ff3860" : "#9fb0c2";
                    const bodyTop = Math.min(yO, yC);
                    const bodyH = Math.max(2.0, Math.abs(yC - yO));

                    return (
                        <g key={`p-candle-${idx}`}>
                            <line x1={x} y1={yH} x2={x} y2={yL} stroke={fillCol} strokeWidth="1.2" strokeOpacity="0.9" />
                            <rect
                                x={x - candleW / 2}
                                y={bodyTop}
                                width={candleW}
                                height={bodyH}
                                fill={fillCol}
                                rx="0.8"
                            />
                        </g>
                    );
                })}

                {/* Linha de Preço Spot Atual + Badge Oficial Estilo TradingView na Escala Direita */}
                <g>
                    <line x1={padL} y1={lastY} x2={padL + plotW} y2={lastY} stroke="#2962ff" strokeWidth="1" strokeDasharray="3,3" opacity="0.85" />
                    <rect x={padL + plotW + 1} y={lastY - 10} width={padR - 5} height={20} rx="3" fill="#2962ff" />
                    <text x={padL + plotW + 7} y={lastY + 4} fill="#ffffff" fontSize="10.5" fontWeight="bold" fontFamily="monospace">
                        {fmtNum(lastPt.close, dec)} {(lastPt.window_dir || 0) > 0 ? "▲" : "▼"}
                    </text>
                </g>

                {/* Marcadores dos Sinais Emitidos (▲ COMPRA / ▼ VENDA) */}
                {showSignalsMarkers && plottedSignals.map((sig) => {
                    const isBuy = sig.dir_num > 0;
                    const col = isBuy ? "#00e87a" : "#ff3860";
                    const isSelected = selectedSigId === sig.id;
                    const x = sig.x;
                    const y = sig.y;
                    const triPoints = isBuy
                        ? `${x},${y + 9} ${x - 5.5},${y + 18} ${x + 5.5},${y + 18}`
                        : `${x},${y - 9} ${x - 5.5},${y - 18} ${x + 5.5},${y - 18}`;

                    return (
                        <g
                            key={sig.id}
                            onClick={(e) => {
                                e.stopPropagation();
                                if (onSelectSignal) onSelectSignal(sig.id);
                            }}
                            style={{ cursor: "pointer" }}
                        >
                            <polygon points={triPoints} fill={col} stroke={isSelected ? "#ffffff" : "#131722"} strokeWidth="1.2" />
                        </g>
                    );
                })}

                {/* ══════════════════════════════════════════════════════════════════════
                   PAINEL 2 (MEIO): FLUXO INSTITUCIONAL EM PONTINHOS (COR MAIS ESCURA = MAIOR PESO)
                   ══════════════════════════════════════════════════════════════════════ */}
                <polyline
                    fill="none"
                    stroke="#2a3a4d"
                    strokeWidth="1.2"
                    points={series.map((pt, idx) => `${toX(idx).toFixed(1)},${toY2(pt.flow_close ?? pt.cvd_inst ?? 0).toFixed(1)}`).join(" ")}
                />
                {series.map((pt, idx) => {
                    const x = toX(idx);
                    const fo = Number(pt.flow_open ?? pt.cvd_inst ?? 0);
                    const fc = Number(pt.flow_close ?? pt.cvd_inst ?? 0);
                    const yC = toY2(fc);
                    const isFlowUp = fc >= fo;
                    const absDelta = Math.abs(Number(pt.inst_delta_bar || (fc - fo)));
                    const refHeavy = symKey === "WDO" ? 700 : 3500;
                    const refMid = symKey === "WDO" ? 280 : 1400;

                    const isHeavy = absDelta >= refHeavy;
                    const isMidWeight = absDelta >= refMid;

                    let fCol;
                    if ((pt.window_dir || 0) < 0) {
                        if (isFlowUp) {
                            fCol = isHeavy ? "#4a5c6b" : isMidWeight ? "#7d91a3" : "#b4c3d0";
                        } else {
                            fCol = isHeavy ? "#9e0b28" : isMidWeight ? "#e01e45" : "#ff758f";
                        }
                    } else {
                        if (isFlowUp) {
                            fCol = isHeavy ? "#007a3d" : isMidWeight ? "#00c466" : "#7bf1a8";
                        } else {
                            fCol = isHeavy ? "#4a5c6b" : isMidWeight ? "#7d91a3" : "#b4c3d0";
                        }
                    }

                    return (
                        <circle
                            key={`f-dot-${idx}`}
                            cx={x}
                            cy={yC}
                            r="2.4"
                            fill={fCol}
                        />
                    );
                })}

                <text x={padL + plotW + 6} y={toY2(lastPt.cvd_inst) + 3} fill={(lastPt.cvd_inst || 0) >= 0 ? "#00e87a" : "#ff3860"} fontSize="9" fontWeight="bold" fontFamily="monospace">
                    {fmtNum(lastPt.cvd_inst, 0, true)}L
                </text>

                {/* ══════════════════════════════════════════════════════════════════════
                   PAINEL 3 (BASE): HISTOGRAMA LINHA ZERO (VERDE = COMPRA / VERMELHO = VENDA)
                   ══════════════════════════════════════════════════════════════════════ */}
                <line x1={padL} y1={yZero3} x2={padL + plotW} y2={yZero3} stroke="#363c4e" strokeWidth="1.0" />
                <text x={padL + plotW + 6} y={yZero3 + 3} fill="#787b86" fontSize="8.5" fontWeight="bold" fontFamily="monospace">
                    ZERO (0)
                </text>

                {series.map((pt, idx) => {
                    const x = toX(idx);
                    const hv = Number(pt.flow_hist || 0);
                    const yH = toY3(hv);
                    const isPos = hv >= 0;
                    const col = isPos ? "#00e87a" : "#ff3860";
                    const barTop = isPos ? yH : yZero3;
                    const barH = Math.max(1.5, Math.abs(yZero3 - yH));

                    return (
                        <rect
                            key={`h-bar-${idx}`}
                            x={x - candleW / 2}
                            y={barTop}
                            width={candleW}
                            height={barH}
                            fill={col}
                            opacity="0.88"
                            rx="0.5"
                        />
                    );
                })}

                {/* Eixo de Tempo no Rodapé estilo TradingView */}
                {timeTicks.map((tIdx) => (
                    <text
                        key={`t-${tIdx}`}
                        x={toX(tIdx)}
                        y={height - 7}
                        textAnchor="middle"
                        fill="#787b86"
                        fontSize="9.5"
                        fontFamily="monospace"
                    >
                        {series[tIdx]?.is_prev_day ? `Ont ${series[tIdx]?.time}` : series[tIdx]?.time}
                    </text>
                ))}

                {/* ── CROSSHAIR INTERATIVO DUPLO ESTILO TRADINGVIEW (VERTICAL + HORIZONTAL COM TAG DE PREÇO E HORA) ── */}
                {hoverPos && series[hoverPos.idx] && (
                    <g>
                        {/* Linha Vertical do Crosshair */}
                        <line
                            x1={toX(hoverPos.idx)}
                            y1={p1Top}
                            x2={toX(hoverPos.idx)}
                            y2={p3Bot}
                            stroke="#9598a1"
                            strokeWidth="1"
                            strokeDasharray="4,4"
                        />
                        {/* Badge de Hora no Eixo X Inferior */}
                        <rect
                            x={toX(hoverPos.idx) - 28}
                            y={p3Bot + 2}
                            width={56}
                            height={18}
                            rx="3"
                            fill="#2962ff"
                        />
                        <text
                            x={toX(hoverPos.idx)}
                            y={p3Bot + 14}
                            textAnchor="middle"
                            fill="#ffffff"
                            fontSize="9"
                            fontWeight="bold"
                            fontFamily="monospace"
                        >
                            {series[hoverPos.idx]?.time}
                        </text>

                        {/* Linha Horizontal do Crosshair + Badge de Preço no Eixo Y Direito */}
                        {hoverPos.relY >= p1Top && hoverPos.relY <= p1Bot && (
                            <>
                                <line
                                    x1={padL}
                                    y1={hoverPos.relY}
                                    x2={padL + plotW}
                                    y2={hoverPos.relY}
                                    stroke="#9598a1"
                                    strokeWidth="1"
                                    strokeDasharray="4,4"
                                />
                                <rect
                                    x={padL + plotW + 2}
                                    y={hoverPos.relY - 9}
                                    width={padR - 6}
                                    height={18}
                                    rx="3"
                                    fill="#363c4e"
                                    stroke="#9598a1"
                                    strokeWidth="0.8"
                                />
                                <text
                                    x={padL + plotW + 7}
                                    y={hoverPos.relY + 3.5}
                                    fill="#ffffff"
                                    fontSize="9.5"
                                    fontWeight="bold"
                                    fontFamily="monospace"
                                >
                                    {fmtNum(fromY1(hoverPos.relY), dec)}
                                </text>
                            </>
                        )}
                    </g>
                )}
            </svg>

            {/* ── Barra Inferior de Dominância Compradores % vs Vendedores % ── */}
            <div style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                background: "#1e222d",
                padding: "6px 12px",
                borderRadius: 7,
                border: "1px solid #2a2e39",
            }}>
                <span style={{ fontSize: 13, fontWeight: "bold", color: "#00e87a", minWidth: 110 }}>
                    {buyersPct}% <span style={{ fontSize: 9.5, fontWeight: "normal", color: "#9598a1" }}>COMPRADORES</span>
                </span>
                <div style={{ flex: 1, height: 8, background: "#ff3860", borderRadius: 4, overflow: "hidden", display: "flex" }}>
                    <div style={{ width: `${buyersPct}%`, height: "100%", background: "#00e87a", boxShadow: "0 0 10px #00e87a", transition: "width 0.3s ease" }} />
                </div>
                <span style={{ fontSize: 13, fontWeight: "bold", color: "#ff3860", minWidth: 110, textAlign: "right" }}>
                    <span style={{ fontSize: 9.5, fontWeight: "normal", color: "#9598a1" }}>VENDEDORES</span> {sellersPct}%
                </span>
            </div>
        </div>
    );
}

/* ══════════════════════════════════════════════════════════════════════════════
   2. HUD FUTURISTA ESTILO "A.S.G (ALGORITHMIC SYSTEM GENERATION)" (VÍDEO 3)
      - Semáforo Gigante: ▲ COMPRA | ▼ VENDA | ❖ NEUTRALIZADO
      - Vela 3D Neon + Anel Circular MICRO (92%) + MACRO (50) + MAKERS (+0.2%)
      - Trilha de Alvos 1 -> 2 -> 3 + Botão para abrir Histórico de Sinais
   ══════════════════════════════════════════════════════════════════════════════ */
function AsgCockpitHud({ symKey, payload, asgHud = {}, scorecard = {}, onToggleHistory, showHistory }) {
    const dec = symKey === "WDO" ? 1 : 0;
    const cmd = asgHud.command || "NEUTRALIZADO";
    const isBuy = cmd === "COMPRA";
    const isSell = cmd === "VENDA";
    const mainColor = isBuy ? "#00e87a" : isSell ? "#ff3860" : "#00d4ff";

    const microPct = Number(asgHud.micro_pct || 50);
    const macroPct = Number(asgHud.macro_pct || 50);
    const makersPct = Number(asgHud.makers_pct || 0);
    const targets = asgHud.targets || [];

    // Arco circular SVG para o medidor MICRO (estilo o arco 92 MICRO do Vídeo 3)
    const radius = 30;
    const circum = 2 * Math.PI * radius;
    const arcOffset = circum - (Math.min(100, Math.max(10, microPct)) / 100) * (circum * 0.75);

    return (
        <div style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            background: "radial-gradient(circle at 50% 25%, #0c1b2a 0%, #05080d 85%)",
            border: `1.5px solid ${mainColor}55`,
            borderRadius: 12,
            padding: "14px 16px",
            boxShadow: `0 0 28px ${mainColor}18`,
        }}>
            {/* ── 1. DISPLAY SUPERIOR: TRIÂNGULO GIGANTE OU ORBE NEUTRALIZADO (VÍDEO 3) ── */}
            <div style={{
                position: "relative",
                background: "#04070b",
                border: `1.5px solid ${mainColor}66`,
                borderRadius: 10,
                padding: "14px 12px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 6,
                boxShadow: `inset 0 0 24px ${mainColor}1f`,
            }}>
                <div style={{ fontSize: 9.5, color: "#7f96a8", letterSpacing: 1.5, fontFamily: "monospace" }}>
                    STATUS OPERACIONAL · {symKey} ({payload?.active_contract})
                </div>

                {/* Ícone Central Gigante (Triângulo Verde / Triângulo Vermelho / Hexágono Neutralizado) */}
                <svg width="110" height="76" viewBox="0 0 110 76">
                    <defs>
                        <filter id={`glow-${symKey}`} x="-30%" y="-30%" width="160%" height="160%">
                            <feGaussianBlur stdDeviation="5" result="blur" />
                            <feComposite in="SourceGraphic" in2="blur" operator="over" />
                        </filter>
                    </defs>
                    {/* Moldura HUD estilo A.S.G */}
                    <polygon
                        points="18,6 92,6 106,38 92,70 18,70 4,38"
                        fill="none"
                        stroke={mainColor}
                        strokeWidth="1.2"
                        strokeOpacity="0.45"
                    />
                    {isBuy && (
                        <polygon
                            points="55,14 82,60 28,60"
                            fill="#00e87a"
                            filter={`url(#glow-${symKey})`}
                        />
                    )}
                    {isSell && (
                        <polygon
                            points="55,62 82,16 28,16"
                            fill="#ff3860"
                            filter={`url(#glow-${symKey})`}
                        />
                    )}
                    {!isBuy && !isSell && (
                        <g>
                            <polygon
                                points="55,12 80,25 80,51 55,64 30,51 30,25"
                                fill="rgba(0, 212, 255, 0.12)"
                                stroke="#00d4ff"
                                strokeWidth="2"
                            />
                            <path d="M 38 38 Q 46 26, 55 38 T 72 38" fill="none" stroke="#ffffff" strokeWidth="2.5" />
                            <ellipse cx="55" cy="58" rx="16" ry="4" fill="#f5a623" opacity="0.75" />
                        </g>
                    )}
                </svg>

                <div style={{
                    fontSize: 22,
                    fontWeight: 900,
                    color: mainColor,
                    letterSpacing: 3,
                    textShadow: `0 0 14px ${mainColor}88`,
                }}>
                    {isBuy ? "COMPRAR" : isSell ? "VENDER" : "NEUTRALIZADO"}
                </div>

                <div style={{
                    fontSize: 10,
                    fontWeight: "bold",
                    color: "#d0dde8",
                    textAlign: "center",
                    letterSpacing: 0.6,
                }}>
                    {asgHud.command_sub || "SIGA O FLUXO NO CONTEXTO"}
                </div>
            </div>

            {/* ── 2. VELA 3D NEON DE CONTEXTO: MICRO + MACRO + MAKERS (IGUAL VÍDEO 3) ── */}
            <div style={{
                background: "#050910",
                border: "1px solid #162636",
                borderRadius: 10,
                padding: "12px 14px",
                display: "flex",
                flexDirection: "column",
                gap: 6,
            }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 10, fontWeight: "bold", color: "#8ca5b5", letterSpacing: 1.5 }}>
                        CONTEXTO:
                    </span>
                    <span style={{
                        fontSize: 9.5,
                        fontWeight: "bold",
                        color: (asgHud.window_dir || 0) > 0 ? "#00e87a" : "#ff3860",
                        background: (asgHud.window_dir || 0) > 0 ? "rgba(0,232,122,0.12)" : "rgba(255,56,96,0.12)",
                        padding: "2px 8px",
                        borderRadius: 4,
                        border: `1px solid ${(asgHud.window_dir || 0) > 0 ? "#00e87a44" : "#ff386044"}`,
                    }}>
                        {asgHud.window_label} (desde {asgHud.window_start_time || "09:00"})
                    </span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1.1fr 1fr", alignItems: "center", gap: 6, padding: "4px 0" }}>
                    {/* Esquerda: Anel Circular Neon MICRO */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <div style={{ position: "relative", width: 76, height: 76, display: "flex", alignItems: "center", justifyContent: "center" }}>
                            <svg width="76" height="76" viewBox="0 0 76 76" style={{ transform: "rotate(135deg)" }}>
                                <circle
                                    cx="38"
                                    cy="38"
                                    r={radius}
                                    fill="none"
                                    stroke="#122230"
                                    strokeWidth="5"
                                    strokeDasharray={circum}
                                    strokeDashoffset={circum * 0.25}
                                    strokeLinecap="round"
                                />
                                <circle
                                    cx="38"
                                    cy="38"
                                    r={radius}
                                    fill="none"
                                    stroke={mainColor}
                                    strokeWidth="5.5"
                                    strokeDasharray={circum}
                                    strokeDashoffset={arcOffset}
                                    strokeLinecap="round"
                                />
                            </svg>
                            <div style={{ position: "absolute", textAlign: "center" }}>
                                <div style={{ fontSize: 19, fontWeight: "bold", color: "#ffffff", lineHeight: 1 }}>{microPct}</div>
                                <div style={{ fontSize: 7.5, color: mainColor, fontWeight: "bold", letterSpacing: 1 }}>MICRO</div>
                            </div>
                        </div>
                    </div>

                    {/* Centro: MACRO + Vela 3D Isométrica Neon */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                        <div style={{ textAlign: "center", marginBottom: 2 }}>
                            <div style={{ fontSize: 16, fontWeight: "bold", color: "#ffffff", lineHeight: 1 }}>{macroPct}</div>
                            <div style={{ fontSize: 7.5, color: "#8ca5b5", letterSpacing: 1 }}>MACRO</div>
                        </div>
                        {/* Cubo/Vela 3D Neon SVG */}
                        <svg width="84" height="110" viewBox="0 0 84 110">
                            {/* Pavio Superior 3D */}
                            <line x1="42" y1="4" x2="42" y2="26" stroke={mainColor} strokeWidth="3" strokeLinecap="round" />
                            {/* Face Topo do Prisma 3D */}
                            <polygon
                                points="42,18 66,28 42,38 18,28"
                                fill={`${mainColor}33`}
                                stroke={mainColor}
                                strokeWidth="1.6"
                            />
                            {/* Face Esquerda */}
                            <polygon
                                points="18,28 42,38 42,84 18,74"
                                fill={`${mainColor}18`}
                                stroke={mainColor}
                                strokeWidth="1.5"
                            />
                            {/* Face Direita */}
                            <polygon
                                points="42,38 66,28 66,74 42,84"
                                fill={`${mainColor}28`}
                                stroke={mainColor}
                                strokeWidth="1.5"
                            />
                            {/* Pavio Inferior Pontilhado */}
                            <line x1="42" y1="84" x2="42" y2="106" stroke="#f5a623" strokeWidth="2.2" strokeDasharray="3,3" />
                            <circle cx="42" cy="96" r="2.5" fill="#ffffff" />
                        </svg>
                    </div>

                    {/* Direita: MAKERS (Pressão dos Market Makers GEX) */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6 }}>
                        <div style={{
                            background: "#09131e",
                            border: "1px solid #1b2f42",
                            borderRadius: 8,
                            padding: "8px 10px",
                            textAlign: "center",
                            width: "100%",
                        }}>
                            <div style={{
                                fontSize: 16,
                                fontWeight: "bold",
                                color: makersPct >= 0 ? "#00e87a" : "#ff3860",
                            }}>
                                {makersPct > 0 ? "+" : ""}{fmtNum(makersPct, 1)}%
                            </div>
                            <div style={{ fontSize: 8, color: "#9fb4c4", fontWeight: "bold", letterSpacing: 1 }}>
                                MAKERS (GEX)
                            </div>
                        </div>

                        <div style={{
                            fontSize: 8.5,
                            color: "#8ca5b5",
                            textAlign: "center",
                        }}>
                            Médio Janela:<br />
                            <strong style={{ color: "#ffd700", fontSize: 11 }}>{fmtNum(asgHud.window_entry_price, dec)}</strong>
                        </div>
                    </div>
                </div>
            </div>

            {/* ── 3. TRILHA DE ALVOS DA JANELA (1 -> 2 -> 3) ── */}
            <div style={{
                background: "#050910",
                border: "1px solid #162636",
                borderRadius: 10,
                padding: "10px 14px",
                display: "flex",
                flexDirection: "column",
                gap: 6,
            }}>
                {/* Escada de Alvos (1 -> 2 -> 3) igual aos degraus dourados do Vídeo 3 */}
                <div>
                    <div style={{ fontSize: 9, color: "#8ca5b5", fontWeight: "bold", letterSpacing: 1, marginBottom: 6, textAlign: "center" }}>
                        SIGA O FLUXO NO CONTEXTO · ALVOS DA JANELA
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
                        {[0, 1, 2].map((idx) => {
                            const tPrice = targets[idx];
                            const isFirst = idx === 0;
                            return (
                                <div
                                    key={`t-step-${idx}`}
                                    style={{
                                        background: isFirst ? "linear-gradient(180deg, #d4af37, #9a7b1c)" : "#0b141e",
                                        color: isFirst ? "#05080d" : "#9fb4c4",
                                        border: isFirst ? "1px solid #ffd700" : "1px solid #1e3144",
                                        borderRadius: 6,
                                        padding: "6px 6px",
                                        textAlign: "center",
                                        boxShadow: isFirst ? "0 0 12px rgba(212,175,55,0.4)" : "none",
                                    }}
                                >
                                    <div style={{ fontSize: 8, fontWeight: "bold", opacity: 0.85 }}>
                                        ALVO {idx + 1}
                                    </div>
                                    <div style={{ fontSize: 13, fontWeight: 900, color: isFirst ? "#05080d" : "#ffffff", marginTop: 1 }}>
                                        {tPrice ? fmtNum(tPrice, dec) : "—"}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* ── 4. PLACAR RESUMIDO + BOTÃO PARA ABRIR HISTÓRICO DE SINAIS ── */}
            <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: "#070e17",
                border: "1px solid #162636",
                borderRadius: 8,
                padding: "8px 12px",
            }}>
                <div style={{ fontSize: 9.5, color: "#9fb4c4" }}>
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
                        background: showHistory ? "rgba(0,212,255,0.18)" : "#0d1824",
                        border: "1px solid #00d4ff55",
                        color: "#00d4ff",
                        borderRadius: 5,
                        cursor: "pointer",
                    }}
                >
                    {showHistory ? "▲ Ocultar Sinais" : "📋 Ver Sinais do Dia"}
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
function DailyOperationsEquityChart({ symKey, signalsLog = [], scorecard = {}, selectedSigId, onSelectSignal }) {
    const [contracts, setContracts] = useState(symKey === "WDO" ? 2 : 5);
    const [hoverTradeIdx, setHoverTradeIdx] = useState(null);

    const dec = symKey === "WDO" ? 1 : 0;
    // WIN = R$ 0,20 por ponto por contrato | WDO = R$ 10,00 por ponto por contrato
    const brlPerPt = symKey === "WDO" ? 10.0 : 0.20;
    const targetRef = Number(scorecard.target_ref_pts || (symKey === "WDO" ? 12.0 : 250));
    const stopRef = Number(scorecard.stop_ref_pts || (symKey === "WDO" ? 7.0 : 250));
    const useBe = scorecard.use_be_protection !== undefined ? Boolean(scorecard.use_be_protection) : (symKey === "WDO");
    const beTrigger = Number(scorecard.be_trigger_pts || (symKey === "WDO" ? 3.5 : 150));
    const beLock = Number(scorecard.be_lock_pts || (symKey === "WDO" ? 1.0 : 50));
    const timeStopMin = Number(scorecard.time_stop_min || (symKey === "WDO" ? 60 : 40));
    const methodLabel = scorecard.methodology_label || (symKey === "WDO" ? "M2 · Alinhada ASG" : "M1 · Pura (Wall + Fluxo)");

    // Ordenar sinais em ordem cronológica (09:00 -> atual)
    const chronoSignals = [...signalsLog].reverse();

    let cumPts = 0;
    let peakPts = 0;
    let maxDrawdownPts = 0;
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

        const tradeBrl = tradePts * brlPerPt * contracts;
        const cumBrl = cumPts * brlPerPt * contracts;

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

    const totalBrl = cumPts * brlPerPt * contracts;
    const isNetPos = totalBrl >= 0;
    const curveColor = isNetPos ? "#00e87a" : "#ff3860";
    const profitFactor = grossLossPts > 0 ? (grossGainPts / grossLossPts) : (grossGainPts > 0 ? 9.9 : 1.0);

    const w = 400;
    const h = 112;
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
            background: "radial-gradient(circle at 50% 0%, #0b1928 0%, #05080d 90%)",
            border: `1.5px solid ${curveColor}44`,
            borderRadius: 12,
            padding: "10px 14px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
            boxShadow: "0 6px 22px rgba(0,0,0,0.4)",
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
                        color: "#00e676",
                        background: "rgba(0, 230, 118, 0.10)",
                        border: "1px solid rgba(0, 230, 118, 0.30)",
                        padding: "1px 5px",
                        borderRadius: 4,
                        fontWeight: "bold",
                    }}>
                        🔒 BARRA FECHADA
                    </span>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                    {(symKey === "WDO" ? [1, 2, 5] : [1, 5, 10]).map(c => (
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
                                background: contracts === c ? "#00d4ff" : "#0b141e",
                                color: contracts === c ? "#04080e" : "#8ca5b5",
                                border: contracts === c ? "1px solid #00d4ff" : "1px solid #1b2d3e",
                            }}
                        >
                            {c} {c === 1 ? "Contr." : "Contr."}
                        </button>
                    ))}
                </div>
            </div>

            {/* Faixa de Parâmetros Operacionais Otimizados (TP / SL / BE / Metodologia) */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr 1.3fr 1.2fr",
                gap: 5,
                background: "#050910",
                border: "1px solid #162636",
                borderRadius: 7,
                padding: "5px 8px",
                fontFamily: "monospace",
            }}>
                <div>
                    <div style={{ fontSize: 7, color: "#6c8496", fontWeight: "bold" }}>ALVO (TP)</div>
                    <div style={{ fontSize: 10.5, fontWeight: 900, color: "#00e87a" }}>
                        +{fmtNum(targetRef, dec)}p <span style={{ fontSize: 8, color: "#7f96a8", fontWeight: "normal" }}>(+R$ {fmtNum(targetRef * brlPerPt * contracts, 0)})</span>
                    </div>
                </div>
                <div>
                    <div style={{ fontSize: 7, color: "#6c8496", fontWeight: "bold" }}>STOP (SL)</div>
                    <div style={{ fontSize: 10.5, fontWeight: 900, color: "#ff3860" }}>
                        -{fmtNum(stopRef, dec)}p <span style={{ fontSize: 8, color: "#7f96a8", fontWeight: "normal" }}>(-R$ {fmtNum(stopRef * brlPerPt * contracts, 0)})</span>
                    </div>
                </div>
                <div>
                    <div style={{ fontSize: 7, color: "#6c8496", fontWeight: "bold" }}>BREAK-EVEN (BE)</div>
                    <div style={{ fontSize: 9.5, fontWeight: "bold", color: useBe ? "#ffd600" : "#8ca5b5" }}>
                        {useBe
                            ? `+${fmtNum(beLock, dec)}p (após +${fmtNum(beTrigger, dec)}p)`
                            : `OFF · OCO 1:1 (${timeStopMin}m)`}
                    </div>
                </div>
                <div>
                    <div style={{ fontSize: 7, color: "#6c8496", fontWeight: "bold" }}>METODOLOGIA</div>
                    <div style={{ fontSize: 9, fontWeight: "bold", color: "#00d4ff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {methodLabel}
                    </div>
                </div>
            </div>

            {/* Faixa de KPIs Financeiros do Dia */}
            <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 0.9fr", gap: 6 }}>
                <div style={{ background: "#060b12", border: `1px solid ${curveColor}44`, borderRadius: 7, padding: "5px 8px" }}>
                    <div style={{ fontSize: 7.5, color: "#7f96a8", fontWeight: "bold" }}>SALDO ACUMULADO ({contracts}c)</div>
                    <div style={{ fontSize: 14, fontWeight: 900, color: curveColor, fontFamily: "monospace" }}>
                        {totalBrl >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(totalBrl), 0)}
                        <span style={{ fontSize: 9.5, color: "#9fb4c4", fontWeight: "normal", marginLeft: 5 }}>
                            ({fmtNum(cumPts, dec, true)}p)
                        </span>
                    </div>
                </div>
                <div style={{ background: "#060b12", border: "1px solid #152535", borderRadius: 7, padding: "5px 8px" }}>
                    <div style={{ fontSize: 7.5, color: "#7f96a8", fontWeight: "bold" }}>FATOR DE LUCRO</div>
                    <div style={{ fontSize: 13, fontWeight: "bold", color: profitFactor >= 1.5 ? "#00e87a" : "#f5a623", fontFamily: "monospace" }}>
                        {fmtNum(profitFactor, 2)}x
                        <span style={{ fontSize: 8.5, color: "#7f96a8", marginLeft: 4 }}>
                            ({chronoSignals.length} ops)
                        </span>
                    </div>
                </div>
                <div style={{ background: "#060b12", border: "1px solid #152535", borderRadius: 7, padding: "5px 8px" }}>
                    <div style={{ fontSize: 7.5, color: "#7f96a8", fontWeight: "bold" }}>DRAWDOWN MÁX</div>
                    <div style={{ fontSize: 12.5, fontWeight: "bold", color: "#ff6b8b", fontFamily: "monospace" }}>
                        -R$ {fmtNum(maxDrawdownPts * brlPerPt * contracts, 0)}
                    </div>
                </div>
            </div>

            {/* Gráfico SVG da Curva de Capital Intraday */}
            <svg
                viewBox={`0 0 ${w} ${h}`}
                style={{ width: "100%", height: "auto", display: "block", background: "#04070c", borderRadius: 7, border: "1px solid #132230", cursor: "crosshair" }}
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
                            <rect x={padL + plotW + 2} y={yLast - 8} width={padR - 4} height={15} rx="3" fill="#071914" stroke={curveColor} strokeWidth="1" />
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
                background: "#060b12",
                padding: "4px 8px",
                borderRadius: 5,
                border: "1px solid #142230",
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
        </div>
    );
}

/* ── COMPONENTE DO COCKPIT DE 1 ATIVO (ESQUERDA: FLUXO REAL | DIREITA: A.S.G HUD + CURVA DE CAPITAL) ── */
function SingleAssetCockpitView({ symKey, payload }) {
    const [selectedSigId, setSelectedSigId] = useState(null);
    const [showHistory, setShowHistory] = useState(false);

    if (!payload) return null;

    const dec = symKey === "WDO" ? 1 : 0;
    const ca = payload.caminho_a || {};
    const sc = ca.signals_scorecard || {};
    const signalsLog = ca.signals_log || [];
    const series = ca.m5_dealer_vs_flow_series || [];
    const flowWindows = ca.flow_windows || [];
    const asgHud = ca.asg_hud || {};
    const radar = payload.walls_radar || {};
    const allWalls = payload.all_walls || [];

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "2.1fr 1fr", gap: 14, alignItems: "stretch" }}>
                {/* Esquerda (68%): Gráfico Triplo Sincronizado Fluxo Real + A.S.G */}
                <FluxoRealAsgChart
                    symKey={symKey}
                    series={series}
                    flowWindows={flowWindows}
                    asgHud={asgHud}
                    wallsRadar={radar}
                    allWalls={allWalls}
                    vwap={payload.vwap}
                    selectedSigId={selectedSigId}
                    onSelectSignal={(id) => {
                        setSelectedSigId(id);
                        setShowHistory(true);
                    }}
                />

                {/* Direita (32%): HUD Visual Instantâneo A.S.G + Gráfico de Capital das Operações do Dia */}
                <div style={{ display: "flex", flexDirection: "column", gap: 12, justifyContent: "space-between" }}>
                    <AsgCockpitHud
                        symKey={symKey}
                        payload={payload}
                        asgHud={asgHud}
                        scorecard={sc}
                        showHistory={showHistory}
                        onToggleHistory={() => setShowHistory(s => !s)}
                    />
                    <DailyOperationsEquityChart
                        symKey={symKey}
                        signalsLog={signalsLog}
                        scorecard={sc}
                        selectedSigId={selectedSigId}
                        onSelectSignal={(id) => {
                            setSelectedSigId(id);
                            setShowHistory(true);
                        }}
                    />
                </div>
            </div>

            {/* Tabela Retrátil de Janelas e Sinais (só aparece se o usuário clicar em "Ver Sinais do Dia") */}
            {showHistory && (
                <div style={{
                    background: "#080f17",
                    border: "1px solid #18293a",
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
            <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#4a6070", fontSize: 10, background: "#090e14", borderRadius: 6, border: "1px solid #16222c" }}>
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
        <div style={{ background: "#090e14", borderRadius: 6, border: "1px solid #16222c", padding: "6px 8px" }}>
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
            background: "#0b121a",
            border: "1px solid #18293a",
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
                    <tr style={{ textAlign: "right", background: "#070c12", fontWeight: "bold" }}>
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
                <div style={{ background: "#070c12", padding: "7px 9px", borderRadius: 5, border: "1px solid #142430" }}>
                    <div style={{ fontSize: 8.5, color: "#00e87a", fontWeight: "bold", marginBottom: 4 }}>🏦 TOP COMPRADORES LÍQUIDOS (PROFIT)</div>
                    {(payload.top_buyers || []).slice(0, 5).map(b => (
                        <div key={b.broker} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, padding: "2px 0", borderBottom: "1px solid #0f1922" }}>
                            <span style={{ color: b.is_institutional ? "#ffffff" : "#8ca5b5", fontWeight: b.is_institutional ? "bold" : "normal" }}>
                                {b.broker} {b.is_institutional ? "🏦" : ""}
                            </span>
                            <span style={{ color: "#00e87a", fontFamily: "monospace" }}>
                                +{fmtNum(b.net, 0)} <span style={{ color: "#657d8f", fontSize: 8 }}>(Agr:{fmtNum((b.aggr_buy || 0) - (b.aggr_sell || 0), 0, true)} | Pas:{fmtNum((b.passive_buy || 0) - (b.passive_sell || 0), 0, true)})</span>
                            </span>
                        </div>
                    ))}
                </div>
                <div style={{ background: "#070c12", padding: "7px 9px", borderRadius: 5, border: "1px solid #142430" }}>
                    <div style={{ fontSize: 8.5, color: "#ff3860", fontWeight: "bold", marginBottom: 4 }}>🏦 TOP VENDEDORES LÍQUIDOS (PROFIT)</div>
                    {(payload.top_sellers || []).slice(0, 5).map(b => (
                        <div key={b.broker} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, padding: "2px 0", borderBottom: "1px solid #0f1922" }}>
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
                        <th style={{ padding: "3px 4px" }}>GEX</th>
                        <th style={{ padding: "3px 4px" }}>DELTA INST NA LINHA</th>
                        <th style={{ padding: "3px 4px" }}>STATUS</th>
                    </tr>
                </thead>
                <tbody>
                    {resWalls.map((w, i) => (
                        <tr key={`r-${i}`} style={{ borderBottom: "1px solid #111b24", textAlign: "right" }}>
                            <td style={{ textAlign: "left", padding: "3px 4px", color: "#ff6b8b", fontWeight: "bold" }}>▲ RES · {w.type}</td>
                            <td style={{ padding: "3px 4px", color: "#e6edf3", fontWeight: "bold" }}>{fmtNum(w.price, dec)}</td>
                            <td style={{ padding: "3px 4px", color: "#8ca5b5" }}>{fmtNum(w.dist_pts, dec, true)}p</td>
                            <td style={{ padding: "3px 4px", color: "#00d4ff" }}>{w.gex_formatted || "—"}</td>
                            <td style={{ padding: "3px 4px", color: (w.inst_delta || 0) >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                            <td style={{ padding: "3px 4px", color: "#9fb4c4" }}>{w.status}</td>
                        </tr>
                    ))}
                    <tr style={{ background: "rgba(0, 212, 255, 0.12)", textAlign: "center", fontWeight: "bold" }}>
                        <td colSpan={6} style={{ padding: "4px", color: "#00d4ff" }}>
                            ◄ PREÇO SPOT ATUAL: {fmtNum(payload.last_price, dec)} (VWAP: {fmtNum(payload.vwap, dec)}) ►
                        </td>
                    </tr>
                    {supWalls.map((w, i) => (
                        <tr key={`s-${i}`} style={{ borderBottom: "1px solid #111b24", textAlign: "right" }}>
                            <td style={{ textAlign: "left", padding: "3px 4px", color: "#00e87a", fontWeight: "bold" }}>▼ SUP · {w.type}</td>
                            <td style={{ padding: "3px 4px", color: "#e6edf3", fontWeight: "bold" }}>{fmtNum(w.price, dec)}</td>
                            <td style={{ padding: "3px 4px", color: "#8ca5b5" }}>{fmtNum(w.dist_pts, dec, true)}p</td>
                            <td style={{ padding: "3px 4px", color: "#00d4ff" }}>{w.gex_formatted || "—"}</td>
                            <td style={{ padding: "3px 4px", color: (w.inst_delta || 0) >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                            <td style={{ padding: "3px 4px", color: "#9fb4c4" }}>{w.status}</td>
                        </tr>
                    ))}
                </tbody>
            </table>

            {/* Gráfico CVD Institucional vs Varejo vs Dealers */}
            <MiniSvgChart
                series={ca.m5_dealer_vs_flow_series || []}
                keys={["cvd_inst", "cum_dealer_hedge", "cvd_retail"]}
                colors={["#00e87a", "#c8a444", "#00d4ff"]}
                labels={["CVD Institucional", "Hedge Acum. Dealers (GEX)", "CVD Varejo"]}
                height={110}
            />
        </div>
    );
}

/* ── COMPONENTE PRINCIPAL EXPORTADO ────────────────────────────────────────── */
export default function IntradayCompassPanel({ compassData, mode = "COCKPIT", onChangeMode, selectedDate = "", onSelectDate }) {
    const [selectedAsset, setSelectedAsset] = useState("WIN"); // "WIN" | "WDO" | "DUAL"

    if (!compassData || !compassData.WIN) {
        return (
            <div style={{
                background: "#0b121a",
                border: "1px solid #1c2c3b",
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
                    background: isSel ? "rgba(0, 212, 255, 0.08)" : "#080d14",
                    border: isSel ? `2px solid ${accent}` : "1px solid #18293a",
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
                        background: isSel ? accent : `${accent}1a`,
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
                    background: `${cmdColor}18`,
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

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
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
                            background: selectedAsset === "DUAL" ? "rgba(0, 232, 122, 0.18)" : "#080d14",
                            border: selectedAsset === "DUAL" ? "2px solid #00e87a" : "1px solid #18293a",
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
                        background: "#080d14",
                        border: isHistView ? "2px solid #d4af37" : "1px solid #18293a",
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
                                border: !isHistView ? "1.5px solid #00e87a" : "1px solid #1c2e3e",
                                background: !isHistView ? "rgba(0, 232, 122, 0.18)" : "#0d151e",
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
                                    border: activeDate === yesterdayDateStr ? "1.5px solid #d4af37" : "1px solid #1c2e3e",
                                    background: activeDate === yesterdayDateStr ? "rgba(212, 175, 55, 0.22)" : "#0d151e",
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
                                    background: "#0d151e",
                                    border: "1px solid #1c2e3e",
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
                selectedAsset === "DUAL" ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                        <SingleAssetCockpitView symKey="WIN" payload={winP} />
                        <SingleAssetCockpitView symKey="WDO" payload={wdoP} />
                    </div>
                ) : (
                    <SingleAssetCockpitView
                        symKey={selectedAsset}
                        payload={selectedAsset === "WIN" ? winP : wdoP}
                    />
                )
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
                            background: "#0b121a",
                            border: "1px solid #18293a",
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
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>IV ATM (NO DINHEIRO)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#00d4ff" }}>{fmtNum(volSurf.atm_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>IV PUT 25Δ (OTM)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#ff6b8b" }}>{fmtNum(volSurf.put_25d_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>IV CALL 25Δ (OTM)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#00e87a" }}>{fmtNum(volSurf.call_25d_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>SKEW 25Δ (PUT − CALL)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#c8a444" }}>{fmtNum(volSurf.skew_25d_pct, 2, true)}%</div>
                                </div>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>PCR VOLUME TOTAL</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#e6edf3" }}>{fmtNum(optComp.pcr_total_volume, 2)}</div>
                                </div>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
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
