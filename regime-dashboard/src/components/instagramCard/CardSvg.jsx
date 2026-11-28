// Componentes de desenho do card Instagram em SVG (movidos de InstagramCardModal.jsx sem alterações de comportamento).
import {
    computeCollisionFreeMarkers,
    formatBrNumber,
    describeSignalRule,
    formatPtsLabel,
} from "../../utils/instagramSignalMetrics";
import { FONT_MONO, FONT_SANS, INK, getCardDimensions } from "./theme";
import { formatDuration, getNweValues } from "./cardHelpers";

/* ══════════════════════════════════════════════════════════════════════════════
   SUB-COMPONENTE SVG: GRÁFICO LIMPO INK AZUL (PREÇO + WALLS + GAUSS + SINAIS + FLUXO)
   ══════════════════════════════════════════════════════════════════════════════ */
export function CleanChartSection({
    x,
    y,
    w,
    h,
    bars,
    walls,
    activeSignals,
    symKey,
    showFlow,
    showGauss,
    showWalls,
    showMidWalls = true,
    showDivLines,
    rulerMode,
    clipPrefix,
}) {
    const isWdo = String(symKey || "").toUpperCase() === "WDO";
    const dec = isWdo ? 1 : 0;

    const innerPadL = 18;
    const rightAxisW = 104;
    const plotLeft = x + innerPadL;
    const plotW = w - innerPadL - rightAxisW;
    const plotRight = plotLeft + plotW;

    const topBarH = 40;
    const timeAxisH = 34;
    const flowGap = showFlow ? 12 : 0;
    const flowH = showFlow ? Math.round((h - topBarH - timeAxisH - flowGap) * 0.27) : 0;
    const priceTop = y + topBarH;
    const priceH = h - topBarH - timeAxisH - flowGap - flowH;
    const priceBot = priceTop + priceH;
    const flowTop = priceBot + flowGap;
    const flowBot = flowTop + flowH;

    // Domínio de preço com margem confortável para evitar corte nos marcadores
    let minP = Infinity;
    let maxP = -Infinity;
    bars.forEach((b) => {
        const hi = Number(b.high ?? b.close);
        const lo = Number(b.low ?? b.close);
        if (Number.isFinite(hi) && hi > maxP) maxP = hi;
        if (Number.isFinite(lo) && lo < minP) minP = lo;
    });
    if (!Number.isFinite(minP) || !Number.isFinite(maxP) || maxP <= minP) {
        minP = 0;
        maxP = 100;
    }
    const rawSpan = Math.max(isWdo ? 5 : 120, maxP - minP);
    const padP = rawSpan * 0.19;
    const domMinP = minP - padP;
    const domMaxP = maxP + padP;
    const domSpanP = Math.max(1e-6, domMaxP - domMinP);

    const toYPrice = (p) => priceTop + ((domMaxP - Number(p)) / domSpanP) * priceH;

    const nBars = Math.max(1, bars.length);
    const xPadInner = 20;
    const usableW = Math.max(40, plotW - xPadInner * 2);
    const stepX = nBars > 1 ? usableW / (nBars - 1) : usableW;
    const toX = (idx) => plotLeft + xPadInner + idx * stepX;
    const candleW = Math.max(2.4, Math.min(8.5, stepX * 0.62));
    const flowBarW = Math.max(2.0, Math.min(7.5, stepX * 0.56));

    // Walls dentro da faixa visível (Walls, MidWalls e FlipWall)
    const visibleWalls = showWalls
        ? (walls || []).filter((wl) => {
            const px = Number(wl?.price);
            if (!Number.isFinite(px)) return false;
            const wt = String(wl?.type || "Wall");
            const isFlip = wt === "GammaFlip" || /flip/i.test(String(wl?.label || ""));
            const isMid = wt.toLowerCase().includes("mid") || String(wl?.label || "").toUpperCase() === "MIDLEWALL";
            if (isMid && !showMidWalls) return false;
            const isMain = wt === "Wall";
            if (!isMain && !isMid && !isFlip) return false;
            return px >= domMinP + domSpanP * 0.03 && px <= domMaxP - domSpanP * 0.03;
        })
        : [];

    const priceTicks = [];
    const tickCount = 5;
    for (let i = 0; i < tickCount; i += 1) {
        const val = domMinP + ((i + 0.5) / tickCount) * domSpanP;
        const rounded = isWdo ? Math.round(val * 2) / 2 : Math.round(val / 50) * 50;
        priceTicks.push({ val: rounded, y: toYPrice(rounded) });
    }

    // Domínio de fluxo
    let minW = 0;
    let maxW = 0;
    bars.forEach((b) => {
        const wv = Number(b?.smart_swing_wave || 0);
        if (wv < minW) minW = wv;
        if (wv > maxW) maxW = wv;
    });
    const absMaxW = Math.max(isWdo ? 120 : 1200, Math.abs(minW), Math.abs(maxW)) * 1.2;
    const flowPlotTop = flowTop + 28;
    const flowPlotBot = flowBot - 12;
    const flowPlotH = Math.max(20, flowPlotBot - flowPlotTop);
    const toYFlow = (v) => flowPlotTop + ((absMaxW - Number(v || 0)) / (2 * absMaxW)) * flowPlotH;
    const yZeroFlow = toYFlow(0);

    // Marcadores numerados sem colisão
    const markerRadius = h >= 720 ? 17 : 15;
    const markers = computeCollisionFreeMarkers(activeSignals, {
        toX,
        toY: toYPrice,
        bars,
        plotTop: priceTop + 8,
        plotBot: priceBot - 8,
        plotLeft: plotLeft + 6,
        plotRight: plotRight - 6,
        radius: markerRadius,
    });

    // Réguas no gráfico (âmbar #d4a259 para melhor pernada / moves vencedores)
    const rulerSignals = rulerMode === "OFF"
        ? []
        : rulerMode === "ALL"
            ? activeSignals.filter((s) => !s.isStopped && s.mfePts >= (isWdo ? 4 : 150))
            : activeSignals.filter((s) => !s.isStopped && s.isBest && s.mfePts > 0);

    // Eixo X de tempo
    const timeTicks = [];
    if (bars.length > 0) {
        const desired = 6;
        const stride = Math.max(1, Math.floor((bars.length - 1) / desired));
        for (let idx = 0; idx < bars.length; idx += stride) {
            timeTicks.push({ idx, x: toX(idx), label: String(bars[idx]?.time || "").slice(0, 5) });
        }
        const lastIdx = bars.length - 1;
        if (timeTicks.length && lastIdx - timeTicks[timeTicks.length - 1].idx >= Math.max(2, Math.floor(stride * 0.55))) {
            timeTicks.push({ idx: lastIdx, x: toX(lastIdx), label: String(bars[lastIdx]?.time || "").slice(0, 5) });
        }
    }

    // Canal Gauss (NWE100)
    const gaussPts = showGauss
        ? bars.map((b, idx) => ({ idx, ...getNweValues(b) })).filter((g) => g.upper > 0 && g.lower > 0)
        : [];

    const flowLinePts = showFlow
        ? bars.map((b, idx) => `${toX(idx).toFixed(1)},${toYFlow(b?.smart_swing_wave || 0).toFixed(1)}`).join(" ")
        : "";

    const lastBar = bars[bars.length - 1];
    const lastClose = Number(lastBar?.close ?? 0);
    const lastY = toYPrice(lastClose);

    const headerSubParts = [];
    if (showWalls) headerSubParts.push(showMidWalls ? "Walls · MidWalls · FlipWall" : "Walls · FlipWall");
    if (showGauss) headerSubParts.push("Canal Gauss");
    headerSubParts.push(activeSignals.length > 0 ? `Sinais 1–${activeSignals.length}` : "Sem sinais");
    const assetName = isWdo ? "Mini-Dólar" : "Mini-Índice";

    return (
        <g>
            <defs>
                <clipPath id={`${clipPrefix}-price`}>
                    <rect x={plotLeft} y={priceTop} width={plotW} height={priceH} />
                </clipPath>
                <clipPath id={`${clipPrefix}-flow`}>
                    <rect x={plotLeft} y={flowTop} width={plotW} height={flowH} />
                </clipPath>
            </defs>

            {/* Contorno externo fosco Ink Azul */}
            <rect
                x={x}
                y={y}
                width={w}
                height={h}
                rx="14"
                fill={INK.card}
                stroke={INK.hairline}
                strokeWidth="1.2"
            />

            {/* Fundo limpo da área de plotagem */}
            <rect
                x={plotLeft}
                y={priceTop}
                width={plotW}
                height={showFlow ? flowBot - priceTop : priceH}
                fill={INK.bg}
            />

            {/* Cabeçalho superior dentro do card do gráfico */}
            <text
                x={plotLeft + 4}
                y={y + 25}
                fill={INK.text1}
                fontSize="16"
                fontWeight="500"
                fontFamily={FONT_SANS}
            >
                {assetName} · M5
                <tspan fill={INK.text3} fontSize="14.5" fontWeight="400">
                    {"   "}{headerSubParts.join(" · ")}
                </tspan>
            </text>
            <text
                x={plotRight - 4}
                y={y + 25}
                fill={showDivLines ? INK.accentInk : INK.text3}
                fontSize="13.5"
                fontWeight="500"
                fontFamily={FONT_MONO}
                textAnchor="end"
            >
                Linhas div. {showDivLines ? "ON" : "OFF"}
            </text>
            <line x1={x + 1} y1={priceTop} x2={x + w - 1} y2={priceTop} stroke={INK.hairline} strokeWidth="1" />

            {/* Escala de preço no eixo Y (sem grade horizontal cruzando os candles) */}
            {priceTicks.map((t, i) => (
                <g key={`pgrid-${i}`}>
                    {!visibleWalls.some((wl) => Math.abs(toYPrice(wl.price) - t.y) < 26) && Math.abs(lastY - t.y) > 24 && (
                        <>
                            <line
                                x1={plotRight}
                                y1={t.y}
                                x2={plotRight + 4}
                                y2={t.y}
                                stroke={INK.hairline}
                                strokeWidth="1"
                            />
                            <text
                                x={plotRight + 10}
                                y={t.y + 4.5}
                                fill="#5d667a"
                                fontSize="13"
                                fontWeight="400"
                                fontFamily={FONT_MONO}
                            >
                                {formatBrNumber(t.val, dec)}
                            </text>
                        </>
                    )}
                </g>
            ))}

            {/* Separador eixo Y */}
            <line x1={plotRight} y1={priceTop} x2={plotRight} y2={priceBot} stroke={INK.hairline} strokeWidth="1" />

            {/* PANE DE PREÇO CLIPPADA */}
            <g clipPath={`url(#${clipPrefix}-price)`}>
                {/* Walls, MidWalls e FlipWall (âmbar #d4a259) */}
                {[...visibleWalls]
                    .sort((a, b) => {
                        const aFlip = String(a?.type || "") === "GammaFlip" || /flip/i.test(String(a?.label || ""));
                        const bFlip = String(b?.type || "") === "GammaFlip" || /flip/i.test(String(b?.label || ""));
                        return Number(aFlip) - Number(bFlip);
                    })
                    .map((wl, i) => {
                        const yW = toYPrice(wl.price);
                        const wt = String(wl.type || "Wall");
                        const isFlip = wt === "GammaFlip" || /flip/i.test(String(wl.label || ""));
                        const isMid = wt.toLowerCase().includes("mid") || String(wl?.label || "").toUpperCase() === "MIDLEWALL";
                        return (
                            <line
                                key={`ig-wall-${i}`}
                                x1={plotLeft}
                                y1={yW}
                                x2={plotRight}
                                y2={yW}
                                stroke={isFlip ? INK.flip : isMid ? "rgba(238, 240, 245, 0.22)" : "rgba(238, 240, 245, 0.42)"}
                                strokeWidth={isFlip ? "1.6" : isMid ? "1.0" : "1.35"}
                                strokeDasharray={isFlip ? "5,4" : isMid ? "4,4" : "none"}
                                strokeOpacity={isFlip ? "0.92" : "1"}
                            />
                        );
                    })}

                {/* Canal Gauss */}
                {gaussPts.length > 2 && (() => {
                    const up = gaussPts.map((g) => `${toX(g.idx).toFixed(1)},${toYPrice(g.upper).toFixed(1)}`).join(" ");
                    const lo = gaussPts.map((g) => `${toX(g.idx).toFixed(1)},${toYPrice(g.lower).toFixed(1)}`).join(" ");
                    const loRev = [...gaussPts].reverse().map((g) => `${toX(g.idx).toFixed(1)},${toYPrice(g.lower).toFixed(1)}`).join(" ");
                    const mid = gaussPts.filter((g) => g.line > 0).map((g) => `${toX(g.idx).toFixed(1)},${toYPrice(g.line).toFixed(1)}`).join(" ");
                    return (
                        <g>
                            <polygon points={`${up} ${loRev}`} fill={INK.text3} fillOpacity="0.06" />
                            <polyline points={up} fill="none" stroke={INK.hairlineStrong} strokeWidth="1.2" />
                            <polyline points={lo} fill="none" stroke={INK.hairlineStrong} strokeWidth="1.2" />
                            {mid && <polyline points={mid} fill="none" stroke={INK.text3} strokeWidth="1" strokeDasharray="4,4" strokeOpacity="0.6" />}
                        </g>
                    );
                })()}

                {/* Régua de melhor pernada — fundo tracejado âmbar */}
                {rulerSignals.map((sig) => {
                    const xEntry = toX(sig.entryIdx);
                    const xPeak = toX(sig.bestIdx);
                    const yEntry = toYPrice(sig.entryPrice);
                    const yPeak = toYPrice(sig.bestPx);
                    const bandX = Math.min(xEntry, xPeak);
                    const bandW = Math.max(12, Math.abs(xPeak - xEntry));
                    const bandTop = Math.min(yEntry, yPeak);
                    const bandH = Math.max(8, Math.abs(yPeak - yEntry));
                    return (
                        <rect
                            key={`ruler-bg-${sig.id}`}
                            x={bandX}
                            y={bandTop}
                            width={bandW}
                            height={bandH}
                            fill={INK.flip}
                            fillOpacity="0.06"
                            stroke={INK.flip}
                            strokeOpacity="0.45"
                            strokeWidth="1.2"
                            strokeDasharray="4,4"
                            rx="4"
                        />
                    );
                })}

                {/* Candles neutros Ink Azul */}
                {bars.map((b, idx) => {
                    const cx = toX(idx);
                    const o = Number(b.open ?? b.close);
                    const c = Number(b.close);
                    const hi = Number(b.high ?? Math.max(o, c));
                    const lo = Number(b.low ?? Math.min(o, c));
                    const isBullC = c >= o;
                    const yH = toYPrice(hi);
                    const yL = toYPrice(lo);
                    const yO = toYPrice(o);
                    const yC = toYPrice(c);
                    const bodyTop = Math.min(yO, yC);
                    const bodyH = Math.max(2, Math.abs(yC - yO));
                    const fillCol = isBullC ? "#9aa5b6" : "#475266";
                    return (
                        <g key={`c-${idx}`}>
                            <line x1={cx} y1={yH} x2={cx} y2={yL} stroke={fillCol} strokeWidth="1.3" />
                            <rect
                                x={cx - candleW / 2}
                                y={bodyTop}
                                width={candleW}
                                height={bodyH}
                                fill={fillCol}
                                rx="1"
                            />
                        </g>
                    );
                })}

                {/* Linhas de divergência opcionais (desligadas por padrão) */}
                {showDivLines && activeSignals.map((sig) => {
                    const x1 = toX(sig.prevIdx);
                    const x2 = toX(sig.pivotIdx);
                    const y1 = toYPrice(sig.prevPrice);
                    const y2 = toYPrice(sig.pivotPrice);
                    const col = sig.isStopped ? INK.neg : (sig.isBull ? INK.pos : INK.neg);
                    return (
                        <g key={`divline-${sig.id}`}>
                            <line
                                x1={x1}
                                y1={y1}
                                x2={x2}
                                y2={y2}
                                stroke={col}
                                strokeWidth="1.8"
                                strokeDasharray="4,3"
                                strokeOpacity="0.82"
                            />
                            <circle cx={x1} cy={y1} r="3" fill={INK.bg} stroke={col} strokeWidth="1.5" />
                            <circle cx={x2} cy={y2} r="3.5" fill={col} />
                        </g>
                    );
                })}

                {/* Tracejado de stop atingido */}
                {activeSignals.filter((s) => s.isStopped && s.stopIdx >= 0).map((sig) => {
                    const xEntry = toX(sig.entryIdx);
                    const xStop = toX(sig.stopIdx);
                    const yEntry = toYPrice(sig.entryPrice);
                    const yStop = toYPrice(sig.stopPrice);
                    return (
                        <line
                            key={`stophit-${sig.id}`}
                            x1={xEntry}
                            y1={yEntry}
                            x2={xStop}
                            y2={yStop}
                            stroke={INK.neg}
                            strokeWidth="1.6"
                            strokeDasharray="3,3"
                            strokeOpacity="0.78"
                        />
                    );
                })}

                {/* Fim de cada operação: trajeto da entrada até o melhor ponto (losango) ou até o stop (X) */}
                {activeSignals.map((sig) => {
                    const dirCol = sig.isBull ? INK.pos : INK.neg;
                    const xEntry = toX(sig.entryIdx);
                    const yEntry = toYPrice(sig.entryPrice);
                    if (sig.isStopped && sig.stopIdx >= 0) {
                        const xs = toX(sig.stopIdx);
                        const ys = toYPrice(sig.stopPrice);
                        const k = 6;
                        return (
                            <g key={`end-${sig.id}`} data-end="stop">
                                <line x1={xs - k} y1={ys - k} x2={xs + k} y2={ys + k} stroke={INK.neg} strokeWidth="2.6" strokeLinecap="round" />
                                <line x1={xs - k} y1={ys + k} x2={xs + k} y2={ys - k} stroke={INK.neg} strokeWidth="2.6" strokeLinecap="round" />
                            </g>
                        );
                    }
                    if (!(sig.mfePts > 0)) return null;
                    const xp = toX(sig.bestIdx);
                    const yp = toYPrice(sig.bestPx);
                    const d = 7;
                    const col = sig.isBest ? INK.flip : dirCol;
                    return (
                        <g key={`end-${sig.id}`} data-end="best">
                            <line x1={xEntry} y1={yEntry} x2={xp} y2={yp} stroke={dirCol} strokeWidth="1.8" strokeOpacity="0.85" />
                            <polygon points={`${xp},${yp - d} ${xp + d},${yp} ${xp},${yp + d} ${xp - d},${yp}`} fill={INK.bg} stroke={col} strokeWidth="2.2" />
                        </g>
                    );
                })}

                {/* Marcadores circulares numerados 1..N */}
                {markers.map((mk) => {
                    const { sig, candleX, candleY, badgeX, badgeY } = mk;
                    const dirCol = sig.isBull ? INK.pos : INK.neg;
                    const circleFill = sig.isStopped ? INK.negSoft : dirCol;
                    const circleStroke = sig.isStopped ? INK.neg : (sig.isBest ? INK.flip : INK.bg);
                    const txtFill = sig.isStopped ? INK.neg : (sig.isBull ? INK.onAccent : INK.text1);
                    const entryY = toYPrice(sig.entryPrice);
                    return (
                        <g key={`mk-${sig.id}`}>
                            <line
                                x1={candleX}
                                y1={candleY}
                                x2={badgeX}
                                y2={badgeY}
                                stroke={sig.isStopped ? INK.neg : dirCol}
                                strokeWidth="1.3"
                                strokeOpacity="0.7"
                            />
                            <circle cx={candleX} cy={entryY} r="3" fill={sig.isStopped ? INK.neg : dirCol} />
                            {sig.isBest && !sig.isStopped && (
                                <circle
                                    cx={badgeX}
                                    cy={badgeY}
                                    r={markerRadius + 4}
                                    fill="none"
                                    stroke={INK.flip}
                                    strokeWidth="1.6"
                                />
                            )}
                            <circle
                                cx={badgeX}
                                cy={badgeY}
                                r={markerRadius}
                                fill={circleFill}
                                stroke={circleStroke}
                                strokeWidth={sig.isStopped ? "2" : "1.5"}
                                strokeDasharray={sig.isStopped ? "4,2" : "none"}
                            />
                            <text
                                x={badgeX}
                                y={badgeY + 5.5}
                                fill={txtFill}
                                fontSize={markerRadius >= 17 ? "16" : "14.5"}
                                fontWeight="600"
                                fontFamily={FONT_MONO}
                                textAnchor="middle"
                            >
                                {sig.num}
                            </text>
                        </g>
                    );
                })}

                {/* Pílula da régua no topo do movimento */}
                {rulerSignals.map((sig) => {
                    const xEntry = toX(sig.entryIdx);
                    const xPeak = toX(sig.bestIdx);
                    const yEntry = toYPrice(sig.entryPrice);
                    const yPeak = toYPrice(sig.bestPx);
                    const bandX = Math.min(xEntry, xPeak);
                    const bandW = Math.max(12, Math.abs(xPeak - xEntry));
                    const bandTop = Math.min(yEntry, yPeak);
                    const pillTxt = `#${sig.num} ${formatPtsLabel(sig.mfePts, isWdo)}`;
                    const pillW = Math.max(132, pillTxt.length * 8.8 + 24);
                    const pillH = 26;
                    const pillX = Math.max(plotLeft + 8, Math.min(plotRight - pillW - 8, bandX + bandW / 2 - pillW / 2));
                    const pillY = Math.max(priceTop + 8, bandTop - pillH - 6);

                    return (
                        <g key={`ruler-fg-${sig.id}`}>
                            <rect
                                x={pillX}
                                y={pillY}
                                width={pillW}
                                height={pillH}
                                rx="6"
                                fill={INK.flipSoft}
                                stroke={INK.flip}
                                strokeWidth="1.2"
                            />
                            <text
                                x={pillX + pillW / 2}
                                y={pillY + 17.5}
                                fill={INK.flip}
                                fontSize="13.5"
                                fontWeight="600"
                                fontFamily={FONT_MONO}
                                textAnchor="middle"
                            >
                                {pillTxt}
                            </text>
                        </g>
                    );
                })}
            </g>

            {/* Rótulos das Walls no eixo Y */}
            {(() => {
                const usedYs = [lastY];
                const prio = (wl) => {
                    const wt = String(wl?.type || "");
                    if (wt === "GammaFlip" || /flip/i.test(String(wl?.label || ""))) return 0;
                    if (wt === "Wall") return 1;
                    return 2;
                };
                return visibleWalls
                    .slice()
                    .sort((a, b) => prio(a) - prio(b))
                    .map((wl, i) => {
                        const yW = toYPrice(wl.price);
                        if (usedYs.some((uy) => Math.abs(uy - yW) < 23)) return null;
                        usedYs.push(yW);
                        const wt = String(wl.type || "");
                        const isFlip = wt === "GammaFlip" || /flip/i.test(String(wl.label || ""));
                        const isMid = wt.toLowerCase().includes("mid") || String(wl?.label || "").toUpperCase() === "MIDLEWALL";
                        return (
                            <g key={`wtag-${i}`}>
                                {(!isMid || isFlip) ? (
                                    <rect
                                        x={plotRight + 6}
                                        y={yW - 11}
                                        width={rightAxisW - 14}
                                        height={22}
                                        rx="4"
                                        fill={isFlip ? INK.flipSoft : INK.raised}
                                        stroke={isFlip ? INK.flip : INK.hairlineStrong}
                                        strokeWidth="1"
                                    />
                                ) : (
                                    <line
                                        x1={plotRight}
                                        y1={yW}
                                        x2={plotRight + 4}
                                        y2={yW}
                                        stroke="rgba(238, 240, 245, 0.28)"
                                        strokeWidth="1"
                                    />
                                )}
                                <text
                                    x={plotRight + 12}
                                    y={yW + 4.5}
                                    fill={isFlip ? INK.flip : isMid ? INK.text2 : INK.text1}
                                    fontSize="12.5"
                                    fontWeight="500"
                                    fontFamily={FONT_MONO}
                                >
                                    {formatBrNumber(wl.price, dec)}
                                </text>
                            </g>
                        );
                    });
            })()}

            {/* Último preço em destaque azul com contraste escuro */}
            {Number.isFinite(lastClose) && lastClose > 0 && (
                <g>
                    <rect
                        x={plotRight + 6}
                        y={Math.max(priceTop + 2, Math.min(priceBot - 26, lastY - 12))}
                        width={rightAxisW - 14}
                        height={24}
                        rx="4"
                        fill={INK.accent}
                    />
                    <text
                        x={plotRight + 12}
                        y={Math.max(priceTop + 18.5, Math.min(priceBot - 9.5, lastY + 4.5))}
                        fill={INK.onAccent}
                        fontSize="13"
                        fontWeight="600"
                        fontFamily={FONT_MONO}
                    >
                        {formatBrNumber(lastClose, dec)}
                    </text>
                </g>
            )}

            {/* SUBPAINEL FLUXO SMART MONEY */}
            {showFlow && (
                <g>
                    <line x1={x + 1} y1={flowTop - 1} x2={x + w - 1} y2={flowTop - 1} stroke={INK.hairline} strokeWidth="1" />
                    <text
                        x={plotLeft + 4}
                        y={flowTop + 18}
                        fill={INK.accentInk}
                        fontSize="13.5"
                        fontWeight="500"
                        fontFamily={FONT_SANS}
                    >
                        Fluxo Smart Money
                    </text>
                    <line x1={plotRight} y1={flowTop} x2={plotRight} y2={flowBot} stroke={INK.hairline} strokeWidth="1" />
                    <line
                        x1={plotLeft}
                        y1={yZeroFlow}
                        x2={plotRight}
                        y2={yZeroFlow}
                        stroke={INK.hairlineStrong}
                        strokeWidth="1"
                        strokeDasharray="4,4"
                    />
                    <text x={plotRight + 12} y={yZeroFlow + 4} fill={INK.text3} fontSize="12" fontFamily={FONT_MONO}>
                        0
                    </text>

                    <g clipPath={`url(#${clipPrefix}-flow)`}>
                        {/* Histograma de fluxo limpo */}
                        {bars.map((b, idx) => {
                            const val = Number(b?.smart_swing_wave || 0);
                            const yVal = toYFlow(val);
                            const barY = val >= 0 ? yVal : yZeroFlow;
                            const barH = Math.max(1.5, Math.abs(yVal - yZeroFlow));
                            return (
                                <rect
                                    key={`fbar-${idx}`}
                                    x={toX(idx) - flowBarW / 2}
                                    y={barY}
                                    width={flowBarW}
                                    height={barH}
                                    fill={val >= 0 ? INK.accent : "#475266"}
                                    fillOpacity="0.82"
                                    rx="1"
                                />
                            );
                        })}

                        {/* Curva de fluxo contínua */}
                        {flowLinePts && (
                            <polyline
                                points={flowLinePts}
                                fill="none"
                                stroke={INK.accentInk}
                                strokeWidth="1.5"
                                strokeLinejoin="round"
                                strokeLinecap="round"
                            />
                        )}

                        {/* Rótulos #N no subpainel sem sobreposição */}
                        {activeSignals.map((sig) => {
                            const xPos = Math.max(plotLeft + 14, Math.min(plotRight - 14, toX(sig.pivotIdx)));
                            const waveVal = Number(bars[sig.pivotIdx]?.smart_swing_wave ?? sig.currWave ?? 0);
                            const col = sig.isStopped ? INK.neg : (sig.isBull ? INK.pos : INK.neg);
                            const lblY = waveVal >= 0
                                ? Math.max(flowPlotTop + 2, Math.min(yZeroFlow - 6, toYFlow(waveVal) - 6))
                                : Math.min(flowBot - 4, Math.max(yZeroFlow + 14, toYFlow(waveVal) + 14));
                            return (
                                <text
                                    key={`fl-lbl-${sig.id}`}
                                    x={xPos}
                                    y={lblY}
                                    fill={col}
                                    fontSize="12.5"
                                    fontWeight="600"
                                    fontFamily={FONT_MONO}
                                    textAnchor="middle"
                                >
                                    #{sig.num}
                                </text>
                            );
                        })}
                    </g>
                </g>
            )}

            {/* Eixo de horário */}
            <line
                x1={x + 1}
                y1={showFlow ? flowBot : priceBot}
                x2={x + w - 1}
                y2={showFlow ? flowBot : priceBot}
                stroke={INK.hairline}
                strokeWidth="1"
            />
            {timeTicks.map((tt, i) => (
                <text
                    key={`t-${i}`}
                    x={tt.x}
                    y={y + h - 11}
                    fill={INK.text3}
                    fontSize="13.5"
                    fontWeight="400"
                    fontFamily={FONT_MONO}
                    textAnchor="middle"
                >
                    {tt.label}
                </text>
            ))}
        </g>
    );
}

