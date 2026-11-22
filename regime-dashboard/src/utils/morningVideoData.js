// Normalização de dados do endpoint /api/morning-brief e gerador de legenda pré-pregão.

export const DEFAULT_FALLBACK_BRIEF = {
    ok: true,
    is_fallback: true,
    ref_date: "20/11/2026",
    generated_at: "2026-11-20 08:30:00",
    win: {
        ticker: "WIN",
        ref_date: "2026-11-19",
        updated_at: "2026-11-20 07:31:09",
        current_price: 167470.0,
        walls: [
            { price: 160355.848, type: "Wall", width: 3, style: 0, strike_ibov: 159000, gex: -117425235094.98 },
            { price: 163381.43, type: "Wall", width: 2, style: 0, strike_ibov: 162000, gex: -50434927178.74 },
            { price: 165398.485, type: "Wall", width: 1, style: 0, strike_ibov: 164000, gex: -15138681672.84 },
            { price: 166407.012, type: "Wall", width: 1, style: 0, strike_ibov: 165000, gex: -37006540652.68 },
            { price: 167415.54, type: "Wall", width: 1, style: 0, strike_ibov: 166000, gex: -30803381265.46 },
            { price: 168424.067, type: "Wall", width: 1, style: 0, strike_ibov: 167000, gex: -21003591945.85 },
            { price: 169432.594, type: "Wall", width: 1, style: 0, strike_ibov: 168000, gex: -25282437169.94 },
            { price: 170441.122, type: "Wall", width: 2, style: 0, strike_ibov: 169000, gex: -56302019915.88 },
            { price: 171597.841, type: "GammaFlip", width: 2, style: 0, gex: 0 },
            { price: 175006.15, type: "MaxGamma", width: 3, style: 0, gex: -250976087371.35 },
            { price: 163114.938, type: "MinGamma", width: 3, style: 0, gex: -386860816965.57 },
        ],
        report: {
            report_date: "20/11/2026",
            gamma_flip: 171598.0,
            status: "NEGATIVE GAMMA (Mercado Vendido)",
            bias: "QUEDA / ALTA VOLATILIDADE",
            great_wall: { price: 160356.0, note: "Baseada no IBOV 159000" },
            immediate_resistance: 168424.0,
            immediate_support: 167416.0,
            conclusion: "Regime de Gamma Negativo favorece aceleração de movimentos; Grande Muralha nos 160.356 atua como ímã gravitacional.",
        },
    },
    wdo: {
        ticker: "USD_BRL",
        ref_date: "2026-11-20",
        updated_at: "2026-11-20 07:31:14",
        current_price: 5943.5,
        walls: [
            { price: 5800.0, type: "Wall", width: 1, style: 0, strike_spy: 5800, gex: 2759933820.99 },
            { price: 5900.0, type: "Wall", width: 2, style: 0, strike_spy: 5900, gex: 4903896560.45 },
            { price: 5920.0, type: "Wall", width: 1, style: 0, strike_spy: 5920, gex: 2338720000.0 },
            { price: 5950.0, type: "Wall", width: 2, style: 0, strike_spy: 5950, gex: 4737500000.0 },
            { price: 5980.0, type: "Wall", width: 3, style: 0, strike_spy: 5980, gex: 6887020000.0 },
            { price: 6000.0, type: "Wall", width: 1, style: 0, strike_spy: 6000, gex: 4523690000.0 },
            { price: 6050.0, type: "Wall", width: 1, style: 0, strike_spy: 6050, gex: 403180000.0 },
            { price: 6061.77, type: "GammaFlip", width: 2, style: 0, gex: 0.0 },
            { price: 5935.14, type: "MaxGamma", width: 3, style: 0, gex: 27414819426.76 },
            { price: 6181.24, type: "MinGamma", width: 3, style: 0, gex: 5990563998.16 },
        ],
        report: {
            expiry: "2026-12-01",
            report_date: "20/11/2026",
            current_price: 5943.5,
            contract: "WDOZ26",
            gamma_flip: 6061.77,
            status: "NEGATIVE GAMMA (Zona de Alta Volatilidade / Hedge Vendido)",
            bias: "QUEDA / ALTA VOLATILIDADE (Choppy/Rapido)",
            min_gamma: 6181.24,
            max_gamma: 5935.14,
        },
    },
    calendar: {
        date: "20/11/2026",
        events: [
            { time: "10:00", currency: "BRL", title: "Produção de Veículos (Mensal) (Oct)", impact: "MEDIO", detail: "Prev: -1,1%" },
            { time: "10:00", currency: "BRL", title: "Vendas de Veículos (Mensal) (Oct)", impact: "MEDIO", detail: "Prev: 2,3%" },
            { time: "10:25", currency: "USD", title: "Discurso de Waller, membro do Fed", impact: "MEDIO", detail: "" },
            { time: "12:00", currency: "USD", title: "Expectativas de Inflação Michigan (Nov)", impact: "MEDIO", detail: "Prev: 4,7% | Proj: 4,3%" },
        ],
    },
    global_assets: [
        { ticker: "SP500_ES", current_price: 7403.92, gamma_flip: 7350.0, regime: "POSITIVE" },
        { ticker: "NASDAQ_NQ", current_price: 27664.32, gamma_flip: 27500.0, regime: "POSITIVE" },
        { ticker: "GOLD_XAU", current_price: 3727.01, gamma_flip: 3700.0, regime: "POSITIVE" },
        { ticker: "BTC_USD", current_price: 61928.5, gamma_flip: 63000.0, regime: "NEGATIVE" },
    ],
};

