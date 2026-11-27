// Pure utilities for computing daily signal performance metrics & layout
// for the Magic Walls Instagram Card generator (Stories 9:16 & Feed/Carousel 4:5).

export function parseTimeToMinutes(timeStr) {
    if (!timeStr) return -1;
    const clean = String(timeStr).slice(0, 5);
    const [hh, mm] = clean.split(":");
    const h = parseInt(hh, 10);
    const m = parseInt(mm, 10);
    if (Number.isNaN(h) || Number.isNaN(m)) return -1;
    return h * 60 + m;
}

export function formatBrNumber(val, decimals = 0) {
    const n = Number(val);
    if (!Number.isFinite(n)) return "—";
    return n.toLocaleString("pt-BR", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

export function formatPtsLabel(pts, isWdo = false, withSign = true) {
    const n = Number(pts);
    if (!Number.isFinite(n)) return "0 pts";
    const dec = isWdo ? 1 : 0;
    const rounded = isWdo ? Math.round(n * 10) / 10 : Math.round(n);
    const sign = withSign ? (rounded > 0 ? "+" : rounded < 0 ? "-" : "") : (rounded < 0 ? "-" : "");
    return `${sign}${formatBrNumber(Math.abs(rounded), dec)} pts`;
}

export function formatSessionDateBr(dateStr) {
    if (!dateStr) {
        const now = new Date();
        const dd = String(now.getDate()).padStart(2, "0");
        const mm = String(now.getMonth() + 1).padStart(2, "0");
        const yyyy = now.getFullYear();
        return { short: `${dd}/${mm}/${yyyy}`, iso: `${yyyy}-${mm}-${dd}`, weekday: "" };
    }
    const clean = String(dateStr).trim().slice(0, 10);
    const m = clean.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) {
        return { short: clean, iso: clean.replace(/\//g, "-"), weekday: "" };
    }
    const [, yyyy, mm, dd] = m;
    const d = new Date(Number(yyyy), Number(mm) - 1, Number(dd));
    const days = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
    const weekday = Number.isFinite(d.getDay()) ? days[d.getDay()] : "";
    return {
        short: `${dd}/${mm}/${yyyy}`,
        iso: `${yyyy}-${mm}-${dd}`,
        weekday,
    };
}

export function getAnchorCode(dv) {
    const anchorUpper = String(dv?.anchor || "").toUpperCase();
    const hasWall = anchorUpper.includes("WALL") || Boolean(dv?.nearWall);
    const hasExtremo = anchorUpper.includes("EXTREMO");
    if (hasWall && hasExtremo) return "XW";
    if (hasWall) return "W";
    if (hasExtremo) return "X";
    return "D";
}

function findBarIndexByTime(bars, timeStr) {
    if (!Array.isArray(bars) || !bars.length || !timeStr) return -1;
    const target = String(timeStr).slice(0, 5);
    const exact = bars.findIndex((b) => String(b?.time || "").slice(0, 5) === target);
    if (exact >= 0) return exact;

    const targetMin = parseTimeToMinutes(target);
    if (targetMin < 0) return -1;
    let bestIdx = -1;
    let bestDiff = Infinity;
    for (let i = 0; i < bars.length; i += 1) {
        const bm = parseTimeToMinutes(bars[i]?.time);
        if (bm < 0) continue;
        const diff = Math.abs(bm - targetMin);
        if (diff < bestDiff && diff <= 5) {
            bestDiff = diff;
            bestIdx = i;
        }
    }
    return bestIdx;
}

/**
 * FONTE ÚNICA da regra de sinais (stop e proteção). Tudo que mostra ou usa essa regra (cálculo, legenda, card,
 * estúdio de Marketing, rascunhos automáticos) lê daqui. Mudou a regra? Mude só estes números (e a lógica de
 * findPivotStop/buildInstagramSignals); o texto do critério e os rótulos acompanham sozinhos.
 *   protectPts: pontos a favor para o sinal ficar "protegido" · minStopPts: distância mínima do stop à entrada ·
 *   stopPadPts: folga atrás do extremo do pivô.
 */
export const SIGNAL_RULES = {
    WIN: { protectPts: 150, minStopPts: 100, stopPadPts: 15 },
    WDO: { protectPts: 4.0, minStopPts: 3.0, stopPadPts: 1.0 },
};

export function signalRulesFor(symKey) {
    return String(symKey || "").toUpperCase() === "WDO" ? SIGNAL_RULES.WDO : SIGNAL_RULES.WIN;
}

const fmtRulePts = (n) => `${Number.isInteger(n) ? n : n.toFixed(1).replace(".", ",")} pt${n === 1 ? "" : "s"}`;

/** Textos da regra gerados a partir de SIGNAL_RULES (nunca digitados à mão em outro arquivo). */
export function describeSignalRule(symKey) {
    const r = signalRulesFor(symKey);
    const protTxt = fmtRulePts(r.protectPts);
    return {
        protTxt,
        ruleTxt: `Critério: stop atrás do extremo do pivô (+${fmtRulePts(r.stopPadPts)}, mínimo ${fmtRulePts(r.minStopPts)} da entrada) · proteção após +${protTxt} a favor.`,
    };
}

/**
 * Computes the protective stop level behind the signal pivot extreme (+15 pts WIN / +1.0 pt WDO padding),
 * enforcing a minimum stop distance from entry (100 pts WIN / 3.0 pts WDO).
 */
function findPivotStop(entryPrice, pivotPrice, isBull, isWdo) {
    const { minStopPts: minDist, stopPadPts: pad } = isWdo ? SIGNAL_RULES.WDO : SIGNAL_RULES.WIN;
    const safePivot = Number.isFinite(Number(pivotPrice)) && Number(pivotPrice) > 0
        ? Number(pivotPrice)
        : entryPrice;

    if (isBull) {
        const stopPrice = Math.min(entryPrice - minDist, safePivot - pad);
        return {
            stopPrice,
            stopLabel: "Stop",
            stopDist: entryPrice - stopPrice,
        };
    }

    const stopPrice = Math.max(entryPrice + minDist, safePivot + pad);
    return {
        stopPrice,
        stopLabel: "Stop",
        stopDist: stopPrice - entryPrice,
    };
}

/**
 * Computes each signal's confirmation entry, technical pivot stop, and Option A MFE:
 * - Stop is placed behind the signal pivot extreme (+15 pts WIN / +1.0 pt WDO, minimum 100 / 3.0 pts from entry).
 * - Protection rule: once price walks >= 150 pts (WIN) / >= 4 pts (WDO) in favor BEFORE hitting the stop,
 *   the signal is protected and tracks MFE until the next opposite signal, stop breach, or end of session.
 * - If price hits the stop BEFORE reaching 150 pts (WIN) / 4 pts (WDO) in favor, it is transparently
 *   recorded as a STOP (-stopPts) and subtracted from the daily net points KPI.
 */
export function buildInstagramSignals(bars = [], divergences = [], symKey = "WIN", excludedIds = null) {
    const isWdo = String(symKey || "").toUpperCase() === "WDO";
    const protectThresholdPts = signalRulesFor(symKey).protectPts;
    const roundPts = (v) => (isWdo ? Math.round(Number(v || 0) * 10) / 10 : Math.round(Number(v || 0)));

    if (!Array.isArray(bars) || bars.length === 0 || !Array.isArray(divergences) || divergences.length === 0) {
        return {
            allSignals: [],
            activeSignals: [],
            summary: {
                totalSignals: 0,
                buyCount: 0,
                sellCount: 0,
                winCount: 0,
                stopCount: 0,
                neutralCount: 0,
                bestSignal: null,
                grossMfePts: 0,
                totalStopPts: 0,
                netPts: 0,
                totalMfePts: 0,
                avgMfePts: 0,
                positiveCount: 0,
                protectThresholdPts,
            },
        };
    }

    // 1. Resolve each divergence onto the official M5 session bars
    const resolved = [];
    divergences.forEach((dv, rawIdx) => {
        if (!dv) return;
        const isBull = dv.type === "BULL_DIV";
        const dir = isBull ? 1 : -1;

        const confTimeStr = dv.confTime ? String(dv.confTime).slice(0, 5) : "";
        const currTimeStr = dv.currTime ? String(dv.currTime).slice(0, 5) : "";
        const prevTimeStr = dv.prevTime ? String(dv.prevTime).slice(0, 5) : "";

        const pivotIdx = findBarIndexByTime(bars, currTimeStr);
        const prevIdx = findBarIndexByTime(bars, prevTimeStr);
        let entryIdx = confTimeStr ? findBarIndexByTime(bars, confTimeStr) : -1;
        if (entryIdx < 0) entryIdx = pivotIdx;
        if (entryIdx < 0) return;

        const entryBar = bars[entryIdx];
        const entryTime = String(entryBar?.time || confTimeStr || currTimeStr).slice(0, 5);
        const entryPrice = Number(entryBar?.close ?? dv.currPrice ?? 0);
        const pivotPrice = Number(dv.currPrice ?? (isBull ? entryBar?.low : entryBar?.high) ?? entryPrice);
        const prevPrice = Number(dv.prevPrice ?? pivotPrice);
        const anchorCode = getAnchorCode(dv);

        const id = `${dir > 0 ? "B" : "S"}_${entryTime}_${anchorCode}_${rawIdx}`;
        resolved.push({
            id,
            rawIdx,
            dir,
            isBull,
            directionLabel: isBull ? "COMPRA" : "VENDA",
            anchorCode,
            anchorText: dv.anchor || (anchorCode === "XW" ? "Wall + Extremo" : anchorCode === "W" ? "Wall" : anchorCode === "X" ? "Extremo" : "Divergência"),
            entryIdx,
            entryTime,
            entryPrice,
            pivotIdx: pivotIdx >= 0 ? pivotIdx : entryIdx,
            pivotTime: currTimeStr || entryTime,
            pivotPrice,
            prevIdx: prevIdx >= 0 ? prevIdx : (pivotIdx >= 0 ? pivotIdx : entryIdx),
            prevTime: prevTimeStr || entryTime,
            prevPrice,
            prevWave: Number(dv.prevWave ?? 0),
            currWave: Number(dv.currWave ?? 0),
            isPendingTrigger: Boolean(dv.isPendingTrigger),
        });
    });

    // Sort chronologically by confirmation bar index, then pivot index
    resolved.sort((a, b) => (a.entryIdx - b.entryIdx) || (a.pivotIdx - b.pivotIdx) || (a.rawIdx - b.rawIdx));

    // Helper to compute transparent Wall Stop + Protection + Option A MFE on an ordered list
    const computeMetrics = (list) => {
        return list.map((sig, i) => {
            // Find next opposite signal confirmed strictly after this entry bar
            let nextOpp = null;
            for (let j = i + 1; j < list.length; j += 1) {
                if (list[j].dir !== sig.dir && list[j].entryIdx > sig.entryIdx) {
                    nextOpp = list[j];
                    break;
                }
            }
            const windowEndIdx = nextOpp ? nextOpp.entryIdx : bars.length - 1;
            const windowEndTime = String(bars[windowEndIdx]?.time || sig.entryTime).slice(0, 5);
            const endedBy = nextOpp ? "SINAL_OPOSTO" : "FECHAMENTO";
            let effectiveWindowEndIdx = windowEndIdx;
            let effectiveWindowEndTime = windowEndTime;
            let effectiveEndedBy = endedBy;

            const { stopPrice, stopLabel, stopDist } = findPivotStop(sig.entryPrice, sig.pivotPrice, sig.isBull, isWdo);
            const stopPts = roundPts(stopDist);

            let bestPx = sig.entryPrice;
            let bestIdx = sig.entryIdx;
            let mfePts = 0;
            let isProtected = false;
            let isStopped = false;
            let stopIdx = -1;
            let stopTime = "";

            for (let k = sig.entryIdx + 1; k <= windowEndIdx; k += 1) {
                const b = bars[k];
                if (!b) continue;
                const hi = Number(b.high ?? b.close);
                const lo = Number(b.low ?? b.close);
                const favInBar = sig.isBull ? (hi - sig.entryPrice) : (sig.entryPrice - lo);
                const hitStopInBar = sig.isBull ? (lo <= stopPrice) : (hi >= stopPrice);

                if (!isProtected) {
                    // Conservative transparency: if stop level is touched before protection was already reached
                    if (hitStopInBar) {
                        isStopped = true;
                        stopIdx = k;
                        stopTime = String(b.time || sig.entryTime).slice(0, 5);
                        break;
                    }
                    if (favInBar >= protectThresholdPts) {
                        isProtected = true;
                    }
                } else if (hitStopInBar) {
                    // Close MFE measurement window once price breaches the technical stop even after protection
                    effectiveWindowEndIdx = k;
                    effectiveWindowEndTime = String(b.time || sig.entryTime).slice(0, 5);
                    effectiveEndedBy = "STOP_POS_PROTECAO";
                    break;
                }

                if (sig.isBull) {
                    if (hi > bestPx) {
                        bestPx = hi;
                        bestIdx = k;
                        mfePts = Math.max(0, bestPx - sig.entryPrice);
                    }
                } else {
                    if (lo < bestPx) {
                        bestPx = lo;
                        bestIdx = k;
                        mfePts = Math.max(0, sig.entryPrice - bestPx);
                    }
                }
            }

            const cleanMfe = roundPts(mfePts);
            const status = isStopped ? "STOP" : isProtected ? "PROTECTED" : "NEUTRAL";
            const resultPts = isStopped ? -stopPts : cleanMfe;

            const peakTime = String(bars[bestIdx]?.time || sig.entryTime).slice(0, 5);
            const endTimeForDur = isStopped ? stopTime : peakTime;
            const entryMin = parseTimeToMinutes(sig.entryTime);
            const endMin = parseTimeToMinutes(endTimeForDur);
            const durationMin = (entryMin >= 0 && endMin >= entryMin) ? (endMin - entryMin) : 0;

            return {
                ...sig,
                num: i + 1,
                status,
                isStopped,
                isProtected,
                stopPrice,
                stopLabel,
                stopPts,
                stopIdx,
                stopTime,
                windowEndIdx: effectiveWindowEndIdx,
                windowEndTime: effectiveWindowEndTime,
                endedBy: effectiveEndedBy,
                bestPx,
                bestIdx,
                peakTime,
                mfePts: cleanMfe,
                resultPts,
                durationMin,
                isBest: false,
            };
        });
    };

    const allWithMetrics = computeMetrics(resolved);
    const excludedSet = excludedIds instanceof Set ? excludedIds : new Set(excludedIds || []);
    const activeBase = resolved.filter((s) => !excludedSet.has(s.id));
    const activeSignals = computeMetrics(activeBase);

    let bestSignal = null;
    let grossMfePts = 0;
    let totalStopPts = 0;
    let buyCount = 0;
    let sellCount = 0;
    let winCount = 0;
    let stopCount = 0;
    let neutralCount = 0;

    activeSignals.forEach((s) => {
        if (s.isBull) buyCount += 1;
        else sellCount += 1;

        if (s.isStopped) {
            stopCount += 1;
            totalStopPts += s.stopPts;
        } else {
            grossMfePts += s.mfePts;
            if (s.isProtected) winCount += 1;
            else neutralCount += 1;
            if (!bestSignal || s.mfePts > bestSignal.mfePts) {
                bestSignal = s;
            }
        }
    });

    if (bestSignal && bestSignal.mfePts > 0) {
        bestSignal.isBest = true;
    }

    const grossRounded = roundPts(grossMfePts);
    const stopsRounded = roundPts(totalStopPts);
    const netRounded = roundPts(grossMfePts - totalStopPts);
    const avgRounded = activeSignals.length > 0 ? roundPts((grossMfePts - totalStopPts) / activeSignals.length) : 0;

    return {
        allSignals: allWithMetrics,
        activeSignals,
        summary: {
            totalSignals: activeSignals.length,
            buyCount,
            sellCount,
            winCount,
            stopCount,
            neutralCount,
            bestSignal,
            grossMfePts: grossRounded,
            totalStopPts: stopsRounded,
            netPts: netRounded,
            totalMfePts: netRounded,
            avgMfePts: avgRounded,
            positiveCount: winCount,
            protectThresholdPts,
        },
    };
}

/**
 * Computes collision-free (x, y) coordinates for circular numbered badges on the chart.
 * Separates top (sell) and bottom (buy) markers and staggers vertically when horizontally close.
 */
export function computeCollisionFreeMarkers(signals, { toX, toY, bars, plotTop, plotBot, plotLeft, plotRight, radius = 19 }) {
    const placed = [];
    const minDistX = radius * 2.55;
    const stepY = radius * 2.35;

    const topGroup = [];
    const botGroup = [];

    signals.forEach((sig) => {
        const bar = bars[sig.entryIdx];
        const x = toX(sig.entryIdx);
        const anchorY = sig.isBull
            ? toY(Number(bar?.low ?? sig.entryPrice))
            : toY(Number(bar?.high ?? sig.entryPrice));
        const clampedX = Math.max(plotLeft + radius + 4, Math.min(plotRight - radius - 4, x));

        const item = {
            sig,
            candleX: x,
            candleY: anchorY,
            badgeX: clampedX,
            badgeY: sig.isBull ? anchorY + radius + 16 : anchorY - radius - 16,
        };
        if (sig.isBull) botGroup.push(item);
        else topGroup.push(item);
    });

    // Resolve overlaps in top group
    topGroup.sort((a, b) => a.badgeX - b.badgeX);
    for (let i = 0; i < topGroup.length; i += 1) {
        const cur = topGroup[i];
        cur.badgeY = Math.max(plotTop + radius + 6, Math.min(plotBot - radius - 6, cur.badgeY));
        for (let pass = 0; pass < 4; pass += 1) {
            let collided = false;
            for (let j = 0; j < i; j += 1) {
                const prev = topGroup[j];
                if (Math.abs(cur.badgeX - prev.badgeX) < minDistX && Math.abs(cur.badgeY - prev.badgeY) < stepY * 0.92) {
                    const tryUp = prev.badgeY - stepY;
                    if (tryUp >= plotTop + radius + 4) {
                        cur.badgeY = tryUp;
                    } else {
                        cur.badgeY = Math.min(plotBot - radius - 6, prev.badgeY + stepY);
                    }
                    collided = true;
                }
            }
            if (!collided) break;
        }
        placed.push(cur);
    }

    // Resolve overlaps in bottom group
    botGroup.sort((a, b) => a.badgeX - b.badgeX);
    for (let i = 0; i < botGroup.length; i += 1) {
        const cur = botGroup[i];
        cur.badgeY = Math.max(plotTop + radius + 6, Math.min(plotBot - radius - 6, cur.badgeY));
        for (let pass = 0; pass < 4; pass += 1) {
            let collided = false;
            for (let j = 0; j < i; j += 1) {
                const prev = botGroup[j];
                if (Math.abs(cur.badgeX - prev.badgeX) < minDistX && Math.abs(cur.badgeY - prev.badgeY) < stepY * 0.92) {
                    const tryDown = prev.badgeY + stepY;
                    if (tryDown <= plotBot - radius - 4) {
                        cur.badgeY = tryDown;
                    } else {
                        cur.badgeY = Math.max(plotTop + radius + 6, prev.badgeY - stepY);
                    }
                    collided = true;
                }
            }
            if (!collided) break;
        }
        placed.push(cur);
    }

    placed.sort((a, b) => a.sig.num - b.sig.num);
    return placed;
}

/**
 * Generates a ready-to-paste institutional Instagram caption (Ink Azul brand voice, zero emojis)
 * listing all active signals transparently including stops.
 */
export function buildInstagramCaption({ symKey, dateInfo, activeSignals, summary, handle }) {
    const isWdo = String(symKey || "").toUpperCase() === "WDO";
    const dec = isWdo ? 1 : 0;
    const { protTxt, ruleTxt } = describeSignalRule(symKey);
    const assetName = isWdo ? "Mini-Dólar (WDO)" : "Mini-Índice (WIN)";
    const header = `Magic Walls — Resumo do pregão · ${assetName} (${dateInfo.weekday ? `${dateInfo.weekday}, ` : ""}${dateInfo.short})`;
    if (!activeSignals.length) {
        return `${header}\n\nSem sinais registrados no pregão.`;
    }
    const lines = activeSignals.map((s) => {
        const dirWord = s.isBull ? "Compra" : "Venda";
        if (s.isStopped) {
            return `• #${s.num} · ${s.entryTime} · ${s.anchorCode} ${dirWord} (${formatBrNumber(s.entryPrice, dec)}) → Stop ${formatPtsLabel(s.resultPts, isWdo)} (${formatBrNumber(s.stopPrice, dec)} às ${s.stopTime})`;
        }
        const bestTag = s.isBest ? " [Melhor pernada]" : "";
        return `• #${s.num} · ${s.entryTime} · ${s.anchorCode} ${dirWord} (${formatBrNumber(s.entryPrice, dec)}) → ${formatPtsLabel(s.mfePts, isWdo)}${bestTag}`;
    });
    const bestTxt = summary.bestSignal && summary.bestSignal.mfePts > 0
        ? `Melhor pernada: ${formatPtsLabel(summary.bestSignal.mfePts, isWdo)} (#${summary.bestSignal.num} às ${summary.bestSignal.entryTime})`
        : "";
    const stopsDetail = summary.stopCount > 0
        ? ` · ${summary.stopCount} stop${summary.stopCount > 1 ? "s" : ""} (-${formatPtsLabel(summary.totalStopPts, isWdo, false)})`
        : " · 0 stops";
    const sumTxt = `Total: ${summary.totalSignals} sinais (${summary.winCount} protegidos ≥${protTxt}${stopsDetail}) · Saldo máx. a favor: ${formatPtsLabel(summary.netPts, isWdo)}`;
    const cleanHandle = handle ? handle.trim() : "@magicwallsb3";
    const footer = [
        `Terminal GEX + Fluxo Smart Money: app.magicwalls.com.br`,
        cleanHandle,
        "",
        "Estudo quantitativo de caráter estritamente educacional. Não constitui recomendação de investimento.",
    ].join("\n");

    return [header, "", ...lines, "", bestTxt, sumTxt, ruleTxt, "", footer]
        .filter((v) => v !== "" || true)
        .join("\n")
        .replace(/\n{3,}/g, "\n\n");
}