/* ══════════════════════════════════════════════════════════════════════════════
   SUB-COMPONENTE SVG: CABEÇALHO (WALLS MARK) + 3 KPIS SILENCIOSOS
   ══════════════════════════════════════════════════════════════════════════════ */
export function CardHeaderAndKpis({
    padX,
    contentW,
    topY,
    compact = false,
    brandTitle,
    symKey,
    dateInfo,
    summary,
    slideBadge = "",
}) {
    const isWdo = String(symKey || "").toUpperCase() === "WDO";
    const headerH = compact ? 74 : 92;
    const kpiTop = topY + headerH + (compact ? 12 : 16);
    const kpiH = compact ? 92 : 108;
    const kpiGap = 14;
    const kpiW = (contentW - kpiGap * 2) / 3;

    const bestSig = summary.bestSignal;
    const bestPtsTxt = bestSig && bestSig.mfePts > 0
        ? formatPtsLabel(bestSig.mfePts, isWdo)
        : "—";
    const bestSubTxt = bestSig && bestSig.mfePts > 0
        ? `#${bestSig.num} ${bestSig.isBull ? "Compra" : "Venda"} às ${bestSig.entryTime}`
        : "Sem movimento positivo";

    const netPtsTxt = summary.totalSignals > 0
        ? formatPtsLabel(summary.netPts, isWdo)
        : "—";
    const netIsNeg = summary.netPts < 0;
    const netValCol = summary.totalSignals === 0 ? INK.text2 : (netIsNeg ? INK.neg : INK.pos);
    const { protTxt } = describeSignalRule(symKey);
    const netSubTxt = summary.totalSignals === 0
        ? "Aguardando sinais"
        : summary.stopCount > 0
            ? `Bruto ${formatPtsLabel(summary.grossMfePts, isWdo)} · Stop -${formatPtsLabel(summary.totalStopPts, isWdo, false)}`
            : `Proteção ${protTxt} · 0 stops`;

    const dateLabel = dateInfo.weekday ? `${dateInfo.weekday}, ${dateInfo.short}` : dateInfo.short;
    // protegido = andou o mínimo a favor antes do stop; sinal sem desfecho (ex.: entrou na última barra) é outra coisa
    const outcomeTxt = [
        `${summary.winCount} protegido${summary.winCount === 1 ? "" : "s"}`,
        `${summary.stopCount} stop${summary.stopCount === 1 ? "" : "s"}`,
        summary.neutralCount > 0 ? `${summary.neutralCount} sem desfecho` : null,
    ].filter(Boolean).join(" · ");
    const brandDisplay = String(brandTitle || "Magic Walls").trim() || "Magic Walls";

    const markSize = compact ? 38 : 44;
    const markScale = markSize / 256;
    const textOffsetX = padX + markSize + Math.round(markSize * 0.38);

    return (
        <g>
            {/* Marca oficial Magic Walls — Flip Strata (corte master 36u, chanfros 45°, sem rx) */}
            <g transform={`translate(${padX}, ${topY + (compact ? 6 : 10)}) scale(${markScale.toFixed(6)})`}>
                <path fill={INK.text1} d="M28 35 H175 L139 71 H28 Z" />
                <path fill={INK.accent} d="M28 110 H228 V146 H28 Z" />
                <path fill={INK.text3} d="M117 185 H228 V221 H81 Z" />
            </g>

            {/* Título & Subtítulo em sentence case */}
            <text
                x={textOffsetX}
                y={topY + (compact ? 25 : 31)}
                fill={INK.text1}
                fontSize={compact ? "28" : "34"}
                fontWeight="600"
                fontFamily={FONT_SANS}
            >
                {brandDisplay}
            </text>
            <text
                x={textOffsetX}
                y={topY + (compact ? 54 : 64)}
                fill={INK.text3}
                fontSize={compact ? "16.5" : "18.5"}
                fontWeight="400"
                fontFamily={FONT_SANS}
            >
                Resumo do pregão · {dateLabel}
            </text>

            {/* Pill do ativo à direita */}
            <g transform={`translate(${padX + contentW}, ${topY + (compact ? 8 : 12)})`}>
                <rect
                    x="-148"
                    y="0"
                    width="148"
                    height={compact ? "38" : "42"}
                    rx="19"
                    fill={INK.card}
                    stroke={INK.hairlineStrong}
                    strokeWidth="1.2"
                />
                <circle cx="-122" cy={compact ? "19" : "21"} r="4" fill={INK.accent} />
                <text
                    x="-106"
                    y={compact ? "25" : "27"}
                    fill={INK.text1}
                    fontSize={compact ? "18" : "20"}
                    fontWeight="600"
                    fontFamily={FONT_MONO}
                >
                    {symKey}
                </text>
                {slideBadge && (
                    <text
                        x="0"
                        y={compact ? "58" : "66"}
                        fill={INK.text3}
                        fontSize="14.5"
                        fontWeight="500"
                        fontFamily={FONT_MONO}
                        textAnchor="end"
                    >
                        {slideBadge}
                    </text>
                )}
            </g>

            {/* KPI 1: Sinais no dia */}
            <g transform={`translate(${padX}, ${kpiTop})`}>
                <rect x="0" y="0" width={kpiW} height={kpiH} rx="12" fill={INK.card} stroke={INK.hairline} strokeWidth="1.2" />
                <rect x="16" y="0" width={kpiW - 32} height="2.5" rx="1" fill={INK.accent} />
                <text x="18" y={compact ? "28" : "32"} fill={INK.text2} fontSize="14.5" fontWeight="500" fontFamily={FONT_SANS}>
                    Sinais no dia
                </text>
                <text x="18" y={compact ? "60" : "70"} fill={INK.text1} fontSize={compact ? "29" : "35"} fontWeight="600" fontFamily={FONT_MONO}>
                    {summary.totalSignals}
                </text>
                <text x="18" y={compact ? "80" : "94"} fill={INK.text3} fontSize={summary.neutralCount > 0 ? "12" : "13.5"} fontWeight="400" fontFamily={FONT_MONO}>
                    {outcomeTxt}
                </text>
            </g>

            {/* KPI 2: Melhor pernada (sem estrela) */}
            <g transform={`translate(${padX + kpiW + kpiGap}, ${kpiTop})`}>
                <rect x="0" y="0" width={kpiW} height={kpiH} rx="12" fill={INK.card} stroke={INK.hairline} strokeWidth="1.2" />
                <rect x="16" y="0" width={kpiW - 32} height="2.5" rx="1" fill={INK.flip} />
                <text x="18" y={compact ? "28" : "32"} fill={INK.text2} fontSize="14.5" fontWeight="500" fontFamily={FONT_SANS}>
                    Melhor pernada
                </text>
                <text x="18" y={compact ? "60" : "70"} fill={INK.flip} fontSize={compact ? "28" : "33"} fontWeight="600" fontFamily={FONT_MONO}>
                    {bestPtsTxt}
                </text>
                <text x="18" y={compact ? "80" : "94"} fill={INK.text3} fontSize="13.5" fontWeight="400" fontFamily={FONT_MONO}>
                    {bestSubTxt}
                </text>
            </g>

            {/* KPI 3: Saldo máx. a favor */}
            <g transform={`translate(${padX + (kpiW + kpiGap) * 2}, ${kpiTop})`}>
                <rect x="0" y="0" width={kpiW} height={kpiH} rx="12" fill={INK.card} stroke={INK.hairline} strokeWidth="1.2" />
                <rect x="16" y="0" width={kpiW - 32} height="2.5" rx="1" fill={netIsNeg ? INK.neg : INK.pos} />
                <text x="18" y={compact ? "28" : "32"} fill={INK.text2} fontSize="14.5" fontWeight="500" fontFamily={FONT_SANS}>
                    Saldo máx. a favor
                </text>
                <text x="18" y={compact ? "60" : "70"} fill={netValCol} fontSize={compact ? "28" : "33"} fontWeight="600" fontFamily={FONT_MONO}>
                    {netPtsTxt}
                </text>
                <text x="18" y={compact ? "80" : "94"} fill={INK.text3} fontSize="13.5" fontWeight="400" fontFamily={FONT_SANS}>
                    {netSubTxt}
                </text>
            </g>
        </g>
    );
}