export function formatAssetPrice(val, isWdo) {
    const n = Number(val);
    if (!Number.isFinite(n)) return "—";
    if (isWdo) {
        return n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    }
    return Math.round(n).toLocaleString("pt-BR");
}

export function formatDistPts(diff, isWdo) {
    const n = Number(diff);
    if (!Number.isFinite(n)) return "0 pts";
    const sign = n >= 0 ? "+" : "-";
    const absVal = Math.abs(n);
    if (isWdo) {
        return `${sign}${absVal.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} pts`;
    }
    return `${sign}${Math.round(absVal).toLocaleString("pt-BR")} pts`;
}

export function formatGexCompact(gexAbs, isWdo) {
    const v = Math.abs(Number(gexAbs) || 0);
    if (v <= 0) return "—";
    const prefix = isWdo ? "$" : "";
    if (v >= 1e9) {
        const b = v / 1e9;
        return `${prefix}${b >= 10 ? b.toFixed(0) : b.toFixed(1).replace(".", ",")}B`;
    }
    if (v >= 1e6) {
        const m = v / 1e6;
        return `${prefix}${m >= 100 ? m.toFixed(0) : m.toFixed(0)}M`;
    }
    if (v >= 1e3) {
        return `${prefix}${(v / 1e3).toFixed(0)}K`;
    }
    return `${prefix}${Math.round(v)}`;
}

function toBrDate(rawDate) {
    if (!rawDate) return "";
    const s = String(rawDate).trim();
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(s)) return s;
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return `${m[3]}/${m[2]}/${m[1]}`;
    return s;
}

function findNearestByPrice(list, targetPrice, maxRelDiff = 0.015) {
    if (!Number.isFinite(targetPrice) || !list.length) return null;
    let best = null;
    let bestDiff = Infinity;
    for (const item of list) {
        const d = Math.abs(item.price - targetPrice);
        if (d < bestDiff && d / Math.max(1, targetPrice) <= maxRelDiff) {
            best = item;
            bestDiff = d;
        }
    }
    return best;
}

