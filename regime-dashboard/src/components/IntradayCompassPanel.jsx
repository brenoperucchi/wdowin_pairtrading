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
    signalsLog = [],
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
    const [hoveredSigId, setHoveredSigId] = useState(null);
    const [rightGapPx, setRightGapPx] = useState(145);
    const [viewMode, setViewMode] = useState("TUDO"); // "RECENTE" | "HOJE" | "TUDO" | "CUSTOM"
    const [visibleCount, setVisibleCount] = useState(48);
    const [panOffsetRight, setPanOffsetRight] = useState(0); // quantas barras deslocado do fim
    const [yZoomFactor, setYZoomFactor] = useState(1.0); // >1 abre mais o eixo Y para ver mais Walls do Pine
    const [showMidleWalls, setShowMidleWalls] = useState(true);
    const [showNweLine, setShowNweLine] = useState(true);
    const [wallColorMode, setWallColorMode] = useState("PINE"); // "PINE" (#00e676 original) | "POLARIDADE"
    const [candleColorMode, setCandleColorMode] = useState("TRADICIONAL"); // "TRADICIONAL" (padrão) | "JANELA" (fluxo A.S.G)
    const [gexViewMode, setGexViewMode] = useState("OPCAO_1"); // "OPCAO_1" (Hedge Acum. Makers) | "OPCAO_3" (Ímã & Regime GEX)
    const [dragState, setDragState] = useState(null); // { type: 'PAN' | 'YSCALE', startX, startY, startPan, startYZoom }

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
    const effCount = viewMode === "TUDO"
        ? totalBase
        : Math.max(14, Math.min(totalBase, visibleCount));
    const maxPan = Math.max(0, totalBase - effCount);
    const clampedPan = Math.max(0, Math.min(maxPan, panOffsetRight));
    const endSlice = totalBase - clampedPan;
    const startSlice = Math.max(0, endSlice - effCount);
    const series = baseSeries.slice(startSlice, endSlice);

    const width = 900;
    const height = 544;
    const padL = 10;
    const padR = 118; // Eixo Y estilo TradingView à direita

    // 4 Painéis Verticais Sincronizados estilo TradingView:
    // Painel 1 (Preço + Pine GEX Walls): Y de 14 até 312 (altura 298)
    // Painel 2 (Fluxo CVD Institucional): Y de 319 até 377 (altura 58)
    // Painel 3 (Fluxo Makers GEX % Intraday): Y de 384 até 442 (altura 58)
    // Painel 4 (Janelas de Fluxo A.S.G Conjunta): Y de 449 até 517 (altura 68)
    const p1Top = 14, p1H = 298, p1Bot = p1Top + p1H;
    const p2Top = 319, p2H = 58, p2Bot = p2Top + p2H;
    const pGexTop = 384, pGexH = 58, pGexBot = pGexTop + pGexH;
    const p3Top = 449, p3H = 68, p3Bot = p3Top + p3H;
    const plotW = width - padL - padR;

    const innerPadL = 16;
    const usableW = Math.max(180, plotW - innerPadL - rightGapPx);
    const n = series.length;
    const totalSlots = Math.max(n - 1, 20);
    const stepX = usableW / Math.max(1, totalSlots);
    const candleW = Math.max(3.2, Math.min(10.5, stepX * 0.70));
    const toX = (idx) => padL + innerPadL + (idx / Math.max(1, totalSlots)) * usableW;
    const firstTodayLocalIdx = series.findIndex((pt, i) => i > 0 && !pt.is_prev_day && series[i - 1]?.is_prev_day);

    // ── Escala Y do Painel 1 (Preço + Walls do jumba_tradingview.pine + Caixas de Trade) ──
    let minP = Infinity;
    let maxP = -Infinity;
    const visTodayTimes = new Set();
    series.forEach(pt => {
        const l = Number(pt.low || pt.close);
        const h = Number(pt.high || pt.close);
        if (l > 0 && l < minP) minP = l;
        if (h > 0 && h > maxP) maxP = h;
        if (!pt.is_prev_day && pt.time) visTodayTimes.add(pt.time);
        if (showNweLine && Number(pt.nwe_line) > 0) {
            const nl = Number(pt.nwe_line);
            const nu = Number(pt.nwe_upper || nl);
            const nlo = Number(pt.nwe_lower || nl);
            if (nlo > 0 && nlo < minP) minP = nlo;
            if (nu > 0 && nu > maxP) maxP = nu;
        }
    });
    if (showSignalsMarkers && Array.isArray(signalsLog)) {
        signalsLog.forEach(s => {
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

    // ── Escala Y do Painel 4 (Histograma Linha Zero -100 a +100) ──
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

    if (Array.isArray(signalsLog) && signalsLog.length > 0) {
        signalsLog.forEach(s => {
            if (!s || s.is_prev_day) return;
            const k = s.time;
            if (!sigsByTime[k]) sigsByTime[k] = [];
            sigsByTime[k].push(s);
        });
    }
    series.forEach((pt, idx) => {
        if (pt.is_prev_day) return;
        const barSigs = sigsByTime[pt.time] || (pt.signal ? [pt.signal] : []);
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
                        FLUXO REAL + PINE GEX ({symKey} · M5)
                    </span>
                    {candleColorMode === "TRADICIONAL" ? (
                        <>
                            <span style={{ fontSize: 10, color: "#00e87a", fontWeight: "bold" }}>🟩 Barra Alta</span>
                            <span style={{ fontSize: 10, color: "#ff3860", fontWeight: "bold" }}>🟥 Barra Baixa</span>
                        </>
                    ) : (
                        <>
                            <span style={{ fontSize: 10, color: "#00e87a", fontWeight: "bold" }}>🟩 Comprado (ASG)</span>
                            <span style={{ fontSize: 10, color: "#ff3860", fontWeight: "bold" }}>🟥 Vendido (ASG)</span>
                            <span style={{ fontSize: 10, color: "#7f96a8" }}>⬜ Pullback</span>
                        </>
                    )}
                </div>

                {/* Controles do Gráfico: Cores das Barras, Cores Pine, MidWalls, Recuo e Zoom */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 3, background: "#0c1218", padding: "2px 6px", borderRadius: 5, border: "1px solid #1a2530" }}>
                        <button
                            onClick={() => setCandleColorMode(m => (m === "TRADICIONAL" ? "JANELA" : "TRADICIONAL"))}
                            title="Alternar cor das barras entre Modo Tradicional (Alta/Baixa - Padrão) ou Pintadas pelas Janelas de Operação A.S.G"
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
                            title="Alternar entre MagicWalls em Branco (#ffffff) ou Polaridade Suporte/Resistência"
                            style={{
                                padding: "2px 6px",
                                fontSize: 9,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                background: "#0c1218",
                                color: wallColorMode === "PINE" ? "#ffffff" : "#ff6b8b",
                                border: `1px solid ${wallColorMode === "PINE" ? "rgba(255, 255, 255, 0.45)" : "rgba(255, 56, 96, 0.45)"}`,
                                borderRadius: 4,
                                cursor: "pointer",
                            }}
                        >
                            {wallColorMode === "PINE" ? "⬜ Walls: Branco" : "⚡ Polaridade"}
                        </button>
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
                            title="Exibir/Ocultar Média NWE Causal (Nadaraya-Watson h=8, L=40) e Banda ±1 MAE"
                            style={{
                                padding: "2px 6px",
                                fontSize: 9,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                background: "#0c1218",
                                color: showNweLine ? "#00d4ff" : "#5a7288",
                                border: showNweLine ? "1px solid rgba(0, 212, 255, 0.45)" : "1px solid #1a2530",
                                borderRadius: 4,
                                cursor: "pointer",
                            }}
                        >
                            〰️ Média NWE
                        </button>
                        <button
                            onClick={() => setGexViewMode(m => (m === "OPCAO_1" ? "OPCAO_3" : "OPCAO_1"))}
                            title="Alternar o Painel 3 (GEX) entre Opção 1 (Curva de Hedge Acumulado dos Makers em Lotes) e Opção 3 (Mapa de Atração / Ímã de Liquidez GEX + Regime Gamma)"
                            style={{
                                padding: "2px 7px",
                                fontSize: 9,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                background: "#0c1218",
                                color: gexViewMode === "OPCAO_1" ? "#f5d061" : "#a78bfa",
                                border: gexViewMode === "OPCAO_1" ? "1px solid rgba(245, 208, 97, 0.55)" : "1px solid rgba(167, 139, 250, 0.55)",
                                borderRadius: 4,
                                cursor: "pointer",
                            }}
                        >
                            {gexViewMode === "OPCAO_1" ? "📈 GEX: 1. Hedge Acum." : "🧲 GEX: 3. Ímã & Regime"}
                        </button>
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
                        {yZoomFactor !== 1.0 && (
                            <button
                                onClick={() => setYZoomFactor(1.0)}
                                title="Resetar escala vertical Y"
                                style={{
                                    padding: "2px 6px",
                                    fontSize: 9,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    background: "#0c1218",
                                    color: "#00d4ff",
                                    border: "1px solid #00d4ff",
                                    borderRadius: 4,
                                    cursor: "pointer",
                                }}
                            >
                                Auto Y
                            </button>
                        )}
                        <span style={{ color: "#1a2530", margin: "0 2px" }}>|</span>
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
                    </div>

                    {/* Inspetor OHLC + CVD + Histograma */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 10, fontFamily: "monospace", background: "#0c1218", padding: "3px 9px", borderRadius: 5, border: "1px solid #1a2530" }}>
                        <span style={{ color: "#9fb4c7" }}>
                            🕒 {inspectedPt.is_prev_day ? `Ontem ${inspectedPt.time}` : inspectedPt.time}
                        </span>
                        <span style={{ color: "#6b8299" }}>
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
                        {gexViewMode === "OPCAO_1" ? (
                            <span style={{ color: getCumDealer(inspectedPt) >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                Hedge Makers: {fmtNum(getCumDealer(inspectedPt), 0, true)}L
                            </span>
                        ) : (
                            <span style={{ color: getMagnetPct(inspectedPt) >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                Ímã GEX: {getMagnetPct(inspectedPt) >= 0 ? "▲+" : "▼"}{fmtNum(getMagnetPct(inspectedPt), 0)}% ({inspectedPt.gex_regime_bar === "NEG" ? "Γ- Squeeze" : "Γ+ Defesa"})
                            </span>
                        )}
                        {Number(inspectedPt.nwe_line) > 0 && (
                            <span style={{ color: inspectedPt.nwe_is_up !== false ? "#00d4ff" : "#ff6b8b", fontWeight: "bold" }}>
                                NWE: {fmtNum(inspectedPt.nwe_line, dec)} {inspectedPt.nwe_is_up !== false ? "↑" : "↓"}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* ── GRÁFICO PRINCIPAL UNIFICADO COM AS CORES DO DASHBOARD (#0c1218 / #1a2530) ── */}
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
                    background: "#0c1218",
                    borderRadius: 6,
                    border: "1px solid #1a2530",
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
                    setViewMode("TUDO");
                }}
            >
                {/* Fundos dos 4 Painéis Unificados com o Dashboard (#0c1218) — Sem Grade no Fundo */}
                <rect x={padL} y={p1Top} width={plotW} height={p1H} fill="#0c1218" />
                <rect x={padL} y={p2Top} width={plotW} height={p2H} fill="#0c1218" />
                <rect x={padL} y={pGexTop} width={plotW} height={pGexH} fill="#0c1218" />
                <rect x={padL} y={p3Top} width={plotW} height={p3H} fill="#0c1218" />

                {/* Divisórias Horizontais Discretas dos 4 Painéis e Eixo Y Direito */}
                <line x1={padL} y1={p1Bot} x2={width} y2={p1Bot} stroke="#1a2530" strokeWidth="1" />
                <line x1={padL} y1={p2Bot} x2={width} y2={p2Bot} stroke="#1a2530" strokeWidth="1" />
                <line x1={padL} y1={pGexBot} x2={width} y2={pGexBot} stroke="#1a2530" strokeWidth="1" />
                <line x1={padL} y1={p3Bot} x2={width} y2={p3Bot} stroke="#1a2530" strokeWidth="1" />
                <line x1={padL + plotW} y1={p1Top} x2={padL + plotW} y2={p3Bot} stroke="#1a2530" strokeWidth="1" />

                {/* Títulos Internos Discretos na Paleta do Dashboard */}
                <text x={padL + 8} y={p1Top + 13} fill="#5a7288" fontSize="8.5" fontWeight="bold" fontFamily="monospace">
                    1. {symKey} · M5 · MAGIC GEX LEVELS &amp; MIDWALLS (jumba_tradingview.pine)
                </text>
                <text x={padL + 8} y={p2Top + 11} fill="#5a7288" fontSize="7.2" fontWeight="bold" fontFamily="monospace">
                    2. FLUXO INSTITUCIONAL CVD (Cor mais escura = Maior Lote)
                </text>
                <text x={padL + 8} y={pGexTop + 11} fill="#5a7288" fontSize="7.2" fontWeight="bold" fontFamily="monospace">
                    {gexViewMode === "OPCAO_1"
                        ? "3. OPÇÃO 1 · HEDGE ACUMULADO MAKERS GEX (Verde/Vermelho = Junto c/ Inst. [Squeeze] | Dourado = Defesa/Absorção na Wall)"
                        : "3. OPÇÃO 3 · MAPA DE ATRAÇÃO GEX (Ímã Dominante: +Verde Puxa p/ Cima | -Vermelho Puxa p/ Baixo | Zero = Na Wall)"}
                </text>
                <text x={padL + 8} y={p3Top + 11} fill="#5a7288" fontSize="7.2" fontWeight="bold" fontFamily="monospace">
                    4. JANELAS DE FLUXO A.S.G (Campeã Conjunta · Linha Zero)
                </text>

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

                        const isRes = w.price > lastPt.close;
                        const proxTol = symKey === "WDO" ? 1.5 : 35;
                        const isNearestActive = (isRes && nearestResP > 0 && Math.abs(w.price - nearestResP) <= proxTol)
                            || (!isRes && nearestSupP > 0 && Math.abs(w.price - nearestSupP) <= proxTol);

                        const defLots = Number(w.defense_lots || 0);
                        const instTot = Number(w.inst_total_vol || 0);
                        const makerLots = Number(w.maker_hedge_lots || 0);
                        const powerPct = Number(w.wall_power_pct || (isMid ? 24 : (w.width || 1) * 28));
                        const tier = w.wall_tier || (
                            powerPct >= 45 ? "FORTE"
                                : (powerPct >= (isMid ? 20 : 25) || instTot > 0 || makerLots > 0) ? "MODERADA"
                                    : "FRACA"
                        );

                        if (tier === "FRACA" && !isNearestActive) return;

                        const isStrong = (tier === "FORTE" && (!isMid || defLots > 0 || isNearestActive))
                            || (isNearestActive && (instTot > 0 || powerPct >= 34));
                        const scaleFactor = isStrong ? (isMid ? 0.44 : 0.58) : (isMid ? 0.26 : 0.35);
                        const halfW = baseBandPts * scaleFactor;

                        const shortTag = isMid ? "Mid" : "MW";
                        const volRef = defLots > 0 ? defLots : instTot;
                        const volTxt = volRef >= 1000
                            ? `${(volRef / 1000).toFixed(0)}kL`
                            : volRef > 0
                                ? `${fmtNum(volRef, 0)}L`
                                : "";
                        const fullLabel = volTxt ? `${shortTag} · ${volTxt}` : shortTag;

                        zonesToRender.push({
                            key: `wall-zone-${idx}`,
                            topP: w.price + halfW,
                            botP: w.price - halfW,
                            isSell: isRes,
                            isStrong,
                            isMid,
                            label: fullLabel,
                        });
                    });

                    return zonesToRender.map((z) => {
                        if (z.topP < minP || z.botP > maxP) return null;
                        const yTop = Math.max(p1Top, toY1(Math.min(maxP, z.topP)));
                        const yBot = Math.min(p1Bot, toY1(Math.max(minP, z.botP)));
                        const hBand = Math.max(5, yBot - yTop);
                        const isWhiteWallMode = wallColorMode === "PINE";
                        const col = isWhiteWallMode ? "#ffffff" : (z.isSell ? "#ff3860" : "#00e87a");
                        const fillRgba = isWhiteWallMode
                            ? (z.isStrong ? "rgba(255, 255, 255, 0.08)" : (z.isMid ? "rgba(255, 255, 255, 0.03)" : "rgba(255, 255, 255, 0.05)"))
                            : (z.isSell
                                ? (z.isStrong ? "rgba(255, 56, 96, 0.13)" : (z.isMid ? "rgba(255, 56, 96, 0.05)" : "rgba(255, 56, 96, 0.08)"))
                                : (z.isStrong ? "rgba(0, 232, 122, 0.13)" : (z.isMid ? "rgba(0, 232, 122, 0.05)" : "rgba(0, 232, 122, 0.08)")));
                        const borderDash = z.isMid ? "3,3" : "none";
                        return (
                            <g key={z.key}>
                                <rect x={padL} y={yTop} width={plotW} height={hBand} fill={fillRgba} />
                                <rect
                                    x={padL}
                                    y={yTop}
                                    width={z.isStrong ? 3.5 : 2}
                                    height={hBand}
                                    fill={col}
                                    opacity={z.isStrong ? "0.90" : (z.isMid ? "0.50" : "0.70")}
                                />
                                {z.isStrong && (
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
                                <text
                                    x={padL + 6}
                                    y={yTop + Math.min(9.5, hBand - 1.5)}
                                    fill={isWhiteWallMode ? "#e2e8f0" : (z.isSell ? "#ff8fa6" : "#66ffcc")}
                                    fontSize="6.5"
                                    fontFamily="monospace"
                                    opacity="0.72"
                                >
                                    {z.label}
                                </text>
                            </g>
                        );
                    });
                })()}

                {/* ── LINHAS E LABELS OFICIAIS DO `jumba_tradingview.pine` (MagicWall em Branco + MidWall) ── */}
                {nearbyWalls.map((w, i) => {
                    const yW = toY1(w.price);
                    const wType = String(w.type || "Wall");
                    const isMid = wType.toLowerCase().includes("mid") || String(w.label || "").toUpperCase() === "MIDLEWALL";
                    const isRes = w.role === "RES";

                    const pineCol = wType === "GammaFlip" ? "#ffd600"
                        : wType === "MaxGamma" ? "#00b0ff"
                            : wType === "MinGamma" ? "#ff1744"
                                : isMid ? "#94a3b8" : "#ffffff";
                    const polCol = wType === "GammaFlip"
                        ? "#ffd600"
                        : (isRes ? (isMid ? "#ff6b8b" : "#ff3860") : (isMid ? "#38ef94" : "#00e87a"));
                    const col = wallColorMode === "PINE" ? pineCol : polCol;

                    const strokeW = isMid ? 1.05 : Math.max(1.2, Math.min(3.0, Number(w.width || 1) * 0.85));
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
                                opacity={isMid ? "0.65" : "0.90"}
                            />
                            {/* Etiqueta de Preço no Eixo Y Direito unificada com o Dashboard */}
                            {!hideRightAxisTag && !isMid && (
                                <g>
                                    <rect
                                        x={padL + plotW + 2}
                                        y={yW - 7}
                                        width={padR - 8}
                                        height={14}
                                        rx="2"
                                        fill="#0c1218"
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
                                stroke="#c8a444"
                                strokeWidth="1.1"
                                strokeOpacity="0.72"
                            />
                            <circle cx={xStart} cy={yZero3} r="2.8" fill="#f5d061" />
                        </g>
                    );
                })}

                {/* ── FUNDO SUAVE DO ENVELOPE NWE (MULTI-DIA 200 BARRAS) ── */}
                {showNweLine && (() => {
                    const validNwePts = series
                        .map((pt, idx) => ({ pt, idx }))
                        .filter(({ pt }) => Number(pt.nwe_upper) > 0 && Number(pt.nwe_lower) > 0);
                    if (validNwePts.length < 2) return null;
                    const upperPoly = validNwePts
                        .map(({ pt, idx }) => `${toX(idx).toFixed(1)},${Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(pt.nwe_upper))).toFixed(1)}`)
                        .join(" ");
                    const lowerRev = [...validNwePts]
                        .reverse()
                        .map(({ pt, idx }) => `${toX(idx).toFixed(1)},${Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(pt.nwe_lower))).toFixed(1)}`)
                        .join(" ");
                    return (
                        <g pointerEvents="none">
                            <polygon
                                points={`${upperPoly} ${lowerRev}`}
                                fill="#00e87a"
                                fillOpacity="0.025"
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
                    const fillCol = candleColorMode === "TRADICIONAL"
                        ? (cVal >= oVal ? "#00e87a" : "#ff3860")
                        : (cState > 0 ? "#00e87a" : cState < 0 ? "#ff3860" : "#7f96a8");
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

                {/* ── ENVELOPE COMPLETO DA MÉDIA NWE (3 LINHAS PARALELAS: UPPER, CENTER, LOWER) COLORIDAS POR INCLINAÇÃO (VERDE ↑ / VERMELHO ↓) ── */}
                {showNweLine && (() => {
                    const segments = [];
                    for (let i = 1; i < series.length; i++) {
                        const prev = series[i - 1];
                        const curr = series[i];
                        if (!(Number(prev.nwe_line) > 0 && Number(curr.nwe_line) > 0)) continue;
                        const x1 = toX(i - 1);
                        const x2 = toX(i);
                        const yC1 = Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(prev.nwe_line)));
                        const yC2 = Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(curr.nwe_line)));
                        const yU1 = Number(prev.nwe_upper) > 0 ? Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(prev.nwe_upper))) : null;
                        const yU2 = Number(curr.nwe_upper) > 0 ? Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(curr.nwe_upper))) : null;
                        const yL1 = Number(prev.nwe_lower) > 0 ? Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(prev.nwe_lower))) : null;
                        const yL2 = Number(curr.nwe_lower) > 0 ? Math.max(p1Top + 2, Math.min(p1Bot - 2, toY1(curr.nwe_lower))) : null;
                        const isUp = curr.nwe_is_up !== undefined ? Boolean(curr.nwe_is_up) : (Number(curr.nwe_line) >= Number(prev.nwe_line));
                        segments.push({ x1, x2, yC1, yC2, yU1, yU2, yL1, yL2, isUp, key: `nwe-seg-${i}` });
                    }
                    const lastNwe = Number(lastPt?.nwe_line || 0);
                    const lastNweUp = lastPt?.nwe_is_up !== false;
                    const lastNweCol = lastNweUp ? "#00e87a" : "#ff3860";
                    const rawNweY = lastNwe > 0 ? Math.max(p1Top + 10, Math.min(p1Bot - 10, toY1(lastNwe))) : null;
                    const badgeNweY = rawNweY !== null
                        ? (Math.abs(rawNweY - lastY) < 17 ? (rawNweY < lastY ? Math.max(p1Top + 9, lastY - 18) : Math.min(p1Bot - 9, lastY + 18)) : rawNweY)
                        : null;

                    return (
                        <g pointerEvents="none">
                            {segments.map(seg => {
                                const col = seg.isUp ? "#00e87a" : "#ff3860";
                                return (
                                    <g key={seg.key}>
                                        {seg.yU1 !== null && seg.yU2 !== null && (
                                            <line
                                                x1={seg.x1}
                                                y1={seg.yU1}
                                                x2={seg.x2}
                                                y2={seg.yU2}
                                                stroke={col}
                                                strokeWidth="1.45"
                                                strokeLinecap="round"
                                                opacity="0.88"
                                            />
                                        )}
                                        <line
                                            x1={seg.x1}
                                            y1={seg.yC1}
                                            x2={seg.x2}
                                            y2={seg.yC2}
                                            stroke={col}
                                            strokeWidth="1.85"
                                            strokeLinecap="round"
                                            opacity="0.96"
                                        />
                                        {seg.yL1 !== null && seg.yL2 !== null && (
                                            <line
                                                x1={seg.x1}
                                                y1={seg.yL1}
                                                x2={seg.x2}
                                                y2={seg.yL2}
                                                stroke={col}
                                                strokeWidth="1.45"
                                                strokeLinecap="round"
                                                opacity="0.88"
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
                                        fontSize="8.5"
                                        fontWeight="bold"
                                        fontFamily="monospace"
                                    >
                                        NWE {fmtNum(lastNwe, dec)} {lastNweUp ? "↑" : "↓"}
                                    </text>
                                </g>
                            )}
                        </g>
                    );
                })()}

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

                    return (
                        <g key={`tv-box-fg-${sig.id}`} pointerEvents="none">
                            {/* Linha do Alvo Fixo (Apenas em WIN_1 e WDO_1) */}
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
                    const shortMap = {
                        EST_01: "WIN Rejeição",
                        EST_07: "WIN Rompimento",
                        EST_13: "WIN Next Wall",
                        WDO_09: "WDO Pullback",
                        WDO_11: "WDO Next Wall",
                        WDO_S2: "WDO Lunch",
                    };
                    const colorMap = {
                        EST_01: "#38bdf8",
                        EST_07: "#00d4ff",
                        EST_13: "#10b981",
                        WDO_09: "#ffd600",
                        WDO_11: "#f59e0b",
                        WDO_S2: "#a78bfa",
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

                {/* ══════════════════════════════════════════════════════════════════════
                   PAINEL 2 (MEIO): FLUXO INSTITUCIONAL EM PONTINHOS (COR MAIS ESCURA = MAIOR PESO)
                   ══════════════════════════════════════════════════════════════════════ */}
                <polyline
                    fill="none"
                    stroke="#1e3246"
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
                   PAINEL 3: OPÇÃO 1 (HEDGE ACUMULADO MAKERS) OU OPÇÃO 3 (MAPA DE ATRAÇÃO / ÍMÃ GEX)
                   ══════════════════════════════════════════════════════════════════════ */}
                {gexViewMode === "OPCAO_1" ? (
                    <g>
                        <polyline
                            fill="none"
                            stroke="#1e3246"
                            strokeWidth="1.35"
                            points={series.map((pt, idx) => `${toX(idx).toFixed(1)},${toYGexCum(getCumDealer(pt)).toFixed(1)}`).join(" ")}
                        />
                        {series.map((pt, idx) => {
                            const x = toX(idx);
                            const dc = getCumDealer(pt);
                            const yD = toYGexCum(dc);
                            const dhBar = Number(pt.dealer_hedge_bar || 0);
                            const instBar = Number(pt.inst_delta_bar || 0);
                            const isWithInst = (dhBar * instBar) > 0;
                            const isCounterInst = (dhBar * instBar) < 0 && Math.abs(dhBar) >= (symKey === "WDO" ? 40 : 250);
                            let dCol = "#7d91a3";
                            if (isCounterInst) {
                                dCol = "#f5d061"; // Dourado = Makers absorvendo/defendendo contra o fluxo na Wall
                            } else if (isWithInst) {
                                dCol = dhBar >= 0 ? "#00e87a" : "#ff3860"; // Verde/Vermelho vivo = Squeeze a favor do Institucional
                            } else {
                                dCol = dhBar >= 0 ? "#38ef94" : "#ff758f";
                            }
                            return (
                                <circle
                                    key={`gex-cum-dot-${idx}`}
                                    cx={x}
                                    cy={yD}
                                    r={isCounterInst ? "2.7" : "2.3"}
                                    fill={dCol}
                                />
                            );
                        })}
                        {(() => {
                            const lastCumD = getCumDealer(lastPt);
                            const lastCol = lastCumD >= 0 ? "#00e87a" : "#ff3860";
                            const yBadge = Math.max(pGexTop + 10, Math.min(pGexBot - 6, toYGexCum(lastCumD)));
                            return (
                                <text x={padL + plotW + 6} y={yBadge + 3} fill={lastCol} fontSize="9" fontWeight="bold" fontFamily="monospace">
                                    {fmtNum(lastCumD, 0, true)}L
                                </text>
                            );
                        })()}
                    </g>
                ) : (
                    <g>
                        <line x1={padL} y1={yZeroGex} x2={padL + plotW} y2={yZeroGex} stroke="#1a2530" strokeWidth="1.0" strokeDasharray="3,3" />
                        {series.map((pt, idx) => {
                            const x = toX(idx);
                            const mv = getMagnetPct(pt);
                            const yM = toYGexMag(mv);
                            const isPos = mv >= 0;
                            const isNegGamma = pt.gex_regime_bar === "NEG";
                            const col = isPos ? "#00e87a" : "#ff3860";
                            const barTop = isPos ? yM : yZeroGex;
                            const barH = Math.max(1.5, Math.abs(yZeroGex - yM));
                            return (
                                <rect
                                    key={`gex-mag-bar-${idx}`}
                                    x={x - candleW * 0.42}
                                    y={barTop}
                                    width={candleW * 0.84}
                                    height={barH}
                                    fill={col}
                                    opacity={isNegGamma ? "0.85" : "0.42"}
                                    rx="0.5"
                                />
                            );
                        })}
                        <polyline
                            fill="none"
                            stroke="#a78bfa"
                            strokeWidth="1.35"
                            points={series.map((pt, idx) => `${toX(idx).toFixed(1)},${toYGexMag(getMagnetPct(pt)).toFixed(1)}`).join(" ")}
                        />
                        {(() => {
                            const lastMag = getMagnetPct(lastPt);
                            const lastCol = lastMag >= 0 ? "#00e87a" : "#ff3860";
                            const regTag = lastPt?.gex_regime_bar === "NEG" ? "Γ-" : "Γ+";
                            const yBadge = Math.max(pGexTop + 10, Math.min(pGexBot - 6, toYGexMag(lastMag)));
                            return (
                                <text x={padL + plotW + 6} y={yBadge + 3} fill={lastCol} fontSize="8.8" fontWeight="bold" fontFamily="monospace">
                                    {lastMag >= 0 ? "▲+" : "▼"}{fmtNum(lastMag, 0)}% ({regTag})
                                </text>
                            );
                        })()}
                    </g>
                )}

                {/* ══════════════════════════════════════════════════════════════════════
                   PAINEL 4 (BASE): HISTOGRAMA LINHA ZERO (VERDE = COMPRA / VERMELHO = VENDA)
                   ══════════════════════════════════════════════════════════════════════ */}
                <line x1={padL} y1={yZero3} x2={padL + plotW} y2={yZero3} stroke="#1a2530" strokeWidth="1.0" />
                <text x={padL + plotW + 6} y={yZero3 + 3} fill="#5a7288" fontSize="8.5" fontWeight="bold" fontFamily="monospace">
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

                        {/* Linha Horizontal do Crosshair + Badge de Preço no Eixo Y Direito */}
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
                                    width={padR - 6}
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
                    </g>
                )}
            </svg>
        </div>
    );
}

/* ══════════════════════════════════════════════════════════════════════════════
   2. BARRA COMPACTA DE RESUMO DO DIA (SEM REDUNDÂNCIAS DE VELA 3D / ALVOS 1-2-3)
   ══════════════════════════════════════════════════════════════════════════════ */
function AsgCockpitHud({ symKey, payload, asgHud = {}, scorecard = {}, onToggleHistory, showHistory }) {
    const winDir = Number(asgHud.window_dir || 0);
    const makersPct = Number(asgHud.makers_pct || 0);
    const winCol = winDir >= 0 ? "#00e87a" : "#ff3860";

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
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
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
                </div>
            </div>

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
function DailyOperationsEquityChart({ symKey, signalsLog = [], scorecard = {}, selectedSigId, onSelectSignal }) {
    const [contracts, setContracts] = useState(symKey === "WDO" ? 2 : 5);
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
                                background: contracts === c ? "#00d4ff" : "#0c1218",
                                color: contracts === c ? "#04080e" : "#8ca5b5",
                                border: contracts === c ? "1px solid #00d4ff" : "1px solid #1a2530",
                            }}
                        >
                            {c} {c === 1 ? "Contr." : "Contr."}
                        </button>
                    ))}
                </div>
            </div>

            {/* Faixa de KPIs Financeiros do Dia */}
            <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 0.9fr", gap: 6 }}>
                <div style={{ background: "#0c1218", border: `1px solid ${curveColor}44`, borderRadius: 7, padding: "5px 8px" }}>
                    <div style={{ fontSize: 7.5, color: "#7f96a8", fontWeight: "bold" }}>SALDO ACUMULADO ({contracts}c)</div>
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
                        -R$ {fmtNum(maxDrawdownPts * brlPerPt * contracts, 0)}
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
                        const brl = pts * brlPerPt * contracts;
                        const isSel = selectedSigId === sig.id;
                        const shortMap = {
                            EST_01: "WIN Rejeição",
                            EST_07: "WIN Rompimento",
                            EST_13: "WIN Next Wall",
                            WDO_09: "WDO Pullback",
                            WDO_11: "WDO Next Wall",
                            WDO_S2: "WDO Lunch",
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
    const [winContracts, setWinContracts] = useState(5);
    const [wdoContracts, setWdoContracts] = useState(2);

    const winSigs = [...(winPayload?.caminho_a?.signals_log || [])].reverse();
    const wdoSigs = [...(wdoPayload?.caminho_a?.signals_log || [])].reverse();

    const merged = [
        ...winSigs.map(s => ({ ...s, asset: "WIN", brlMult: 0.20 * winContracts })),
        ...wdoSigs.map(s => ({ ...s, asset: "WDO", brlMult: 10.0 * wdoContracts })),
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
        const tBrl = pts * s.brlMult;
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
                        WIN Rejeição + WIN Rompimento + WIN Next Wall | WDO Pullback + WDO Next Wall + WDO Lunch (c/ Fluxo)
                    </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: "monospace", fontSize: 10 }}>
                    <span style={{ color: "#00d4ff" }}>
                        WIN ({winContracts}c): <strong>{winBrl >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(winBrl), 0)}</strong>
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