/* ══════════════════════════════════════════════════════════════════════════════
   SUB-COMPONENTE SVG: TABELA EDITORIAL INK AZUL (TRILHO ESQUERDO DE 2PX)
   ══════════════════════════════════════════════════════════════════════════════ */
export function SignalListSection({
    x,
    y,
    w,
    h,
    activeSignals,
    summary,
    symKey,
    detailed = false,
}) {
    const isWdo = String(symKey || "").toUpperCase() === "WDO";
    const dec = isWdo ? 1 : 0;
    const count = activeSignals.length;
    const maxMag = Math.max(
        isWdo ? 10 : 200,
        summary.bestSignal?.mfePts || 0,
        ...activeSignals.map((s) => Math.abs(s.resultPts || 0)),
    );

    const headerH = 38;
    const listTop = y + headerH;
    const listH = Math.max(60, h - headerH);

    const minRowH = detailed ? 62 : 54;
    const useTwoCols = count > 0 && (listH / count) < minRowH;

    return (
        <g>
            {/* Título e ordenação */}
            <text
                x={x + 2}
                y={y + 24}
                fill={INK.text1}
                fontSize="18"
                fontWeight="500"
                fontFamily={FONT_SANS}
            >
                Entradas do pregão
            </text>
            <text
                x={x + w - 2}
                y={y + 24}
                fill={INK.text3}
                fontSize="14"
                fontWeight="400"
                fontFamily={FONT_MONO}
                textAnchor="end"
            >
                {count} {count === 1 ? "sinal" : "sinais"}
            </text>
            {/* Legenda do fim de cada operação (formas desenhadas, sem depender de fonte) */}
            {(() => {
                const cw = 8.4;
                const countTxt = `${count} ${count === 1 ? "sinal" : "sinais"}`;
                const right = x + w - 2 - countTxt.length * cw - 22;
                const stopW = "stop".length * cw;
                const bestW = "melhor ponto".length * cw;
                const yy = y + 19;
                const stopTextX = right;
                const crossX = stopTextX - stopW - 14;
                const bestTextX = crossX - 20 - 8;
                const diaX = bestTextX - bestW - 14;
                return (
                    <g>
                        <text x={stopTextX} y={y + 24} fill={INK.text3} fontSize="14" fontFamily={FONT_MONO} textAnchor="end">stop</text>
                        <line x1={crossX - 5} y1={yy - 5} x2={crossX + 5} y2={yy + 5} stroke={INK.neg} strokeWidth="2.2" strokeLinecap="round" />
                        <line x1={crossX - 5} y1={yy + 5} x2={crossX + 5} y2={yy - 5} stroke={INK.neg} strokeWidth="2.2" strokeLinecap="round" />
                        <text x={bestTextX} y={y + 24} fill={INK.text3} fontSize="14" fontFamily={FONT_MONO} textAnchor="end">melhor ponto</text>
                        <polygon points={`${diaX},${yy - 6} ${diaX + 6},${yy} ${diaX},${yy + 6} ${diaX - 6},${yy}`} fill={INK.bg} stroke={INK.flip} strokeWidth="2" />
                    </g>
                );
            })()}

            {count === 0 ? (
                <g>
                    <rect x={x} y={listTop} width={w} height={Math.min(120, listH)} rx="12" fill={INK.card} stroke={INK.hairline} strokeWidth="1.2" />
                    <text
                        x={x + w / 2}
                        y={listTop + Math.min(120, listH) / 2 + 6}
                        fill={INK.text3}
                        fontSize="18"
                        fontWeight="500"
                        fontFamily={FONT_SANS}
                        textAnchor="middle"
                    >
                        Nenhum sinal selecionado para este pregão.
                    </text>
                </g>
            ) : useTwoCols ? (
                (() => {
                    const cols = 2;
                    const rowsPerCol = Math.ceil(count / cols);
                    const gapX = 14;
                    const gapY = 10;
                    const cardW = (w - gapX) / 2;
                    const cardH = Math.min(88, Math.max(58, (listH - gapY * (rowsPerCol - 1)) / rowsPerCol));

                    return activeSignals.map((sig, idx) => {
                        const colIdx = idx % 2;
                        const rowIdx = Math.floor(idx / 2);
                        const rx = x + colIdx * (cardW + gapX);
                        const ry = listTop + rowIdx * (cardH + gapY);

                        const dirCol = sig.isBull ? INK.pos : INK.neg;
                        const outcomeCol = sig.isStopped
                            ? INK.neg
                            : sig.isBest
                                ? INK.flip
                                : sig.mfePts > 0
                                    ? INK.pos
                                    : INK.text2;
                        const railCol = sig.isStopped ? INK.neg : (sig.isBest ? INK.flip : dirCol);
                        const barRatio = Math.max(0.06, Math.min(1, Math.abs(sig.resultPts) / maxMag));

                        return (
                            <g key={`row2-${sig.id}`} transform={`translate(${rx}, ${ry})`}>
                                <rect
                                    x="0"
                                    y="0"
                                    width={cardW}
                                    height={cardH}
                                    rx="10"
                                    fill={sig.isStopped ? INK.stopCard : INK.card}
                                    stroke={sig.isStopped ? INK.negSoft : INK.hairline}
                                    strokeWidth="1.2"
                                />
                                <rect x="0" y="10" width="2.5" height={cardH - 20} rx="1" fill={railCol} />

                                <circle
                                    cx="26"
                                    cy={cardH / 2}
                                    r="14"
                                    fill={sig.isStopped ? INK.negSoft : dirCol}
                                    stroke={sig.isStopped ? INK.neg : "none"}
                                    strokeWidth={sig.isStopped ? "1.6" : "0"}
                                />
                                <text
                                    x="26"
                                    y={cardH / 2 + 5}
                                    fill={sig.isStopped ? INK.neg : (sig.isBull ? INK.onAccent : INK.text1)}
                                    fontSize="14"
                                    fontWeight="600"
                                    fontFamily={FONT_MONO}
                                    textAnchor="middle"
                                >
                                    {sig.num}
                                </text>

                                <text x="50" y={cardH / 2 - 4} fill={INK.text1} fontSize="16.5" fontWeight="600" fontFamily={FONT_MONO}>
                                    {sig.entryTime}
                                    <tspan fill={dirCol} fontSize="14" fontWeight="500"> · {sig.anchorCode} {sig.isBull ? "Compra" : "Venda"}</tspan>
                                </text>
                                <text x="50" y={cardH / 2 + 16} fill={sig.isStopped ? INK.neg : INK.text3} fontSize="12.5" fontWeight="400" fontFamily={FONT_MONO}>
                                    {sig.isStopped
                                        ? `Stop ${sig.stopTime} · ${formatBrNumber(sig.stopPrice, dec)}`
                                        : `Ent. ${formatBrNumber(sig.entryPrice, dec)} · Melhor ${sig.peakTime}`}
                                </text>

                                <text x={cardW - 14} y={cardH / 2 + 2} fill={outcomeCol} fontSize="18" fontWeight="600" fontFamily={FONT_MONO} textAnchor="end">
                                    {sig.isStopped
                                        ? formatPtsLabel(sig.resultPts, isWdo)
                                        : formatPtsLabel(sig.mfePts, isWdo)}
                                </text>

                                <rect x="50" y={cardH - 9} width={cardW - 64} height="4" rx="2" fill={INK.raised} />
                                <rect x="50" y={cardH - 9} width={(cardW - 64) * barRatio} height="4" rx="2" fill={outcomeCol} />
                            </g>
                        );
                    });
                })()
            ) : (
                (() => {
                    const gapY = count <= 6 ? 10 : 8;
                    const maxRowH = detailed ? 96 : 74;
                    const rowH = Math.min(maxRowH, Math.max(52, (listH - gapY * (count - 1)) / count));
                    const isCompactRow = rowH < 64;

                    return activeSignals.map((sig, idx) => {
                        const ry = listTop + idx * (rowH + gapY);
                        const dirCol = sig.isBull ? INK.pos : INK.neg;
                        const dirSoft = sig.isBull ? INK.posSoft : INK.negSoft;
                        const outcomeCol = sig.isStopped
                            ? INK.neg
                            : sig.isBest
                                ? INK.flip
                                : sig.mfePts > 0
                                    ? INK.pos
                                    : INK.text2;
                        const railCol = sig.isStopped ? INK.neg : (sig.isBest ? INK.flip : INK.pos);
                        const barRatio = Math.max(0.06, Math.min(1, Math.abs(sig.resultPts) / maxMag));
                        const barW = detailed ? 190 : 156;

                        return (
                            <g key={`row1-${sig.id}`} transform={`translate(${x}, ${ry})`}>
                                <rect
                                    x="0"
                                    y="0"
                                    width={w}
                                    height={rowH}
                                    rx="10"
                                    fill={sig.isStopped ? INK.stopCard : INK.card}
                                    stroke={sig.isStopped ? INK.negSoft : INK.hairline}
                                    strokeWidth="1.2"
                                />
                                {/* Trilho esquerdo de 2px */}
                                <rect x="0" y="10" width="2.5" height={rowH - 20} rx="1" fill={railCol} />

                                {/* Círculo numerado */}
                                <circle
                                    cx="32"
                                    cy={rowH / 2}
                                    r={isCompactRow ? "14" : "16"}
                                    fill={sig.isStopped ? INK.negSoft : dirCol}
                                    stroke={sig.isStopped ? INK.neg : "none"}
                                    strokeWidth={sig.isStopped ? "1.6" : "0"}
                                />
                                <text
                                    x="32"
                                    y={rowH / 2 + (isCompactRow ? 5 : 5.5)}
                                    fill={sig.isStopped ? INK.neg : (sig.isBull ? INK.onAccent : INK.text1)}
                                    fontSize={isCompactRow ? "14" : "16"}
                                    fontWeight="600"
                                    fontFamily={FONT_MONO}
                                    textAnchor="middle"
                                >
                                    {sig.num}
                                </text>

                                {/* Pill direcional limpa (F▲ Compra / F▼ Venda) */}
                                <rect
                                    x="62"
                                    y={rowH / 2 - 15}
                                    width={detailed ? "132" : "118"}
                                    height="30"
                                    rx="6"
                                    fill={dirSoft}
                                    stroke={dirCol}
                                    strokeOpacity="0.45"
                                    strokeWidth="1"
                                />
                                <text
                                    x={62 + (detailed ? 66 : 59)}
                                    y={rowH / 2 + 5}
                                    fill={dirCol}
                                    fontSize={detailed ? "14.5" : "13.5"}
                                    fontWeight="600"
                                    fontFamily={FONT_MONO}
                                    textAnchor="middle"
                                >
                                    {sig.anchorCode} {sig.isBull ? "Compra" : "Venda"}
                                </text>

                                {/* Horário + Preço */}
                                <text
                                    x={detailed ? "214" : "196"}
                                    y={isCompactRow ? rowH / 2 + 5 : rowH / 2 - 4}
                                    fill={INK.text1}
                                    fontSize={detailed ? "20" : "18.5"}
                                    fontWeight="600"
                                    fontFamily={FONT_MONO}
                                >
                                    {sig.entryTime}
                                </text>
                                {!isCompactRow && (
                                    <text
                                        x={detailed ? "214" : "196"}
                                        y={rowH / 2 + 18}
                                        fill={INK.text3}
                                        fontSize="13.5"
                                        fontWeight="400"
                                        fontFamily={FONT_MONO}
                                    >
                                        Ent. {formatBrNumber(sig.entryPrice, dec)}
                                    </text>
                                )}

                                {/* Pico ou Stop */}
                                <text
                                    x={detailed ? "386" : "356"}
                                    y={isCompactRow ? rowH / 2 + 5 : rowH / 2 - 4}
                                    fill={sig.isStopped ? INK.neg : INK.text2}
                                    fontSize="15"
                                    fontWeight="500"
                                    fontFamily={FONT_MONO}
                                >
                                    {sig.isStopped
                                        ? `Stop ${sig.stopTime} (${formatDuration(sig.durationMin)})`
                                        : !(sig.mfePts > 0)
                                            ? (isCompactRow ? `Ent. ${formatBrNumber(sig.entryPrice, dec)} · sem desfecho` : "Sem desfecho")
                                            : isCompactRow
                                                ? `Ent. ${formatBrNumber(sig.entryPrice, dec)} · Melhor ${sig.peakTime}`
                                                : `Melhor ponto ${sig.peakTime} (${formatDuration(sig.durationMin)})`}
                                </text>
                                {!isCompactRow && (
                                    <text
                                        x={detailed ? "386" : "356"}
                                        y={rowH / 2 + 18}
                                        fill={INK.text3}
                                        fontSize="13"
                                        fontWeight="400"
                                        fontFamily={FONT_MONO}
                                    >
                                        {sig.isStopped
                                            ? `${sig.stopLabel} ${formatBrNumber(sig.stopPrice, dec)} · antes da proteção`
                                            : !(sig.mfePts > 0)
                                                ? (sig.windowEndIdx <= sig.entryIdx ? "Entrada na última barra do pregão" : "Não andou a favor até o fim da janela")
                                                : `Preço ${formatBrNumber(sig.bestPx, dec)} · janela ${sig.endedBy === "FECHAMENTO" ? "até o fechamento" : `até ${sig.windowEndTime} (sinal oposto)`}`}
                                    </text>
                                )}

                                {/* Badge Melhor ou Stop */}
                                {(sig.isBest && !sig.isStopped) && (
                                    <g transform={`translate(${w - 20 - barW - 76}, ${rowH / 2 - 12})`}>
                                        <rect x="0" y="0" width="64" height="22" rx="6" fill={INK.flipSoft} stroke={INK.flip} strokeOpacity="0.45" strokeWidth="1" />
                                        <text x="32" y="15" fill={INK.flip} fontSize="12" fontWeight="500" fontFamily={FONT_SANS} textAnchor="middle">
                                            Melhor
                                        </text>
                                    </g>
                                )}
                                {sig.isStopped && (
                                    <g transform={`translate(${w - 20 - barW - 70}, ${rowH / 2 - 12})`}>
                                        <rect x="0" y="0" width="58" height="22" rx="6" fill={INK.negSoft} stroke={INK.neg} strokeOpacity="0.5" strokeWidth="1" />
                                        <text x="29" y="15" fill={INK.neg} fontSize="12" fontWeight="500" fontFamily={FONT_SANS} textAnchor="middle">
                                            Stop
                                        </text>
                                    </g>
                                )}

                                {/* Valor em pontos + Barra de magnitude */}
                                <text
                                    x={w - 20}
                                    y={isCompactRow ? rowH / 2 + 6 : rowH / 2 - 3}
                                    fill={outcomeCol}
                                    fontSize={detailed ? "24" : "22"}
                                    fontWeight="600"
                                    fontFamily={FONT_MONO}
                                    textAnchor="end"
                                >
                                    {sig.isStopped
                                        ? formatPtsLabel(sig.resultPts, isWdo)
                                        : formatPtsLabel(sig.mfePts, isWdo)}
                                </text>
                                {!isCompactRow && (
                                    <g>
                                        <rect x={w - 20 - barW} y={rowH / 2 + 12} width={barW} height="4" rx="2" fill={INK.raised} />
                                        <rect x={w - 20 - barW} y={rowH / 2 + 12} width={barW * barRatio} height="4" rx="2" fill={outcomeCol} />
                                    </g>
                                )}
                            </g>
                        );
                    });
                })()
            )}
        </g>
    );
}

