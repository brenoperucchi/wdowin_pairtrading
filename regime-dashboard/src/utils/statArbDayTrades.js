import RAW_2026 from "../data/statarb2026Data.json";

export const STATARB_STRAT_META = {
    CONS: {
        id: "CONS",
        short: "CONS",
        label: "1. CONSENSO (WDO+DI)",
        color: "#00e87a",
        zRule: "WDO ±1.8 + DI ±1.2 (ou DI ±2.2 + WDO ±1.2)",
        nweProx: 0.15,
        beAct: 150,
    },
    DI_NWE: {
        id: "DI_NWE",
        short: "DI_NWE",
        label: "2. DI_NWE (ISOLADO)",
        color: "#a855f7",
        zRule: "DI ±2.2 + NWE 10%",
        nweProx: 0.10,
        beAct: 200,
    },
    WDO_NWE: {
        id: "WDO_NWE",
        short: "WDO_NWE",
        label: "3. WDO_NWE (ISOLADO)",
        color: "#f59e0b",
        zRule: "WDO ±1.4 + NWE 15%",
        nweProx: 0.15,
        beAct: 150,
    },
};

export function calcWallTpSlJs(direction, entryPx, walls, minPts = 200, slBuf = 30, tpBuf = 10) {
    const wallList = Array.isArray(walls?.walls) ? walls.walls : (Array.isArray(walls) ? walls : []);
    const wallPrices = Array.from(
        new Set(
            wallList
                .map((w) => (typeof w === "object" && w !== null ? Number(w.price) : Number(w)))
                .filter((p) => Number.isFinite(p) && p > 0)
        )
    ).sort((a, b) => a - b);

    const isBuy = direction === "BUY" || direction === 1;
    if (wallPrices.length === 0) {
        const tpPts = Math.max(minPts, 400);
        const slPts = Math.max(minPts, 200);
        const tpPx = isBuy ? entryPx + tpPts : entryPx - tpPts;
        const slPx = isBuy ? entryPx - slPts : entryPx + slPts;
        return { tpPx: Math.round(tpPx), slPx: Math.round(slPx), tpPts: Math.round(tpPts), slPts: Math.round(slPts) };
    }

    if (isBuy) {
        const downWalls = wallPrices.filter((w) => w <= entryPx);
        const prevWall = downWalls.length > 0 ? downWalls[downWalls.length - 1] : entryPx - minPts;
        const slPts = Math.max(minPts, (entryPx - prevWall) + slBuf);
        const slPx = entryPx - slPts;

        const upWalls = wallPrices.filter((w) => (w - tpBuf) - entryPx >= minPts);
        const tpPx = upWalls.length > 0 ? upWalls[0] - tpBuf : entryPx + Math.max(minPts * 2, 400);
        const tpPts = tpPx - entryPx;
        return { tpPx: Math.round(tpPx), slPx: Math.round(slPx), tpPts: Math.round(tpPts), slPts: Math.round(slPts) };
    } else {
        const upWalls = wallPrices.filter((w) => w >= entryPx);
        const prevWall = upWalls.length > 0 ? upWalls[0] : entryPx + minPts;
        const slPts = Math.max(minPts, (prevWall - entryPx) + slBuf);
        const slPx = entryPx + slPts;

        const downWalls = [...wallPrices].reverse().filter((w) => entryPx - (w + tpBuf) >= minPts);
        const tpPx = downWalls.length > 0 ? downWalls[0] + tpBuf : entryPx - Math.max(minPts * 2, 400);
        const tpPts = entryPx - tpPx;
        return { tpPx: Math.round(tpPx), slPx: Math.round(slPx), tpPts: Math.round(tpPts), slPts: Math.round(slPts) };
    }
}