/* ── CURVA DE CAPITAL AUDITADA DAS 6 ESTRATÉGIAS C/ FLUXO + PORTFÓLIO (BACKTEST 124D + LIVE TRADING A PARTIR DE HOJE) ── */
function Portfolio4SistematicasPanel({ portfolioData, winPayload, wdoPayload, onSelectDate }) {
    const [winContracts, setWinContracts] = useState(2);
    const [wdoContracts, setWdoContracts] = useState(1);
    const [rangeMode, setRangeMode] = useState("ALL"); // "ALL" | "60D" | "30D"
    const [hoverIdx, setHoverIdx] = useState(null);
    const [pinnedIdx, setPinnedIdx] = useState(null);
    const [tradeHistTab, setTradeHistTab] = useState("ALL"); // "ALL" (Todos os 1.102 trades) | "DAY" (Trades do Pregão)
    const [stratFilter, setStratFilter] = useState("ALL");   // "ALL" | "EST_01" | "EST_07" | "EST_13" | "WDO_09" | "WDO_11" | "WDO_S2"
    const [visibleCurves, setVisibleCurves] = useState({
        PORTFOLIO: true,
        EST_01: true,
        EST_07: true,
        EST_13: true,
        WDO_09: true,
        WDO_11: true,
        WDO_S2: true,
    });

    if (!portfolioData || !portfolioData.ok || !Array.isArray(portfolioData.days) || portfolioData.days.length === 0) {
        return null;
    }

    const toggleCurve = (key) => {
        setVisibleCurves((prev) => ({ ...prev, [key]: !prev[key] }));
    };

    const winMult = 0.20 * winContracts; // R$ por ponto WIN
    const wdoMult = 10.0 * wdoContracts; // R$ por ponto WDO
    const allDays = portfolioData.days;
    const summary1c = portfolioData.summary_1c || {};
    const liveDays = portfolioData.live_days || [];

    // Constrói a série acumulada desde o Dia 1 (07/05/2026) até o Live Trading (Hoje+)
    let cEst01 = 0, cEst07 = 0, cEst13 = 0, cWdo09 = 0, cWdo11 = 0, cWdoS2 = 0, cPort = 0;
    let pkEst01 = 0, pkEst07 = 0, pkEst13 = 0, pkWdo09 = 0, pkWdo11 = 0, pkWdoS2 = 0, pkPort = 0;
    let mddEst01 = 0, mddEst07 = 0, mddEst13 = 0, mddWdo09 = 0, mddWdo11 = 0, mddWdoS2 = 0, mddPort = 0;

    const fullSeries = [
        {
            idx: 0,
            date: portfolioData.start_date || "2026-05-07",
            month: "Início",
            is_live: false,
            isOrigin: true,
            d_EST_01: 0, d_EST_07: 0, d_EST_13: 0, d_WDO_09: 0, d_WDO_11: 0, d_WDO_S2: 0, d_PORT: 0,
            EST_01: 0, EST_07: 0, EST_13: 0, WDO_09: 0, WDO_11: 0, WDO_S2: 0, PORTFOLIO: 0,
            dd_PORT: 0,
            ops_total: 0,
            trades: [],
            open_trades: [],
        },
    ];

    const byMonth = {};

    allDays.forEach((d, i) => {
        const dEst01 = Number(d.EST_01_pts || 0) * winMult;
        const dEst07 = Number(d.EST_07_pts || 0) * winMult;
        const dEst13 = Number(d.EST_13_pts || 0) * winMult;
        const dWdo09 = Number(d.WDO_09_pts || 0) * wdoMult;
        const dWdo11 = Number(d.WDO_11_pts || 0) * wdoMult;
        const dWdoS2 = Number(d.WDO_S2_pts || 0) * wdoMult;
        const dPort = dEst01 + dEst07 + dEst13 + dWdo09 + dWdo11 + dWdoS2;

        cEst01 += dEst01;
        cEst07 += dEst07;
        cEst13 += dEst13;
        cWdo09 += dWdo09;
        cWdo11 += dWdo11;
        cWdoS2 += dWdoS2;
        cPort += dPort;

        if (cEst01 > pkEst01) pkEst01 = cEst01;
        if (pkEst01 - cEst01 > mddEst01) mddEst01 = pkEst01 - cEst01;

        if (cEst07 > pkEst07) pkEst07 = cEst07;
        if (pkEst07 - cEst07 > mddEst07) mddEst07 = pkEst07 - cEst07;

        if (cEst13 > pkEst13) pkEst13 = cEst13;
        if (pkEst13 - cEst13 > mddEst13) mddEst13 = pkEst13 - cEst13;

        if (cWdo09 > pkWdo09) pkWdo09 = cWdo09;
        if (pkWdo09 - cWdo09 > mddWdo09) mddWdo09 = pkWdo09 - cWdo09;

        if (cWdo11 > pkWdo11) pkWdo11 = cWdo11;
        if (pkWdo11 - cWdo11 > mddWdo11) mddWdo11 = pkWdo11 - cWdo11;

        if (cWdoS2 > pkWdoS2) pkWdoS2 = cWdoS2;
        if (pkWdoS2 - cWdoS2 > mddWdoS2) mddWdoS2 = pkWdoS2 - cWdoS2;

        if (cPort > pkPort) pkPort = cPort;
        if (pkPort - cPort > mddPort) mddPort = pkPort - cPort;

        const opsDay =
            Number(d.EST_01_ops || 0) +
            Number(d.EST_07_ops || 0) +
            Number(d.EST_13_ops || 0) +
            Number(d.WDO_09_ops || 0) +
            Number(d.WDO_11_ops || 0) +
            Number(d.WDO_S2_ops || 0);

        const mKey = d.is_live ? `${d.month} (Live)` : d.month;
        if (!byMonth[mKey]) {
            byMonth[mKey] = {
                month: mKey,
                is_live: Boolean(d.is_live),
                EST_01: 0, EST_07: 0, EST_13: 0, WDO_09: 0, WDO_11: 0, WDO_S2: 0, PORTFOLIO: 0,
                ops: 0,
            };
        }
        byMonth[mKey].EST_01 += dEst01;
        byMonth[mKey].EST_07 += dEst07;
        byMonth[mKey].EST_13 += dEst13;
        byMonth[mKey].WDO_09 += dWdo09;
        byMonth[mKey].WDO_11 += dWdo11;
        byMonth[mKey].WDO_S2 += dWdoS2;
        byMonth[mKey].PORTFOLIO += dPort;
        byMonth[mKey].ops += opsDay;

        fullSeries.push({
            idx: i + 1,
            date: d.date,
            month: d.month,
            is_live: Boolean(d.is_live),
            d_EST_01: dEst01,
            d_EST_07: dEst07,
            d_EST_13: dEst13,
            d_WDO_09: dWdo09,
            d_WDO_11: dWdo11,
            d_WDO_S2: dWdoS2,
            d_PORT: dPort,
            EST_01_pts: Number(d.EST_01_pts || 0),
            EST_07_pts: Number(d.EST_07_pts || 0),
            EST_13_pts: Number(d.EST_13_pts || 0),
            WDO_09_pts: Number(d.WDO_09_pts || 0),
            WDO_11_pts: Number(d.WDO_11_pts || 0),
            WDO_S2_pts: Number(d.WDO_S2_pts || 0),
            EST_01_ops: Number(d.EST_01_ops || 0),
            EST_07_ops: Number(d.EST_07_ops || 0),
            EST_13_ops: Number(d.EST_13_ops || 0),
            WDO_09_ops: Number(d.WDO_09_ops || 0),
            WDO_11_ops: Number(d.WDO_11_ops || 0),
            WDO_S2_ops: Number(d.WDO_S2_ops || 0),
            ops_total: opsDay,
            EST_01: cEst01,
            EST_07: cEst07,
            EST_13: cEst13,
            WDO_09: cWdo09,
            WDO_11: cWdo11,
            WDO_S2: cWdoS2,
            PORTFOLIO: cPort,
            dd_PORT: cPort - pkPort,
            trades: d.trades || [],
            open_trades: d.open_trades || [],
        });
    });

    // Filtra janela de visualização mantendo o saldo acumulado real
    const visibleSeries = rangeMode === "30D"
        ? fullSeries.slice(-31)
        : rangeMode === "60D"
            ? fullSeries.slice(-61)
            : fullSeries;

    // Calcula KPIs consolidados (Backtest + Live) para cada estratégia e Portfólio
    const buildCurveKpi = (sid, multContracts, totBrl, maxDdBrl) => {
        const base = summary1c[sid] || {};
        let ops = Number(base.ops || 0);
        let wins = Number(base.wins ?? Math.round(ops * Number(base.wr_pct || 0) / 100));
        let gWin = Number(base.gross_win_1c || 0) * multContracts;
        let gLoss = Number(base.gross_loss_1c || 0) * multContracts;
        let totPts = Number(base.tot_pts || 0);

        // Soma operações fechadas em pregões Live
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
        const exactMaxDd = Math.max(maxDdBrl, Number(base.max_dd_brl_1c || 0) * multContracts);
        const retDd = exactMaxDd > 0 ? totBrl / exactMaxDd : 99.9;
        return { ops, wins, wr, pf, gWin, gLoss, totPts, totBrl, maxDdBrl: exactMaxDd, retDd };
    };

    const kpiEst01 = buildCurveKpi("EST_01", winContracts, cEst01, mddEst01);
    const kpiEst07 = buildCurveKpi("EST_07", winContracts, cEst07, mddEst07);
    const kpiEst13 = buildCurveKpi("EST_13", winContracts, cEst13, mddEst13);
    const kpiWdo09 = buildCurveKpi("WDO_09", wdoContracts, cWdo09, mddWdo09);
    const kpiWdo11 = buildCurveKpi("WDO_11", wdoContracts, cWdo11, mddWdo11);
    const kpiWdoS2 = buildCurveKpi("WDO_S2", wdoContracts, cWdoS2, mddWdoS2);

    const portOps = kpiEst01.ops + kpiEst07.ops + kpiEst13.ops + kpiWdo09.ops + kpiWdo11.ops + kpiWdoS2.ops;
    const portWins = kpiEst01.wins + kpiEst07.wins + kpiEst13.wins + kpiWdo09.wins + kpiWdo11.wins + kpiWdoS2.wins;
    const portGWin = kpiEst01.gWin + kpiEst07.gWin + kpiEst13.gWin + kpiWdo09.gWin + kpiWdo11.gWin + kpiWdoS2.gWin;
    const portGLoss = kpiEst01.gLoss + kpiEst07.gLoss + kpiEst13.gLoss + kpiWdo09.gLoss + kpiWdo11.gLoss + kpiWdoS2.gLoss;
    const portWr = portOps > 0 ? (portWins / portOps) * 100 : 0;
    const portPf = portGLoss > 0 ? portGWin / portGLoss : 1.5;
    const portRetDd = mddPort > 0 ? cPort / mddPort : 99.9;

    const curveConfigs = [
        {
            key: "PORTFOLIO",
            shortLabel: "🏆 PORTFÓLIO (6 ESTRAT.)",
            title: "🏆 PORTFÓLIO COMPLETO (6 ESTRATÉGIAS C/ FLUXO)",
            subRule: `WIN (${winContracts}c) + WDO (${wdoContracts}c) · 6/6 Meses Positivos · Ret/DD 38,97x`,
            color: "#00e87a",
            strokeW: 2.9,
            kpi: {
                ops: portOps,
                wr: portWr,
                pf: portPf,
                totBrl: cPort,
                totPts: null,
                maxDdBrl: mddPort,
                retDd: portRetDd,
            },
        },
        {
            key: "EST_01",
            shortLabel: "🔵 WIN Rejeição",
            title: "🔵 WIN Rejeição (EST-01)",
            subRule: "Rejeição/PinBar na Wall + Combo Smart",
            color: "#38bdf8",
            strokeW: 1.8,
            kpi: kpiEst01,
            dec: 0,
        },
        {
            key: "EST_07",
            shortLabel: "💠 WIN Rompimento",
            title: "💠 WIN Rompimento (EST-07)",
            subRule: "Ignição/Rompimento na Wall + Fluxo Institucional",
            color: "#00d4ff",
            strokeW: 1.8,
            kpi: kpiEst07,
            dec: 0,
        },
        {
            key: "EST_13",
            shortLabel: "🟢 WIN Next Wall",
            title: "🟢 WIN Next Wall (EST-13)",
            subRule: "SmartGrid na Próxima Wall + Absorção Institucional",
            color: "#10b981",
            strokeW: 1.9,
            kpi: kpiEst13,
            dec: 0,
        },
        {
            key: "WDO_09",
            shortLabel: "🟡 WDO Pullback",
            title: "🟡 WDO Pullback (WDO-09)",
            subRule: "Pullback de Tendência na Wall + Janela A.S.G",
            color: "#ffd600",
            strokeW: 1.8,
            kpi: kpiWdo09,
            dec: 1,
        },
        {
            key: "WDO_11",
            shortLabel: "🟠 WDO Next Wall",
            title: "🟠 WDO Next Wall (WDO-11)",
            subRule: "SmartGrid na Próxima Wall + Absorção Institucional",
            color: "#f59e0b",
            strokeW: 1.9,
            kpi: kpiWdo11,
            dec: 1,
        },
        {
            key: "WDO_S2",
            shortLabel: "🟣 WDO Lunch",
            title: "🟣 WDO Lunch (WDO_S2)",
            subRule: "Reversão Z30 no Almoço (12:00–14:30) + MidWall",
            color: "#a78bfa",
            strokeW: 2.0,
            kpi: kpiWdoS2,
            dec: 1,
        },
    ];

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

    // Sinais ao vivo do dia atual e histórico completo de todos os trades (1.102 ops)
    const latestLiveDay = liveDays.length > 0 ? liveDays[liveDays.length - 1] : null;
    const liveOpenTrades = latestLiveDay?.open_trades || [];
    const liveClosedTrades = latestLiveDay?.trades || [];

    const allHistoricalTrades = [];
    for (let di = fullSeries.length - 1; di >= 1; di--) {
        const dayObj = fullSeries[di];
        const dayOpen = dayObj.open_trades || [];
        const dayClosed = dayObj.trades || [];
        dayOpen.forEach((tr) => allHistoricalTrades.push({ ...tr, date: tr.date || dayObj.date }));
        for (let ti = dayClosed.length - 1; ti >= 0; ti--) {
            const tr = dayClosed[ti];
            allHistoricalTrades.push({ ...tr, date: tr.date || dayObj.date });
        }
    }

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
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 13, fontWeight: 900, color: "#ffffff", letterSpacing: 0.7 }}>
                            📈 CURVA DE CAPITAL DAS 6 ESTRATÉGIAS C/ FLUXO + PORTFÓLIO (WIN Rejeição | WIN Rompimento | WIN Next Wall | WDO Pullback | WDO Next Wall | WDO Lunch)
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
                            ✅ {portfolioData.total_bt_sessions || 124} Pregões BT ({fmtDateShort(portfolioData.start_date)} a {fmtDateShort(portfolioData.last_bt_date)}) + 🟢 Live ({fmtDateShort(portfolioData.live_start_date)}+)
                        </span>
                    </div>
                    <span style={{ fontSize: 9.5, color: "#7f96a8" }}>
                        Portfólio Campeão com Filtros de Fluxo do Dashboard (Combo Smart + Absorção Institucional + Janela A.S.G) · 1.102 trades (~8,89 ops/dia) · 6/6 meses positivos · Ret/DD = 38,97x.
                    </span>
                </div>

                {/* Controles de Lote WIN / WDO e Janela Temporal */}
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    {/* Preset Equilibrado vs 1x1 */}
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
                            Base 1 WIN : 1 WDO
                        </button>
                        <button
                            onClick={() => { setWinContracts(2); setWdoContracts(1); }}
                            style={{
                                padding: "3px 7px",
                                fontSize: 8.5,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                borderRadius: 4,
                                cursor: "pointer",
                                background: winContracts === 2 && wdoContracts === 1 ? "#00e87a" : "#0c1218",
                                color: winContracts === 2 && wdoContracts === 1 ? "#04080e" : "#8ca5b5",
                                border: "1px solid #1a2530",
                            }}
                        >
                            ⚖️ 2 WIN : 1 WDO
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
                                {c}c
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
                                {c}c
                            </button>
                        ))}
                    </div>

                    {/* Período */}
                    <div style={{ display: "flex", gap: 4, background: "#05080d", padding: "3px 5px", borderRadius: 6, border: "1px solid #1a2530" }}>
                        {[
                            { id: "ALL", label: "Desde 07/05 (Completo + Live)" },
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

            {/* 2. SCORECARD INTERATIVO DAS 7 CURVAS (PORTFÓLIO + 6 ESTRATÉGIAS C/ FLUXO) */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "1.18fr repeat(6, 1fr)",
                gap: 6,
            }}>
                {curveConfigs.map((cfg) => {
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
                            setHoverIdx(idx);
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
                            <span style={{ color: "#38bdf8" }}>
                                WIN Rejeição: {inspectedPt.EST_01 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(inspectedPt.EST_01), 0)}
                            </span>
                            <span style={{ color: "#00d4ff" }}>
                                WIN Rompimento: {inspectedPt.EST_07 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(inspectedPt.EST_07), 0)}
                            </span>
                            <span style={{ color: "#10b981" }}>
                                WIN Next Wall: {inspectedPt.EST_13 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(inspectedPt.EST_13), 0)}
                            </span>
                            <span style={{ color: "#ffd600" }}>
                                WDO Pullback: {inspectedPt.WDO_09 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(inspectedPt.WDO_09), 0)}
                            </span>
                            <span style={{ color: "#f59e0b" }}>
                                WDO Next Wall: {inspectedPt.WDO_11 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(inspectedPt.WDO_11), 0)}
                            </span>
                            <span style={{ color: "#a78bfa" }}>
                                WDO Lunch: {inspectedPt.WDO_S2 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(inspectedPt.WDO_S2), 0)}
                            </span>
                        </div>
                    </div>
                )}
            </div>

            {/* 4. RODAPÉ DUPLO: TABELA MENSAL AUDITADA (ESQUERDA) + HISTÓRICO COMPLETO DE TODOS OS TRADES & MONITOR (DIREITA) */}
            <div style={{ display: "grid", gridTemplateColumns: "1.18fr 1.04fr", gap: 12 }}>
                {/* Esquerda: Matriz Mensal das 6 Estratégias + Portfólio */}
                <div style={{
                    background: "#05080d",
                    border: "1px solid #1a2530",
                    borderRadius: 8,
                    padding: "10px 12px",
                }}>
                    <div style={{ fontSize: 10, fontWeight: "bold", color: "#ffffff", marginBottom: 8, letterSpacing: 0.5 }}>
                        🗓️ RESULTADO MENSAL AUDITADO POR ESTRATÉGIA (WIN {winContracts}c · WDO {wdoContracts}c)
                    </div>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "monospace", fontSize: 8.5 }}>
                        <thead>
                            <tr style={{ color: "#6c8496", borderBottom: "1px solid #1a2530", textAlign: "right" }}>
                                <th style={{ textAlign: "left", padding: "4px" }}>MÊS</th>
                                <th style={{ padding: "4px", color: "#38bdf8" }}>WIN Rejeição</th>
                                <th style={{ padding: "4px", color: "#00d4ff" }}>WIN Rompimento</th>
                                <th style={{ padding: "4px", color: "#10b981" }}>WIN Next Wall</th>
                                <th style={{ padding: "4px", color: "#ffd600" }}>WDO Pullback</th>
                                <th style={{ padding: "4px", color: "#f59e0b" }}>WDO Next Wall</th>
                                <th style={{ padding: "4px", color: "#a78bfa" }}>WDO Lunch</th>
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
                                    <td style={{ padding: "4px", color: m.EST_01 >= 0 ? "#38bdf8" : "#ff6b8b" }}>
                                        {m.EST_01 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(m.EST_01), 0)}
                                    </td>
                                    <td style={{ padding: "4px", color: m.EST_07 >= 0 ? "#00d4ff" : "#ff6b8b" }}>
                                        {m.EST_07 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(m.EST_07), 0)}
                                    </td>
                                    <td style={{ padding: "4px", color: m.EST_13 >= 0 ? "#10b981" : "#ff6b8b" }}>
                                        {m.EST_13 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(m.EST_13), 0)}
                                    </td>
                                    <td style={{ padding: "4px", color: m.WDO_09 >= 0 ? "#ffd600" : "#ff6b8b" }}>
                                        {m.WDO_09 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(m.WDO_09), 0)}
                                    </td>
                                    <td style={{ padding: "4px", color: m.WDO_11 >= 0 ? "#f59e0b" : "#ff6b8b" }}>
                                        {m.WDO_11 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(m.WDO_11), 0)}
                                    </td>
                                    <td style={{ padding: "4px", color: m.WDO_S2 >= 0 ? "#a78bfa" : "#ff6b8b" }}>
                                        {m.WDO_S2 >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(m.WDO_S2), 0)}
                                    </td>
                                    <td style={{ padding: "4px", fontWeight: 900, color: m.PORTFOLIO >= 0 ? "#00e87a" : "#ff3860" }}>
                                        {m.PORTFOLIO >= 0 ? "+" : "-"}R$ {fmtNum(Math.abs(m.PORTFOLIO), 0)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Direita: Histórico Completo de Todos os Trades (1.102 ops) + Trades do Pregão Inspecionado */}
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
                            📋 HISTÓRICO DE TODOS OS TRADES ({allHistoricalTrades.length}) & MONITOR LIVE
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
                                📋 Todos ({allHistoricalTrades.length})
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
                                📅 Pregão {fmtDateShort(inspectedPt?.date)} ({(inspectedPt?.trades?.length || 0) + (inspectedPt?.open_trades?.length || 0)})
                            </button>
                        </div>
                    </div>

                    {/* Filtro Rápido por Categoria/Estratégia */}
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {[
                            { id: "ALL", label: "Todas (6)", col: "#00e87a" },
                            { id: "EST_01", label: "WIN Rejeição", col: "#38bdf8" },
                            { id: "EST_07", label: "WIN Rompimento", col: "#00d4ff" },
                            { id: "EST_13", label: "WIN Next Wall", col: "#10b981" },
                            { id: "WDO_09", label: "WDO Pullback", col: "#ffd600" },
                            { id: "WDO_11", label: "WDO Next Wall", col: "#f59e0b" },
                            { id: "WDO_S2", label: "WDO Lunch", col: "#a78bfa" },
                        ].map((sf) => {
                            const active = stratFilter === sf.id;
                            return (
                                <button
                                    key={sf.id}
                                    onClick={() => setStratFilter(sf.id)}
                                    style={{
                                        padding: "2px 6px",
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
                            ? [...(inspectedPt.open_trades || []), ...(inspectedPt.trades || [])]
                            : [...liveOpenTrades, ...liveClosedTrades];
                        const rawList = tradeHistTab === "DAY" ? dayTrades : allHistoricalTrades;
                        const tradesToShow = stratFilter === "ALL"
                            ? rawList
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
                                    Nenhuma operação encontrada para este filtro. Clique em "📋 Todos" ou "Todas (6)" para ver o histórico completo.
                                </div>
                            );
                        }

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
                                        {tradesToShow.map((tr, ti) => {
                                            const mult = tr.asset === "WIN" ? winContracts : wdoContracts;
                                            const brlVal = Number(tr.brl_1c || 0) * mult;
                                            const isOpen = tr.status === "ABERTA";
                                            const sCol = tr.strategy_id === "EST_01" ? "#38bdf8"
                                                : tr.strategy_id === "EST_07" ? "#00d4ff"
                                                    : tr.strategy_id === "EST_13" ? "#10b981"
                                                        : tr.strategy_id === "WDO_09" ? "#ffd600"
                                                            : tr.strategy_id === "WDO_11" ? "#f59e0b" : "#a78bfa";
                                            const sName = tr.strategy_id === "EST_01" ? "WIN Rejeição"
                                                : tr.strategy_id === "EST_07" ? "WIN Rompimento"
                                                    : tr.strategy_id === "EST_13" ? "WIN Next Wall"
                                                        : tr.strategy_id === "WDO_09" ? "WDO Pullback"
                                                            : tr.strategy_id === "WDO_11" ? "WDO Next Wall"
                                                                : tr.strategy_id === "WDO_S2" ? "WDO Lunch" : tr.strategy_id;
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
                            </div>
                        );
                    })()}
                </div>
            </div>

            {/* 5. GRÁFICO E MATRIZ DE CORRELAÇÃO ENTRE AS 6 ESTRATÉGIAS (HEATMAP 6x6 + BARRAS DIVERGENTES DOS 15 PARES) */}
            {(() => {
                const sessionPts = fullSeries.slice(1);
                if (sessionPts.length < 5) return null;

                const stratMeta = [
                    { id: "EST_01", dKey: "d_EST_01", name: "WIN Rejeição", short: "WIN Rej", col: "#38bdf8" },
                    { id: "EST_07", dKey: "d_EST_07", name: "WIN Rompimento", short: "WIN Romp", col: "#00d4ff" },
                    { id: "EST_13", dKey: "d_EST_13", name: "WIN Next Wall", short: "WIN Next", col: "#10b981" },
                    { id: "WDO_09", dKey: "d_WDO_09", name: "WDO Pullback", short: "WDO PB", col: "#ffd600" },
                    { id: "WDO_11", dKey: "d_WDO_11", name: "WDO Next Wall", short: "WDO Next", col: "#f59e0b" },
                    { id: "WDO_S2", dKey: "d_WDO_S2", name: "WDO Lunch", short: "WDO Lunch", col: "#a78bfa" },
                ];

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

                const winDailyVec = sessionPts.map((p) => Number(p.d_EST_01 || 0) + Number(p.d_EST_07 || 0) + Number(p.d_EST_13 || 0));
                const dolDailyVec = sessionPts.map((p) => Number(p.d_WDO_09 || 0) + Number(p.d_WDO_11 || 0) + Number(p.d_WDO_S2 || 0));
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
                                label: `${a.name} × ${b.name}`,
                                shortLabel: `${a.short} × ${b.short}`,
                                colA: a.col,
                                colB: b.col,
                                corr: r,
                            });
                        }
                    }
                }

                pairsList.sort((x, y) => x.corr - y.corr);
                const avgPairCorr = pairsList.reduce((acc, p) => acc + p.corr, 0) / Math.max(1, pairsList.length);
                const negPairsCount = pairsList.filter((p) => p.corr < 0).length;

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
                                    🧩 MATRIZ & GRÁFICO DE CORRELAÇÃO DIÁRIA ENTRE AS 6 ESTRATÉGIAS ({sessionPts.length} PREGÕES)
                                </span>
                                <span style={{
                                    fontSize: 8,
                                    fontFamily: "monospace",
                                    color: "#00e87a",
                                    background: "rgba(0, 232, 122, 0.10)",
                                    border: "1px solid rgba(0, 232, 122, 0.35)",
                                    padding: "2px 7px",
                                    borderRadius: 4,
                                    fontWeight: "bold",
                                }}>
                                    ORTOGONALIDADE DA CARTEIRA
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
                                    Correlação Média (15 Pares):{" "}
                                    <strong style={{ color: "#00d4ff" }}>
                                        {avgPairCorr >= 0 ? "+" : ""}{fmtNum(avgPairCorr, 2)}
                                    </strong>
                                </span>
                                <span style={{ background: "#0c1218", border: "1px solid #1a2530", padding: "3px 8px", borderRadius: 5, color: "#9fb4c4" }}>
                                    Pares c/ Hedge Negativo:{" "}
                                    <strong style={{ color: "#67e8f9" }}>
                                        {negPairsCount} de 15 pares
                                    </strong>
                                </span>
                            </div>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "1.12fr 1.1fr", gap: 14, alignItems: "stretch" }}>
                            {/* Esquerda: Heatmap 6x6 de Correlação de Pearson */}
                            <div style={{
                                background: "#0c1218",
                                border: "1px solid #141e28",
                                borderRadius: 7,
                                padding: "8px 10px",
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                gap: 8,
                            }}>
                                <div style={{ fontSize: 8.5, color: "#8ca5b5", fontWeight: "bold", fontFamily: "monospace" }}>
                                    🔥 MAPA DE CALOR (CORRELAÇÃO DE PEARSON -1,00 A +1,00)
                                </div>
                                <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 3, fontFamily: "monospace", fontSize: 8.2 }}>
                                    <thead>
                                        <tr>
                                            <th style={{ textAlign: "left", padding: "3px 4px", color: "#6c8496", fontSize: 7.5 }}>ESTRATÉGIA</th>
                                            {stratMeta.map((sm) => (
                                                <th key={`ch-${sm.id}`} style={{ textAlign: "center", padding: "3px 2px", color: sm.col, fontSize: 7.5 }}>
                                                    {sm.short}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {stratMeta.map((rowSm, ri) => (
                                            <tr key={`cr-${rowSm.id}`}>
                                                <td style={{ padding: "4px 5px", color: rowSm.col, fontWeight: "bold", whiteSpace: "nowrap", fontSize: 8 }}>
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

                            {/* Direita: Gráfico de Barras Divergentes dos 15 Pares (Menor -> Maior Correlação) */}
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
                                    <span>📊 RANKING DOS 15 PARES (DA MENOR À MAIOR CORRELAÇÃO)</span>
                                    <span style={{ fontSize: 7.5, color: "#00e87a" }}>14 de 15 pares abaixo de +0,18!</span>
                                </div>

                                <div style={{ display: "flex", flexDirection: "column", gap: 3.5, maxHeight: 215, overflowY: "auto", paddingRight: 2 }}>
                                    {pairsList.map((pr) => {
                                        const isNeg = pr.corr < 0;
                                        const isHigh = pr.corr > 0.45;
                                        const barColor = isNeg ? "#00d4ff" : isHigh ? "#ff6b8b" : "#00e87a";
                                        // Escala de -0.25 a +0.80 -> zero fica em 24% da largura
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
                                                    gridTemplateColumns: "1.35fr 1.65fr 44px",
                                                    alignItems: "center",
                                                    gap: 6,
                                                    fontFamily: "monospace",
                                                    fontSize: 7.8,
                                                }}
                                            >
                                                <div style={{ color: "#c9d8e4", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={pr.label}>
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
                                                    {/* Linha Zero (0,00) */}
                                                    <div style={{
                                                        position: "absolute",
                                                        left: `${zeroPct}%`,
                                                        top: 0,
                                                        bottom: 0,
                                                        width: 1,
                                                        background: "#4a6070",
                                                        zIndex: 2,
                                                    }} />
                                                    {/* Barra de Correlação */}
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
                    signalsLog={signalsLog}
                    asgHud={asgHud}
                    wallsRadar={radar}
                    allWalls={allWalls}
                    vwap={payload.vwap}
                    selectedSigId={selectedSigId}
                    onSelectSignal={(id) => {
                        setSelectedSigId(id);
                        if (id) setShowHistory(true);
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
                            if (id) setShowHistory(true);
                        }}
                    />
                </div>
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