/* ══════════════════════════════════════════════════════════════════════════════
   SUB-COMPONENTE SVG: RODAPÉ INK AZUL
   ══════════════════════════════════════════════════════════════════════════════ */
export function CardFooter({ padX, contentW, y, handle, rightNote = "Estudo quantitativo educacional · Sem recomendação" }) {
    const cleanHandle = handle ? handle.trim() : "@magicwallsb3";
    return (
        <g>
            <line x1={padX} y1={y - 14} x2={padX + contentW} y2={y - 14} stroke={INK.hairline} strokeWidth="1" />
            <text
                x={padX}
                y={y + 12}
                fill={INK.text2}
                fontSize="15.5"
                fontWeight="500"
                fontFamily={FONT_MONO}
            >
                {cleanHandle} · www.magicwalls.com.br
            </text>
            <text
                x={padX + contentW}
                y={y + 12}
                fill={INK.text3}
                fontSize="14"
                fontWeight="400"
                fontFamily={FONT_SANS}
                textAnchor="end"
            >
                {rightNote}
            </text>
        </g>
    );
}

/* ══════════════════════════════════════════════════════════════════════════════
   RENDERIZADOR DO CARD SVG COMPLETO (STORIES | FEED | CAROUSEL_1 | CAROUSEL_2)
   ══════════════════════════════════════════════════════════════════════════════ */