export function simulateDayStatArbTradesJs(historyBars, walls = [], isLiveSession = true) {
    if (!Array.isArray(historyBars) || historyBars.length === 0) return [];

    // Filter out empty padded bars (that have no win_price)
    const validBars = historyBars.filter((b) => b && b.bar_time && b.win_price != null && Number.isFinite(Number(b.win_price)) && Number(b.win_price) > 0);
    if (validBars.length === 0) return [];

    const sessionDate = validBars[validBars.length - 1]?.date || "";

    // If viewing a historical date that is in RAW_2026.trades and we don't have intraday M5 high/low on all bars,
    // check if RAW_2026 has audited trades for that date
    const auditedTradesForDate = (RAW_2026.trades || []).filter((t) => t.date === sessionDate);
    if (!isLiveSession && auditedTradesForDate.length > 0) {
        return auditedTradesForDate;
    }

    const stratConfigs = [
        { id: "CONS", sigKey: "sig_cons", beAct: 150, waitBars: 4 },
        { id: "WDO_NWE", sigKey: "sig_wdo", beAct: 150, waitBars: 4 },
        { id: "DI_NWE", sigKey: "sig_di", beAct: 200, waitBars: 4 },
    ];

    const allTrades = [];

    for (const cfg of stratConfigs) {
        const { id: stratId, sigKey, beAct, waitBars } = cfg;
        let pos = null;
        let cooldownUntil = -1;

        for (let i = 0; i < validBars.length; i++) {
            const b = validBars[i];
            const bt = b.bar_time || "";
            const [hh, mm] = bt.split(":").map(Number);
            const tm = (hh || 0) * 60 + (mm || 0);
            const px = Number(b.win_price);
            const hi = Number(b.win_high ?? px);
            const lo = Number(b.win_low ?? px);
            const zw = Number(b.z ?? 0);
            const zd = Number(b.z_di ?? 0);
            const isLastLiveBar = isLiveSession && i === validBars.length - 1;
            const isClosedBar = !isLastLiveBar;

            if (pos !== null) {
                const d = pos.dir;
                let closed = false;
                let pnlPts = 0;
                let exitPx = px;
                let exitReason = "";

                if (d === 1) {
                    if (lo <= pos.slPx) {
                        pnlPts = pos.slPx - pos.entryPx;
                        exitPx = pos.slPx;
                        exitReason = pos.beTriggered ? "STOP BE (+15p)" : "STOP WALL";
                        closed = true;
                    } else if (hi >= pos.tpPx) {
                        pnlPts = pos.tpPx - pos.entryPx;
                        exitPx = pos.tpPx;
                        exitReason = "ALVO WALL";
                        closed = true;
                    } else if (
                        isClosedBar &&
                        ((stratId === "WDO_NWE" && zw >= 0.2) ||
                            (stratId === "DI_NWE" && zd >= 0.2) ||
                            (stratId === "CONS" && zw >= 0.0 && zd >= 0.0)) &&
                        px - pos.entryPx >= 200
                    ) {
                        pnlPts = px - pos.entryPx;
                        exitPx = px;
                        exitReason = "ALVO Z-REV";
                        closed = true;
                    } else if (beAct > 0 && hi - pos.entryPx >= beAct && pos.slPx < pos.entryPx) {
                        pos.slPx = pos.entryPx + 15;
                        pos.beTriggered = true;
                        pos.beTime = bt;
                        pos.beStopPx = pos.slPx;
                        pos.beTrigPx = pos.entryPx + beAct;
                    }
                } else {
                    if (hi >= pos.slPx) {
                        pnlPts = pos.entryPx - pos.slPx;
                        exitPx = pos.slPx;
                        exitReason = pos.beTriggered ? "STOP BE (+15p)" : "STOP WALL";
                        closed = true;
                    } else if (lo <= pos.tpPx) {
                        pnlPts = pos.entryPx - pos.tpPx;
                        exitPx = pos.tpPx;
                        exitReason = "ALVO WALL";
                        closed = true;
                    } else if (
                        isClosedBar &&
                        ((stratId === "WDO_NWE" && zw <= -0.2) ||
                            (stratId === "DI_NWE" && zd <= -0.2) ||
                            (stratId === "CONS" && zw <= 0.0 && zd <= 0.0)) &&
                        pos.entryPx - px >= 200
                    ) {
                        pnlPts = pos.entryPx - px;
                        exitPx = px;
                        exitReason = "ALVO Z-REV";
                        closed = true;
                    } else if (beAct > 0 && pos.entryPx - lo >= beAct && pos.slPx > pos.entryPx) {
                        pos.slPx = pos.entryPx - 15;
                        pos.beTriggered = true;
                        pos.beTime = bt;
                        pos.beStopPx = pos.slPx;
                        pos.beTrigPx = pos.entryPx - beAct;
                    }
                }

                if (!closed && isClosedBar && tm >= 17 * 60 + 40) {
                    pnlPts = (px - pos.entryPx) * d;
                    exitPx = px;
                    exitReason = "FECHAMENTO 17:40";
                    closed = true;
                }

                if (closed) {
                    allTrades.push({
                        id: `${sessionDate}_${pos.entryTime}_${stratId}`,
                        date: sessionDate,
                        strategy_id: stratId,
                        direction: d === 1 ? "COMPRA" : "VENDA",
                        dir_num: d,
                        entry_time: pos.entryTime,
                        exit_time: bt,
                        entry_price: Math.round(pos.entryPx),
                        exit_price: Math.round(exitPx),
                        tp_price: Math.round(pos.tpPx),
                        stop_price: Math.round(pos.initSlPx),
                        be_triggered: pos.beTriggered,
                        be_time: pos.beTime,
                        be_stop_price: pos.beTriggered ? Math.round(pos.beStopPx) : null,
                        be_trigger_price: pos.beTriggered ? Math.round(pos.beTrigPx) : null,
                        pts: Math.round(pnlPts),
                        brl_2c: Math.round(pnlPts * 0.4),
                        exit_reason: exitReason,
                        status: "FECHADA",
                    });
                    pos = null;
                    cooldownUntil = i + waitBars;
                }
                continue;
            }

            if (!isClosedBar || i <= cooldownUntil || tm < 545 || tm > 930) continue;

            const sigVal = Number(b[sigKey] || 0);
            if (sigVal !== 0 && px > 0) {
                const dirNum = sigVal < 0 ? 1 : -1;
                const tpPx = Number(b.wall_tp) || calcWallTpSlJs(dirNum, px, walls).tpPx;
                const slPx = Number(b.wall_sl) || calcWallTpSlJs(dirNum, px, walls).slPx;
                const tpDist = Math.abs(tpPx - px);
                const slDist = Math.abs(slPx - px);
                if (slDist <= 300 && tpDist / Math.max(slDist, 1) >= 1.4) {
                    pos = {
                        dir: dirNum,
                        entryPx: px,
                        tpPx,
                        slPx,
                        initSlPx: slPx,
                        entryTime: bt,
                        beTriggered: false,
                        beTime: null,
                        beStopPx: null,
                        beTrigPx: null,
                    };
                }
            }
        }

        if (pos !== null && validBars.length > 0) {
            const lastB = validBars[validBars.length - 1];
            const lastPx = Number(lastB.win_price || pos.entryPx);
            const d = pos.dir;
            const livePts = (lastPx - pos.entryPx) * d;
            allTrades.push({
                id: `${sessionDate}_${pos.entryTime}_${stratId}`,
                date: sessionDate,
                strategy_id: stratId,
                direction: d === 1 ? "COMPRA" : "VENDA",
                dir_num: d,
                entry_time: pos.entryTime,
                exit_time: lastB.bar_time || pos.entryTime,
                entry_price: Math.round(pos.entryPx),
                exit_price: Math.round(lastPx),
                tp_price: Math.round(pos.tpPx),
                stop_price: Math.round(pos.initSlPx),
                be_triggered: pos.beTriggered,
                be_time: pos.beTime,
                be_stop_price: pos.beTriggered ? Math.round(pos.beStopPx) : null,
                be_trigger_price: pos.beTriggered ? Math.round(pos.beTrigPx) : null,
                pts: Math.round(livePts),
                brl_2c: Math.round(livePts * 0.4),
                exit_reason: "⏳ EM ABERTO (AO VIVO)",
                status: "ABERTA",
            });
        }
    }

    return allTrades.sort((a, b) => a.entry_time.localeCompare(b.entry_time) || a.strategy_id.localeCompare(b.strategy_id));
}

export function getAllAudited2026Trades() {
    return RAW_2026.trades || [];
}