export function normalizeAssetLadder(assetRaw, isWdo) {
    const raw = assetRaw || {};
    const report = raw.report || {};
    const wallsRaw = Array.isArray(raw.walls) ? raw.walls : [];

    const currentPrice = Number(raw.current_price ?? report.current_price ?? 0);

    const gammaFlipObj = wallsRaw.find((w) => w && w.type === "GammaFlip");
    const maxGammaObj = wallsRaw.find((w) => w && w.type === "MaxGamma");
    const minGammaObj = wallsRaw.find((w) => w && w.type === "MinGamma");

    const gammaFlip = Number(gammaFlipObj?.price ?? report.gamma_flip ?? currentPrice);
    const maxGamma = Number(maxGammaObj?.price ?? report.max_gamma ?? 0) || null;
    const minGamma = Number(minGammaObj?.price ?? report.min_gamma ?? 0) || null;

    const isPositiveGamma = Number.isFinite(gammaFlip) && gammaFlip > 0 ? currentPrice >= gammaFlip : false;
    const regimeLabel = isPositiveGamma ? "Gamma positivo" : "Gamma negativo";
    const regimeShort = isPositiveGamma ? "Defesa e reversão" : "Alta volatilidade";
    const regimeColor = isPositiveGamma ? "#4cc38a" : "#e5484d";

    const mainWalls = wallsRaw
        .filter((w) => w && w.type === "Wall" && Number.isFinite(Number(w.price)))
        .map((w) => ({
            price: Number(w.price),
            type: "Wall",
            width: Math.max(1, Math.min(3, Number(w.width) || 1)),
            gexAbs: Math.abs(Number(w.gex) || 0),
            gexSigned: Number(w.gex) || 0,
            strikeRef: w.strike_ibov ?? w.strike_spy ?? null,
        }));

    // Identifica a Grande Muralha / Ímã Dominante
    let magnetCandidate = null;
    const greatWallPrice = Number(report?.great_wall?.price);
    if (!isWdo && Number.isFinite(greatWallPrice) && greatWallPrice > 0) {
        magnetCandidate = findNearestByPrice(mainWalls, greatWallPrice, 0.005);
    }
    if (!magnetCandidate && mainWalls.length) {
        const sortedByStrength = [...mainWalls].sort((a, b) => {
            if (b.width !== a.width) return b.width - a.width;
            if (b.gexAbs !== a.gexAbs) return b.gexAbs - a.gexAbs;
            return Math.abs(a.price - currentPrice) - Math.abs(b.price - currentPrice);
        });
        magnetCandidate = sortedByStrength[0];
    }

    // Resistência & Suporte imediatos
    const aboveWalls = mainWalls
        .filter((w) => w.price >= currentPrice)
        .sort((a, b) => a.price - b.price);
    const belowWalls = mainWalls
        .filter((w) => w.price < currentPrice)
        .sort((a, b) => b.price - a.price);

    let immediateResistance = aboveWalls[0] || null;
    if (!isWdo && Number.isFinite(Number(report.immediate_resistance))) {
        const rFound = findNearestByPrice(mainWalls, Number(report.immediate_resistance), 0.004);
        if (rFound) immediateResistance = rFound;
    }
    let immediateSupport = belowWalls[0] || null;
    if (!isWdo && Number.isFinite(Number(report.immediate_support))) {
        const sFound = findNearestByPrice(mainWalls, Number(report.immediate_support), 0.004);
        if (sFound) immediateSupport = sFound;
    }

    // Monta pool de seleção (até 7 níveis sem sobreposição)
    const flipFar = Number.isFinite(gammaFlip) && currentPrice > 0
        ? Math.abs(gammaFlip - currentPrice) / currentPrice > 0.12
        : true;

    const flipEntry = !flipFar && Number.isFinite(gammaFlip) && gammaFlip > 0
        ? {
            price: gammaFlip,
            type: "GammaFlip",
            width: 2,
            gexAbs: 0,
            gexSigned: 0,
            isGammaFlip: true,
            isMagnet: false,
            priority: 100,
        }
        : null;

    const candidates = [];
    const seenKeys = new Set();

    const pushCandidate = (item, priority, forceTag = {}) => {
        if (!item || !Number.isFinite(item.price)) return;
        const key = `${item.type}_${item.price.toFixed(2)}`;
        if (seenKeys.has(key)) return;
        seenKeys.add(key);
        candidates.push({
            ...item,
            isGammaFlip: Boolean(forceTag.isGammaFlip || item.type === "GammaFlip"),
            isMagnet: Boolean(forceTag.isMagnet || (magnetCandidate && Math.abs(item.price - magnetCandidate.price) < 1e-4)),
            priority,
        });
    };

    if (flipEntry) pushCandidate(flipEntry, 100, { isGammaFlip: true });
    if (magnetCandidate) pushCandidate(magnetCandidate, 95, { isMagnet: true });
    if (immediateResistance) pushCandidate(immediateResistance, 90);
    if (immediateSupport) pushCandidate(immediateSupport, 88);

    // Preenche com próximas 3 acima e 3 abaixo
    aboveWalls.slice(0, 3).forEach((w, idx) => pushCandidate(w, 70 - idx * 5));
    belowWalls.slice(0, 3).forEach((w, idx) => pushCandidate(w, 69 - idx * 5));

    // Ordena por prioridade para deduplicar colisões próximas (< 0.05%)
    candidates.sort((a, b) => b.priority - a.priority);
    const deduped = [];
    for (const c of candidates) {
        const tooClose = deduped.find((d) => {
            // Nunca descarta GammaFlip nem Magnet por proximidade a uma wall comum; só deduplica se idênticos
            const rel = Math.abs(d.price - c.price) / Math.max(1, c.price);
            if (c.isGammaFlip || d.isGammaFlip) return rel < 0.0001;
            return rel < 0.0005;
        });
        if (!tooClose) {
            deduped.push(c);
        }
    }

    // Seleciona até 7 níveis: mantém os prioritários e ordena os restantes por proximidade ao currentPrice
    deduped.sort((a, b) => {
        const aMust = a.isGammaFlip || a.isMagnet || a === immediateResistance || a === immediateSupport ? 1 : 0;
        const bMust = b.isGammaFlip || b.isMagnet || b === immediateResistance || b === immediateSupport ? 1 : 0;
        if (bMust !== aMust) return bMust - aMust;
        if (b.priority !== a.priority) return b.priority - a.priority;
        return Math.abs(a.price - currentPrice) - Math.abs(b.price - currentPrice);
    });

    const selected = deduped.slice(0, 7).sort((a, b) => b.price - a.price);
    const maxGexInLadder = Math.max(1, ...selected.map((s) => s.gexAbs || 0));

    const levels = selected.map((lvl) => {
        const diff = lvl.price - currentPrice;
        let role = diff >= 0 ? "RESISTANCE" : "SUPPORT";
        if (lvl.isGammaFlip) role = "GAMMA_FLIP";
        else if (lvl.isMagnet) role = "MAGNET";

        const gexRatio = lvl.gexAbs > 0
            ? Math.max(0.14, Math.min(1.0, lvl.gexAbs / maxGexInLadder))
            : (lvl.isGammaFlip ? 0.55 : 0.14);

        return {
            price: lvl.price,
            priceLabel: formatAssetPrice(lvl.price, isWdo),
            type: lvl.type,
            role,
            stars: lvl.width || 1,
            gexAbs: lvl.gexAbs,
            gexRatio,
            gexLabel: lvl.isGammaFlip ? "FLIP GEX" : formatGexCompact(lvl.gexAbs, isWdo),
            distPts: diff,
            distLabel: formatDistPts(diff, isWdo),
            isMagnet: Boolean(lvl.isMagnet),
            isGammaFlip: Boolean(lvl.isGammaFlip),
            isImmediateResistance: Boolean(immediateResistance && Math.abs(lvl.price - immediateResistance.price) < 0.01),
            isImmediateSupport: Boolean(immediateSupport && Math.abs(lvl.price - immediateSupport.price) < 0.01),
        };
    });

    let insertIndex = levels.findIndex((l) => l.price < currentPrice);
    if (insertIndex === -1) insertIndex = levels.length;

    const magnetLevel = levels.find((l) => l.isMagnet) || (magnetCandidate ? {
        price: magnetCandidate.price,
        priceLabel: formatAssetPrice(magnetCandidate.price, isWdo),
        stars: magnetCandidate.width || 3,
        distPts: magnetCandidate.price - currentPrice,
        distLabel: formatDistPts(magnetCandidate.price - currentPrice, isWdo),
        gexLabel: formatGexCompact(magnetCandidate.gexAbs, isWdo),
    } : null);

    const resLevel = immediateResistance
        ? {
            price: immediateResistance.price,
            priceLabel: formatAssetPrice(immediateResistance.price, isWdo),
            stars: immediateResistance.width || 1,
            distPts: immediateResistance.price - currentPrice,
            distLabel: formatDistPts(immediateResistance.price - currentPrice, isWdo),
        }
        : null;

    const supLevel = immediateSupport
        ? {
            price: immediateSupport.price,
            priceLabel: formatAssetPrice(immediateSupport.price, isWdo),
            stars: immediateSupport.width || 1,
            distPts: immediateSupport.price - currentPrice,
            distLabel: formatDistPts(immediateSupport.price - currentPrice, isWdo),
        }
        : null;

    return {
        key: isWdo ? "WDO" : "WIN",
        title: isWdo ? "WDO · MINI-DÓLAR" : "WIN · MINI-ÍNDICE",
        shortName: isWdo ? "WDO" : "WIN",
        contract: report.contract || (isWdo ? "WDOFUT" : "WINFUT"),
        expiry: report.expiry || "",
        refDate: toBrDate(report.report_date || raw.ref_date),
        updatedAt: raw.updated_at || "",
        currentPrice,
        currentPriceLabel: formatAssetPrice(currentPrice, isWdo),
        gammaFlip,
        gammaFlipLabel: formatAssetPrice(gammaFlip, isWdo),
        maxGamma,
        maxGammaLabel: maxGamma ? formatAssetPrice(maxGamma, isWdo) : null,
        minGamma,
        minGammaLabel: minGamma ? formatAssetPrice(minGamma, isWdo) : null,
        isPositiveGamma,
        regimeLabel,
        regimeShort,
        regimeColor,
        bias: report.bias || (isPositiveGamma ? "CONSOLIDAÇÃO / DEFESA NAS WALLS" : "ALTA VOLATILIDADE / AMPLITUDE"),
        conclusion: report.conclusion || "",
        immediateResistance: resLevel,
        immediateSupport: supLevel,
        magnetWall: magnetLevel,
        levels,
        insertIndex,
        totalWallsCount: mainWalls.length,
    };
}