export function InstagramCardSvg({
    svgRef,
    variant,
    bars,
    walls,
    activeSignals,
    summary,
    symKey,
    dateInfo,
    brandTitle,
    handle,
    showFlow,
    showGauss,
    showWalls,
    showMidWalls = true,
    showDivLines,
    rulerMode,
}) {
    const { width: W, height: H } = getCardDimensions(variant);
    const padX = 44;
    const contentW = W - padX * 2;
    const isWdo = String(symKey || "").toUpperCase() === "WDO";
    const clipPrefix = `ig-${variant.toLowerCase()}`;

    return (
        <svg
            ref={svgRef}
            width={W}
            height={H}
            viewBox={`0 0 ${W} ${H}`}
            style={{
                width: "100%",
                height: "auto",
                display: "block",
                borderRadius: 12,
                border: `1px solid ${INK.hairline}`,
            }}
        >
            {/* Fundo sólido fosco Ink Azul (zero gradiente, zero brilho radial) */}
            <rect x="0" y="0" width={W} height={H} fill={INK.bg} />

            {/* ── LAYOUT 1: STORIES 9:16 (1080×1920) ── */}
            {variant === "STORIES" && (
                <>
                    <CardHeaderAndKpis
                        padX={padX}
                        contentW={contentW}
                        topY={72}
                        compact={false}
                        brandTitle={brandTitle}
                        symKey={symKey}
                        dateInfo={dateInfo}
                        summary={summary}
                    />
                    <CleanChartSection
                        x={padX}
                        y={316}
                        w={contentW}
                        h={774}
                        bars={bars}
                        walls={walls}
                        activeSignals={activeSignals}
                        symKey={symKey}
                        showFlow={showFlow}
                        showGauss={showGauss}
                        showWalls={showWalls}
                        showMidWalls={showMidWalls}
                        showDivLines={showDivLines}
                        rulerMode={rulerMode}
                        clipPrefix={clipPrefix}
                    />
                    <SignalListSection
                        x={padX}
                        y={1114}
                        w={contentW}
                        h={682}
                        activeSignals={activeSignals}
                        summary={summary}
                        symKey={symKey}
                        detailed={false}
                    />
                    <CardFooter padX={padX} contentW={contentW} y={1844} handle={handle} />
                </>
            )}

            {/* ── LAYOUT 2: FEED ÚNICO 4:5 (1080×1350) ── */}
            {variant === "FEED" && (
                <>
                    <CardHeaderAndKpis
                        padX={padX}
                        contentW={contentW}
                        topY={32}
                        compact={true}
                        brandTitle={brandTitle}
                        symKey={symKey}
                        dateInfo={dateInfo}
                        summary={summary}
                    />
                    <CleanChartSection
                        x={padX}
                        y={224}
                        w={contentW}
                        h={558}
                        bars={bars}
                        walls={walls}
                        activeSignals={activeSignals}
                        symKey={symKey}
                        showFlow={showFlow}
                        showGauss={showGauss}
                        showWalls={showWalls}
                        showMidWalls={showMidWalls}
                        showDivLines={showDivLines}
                        rulerMode={rulerMode}
                        clipPrefix={clipPrefix}
                    />
                    <SignalListSection
                        x={padX}
                        y={800}
                        w={contentW}
                        h={472}
                        activeSignals={activeSignals}
                        summary={summary}
                        symKey={symKey}
                        detailed={false}
                    />
                    <CardFooter padX={padX} contentW={contentW} y={1308} handle={handle} />
                </>
            )}

            {/* ── LAYOUT 3A: CARROSSEL SLIDE 1 — GRÁFICO HERO (1080×1350) ── */}
            {variant === "CAROUSEL_1" && (
                <>
                    <CardHeaderAndKpis
                        padX={padX}
                        contentW={contentW}
                        topY={32}
                        compact={true}
                        brandTitle={brandTitle}
                        symKey={symKey}
                        dateInfo={dateInfo}
                        summary={summary}
                        slideBadge="Slide 1 / 2"
                    />
                    <CleanChartSection
                        x={padX}
                        y={228}
                        w={contentW}
                        h={950}
                        bars={bars}
                        walls={walls}
                        activeSignals={activeSignals}
                        symKey={symKey}
                        showFlow={showFlow}
                        showGauss={showGauss}
                        showWalls={showWalls}
                        showMidWalls={showMidWalls}
                        showDivLines={showDivLines}
                        rulerMode={rulerMode}
                        clipPrefix={clipPrefix}
                    />
                    <g transform={`translate(${padX}, 1198)`}>
                        <rect x="0" y="0" width={contentW} height="64" rx="10" fill={INK.card} stroke={INK.hairline} strokeWidth="1.2" />
                        <text x="20" y="38" fill={INK.text2} fontSize="17" fontWeight="500" fontFamily={FONT_SANS}>
                            {summary.bestSignal && summary.bestSignal.mfePts > 0
                                ? `Destaque: #${summary.bestSignal.num} ${summary.bestSignal.isBull ? "Compra" : "Venda"} às ${summary.bestSignal.entryTime} → ${formatPtsLabel(summary.bestSignal.mfePts, isWdo)}`
                                : `${summary.totalSignals} sinais mapeados no pregão`}
                        </text>
                        <rect x={contentW - 236} y="12" width="216" height="40" rx="8" fill={INK.accent} />
                        <text x={contentW - 128} y="37" fill={INK.onAccent} fontSize="15" fontWeight="600" fontFamily={FONT_MONO} textAnchor="middle">
                            Ver horários e pts →
                        </text>
                    </g>
                    <CardFooter padX={padX} contentW={contentW} y={1308} handle={handle} />
                </>
            )}

            {/* ── LAYOUT 3B: CARROSSEL SLIDE 2 — TABELA DETALHADA (1080×1350) ── */}
            {variant === "CAROUSEL_2" && (
                <>
                    <CardHeaderAndKpis
                        padX={padX}
                        contentW={contentW}
                        topY={32}
                        compact={true}
                        brandTitle={brandTitle}
                        symKey={symKey}
                        dateInfo={dateInfo}
                        summary={summary}
                        slideBadge="Slide 2 / 2"
                    />
                    <SignalListSection
                        x={padX}
                        y={236}
                        w={contentW}
                        h={1028}
                        activeSignals={activeSignals}
                        summary={summary}
                        symKey={symKey}
                        detailed={true}
                    />
                    <CardFooter padX={padX} contentW={contentW} y={1308} handle={handle} />
                </>
            )}
        </svg>
    );
}