export function normalizeMorningBrief(raw) {
    const src = raw && raw.win && raw.wdo ? raw : DEFAULT_FALLBACK_BRIEF;
    const win = normalizeAssetLadder(src.win, false);
    const wdo = normalizeAssetLadder(src.wdo, true);
    const rawEvents = Array.isArray(src.calendar?.events) ? src.calendar.events : DEFAULT_FALLBACK_BRIEF.calendar.events;

    const events = rawEvents.slice(0, 4).map((e) => ({
        time: e.time || "--:--",
        currency: e.currency || "USD",
        title: e.title || "",
        impact: e.impact || "MEDIO",
        detail: e.detail || "",
    }));

    const dateBr = toBrDate(src.ref_date || win.refDate || wdo.refDate || DEFAULT_FALLBACK_BRIEF.ref_date);
    const globalAssets = Array.isArray(src.global_assets) ? src.global_assets.slice(0, 4) : [];

    return {
        isFallback: Boolean(src.is_fallback),
        generatedAt: src.generated_at || "",
        dateBr,
        win,
        wdo,
        calendar: {
            date: toBrDate(src.calendar?.date) || dateBr,
            events,
        },
        globalAssets,
    };
}

export function buildMorningCaption(brief, options = {}) {
    const b = brief || normalizeMorningBrief(DEFAULT_FALLBACK_BRIEF);
    const stamp = options.stampLabel || "Pré-pregão · 08:30 BRT";
    const ctaUrl = options.ctaUrl || "app.magicwalls.com.br";
    const handle = options.handle || "@magicwallsb3";

    const winStars = b.win.magnetWall ? `${b.win.magnetWall.stars || 3}/3` : "3/3";
    const wdoStars = b.wdo.magnetWall ? `${b.wdo.magnetWall.stars || 3}/3` : "3/3";

    const macroLines = b.calendar.events.length
        ? b.calendar.events.map((e) => `• ${e.time} [${e.currency}] ${e.title}`).join("\n")
        : "• Agenda macro sem eventos de alto impacto listados.";

    return [
        `Mapa de Liquidez GEX — ${b.dateBr} (${stamp})`,
        `Mapeamento pré-pregão de Walls e níveis institucionais para WIN e WDO. Salve este post e acompanhe o pregão.`,
        ``,
        `Mini-Índice (WIN)`,
        `• Regime: ${b.win.regimeLabel} (${b.win.regimeShort})`,
        `• FlipWall: ${b.win.gammaFlipLabel}`,
        `• Resistência imediata: ${b.win.immediateResistance?.priceLabel || "—"} | Suporte imediato: ${b.win.immediateSupport?.priceLabel || "—"}`,
        `• Ímã GEX (força ${winStars}): ${b.win.magnetWall?.priceLabel || "—"}`,
        ``,
        `Mini-Dólar (${b.wdo.contract || "WDO"})`,
        `• Regime: ${b.wdo.regimeLabel} (${b.wdo.regimeShort})`,
        `• FlipWall: ${b.wdo.gammaFlipLabel}`,
        `• Resistência imediata: ${b.wdo.immediateResistance?.priceLabel || "—"} | Suporte imediato: ${b.wdo.immediateSupport?.priceLabel || "—"}`,
        `• Ímã GEX (força ${wdoStars}): ${b.wdo.magnetWall?.priceLabel || "—"}`,
        ``,
        `Horários de atenção na agenda (BRT):`,
        macroLines,
        ``,
        `Acompanhe o terminal GEX + Fluxo Smart Money em tempo real: ${ctaUrl}`,
        `${handle}`,
        ``,
        `Ferramenta analítica quantitativa de caráter estritamente educacional. Não constitui recomendação de compra ou venda de ativos.`,
    ].join("\n");
}
