import React, { useState, useRef, useEffect, useMemo, memo } from "react";
import { API_BASE, FORCE_WALLS_FLOW, isManualChartMode } from "../apiBase";
import { authFetch, canAccessMediaStudio } from "../utils/saasAuth";
import InstagramCardModal from "./InstagramCardModal";
import MorningWallsVideoModal from "./MorningWallsVideoModal";

import { MT5_TOP6_SET, WALLS_FLOW_6_IDS, filterSignalsForHost } from "../utils/signalFilters";
const IconCamera = () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" />
        <circle cx="12" cy="13" r="3" />
    </svg>
);

const IconFilm = () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="2" y="4" width="20" height="16" rx="2" />
        <path d="m10 9 5 3-5 3V9z" />
    </svg>
);

const IconChevLeft = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polyline points="15 18 9 12 15 6" />
    </svg>
);

const IconChevRight = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polyline points="9 18 15 12 9 6" />
    </svg>
);

const IconCalendar = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="4" width="18" height="18" rx="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
);

const IconArrowRight = () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <line x1="5" y1="12" x2="19" y2="12" />
        <polyline points="12 5 19 12 12 19" />
    </svg>
);

const IconList = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <line x1="8" y1="6" x2="21" y2="6" />
        <line x1="8" y1="12" x2="21" y2="12" />
        <line x1="8" y1="18" x2="21" y2="18" />
        <line x1="3" y1="6" x2="3.01" y2="6" />
        <line x1="3" y1="12" x2="3.01" y2="12" />
        <line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
);

function fmtAbsorptionState(raw) {
    const s = String(raw || "").trim();
    if (!s || s === "NEUTRO") return "Neutro";
    const map = {
        ABSORCAO_VENDEDORA: "Absorção vendedora",
        ABSORCAO_COMPRADORA: "Absorção compradora",
        EXAUSTAO_COMPRADORA: "Exaustão compradora",
        EXAUSTAO_VENDEDORA: "Exaustão vendedora",
        INICIATIVA_COMPRADORA: "Iniciativa compradora",
        INICIATIVA_VENDEDORA: "Iniciativa vendedora",
    };
    if (map[s]) return map[s];
    const clean = s.replace(/_/g, " ").toLowerCase();
    return clean.charAt(0).toUpperCase() + clean.slice(1);
}

function stripUiEmoji(raw) {
    return String(raw || "")
        .replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}\uFE0F]/gu, "")
        .replace(/\s{2,}/g, " ")
        .trim();
}

// Posicionamento sem colisão para marcadores circulares numerados (alinhado ao InstagramCardModal)
function computeChartDivMarkers(divs, { toX, toY, series, plotTop, plotBot, plotLeft, plotRight, radius }) {
    const placed = [];
    const minDistX = radius * 2.55;
    const stepY = radius * 2.35;
    const topGroup = [];
    const botGroup = [];

    divs.forEach((dv) => {
        const b = series[dv.currIdx];
        if (!b) return;
        const isBull = dv.type === "BULL_DIV";
        const x = toX(dv.currIdx);
        const anchorPrice = isBull ? Number(b.low ?? dv.currPrice) : Number(b.high ?? dv.currPrice);
        const anchorY = Math.max(plotTop + 6, Math.min(plotBot - 6, toY(anchorPrice)));
        const clampedX = Math.max(plotLeft + radius + 4, Math.min(plotRight - radius - 4, x));
        const item = {
            dv,
            isBull,
            candleX: x,
            candleY: anchorY,
            badgeX: clampedX,
            badgeY: isBull ? anchorY + radius + 12 : anchorY - radius - 12,
        };
        if (isBull) botGroup.push(item);
        else topGroup.push(item);
    });

    topGroup.sort((a, b) => a.badgeX - b.badgeX);
    for (let i = 0; i < topGroup.length; i += 1) {
        const cur = topGroup[i];
        cur.badgeY = Math.max(plotTop + radius + 4, Math.min(plotBot - radius - 4, cur.badgeY));
        for (let pass = 0; pass < 5; pass += 1) {
            let collided = false;
            for (let j = 0; j < i; j += 1) {
                const prev = topGroup[j];
                if (Math.abs(cur.badgeX - prev.badgeX) < minDistX && Math.abs(cur.badgeY - prev.badgeY) < stepY * 0.94) {
                    const tryUp = prev.badgeY - stepY;
                    if (tryUp >= plotTop + radius + 4) cur.badgeY = tryUp;
                    else cur.badgeY = Math.min(plotBot - radius - 4, prev.badgeY + stepY);
                    collided = true;
                }
            }
            if (!collided) break;
        }
        placed.push(cur);
    }

    botGroup.sort((a, b) => a.badgeX - b.badgeX);
    for (let i = 0; i < botGroup.length; i += 1) {
        const cur = botGroup[i];
        cur.badgeY = Math.max(plotTop + radius + 4, Math.min(plotBot - radius - 4, cur.badgeY));
        for (let pass = 0; pass < 5; pass += 1) {
            let collided = false;
            for (let j = 0; j < i; j += 1) {
                const prev = botGroup[j];
                if (Math.abs(cur.badgeX - prev.badgeX) < minDistX && Math.abs(cur.badgeY - prev.badgeY) < stepY * 0.94) {
                    const tryDown = prev.badgeY + stepY;
                    if (tryDown <= plotBot - radius - 4) cur.badgeY = tryDown;
                    else cur.badgeY = Math.max(plotTop + radius + 4, prev.badgeY - stepY);
                    collided = true;
                }
            }
            if (!collided) break;
        }
        placed.push(cur);
    }

    placed.sort((a, b) => (a.dv.num || 0) - (b.dv.num || 0));
    return placed;
}

function fmtNum(v, decimals = 0, showSign = false) {
    if (v === undefined || v === null || Number.isNaN(Number(v))) return "—";
    let n = Number(v);
    if (Object.is(n, -0) || Math.abs(n) < 0.5 * Math.pow(10, -decimals)) n = 0;
    const sign = showSign && n > 0 ? "+" : "";
    return sign + n.toLocaleString("pt-BR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function scoreColor(score) {
    const s = Number(score || 0);
    if (s >= 20) return "#4cc38a";
    if (s <= -20) return "#e5484d";
    return "#d4a259";
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

function isWallsFlowLocalhost() {
    if (FORCE_WALLS_FLOW || isManualChartMode()) return true;
    if (typeof window === "undefined") return false;
    const port = String(window.location.port || "");
    const params = new URLSearchParams(window.location.search || "");
    if (params.get("mode") === "walls_flow" || params.get("mode") === "manual") return true;
    if (params.get("mode") === "mt5") return false;
    return port === "5176" || port === "5178";
}

const _M1_CHART_CACHE = {};
const _M1_CHART_INFLIGHT = {};
function fetchM1ChartByDate(dateKey, force = false) {
    const dk = String(dateKey || "").trim();
    const cacheKey = dk || "__LATEST__";
    const cached = _M1_CHART_CACHE[cacheKey];
    const hasValidBars = cached && (
        (Array.isArray(cached.WIN?.m1_series) && cached.WIN.m1_series.length > 0) ||
        (Array.isArray(cached.WDO?.m1_series) && cached.WDO.m1_series.length > 0)
    );
    if (!force && hasValidBars) {
        return Promise.resolve(cached);
    }
    if (!force && _M1_CHART_INFLIGHT[cacheKey]) {
        return _M1_CHART_INFLIGHT[cacheKey];
    }
    const url = dk
        ? `${API_BASE}/api/compass/m1_series?date_str=${encodeURIComponent(dk)}`
        : `${API_BASE}/api/compass/m1_series`;
    const p = authFetch(url)
        .then((r) => r.json())
        .then((data) => {
            delete _M1_CHART_INFLIGHT[cacheKey];
            const okBars = data && data.ok && (
                (Array.isArray(data.WIN?.m1_series) && data.WIN.m1_series.length > 0) ||
                (Array.isArray(data.WDO?.m1_series) && data.WDO.m1_series.length > 0)
            );
            if (okBars) {
                data._fetchedAt = Date.now();
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
    volumeProfile = null,
    vwap,
    selectedSigId,
    onSelectSignal,
    showSignalsMarkers = true,
    wideMode = false,
    capitalDrawerInfo = null,
    sessionDate = "",
    payloadDate = "",
    precomputedDivs = null,
    compassData = null,
    embeddedHeader = null,
    isSideBySide = false,
    contractName = "",
}) {
    const svgRef = useRef(null);
    const [chartTf, setChartTf] = useState("M5"); // "M5" | "M1"
    const [m1AssetData, setM1AssetData] = useState(null);
    const [m1Loading, setM1Loading] = useState(false);
    const [hoverPos, setHoverPos] = useState(null); // { idx, relX, relY }
    const [hoveredSigId, setHoveredSigId] = useState(null);
    const [hoveredDivId, setHoveredDivId] = useState(null);
    const [selectedDivId, setSelectedDivId] = useState(null);
    const [rightGapPx, setRightGapPx] = useState(28);
    const [viewMode, setViewMode] = useState("HOJE"); // Padrão: Dia Todo no M5; no M1 abre janela legível de 2h
    const [visibleCount, setVisibleCount] = useState(120);
    const [m1WinSize, setM1WinSize] = useState(120); // 60 (1h) | 120 (2h) | 180 (3h)
    const [panOffsetRight, setPanOffsetRight] = useState(0); // quantas barras deslocado do fim
    const [yZoomFactor, setYZoomFactor] = useState(1.0); // >1 abre mais o eixo Y para ver mais Walls do Pine
    const isWallsHost = isWallsFlowLocalhost();
    const [showMidleWalls, setShowMidleWalls] = useState(true);
    const [showVolumeProfile, setShowVolumeProfile] = useState(() => {
        try { return window.localStorage.getItem("vol_profile_5176") !== "0"; } catch (e) { return true; }
    });
    const toggleVolumeProfile = () => {
        setShowVolumeProfile(v => {
            try { window.localStorage.setItem("vol_profile_5176", v ? "0" : "1"); } catch (e) { /* armazenamento indisponível */ }
            return !v;
        });
    };
    const [showAvwap, setShowAvwap] = useState(() => {
        try { return window.localStorage.getItem("avwap_5176") !== "0"; } catch (e) { return true; }
    });
    const toggleAvwap = () => {
        setShowAvwap(v => {
            try { window.localStorage.setItem("avwap_5176", v ? "0" : "1"); } catch (e) { /* armazenamento indisponível */ }
            return !v;
        });
    };
    const [showNweLine, setShowNweLine] = useState(() => {
        // 5176: Canal Gauss (NWE100) ligado por padrão nos dois ativos (lembra a escolha do usuário)
        if (!isWallsFlowLocalhost()) return false;
        try { return window.localStorage.getItem("canal_gauss_5176") !== "0"; } catch (e) { return true; }
    });
    // 5176 (12/11/2026, versão final): desenha só a NWE100 (L=100, bw 8, mult 3) = "Canal Gauss"
    const nweKind = "100";
    const toggleCanalGauss = () => {
        setShowNweLine(v => {
            try { window.localStorage.setItem("canal_gauss_5176", v ? "0" : "1"); } catch (e) { /* armazenamento indisponível */ }
            return !v;
        });
    };
    const [showDivLines, setShowDivLines] = useState(() => {
        try { return window.localStorage.getItem("div_lines_5176") === "1"; } catch (e) { return false; }
    });
    const toggleDivLines = () => {
        setShowDivLines(v => {
            try { window.localStorage.setItem("div_lines_5176", v ? "0" : "1"); } catch (e) { /* armazenamento indisponível */ }
            return !v;
        });
    };
    useEffect(() => {
        setHoveredDivId(null);
        setSelectedDivId(null);
        setPanOffsetRight(0);
    }, [sessionDate, symKey]);
    const [showWindowFlips, setShowWindowFlips] = useState(false); // Linhas verticais de virada de fluxo (toggle)
    const [showWallBattleLabels, setShowWallBattleLabels] = useState(false); // Escrita nos candles opcional (desativada na 5176)
    const [showSwingDivLines, setShowSwingDivLines] = useState(true); // Linhas de Divergência Topo/Fundo (F1->F2 / T1->T2) sincronizadas Preço x Fluxo
    // Divergências no gráfico (12/11/2026, versão final): só o motor oficial V3.2 (core/div_engines_view.py), o mesmo
    // que gera os trades do Sniper e do Especialista. "NENHUMA" = gráfico limpo (botão liga/desliga).
    const [divEngine, setDivEngine] = useState(() => {
        try {
            return window.localStorage.getItem("div_v32_5176") === "0" ? "NENHUMA" : "v3.2";
        } catch (e) {
            return "v3.2";
        }
    });
    const [engineDivs, setEngineDivs] = useState({ key: "", list: [], status: "idle" });
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
    const [showInstaModal, setShowInstaModal] = useState(false);
    const [showMorningVideoModal, setShowMorningVideoModal] = useState(false);
    const [canUseMediaStudio, setCanUseMediaStudio] = useState(() => canAccessMediaStudio());
    useEffect(() => {
        const sync = (ev) => setCanUseMediaStudio(canAccessMediaStudio(ev?.detail?.user));
        window.addEventListener("mw-saas-auth-updated", sync);
        return () => window.removeEventListener("mw-saas-auth-updated", sync);
    }, []);
    const tvMetricsRef = useRef(null);
    const chartBoxRef = useRef(null);
    const [viewport, setViewport] = useState(() => {
        if (typeof window === "undefined") return { boxW: 1240, winH: 800, narrow: false };
        const w = Number(window.innerWidth) || 1240;
        return { boxW: w, winH: Number(window.innerHeight) || 800, narrow: w < 560 };
    });
    useEffect(() => {
        const measure = () => {
            const boxW = (chartBoxRef.current && chartBoxRef.current.clientWidth) || window.innerWidth || 1240;
            const winH = window.innerHeight || 800;
            setViewport({ boxW, winH, narrow: boxW < 560 });
        };
        measure();
        const raf = (typeof requestAnimationFrame !== "undefined") ? requestAnimationFrame(measure) : 0;
        const ro = (typeof ResizeObserver !== "undefined") ? new ResizeObserver(measure) : null;
        if (ro && chartBoxRef.current) ro.observe(chartBoxRef.current);
        window.addEventListener("resize", measure);
        return () => {
            if (raf && typeof cancelAnimationFrame !== "undefined") cancelAnimationFrame(raf);
            if (ro) ro.disconnect();
            window.removeEventListener("resize", measure);
        };
    }, [m5RawSeries?.length, isSideBySide]);


    // Pré-carrega a série M1 em background assim que a data da sessão estiver disponível (troca M5 <-> M1 em 0ms)
    useEffect(() => {
        let cancelled = false;
        const dKey = String(sessionDate || "").trim();
        const cached = _M1_CHART_CACHE[dKey || "__LATEST__"];
        const cachedHasBars = Array.isArray(cached?.[symKey]?.m1_series) && cached[symKey].m1_series.length > 0;
        if (cachedHasBars) {
            setM1AssetData(cached[symKey]);
        } else if (chartTf === "M1") {
            setM1Loading(true);
        }
        const loadM1 = (forceRefresh = false) => {
            fetchM1ChartByDate(dKey, forceRefresh)
                .then((data) => {
                    if (cancelled) return;
                    if (data && data[symKey] && Array.isArray(data[symKey].m1_series) && data[symKey].m1_series.length > 0) {
                        setM1AssetData(data[symKey]);
                    }
                    setM1Loading(false);
                })
                .catch(() => {
                    if (!cancelled) setM1Loading(false);
                });
        };
        loadM1(!cachedHasBars);
        let pollTimer = null;
        if (chartTf === "M1") {
            pollTimer = setInterval(() => {
                if (typeof document === "undefined" || !document.hidden) loadM1(true);
            }, 5000);
        }
        return () => {
            cancelled = true;
            if (pollTimer) clearInterval(pollTimer);
        };
    }, [sessionDate, symKey, chartTf]);

    const useM1Active = chartTf === "M1" && Array.isArray(m1AssetData?.m1_series) && m1AssetData.m1_series.length > 0;
    // Sincroniza o fluxo do M1 com a série oficial M5 do Profit para que o Fluxo Smart Money / CVD / Janela
    // seja 100% independente do timeframe (mesma curva, escala e polaridade em M5 e M1).
    const rawSeries = (() => {
        if (!useM1Active) return m5RawSeries;
        const m1List = m1AssetData.m1_series || [];
        const m5Today = (m5RawSeries || []).filter(pt => pt && !pt.is_prev_day && pt.time);
        if (m5Today.length === 0) return m1List;
        const m5ByBucket = {};
        m5Today.forEach((pt, idx) => {
            const k = String(pt.time).slice(0, 5);
            m5ByBucket[k] = { curr: pt, prev: idx > 0 ? m5Today[idx - 1] : null };
        });
        const lastM5Pair = { curr: m5Today[m5Today.length - 1], prev: m5Today.length > 1 ? m5Today[m5Today.length - 2] : null };
        const lerp = (a, b, f) => Number(a || 0) + (Number(b || 0) - Number(a || 0)) * f;
        return m1List.map((b) => {
            if (!b || b.is_prev_day || !b.time) return b;
            const [hhStr, mmStr] = String(b.time).slice(0, 5).split(":");
            const hh = parseInt(hhStr, 10);
            const mm = parseInt(mmStr, 10);
            if (Number.isNaN(hh) || Number.isNaN(mm)) return b;
            const bucketMin = Math.floor(mm / 5) * 5;
            const bucketKey = `${String(hh).padStart(2, "0")}:${String(bucketMin).padStart(2, "0")}`;
            const pair = m5ByBucket[bucketKey] || lastM5Pair;
            const curr = pair.curr;
            const prev = pair.prev;
            const frac = ((mm % 5) + 1) / 5.0;
            const prevWave = prev ? Number(prev.smart_swing_wave || 0) : 0;
            const currWave = Number(curr.smart_swing_wave || 0);
            const prevCvdI = prev ? Number(prev.cvd_inst_aggr ?? prev.cvd_inst ?? 0) : 0;
            const currCvdI = Number(curr.cvd_inst_aggr ?? curr.cvd_inst ?? 0);
            const prevCvdP = prev ? Number(prev.cvd_inst_pass ?? 0) : 0;
            const currCvdP = Number(curr.cvd_inst_pass ?? 0);
            const prevCvdR = prev ? Number(prev.cvd_retail ?? 0) : 0;
            const currCvdR = Number(curr.cvd_retail ?? 0);
            const prevCvdH = prev ? Number(prev.cvd_hft ?? 0) : 0;
            const currCvdH = Number(curr.cvd_hft ?? 0);
            const prevCvdRlp = prev ? Number(prev.cvd_rlp_delta ?? 0) : 0;
            const currCvdRlp = Number(curr.cvd_rlp_delta ?? 0);
            return {
                ...b,
                smart_swing_wave: Math.round(lerp(prevWave, currWave, frac)),
                cvd_inst: Math.round(lerp(prevCvdI, currCvdI, frac)),
                cvd_inst_aggr: Math.round(lerp(prevCvdI, currCvdI, frac)),
                cvd_inst_pass: Math.round(lerp(prevCvdP, currCvdP, frac)),
                cvd_retail: Math.round(lerp(prevCvdR, currCvdR, frac)),
                cvd_hft: Math.round(lerp(prevCvdH, currCvdH, frac)),
                cvd_rlp_delta: Math.round(lerp(prevCvdRlp, currCvdRlp, frac)),
                inst_aggr_delta: Math.round(Number(curr.inst_aggr_delta ?? curr.inst_delta_bar ?? 0) / 5.0),
                inst_delta_bar: Math.round(Number(curr.inst_delta_bar ?? curr.inst_aggr_delta ?? 0) / 5.0),
                inst_pass_delta: Math.round(Number(curr.inst_pass_delta ?? 0) / 5.0),
                ret_delta_bar: Math.round(Number(curr.ret_delta_bar ?? 0) / 5.0),
                window_dir: curr.window_dir ?? b.window_dir,
                flow_hist: curr.flow_hist ?? b.flow_hist,
            };
        });
    })();
    const flowWindows = useM1Active ? (m1AssetData.flow_windows || []) : m5FlowWindows;

    // ── Divergências dos motores V2.1 / V3.1 / V3.2 sempre sobre a série oficial M5 da sessão (mesmas divergências em M5 e M1) ──
    const engineBars = (m5RawSeries || []).filter(pt => pt && !pt.is_prev_day && pt.time);
    const lastEngineBar = engineBars[engineBars.length - 1] || {};
    // Trades do dia: o backend devolve também a divergência que liberou cada um (mesmo se depois foi estendida)
    const engineTrades = filterSignalsForHost(signalsLog, isWallsHost)
        .filter(s => s && !s.is_prev_day && s.time)
        .map(s => ({ strategy_id: s.strategy_id, time: String(s.time).slice(0, 5), direction: s.direction }));
    const engineTradesKey = engineTrades.map(t => `${t.strategy_id}@${t.time}@${t.direction}`).join(",");
    const engineScopeKey = `${divEngine}|${symKey}|${sessionDate}`;
    const payloadDateIso = String(payloadDate || sessionDate || "").slice(0, 10);
    const targetDateIso = String(sessionDate || payloadDate || "").slice(0, 10);
    const isPrecomputedSameDate = !payloadDateIso || !targetDateIso || payloadDateIso === targetDateIso;
    const precomputedV32 = (
        divEngine === "v3.2" &&
        isPrecomputedSameDate &&
        engineBars.length >= 5 &&
        Array.isArray(precomputedDivs)
    ) ? precomputedDivs : null;
    const engineReqKey = (isWallsHost && ["v2.1", "v2.2", "v3.1", "v3.2"].includes(divEngine) && engineBars.length >= 5)
        ? `${engineScopeKey}|${engineBars.length}|${lastEngineBar.time}|${lastEngineBar.high}|${lastEngineBar.low}|${(allWalls || []).length}|${engineTradesKey}`
        : "";
    useEffect(() => {
        if (!engineReqKey) return undefined;
        if (precomputedV32 !== null) {
            setEngineDivs({
                key: engineReqKey,
                scopeKey: engineScopeKey,
                list: precomputedV32,
                status: "ok",
            });
            return undefined;
        }
        let cancelled = false;
        setEngineDivs(prev => ({ ...prev, status: "loading" }));
        const postDivs = () => authFetch(`${API_BASE}/api/compass/divergencias_motor`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                asset: symKey === "WDO" ? "WDO" : "WIN",
                engine: divEngine,
                bars: engineBars.map(pt => ({
                    time: String(pt.time).slice(0, 5), open: Number(pt.open), high: Number(pt.high),
                    low: Number(pt.low), close: Number(pt.close), wave: Number(pt.smart_swing_wave || 0),
                })),
                walls: (allWalls || []).map(w => ({ type: w.type, price: Number(w.price) })),
                trades: engineTrades,
            }),
        }).then(r => r.json());
        const applyDivs = (d) => {
            if (cancelled) return;
            const apiList = (d && d.ok && Array.isArray(d.divergences)) ? d.divergences : [];
            const fallbackList = (apiList.length === 0 && precomputedV32 && precomputedV32.length > 0) ? precomputedV32 : apiList;
            setEngineDivs({
                key: engineReqKey,
                scopeKey: engineScopeKey,
                list: fallbackList,
                status: (d && d.ok) || fallbackList.length > 0 ? "ok" : "erro",
            });
        };
        postDivs().then(applyDivs).catch(() => {
            if (cancelled) return;
            postDivs().then(applyDivs).catch(() => {
                if (cancelled) return;
                if (precomputedV32 && precomputedV32.length > 0) {
                    setEngineDivs({
                        key: engineReqKey,
                        scopeKey: engineScopeKey,
                        list: precomputedV32,
                        status: "ok",
                    });
                    return;
                }
                // Falha de rede/túnel: não apaga as linhas já desenhadas nem trava o botão em "erro"
                setEngineDivs(prev => {
                    if (prev.scopeKey === engineScopeKey && Array.isArray(prev.list) && prev.list.length) {
                        return { ...prev, status: "ok" };
                    }
                    return { ...prev, status: "erro" };
                });
            });
        });
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [engineReqKey, precomputedV32]);
    const chooseDivEngine = (v) => {
        setDivEngine(v);
        try { window.localStorage.setItem("div_v32_5176", v === "NENHUMA" ? "0" : "1"); } catch (e) { /* armazenamento indisponível */ }
    };

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

    // Canal Gauss = NWE100 na 5176; se o campo não vier no payload, cai na NWE30
    const nweKey = isWallsHost ? `nwe${nweKind}` : null;
    const nweLbl = isWallsHost ? "Canal Gauss" : "NWE";
    const getNweLine = (pt) => Number(isWallsHost ? ((nweKey ? pt?.[`${nweKey}_line`] : undefined) ?? pt?.nwe30_line ?? pt?.nwe_line ?? 0) : (pt?.nwe_line ?? 0));
    const getNweUpper = (pt) => Number(isWallsHost ? ((nweKey ? pt?.[`${nweKey}_upper`] : undefined) ?? pt?.nwe30_upper ?? pt?.nwe_upper ?? 0) : (pt?.nwe_upper ?? 0));
    const getNweLower = (pt) => Number(isWallsHost ? ((nweKey ? pt?.[`${nweKey}_lower`] : undefined) ?? pt?.nwe30_lower ?? pt?.nwe_lower ?? 0) : (pt?.nwe_lower ?? 0));
    const getNweIsUp = (pt) => (isWallsHost ? ((nweKey ? pt?.[`${nweKey}_is_up`] : undefined) ?? pt?.nwe30_is_up ?? pt?.nwe_is_up) : pt?.nwe_is_up);

    const dec = symKey === "WDO" ? 1 : 0;

    if (!rawSeries || rawSeries.length < 1) {
        return (
            <div className="mw-card" style={{
                height: "min(540px, 62vh)",
                minHeight: 260,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--mw-text-3)",
                fontSize: 13,
                padding: "16px 20px",
                textAlign: "center",
            }}>
                Aguardando barras M5 da sessão para exibir o gráfico.
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
    const effCount = useM1Active
        ? (viewMode === "CUSTOM"
            ? Math.max(20, Math.min(totalBase, visibleCount))
            : Math.max(20, Math.min(totalBase, m1WinSize)))
        : ((viewMode === "TUDO" || viewMode === "HOJE")
            ? totalBase
            : Math.max(14, Math.min(totalBase, visibleCount)));
    const maxPan = Math.max(0, totalBase - effCount);
    const clampedPan = Math.max(0, Math.min(maxPan, panOffsetRight));
    const endSlice = totalBase - clampedPan;
    const startSlice = Math.max(0, endSlice - effCount);
    const series = baseSeries.slice(startSlice, endSlice);

    const isNarrow = !isSideBySide && viewport.narrow;
    const width = Math.max(320, Math.round(viewport.boxW || (wideMode ? 1240 : 900)));
    const height = isSideBySide
        ? 460
        : isNarrow
            ? 390
            : (isWallsHost ? 510 : 544);
    const padL = isNarrow ? 8 : 12;
    const padR = isNarrow ? 74 : (isSideBySide ? 78 : 94);

    // Layout Dinâmico estilo TradingView em 2 Painéis Verticais Redimensionáveis:
    const bottomAxisH = 26;
    const splitterGap = 12;
    const clampedFlowH = Math.max(isNarrow ? 104 : 86, Math.min(height - (isNarrow ? 210 : 210), flowPaneH));
    const p1Top = 24;
    const p1H = Math.max(isNarrow ? 190 : 180, height - p1Top - bottomAxisH - splitterGap - clampedFlowH);
    const p1Bot = p1Top + p1H;
    const p2Top = 0, p2H = 0, p2Bot = 0; // Removido (Fluxo CVD)
    const pGexTop = 0, pGexH = 0, pGexBot = 0; // Removido (Hedge Makers GEX)
    const p3Top = p1Bot + splitterGap;
    const p3H = clampedFlowH;
    const p3Bot = p3Top + p3H;
    const splitterMidY = (p1Bot + p3Top) / 2;
    const plotW = width - padL - padR;

    const innerPadL = isNarrow ? 10 : 14;
    const effRightGap = isNarrow ? Math.min(rightGapPx, 16) : rightGapPx;
    const usableW = Math.max(isNarrow ? 140 : 180, plotW - innerPadL - effRightGap);
    const n = series.length;
    const totalSlots = Math.max(n - 1, 14);
    const stepX = usableW / Math.max(1, totalSlots);
    const candleW = Math.max(useM1Active ? 2.2 : 3.0, Math.min(11.5, stepX * 0.64));
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
    const halfSpan = Math.max(symKey === "WDO" ? 1.8 : 45, ((maxP - minP) / 2) * (isWallsHost ? 1.24 : 1.15) * yZoomFactor);
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
        let divLabel = "Fluxo alinhado";
        let divColor = "#848da2";
        let divShort = "";

        if (fomoBuyTrap) {
            divType = "TRAP_FOMO_BUY";
            divLabel = "Armadilha FOMO compra (varejo comprando topo vs Inst absorvendo na venda)";
            divColor = "#d4a259";
            divShort = "FOMO";
        } else if (fomoSellTrap) {
            divType = "TRAP_FOMO_SELL";
            divLabel = "Armadilha venda varejo (varejo vendendo fundo vs Inst absorvendo na compra)";
            divColor = "#4cc38a";
            divShort = "TRAP";
        } else if (bullDiv) {
            divType = "BULL_DIV";
            divLabel = "Divergência compra (preço/varejo caindo vs absorção não-varejo compradora)";
            divColor = "#4cc38a";
            divShort = "DIV▲";
        } else if (bearDiv) {
            divType = "BEAR_DIV";
            divLabel = "Divergência venda (preço/varejo subindo vs distribuição vendedora)";
            divColor = "#e5484d";
            divShort = "DIV▼";
        } else if (sweepBuy) {
            divType = "SWEEP_BUY";
            divLabel = "Sweep institucional compra (tomada agressiva não-varejo + ticket alto)";
            divColor = "#38bdf8";
            divShort = "SWP▲";
        } else if (sweepSell) {
            divType = "SWEEP_SELL";
            divLabel = "Sweep institucional venda (batida agressiva não-varejo + ticket alto)";
            divColor = "#e5484d";
            divShort = "SWP▼";
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
                    sb.divColor = "#38bdf8";
                    sb.divLabel = `Meta diária atingida (+R$ ${fmtNum(dailyRealizedSum, 0)}) · novas entradas bloqueadas`;
                } else if (!isInSniperHours(tS)) {
                    sb.divType = null;
                    sb.divColor = "#848da2";
                    sb.divLabel = `Fora do horário operacional (${isWinSym ? "09:05–16:45 s/ 12h" : "09:00–17:00 s/ 11h NY"})`;
                } else if (sb.divType === "BULL_DIV" || sb.divType === "BEAR_DIV") {
                    // Evita exibir divergência de 1 barra no HUD se não for divergência F1->F2 / T1->T2 confirmada
                    sb.divType = null;
                    sb.divColor = "#848da2";
                    sb.divLabel = "Monitorando fluxo na Wall";
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
                                sb.divColor = "#4cc38a";
                                sb.divLabel = `Div. compra de fundo (${bestP1.time} → ${series[i]?.time}): preço ${fmtNum(bestP1.price, dec)} → ${fmtNum(l2, dec)} | fluxo subiu (${driverTxt})`;
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
                                sb.divColor = "#e5484d";
                                sb.divLabel = `Div. venda de topo (${bestT1.time} → ${series[i]?.time}): preço ${fmtNum(bestT1.price, dec)} → ${fmtNum(h2, dec)} | fluxo caiu (${driverTxt})`;
                            }
                        }
                    }
                }
            }
        }
    }

    // ── Camada escolhida no seletor "Sinais": V3.2 (numeração cronológica 1..N alinhada ao Card IG) ou Nenhuma ──
    let totalDayDivCount = swingDivergences.length;
    if (isWallsFlowLocalhost() && divEngine !== "ATUAL") {
        subPanelBars.forEach((sb) => {
            if (sb.swingDiv) {
                sb.swingDiv = undefined;
                if (sb.divType === "BULL_DIV" || sb.divType === "BEAR_DIV") {
                    sb.divType = null;
                    sb.divColor = "#7f96a8";
                    sb.divLabel = "Monitorando fluxo na Wall";
                }
            }
        });
        swingDivergences.length = 0;
        totalDayDivCount = 0;
        const effectiveEngineList =
            (engineDivs.scopeKey === engineScopeKey && Array.isArray(engineDivs.list) && engineDivs.list.length > 0)
                ? engineDivs.list
                : (precomputedV32 || []);
        if (["v2.1", "v2.2", "v3.1", "v3.2"].includes(divEngine) && (effectiveEngineList.length > 0 || engineDivs.scopeKey === engineScopeKey)) {
            const idxByTime = {};
            const parseMin = (t) => {
                const [hh, mm] = String(t || "").slice(0, 5).split(":");
                const h = parseInt(hh, 10);
                const m = parseInt(mm, 10);
                return (Number.isNaN(h) || Number.isNaN(m)) ? -1 : (h * 60 + m);
            };
            series.forEach((pt, ix) => { if (pt && !pt.is_prev_day && pt.time) idxByTime[String(pt.time).slice(0, 5)] = ix; });
            const firstVisMin = series.length > 0 ? parseMin(series[0]?.time) : -1;
            const findBarIdxForM5Time = (tStr, dir) => {
                const k = String(tStr || "").slice(0, 5);
                if (!useM1Active) return idxByTime[k];
                const m0 = parseMin(k);
                if (m0 < 0) return idxByTime[k];
                let bestIdx = idxByTime[k];
                let bestExtreme = dir === 1 ? Infinity : -Infinity;
                series.forEach((pt, ix) => {
                    if (!pt || pt.is_prev_day || !pt.time) return;
                    const m = parseMin(pt.time);
                    if (m >= m0 && m <= m0 + 4) {
                        const px = dir === 1 ? Number(pt.low) : Number(pt.high);
                        if ((dir === 1 && px <= bestExtreme) || (dir !== 1 && px >= bestExtreme)) {
                            bestExtreme = px;
                            bestIdx = ix;
                        }
                    }
                });
                return bestIdx;
            };
            // Numeração permanente cronológica no dia inteiro (espelha 1-para-1 a ordem do Card IG)
            const orderedDayDivs = [...effectiveEngineList]
                .map((d, rawIdx) => ({
                    ...d,
                    _rawIdx: rawIdx,
                    _confMin: parseMin(d.conf_time || d.f2_time),
                    _f2Min: parseMin(d.f2_time),
                }))
                .sort((a, b) => (a._confMin - b._confMin) || (a._f2Min - b._f2Min) || (a._rawIdx - b._rawIdx));
            totalDayDivCount = orderedDayDivs.length;

            orderedDayDivs.forEach((d, orderedIdx) => {
                const ci = findBarIdxForM5Time(d.f2_time, d.dir);
                if (ci === undefined) return;
                let pi = findBarIdxForM5Time(d.f1_time, d.dir);
                let prevOffLeft = false;
                if (pi === undefined) {
                    const f1m = parseMin(d.f1_time);
                    if (firstVisMin >= 0 && f1m >= 0 && f1m < firstVisMin) {
                        pi = 0;
                        prevOffLeft = true;
                    } else {
                        pi = ci;
                    }
                }
                const trigTxt = d.trigger_time ? `gatilho Opção C ${d.trigger_time} (${d.trigger_kind})` : "sem gatilho Opção C";
                const tradeTxt = showSignalsMarkers && Array.isArray(d.trades) && d.trades.length ? ` · liberou ${d.trades.join(", ")}` : "";
                const anchorUpper = String(d.anchor || "").toUpperCase();
                const hasWallAnchor = anchorUpper.includes("WALL");
                const hasExtremoAnchor = anchorUpper.includes("EXTREMO");
                const anchorCode = (hasWallAnchor && hasExtremoAnchor) ? "XW" : hasWallAnchor ? "W" : hasExtremoAnchor ? "X" : "D";
                swingDivergences.push({
                    num: orderedIdx + 1,
                    divId: `${d.dir > 0 ? "B" : "S"}_${d.f2_time}_${orderedIdx}`,
                    anchorCode,
                    prevOffLeft,
                    type: d.dir === 1 ? "BULL_DIV" : "BEAR_DIV",
                    prevIdx: pi, prevTime: d.f1_time, prevPrice: Number(d.f1_px), prevWave: Number(d.f1_wave),
                    currIdx: ci, currTime: d.f2_time, currPrice: Number(d.f2_px), currWave: Number(d.f2_wave),
                    confTime: d.conf_time,
                    triggerTime: d.trigger_time,
                    triggerKind: d.trigger_kind,
                    nearWall: hasWallAnchor,
                    isPendingTrigger: false,
                    engine: divEngine,
                    anchor: d.anchor,
                    driver: `${divEngine.toUpperCase()} · âncora ${d.anchor} · confirmada ${d.conf_time} · ${trigTxt} · onda divergiu ${fmtNum(d.wave_div, 0)} (limiar ${fmtNum(d.wave_thr, 0)})${tradeTxt}`,
                    fromTrade: tradeTxt !== "",
                });
            });
        }
    } else {
        swingDivergences.forEach((dv, idx) => {
            if (!dv.num) dv.num = idx + 1;
            if (!dv.divId) dv.divId = `${dv.type === "BULL_DIV" ? "B" : "S"}_${dv.currTime}_${idx}`;
            if (!dv.anchorCode) dv.anchorCode = dv.nearWall ? "W" : "D";
        });
        totalDayDivCount = swingDivergences.length;
    }

    // ── AVWAP Automática nas Divergências de Extremo do Dia (BULL_DIV na mínima / BEAR_DIV na máxima) ──
    const avwapCurves = (() => {
        if (!showAvwap) return [];
        const todayBars = indexedSeries.filter((pt) => pt && !pt.is_prev_day && pt.time);
        if (todayBars.length < 2) return [];

        const parseMinAvwap = (t) => {
            const [hh, mm] = String(t || "").slice(0, 5).split(":");
            const h = parseInt(hh, 10);
            const m = parseInt(mm, 10);
            return (Number.isNaN(h) || Number.isNaN(m)) ? -1 : (h * 60 + m);
        };
        const getBarVol = (b) => {
            const v = Number(b?.buy_vol || 0) + Number(b?.sell_vol || 0);
            if (v > 0) return v;
            const fb = Number(b?.total_vol ?? b?.volume ?? b?.real_volume ?? 0);
            return fb > 0 ? fb : 1;
        };

        const runMinLow = new Array(todayBars.length);
        const runMaxHigh = new Array(todayBars.length);
        const todayIdxByTime = {};
        let curMinL = Infinity;
        let curMaxH = -Infinity;
        for (let i = 0; i < todayBars.length; i += 1) {
            const bi = todayBars[i];
            const lo = Number(bi.low ?? bi.close);
            const hi = Number(bi.high ?? bi.close);
            if (lo < curMinL) curMinL = lo;
            if (hi > curMaxH) curMaxH = hi;
            runMinLow[i] = curMinL;
            runMaxHigh[i] = curMaxH;
            todayIdxByTime[String(bi.time).slice(0, 5)] = i;
        }
        const lastTodayMin = parseMinAvwap(todayBars[todayBars.length - 1]?.time);

        const findTodayIdx = (tStr, dir) => {
            const k = String(tStr || "").slice(0, 5);
            if (!useM1Active) return todayIdxByTime[k];
            const m0 = parseMinAvwap(k);
            if (m0 < 0) return todayIdxByTime[k];
            let bestIdx = todayIdxByTime[k];
            let bestExt = dir === 1 ? Infinity : -Infinity;
            for (let i = 0; i < todayBars.length; i += 1) {
                const m = parseMinAvwap(todayBars[i].time);
                if (m >= m0 && m <= m0 + 4) {
                    const px = dir === 1
                        ? Number(todayBars[i].low ?? todayBars[i].close)
                        : Number(todayBars[i].high ?? todayBars[i].close);
                    if ((dir === 1 && px <= bestExt) || (dir !== 1 && px >= bestExt)) {
                        bestExt = px;
                        bestIdx = i;
                    }
                }
            }
            return bestIdx;
        };

        const engineList =
            (engineDivs.scopeKey === engineScopeKey && Array.isArray(engineDivs.list) && engineDivs.list.length > 0)
                ? engineDivs.list
                : (precomputedV32 && precomputedV32.length > 0)
                    ? precomputedV32
                    : (isPrecomputedSameDate && Array.isArray(precomputedDivs) && precomputedDivs.length > 0)
                        ? precomputedDivs
                        : null;

        let candidates = [];
        if (engineList && engineList.length > 0) {
            candidates = [...engineList]
                .map((d, rawIdx) => ({
                    ...d,
                    _rawIdx: rawIdx,
                    _confMin: parseMinAvwap(d.conf_time || d.f2_time),
                    _f2Min: parseMinAvwap(d.f2_time),
                }))
                .sort((a, b) => (a._confMin - b._confMin) || (a._f2Min - b._f2Min) || (a._rawIdx - b._rawIdx))
                .map((d, idx) => ({
                    num: idx + 1,
                    dir: Number(d.dir) >= 0 ? 1 : -1,
                    f2Time: String(d.f2_time || "").slice(0, 5),
                    confTime: String(d.conf_time || d.f2_time || "").slice(0, 5),
                    anchor: d.anchor || "",
                    dayExtreme: Boolean(d.day_extreme),
                }));
        } else {
            candidates = swingDivergences.map((dv, idx) => ({
                num: dv.num || idx + 1,
                dir: dv.type === "BULL_DIV" ? 1 : -1,
                f2Time: String(dv.currTime || "").slice(0, 5),
                confTime: String(dv.confTime || dv.currTime || "").slice(0, 5),
                anchor: dv.anchor || (dv.anchorCode === "X" || dv.anchorCode === "XW" ? "EXTREMO" : ""),
                dayExtreme: dv.anchorCode === "X" || dv.anchorCode === "XW",
            }));
        }

        const extTol = isWinSym ? 5 : 0.5;
        const eps = 1e-6;
        const built = [];
        const seenKeys = new Set();

        candidates.forEach((cand) => {
            const confMin = parseMinAvwap(cand.confTime);
            if (confMin >= 0 && lastTodayMin >= 0 && confMin > lastTodayMin) return;

            const i0 = findTodayIdx(cand.f2Time, cand.dir);
            if (i0 === undefined || i0 < 0 || i0 >= todayBars.length) return;

            const isBull = cand.dir === 1;
            const b0 = todayBars[i0];
            const anchorPx = isBull ? Number(b0.low ?? b0.close) : Number(b0.high ?? b0.close);
            if (!(anchorPx > 0)) return;

            const anchorUpper = String(cand.anchor || "").toUpperCase();
            const hasExtTag = anchorUpper.includes("EXTREMO") || cand.dayExtreme;
            const atRunExtreme = isBull
                ? (anchorPx <= runMinLow[i0] + extTol)
                : (anchorPx >= runMaxHigh[i0] - extTol);
            if (!hasExtTag && !(i0 >= 1 && atRunExtreme)) return;

            const dedupKey = `${cand.dir}_${i0}`;
            if (seenKeys.has(dedupKey)) return;
            seenKeys.add(dedupKey);

            const v0 = getBarVol(b0);
            let cumPV = anchorPx * v0;
            let cumV = v0;
            const pts = [{ origIdx: b0._origIdx, time: String(b0.time).slice(0, 5), price: anchorPx }];
            let invalidated = false;
            let breakTime = null;

            for (let t = i0 + 1; t < todayBars.length; t += 1) {
                const bt = todayBars[t];
                const hi = Number(bt.high ?? bt.close);
                const lo = Number(bt.low ?? bt.close);
                const cl = Number(bt.close);
                if ((isBull && lo < anchorPx - eps) || (!isBull && hi > anchorPx + eps)) {
                    invalidated = true;
                    breakTime = String(bt.time).slice(0, 5);
                    break;
                }
                const tp = (hi + lo + cl) / 3;
                const vt = getBarVol(bt);
                cumPV += tp * vt;
                cumV += vt;
                pts.push({
                    origIdx: bt._origIdx,
                    time: String(bt.time).slice(0, 5),
                    price: cumPV / Math.max(1e-9, cumV),
                });
            }

            if (invalidated && pts.length < 2) return;

            built.push({
                id: `avwap-${isBull ? "bull" : "bear"}-${cand.num}-${i0}`,
                num: cand.num,
                dir: cand.dir,
                isBull,
                i0,
                anchorTime: String(b0.time).slice(0, 5),
                anchorPx,
                lastPrice: pts[pts.length - 1].price,
                lastOrigIdx: pts[pts.length - 1].origIdx,
                invalidated,
                breakTime,
                pts,
            });
        });

        const keepForDir = (dir) => {
            const list = built.filter((c) => c.dir === dir);
            const ended = list.filter((c) => c.invalidated).slice(-2);
            const active = list.filter((c) => !c.invalidated).slice(-1);
            return [...ended, ...active];
        };

        return [...keepForDir(1), ...keepForDir(-1)].sort((a, b) => (Number(a.invalidated) === Number(b.invalidated) ? a.i0 - b.i0 : (a.invalidated ? -1 : 1)));
    })();

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

    // ── Paredes GEX vindas do `gex/docs/magicwalls_tradingview.pine` dentro da janela [minP, maxP] ──
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
                                    label: isFlip ? "Virou Sup" : "Defendeu",
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
                                    label: "Absorveu",
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
                                    label: "Rompeu",
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
                                    label: isFlip ? "Virou Res" : "Defendeu",
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
                                    label: "Absorveu",
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
                                    label: "Rompeu",
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
                liveVerdict = `Wall gasta (${touchCount}x)`;
                isExhausted = true;
            } else if (isNearWall && (lastEv === "VIOLINADA_COMPRA" || (isTakingHeat && smartBias === "BUY" && smartStage === "FORTE"))) {
                liveVerdict = "Violinada (absorvendo compra)";
                dynamicBias = "BUY";
                isTrap = true;
            } else if (isNearWall && (lastEv === "VIOLINADA_VENDA" || (isTakingHeat && smartBias === "SELL" && smartStage === "FORTE"))) {
                liveVerdict = "Violinada (absorvendo venda)";
                dynamicBias = "SELL";
                isTrap = true;
            } else if (brokeUpConfirmed) {
                liveVerdict = "Romperam p/ alta (virou sup)";
                dynamicBias = "BUY";
            } else if (brokeDnConfirmed) {
                liveVerdict = "Romperam p/ baixo (virou res)";
                dynamicBias = "SELL";
            } else if (lastEv === "VIROU_SUP" && spotNow >= p - breakTol) {
                liveVerdict = "Virou suporte (defendendo)";
                dynamicBias = "BUY";
            } else if (lastEv === "VIROU_RES" && spotNow <= p + breakTol) {
                liveVerdict = "Virou resist. (defendendo)";
                dynamicBias = "SELL";
            } else if (smartBias === "BUY" || lastEv === "DEFENDEU_COMPRA") {
                liveVerdict = "Defendendo compra";
                dynamicBias = "BUY";
            } else if (smartBias === "SELL" || lastEv === "DEFENDEU_VENDA") {
                liveVerdict = "Defendendo venda";
                dynamicBias = "SELL";
            } else if (brokenDir === 1 && spotNow > p + breakTol) {
                liveVerdict = "Romperam p/ alta (virou sup)";
                dynamicBias = "BUY";
            } else if (brokenDir === -1 && spotNow < p - breakTol) {
                liveVerdict = "Romperam p/ baixo (virou res)";
                dynamicBias = "SELL";
            } else {
                liveVerdict = spotNow >= p ? "Suporte em disputa" : "Resist. em disputa";
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

    const activeFocusDivId = hoveredDivId || selectedDivId;
    const focusedDiv = activeFocusDivId
        ? swingDivergences.find((d) => d.divId === activeFocusDivId) || null
        : null;
    const fmtWaveCompact = (val) => {
        const num = Number(val || 0);
        if (Math.abs(num) < 0.5) return "0";
        const av = Math.abs(num);
        const sg = num > 0 ? "+" : "−";
        return av >= 1000
            ? `${sg}${(av / 1000).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}k`
            : `${sg}${Math.round(av).toLocaleString("pt-BR")}`;
    };

    const handleSwitchTimeframe = (nextTf) => {
        setChartTf(nextTf);
        setHoverPos(null);
        setHoveredDivId(null);
        if (nextTf === "M1") {
            setViewMode("M1_WINDOW");
            setVisibleCount(m1WinSize);
            let targetPan = 0;
            if (selectedDivId && Array.isArray(m1AssetData?.m1_series) && m1AssetData.m1_series.length > 0) {
                const m1List = m1AssetData.m1_series.filter((pt) => pt && !pt.is_prev_day && pt.time);
                const matched = swingDivergences.find((d) => d.divId === selectedDivId);
                if (matched && m1List.length > m1WinSize) {
                    const tKey = String(matched.currTime || "").slice(0, 5);
                    const m1Idx = m1List.findIndex((pt) => String(pt.time).slice(0, 5) >= tKey);
                    if (m1Idx >= 0) {
                        const desiredEnd = Math.max(m1WinSize, Math.min(m1List.length, m1Idx + Math.round(m1WinSize * 0.45)));
                        targetPan = Math.max(0, m1List.length - desiredEnd);
                    }
                }
            }
            setPanOffsetRight(targetPan);
        } else {
            setViewMode("HOJE");
            setPanOffsetRight(0);
        }
    };

    const showResetZoomBtn = !priceAutoScale
        || yZoomFactor !== 1.0
        || !flowAutoScale
        || flowYZoom !== 1.0
        || (!useM1Active && (viewMode === "CUSTOM" || rightGapPx !== 28))
        || (useM1Active && viewMode === "CUSTOM");

    const m1FirstTime = series[0]?.time ? String(series[0].time).slice(0, 5) : "09:00";
    const m1LastTime = series[series.length - 1]?.time ? String(series[series.length - 1].time).slice(0, 5) : "18:30";

    return (
        <div
            ref={chartBoxRef}
            className="mw-card rb-fade-up mw-chart-card"
            style={{
                minWidth: 0,
                width: "100%",
                height: "100%",
                boxSizing: "border-box",
                overflow: "hidden",
                display: "flex",
                flexDirection: "column",
            }}
        >
            {embeddedHeader}

            {/* ── Barra Superior Unificada Ink Azul ── */}
            <div
                className="mw-chart-toolbar"
                data-side={isSideBySide ? "true" : "false"}
                style={{
                    backgroundColor: "var(--mw-bg)",
                    padding: isNarrow ? "10px 12px" : (isSideBySide ? "8px 14px" : "8px 20px"),
                    borderBottom: "1px solid var(--mw-hairline)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: isSideBySide ? "6px 8px" : 8,
                }}
            >
                <div style={{
                    display: "flex",
                    alignItems: "center",
                    gap: isSideBySide ? 6 : 8,
                    flexWrap: "wrap",
                    ...(isSideBySide ? { flex: "1 1 auto", minWidth: 0 } : {}),
                }}>
                    {!embeddedHeader && (
                        <span className="mw-mono" style={{
                            fontSize: 12,
                            fontWeight: 600,
                            color: "var(--mw-accent-ink)",
                            background: "var(--mw-accent-soft)",
                            padding: "3px 8px",
                            borderRadius: 6,
                            border: "1px solid var(--mw-accent-border)",
                        }}>
                            {contractName || symKey} · {useM1Active ? "M1" : "M5"}
                        </span>
                    )}

                    {/* Timeframe M5 / M1 */}
                    <div className="mw-track" role="group" aria-label={`Timeframe ${symKey}`}>
                        {[
                            { id: "M5", label: "M5", desc: "Gráfico de 5 minutos (sessão completa)" },
                            { id: "M1", label: m1Loading && chartTf === "M1" ? "M1..." : "M1", desc: "Gráfico de 1 minuto (janela navegável)" },
                        ].map((tfOpt) => {
                            const active = chartTf === tfOpt.id;
                            return (
                                <button
                                    key={tfOpt.id}
                                    type="button"
                                    className="mw-btn mw-mono"
                                    data-active={active ? "true" : "false"}
                                    onClick={() => handleSwitchTimeframe(tfOpt.id)}
                                    title={tfOpt.desc}
                                >
                                    {active && <span className="mw-dot-accent" />}
                                    <span>{tfOpt.label}</span>
                                </button>
                            );
                        })}
                    </div>

                    {/* Navegação limpa exibida apenas no M1 */}
                    {useM1Active && (
                        <div className="mw-track" role="group" aria-label={`Janela M1 ${symKey}`}>
                            <button
                                type="button"
                                className="mw-btn"
                                disabled={clampedPan >= maxPan}
                                onClick={() => {
                                    setViewMode("M1_WINDOW");
                                    setPanOffsetRight((p) => Math.min(maxPan, p + 45));
                                    setHoverPos(null);
                                }}
                                title="Recuar 45 minutos"
                            >
                                <IconChevLeft />
                            </button>
                            <span className="mw-mono" style={{ padding: "0 6px", fontSize: 11, color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>
                                {m1FirstTime}–{m1LastTime}
                            </span>
                            <button
                                type="button"
                                className="mw-btn"
                                disabled={clampedPan <= 0}
                                onClick={() => {
                                    setViewMode("M1_WINDOW");
                                    setPanOffsetRight((p) => Math.max(0, p - 45));
                                    setHoverPos(null);
                                }}
                                title="Avançar 45 minutos"
                            >
                                <IconChevRight />
                            </button>
                            <span style={{ width: 1, height: 14, backgroundColor: "var(--mw-hairline-strong)", margin: "0 2px" }} />
                            {[
                                { label: "1h", bars: 60 },
                                { label: "2h", bars: 120 },
                                { label: "3h", bars: 180 },
                            ].map((winOpt) => {
                                const active = viewMode !== "CUSTOM" && m1WinSize === winOpt.bars;
                                return (
                                    <button
                                        key={winOpt.label}
                                        type="button"
                                        className="mw-btn mw-mono"
                                        data-active={active ? "true" : "false"}
                                        onClick={() => {
                                            setM1WinSize(winOpt.bars);
                                            setVisibleCount(winOpt.bars);
                                            setViewMode("M1_WINDOW");
                                            setHoverPos(null);
                                        }}
                                        title={`Mostrar janela de ${winOpt.label} (${winOpt.bars} candles M1)`}
                                    >
                                        {active && <span className="mw-dot-accent" />}
                                        <span>{winOpt.label}</span>
                                    </button>
                                );
                            })}
                        </div>
                    )}

                    {/* Camadas do gráfico */}
                    <div className="mw-track" role="group" aria-label={`Camadas ${symKey}`}>
                        {!isWallsHost && (
                            <>
                                <button
                                    type="button"
                                    className="mw-btn"
                                    data-active={candleColorMode !== "TRADICIONAL" ? "true" : "false"}
                                    onClick={() => setCandleColorMode(m => (m === "TRADICIONAL" ? "JANELA" : "TRADICIONAL"))}
                                >
                                    {candleColorMode === "TRADICIONAL" ? "Barras padrão" : "Barras fluxo"}
                                </button>
                                <button
                                    type="button"
                                    className="mw-btn"
                                    data-active={wallColorMode !== "PINE" ? "true" : "false"}
                                    onClick={() => setWallColorMode(m => (m === "PINE" ? "POLARIDADE" : "PINE"))}
                                >
                                    {wallColorMode === "PINE" ? "Walls neutro" : "Walls polaridade"}
                                </button>
                                <button
                                    type="button"
                                    className="mw-btn"
                                    data-active="true"
                                    onClick={() => setSmWinVisualMode(m => (m === "HIST_LINE" ? "LINE" : m === "LINE" ? "HIST" : "HIST_LINE"))}
                                >
                                    {smWinVisualMode === "HIST_LINE" ? "Hist + linha" : smWinVisualMode === "LINE" ? "Linha" : "Histograma"}
                                </button>
                            </>
                        )}
                        <button
                            type="button"
                            className="mw-btn"
                            data-active={showMidleWalls ? "true" : "false"}
                            onClick={() => setShowMidleWalls(v => !v)}
                            title="Exibir ou ocultar MidWalls tracejadas"
                        >
                            {showMidleWalls && <span className="mw-dot-accent" />}
                            <span>MidWalls</span>
                        </button>
                        <button
                            type="button"
                            className="mw-btn"
                            data-active={showVolumeProfile ? "true" : "false"}
                            onClick={toggleVolumeProfile}
                            title="Exibir ou ocultar Volume Profile da sessão na borda direita interna (Total + Núcleo Institucional)"
                        >
                            {showVolumeProfile && <span className="mw-dot-accent" />}
                            <span>Vol. Profile</span>
                        </button>
                        <button
                            type="button"
                            className="mw-btn"
                            data-active={showAvwap ? "true" : "false"}
                            onClick={toggleAvwap}
                            title="Exibir ou ocultar VWAP Ancorada automática nas divergências de extremo do dia (Compra na mínima / Venda na máxima)"
                        >
                            {showAvwap && <span className="mw-dot-accent" />}
                            <span>AVWAP</span>
                        </button>
                        {isWallsHost ? (
                            <button
                                type="button"
                                className="mw-btn"
                                data-active={showNweLine ? "true" : "false"}
                                onClick={toggleCanalGauss}
                                title="Exibir ou ocultar o Canal Gauss (Nadaraya-Watson L=100)"
                            >
                                {showNweLine && <span className="mw-dot-accent" />}
                                <span>Canal Gauss</span>
                            </button>
                        ) : (
                            <button
                                type="button"
                                className="mw-btn"
                                data-active={showNweLine ? "true" : "false"}
                                onClick={() => setShowNweLine(v => !v)}
                                title="Exibir ou ocultar Média NWE"
                            >
                                {showNweLine && <span className="mw-dot-accent" />}
                                <span>Média NWE</span>
                            </button>
                        )}
                        {!isWallsHost && (
                            <>
                                <button
                                    type="button"
                                    className="mw-btn"
                                    data-active={showWindowFlips ? "true" : "false"}
                                    onClick={() => setShowWindowFlips(v => !v)}
                                >
                                    Viradas
                                </button>
                                <button
                                    type="button"
                                    className="mw-btn"
                                    data-active={showWallBattleLabels ? "true" : "false"}
                                    onClick={() => setShowWallBattleLabels(v => !v)}
                                >
                                    Eventos Wall
                                </button>
                            </>
                        )}
                        {isWallsHost && (() => {
                            const on = divEngine === "v3.2";
                            const busy = on && engineDivs.status === "loading";
                            const err = on && engineDivs.status === "erro";
                            return (
                                <>
                                    <button
                                        type="button"
                                        className="mw-btn"
                                        data-active={on ? "true" : "false"}
                                        onClick={() => {
                                            const nv = on ? "NENHUMA" : "v3.2";
                                            chooseDivEngine(nv);
                                            setShowSwingDivLines(nv !== "NENHUMA");
                                        }}
                                        style={err ? { color: "var(--mw-neg)" } : undefined}
                                        title="Exibir ou ocultar os sinais numerados (1, 2, 3...) no gráfico"
                                    >
                                        {on && <span className="mw-dot-accent" />}
                                        <span>Sinais{on ? ` (${busy ? "…" : err ? "erro" : totalDayDivCount})` : ""}</span>
                                    </button>
                                    {on && (
                                        <button
                                            type="button"
                                            className="mw-btn"
                                            data-active={showDivLines ? "true" : "false"}
                                            onClick={toggleDivLines}
                                            title="Exibir ou ocultar todas as linhas de divergência (F1→F2 / T1→T2) no preço e no fluxo"
                                        >
                                            {showDivLines && <span className="mw-dot-accent" />}
                                            <span>Linhas div.</span>
                                        </button>
                                    )}
                                </>
                            );
                        })()}
                    </div>

                    {showResetZoomBtn && (
                        <button
                            type="button"
                            className="mw-btn mw-btn-secondary"
                            onClick={() => {
                                setPriceAutoScale(true);
                                setYZoomFactor(1.0);
                                setPriceYOffset(0);
                                setFlowAutoScale(true);
                                setFlowYZoom(1.0);
                                setFlowYOffset(0);
                                setRightGapPx(28);
                                setPanOffsetRight(0);
                                setViewMode(useM1Active ? "M1_WINDOW" : "HOJE");
                                if (useM1Active) setVisibleCount(m1WinSize);
                            }}
                            title="Restaurar escala automática e zoom padrão"
                        >
                            Resetar zoom
                        </button>
                    )}

                    {capitalDrawerInfo && (
                        <button
                            type="button"
                            className="mw-btn mw-btn-secondary mw-mono"
                            onClick={capitalDrawerInfo.onToggle}
                            title={capitalDrawerInfo.isCollapsed ? "Expandir painel lateral" : "Recuar painel lateral"}
                        >
                            <span style={{ color: capitalDrawerInfo.netBrl >= 0 ? "var(--mw-pos)" : "var(--mw-neg)" }}>
                                {capitalDrawerInfo.netBrl >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(capitalDrawerInfo.netBrl), 0)}
                            </span>
                            <span style={{ color: "var(--mw-accent-ink)" }}>
                                {capitalDrawerInfo.isCollapsed ? "Resumo" : "Recuar"}
                            </span>
                        </button>
                    )}
                    {isSideBySide && canUseMediaStudio && (
                        <div style={{ display: "inline-flex", alignItems: "center", gap: 6, marginLeft: "auto", flexShrink: 0 }}>
                            <button
                                type="button"
                                className="mw-btn mw-btn-secondary"
                                style={{ padding: "0 8px" }}
                                onClick={() => setShowInstaModal(true)}
                                title="Gerar card para Instagram (Stories 9:16 ou Feed 4:5)"
                            >
                                <IconCamera />
                                <span>Card IG</span>
                            </button>
                            <button
                                type="button"
                                className="mw-btn mw-btn-secondary"
                                style={{ padding: "0 8px" }}
                                data-testid="open-morning-video-btn"
                                onClick={() => setShowMorningVideoModal(true)}
                                title="Gerar vídeo animado de início do pregão (Reels 9:16 ou 16:9)"
                            >
                                <IconFilm />
                                <span>Vídeo 08h30</span>
                            </button>
                        </div>
                    )}
                </div>

                {/* Direita (ou linha 2 dedicada no Lado a lado): Inspetor OHLC / Sinal focado + Exportações */}
                <div style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    flexWrap: isSideBySide ? "nowrap" : "wrap",
                    marginLeft: isSideBySide ? 0 : "auto",
                    ...(isSideBySide ? { flex: "1 0 100%", minWidth: 0 } : {}),
                }}>
                    <div
                        className="mw-mono"
                        style={{
                            display: isSideBySide ? "flex" : "inline-flex",
                            alignItems: "center",
                            gap: isSideBySide ? 8 : 10,
                            flexWrap: isSideBySide ? "nowrap" : "wrap",
                            width: isSideBySide ? "100%" : "auto",
                            overflow: isSideBySide ? "hidden" : "visible",
                            whiteSpace: isSideBySide ? "nowrap" : "normal",
                            fontSize: isSideBySide ? 11.5 : 12,
                            lineHeight: "16px",
                            background: "var(--mw-chrome)",
                            padding: "4px 10px",
                            borderRadius: 6,
                            border: "1px solid var(--mw-hairline)",
                            color: "var(--mw-text-3)",
                        }}
                    >
                        {focusedDiv ? (
                            <>
                                <span style={{ color: focusedDiv.type === "BULL_DIV" ? "var(--mw-pos)" : "var(--mw-neg)", fontWeight: 500 }}>
                                    #{focusedDiv.num} · {focusedDiv.type === "BULL_DIV" ? "Compra" : "Venda"} ({focusedDiv.anchorCode})
                                </span>
                                <span style={{ color: "var(--mw-text-2)" }}>{focusedDiv.currTime}</span>
                                <span>
                                    Preço <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(focusedDiv.currPrice, dec)}</strong>
                                </span>
                                <span>
                                    Fluxo {focusedDiv.type === "BULL_DIV" ? "F1→F2" : "T1→T2"}{" "}
                                    <strong style={{ fontWeight: 500, color: focusedDiv.type === "BULL_DIV" ? "var(--mw-pos)" : "var(--mw-neg)" }}>
                                        {fmtWaveCompact(focusedDiv.currWave - focusedDiv.prevWave)}
                                    </strong>
                                </span>
                                {selectedDivId === focusedDiv.divId && !hoveredDivId && (
                                    <button
                                        type="button"
                                        onClick={() => setSelectedDivId(null)}
                                        title="Limpar seleção do sinal"
                                        style={{
                                            padding: "0 5px",
                                            borderRadius: 4,
                                            background: "var(--mw-raised)",
                                            border: "1px solid var(--mw-hairline-strong)",
                                            color: "var(--mw-text-2)",
                                            fontSize: 11,
                                            cursor: "pointer",
                                        }}
                                    >
                                        ×
                                    </button>
                                )}
                            </>
                        ) : (
                            <>
                                <span style={{ color: "var(--mw-text-2)" }}>
                                    {inspectedPt.is_prev_day ? `Ontem ${inspectedPt.time}` : inspectedPt.time}
                                </span>
                                <span>
                                    A <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(inspectedPt.open, dec)}</strong>
                                </span>
                                <span>
                                    M <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(inspectedPt.high, dec)}</strong>
                                </span>
                                <span>
                                    m <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(inspectedPt.low, dec)}</strong>
                                </span>
                                <span>
                                    F <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(inspectedPt.close, dec)}</strong>
                                </span>
                                {showNweLine && getNweLine(inspectedPt) > 0 && (
                                    <span>
                                        Gauss <strong style={{ fontWeight: 500, color: "var(--mw-accent-ink)" }}>{fmtNum(getNweLine(inspectedPt), dec)}</strong>
                                    </span>
                                )}
                                <span>
                                    Fluxo <strong style={{ fontWeight: 500, color: "var(--mw-flow)" }}>{fmtWaveCompact(inspectedSub?.smartSwingWave ?? 0)}</strong>
                                </span>
                            </>
                        )}
                    </div>

                    {!isSideBySide && canUseMediaStudio && (
                        <>
                            <button
                                type="button"
                                className="mw-btn mw-btn-secondary"
                                onClick={() => setShowInstaModal(true)}
                                title="Gerar card para Instagram (Stories 9:16 ou Feed 4:5)"
                            >
                                <IconCamera />
                                <span>Card IG</span>
                            </button>
                            <button
                                type="button"
                                className="mw-btn mw-btn-secondary"
                                data-testid="open-morning-video-btn"
                                onClick={() => setShowMorningVideoModal(true)}
                                title="Gerar vídeo animado de início do pregão (Reels 9:16 ou 16:9)"
                            >
                                <IconFilm />
                                <span>Vídeo 08h30</span>
                            </button>
                        </>
                    )}
                </div>
            </div>

            {/* ── GRÁFICO PRINCIPAL INTERATIVO INK AZUL ── */}
            <svg
                ref={svgRef}
                viewBox={`0 0 ${width} ${height}`}
                preserveAspectRatio="xMidYMid meet"
                style={{
                    width: "100%",
                    height: `${height}px`,
                    maxWidth: "100%",
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
                                : useM1Active
                                    ? "grab"
                                    : "crosshair",
                    background: "#0e1118",
                }}
                onMouseDown={(e) => {
                    if (e.target && e.target.closest && e.target.closest("[data-div-id]")) return;
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
                        setRightGapPx(28);
                        setPanOffsetRight(0);
                        setViewMode(useM1Active ? "M1_WINDOW" : "HOJE");
                    }
                }}
            >
                <defs>
                    <clipPath id={`clip-p1-band-${symKey}`}>
                        <rect x="0" y={p1Top} width={width} height={p1H} />
                    </clipPath>
                    <clipPath id={`clip-p1-plot-${symKey}`}>
                        <rect x={padL} y={p1Top} width={plotW} height={p1H} />
                    </clipPath>
                    <clipPath id={`clip-p3-band-${symKey}`}>
                        <rect x="0" y={p3Top + 15} width={width} height={Math.max(10, p3H - 15)} />
                    </clipPath>
                </defs>

                {/* Fundos dos 2 Painéis Unificados Ink Azul (#0e1118) */}
                <rect x={padL} y={p1Top} width={plotW} height={p1H} fill="#0e1118" />
                <rect x={padL} y={p3Top} width={plotW} height={p3H} fill="#0e1118" />

                {/* Escala de Preço no Eixo Y (sem grade horizontal cruzando os candles) */}
                {priceAxisTicks.map((tk, tIdx) => {
                    const nearSpot = Math.abs(tk.y - lastY) < 13;
                    const nearWall = nearbyWalls.some((w) => Math.abs(toY1(w.price) - tk.y) < 11);
                    const nearAutoBtn = tk.y > p1Bot - 22;
                    return (
                        <g key={`tv-p1-tick-${tIdx}`}>
                            {!nearSpot && !nearWall && !nearAutoBtn && (
                                <>
                                    <line
                                        x1={padL + plotW}
                                        y1={tk.y}
                                        x2={padL + plotW + 3}
                                        y2={tk.y}
                                        stroke="rgba(238, 240, 245, 0.14)"
                                        strokeWidth="1"
                                    />
                                    <text
                                        x={padL + plotW + 6}
                                        y={tk.y + 3.5}
                                        fill="#5d667a"
                                        fontSize={isNarrow ? "9.5" : "10"}
                                        fontFamily="var(--mono)"
                                    >
                                        {fmtNum(tk.price, dec)}
                                    </text>
                                </>
                            )}
                        </g>
                    );
                })}

                {/* Divisórias Horizontais + Barra Splitter Redimensionável */}
                <line x1={padL} y1={p1Bot} x2={width} y2={p1Bot} stroke={cursorZone === "SPLITTER" || dragState?.type === "SPLITTER" ? "rgba(56, 189, 248, 0.55)" : "rgba(238, 240, 245, 0.08)"} strokeWidth="1" />
                <line x1={padL} y1={p3Top} x2={width} y2={p3Top} stroke={cursorZone === "SPLITTER" || dragState?.type === "SPLITTER" ? "rgba(56, 189, 248, 0.55)" : "rgba(238, 240, 245, 0.08)"} strokeWidth="1" />
                <rect
                    x={padL}
                    y={p1Bot}
                    width={plotW}
                    height={splitterGap}
                    fill={cursorZone === "SPLITTER" || dragState?.type === "SPLITTER" ? "rgba(56, 189, 248, 0.08)" : "#0a0c12"}
                />
                <rect
                    x={padL + plotW / 2 - 18}
                    y={splitterMidY - 1.5}
                    width={36}
                    height={3}
                    rx="1.5"
                    fill={cursorZone === "SPLITTER" || dragState?.type === "SPLITTER" ? "#38bdf8" : "rgba(238, 240, 245, 0.16)"}
                />
                <line x1={padL} y1={p3Bot} x2={width} y2={p3Bot} stroke="rgba(238, 240, 245, 0.08)" strokeWidth="1" />
                <line x1={padL + plotW} y1={0} x2={padL + plotW} y2={p3Bot} stroke="rgba(238, 240, 245, 0.08)" strokeWidth="1" />

                {/* Títulos Internos Discretos + Legenda Silenciosa no Canvas */}
                <text x={padL + 4} y={16} fill="#a3a9b8" fontSize="11" fontWeight="500" fontFamily="var(--sans)">
                    Preço · {contractName || symKey} ({useM1Active ? "M1 · arraste para navegar" : "M5"})
                </text>
                {isWallsHost && !isNarrow && (() => {
                    const legX = padL + (useM1Active ? 276 : 156);
                    if (legX + 245 > padL + plotW) return null;
                    const showAvwapLegend = showAvwap && (legX + 295 <= padL + plotW);
                    return (
                        <g fontSize="10.5" fontFamily="var(--sans)" fill="#848da2">
                            <line x1={legX} y1="12" x2={legX + 14} y2="12" stroke="rgba(238, 240, 245, 0.88)" strokeWidth="2.6" />
                            <text x={legX + 18} y="15.5" fill="#d8dee9">Call/Put Wall</text>
                            <line x1={legX + 86} y1="12" x2={legX + 100} y2="12" stroke="rgba(238, 240, 245, 0.34)" strokeWidth="1.0" />
                            <text x={legX + 104} y="15.5">Wall</text>
                            <line x1={legX + 134} y1="12" x2={legX + 148} y2="12" stroke="rgba(238, 240, 245, 0.24)" strokeWidth="1.0" strokeDasharray="3 2" />
                            <text x={legX + 152} y="15.5">Mid</text>
                            <line x1={legX + 178} y1="12" x2={legX + 192} y2="12" stroke="#d4a259" strokeWidth="2.0" />
                            <text x={legX + 196} y="15.5" fill="#d4a259">Flip</text>
                            {showAvwapLegend && (
                                <>
                                    <line x1={legX + 224} y1="12" x2={legX + 238} y2="12" stroke="#7dd3fc" strokeWidth="1.7" />
                                    <text x={legX + 242} y="15.5" fill="#7dd3fc">AVWAP</text>
                                </>
                            )}
                        </g>
                    );
                })()}
                <text x={padL + 4} y={p3Top + 12} fill="#a3a9b8" fontSize="11" fontWeight="500" fontFamily="var(--sans)">
                    {flowSubMode === "SWING_DIVERGENCIA"
                        ? "Fluxo Smart Money"
                        : flowSubMode === "CABO_GUERRA"
                            ? "Cabo de guerra (Institucional vs Varejo · M5)"
                            : flowSubMode === "OSC_DIVERGENCIA"
                                ? `Oscilador de divergência (${oscTf})`
                                : flowSubMode === "CVD_4PLAYERS"
                                    ? "CVD acumulado 4-players (sessão)"
                                    : smWinVisualMode === "HIST_LINE"
                                        ? "Janela de Fluxo Smart Money (histograma + linha)"
                                        : smWinVisualMode === "LINE"
                                            ? "Janela de Fluxo Smart Money (linha)"
                                            : "Janela de Fluxo Smart Money (histograma)"}
                </text>
                {flowSubMode === "JANELA_ASG" && (
                    <g onMouseDown={(e) => e.stopPropagation()}>
                        {[
                            { id: "HIST_LINE", label: "Hist + Linha", w: 66 },
                            { id: "LINE", label: "Linha", w: 42 },
                            { id: "HIST", label: "Hist", w: 38 },
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
                                        rx="3"
                                        fill={active ? "rgba(56, 189, 248, 0.14)" : "#0e1118"}
                                        stroke={active ? "#38bdf8" : "#1b212e"}
                                        strokeWidth="0.85"
                                    />
                                    <text
                                        x={xBtn + mOpt.w / 2}
                                        y={p3Top + 11}
                                        fill={active ? "#38bdf8" : "#848da2"}
                                        fontSize="7.4"
                                        fontWeight="600"
                                        fontFamily="IBM Plex Mono, monospace"
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

                {/* Volume Profile Monocromático da Sessão na Borda Direita Interna (Total + Núcleo Institucional) */}
                {showVolumeProfile && (() => {
                    const defaultStep = symKey === "WIN" ? 25 : 1;
                    let vp = (volumeProfile && Array.isArray(volumeProfile.bins) && volumeProfile.bins.length > 0)
                        ? volumeProfile
                        : null;

                    if (!vp && Array.isArray(m5RawSeries) && m5RawSeries.length > 0) {
                        const binMap = new Map();
                        m5RawSeries.forEach((b) => {
                            if (!b || b.is_prev_day) return;
                            const hi = Number(b.high || 0);
                            const lo = Number(b.low || 0);
                            const op = Number(b.open || lo);
                            const cl = Number(b.close || hi);
                            if (hi <= 0 || lo <= 0) return;
                            const loP = Math.min(lo, hi);
                            const hiP = Math.max(lo, hi);
                            const bv = Number(b.buy_vol || 0);
                            const sv = Number(b.sell_vol || 0);
                            const totB = bv + sv > 0 ? bv + sv : Math.abs(Number(b.delta_bar || 0));
                            if (totB <= 0) return;
                            const idB = Number(b.inst_delta_bar ?? b.inst_aggr_delta ?? 0);
                            const instEst = Math.min(totB, Math.max(Math.abs(idB), totB * 0.25));
                            const bLo = Math.round(loP / defaultStep) * defaultStep;
                            const bHi = Math.round(hiP / defaultStep) * defaultStep;
                            const stepsN = Math.min(200, Math.max(1, Math.round((bHi - bLo) / defaultStep) + 1));
                            const midC = (op + cl) * 0.5;
                            const span = Math.max(defaultStep, (bHi - bLo) * 0.5 + defaultStep);
                            const pks = [];
                            let wSum = 0;
                            for (let s = 0; s < stepsN; s += 1) {
                                const pk = Number((bLo + s * defaultStep).toFixed(2));
                                const wt = Math.max(0.15, 1.0 - Math.abs(pk - midC) / span);
                                pks.push([pk, wt]);
                                wSum += wt;
                            }
                            pks.forEach(([pk, wt]) => {
                                const frac = wt / (wSum || 1);
                                const cur = binMap.get(pk) || { p: pk, v: 0, iv: 0, d: 0 };
                                cur.v += totB * frac;
                                cur.iv += instEst * frac;
                                cur.d += (bv - sv) * frac;
                                binMap.set(pk, cur);
                            });
                        });
                        const fbBins = Array.from(binMap.values()).sort((a, b) => a.p - b.p);
                        if (fbBins.length > 0) {
                            let pocIdx = 0;
                            let totV = 0;
                            fbBins.forEach((bn, idx) => {
                                totV += bn.v;
                                if (bn.v > fbBins[pocIdx].v) pocIdx = idx;
                            });
                            let loIdx = pocIdx;
                            let hiIdx = pocIdx;
                            let accV = fbBins[pocIdx].v;
                            while (accV < totV * 0.70 && (loIdx > 0 || hiIdx < fbBins.length - 1)) {
                                const vDn = loIdx > 0 ? fbBins[loIdx - 1].v : -1;
                                const vUp = hiIdx < fbBins.length - 1 ? fbBins[hiIdx + 1].v : -1;
                                if (vUp >= vDn && hiIdx < fbBins.length - 1) {
                                    hiIdx += 1;
                                    accV += fbBins[hiIdx].v;
                                } else if (loIdx > 0) {
                                    loIdx -= 1;
                                    accV += fbBins[loIdx].v;
                                } else {
                                    break;
                                }
                            }
                            vp = {
                                step: defaultStep,
                                source: "M5_FALLBACK",
                                poc: fbBins[pocIdx].p,
                                vah: fbBins[hiIdx].p,
                                val: fbBins[loIdx].p,
                                bins: fbBins,
                            };
                        }
                    }

                    if (!vp || !Array.isArray(vp.bins) || vp.bins.length === 0) return null;

                    const rawStep = Math.max(0.25, Number(vp.step || defaultStep));
                    const rawBinPx = Math.abs(toY1(minP) - toY1(minP + rawStep));
                    let mergeK = 1;
                    if (rawBinPx < 3.0) {
                        const mults = [2, 4, 5, 10, 20];
                        for (let mIdx = 0; mIdx < mults.length; mIdx += 1) {
                            if (rawBinPx * mults[mIdx] >= 3.2) {
                                mergeK = mults[mIdx];
                                break;
                            }
                            mergeK = mults[mIdx];
                        }
                    }
                    const mergedStep = rawStep * mergeK;

                    let displayBins = vp.bins;
                    if (mergeK > 1) {
                        const mMap = new Map();
                        vp.bins.forEach((bn) => {
                            const mp = Number((Math.round(Number(bn.p) / mergedStep) * mergedStep).toFixed(2));
                            const cur = mMap.get(mp) || { p: mp, v: 0, iv: 0, d: 0, id: 0 };
                            cur.v += Number(bn.v || 0);
                            cur.iv += Number(bn.iv || 0);
                            cur.d += Number(bn.d || 0);
                            cur.id += Number(bn.id || 0);
                            mMap.set(mp, cur);
                        });
                        displayBins = Array.from(mMap.values()).sort((a, b) => a.p - b.p);
                    }

                    const visibleBins = displayBins.filter((bn) => bn.p >= minP - mergedStep && bn.p <= maxP + mergedStep);
                    if (visibleBins.length === 0) return null;

                    const maxBinV = Math.max(1, ...displayBins.map((bn) => Number(bn.v || 0)));
                    const pocRaw = Number(vp.poc || 0);
                    const pocMerged = mergeK > 1 ? Number((Math.round(pocRaw / mergedStep) * mergedStep).toFixed(2)) : pocRaw;
                    const valNum = Number(vp.val || 0);
                    const vahNum = Number(vp.vah || 0);

                    const rightEdge = padL + plotW;
                    const vpMaxW = Math.max(28, Math.min(130, plotW * 0.18));
                    const binPx = Math.abs(toY1(minP) - toY1(minP + mergedStep));
                    const barH = Math.max(2.0, binPx - 1.0);
                    const pocY = pocRaw > 0 ? toY1(pocRaw) : null;

                    return (
                        <g>
                            {visibleBins.map((bn, idx) => {
                                const pVal = Number(bn.p);
                                const vTot = Number(bn.v || 0);
                                if (vTot <= 0) return null;
                                const vInst = Math.min(vTot, Math.max(0, Number(bn.iv || 0)));
                                const dNet = Number(bn.d || 0);
                                const yCenter = toY1(pVal);
                                const yTopBar = yCenter - barH / 2;
                                const barW = Math.max(1.5, (vTot / maxBinV) * vpMaxW);
                                const instW = vInst > 0 ? Math.max(1.0, Math.min(barW, (vInst / maxBinV) * vpMaxW)) : 0;

                                const isPoc = pocMerged > 0 && Math.abs(pVal - pocMerged) <= mergedStep * 0.45;
                                const inVa = valNum > 0 && vahNum >= valNum && pVal >= valNum - mergedStep * 0.5 && pVal <= vahNum + mergedStep * 0.5;

                                const totalFill = isPoc
                                    ? "rgba(238, 240, 245, 0.34)"
                                    : inVa
                                        ? "rgba(226, 232, 240, 0.21)"
                                        : "rgba(148, 163, 184, 0.10)";
                                const instFill = isPoc
                                    ? "rgba(248, 250, 252, 0.52)"
                                    : inVa
                                        ? "rgba(241, 245, 249, 0.34)"
                                        : "rgba(203, 213, 225, 0.18)";
                                const instPct = Math.round((vInst / vTot) * 100);
                                const tagTxt = isPoc ? " [POC]" : (inVa ? " [Área de Valor]" : "");

                                return (
                                    <g key={`vp-bin-${idx}`}>
                                        <title>{`Volume Profile @ ${fmtNum(pVal, dec)}${tagTxt} | Total: ${fmtNum(vTot, 0)} | Inst: ${fmtNum(vInst, 0)} (${instPct}%) | Delta: ${fmtNum(dNet, 0, true)}`}</title>
                                        <rect
                                            x={rightEdge - barW}
                                            y={yTopBar}
                                            width={barW}
                                            height={barH}
                                            fill={totalFill}
                                            rx="0.8"
                                        />
                                        {instW > 0 && (
                                            <rect
                                                x={rightEdge - instW}
                                                y={yTopBar}
                                                width={instW}
                                                height={barH}
                                                fill={instFill}
                                                rx="0.8"
                                            />
                                        )}
                                    </g>
                                );
                            })}
                            {pocY !== null && pocY >= p1Top + 4 && pocY <= p1Bot - 4 && (
                                <g pointerEvents="none">
                                    <line
                                        x1={rightEdge - vpMaxW}
                                        y1={pocY}
                                        x2={rightEdge}
                                        y2={pocY}
                                        stroke="rgba(248, 250, 252, 0.62)"
                                        strokeWidth="1"
                                    />
                                    {pocY >= p1Top + 12 && pocY <= p1Bot - 12 && (
                                        <text
                                            x={rightEdge - 3}
                                            y={pocY - 3}
                                            textAnchor="end"
                                            fill="rgba(238, 240, 245, 0.72)"
                                            fontSize="8"
                                            fontWeight="600"
                                            fontFamily="var(--mono)"
                                        >
                                            POC
                                        </text>
                                    )}
                                </g>
                            )}
                        </g>
                    );
                })()}

                {/* Regiões Sombreadas de Compra e Venda (MagicWall + MidWall) Diferenciadas por Defesa Institucional + Hedge Makers */}
                {(() => {
                    const zonesToRender = [];
                    const baseBandPts = rangeP * 0.032;

                    const nearestResP = Number(sellZone?.ref_price || 0);
                    const nearestSupP = Number(buyZone?.ref_price || 0);

                    const hasZoneStruct = nearbyWalls.some((w) => w && (w.is_local_call_wall || w.is_local_put_wall));
                    const zoneCallPrices = new Set();
                    const zonePutPrices = new Set();
                    if (hasZoneStruct) {
                        nearbyWalls.forEach((w) => {
                            if (!w || String(w.type || "") !== "Wall") return;
                            if (w.is_local_call_wall) zoneCallPrices.add(Number(w.price));
                            if (w.is_local_put_wall) zonePutPrices.add(Number(w.price));
                        });
                    } else {
                        let bestCall = null;
                        let bestPut = null;
                        const getG = (w) => Number(w.gex_raw ?? w.gex ?? 0);
                        nearbyWalls.forEach((w) => {
                            if (!w || String(w.type || "") !== "Wall") return;
                            const g = getG(w);
                            if (g > 0 && (!bestCall || g > getG(bestCall))) bestCall = w;
                            if (g < 0 && (!bestPut || g < getG(bestPut))) bestPut = w;
                        });
                        if (bestCall) zoneCallPrices.add(Number(bestCall.price));
                        if (bestPut) zonePutPrices.add(Number(bestPut.price));
                    }

                    nearbyWalls.forEach((w, idx) => {
                        const wType = String(w.type || "Wall");
                        const isMid = wType.toLowerCase().includes("mid") || String(w.label || "").toUpperCase() === "MIDLEWALL";
                        const isMainWall = wType === "Wall";
                        if (!isMainWall && !isMid) return;

                        const isDomCallOrPut = isMainWall && (zoneCallPrices.has(Number(w.price)) || zonePutPrices.has(Number(w.price)));
                        if (isWallsHost && !isDomCallOrPut) return;

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

                        if (!isWallsHost && tier === "FRACA" && !isNearestActive && isNeutral) return;

                        const isStrong = isDomCallOrPut
                            || w.smart_stage === "FORTE"
                            || (tier === "FORTE" && (!isMid || defLots > 0 || isNearestActive));
                        const scaleFactor = isWallsHost ? 0.62 : (isStrong ? (isMid ? 0.44 : 0.58) : (isMid ? 0.26 : 0.35));
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
                        if (isWallsHost && z.isMid) return null;
                        if (z.topP < minP || z.botP > maxP) return null;
                        const yTop = Math.max(p1Top, toY1(Math.min(maxP, z.topP)));
                        const yBot = Math.min(p1Bot, toY1(Math.max(minP, z.botP)));
                        const hBand = Math.max(5, yBot - yTop);
                        const isWhiteWallMode = isWallsHost || wallColorMode === "PINE" || z.isNeutral;
                        const col = isWallsHost
                            ? (z.isMid ? "#8b9bb0" : "#eef0f5")
                            : (isWhiteWallMode ? "#eef0f5" : (z.isSell ? "#e5484d" : "#4cc38a"));
                        const fillRgba = isWallsHost
                            ? "rgba(241, 245, 249, 0.075)"
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

                {/* ── LINHAS E LABELS OFICIAIS DO `magicwalls_tradingview.pine` + TRADUÇÃO DINÂMICA (Vai Defender / Violinada / Romperam / Virou) ── */}
                {(() => {
                    const hasBackendStruct = nearbyWalls.some((w) => w && (w.is_local_call_wall || w.is_local_put_wall));
                    const fallbackCallPrices = new Set();
                    const fallbackPutPrices = new Set();
                    const fallbackFlipPrices = new Set();
                    if (!hasBackendStruct) {
                        const wallOnly = nearbyWalls
                            .filter((w) => w && String(w.type || "") === "Wall")
                            .sort((a, b) => Number(a.price || 0) - Number(b.price || 0));
                        const getG = (w) => Number(w.gex_raw ?? w.gex ?? 0);
                        let bestCall = null;
                        let bestPut = null;
                        wallOnly.forEach((w) => {
                            const g = getG(w);
                            if (g > 0 && (!bestCall || g > getG(bestCall))) bestCall = w;
                            if (g < 0 && (!bestPut || g < getG(bestPut))) bestPut = w;
                        });
                        if (bestCall) fallbackCallPrices.add(Number(bestCall.price));
                        if (bestPut) fallbackPutPrices.add(Number(bestPut.price));
                        let bestPair = null;
                        let bestDist = Infinity;
                        const spotRef = Number(lastPrice || 0);
                        for (let j = 0; j < wallOnly.length - 1; j += 1) {
                            const gp = getG(wallOnly[j]);
                            const gc = getG(wallOnly[j + 1]);
                            if (gp * gc < 0) {
                                const midP = (Number(wallOnly[j].price) + Number(wallOnly[j + 1].price)) / 2;
                                const dist = spotRef > 0 ? Math.abs(midP - spotRef) : j;
                                if (dist < bestDist) {
                                    bestDist = dist;
                                    bestPair = gc > 0 ? wallOnly[j + 1] : wallOnly[j];
                                }
                            }
                        }
                        if (bestPair) fallbackFlipPrices.add(Number(bestPair.price));
                    }
                    return [...nearbyWalls]
                    .sort((a, b) => {
                        const aFlip = String(a.type || "") === "GammaFlip" || /flip/i.test(String(a.label || ""));
                        const bFlip = String(b.type || "") === "GammaFlip" || /flip/i.test(String(b.label || ""));
                        return Number(aFlip) - Number(bFlip);
                    })
                    .map((w, i) => {
                    const yW = toY1(w.price);
                    const wType = String(w.type || "Wall");
                    const isGammaFlip = wType === "GammaFlip" || /flip/i.test(String(w.label || ""));
                    const isMid = wType.toLowerCase().includes("mid") || String(w.label || "").toUpperCase() === "MIDLEWALL";
                    const isNeutral = w.smart_bias === "NEUTRAL" || Boolean(w.is_exhausted);
                    const isSell = w.smart_bias === "SELL";

                    const gexRaw = Number(w.gex_raw ?? w.gex ?? 0);
                    const gexSide = String(w.gex_side || (gexRaw > 0 ? "CALL" : (gexRaw < 0 ? "PUT" : "NEUTRAL")));
                    const isLocalCall = Boolean(w.is_local_call_wall) || (!hasBackendStruct && fallbackCallPrices.has(Number(w.price)));
                    const isLocalPut = Boolean(w.is_local_put_wall) || (!hasBackendStruct && fallbackPutPrices.has(Number(w.price)));
                    const isStrikeFlip = Boolean(w.is_strike_flip) || (!hasBackendStruct && fallbackFlipPrices.has(Number(w.price)));
                    const wWidth = Math.max(1, Math.min(3, Number(w.width || 1)));
                    const localTier = String(w.local_wall_tier || "");
                    const isPrimaryWall = !isMid && !isGammaFlip && (wWidth >= 3 || isLocalCall || isLocalPut || localTier === "PRIMARY");
                    const isSecondaryWall = !isMid && !isGammaFlip && !isPrimaryWall && (wWidth === 2 || isStrikeFlip || localTier === "SECONDARY");

                    const pineCol = isGammaFlip ? "#d4a259"
                        : wType === "MaxGamma" ? "#38bdf8"
                            : wType === "MinGamma" ? "#e5484d"
                                : isMid ? "#848da2" : "#eef0f5";
                    const polCol = isGammaFlip
                        ? "#d4a259"
                        : w.is_exhausted
                            ? "#848da2"
                            : isNeutral
                                ? pineCol
                                : (isSell ? "#e5484d" : "#4cc38a");
                    const wallsHostLineCol = isGammaFlip
                        ? "#d4a259"
                        : isMid
                            ? "rgba(238, 240, 245, 0.18)"
                            : isPrimaryWall
                                ? "rgba(238, 240, 245, 0.88)"
                                : isSecondaryWall
                                    ? "rgba(238, 240, 245, 0.50)"
                                    : "rgba(238, 240, 245, 0.24)";
                    const wallsHostTagCol = isGammaFlip
                        ? "#d4a259"
                        : isMid
                            ? "#9aa5b6"
                            : isPrimaryWall
                                ? "#ffffff"
                                : isSecondaryWall
                                    ? "#dce3ef"
                                    : "#9aa5b6";
                    const wallsHostTagBg = isGammaFlip ? "#211d17" : "#131720";
                    const wallsHostTagBorder = isGammaFlip
                        ? "rgba(212, 162, 89, 0.60)"
                        : isPrimaryWall
                            ? "rgba(238, 240, 245, 0.58)"
                            : isSecondaryWall
                                ? "rgba(238, 240, 245, 0.34)"
                                : "rgba(238, 240, 245, 0.16)";
                    const col = isWallsHost
                        ? wallsHostTagCol
                        : (wallColorMode === "PINE" ? pineCol : polCol);
                    const lineStrokeCol = isWallsHost
                        ? wallsHostLineCol
                        : col;
                    const textCol = (!isWallsHost && wallColorMode !== "PINE" && w.is_trap) ? "#fbbf24" : col;

                    const isStrong = w.smart_stage === "FORTE" && !w.is_exhausted;
                    const strokeW = isGammaFlip
                        ? 2.0
                        : isMid
                            ? 0.85
                            : isWallsHost
                                ? (isPrimaryWall ? 2.4 : (isSecondaryWall ? 1.55 : 0.85))
                                : Math.max(1.2, Math.min(3.0, wWidth * (isStrong ? 0.95 : 0.85)));
                    const isDashed = !isGammaFlip && (w.style === "dashed" || isMid || Boolean(w.is_exhausted));
                    const hideRightAxisTag = Math.abs(yW - lastY) < 15 || yW > p1Bot - 20;

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
                        : (instD > 0 ? "#4cc38a" : (instD < 0 ? "#e5484d" : col));

                    const shortTag = isMid ? "Mid" : (wType === "Wall" ? "MW" : wType);
                    const pVerdictRaw = stripUiEmoji(w.player_verdict);
                    const pVerdict = isWallsHost && pVerdictRaw && !/aguardando toque/i.test(pVerdictRaw)
                        ? pVerdictRaw
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
                        ? `Agr:${fmtShortK(instAggrW)} Pas:${fmtShortK(instPassW)} · Var:${fmtShortK(retDeltaW)} · HFT:${fmtShortK(hftDeltaW)} · RLP:${fmtShortK(rlpDeltaW)}`
                        : "";
                    const profit4PlayerHoverExtra = isWallsHost && profit4PlayerSub
                        ? ` (Giro bruto: HFT ${Math.round(hftChurnW)}% | RLP ${Math.round(rlpShareW)}%)`
                        : "";
                    const belowLineDeltaText = profit4PlayerSub
                        ? (hideRightAxisTag ? `${fmtNum(w.price, dec)} · ${profit4PlayerSub}` : profit4PlayerSub)
                        : hasDeltaInfo
                            ? (hideRightAxisTag ? `${fmtNum(w.price, dec)} · ${deltaShort}${dirArrow}` : `${deltaShort}${dirArrow}`)
                            : (hideRightAxisTag ? `${fmtNum(w.price, dec)}` : "");
                    const topBrokersTitle = isWallsHost && Array.isArray(w.top_wall_brokers) && w.top_wall_brokers.length > 0
                        ? ` | Top Players na Wall: ${w.top_wall_brokers.map(tb => `${tb.broker} (${tb.net >= 0 ? "+" : ""}${Math.round(tb.net)})`).join(", ")}`
                        : "";

                    const gexTitleStr = w.gex_formatted ? ` (${w.gex_formatted})` : "";
                    const structTitle = isLocalCall
                        ? `CallWall Dominante${gexTitleStr}`
                        : isLocalPut
                            ? `PutWall Dominante${gexTitleStr}`
                            : isStrikeFlip
                                ? `Virada Put→Call${gexTitleStr}`
                                : `${w.label || wType}${gexTitleStr}`;
                    const wallsHostOpacity = isGammaFlip
                        ? "0.96"
                        : isMid
                            ? "0.55"
                            : isPrimaryWall
                                ? "0.95"
                                : isSecondaryWall
                                    ? "0.85"
                                    : "0.72";

                    return (
                        <g key={`pine-wall-${i}`}>
                            <title>{`${structTitle} @ ${fmtNum(w.price, dec)}`}</title>
                            {isWallsHost && (isLocalCall || isLocalPut) && (
                                <line
                                    x1={padL}
                                    y1={yW}
                                    x2={padL + plotW}
                                    y2={yW}
                                    stroke="rgba(241, 245, 249, 0.5)"
                                    strokeWidth="6"
                                    opacity="0.12"
                                />
                            )}
                            <line
                                x1={padL}
                                y1={yW}
                                x2={padL + plotW}
                                y2={yW}
                                stroke={lineStrokeCol}
                                strokeWidth={strokeW}
                                strokeDasharray={isDashed ? "4,4" : "none"}
                                opacity={isWallsHost ? "1" : (isGammaFlip ? "0.94" : isNeutral ? (isMid ? "0.45" : "0.68") : (isMid ? "0.80" : "0.95"))}
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
                                    {(!isMid || isGammaFlip) ? (
                                        <rect
                                            x={padL + plotW + 4}
                                            y={yW - 8}
                                            width={padR - 8}
                                            height={16}
                                            rx="4"
                                            fill={isWallsHost ? wallsHostTagBg : (isGammaFlip ? "#211d17" : "#131720")}
                                            stroke={isWallsHost ? wallsHostTagBorder : (isGammaFlip ? "rgba(212, 162, 89, 0.55)" : "rgba(238, 240, 245, 0.24)")}
                                            strokeWidth={(isWallsHost && isPrimaryWall) ? "1.3" : "1"}
                                        />
                                    ) : (
                                        <line
                                            x1={padL + plotW}
                                            y1={yW}
                                            x2={padL + plotW + 4}
                                            y2={yW}
                                            stroke="rgba(238, 240, 245, 0.28)"
                                            strokeWidth="1"
                                        />
                                    )}
                                    <text
                                        x={padL + plotW + 4 + (padR - 8) / 2}
                                        y={yW + 3.5}
                                        textAnchor="middle"
                                        fill={isWallsHost ? wallsHostTagCol : (isGammaFlip ? "#d4a259" : isMid ? "#9aa5b6" : "#eef0f5")}
                                        fontSize={isNarrow ? "9.5" : "10"}
                                        fontWeight={(isGammaFlip || (isWallsHost && (isPrimaryWall || isLocalCall || isLocalPut || isStrikeFlip))) ? "700" : (isWallsHost && isSecondaryWall ? "600" : "500")}
                                        fontFamily="var(--mono)"
                                    >
                                        {fmtNum(w.price, dec)}
                                    </text>
                                </g>
                            )}
                        </g>
                    );
                });
                })()}

                {/* Divisória Vertical indicando o início do Pregão de Hoje */}
                {firstTodayLocalIdx > 0 && (
                    <g>
                        <line
                            x1={toX(firstTodayLocalIdx) - stepX * 0.45}
                            y1={p1Top}
                            x2={toX(firstTodayLocalIdx) - stepX * 0.45}
                            y2={p3Bot}
                            stroke="#38bdf8"
                            strokeWidth="1.2"
                            strokeDasharray="4,3"
                            strokeOpacity="0.7"
                        />
                        <rect
                            x={toX(firstTodayLocalIdx) - stepX * 0.45 + 3}
                            y={p1Top + 4}
                            width={68}
                            height={13}
                            rx="3"
                            fill="#0c131e"
                            stroke="rgba(56, 189, 248, 0.6)"
                            strokeWidth="1"
                        />
                        <text
                            x={toX(firstTodayLocalIdx) - stepX * 0.45 + 7}
                            y={p1Top + 13}
                            fill="#7dd3fc"
                            fontSize="7.5"
                            fontWeight="bold"
                            fontFamily="var(--mono)"
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
                                        stroke="#d4a259"
                                        strokeWidth="1.0"
                                        strokeDasharray="4,3"
                                        strokeOpacity="0.55"
                                    />
                                )}
                                {!isWallsHost && flowSubMode === "JANELA_ASG" && yZeroWave >= flowPlotTop && yZeroWave <= flowPlotBot && (
                                    <circle cx={xStart} cy={yZeroWave} r="2.6" fill="#d4a259" stroke="#0e1118" strokeWidth="0.8" opacity="0.9" />
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
                                fill={isWallsHost ? "#848da2" : "#4cc38a"}
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
                            ? (isBullCandle ? "#4cc38a" : "#e5484d")
                            : (cState > 0 ? "#4cc38a" : cState < 0 ? "#e5484d" : "#848da2"));
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
                            ? "#d4a259"
                            : (isBreak
                                ? (isBuyDir ? "#38bdf8" : "#e5484d")
                                : (isBuyDir ? "#4cc38a" : "#e5484d"));

                        const yH = toY1(pt.high || pt.close);
                        const yL = toY1(pt.low || pt.close);
                        const rawBadgeY = isBuyDir
                            ? Math.min(p1Bot - 13, Math.max(yWall + 4, yL + 3))
                            : Math.max(p1Top + 3, Math.min(yWall - 15, yH - 14));

                        const txt = mk.label || "Defendeu";
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
                    const lastNweCol = isWallsHost ? "#7dd3fc" : (lastNweUp ? "#4cc38a" : "#e5484d");
                    const rawNweY = lastNwe > 0 ? Math.max(p1Top + 10, Math.min(p1Bot - 10, toY1(lastNwe))) : null;
                    const badgeNweY = rawNweY !== null
                        ? (Math.abs(rawNweY - lastY) < 19 ? (rawNweY < lastY ? Math.max(p1Top + 10, lastY - 20) : Math.min(p1Bot - 10, lastY + 20)) : rawNweY)
                        : null;

                    const envUpPts = [];
                    const envLoPts = [];
                    if (isWallsHost) {
                        segments.forEach((seg, sIdx) => {
                            if (seg.yU1 !== null && seg.yL1 !== null && sIdx === 0) {
                                envUpPts.push(`${seg.x1.toFixed(1)},${seg.yU1.toFixed(1)}`);
                                envLoPts.unshift(`${seg.x1.toFixed(1)},${seg.yL1.toFixed(1)}`);
                            }
                            if (seg.yU2 !== null && seg.yL2 !== null) {
                                envUpPts.push(`${seg.x2.toFixed(1)},${seg.yU2.toFixed(1)}`);
                                envLoPts.unshift(`${seg.x2.toFixed(1)},${seg.yL2.toFixed(1)}`);
                            }
                        });
                    }

                    return (
                        <g pointerEvents="none">
                            {isWallsHost && envUpPts.length > 2 && (
                                <polygon points={`${envUpPts.join(" ")} ${envLoPts.join(" ")}`} fill="rgba(56, 189, 248, 0.045)" />
                            )}
                            {segments.map(seg => {
                                const col = isWallsHost ? "rgba(56, 189, 248, 0.45)" : (seg.isUp ? "#4cc38a" : "#e5484d");
                                const bandCol = isWallsHost ? "rgba(125, 211, 252, 0.22)" : col;
                                return (
                                    <g key={seg.key}>
                                        {seg.yU1 !== null && seg.yU2 !== null && (
                                            <line
                                                x1={seg.x1}
                                                y1={seg.yU1}
                                                x2={seg.x2}
                                                y2={seg.yU2}
                                                stroke={bandCol}
                                                strokeWidth={isWallsHost ? "1" : "1.4"}
                                                strokeLinecap="round"
                                            />
                                        )}
                                        <line
                                            x1={seg.x1}
                                            y1={seg.yC1}
                                            x2={seg.x2}
                                            y2={seg.yC2}
                                            stroke={col}
                                            strokeWidth={isWallsHost ? "1.15" : "1.7"}
                                            strokeDasharray={isWallsHost ? "2,3" : "none"}
                                            strokeLinecap="round"
                                        />
                                        {seg.yL1 !== null && seg.yL2 !== null && (
                                            <line
                                                x1={seg.x1}
                                                y1={seg.yL1}
                                                x2={seg.x2}
                                                y2={seg.yL2}
                                                stroke={bandCol}
                                                strokeWidth={isWallsHost ? "1" : "1.4"}
                                                strokeLinecap="round"
                                            />
                                        )}
                                    </g>
                                );
                            })}
                            {rawNweY !== null && badgeNweY !== null && (
                                <g>
                                    <rect
                                        x={padL + plotW + 4}
                                        y={badgeNweY - 8.5}
                                        width={padR - 8}
                                        height={17}
                                        rx="4"
                                        fill="#131720"
                                        stroke={isWallsHost ? "rgba(56, 189, 248, 0.38)" : lastNweCol}
                                        strokeWidth="1"
                                    />
                                    <text
                                        x={padL + plotW + 4 + (padR - 8) / 2}
                                        y={badgeNweY + 3.5}
                                        textAnchor="middle"
                                        fill={lastNweCol}
                                        fontSize={isNarrow ? "9.5" : "10"}
                                        fontWeight="500"
                                        fontFamily="var(--mono)"
                                    >
                                        G {fmtNum(lastNwe, dec)}
                                    </text>
                                </g>
                            )}
                        </g>
                    );
                })()}

                {/* ── AVWAP AUTOMÁTICA NAS DIVERGÊNCIAS DE EXTREMO DO DIA (AZUL-GELO DISCRETO) ── */}
                {showAvwap && avwapCurves.length > 0 && (() => {
                    const visIdxByOrigIdx = new Map();
                    series.forEach((pt, vi) => visIdxByOrigIdx.set(pt._origIdx, vi));

                    const occupiedAxisYs = [lastY];
                    if (showNweLine) {
                        const lastNweV = getNweLine(lastPt);
                        if (lastNweV > 0) {
                            const rawNwe = Math.max(p1Top + 10, Math.min(p1Bot - 10, toY1(lastNweV)));
                            const adjNwe = Math.abs(rawNwe - lastY) < 19
                                ? (rawNwe < lastY ? Math.max(p1Top + 10, lastY - 20) : Math.min(p1Bot - 10, lastY + 20))
                                : rawNwe;
                            occupiedAxisYs.push(adjNwe);
                        }
                    }

                    return (
                        <g>
                            {avwapCurves.map((c) => {
                                const visPts = [];
                                c.pts.forEach((p) => {
                                    const vi = visIdxByOrigIdx.get(p.origIdx);
                                    if (vi !== undefined) {
                                        visPts.push({ x: toX(vi), y: toY1(p.price), price: p.price });
                                    }
                                });
                                if (visPts.length === 0) return null;

                                const hasAnchorVis = visIdxByOrigIdx.has(c.pts[0].origIdx);
                                const hasEndVis = visIdxByOrigIdx.has(c.lastOrigIdx);
                                const polyStr = visPts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
                                const extName = c.isBull ? "mínima" : "máxima";
                                const dirName = c.isBull ? "Compra" : "Venda";
                                const tip = c.invalidated
                                    ? `AVWAP ${dirName} (#${c.num} · ${extName} ${c.anchorTime} @ ${fmtNum(c.anchorPx, dec)}) · Encerrada às ${c.breakTime} (extremo rompido)`
                                    : `AVWAP ${dirName} (#${c.num} · ${extName} ${c.anchorTime} @ ${fmtNum(c.anchorPx, dec)}) · Atual: ${fmtNum(c.lastPrice, dec)}`;

                                const lastVis = visPts[visPts.length - 1];
                                const rawTagY = toY1(c.lastPrice);
                                const canShowAxisPill = !c.invalidated && visPts.length >= 2 && hasEndVis
                                    && rawTagY >= p1Top + 10 && rawTagY <= p1Bot - 22
                                    && !occupiedAxisYs.some((oy) => Math.abs(oy - rawTagY) < 18);
                                if (canShowAxisPill) occupiedAxisYs.push(rawTagY);

                                const showInlineFallback = !c.invalidated && visPts.length >= 2 && hasEndVis && !canShowAxisPill
                                    && lastVis.y >= p1Top + 14 && lastVis.y <= p1Bot - 14;
                                const inlineY = Math.max(p1Top + 10, Math.min(p1Bot - 6, c.isBull ? lastVis.y - 5 : lastVis.y + 10));

                                return (
                                    <g key={c.id}>
                                        <g clipPath={`url(#clip-p1-plot-${symKey})`}>
                                            {visPts.length >= 2 && !c.invalidated && (
                                                <>
                                                    <polyline
                                                        points={polyStr}
                                                        fill="none"
                                                        stroke="#38bdf8"
                                                        strokeWidth="4.2"
                                                        strokeOpacity="0.14"
                                                        strokeLinejoin="round"
                                                        strokeLinecap="round"
                                                        pointerEvents="none"
                                                    />
                                                    <polyline
                                                        points={polyStr}
                                                        fill="none"
                                                        stroke="#7dd3fc"
                                                        strokeWidth="1.6"
                                                        strokeOpacity="0.86"
                                                        strokeLinejoin="round"
                                                        strokeLinecap="round"
                                                        pointerEvents="none"
                                                    />
                                                    <polyline points={polyStr} fill="none" stroke="transparent" strokeWidth="10">
                                                        <title>{tip}</title>
                                                    </polyline>
                                                </>
                                            )}
                                            {visPts.length >= 2 && c.invalidated && (
                                                <>
                                                    <polyline
                                                        points={polyStr}
                                                        fill="none"
                                                        stroke="rgba(125, 211, 252, 0.40)"
                                                        strokeWidth="1.15"
                                                        strokeDasharray="3,2.5"
                                                        strokeLinejoin="round"
                                                        strokeLinecap="round"
                                                        pointerEvents="none"
                                                    />
                                                    {hasEndVis && (
                                                        <circle
                                                            cx={lastVis.x}
                                                            cy={lastVis.y}
                                                            r="2.0"
                                                            fill="rgba(125, 211, 252, 0.55)"
                                                            pointerEvents="none"
                                                        />
                                                    )}
                                                    <polyline points={polyStr} fill="none" stroke="transparent" strokeWidth="10">
                                                        <title>{tip}</title>
                                                    </polyline>
                                                </>
                                            )}
                                            {hasAnchorVis && (
                                                <circle
                                                    cx={visPts[0].x}
                                                    cy={visPts[0].y}
                                                    r={c.invalidated ? "2.0" : "2.6"}
                                                    fill="#0e1118"
                                                    stroke={c.invalidated ? "rgba(125, 211, 252, 0.50)" : "#7dd3fc"}
                                                    strokeWidth="1.35"
                                                    pointerEvents="none"
                                                />
                                            )}
                                            {showInlineFallback && (
                                                <text
                                                    x={Math.min(padL + plotW - 6, lastVis.x - 2)}
                                                    y={inlineY}
                                                    textAnchor="end"
                                                    fill="#7dd3fc"
                                                    fontSize="8.5"
                                                    fontWeight="600"
                                                    fontFamily="var(--mono)"
                                                    opacity="0.88"
                                                    pointerEvents="none"
                                                >
                                                    AV {fmtNum(c.lastPrice, dec)}
                                                </text>
                                            )}
                                        </g>
                                        {canShowAxisPill && (
                                            <g pointerEvents="none">
                                                <rect
                                                    x={padL + plotW + 4}
                                                    y={rawTagY - 8.5}
                                                    width={padR - 8}
                                                    height={17}
                                                    rx="4"
                                                    fill="#101824"
                                                    stroke="rgba(125, 211, 252, 0.45)"
                                                    strokeWidth="1"
                                                />
                                                <text
                                                    x={padL + plotW + 4 + (padR - 8) / 2}
                                                    y={rawTagY + 3.5}
                                                    textAnchor="middle"
                                                    fill="#7dd3fc"
                                                    fontSize={isNarrow ? "9.5" : "10"}
                                                    fontWeight="500"
                                                    fontFamily="var(--mono)"
                                                >
                                                    AV {fmtNum(c.lastPrice, dec)}
                                                </text>
                                            </g>
                                        )}
                                    </g>
                                );
                            })}
                        </g>
                    );
                })()}

                {/* ── SINAIS NUMERADOS (1, 2, 3...) ESTILO CARD IG + LINHAS DE DIVERGÊNCIA OPCIONAIS / NO HOVER ── */}
                {isWallsFlowLocalhost() && showSwingDivLines && (() => {
                    const linesToShow = showDivLines
                        ? swingDivergences
                        : activeFocusDivId
                            ? swingDivergences.filter((dv) => dv.divId === activeFocusDivId)
                            : [];
                    const markerRadius = isNarrow ? 9 : 10;
                    const divMarkers = computeChartDivMarkers(swingDivergences, {
                        toX,
                        toY: toY1,
                        series,
                        plotTop: p1Top + 4,
                        plotBot: p1Bot - 4,
                        plotLeft: padL + 2,
                        plotRight: padL + plotW - 2,
                        radius: markerRadius,
                    });

                    return (
                        <g>
                            {/* Linhas diagonais F1->F2 / T1->T2: somente quando "Linhas div." está ativo ou no sinal focado */}
                            {linesToShow.map((dv, dIdx) => {
                                if (dv.currIdx <= dv.prevIdx) return null;
                                const isBull = dv.type === "BULL_DIV";
                                const x1 = toX(dv.prevIdx);
                                const x2 = toX(dv.currIdx);
                                const y1 = Math.max(p1Top + 10, Math.min(p1Bot - 10, toY1(dv.prevPrice)));
                                const y2 = Math.max(p1Top + 10, Math.min(p1Bot - 10, toY1(dv.currPrice)));
                                const col = dv.isPendingTrigger ? "#38bdf8" : (isBull ? "#4cc38a" : "#e5484d");
                                return (
                                    <g key={`p1-div-line-${dv.divId || dIdx}`} pointerEvents="none">
                                        <line
                                            x1={x1}
                                            y1={y1}
                                            x2={x2}
                                            y2={y2}
                                            stroke={col}
                                            strokeWidth="1.5"
                                            strokeDasharray="3,2"
                                        />
                                        {!dv.prevOffLeft && (
                                            <circle cx={x1} cy={y1} r="2.5" fill="#0e1118" stroke={col} strokeWidth="1.5" />
                                        )}
                                        <circle cx={x2} cy={y2} r="3" fill={col} />
                                    </g>
                                );
                            })}

                            {/* Círculos numerados cronológicos anticolisão (1, 2, 3...) */}
                            {divMarkers.map(({ dv, isBull, candleX, candleY, badgeX, badgeY }) => {
                                const col = dv.isPendingTrigger ? "#38bdf8" : (isBull ? "#4cc38a" : "#e5484d");
                                const bgFill = isBull ? "#10231b" : "#261316";
                                const isFocused = activeFocusDivId === dv.divId;
                                const isDimmed = Boolean(activeFocusDivId && !isFocused);
                                const tipStr = `#${dv.num} · ${isBull ? "Compra" : "Venda"} (${dv.anchorCode}) às ${dv.currTime} · Preço ${fmtNum(dv.currPrice, dec)} · ${dv.driver || ""}`;
                                return (
                                    <g
                                        key={`p1-div-mk-${dv.divId}`}
                                        data-div-id={dv.divId}
                                        style={{ cursor: "pointer", opacity: isDimmed ? 0.4 : 1 }}
                                        onMouseEnter={() => setHoveredDivId(dv.divId)}
                                        onMouseLeave={() => setHoveredDivId((cur) => (cur === dv.divId ? null : cur))}
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setSelectedDivId((cur) => (cur === dv.divId ? null : dv.divId));
                                        }}
                                    >
                                        <title>{tipStr}</title>
                                        <line
                                            x1={candleX}
                                            y1={badgeY}
                                            x2={candleX}
                                            y2={p1Bot}
                                            stroke={col}
                                            strokeWidth="1"
                                            strokeDasharray="2,3"
                                            strokeOpacity={isFocused ? "0.55" : "0.22"}
                                        />
                                        <line
                                            x1={candleX}
                                            y1={candleY}
                                            x2={badgeX}
                                            y2={badgeY}
                                            stroke={col}
                                            strokeWidth="1.25"
                                            strokeOpacity="0.82"
                                        />
                                        <circle cx={candleX} cy={candleY} r="2.5" fill={col} stroke="#0e1118" strokeWidth="1" />
                                        {isFocused && (
                                            <circle cx={badgeX} cy={badgeY} r={markerRadius + 3} fill="none" stroke="#eef0f5" strokeWidth="1.25" />
                                        )}
                                        <circle cx={badgeX} cy={badgeY} r={markerRadius} fill={bgFill} stroke={col} strokeWidth="1.5" />
                                        <text
                                            x={badgeX}
                                            y={badgeY + 3.5}
                                            textAnchor="middle"
                                            fill="#eef0f5"
                                            fontSize={isNarrow ? "9.5" : "10.5"}
                                            fontWeight="600"
                                            fontFamily="var(--mono)"
                                        >
                                            {dv.num}
                                        </text>
                                    </g>
                                );
                            })}
                        </g>
                    );
                })()}

                {/* Linha de Preço Spot Atual + Badge Oficial na Escala Direita (#38bdf8) */}
                <g>
                    <line x1={padL} y1={lastY} x2={padL + plotW} y2={lastY} stroke="rgba(56, 189, 248, 0.42)" strokeWidth="1" strokeDasharray="2,3" />
                    <rect x={padL + plotW + 4} y={Math.max(p1Top + 2, Math.min(p1Bot - 19, lastY - 9))} width={padR - 8} height={18} rx="4" fill="#38bdf8" />
                    <text x={padL + plotW + 4 + (padR - 8) / 2} y={Math.max(p1Top + 14.5, Math.min(p1Bot - 6.5, lastY + 3.5))} textAnchor="middle" fill="#070a10" fontSize={isNarrow ? "9.5" : "10.5"} fontWeight="600" fontFamily="var(--mono)">
                        {fmtNum(lastPt.close, dec)}
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
                        WIN_DIV_WALL: "WIN Sniper · 2L Mix",
                        WDO_DIV_WALL: "WDO Sniper · 1L",
                        ESP_DIV_V22_WIN: "WIN Especialista · 2L",
                        C1a_BRK_WIN: "WIN Brk Conv C1a · 1L",
                        V1a_DIV_WDO: "WDO Div V3.2 V1a · 1L",
                        SYM_DIV_WIN: "WIN Simétrica · 1L",
                        SYM_DIV_WDO: "WDO Simétrica · 1L",
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
                        WIN_DIV_WALL: "#4cc38a",
                        WDO_DIV_WALL: "#d4a259",
                        ESP_DIV_V22_WIN: "#a78bfa",
                        C1a_BRK_WIN: "#38bdf8",
                        V1a_DIV_WDO: "#e09153",
                        SYM_DIV_WIN: "#2dd4bf",
                        SYM_DIV_WDO: "#f472b6",
                        EST_01: "#38bdf8",
                        EST_04: "#38bdf8",
                        EST_07: "#60a5fa",
                        EST_13: "#34d399",
                        EST_14: "#4cc38a",
                        EST_15: "#2dd4bf",
                        EST_16: "#818cf8",
                        WIN_E2: "#a78bfa",
                        WDO_02: "#d4a259",
                        WDO_07: "#e09153",
                        WDO_09: "#f59e0b",
                        WDO_10: "#fb923c",
                        WDO_11: "#d4a259",
                        WDO_S2: "#e09153",
                    };
                    const tagLabel = shortMap[sid] || sig.strategy_short || sid || (isBuy ? "Compra" : "Venda");
                    const stratCol = colorMap[sid] || (isBuy ? "#4cc38a" : "#e5484d");
                    const col = isBuy ? "#4cc38a" : "#e5484d";
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
                        ? "aberta"
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
                                fill={isPAuto ? "rgba(56, 189, 248, 0.2)" : "#0c131e"}
                                stroke={isPAuto ? "#38bdf8" : "#334155"}
                                strokeWidth="0.9"
                            />
                            <text
                                x={width - 13}
                                y={p1Bot - 6.8}
                                fill={isPAuto ? "#7dd3fc" : "#64748b"}
                                fontSize="8"
                                fontWeight="bold"
                                fontFamily="var(--mono)"
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
                                {/* Linha Azul Limpa do Fluxo Smart Money */}
                                <polyline
                                    fill="none"
                                    stroke="#38bdf8"
                                    strokeWidth="1.8"
                                    strokeLinejoin="round"
                                    strokeLinecap="round"
                                    points={wavePts}
                                />

                                {/* Divergências no Fluxo: linhas com anticolisão quando "Linhas div." ativo ou sinal focado */}
                                {(() => {
                                    const flowLinesToShow = showDivLines
                                        ? swingDivergences
                                        : activeFocusDivId
                                            ? swingDivergences.filter((dv) => dv.divId === activeFocusDivId)
                                            : [];
                                    const placedBoxes = [];
                                    return flowLinesToShow.map((dv, dIdx) => {
                                        if (dv.currIdx <= dv.prevIdx) return null;
                                        const isBull = dv.type === "BULL_DIV";
                                        const x1 = toX(dv.prevIdx);
                                        const x2 = toX(dv.currIdx);
                                        const y1 = toYSwingWave(dv.prevWave);
                                        const y2 = toYSwingWave(dv.currWave);
                                        const col = dv.isPendingTrigger ? "#38bdf8" : (isBull ? "#4cc38a" : "#e5484d");
                                        const deltaW = Number(dv.currWave || 0) - Number(dv.prevWave || 0);
                                        const lbl = isNarrow
                                            ? `#${dv.num} ${isBull ? "F1→F2" : "T1→T2"}`
                                            : `#${dv.num} ${isBull ? "F1→F2" : "T1→T2"} (${fmtW(deltaW)})`;
                                        const lblW = lbl.length * 6.0 + 8;
                                        const lx = Math.max(padL + lblW / 2 + 2, Math.min(padL + plotW - lblW / 2 - 4, (x1 + x2) / 2));
                                        let ly = isBull
                                            ? Math.min(p3Bot - 6, Math.max(y1, y2) + 12)
                                            : Math.max(p3Top + 26, Math.min(y1, y2) - 7);
                                        const stepDir = isBull ? -13 : 13;
                                        for (let tries = 0; tries < 5; tries += 1) {
                                            const hit = placedBoxes.some((b) => Math.abs(b.y - ly) < 12 && lx - lblW / 2 < b.x2 + 4 && lx + lblW / 2 > b.x1 - 4);
                                            if (!hit) break;
                                            ly += stepDir;
                                            if (ly < p3Top + 26) ly = p3Bot - 6;
                                            if (ly > p3Bot - 5) ly = p3Top + 26;
                                        }
                                        placedBoxes.push({ x1: lx - lblW / 2, x2: lx + lblW / 2, y: ly });

                                        return (
                                            <g key={`p2-div-line-${dv.divId || dIdx}`} pointerEvents="none">
                                                <line x1={x2} y1={p3Top + 15} x2={x2} y2={y2} stroke={col} strokeWidth="0.9" strokeDasharray="2,3" opacity="0.45" />
                                                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={col} strokeWidth="1.5" />
                                                {!dv.prevOffLeft && <circle cx={x1} cy={y1} r="2.4" fill="#0e1118" stroke={col} strokeWidth="1.4" />}
                                                <circle cx={x2} cy={y2} r="3" fill={col} />
                                                <rect x={lx - lblW / 2} y={ly - 9} width={lblW} height={12} rx="3" fill="rgba(14, 17, 24, 0.90)" />
                                                <text x={lx} y={ly} fill={col} fontSize="9.5" fontWeight="500" fontFamily="var(--mono)" textAnchor="middle">
                                                    {lbl}
                                                </text>
                                            </g>
                                        );
                                    });
                                })()}

                                {/* Marcadores #1, #2, #3... sincronizados na curva de Fluxo (padrão limpo sem linhas sobrepostas) */}
                                {showSwingDivLines && !showDivLines && (() => {
                                    const placedPins = [];
                                    return swingDivergences.map((dv) => {
                                        const isBull = dv.type === "BULL_DIV";
                                        const cx = toX(dv.currIdx);
                                        const fy = toYSwingWave(dv.currWave);
                                        const col = dv.isPendingTrigger ? "#38bdf8" : (isBull ? "#4cc38a" : "#e5484d");
                                        const bgFill = isBull ? "#10231b" : "#261316";
                                        const isFocused = activeFocusDivId === dv.divId;
                                        const isDimmed = Boolean(activeFocusDivId && !isFocused);
                                        let ty = isBull ? Math.min(p3Bot - 9, fy + 14) : Math.max(p3Top + 24, fy - 14);
                                        let tx = cx;
                                        for (let tries = 0; tries < 5; tries += 1) {
                                            const hit = placedPins.some((p) => Math.abs(p.x - tx) < 24 && Math.abs(p.y - ty) < 16);
                                            if (!hit) break;
                                            if (tries < 2) {
                                                ty += isBull ? 16 : -16;
                                                if (ty > p3Bot - 9) ty = Math.max(p3Top + 24, fy - 16);
                                                if (ty < p3Top + 24) ty = Math.min(p3Bot - 9, fy + 16);
                                            } else {
                                                tx = Math.max(padL + 12, Math.min(padL + plotW - 12, cx + (tries % 2 === 0 ? 18 : -18)));
                                            }
                                        }
                                        placedPins.push({ x: tx, y: ty });
                                        return (
                                            <g
                                                key={`p2-div-pin-${dv.divId}`}
                                                data-div-id={dv.divId}
                                                style={{ cursor: "pointer", opacity: isDimmed ? 0.4 : 1 }}
                                                onMouseEnter={() => setHoveredDivId(dv.divId)}
                                                onMouseLeave={() => setHoveredDivId((cur) => (cur === dv.divId ? null : cur))}
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setSelectedDivId((cur) => (cur === dv.divId ? null : dv.divId));
                                                }}
                                            >
                                                <line x1={cx} y1={p3Top + 15} x2={cx} y2={fy} stroke={col} strokeWidth="1" strokeDasharray="2,3" strokeOpacity={isFocused ? "0.55" : "0.22"} />
                                                <circle cx={cx} cy={fy} r={isFocused ? "3.5" : "2.5"} fill={col} />
                                                {!isFocused && (
                                                    <>
                                                        <rect x={tx - 10} y={ty - 7.5} width={20} height={14} rx="4" fill={bgFill} stroke={col} strokeOpacity="0.72" strokeWidth="1" />
                                                        <text x={tx} y={ty + 3} textAnchor="middle" fill="#eef0f5" fontSize="9.5" fontWeight="600" fontFamily="var(--mono)">
                                                            #{dv.num}
                                                        </text>
                                                    </>
                                                )}
                                            </g>
                                        );
                                    });
                                })()}

                                {/* Badge do Valor Atual da Onda na Escala Direita */}
                                {(() => {
                                    const clampedTagY = Math.max(flowPlotTop + 8, Math.min(flowPlotBot - 8, lastWaveY));
                                    return (
                                        <g>
                                            <line x1={lastX} y1={clampedTagY} x2={padL + plotW} y2={clampedTagY} stroke="rgba(56, 189, 248, 0.42)" strokeWidth="1" strokeDasharray="2,3" />
                                            <rect x={padL + plotW + 4} y={clampedTagY - 8.5} width={padR - 8} height={17} rx="4" fill="#131720" stroke="rgba(56, 189, 248, 0.48)" strokeWidth="1" />
                                            <text x={padL + plotW + 4 + (padR - 8) / 2} y={clampedTagY + 3.5} textAnchor="middle" fill="#38bdf8" fontSize={isNarrow ? "9.5" : "10"} fontWeight="500" fontFamily="var(--mono)">
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
                                    fill={isFAuto ? "rgba(56, 189, 248, 0.2)" : "#0c131e"}
                                    stroke={isFAuto ? "#38bdf8" : "#334155"}
                                    strokeWidth="0.9"
                                />
                                <text
                                    x={width - 13}
                                    y={p3Bot - 6.8}
                                    fill={isFAuto ? "#7dd3fc" : "#64748b"}
                                    fontSize="8"
                                    fontWeight="bold"
                                    fontFamily="var(--mono)"
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
                        <text x={padL + plotW + 5} y={p3Top + 25} fill="#4cc38a" fontSize="7.5" fontFamily="IBM Plex Mono, monospace">
                            +{fmtNum(maxCaboVal, 0)}L
                        </text>
                        <text x={padL + plotW + 5} y={p3Bot - 5} fill="#e5484d" fontSize="7.5" fontFamily="IBM Plex Mono, monospace">
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
                                    <title>{`${series[sb.idx]?.time} | Inst Agressor: ${fmtNum(ia, 0, true)}L | Inst Passivo: ${fmtNum(ip, 0, true)}L | Varejo: ${fmtNum(ret, 0, true)}L | ${sb.divLabel}`}</title>
                                    {/* Camada 1: Agressão Institucional (Verde / Vermelho) */}
                                    {iaH >= 0.8 && (
                                        <rect
                                            x={x - candleW * 0.48}
                                            y={iaY}
                                            width={candleW * 0.96}
                                            height={Math.max(1.2, iaH)}
                                            fill={ia >= 0 ? "#4cc38a" : "#e5484d"}
                                            opacity="0.88"
                                            rx="0.5"
                                        />
                                    )}
                                    {/* Camada 2: Absorção Passiva Institucional na Pedra (Azul / Âmbar) */}
                                    {ipH >= 0.8 && (
                                        <rect
                                            x={x - candleW * 0.48}
                                            y={ipY}
                                            width={candleW * 0.96}
                                            height={Math.max(1.2, ipH)}
                                            fill={ip >= 0 ? "#38bdf8" : "#d4a259"}
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
                            {/* Curva Fluxo Não-Varejo (Ink Azul Green) */}
                            <polyline fill="none" stroke="#4cc38a" strokeWidth="2.2" points={nrPts} />

                            {/* Etiquetas na escala direita */}
                            <text x={padL + plotW + 5} y={Math.max(p3Top + 22, Math.min(p3Bot - 6, toYOscNr(lastSb.nrOsc || 0)))} fill="#4cc38a" fontSize="8" fontWeight="600" fontFamily="'IBM Plex Mono', monospace">
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
                            <polyline fill="none" stroke="#d4a259" strokeWidth="1.25" strokeDasharray="2,2" opacity="0.85" points={ptsRlp} />
                            <polyline fill="none" stroke="#a78bfa" strokeWidth="1.35" strokeDasharray="3,2" opacity="0.88" points={ptsHft} />
                            <polyline fill="none" stroke="#e09153" strokeWidth="1.45" strokeDasharray="4,2" opacity="0.90" points={ptsRet} />
                            <polyline fill="none" stroke="#38bdf8" strokeWidth="1.85" points={ptsIp} />
                            <polyline fill="none" stroke="#4cc38a" strokeWidth="2.15" points={ptsIa} />

                            <text x={padL + plotW + 4} y={p3Top + 25} fill="#4cc38a" fontSize="7.5" fontWeight="600" fontFamily="IBM Plex Mono, monospace">
                                Agr {fmtK(lastSb.cvdIa)}
                            </text>
                            <text x={padL + plotW + 4} y={p3Top + 39} fill="#38bdf8" fontSize="7.5" fontWeight="600" fontFamily="IBM Plex Mono, monospace">
                                Pas {fmtK(lastSb.cvdIp)}
                            </text>
                            <text x={padL + plotW + 4} y={p3Top + 53} fill="#e09153" fontSize="7.5" fontFamily="IBM Plex Mono, monospace">
                                Var {fmtK(lastSb.cvdRet)}
                            </text>
                            <text x={padL + plotW + 4} y={p3Top + 67} fill="#a78bfa" fontSize="7.5" fontFamily="IBM Plex Mono, monospace">
                                HFT {fmtK(lastSb.cvdHft)}
                            </text>
                            <text x={padL + plotW + 4} y={p3Top + 81} fill="#d4a259" fontSize="7.5" fontFamily="IBM Plex Mono, monospace">
                                RLP {fmtK(lastSb.cvdRlp)}
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
                                    const col = isPos ? "#4cc38a" : "#e5484d";
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

                                {/* Camada 2: Linha Azul de Fluxo Smart Money */}
                                {showLineWave && subPanelBars.length >= 2 && (
                                    <g>
                                        {smWinVisualMode === "HIST_LINE" && (
                                            <polyline
                                                fill="none"
                                                stroke="#0a0c12"
                                                strokeWidth="3.4"
                                                strokeLinejoin="round"
                                                strokeLinecap="round"
                                                points={wavePts}
                                                opacity="0.80"
                                            />
                                        )}
                                        <polyline
                                            fill="none"
                                            stroke="#38bdf8"
                                            strokeWidth="2.15"
                                            strokeLinejoin="round"
                                            strokeLinecap="round"
                                            points={wavePts}
                                            opacity="0.96"
                                        />
                                    </g>
                                )}

                                {/* Badge do valor atual na escala direita */}
                                {subPanelBars.length > 0 && (() => {
                                    const clampedTagY = Math.max(flowPlotTop + 7, Math.min(flowPlotBot - 7, lastWaveY));
                                    return (
                                        <g>
                                            <line x1={lastX} y1={clampedTagY} x2={padL + plotW} y2={clampedTagY} stroke="#38bdf8" strokeWidth="0.85" strokeDasharray="2,3" opacity="0.65" />
                                            <rect x={padL + plotW + 2} y={clampedTagY - 7.5} width={padR - 26} height={15} rx="3" fill="rgba(56, 189, 248, 0.14)" stroke="#38bdf8" strokeWidth="0.9" />
                                            <text x={padL + plotW + 6} y={clampedTagY + 3} fill="#7dd3fc" fontSize="8.2" fontWeight="600" fontFamily="IBM Plex Mono, monospace">
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
                                    fill={isFAuto ? "rgba(56, 189, 248, 0.2)" : "#0c131e"}
                                    stroke={isFAuto ? "#38bdf8" : "#334155"}
                                    strokeWidth="0.9"
                                />
                                <text
                                    x={width - 13}
                                    y={p3Bot - 6.8}
                                    fill={isFAuto ? "#7dd3fc" : "#64748b"}
                                    fontSize="8"
                                    fontWeight="bold"
                                    fontFamily="var(--mono)"
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

                {/* ── CROSSHAIR INTERATIVO INK AZUL ── */}
                {hoverPos && series[hoverPos.idx] && (
                    <g pointerEvents="none">
                        <line
                            x1={toX(hoverPos.idx)}
                            y1={p1Top}
                            x2={toX(hoverPos.idx)}
                            y2={p3Bot}
                            stroke="rgba(238, 240, 245, 0.30)"
                            strokeWidth="1"
                            strokeDasharray="3,3"
                        />
                        <rect
                            x={toX(hoverPos.idx) - 24}
                            y={p3Bot + 3}
                            width={48}
                            height={17}
                            rx="4"
                            fill="#1b212e"
                            stroke="rgba(56, 189, 248, 0.38)"
                            strokeWidth="1"
                        />
                        <text
                            x={toX(hoverPos.idx)}
                            y={p3Bot + 15}
                            textAnchor="middle"
                            fill="#eef0f5"
                            fontSize="10"
                            fontWeight="500"
                            fontFamily="var(--mono)"
                        >
                            {series[hoverPos.idx]?.time}
                        </text>

                        {hoverPos.relY >= p1Top && hoverPos.relY <= p1Bot && (
                            <>
                                <line
                                    x1={padL}
                                    y1={hoverPos.relY}
                                    x2={padL + plotW}
                                    y2={hoverPos.relY}
                                    stroke="rgba(238, 240, 245, 0.24)"
                                    strokeWidth="1"
                                    strokeDasharray="3,3"
                                />
                                <rect
                                    x={padL + plotW + 4}
                                    y={hoverPos.relY - 8.5}
                                    width={padR - 8}
                                    height={17}
                                    rx="4"
                                    fill="#1b212e"
                                    stroke="rgba(56, 189, 248, 0.38)"
                                    strokeWidth="1"
                                />
                                <text
                                    x={padL + plotW + 4 + (padR - 8) / 2}
                                    y={hoverPos.relY + 3.5}
                                    textAnchor="middle"
                                    fill="#eef0f5"
                                    fontSize={isNarrow ? "9.5" : "10"}
                                    fontWeight="500"
                                    fontFamily="var(--mono)"
                                >
                                    {fmtNum(fromY1(hoverPos.relY), dec)}
                                </text>
                            </>
                        )}
                        {(flowSubMode === "SWING_DIVERGENCIA" || (flowSubMode === "JANELA_ASG" && smWinVisualMode !== "HIST")) && hoverPos.relY >= flowPlotTop && hoverPos.relY <= flowPlotBot && (() => {
                            const wVal = fromYSwingWave(hoverPos.relY);
                            const absW = Math.abs(wVal);
                            const sgW = wVal >= 0 ? "+" : "−";
                            const crossLbl = absW >= 1000 ? `${sgW}${(absW / 1000).toFixed(1)}k` : `${sgW}${Math.round(absW)}`;
                            return (
                                <>
                                    <line
                                        x1={padL}
                                        y1={hoverPos.relY}
                                        x2={padL + plotW}
                                        y2={hoverPos.relY}
                                        stroke="rgba(238, 240, 245, 0.24)"
                                        strokeWidth="1"
                                        strokeDasharray="3,3"
                                    />
                                    <rect
                                        x={padL + plotW + 4}
                                        y={hoverPos.relY - 8.5}
                                        width={padR - 8}
                                        height={17}
                                        rx="4"
                                        fill="#1b212e"
                                        stroke="rgba(56, 189, 248, 0.38)"
                                        strokeWidth="1"
                                    />
                                    <text
                                        x={padL + plotW + 4 + (padR - 8) / 2}
                                        y={hoverPos.relY + 3.5}
                                        textAnchor="middle"
                                        fill="#eef0f5"
                                        fontSize={isNarrow ? "9.5" : "10"}
                                        fontWeight="500"
                                        fontFamily="var(--mono)"
                                    >
                                        {crossLbl}
                                    </text>
                                </>
                            );
                        })()}
                    </g>
                )}
            </svg>
            {canUseMediaStudio && showInstaModal && (() => {
                const modalEngineList =
                    (engineDivs.scopeKey === engineScopeKey && Array.isArray(engineDivs.list) && engineDivs.list.length > 0)
                        ? engineDivs.list
                        : (precomputedV32 || []);
                return (
                <InstagramCardModal
                    isOpen={showInstaModal}
                    onClose={() => setShowInstaModal(false)}
                    symKey={symKey}
                    sessionDate={sessionDate}
                    bars={engineBars.length ? engineBars : series.filter((pt) => pt && !pt.is_prev_day)}
                    walls={allWalls}
                    divergences={
                        isWallsHost && Array.isArray(modalEngineList) && modalEngineList.length > 0
                            ? modalEngineList.map((d) => ({
                                type: d.dir === 1 ? "BULL_DIV" : "BEAR_DIV",
                                prevTime: d.f1_time,
                                prevPrice: Number(d.f1_px),
                                prevWave: Number(d.f1_wave),
                                currTime: d.f2_time,
                                currPrice: Number(d.f2_px),
                                currWave: Number(d.f2_wave),
                                confTime: d.conf_time,
                                triggerTime: d.trigger_time,
                                triggerKind: d.trigger_kind,
                                nearWall: String(d.anchor || "").includes("WALL"),
                                anchor: d.anchor,
                                isPendingTrigger: false,
                            }))
                            : swingDivergences
                    }
                />
                );
            })()}
            {canUseMediaStudio && showMorningVideoModal && (
                <MorningWallsVideoModal
                    isOpen={showMorningVideoModal}
                    onClose={() => setShowMorningVideoModal(false)}
                    selectedDate=""
                    compassData={compassData}
                />
            )}
        </div>
    );
}

/* ══════════════════════════════════════════════════════════════════════════════
   2. BARRA COMPACTA DE RESUMO DO DIA (SEM REDUNDÂNCIAS DE VELA 3D / ALVOS 1-2-3)
   ══════════════════════════════════════════════════════════════════════════════ */
function AsgCockpitHud({ symKey, payload, asgHud = {}, scorecard = {}, onToggleHistory, showHistory, onCollapseDrawer }) {
    const winDir = Number(asgHud.window_dir || 0);
    const makersPct = Number(asgHud.makers_pct || 0);
    const winCol = winDir >= 0 ? "var(--mw-pos)" : "var(--mw-neg)";
    const isWallsHost = isWallsFlowLocalhost();
    const tot = payload?.session_totals || {};
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
        <div
            className="mw-card"
            style={{
                display: "flex",
                flexDirection: "column",
                gap: 10,
                padding: "12px 14px",
                borderLeft: `2px solid ${winCol}`,
            }}
        >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span className="mw-mono" style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        fontSize: 11.5,
                        fontWeight: 500,
                        color: "var(--mw-text-1)",
                        background: "var(--mw-raised)",
                        padding: "2px 8px",
                        borderRadius: 6,
                        border: "1px solid var(--mw-hairline)",
                    }}>
                        <span style={{ width: 6, height: 6, borderRadius: 999, background: winCol, display: "inline-block" }} />
                        {winDir >= 0 ? "Janela comprada" : "Janela vendida"} · {asgHud.window_start_time || "09:00"}
                    </span>
                    <span className="mw-mono" style={{
                        fontSize: 11.5,
                        fontWeight: 500,
                        color: makersPct >= 0 ? "var(--mw-pos)" : "var(--mw-neg)",
                    }}>
                        Makers {makersPct >= 0 ? "+" : ""}{fmtNum(makersPct, 1)}%
                    </span>
                </div>
                {onCollapseDrawer && (
                    <button
                        type="button"
                        className="mw-btn mw-btn-secondary"
                        onClick={onCollapseDrawer}
                        title="Recuar painel lateral para ampliar o gráfico"
                        style={{ height: 24, padding: "0 8px", fontSize: 11 }}
                    >
                        Recuar ›
                    </button>
                )}
            </div>

            {isWallsHost && (
                <div style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    background: "var(--mw-bg)",
                    border: "1px solid var(--mw-hairline)",
                    borderRadius: 8,
                    padding: "8px 10px",
                }}>
                    <div className="mw-mono" style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 6, fontSize: 11 }}>
                        <div style={{ background: "var(--mw-card)", padding: "6px 8px", borderRadius: 6, border: "1px solid var(--mw-hairline)" }}>
                            <div style={{ color: "var(--mw-text-3)", fontSize: 10 }}>Inst (Agr / Pas)</div>
                            <div style={{ fontWeight: 500, color: sessInstAggr >= 0 ? "var(--mw-pos)" : "var(--mw-neg)", whiteSpace: "nowrap" }}>
                                {fmtNum(sessInstAggr, 0, true)}L <span style={{ color: "var(--mw-text-3)" }}>/</span> <span style={{ color: sessInstPass >= 0 ? "var(--mw-pos)" : "var(--mw-neg)" }}>{fmtNum(sessInstPass, 0, true)}L</span>
                            </div>
                        </div>
                        <div style={{ background: "var(--mw-card)", padding: "6px 8px", borderRadius: 6, border: "1px solid var(--mw-hairline)" }}>
                            <div style={{ color: "var(--mw-text-3)", fontSize: 10 }}>Varejo puro</div>
                            <div style={{ fontWeight: 500, color: "var(--mw-text-1)", whiteSpace: "nowrap" }}>
                                {fmtNum(sessRetDelta, 0, true)}L
                            </div>
                        </div>
                        <div style={{ background: "var(--mw-card)", padding: "6px 8px", borderRadius: 6, border: "1px solid var(--mw-hairline)" }} title={`Giro bruto HFT: ${fmtNum(sessHftChurn, 1)}% do volume`}>
                            <div style={{ color: "var(--mw-text-3)", fontSize: 10 }}>HFT (saldo)</div>
                            <div style={{ fontWeight: 500, color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>
                                {fmtNum(sessHftDelta, 0, true)}L <span style={{ color: "var(--mw-text-3)", fontSize: 10 }}>({fmtNum(sessHftChurn, 0)}%)</span>
                            </div>
                        </div>
                        <div style={{ background: "var(--mw-card)", padding: "6px 8px", borderRadius: 6, border: "1px solid var(--mw-hairline)" }} title={`Participação RLP: ${fmtNum(sessRlpPct, 1)}% do volume`}>
                            <div style={{ color: "var(--mw-text-3)", fontSize: 10 }}>RLP (saldo)</div>
                            <div style={{ fontWeight: 500, color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>
                                {fmtNum(sessRlpDelta, 0, true)}L <span style={{ color: "var(--mw-text-3)", fontSize: 10 }}>({fmtNum(sessRlpPct, 0)}%)</span>
                            </div>
                        </div>
                    </div>

                    <div className="mw-mono" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, flexWrap: "wrap", fontSize: 10.5, borderTop: "1px solid var(--mw-hairline)", paddingTop: 6, color: "var(--mw-text-3)" }}>
                        {symKey === "WIN" ? (
                            <>
                                <span><strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>WIN 2L Mix:</strong> L1 NWE30 · L2 750p</span>
                                <span>SL 240/260p · BE +180→+20p</span>
                            </>
                        ) : (
                            <>
                                <span><strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>WDO 1L:</strong> TP MidWall GEX</span>
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
                gap: 8,
                flexWrap: "wrap",
                borderTop: "1px solid var(--mw-hairline)",
                paddingTop: 8,
            }}>
                <div className="mw-mono" style={{ fontSize: 11.5, color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>
                    Assertividade{" "}
                    <strong style={{ color: "var(--mw-pos)", fontWeight: 600 }}>
                        {fmtNum(scorecard.win_rate_pct, 0)}%
                    </strong>{" "}
                    <span style={{ color: "var(--mw-text-3)" }}>
                        ({scorecard.valid_signals || 0}W / {scorecard.invalid_signals || 0}L)
                    </span>
                </div>
                <button
                    type="button"
                    className="mw-btn mw-btn-secondary"
                    onClick={onToggleHistory}
                    style={{ height: 26, padding: "0 10px", fontSize: 11 }}
                >
                    {showHistory ? "Ocultar tabela" : "Sinais do dia"}
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
    const curveColor = isNetPos ? "#4cc38a" : "#e5484d";
    const profitFactor = grossLossPts > 0 ? (grossGainPts / grossLossPts) : (grossGainPts > 0 ? 9.9 : 1.0);

    const w = 400;
    const h = 152;
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
        <div
            className="mw-card"
            style={{
                flex: 1,
                padding: "12px 14px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                gap: 10,
            }}
        >
            {/* Cabeçalho + Seletor de Contratos */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--mw-text-1)" }}>
                        Capital do dia · {symKey}
                    </span>
                    <span className="mw-mono" style={{
                        fontSize: 10,
                        color: "var(--mw-text-3)",
                        background: "var(--mw-bg)",
                        border: "1px solid var(--mw-hairline)",
                        padding: "1px 6px",
                        borderRadius: 4,
                    }}>
                        Barra fechada
                    </span>
                </div>
                <div className="mw-track">
                    {(isWallsFlowLocalhost()
                        ? [1, 2, 5]
                        : (symKey === "WDO" ? [1, 2, 5] : [1, 5, 10])
                    ).map(c => {
                        const btnLbl = isWallsFlowLocalhost()
                            ? (symKey === "WIN" ? `${c}x` : `${c}x`)
                            : `${c}c`;
                        return (
                            <button
                                key={c}
                                type="button"
                                className="mw-btn mw-mono"
                                data-active={contracts === c ? "true" : "false"}
                                onClick={() => setContracts(c)}
                                style={{ height: 24, padding: "0 7px", fontSize: 11 }}
                            >
                                {btnLbl}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Faixa de KPIs Financeiros do Dia */}
            <div style={{ display: "grid", gridTemplateColumns: "1.35fr 1fr 0.95fr", gap: 6 }}>
                <div style={{ background: "var(--mw-bg)", border: "1px solid var(--mw-hairline)", borderRadius: 6, padding: "6px 8px" }}>
                    <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>
                        Saldo ({isWallsFlowLocalhost() ? (symKey === "WIN" ? `${contracts * 2}L` : `${contracts}L`) : `${contracts}c`})
                    </div>
                    <div className="mw-mono" style={{ fontSize: 13.5, fontWeight: 600, color: curveColor, whiteSpace: "nowrap" }}>
                        {totalBrl >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(totalBrl), 0)}
                        <span style={{ fontSize: 10, color: "var(--mw-text-3)", fontWeight: 400, marginLeft: 4 }}>
                            ({fmtNum(cumPts, dec, true)}p)
                        </span>
                    </div>
                </div>
                <div style={{ background: "var(--mw-bg)", border: "1px solid var(--mw-hairline)", borderRadius: 6, padding: "6px 8px" }}>
                    <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>Fator lucro</div>
                    <div className="mw-mono" style={{ fontSize: 13, fontWeight: 600, color: profitFactor >= 1.5 ? "var(--mw-pos)" : "var(--mw-flip)", whiteSpace: "nowrap" }}>
                        {fmtNum(profitFactor, 2)}x
                        <span style={{ fontSize: 10, color: "var(--mw-text-3)", fontWeight: 400, marginLeft: 4 }}>
                            ({chronoSignals.length})
                        </span>
                    </div>
                </div>
                <div style={{ background: "var(--mw-bg)", border: "1px solid var(--mw-hairline)", borderRadius: 6, padding: "6px 8px" }}>
                    <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>DD máx</div>
                    <div className="mw-mono" style={{ fontSize: 13, fontWeight: 600, color: "var(--mw-neg)", whiteSpace: "nowrap" }}>
                        −R$ {fmtNum(maxDrawdownBrlDay, 0)}
                    </div>
                </div>
            </div>

            {/* Gráfico SVG da Curva de Capital Intraday */}
            <svg
                viewBox={`0 0 ${w} ${h}`}
                style={{ width: "100%", height: "auto", display: "block", background: "var(--mw-bg)", borderRadius: 8, border: "1px solid var(--mw-hairline)", cursor: "crosshair" }}
                onMouseLeave={() => setHoverTradeIdx(null)}
            >
                <defs>
                    <linearGradient id={`eq-grad-${symKey}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={curveColor} stopOpacity="0.22" />
                        <stop offset="100%" stopColor={curveColor} stopOpacity="0.01" />
                    </linearGradient>
                </defs>

                <line x1={padL} y1={yZero} x2={padL + plotW} y2={yZero} stroke="rgba(238,240,245,0.14)" strokeWidth="1" strokeDasharray="3,3" />
                <text x={padL + plotW + 4} y={yZero + 3} fill="#848da2" fontSize="8.5" fontFamily="var(--mono)">
                    R$ 0
                </text>

                <polygon points={areaPts} fill={`url(#eq-grad-${symKey})`} />
                <polyline fill="none" stroke={curveColor} strokeWidth="2" points={polyPts} />

                {equityPoints.map((pt, i) => {
                    const cx = toX(i);
                    const cy = toY(pt.cumBrl);
                    const isSel = pt.id && selectedSigId === pt.id;
                    const dotCol = i === 0 ? "#38bdf8" : pt.isOpen ? "#d4a259" : pt.isGain ? "#4cc38a" : "#e5484d";
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
                                stroke="#0e1118"
                                strokeWidth="1.2"
                            />
                        </g>
                    );
                })}

                {(() => {
                    const lastEq = equityPoints[equityPoints.length - 1];
                    const xLast = toX(equityPoints.length - 1);
                    const yLast = toY(lastEq.cumBrl);
                    return (
                        <g>
                            <line x1={xLast + 4} y1={yLast} x2={padL + plotW} y2={yLast} stroke={curveColor} strokeWidth="1" strokeDasharray="2,2" opacity="0.7" />
                            <rect x={padL + plotW + 2} y={yLast - 8} width={padR - 4} height={16} rx="4" fill="#131720" stroke={curveColor} strokeWidth="1" />
                            <text x={padL + plotW + 5} y={yLast + 3.5} fill={curveColor} fontSize="8.5" fontWeight="600" fontFamily="var(--mono)">
                                {lastEq.cumBrl >= 0 ? "+" : ""}{fmtNum(lastEq.cumBrl, 0)}
                            </text>
                        </g>
                    );
                })()}

                <text x={padL + 2} y={h - 4} fill="#848da2" fontSize="8.5" fontFamily="var(--mono)">09:00</text>
                {equityPoints.length > 2 && (
                    <text x={padL + plotW / 2 - 14} y={h - 4} fill="#848da2" fontSize="8.5" fontFamily="var(--mono)">
                        {equityPoints[Math.floor(equityPoints.length / 2)]?.time}
                    </text>
                )}
                <text x={padL + plotW - 26} y={h - 4} fill="#848da2" fontSize="8.5" fontFamily="var(--mono)">
                    {equityPoints[equityPoints.length - 1]?.time}
                </text>
            </svg>

            {/* Barra de Inspeção da Operação */}
            <div className="mw-mono" style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: 11,
                background: "var(--mw-bg)",
                padding: "6px 10px",
                borderRadius: 6,
                border: "1px solid var(--mw-hairline)",
                gap: 8,
            }}>
                <span style={{ color: "var(--mw-text-3)", whiteSpace: "nowrap" }}>
                    {inspected.time} · <strong style={{ fontWeight: 500, color: inspected.isOpen ? "var(--mw-flip)" : (inspected.isGain ? "var(--mw-pos)" : "var(--mw-neg)") }}>{inspected.dirLabel}</strong>
                </span>
                <span style={{ color: inspected.isOpen ? "var(--mw-flip)" : (inspected.tradeBrl >= 0 ? "var(--mw-pos)" : "var(--mw-neg)"), fontWeight: 600, whiteSpace: "nowrap" }}>
                    {inspected.isOpen
                        ? "Em aberto"
                        : `${inspected.tradeBrl >= 0 ? "+" : "−"}R$ ${fmtNum(Math.abs(inspected.tradeBrl), 0)} (${fmtNum(inspected.tradePts, dec, true)}p)`}
                </span>
            </div>

            {/* Lista Compacta das Operações do Dia */}
            <div style={{
                display: "flex",
                flexDirection: "column",
                gap: 4,
                maxHeight: 165,
                overflowY: "auto",
                borderTop: "1px solid var(--mw-hairline)",
                paddingTop: 8,
            }}>
                {signalsLog.length === 0 ? (
                    <div className="mw-mono" style={{ fontSize: 11, color: "var(--mw-text-3)", textAlign: "center", padding: "12px 0" }}>
                        Nenhuma operação encerrada ou aberta neste pregão.
                    </div>
                ) : (
                    signalsLog.map((sig) => {
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
                            WIN_DIV_WALL: "WIN Sniper · 2L",
                            WDO_DIV_WALL: "WDO Sniper · 1L",
                            ESP_DIV_V22_WIN: "WIN Especialista · 2L",
                            C1a_BRK_WIN: "WIN Brk C1a · 1L",
                            V1a_DIV_WDO: "WDO Div V1a · 1L",
                            SYM_DIV_WIN: "WIN Simétrica · 1L",
                            SYM_DIV_WDO: "WDO Simétrica · 1L",
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
                                className="mw-mono"
                                onClick={() => onSelectSignal && onSelectSignal(isSel ? null : sig.id)}
                                style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    fontSize: 10.5,
                                    padding: "5px 8px",
                                    borderRadius: 6,
                                    cursor: "pointer",
                                    background: isSel ? "var(--mw-accent-soft)" : "var(--mw-bg)",
                                    border: isSel ? "1px solid var(--mw-accent-border)" : "1px solid var(--mw-hairline)",
                                    gap: 8,
                                }}
                            >
                                <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0, overflow: "hidden", whiteSpace: "nowrap" }}>
                                    <span style={{ color: "var(--mw-text-2)", fontWeight: 500 }}>{sig.time}</span>
                                    <span style={{ color: isBuy ? "var(--mw-pos)" : "var(--mw-neg)", fontWeight: 600 }}>
                                        {isBuy ? "▲" : "▼"}
                                    </span>
                                    <span style={{ color: "var(--mw-text-1)", overflow: "hidden", textOverflow: "ellipsis" }}>{sName}</span>
                                    <span style={{ color: "var(--mw-text-3)" }}>@{fmtNum(sig.entry_price, dec)}</span>
                                </div>
                                <span style={{
                                    fontWeight: 600,
                                    whiteSpace: "nowrap",
                                    color: isOpen ? "var(--mw-flip)" : (pts >= 0 ? "var(--mw-pos)" : "var(--mw-neg)"),
                                }}>
                                    {isOpen ? "Aberto" : `${brl >= 0 ? "+" : "−"}R$ ${fmtNum(Math.abs(brl), 0)} (${pts >= 0 ? "+" : ""}${fmtNum(pts, dec)}p)`}
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
    const col = isPos ? "#4cc38a" : "#e5484d";
    const pf = lossBrl > 0 ? (gainBrl / lossBrl) : (gainBrl > 0 ? 9.9 : 1.0);

    const w = 900, h = 84, padL = 14, padR = 76, padT = 10, padB = 16;
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
        <div
            className="mw-card"
            style={{
                borderLeft: `2px solid ${col}`,
                padding: "14px 20px",
                display: "flex",
                flexDirection: "column",
                gap: 10,
            }}
        >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "var(--mw-text-1)" }}>
                        Carteira combinada do dia
                    </span>
                    <span className="mw-mono" style={{ fontSize: 12, color: "var(--mw-text-3)" }}>
                        {isWallsFlow
                            ? "Carteira 5176 · 7 estratégias (WIN + WDO)"
                            : "Portfólio Elite M5 · 5 WIN + 3 WDO"}
                    </span>
                </div>
                <div className="mw-mono" style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 12, flexWrap: "wrap" }}>
                    <span style={{ color: "var(--mw-text-3)" }}>
                        WIN ({isWallsFlow ? `${winContracts}x` : `${winContracts}c`}){" "}
                        <strong style={{ color: winBrl >= 0 ? "var(--mw-accent-ink)" : "var(--mw-neg)", fontWeight: 500 }}>
                            {winBrl >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(winBrl), 0)}
                        </strong>
                    </span>
                    <span style={{ color: "var(--mw-text-3)" }}>
                        WDO ({wdoContracts}c){" "}
                        <strong style={{ color: wdoBrl >= 0 ? "var(--mw-flip)" : "var(--mw-neg)", fontWeight: 500 }}>
                            {wdoBrl >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(wdoBrl), 0)}
                        </strong>
                    </span>
                    <span style={{
                        color: col,
                        fontSize: 13,
                        fontWeight: 600,
                        background: isPos ? "var(--mw-pos-bg)" : "var(--mw-neg-bg)",
                        padding: "4px 10px",
                        borderRadius: 6,
                        border: `1px solid ${isPos ? "rgba(76, 195, 138, 0.28)" : "rgba(229, 72, 77, 0.28)"}`,
                        whiteSpace: "nowrap",
                    }}>
                        {cumBrl >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(cumBrl), 0)}
                        <span style={{ color: "var(--mw-text-2)", fontWeight: 400, marginLeft: 8, fontSize: 11.5 }}>
                            {merged.length} ops · PF {fmtNum(pf, 2)}x · DD −R$ {fmtNum(maxDdBrl, 0)}
                        </span>
                    </span>
                </div>
            </div>
            <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "auto", display: "block", background: "var(--mw-bg)", borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                <line x1={padL} y1={yZero} x2={padL + plotW} y2={yZero} stroke="rgba(238,240,245,0.12)" strokeWidth="1" strokeDasharray="3,3" />
                <polygon points={area} fill={col} fillOpacity="0.12" />
                <polyline fill="none" stroke={col} strokeWidth="2" points={poly} />
                {eqPts.map((p, i) => (
                    <circle
                        key={`comb-pt-${i}`}
                        cx={toX(i)}
                        cy={toY(p.cumBrl)}
                        r={i === eqPts.length - 1 ? "3.8" : "2.8"}
                        fill={i === 0 ? "#848da2" : p.asset === "WIN" ? "#38bdf8" : "#d4a259"}
                        stroke="#0e1118"
                        strokeWidth="1"
                    >
                        <title>{`${p.time} · ${p.asset} (${p.type || "Início"}) → Acumulado: R$ ${fmtNum(p.cumBrl, 0)}`}</title>
                    </circle>
                ))}
                <text x={padL + plotW + 8} y={toY(cumBrl) + 3.5} fill={col} fontSize="10.5" fontWeight="600" fontFamily="var(--mono)">
                    {cumBrl >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(cumBrl), 0)}
                </text>
            </svg>
        </div>
    );
}

/* ── CURVA DE CAPITAL AUDITADA (MODO 5174 vs MODO 5176) ── */
const MT5_STRAT_META = [
    {
        id: "EST_04", asset: "WIN", code: "EST-04", shortLabel: "EST-04 Pullback", name: "EST-04 · WIN Pullback WDO", short: "EST-04",
        color: "#38bdf8", strokeW: 1.8, dec: 0,
        subRule: "TP MidWall · BE 2-Estágios Wall (15p→45p) · 15_NR_IGNITION_DIV",
    },
    {
        id: "EST_07", asset: "WIN", code: "EST-07", shortLabel: "EST-07 Rompimento", name: "EST-07 · WIN Ignição Wall", short: "EST-07",
        color: "#7dd3fc", strokeW: 1.8, dec: 0,
        subRule: "TP MidWall · BE Escudo Wall (15p) · NWE Dual Slope",
    },
    {
        id: "EST_13", asset: "WIN", code: "EST-13", shortLabel: "EST-13 Longa (35% B1)", name: "EST-13 · WIN SmartGrid Longa (TP 360p)", short: "EST-13",
        color: "#60a5fa", strokeW: 1.8, dec: 0,
        subRule: "Limite 35% B1 · TP Estendido 360p · NextWall 1+2L (BE 145p)",
    },
    {
        id: "EST_14", asset: "WIN", code: "EST-14", shortLabel: "EST-14 Média (50% B1)", name: "EST-14 · WIN SmartGrid Média (TP 280p)", short: "EST-14",
        color: "#4cc38a", strokeW: 1.8, dec: 0,
        subRule: "Limite 50% B1 · TP Intermediário 280p · NextWall 1+2L (BE 130p)",
    },
    {
        id: "EST_15", asset: "WIN", code: "EST-15", shortLabel: "EST-15 Curta (55% B1)", name: "EST-15 · WIN SmartGrid Curta (TP 210p)", short: "EST-15",
        color: "#2dd4bf", strokeW: 1.8, dec: 0,
        subRule: "Limite 55% B1 · TP Encurtado 210p · NextWall 1+2L (BE 110p)",
    },
    {
        id: "WDO_01", asset: "WDO", code: "WDO-01", shortLabel: "WDO-01 Curta NY", name: "WDO-01 · WDO Scalper Curto NY (TP 6–8p)", short: "WDO-01",
        color: "#d4a259", strokeW: 1.8, dec: 1,
        subRule: "TP Curto 6.0p–8.0p · SL 9.5p + BE Escudo Wall (1.0p)",
    },
    {
        id: "WDO_05", asset: "WDO", code: "WDO-05", shortLabel: "WDO-05 Média Limite", name: "WDO-05 · WDO Cluster Limit Wall (TP 7–9.5p)", short: "WDO-05",
        color: "#a78bfa", strokeW: 1.8, dec: 1,
        subRule: "Limite B1±0.5p · TP 7.0p–9.5p · SL 10.0p + BE Escudo Wall",
    },
    {
        id: "WDO_07", asset: "WDO", code: "WDO-07", shortLabel: "WDO-07 Longa NY", name: "WDO-07 · WDO Absorção Longa NY (TP 11p)", short: "WDO-07",
        color: "#f59e0b", strokeW: 1.8, dec: 1,
        subRule: "TP Estendido até 11.0p · SL 11.5p + BE Escudo Wall (1.0p)",
    },
];

const WALLS_FLOW_STRAT_META = [
    {
        id: "WIN_DIV_WALL", asset: "WIN", code: "WIN-2L-MIX", shortLabel: "WIN Sniper · 2c Mix", name: "WIN_DIV_WALL · WIN Sniper F1→F2 / T1→T2 · 2 Contratos Mix", short: "WIN 2c Mix",
        color: "#4cc38a", strokeW: 2.0, dec: 0,
        subRule: "Divergência até 2 barras antes · s/ 12h · Meta +R$ 180/dia · 2c (NWE30 + 750p)",
    },
    {
        id: "WDO_DIV_WALL", asset: "WDO", code: "WDO-1L-MID", shortLabel: "WDO Sniper · 1c MidWalls", name: "WDO_DIV_WALL · WDO Sniper F1→F2 / T1→T2 · 1 Contrato MidWall", short: "WDO 1c Mid",
        color: "#d4a259", strokeW: 2.0, dec: 1,
        subRule: "Divergência até 2 barras antes · s/ 11h NY/PTAX · Meta +R$ 120/dia · 1c",
    },
    {
        id: "ESP_DIV_V22_WIN", asset: "WIN", code: "WIN-ESP-V22", shortLabel: "WIN Especialista · 2c", name: "ESP_DIV_V22_WIN · WIN Especialista de Divergência · 2 Contratos", short: "WIN Esp. 2c",
        color: "#a78bfa", strokeW: 1.9, dec: 0,
        subRule: "Divergência na Wall ou extremo do dia · 10:00–15:55 · SL 200 · BE 180→20 · 60 min",
    },
    {
        id: "C1a_BRK_WIN", asset: "WIN", code: "WIN-C1A-BRK", shortLabel: "WIN Brk Conv C1a · 1c", name: "C1a_BRK_WIN · WIN Rompimento Convergente BRK_F1F2 · 1 Contrato", short: "WIN Brk C1a",
        color: "#38bdf8", strokeW: 1.9, dec: 0,
        subRule: "BRK_F1F2 convergência k1w2 · cruzando Wall · s/ 11h · SL 280 / TP 280 / 24b",
    },
    {
        id: "V1a_DIV_WDO", asset: "WDO", code: "WDO-V1A-DIV", shortLabel: "WDO Div V3.2 V1a · 1c", name: "V1a_DIV_WDO · WDO Divergência V3.2 Wall ProxWall · 1 Contrato", short: "WDO V1a",
        color: "#fb923c", strokeW: 1.9, dec: 1,
        subRule: "Divergência V3.2 Wall z=3,5 · CONF · s/ 11h · SL 14 / ProxWall [4..22] / 24b",
    },
    {
        id: "SYM_DIV_WIN", asset: "WIN", code: "WIN-SYM-V32", shortLabel: "WIN Simétrica · 1c", name: "SYM_DIV_WIN · WIN Simétrica SYM_TOP1 V3.2 · 1 Contrato", short: "WIN Sym",
        color: "#2dd4bf", strokeW: 1.8, dec: 0,
        subRule: "Simétrica V3.2 Wall · CONF · seq≤1 · s/ 11h · SL 280 / TP 240 / 24b",
    },
    {
        id: "SYM_DIV_WDO", asset: "WDO", code: "WDO-SYM-V32", shortLabel: "WDO Simétrica · 1c", name: "SYM_DIV_WDO · WDO Simétrica SYM_TOP1 V3.2 ProxWall · 1 Contrato", short: "WDO Sym",
        color: "#f472b6", strokeW: 1.8, dec: 1,
        subRule: "Simétrica V3.2 Wall · CONF · seq≤1 · s/ 11h · SL 14 / ProxWall [3,5..20] / 18b",
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
                shortLabel: `Portfólio (${effectivePortIds.length} ativas)`,
                title: `Portfólio combinado (${effectivePortIds.length} estratégias ativas)`,
                subRule: `WIN (${isWallsFlow ? 2 * winContracts : winContracts}L) + WDO (${wdoContracts}L) · ${_posMonthsCount}/${_totalMonthsCount} meses positivos · Ret/DD ${fmtNum(_portRetDd, 2)}x`,
                color: "#4cc38a",
                strokeW: 2.6,
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

    // Anti-colisão vertical para rótulos finais à direita do gráfico SVG
    const rightEndLabels = (() => {
        const lastPt = visibleSeries[nPts - 1];
        if (!lastPt) return [];
        const items = curveConfigs
            .filter((cfg) => visibleCurves[cfg.key])
            .map((cfg) => {
                const rawVal = Number(lastPt[cfg.key] || 0);
                const yRaw = toYEq(rawVal);
                return { cfg, rawVal, yRaw, yLabel: yRaw };
            })
            .sort((a, b) => a.yRaw - b.yRaw);
        const minGap = 13;
        const yMin = padT + 9;
        const yMax = padT + plotHEq - 4;
        for (let i = 1; i < items.length; i++) {
            if (items[i].yLabel - items[i - 1].yLabel < minGap) {
                items[i].yLabel = items[i - 1].yLabel + minGap;
            }
        }
        if (items.length > 0 && items[items.length - 1].yLabel > yMax) {
            const overflow = items[items.length - 1].yLabel - yMax;
            items[items.length - 1].yLabel -= overflow;
            for (let i = items.length - 2; i >= 0; i--) {
                if (items[i + 1].yLabel - items[i].yLabel < minGap) {
                    items[i].yLabel = items[i + 1].yLabel - minGap;
                }
            }
        }
        items.forEach((it) => {
            it.yLabel = Math.max(yMin, Math.min(yMax, it.yLabel));
        });
        return items;
    })();

    const isBasePreset = winContracts === 1 && wdoContracts === 1;
    const isScale2Preset = isWallsFlow
        ? (winContracts === 2 && wdoContracts === 2)
        : (winContracts === 2 && wdoContracts === 1);

    return (
        <section
            className="mw-card"
            style={{
                padding: "16px 18px",
                display: "flex",
                flexDirection: "column",
                gap: 14,
                marginTop: 4,
            }}
        >
            {/* 1. Cabeçalho + seletores de contratos e período */}
            <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                flexWrap: "wrap",
                gap: 12,
                borderBottom: "1px solid var(--mw-hairline)",
                paddingBottom: 12,
            }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 280, flex: "1 1 420px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 15, fontWeight: 600, color: "var(--mw-text-1)", letterSpacing: "-0.01em" }}>
                            {isWallsFlow
                                ? "Portfólio Sniper · Divergência de fluxo na Wall"
                                : "Portfólio Elite M5 · Fluxo sistemático"}
                        </span>
                        <span
                            className="mw-mono"
                            style={{
                                fontSize: 11,
                                fontWeight: 500,
                                color: "var(--mw-accent-ink)",
                                background: "var(--mw-accent-soft)",
                                border: "1px solid var(--mw-accent-border)",
                                padding: "2px 8px",
                                borderRadius: 6,
                                whiteSpace: "nowrap",
                            }}
                        >
                            WR {fmtNum(portWr, 1)}% · PF {fmtNum(portPf, 2)}x · Ret/DD {fmtNum(portRetDd, 2)}x
                        </span>
                        <span
                            className="mw-mono"
                            style={{
                                fontSize: 11,
                                fontWeight: 500,
                                color: "#4cc38a",
                                background: "rgba(76, 195, 138, 0.08)",
                                border: "1px solid rgba(76, 195, 138, 0.25)",
                                padding: "2px 8px",
                                borderRadius: 6,
                                whiteSpace: "nowrap",
                            }}
                        >
                            {portfolioData.total_bt_sessions || 123} pregões BT ({fmtDateShort(portfolioData.start_date)}–{fmtDateShort(portfolioData.last_bt_date)}) + Live ({fmtDateShort(portfolioData.live_start_date)}+)
                        </span>
                    </div>
                    <span className="mw-mono" style={{ fontSize: 11.5, color: "var(--mw-text-2)", lineHeight: 1.45 }}>
                        Carteira ({effectivePortIds.length} estratégias ativas):{" "}
                        <strong style={{ color: cPort >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 600, whiteSpace: "nowrap" }}>
                            {cPort >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(cPort), 0)}
                        </strong>{" "}
                        líquido B3 ·{" "}
                        <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{portOps} trades</strong> (~{fmtNum(portOps / Math.max(1, fullSeries.length - 1), 1)} ops/dia) ·{" "}
                        <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{posMonthsCount}/{totalMonthsCount} meses positivos</strong> · Max DD{" "}
                        <strong style={{ color: "#e5484d", fontWeight: 500, whiteSpace: "nowrap" }}>−R$ {fmtNum(mddPort, 0)}</strong>
                    </span>
                </div>

                {/* Controles de lote WIN / WDO e janela temporal */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <button
                        type="button"
                        className="mw-btn mw-btn-secondary mw-mono"
                        data-active={visibleCurves.PORTFOLIO ? "true" : "false"}
                        onClick={() => toggleCurve("PORTFOLIO")}
                        style={{
                            height: 28,
                            padding: "0 10px",
                            fontSize: 11,
                            color: visibleCurves.PORTFOLIO ? "#4cc38a" : "var(--mw-text-3)",
                            borderColor: visibleCurves.PORTFOLIO ? "rgba(76, 195, 138, 0.35)" : "var(--mw-hairline)",
                            background: visibleCurves.PORTFOLIO ? "rgba(76, 195, 138, 0.08)" : "var(--mw-chrome)",
                        }}
                    >
                        Curva portfólio ({visibleCurves.PORTFOLIO ? "ON" : "OFF"})
                    </button>

                    {/* Preset escala base */}
                    <div className="mw-track">
                        <button
                            type="button"
                            className="mw-btn mw-mono"
                            data-active={isBasePreset ? "true" : "false"}
                            onClick={() => { setWinContracts(1); setWdoContracts(1); }}
                            style={{ height: 24, padding: "0 9px", fontSize: 11 }}
                        >
                            {isWallsFlow ? "Base (2L WIN + 1L WDO)" : "Base 1 WIN : 1 WDO"}
                        </button>
                        <button
                            type="button"
                            className="mw-btn mw-mono"
                            data-active={isScale2Preset ? "true" : "false"}
                            onClick={() => isWallsFlow ? (setWinContracts(2), setWdoContracts(2)) : (setWinContracts(2), setWdoContracts(1))}
                            style={{ height: 24, padding: "0 9px", fontSize: 11 }}
                        >
                            {isWallsFlow ? "Escala 2x (4L + 2L)" : "2 WIN : 1 WDO"}
                        </button>
                    </div>

                    {/* Contratos WIN */}
                    <div className="mw-track" style={{ alignItems: "center", paddingLeft: 8 }}>
                        <span className="mw-mono" style={{ fontSize: 10.5, color: "#38bdf8", fontWeight: 600, marginRight: 2 }}>WIN</span>
                        {[1, 2, 4, 5, 10].map((c) => (
                            <button
                                key={`winc-${c}`}
                                type="button"
                                className="mw-btn mw-mono"
                                data-active={winContracts === c ? "true" : "false"}
                                onClick={() => setWinContracts(c)}
                                style={{ height: 24, padding: "0 7px", fontSize: 11 }}
                            >
                                {isWallsFlow ? `${c}x(${c * 2}L)` : `${c}c`}
                            </button>
                        ))}
                    </div>

                    {/* Contratos WDO */}
                    <div className="mw-track" style={{ alignItems: "center", paddingLeft: 8 }}>
                        <span className="mw-mono" style={{ fontSize: 10.5, color: "#d4a259", fontWeight: 600, marginRight: 2 }}>WDO</span>
                        {[1, 2, 5].map((c) => (
                            <button
                                key={`wdoc-${c}`}
                                type="button"
                                className="mw-btn mw-mono"
                                data-active={wdoContracts === c ? "true" : "false"}
                                onClick={() => setWdoContracts(c)}
                                style={{ height: 24, padding: "0 7px", fontSize: 11 }}
                            >
                                {isWallsFlow ? `${c}x(${c}L)` : `${c}c`}
                            </button>
                        ))}
                    </div>

                    {/* Período */}
                    <div className="mw-track">
                        {[
                            { id: "ALL", label: "Completo + Live" },
                            { id: "60D", label: "60d" },
                            { id: "30D", label: "30d" },
                        ].map((rm) => (
                            <button
                                key={rm.id}
                                type="button"
                                className="mw-btn mw-mono"
                                data-active={rangeMode === rm.id ? "true" : "false"}
                                onClick={() => { setRangeMode(rm.id); setHoverIdx(null); setPinnedIdx(null); }}
                                style={{ height: 24, padding: "0 8px", fontSize: 11 }}
                            >
                                {rm.label}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* 2. Scorecard interativo das estratégias (clique para ativar/desativar curva) */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                gap: 10,
            }}>
                {curveConfigs.filter((cfg) => cfg.key !== "PORTFOLIO").map((cfg) => {
                    const isOn = visibleCurves[cfg.key];
                    const k = cfg.kpi;
                    return (
                        <div
                            key={cfg.key}
                            onClick={() => toggleCurve(cfg.key)}
                            title="Clique para exibir ou ocultar esta curva no gráfico"
                            style={{
                                background: "var(--mw-chrome)",
                                border: "1px solid var(--mw-hairline)",
                                borderLeft: isOn ? `2px solid ${cfg.color}` : "2px solid transparent",
                                borderRadius: 8,
                                padding: "10px 12px",
                                cursor: "pointer",
                                opacity: isOn ? 1 : 0.45,
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                gap: 6,
                                transition: "opacity 120ms ease, border-color 120ms ease",
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                                <span style={{ fontSize: 12, fontWeight: 600, color: isOn ? cfg.color : "var(--mw-text-2)", letterSpacing: "-0.005em" }}>
                                    {cfg.shortLabel}
                                </span>
                                <span
                                    className="mw-mono"
                                    style={{
                                        fontSize: 10,
                                        fontWeight: 500,
                                        padding: "1px 6px",
                                        borderRadius: 4,
                                        background: isOn ? `${cfg.color}18` : "var(--mw-card)",
                                        color: isOn ? cfg.color : "var(--mw-text-3)",
                                        border: isOn ? `1px solid ${cfg.color}44` : "1px solid var(--mw-hairline)",
                                    }}
                                >
                                    {isOn ? "ON" : "OFF"}
                                </span>
                            </div>

                            <div className="mw-mono" style={{ fontSize: 16, fontWeight: 600, color: k.totBrl >= 0 ? "var(--mw-text-1)" : "#e5484d", whiteSpace: "nowrap" }}>
                                {k.totBrl >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(k.totBrl), 0)}
                                {k.totPts !== null && (
                                    <span style={{ fontSize: 11, color: "var(--mw-text-3)", fontWeight: 400, marginLeft: 6 }}>
                                        ({fmtNum(k.totPts, cfg.dec || 0, true)}p)
                                    </span>
                                )}
                            </div>

                            <div
                                className="mw-mono"
                                style={{
                                    display: "grid",
                                    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                                    gap: 4,
                                    fontSize: 11,
                                    borderTop: "1px solid var(--mw-hairline)",
                                    paddingTop: 6,
                                }}
                            >
                                <div>
                                    <div style={{ fontSize: 9.5, color: "var(--mw-text-3)" }}>WR ({k.ops})</div>
                                    <div style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(k.wr, 1)}%</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: 9.5, color: "var(--mw-text-3)" }}>PF</div>
                                    <div style={{ fontWeight: 500, color: k.pf >= 1.5 ? "#4cc38a" : "#d4a259" }}>{fmtNum(k.pf, 2)}x</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: 9.5, color: "var(--mw-text-3)" }}>Max DD</div>
                                    <div style={{ fontWeight: 500, color: "#e5484d", whiteSpace: "nowrap" }}>−R$ {fmtNum(k.maxDdBrl, 0)}</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: 9.5, color: "var(--mw-text-3)" }}>Ret/DD</div>
                                    <div style={{ fontWeight: 500, color: "#38bdf8" }}>{fmtNum(k.retDd, 2)}x</div>
                                </div>
                            </div>

                            <div style={{ fontSize: 10.5, color: "var(--mw-text-3)", lineHeight: 1.3 }}>
                                {cfg.subRule}
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* 3. Gráfico principal SVG (curvas de capital + marco live + drawdown subwater) */}
            <div style={{ position: "relative" }}>
                <svg
                    viewBox={`0 0 ${w} ${h}`}
                    style={{
                        width: "100%",
                        height: "auto",
                        display: "block",
                        background: "#0e1118",
                        borderRadius: 8,
                        border: "1px solid var(--mw-hairline)",
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
                            <stop offset="0%" stopColor="#4cc38a" stopOpacity="0.16" />
                            <stop offset="100%" stopColor="#4cc38a" stopOpacity="0.01" />
                        </linearGradient>
                        <linearGradient id="dd4-grad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#e5484d" stopOpacity="0.06" />
                            <stop offset="100%" stopColor="#e5484d" stopOpacity="0.28" />
                        </linearGradient>
                    </defs>

                    {/* Faixa de fundo do Live Trading */}
                    {firstLiveIdx > 0 && (() => {
                        const xLive = toX(firstLiveIdx) - Math.max(3, plotW / Math.max(20, nPts) * 0.45);
                        const badgeX = Math.min(padL + plotW - 118, Math.max(padL + 8, xLive - 116));
                        return (
                            <g>
                                <rect
                                    x={xLive}
                                    y={padT}
                                    width={Math.max(8, padL + plotW - xLive + 6)}
                                    height={plotHEq + plotHDd + 16}
                                    fill="rgba(76, 195, 138, 0.05)"
                                />
                                <line
                                    x1={xLive}
                                    y1={padT}
                                    x2={xLive}
                                    y2={ddTop + plotHDd}
                                    stroke="#4cc38a"
                                    strokeWidth="1.2"
                                    strokeDasharray="4,3"
                                />
                                <rect
                                    x={badgeX}
                                    y={padT + 2}
                                    width="112"
                                    height="16"
                                    rx="4"
                                    fill="#131720"
                                    stroke="rgba(76, 195, 138, 0.45)"
                                    strokeWidth="1"
                                />
                                <text
                                    x={badgeX + 56}
                                    y={padT + 13}
                                    fill="#4cc38a"
                                    fontSize="8.5"
                                    fontWeight="600"
                                    fontFamily="IBM Plex Mono, monospace"
                                    textAnchor="middle"
                                >
                                    Live · {fmtDateShort(portfolioData.live_start_date)}
                                </text>
                            </g>
                        );
                    })()}

                    {/* Linhas horizontais de grade (R$) */}
                    {yGridVals.map((yv, gi) => {
                        const yy = toYEq(yv);
                        return (
                            <g key={`yg-${gi}`}>
                                <line x1={padL} y1={yy} x2={padL + plotW} y2={yy} stroke="#171d29" strokeWidth="1" />
                                <text x={padL - 7} y={yy + 3} fill="#6b7489" fontSize="8.5" fontFamily="IBM Plex Mono, monospace" textAnchor="end">
                                    {yv >= 0 ? "+" : "−"}R${fmtNum(Math.abs(yv), 0)}
                                </text>
                            </g>
                        );
                    })}

                    {/* Linha zero (R$ 0) */}
                    <line x1={padL} y1={yZeroEq} x2={padL + plotW} y2={yZeroEq} stroke="#2a3346" strokeWidth="1" strokeDasharray="3,3" />

                    {/* Divisórias mensais */}
                    {monthTicks.map((mt, mi) => {
                        const xx = toX(mt.idx);
                        return (
                            <g key={`mt-${mi}`}>
                                <line x1={xx} y1={padT} x2={xx} y2={ddTop + plotHDd} stroke="#171d29" strokeWidth="1" strokeDasharray="2,3" />
                                <text x={xx + 4} y={hEq - 2} fill="#6b7489" fontSize="8" fontFamily="IBM Plex Mono, monospace" fontWeight="500">
                                    {mt.label}
                                </text>
                            </g>
                        );
                    })}

                    {/* Área sombreada do portfólio completo */}
                    {visibleCurves.PORTFOLIO && (() => {
                        const ptsStr = visibleSeries.map((pt, i) => `${toX(i).toFixed(1)},${toYEq(pt.PORTFOLIO).toFixed(1)}`).join(" ");
                        const areaStr = `${toX(0).toFixed(1)},${yZeroEq.toFixed(1)} ${ptsStr} ${toX(nPts - 1).toFixed(1)},${yZeroEq.toFixed(1)}`;
                        return <polygon points={areaStr} fill="url(#port4-grad)" />;
                    })()}

                    {/* Curvas de capital */}
                    {[...curveConfigs].reverse().map((cfg) => {
                        if (!visibleCurves[cfg.key]) return null;
                        const ptsStr = visibleSeries.map((pt, i) => `${toX(i).toFixed(1)},${toYEq(pt[cfg.key]).toFixed(1)}`).join(" ");
                        return (
                            <g key={`curve-${cfg.key}`}>
                                <polyline
                                    fill="none"
                                    stroke={cfg.color}
                                    strokeWidth={cfg.strokeW}
                                    points={ptsStr}
                                />
                                {visibleSeries.map((pt, i) => (
                                    pt.is_live ? (
                                        <circle
                                            key={`live-dot-${cfg.key}-${i}`}
                                            cx={toX(i)}
                                            cy={toYEq(pt[cfg.key])}
                                            r={cfg.key === "PORTFOLIO" ? "4" : "2.8"}
                                            fill={cfg.color}
                                            stroke="#0e1118"
                                            strokeWidth="1.2"
                                        />
                                    ) : null
                                ))}
                            </g>
                        );
                    })}

                    {/* Etiquetas de saldo final à direita com anti-colisão */}
                    {rightEndLabels.map(({ cfg, rawVal, yRaw, yLabel }) => (
                        <g key={`end-lbl-${cfg.key}`}>
                            {Math.abs(yLabel - yRaw) > 2.5 && (
                                <line
                                    x1={padL + plotW + 1}
                                    y1={yRaw}
                                    x2={padL + plotW + 6}
                                    y2={yLabel}
                                    stroke={cfg.color}
                                    strokeOpacity="0.45"
                                    strokeWidth="0.9"
                                />
                            )}
                            <text
                                x={padL + plotW + 8}
                                y={yLabel + 3}
                                fill={cfg.color}
                                fontSize={cfg.key === "PORTFOLIO" ? "9.5" : "8.2"}
                                fontWeight={cfg.key === "PORTFOLIO" ? "600" : "500"}
                                fontFamily="IBM Plex Mono, monospace"
                            >
                                {rawVal >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(rawVal), 0)}
                            </text>
                        </g>
                    ))}

                    {/* Separador do painel Subwater Drawdown */}
                    <line x1={padL} y1={ddTop} x2={padL + plotW} y2={ddTop} stroke="#1b212e" strokeWidth="1" />

                    {/* Curva Subwater Drawdown do Portfólio */}
                    {(() => {
                        const ddPts = visibleSeries.map((pt, i) => `${toX(i).toFixed(1)},${toYDd(pt.dd_PORT).toFixed(1)}`).join(" ");
                        const ddArea = `${toX(0).toFixed(1)},${ddTop.toFixed(1)} ${ddPts} ${toX(nPts - 1).toFixed(1)},${ddTop.toFixed(1)}`;
                        return (
                            <g>
                                <polygon points={ddArea} fill="url(#dd4-grad)" />
                                <polyline fill="none" stroke="#e5484d" strokeWidth="1.35" points={ddPts} />
                            </g>
                        );
                    })()}

                    {/* Rótulo do Drawdown em pílula opaca (não colide com a curva vermelha) */}
                    <g>
                        <rect
                            x={padL + 5}
                            y={ddTop + 4}
                            width="222"
                            height="15"
                            rx="3"
                            fill="#0e1118"
                            fillOpacity="0.92"
                            stroke="#1b212e"
                            strokeWidth="0.8"
                        />
                        <text x={padL + 11} y={ddTop + 14} fill="#8b94a7" fontSize="8" fontFamily="IBM Plex Mono, monospace" fontWeight="500">
                            Drawdown subwater · máx −R$ {fmtNum(mddPort, 0)}
                        </text>
                    </g>

                    {/* Crosshair do pregão selecionado / hover */}
                    {inspectedPt && (() => {
                        const ix = toX(visibleSeries.indexOf(inspectedPt));
                        return (
                            <g>
                                <line x1={ix} y1={padT} x2={ix} y2={ddTop + plotHDd} stroke="#8b94a7" strokeWidth="1" strokeDasharray="2,2" />
                                {curveConfigs.map((cfg) => (
                                    visibleCurves[cfg.key] ? (
                                        <circle
                                            key={`hov-${cfg.key}`}
                                            cx={ix}
                                            cy={toYEq(inspectedPt[cfg.key])}
                                            r="3.6"
                                            fill={cfg.color}
                                            stroke="#0e1118"
                                            strokeWidth="1.2"
                                        />
                                    ) : null
                                ))}
                            </g>
                        );
                    })()}
                </svg>

                {/* Barra de inspeção do pregão sob o cursor */}
                {inspectedPt && (
                    <div
                        className="mw-mono"
                        style={{
                            marginTop: 8,
                            background: "var(--mw-chrome)",
                            border: inspectedPt.is_live ? "1px solid rgba(76, 195, 138, 0.35)" : "1px solid var(--mw-hairline)",
                            borderRadius: 8,
                            padding: "8px 12px",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            flexWrap: "wrap",
                            gap: 10,
                            fontSize: 11,
                        }}
                    >
                        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                            <span style={{
                                fontWeight: 600,
                                color: inspectedPt.is_live ? "#4cc38a" : "var(--mw-text-1)",
                                background: inspectedPt.is_live ? "rgba(76, 195, 138, 0.10)" : "var(--mw-card)",
                                padding: "2px 8px",
                                borderRadius: 5,
                                border: inspectedPt.is_live ? "1px solid rgba(76, 195, 138, 0.30)" : "1px solid var(--mw-hairline)",
                            }}>
                                {inspectedPt.is_live ? `Live · ${fmtDateFull(inspectedPt.date)}` : `BT auditado · ${fmtDateFull(inspectedPt.date)}`}
                            </span>
                            <span style={{ color: "var(--mw-text-2)" }}>
                                Dia:{" "}
                                <strong style={{ color: inspectedPt.d_PORT >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 600, whiteSpace: "nowrap" }}>
                                    {inspectedPt.d_PORT >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(inspectedPt.d_PORT), 0)}
                                </strong>{" "}
                                ({inspectedPt.ops_total} ops)
                            </span>
                            {onSelectDate && !inspectedPt.isOrigin && (
                                <button
                                    type="button"
                                    className="mw-btn mw-btn-secondary mw-mono"
                                    onClick={() => onSelectDate(inspectedPt.is_live ? "" : inspectedPt.date)}
                                    style={{ height: 24, padding: "0 9px", fontSize: 10.5, color: "var(--mw-accent-ink)" }}
                                >
                                    Abrir pregão no gráfico
                                </button>
                            )}
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                            <span style={{ color: "#4cc38a", fontWeight: 600, whiteSpace: "nowrap" }}>
                                Portfólio: {inspectedPt.PORTFOLIO >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(inspectedPt.PORTFOLIO), 0)}
                            </span>
                            {ALL_11_STRAT_META.filter((m) => visibleCurves[m.id]).map((m) => {
                                const val = Number(inspectedPt[m.id] || 0);
                                return (
                                    <span key={`insp-${m.id}`} style={{ color: m.color, whiteSpace: "nowrap" }}>
                                        {m.short}: {val >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(val), 0)}
                                    </span>
                                );
                            })}
                        </div>
                    </div>
                )}
            </div>

            {/* 4. Rodapé duplo: matriz mensal auditada (esquerda) + histórico de trades (direita) */}
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.32fr) minmax(0, 1fr)", gap: 12 }}>
                {/* Esquerda: Matriz Mensal das Estratégias Ativas + Portfólio */}
                <div style={{
                    background: "var(--mw-chrome)",
                    border: "1px solid var(--mw-hairline)",
                    borderRadius: 8,
                    padding: "12px 12px",
                    overflowX: "auto",
                    minWidth: 0,
                }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--mw-text-1)", marginBottom: 10 }}>
                        Resultado mensal auditado ({effectivePortIds.length} ativas · WIN {isWallsFlow ? `${winContracts * 2}L` : `${winContracts}c`} · WDO {isWallsFlow ? `${wdoContracts}L` : `${wdoContracts}c`})
                    </div>
                    <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
                        <thead>
                            <tr style={{ color: "var(--mw-text-3)", borderBottom: "1px solid var(--mw-hairline)", textAlign: "right" }}>
                                <th style={{ textAlign: "left", padding: "5px 4px 5px 2px", fontWeight: 500 }}>Mês</th>
                                {effectivePortIds.map((sid) => {
                                    const sm = STRAT_META_BY_ID[sid];
                                    return (
                                        <th key={`mh-${sid}`} style={{ padding: "5px 3px", color: sm?.color || "var(--mw-text-2)", fontWeight: 500, whiteSpace: "nowrap" }}>
                                            {sm?.short || sid}
                                        </th>
                                    );
                                })}
                                <th style={{ padding: "5px 2px 5px 5px", color: "#4cc38a", fontWeight: 600, whiteSpace: "nowrap" }}>Portfólio</th>
                            </tr>
                        </thead>
                        <tbody>
                            {Object.values(byMonth).map((m) => (
                                <tr
                                    key={m.month}
                                    style={{
                                        borderBottom: "1px solid rgba(255,255,255,0.04)",
                                        textAlign: "right",
                                        background: m.is_live ? "rgba(76, 195, 138, 0.06)" : "transparent",
                                    }}
                                >
                                    <td style={{ textAlign: "left", padding: "5px 4px 5px 2px", fontWeight: 500, color: m.is_live ? "#4cc38a" : "var(--mw-text-1)", whiteSpace: "nowrap" }}>
                                        {m.is_live && !/live/i.test(String(m.month || "")) ? `${m.month} (Live)` : m.month}
                                    </td>
                                    {effectivePortIds.map((sid) => {
                                        const sm = STRAT_META_BY_ID[sid];
                                        const v = Number(m[sid] || 0);
                                        return (
                                            <td key={`mc-${m.month}-${sid}`} style={{ padding: "5px 3px", color: v >= 0 ? (sm?.color || "#4cc38a") : "#e5484d", whiteSpace: "nowrap" }}>
                                                {v >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(v), 0)}
                                            </td>
                                        );
                                    })}
                                    <td style={{ padding: "5px 2px 5px 5px", fontWeight: 600, color: m.PORTFOLIO >= 0 ? "#4cc38a" : "#e5484d", whiteSpace: "nowrap" }}>
                                        {m.PORTFOLIO >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(m.PORTFOLIO), 0)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Direita: Histórico Completo de Todos os Trades + Trades do Pregão Inspecionado */}
                <div style={{
                    background: "var(--mw-chrome)",
                    border: "1px solid var(--mw-hairline)",
                    borderRadius: 8,
                    padding: "12px 14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                    minWidth: 0,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--mw-text-1)" }}>
                            Histórico auditado ({allHistoricalTrades.length} ops)
                        </span>
                        <div className="mw-track">
                            <button
                                type="button"
                                className="mw-btn mw-mono"
                                data-active={tradeHistTab === "ALL" ? "true" : "false"}
                                onClick={() => setTradeHistTab("ALL")}
                                style={{ height: 22, padding: "0 8px", fontSize: 10.5 }}
                            >
                                Todas ({allHistoricalTrades.length})
                            </button>
                            <button
                                type="button"
                                className="mw-btn mw-mono"
                                data-active={tradeHistTab === "DAY" ? "true" : "false"}
                                onClick={() => setTradeHistTab("DAY")}
                                style={{ height: 22, padding: "0 8px", fontSize: 10.5 }}
                            >
                                Pregão {fmtDateShort(inspectedPt?.date)} ({((inspectedPt?.trades || []).filter((tr) => PRESET_TOP6_IDS.includes(tr.strategy_id)).length) + ((inspectedPt?.open_trades || []).filter((tr) => PRESET_TOP6_IDS.includes(tr.strategy_id)).length)})
                            </button>
                        </div>
                    </div>

                    {/* Filtro Rápido por Estratégia */}
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {[
                            { id: "ALL", label: `Todas (${ALL_11_STRAT_META.length})`, col: "#4cc38a" },
                            ...ALL_11_STRAT_META.map((m) => ({ id: m.id, label: m.short, col: m.color })),
                        ].map((sf) => {
                            const active = stratFilter === sf.id;
                            return (
                                <button
                                    key={sf.id}
                                    type="button"
                                    onClick={() => setStratFilter(sf.id)}
                                    className="mw-mono"
                                    style={{
                                        padding: "2px 7px",
                                        fontSize: 10,
                                        fontWeight: active ? 600 : 500,
                                        borderRadius: 5,
                                        cursor: "pointer",
                                        background: active ? `${sf.col}1a` : "var(--mw-card)",
                                        color: active ? sf.col : "var(--mw-text-3)",
                                        border: active ? `1px solid ${sf.col}66` : "1px solid var(--mw-hairline)",
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
                                <div className="mw-mono" style={{
                                    padding: "16px 12px",
                                    background: "var(--mw-card)",
                                    borderRadius: 6,
                                    border: "1px dashed var(--mw-hairline)",
                                    color: "var(--mw-text-3)",
                                    fontSize: 11,
                                    textAlign: "center",
                                }}>
                                    Nenhuma operação encontrada para este filtro no pregão selecionado.
                                </div>
                            );
                        }

                        const visibleTradesToShow = tradesToShow.slice(0, maxHistRows);
                        const remainingCount = Math.max(0, tradesToShow.length - visibleTradesToShow.length);

                        return (
                            <div style={{ maxHeight: 215, overflowY: "auto", overflowX: "auto", border: "1px solid var(--mw-hairline)", borderRadius: 6 }}>
                                <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 10.5 }}>
                                    <thead style={{ position: "sticky", top: 0, background: "var(--mw-card)", zIndex: 1 }}>
                                        <tr style={{ color: "var(--mw-text-3)", borderBottom: "1px solid var(--mw-hairline)", textAlign: "right" }}>
                                            <th style={{ textAlign: "left", padding: "6px 6px", fontWeight: 500 }}>Data / hora</th>
                                            <th style={{ textAlign: "left", padding: "6px 6px", fontWeight: 500 }}>Estratégia</th>
                                            <th style={{ textAlign: "center", padding: "6px 6px", fontWeight: 500 }}>Lado</th>
                                            <th style={{ padding: "6px 6px", fontWeight: 500 }}>Entrada</th>
                                            <th style={{ padding: "6px 6px", fontWeight: 500 }}>Pts</th>
                                            <th style={{ padding: "6px 6px", fontWeight: 500 }}>Resultado</th>
                                            <th style={{ textAlign: "left", padding: "6px 6px", fontWeight: 500 }}>Desfecho</th>
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
                                                    title="Clique para abrir este pregão no gráfico acima"
                                                    style={{ borderBottom: "1px solid rgba(255,255,255,0.04)", textAlign: "right", cursor: "pointer" }}
                                                >
                                                    <td style={{ textAlign: "left", padding: "5px 6px", color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>
                                                        {fmtDateShort(tr.date)} {tr.time}
                                                    </td>
                                                    <td style={{ textAlign: "left", padding: "5px 6px", color: sCol, fontWeight: 500, whiteSpace: "nowrap" }}>
                                                        {sName}
                                                    </td>
                                                    <td style={{ textAlign: "center", padding: "5px 6px", color: tr.direction === "COMPRA" ? "#4cc38a" : "#e5484d", fontWeight: 600, whiteSpace: "nowrap" }}>
                                                        {tr.direction === "COMPRA" ? "Compra" : "Venda"}
                                                    </td>
                                                    <td style={{ padding: "5px 6px", color: "var(--mw-text-1)", whiteSpace: "nowrap" }}>
                                                        {fmtNum(tr.entry_price, tr.asset === "WDO" ? 1 : 0)}
                                                    </td>
                                                    <td style={{ padding: "5px 6px", color: isOpen ? "#d4a259" : (tr.pts >= 0 ? "#4cc38a" : "#e5484d"), whiteSpace: "nowrap" }}>
                                                        {fmtNum(tr.pts, tr.asset === "WDO" ? 1 : 0, true)}p
                                                    </td>
                                                    <td style={{ padding: "5px 6px", fontWeight: 600, color: isOpen ? "#d4a259" : (brlVal >= 0 ? "#4cc38a" : "#e5484d"), whiteSpace: "nowrap" }}>
                                                        {isOpen ? "Aberta" : `${brlVal >= 0 ? "+" : "−"}R$ ${fmtNum(Math.abs(brlVal), 0)}`}
                                                    </td>
                                                    <td style={{ textAlign: "left", padding: "5px 6px", color: "var(--mw-text-3)", fontSize: 10, whiteSpace: "nowrap" }}>
                                                        {stripUiEmoji(tr.label) || (isOpen ? "Em aberto" : "Fechada")}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                                {remainingCount > 0 && (
                                    <div style={{ padding: "8px", textAlign: "center", background: "var(--mw-card)", borderTop: "1px solid var(--mw-hairline)" }}>
                                        <button
                                            type="button"
                                            className="mw-btn mw-btn-secondary mw-mono"
                                            onClick={() => setMaxHistRows((prev) => prev + 250)}
                                            style={{ height: 26, padding: "0 12px", fontSize: 11, color: "var(--mw-accent-ink)" }}
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

            {/* 5. Sinergia e matriz de correlação diária */}
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
                            bg: "rgba(255, 255, 255, 0.04)",
                            border: "1px solid var(--mw-hairline)",
                            text: "var(--mw-text-3)",
                        };
                    }
                    if (r < -0.02) {
                        const alpha = Math.min(0.32, 0.12 + Math.abs(r) * 1.1);
                        return {
                            bg: `rgba(56, 189, 248, ${alpha.toFixed(2)})`,
                            border: "1px solid rgba(56, 189, 248, 0.35)",
                            text: "#7dd3fc",
                        };
                    }
                    if (r <= 0.18) {
                        const alpha = Math.min(0.26, 0.08 + Math.abs(r) * 0.7);
                        return {
                            bg: `rgba(76, 195, 138, ${alpha.toFixed(2)})`,
                            border: "1px solid rgba(76, 195, 138, 0.30)",
                            text: "#4cc38a",
                        };
                    }
                    if (r <= 0.45) {
                        return {
                            bg: "rgba(212, 162, 89, 0.15)",
                            border: "1px solid rgba(212, 162, 89, 0.35)",
                            text: "#d4a259",
                        };
                    }
                    return {
                        bg: "rgba(229, 72, 77, 0.18)",
                        border: "1px solid rgba(229, 72, 77, 0.38)",
                        text: "#e5484d",
                    };
                };

                if (isWallsFlow) {
                    return (
                        <div
                            className="mw-mono"
                            style={{
                                background: "var(--mw-chrome)",
                                border: "1px solid var(--mw-hairline)",
                                borderRadius: 8,
                                padding: "10px 14px",
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                flexWrap: "wrap",
                                gap: 10,
                                fontSize: 11,
                            }}
                        >
                            <span style={{ color: "var(--mw-text-1)", fontWeight: 600 }}>
                                Sinergia e descorrelação diária ({sessionPts.length} pregões)
                            </span>
                            <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
                                <span style={{ color: "var(--mw-text-2)" }}>
                                    Pearson WIN × WDO:{" "}
                                    <strong style={{ color: corrWinDol <= 0.15 ? "#4cc38a" : "#38bdf8", fontWeight: 600 }}>
                                        r = {corrWinDol >= 0 ? "+" : "−"}{fmtNum(Math.abs(corrWinDol), 2)} (independentes)
                                    </strong>
                                </span>
                                <span style={{ color: "var(--mw-text-3)" }}>
                                    Diversificação: DD{" "}
                                    <strong style={{ color: "#e5484d", fontWeight: 500, whiteSpace: "nowrap" }}>−R$ {fmtNum(mddPort, 0)}</strong> · Ret/DD{" "}
                                    <strong style={{ color: "#38bdf8", fontWeight: 600 }}>{fmtNum(portRetDd, 2)}x</strong>
                                </span>
                            </div>
                        </div>
                    );
                }

                return (
                    <div style={{
                        background: "var(--mw-chrome)",
                        border: "1px solid var(--mw-hairline)",
                        borderRadius: 8,
                        padding: "12px 14px",
                        display: "flex",
                        flexDirection: "column",
                        gap: 10,
                    }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--mw-text-1)" }}>
                                Matriz e correlação diária ({stratMeta.length} estratégias · {totalPairs} pares · {sessionPts.length} pregões)
                            </span>

                            <div className="mw-mono" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 11 }}>
                                <span style={{ background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", padding: "3px 8px", borderRadius: 5, color: "var(--mw-text-2)" }}>
                                    WIN × WDO:{" "}
                                    <strong style={{ color: "#4cc38a", fontWeight: 600 }}>
                                        {corrWinDol >= 0 ? "+" : "−"}{fmtNum(Math.abs(corrWinDol), 2)}
                                    </strong>
                                </span>
                                <span style={{ background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", padding: "3px 8px", borderRadius: 5, color: "var(--mw-text-2)" }}>
                                    Média ({totalPairs} pares):{" "}
                                    <strong style={{ color: "#38bdf8", fontWeight: 600 }}>
                                        {avgPairCorr >= 0 ? "+" : "−"}{fmtNum(Math.abs(avgPairCorr), 2)}
                                    </strong>
                                </span>
                                <span style={{ background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", padding: "3px 8px", borderRadius: 5, color: "var(--mw-text-2)" }}>
                                    Hedge negativo:{" "}
                                    <strong style={{ color: "#7dd3fc", fontWeight: 600 }}>
                                        {negPairsCount}/{totalPairs}
                                    </strong>
                                </span>
                            </div>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.18fr) minmax(0, 1.04fr)", gap: 12, alignItems: "stretch" }}>
                            {/* Esquerda: Heatmap de Correlação de Pearson */}
                            <div style={{
                                background: "var(--mw-card)",
                                border: "1px solid var(--mw-hairline)",
                                borderRadius: 7,
                                padding: "10px 12px",
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                gap: 8,
                                overflowX: "auto",
                            }}>
                                <div className="mw-mono" style={{ fontSize: 11, color: "var(--mw-text-2)", fontWeight: 500 }}>
                                    Mapa de calor (correlação de Pearson −1,00 a +1,00)
                                </div>
                                <table className="mw-mono" style={{ width: "100%", borderCollapse: "separate", borderSpacing: 2, fontSize: 10 }}>
                                    <thead>
                                        <tr>
                                            <th style={{ textAlign: "left", padding: "3px 4px", color: "var(--mw-text-3)", fontSize: 9.5, fontWeight: 500 }}>Estratégia</th>
                                            {stratMeta.map((sm) => (
                                                <th key={`ch-${sm.id}`} style={{ textAlign: "center", padding: "3px 2px", color: sm.col, fontSize: 9.5, fontWeight: 500 }}>
                                                    {sm.short}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {stratMeta.map((rowSm, ri) => (
                                            <tr key={`cr-${rowSm.id}`}>
                                                <td style={{ padding: "3px 4px", color: rowSm.col, fontWeight: 500, whiteSpace: "nowrap", fontSize: 10 }}>
                                                    {rowSm.name}
                                                </td>
                                                {stratMeta.map((colSm, ci) => {
                                                    const r = corrMatrix[rowSm.id][colSm.id];
                                                    const isDiag = ri === ci;
                                                    const st = getCellStyle(r, isDiag);
                                                    return (
                                                        <td
                                                            key={`cc-${rowSm.id}-${colSm.id}`}
                                                            title={`${rowSm.name} × ${colSm.name}: Correlação = ${r >= 0 ? "+" : "−"}${fmtNum(Math.abs(r), 2)}`}
                                                            style={{
                                                                textAlign: "center",
                                                                padding: "5px 3px",
                                                                borderRadius: 4,
                                                                background: st.bg,
                                                                border: st.border,
                                                                color: st.text,
                                                                fontWeight: isDiag ? 400 : 600,
                                                                fontSize: 10,
                                                            }}
                                                        >
                                                            {isDiag ? "1,00" : `${r >= 0 ? "+" : "−"}${fmtNum(Math.abs(r), 2)}`}
                                                        </td>
                                                    );
                                                })}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                                <div className="mw-mono" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 9.5, color: "var(--mw-text-3)", paddingTop: 2, flexWrap: "wrap", gap: 6 }}>
                                    <span>&lt; 0,00: Hedge natural</span>
                                    <span>0,00 a +0,18: Descorrelacionadas</span>
                                    <span>&gt; +0,50: Alta sinergia direcional</span>
                                </div>
                            </div>

                            {/* Direita: Ranking de pares */}
                            <div style={{
                                background: "var(--mw-card)",
                                border: "1px solid var(--mw-hairline)",
                                borderRadius: 7,
                                padding: "10px 12px",
                                display: "flex",
                                flexDirection: "column",
                                gap: 6,
                            }}>
                                <div className="mw-mono" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, color: "var(--mw-text-2)", fontWeight: 500 }}>
                                    <span>Ranking dos {totalPairs} pares</span>
                                    <span style={{ fontSize: 10, color: "#4cc38a" }}>{lowCorrPairsCount}/{totalPairs} pares ≤ +0,18</span>
                                </div>

                                <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 240, overflowY: "auto", paddingRight: 2 }}>
                                    {pairsList.map((pr) => {
                                        const isNeg = pr.corr < 0;
                                        const isHigh = pr.corr > 0.45;
                                        const barColor = isNeg ? "#38bdf8" : isHigh ? "#e5484d" : "#4cc38a";
                                        const zeroPct = 24;
                                        const widthPct = pr.corr < 0
                                            ? Math.min(zeroPct, (Math.abs(pr.corr) / 0.25) * zeroPct)
                                            : Math.min(100 - zeroPct, (pr.corr / 0.80) * (100 - zeroPct));
                                        const leftPct = pr.corr < 0 ? (zeroPct - widthPct) : zeroPct;

                                        return (
                                            <div
                                                key={pr.key}
                                                className="mw-mono"
                                                style={{
                                                    display: "grid",
                                                    gridTemplateColumns: "1.25fr 1.75fr 46px",
                                                    alignItems: "center",
                                                    gap: 6,
                                                    fontSize: 10,
                                                }}
                                            >
                                                <div style={{ color: "var(--mw-text-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={pr.fullLabel}>
                                                    {pr.label}
                                                </div>
                                                <div style={{
                                                    position: "relative",
                                                    height: 8,
                                                    background: "var(--mw-chrome)",
                                                    borderRadius: 3,
                                                    border: "1px solid var(--mw-hairline)",
                                                    overflow: "hidden",
                                                }}>
                                                    <div style={{
                                                        position: "absolute",
                                                        left: `${zeroPct}%`,
                                                        top: 0,
                                                        bottom: 0,
                                                        width: 1,
                                                        background: "#2a3346",
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
                                                    fontWeight: 600,
                                                    color: barColor,
                                                }}>
                                                    {pr.corr >= 0 ? "+" : "−"}{fmtNum(Math.abs(pr.corr), 2)}
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
        </section>
    );
}, (prev, next) => prev.portfolioData === next.portfolioData);

/* ── COMPONENTE DO COCKPIT DE 1 ATIVO (ESQUERDA: FLUXO REAL | DIREITA: A.S.G HUD + CURVA DE CAPITAL) ── */
function SingleAssetCockpitView({ symKey, payload, manualMode = false, sessionDateOverride = "", isSideBySide = false, compassData = null }) {
    const [selectedSigId, setSelectedSigId] = useState(null);
    const [showHistory, setShowHistory] = useState(false);
    const [isCapitalCollapsed, setIsCapitalCollapsed] = useState(() => isWallsFlowLocalhost());

    if (!payload) return null;

    const dec = symKey === "WDO" ? 1 : 0;
    const ca = payload.caminho_a || {};
    const rawSc = ca.signals_scorecard || {};
    const isWallsFlow = isWallsFlowLocalhost();
    const allFilteredSignals = filterSignalsForHost(ca.signals_log || [], isWallsFlow);
    const signalsLog = manualMode ? [] : allFilteredSignals;
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
    const tot = payload.session_totals || {};
    const lastBar = series.length > 0 ? series[series.length - 1] : {};
    const winDir = Number(asgHud.window_dir || 0);
    const winCol = winDir >= 0 ? "var(--mw-pos)" : "var(--mw-neg)";
    const makersPct = Number(asgHud.makers_pct || 0);
    const sessInstAggr = Number(tot.inst_aggr_delta ?? lastBar.cvd_inst_aggr ?? tot.inst_delta ?? 0);
    const sessInstPass = Number(tot.inst_pass_delta ?? lastBar.cvd_inst_pass ?? 0);
    const sessRetDelta = Number(tot.retail_delta ?? lastBar.cvd_retail ?? 0);
    const sessHftDelta = Number(tot.hft_delta ?? lastBar.cvd_hft ?? 0);
    const sessHftChurn = Number(tot.hft_churn_pct ?? lastBar.hft_churn_pct ?? 0);
    const sessRlpPct = Number(tot.rlp_pct ?? lastBar.rlp_pct ?? 0);
    const sessRlpDelta = Number(tot.rlp_delta ?? lastBar.cvd_rlp_delta ?? Math.round(-sessRetDelta * (sessRlpPct / 100.0)));
    const sup0 = radar.support_walls?.[0] || null;
    const res0 = radar.resistance_walls?.[0] || null;
    const flipWall = allWalls.find((w) => w && (String(w.type || "") === "GammaFlip" || /flip/i.test(String(w.label || "")))) || null;
    const barriers = radar.structural_barriers || {};
    const localCallWall = barriers.local_call_wall || allWalls.find((w) => w && w.is_local_call_wall) || null;
    const localPutWall = barriers.local_put_wall || allWalls.find((w) => w && w.is_local_put_wall) || null;
    const lastPriceNum = Number(payload.last_price ?? lastBar.close ?? 0);
    const vwapNum = Number(payload.vwap ?? 0);
    const vwapDiffPct = (lastPriceNum > 0 && vwapNum > 0) ? ((lastPriceNum - vwapNum) / vwapNum) * 100 : null;
    const contractLabel = payload.active_contract || symKey;
    const assetSubtitle = symKey === "WIN" ? "Índice futuro" : "Dólar futuro";

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
    const drawerCollapsedActive = !manualMode && isWallsFlow && isCapitalCollapsed;
    const lotBaseTag = isWallsFlow ? (symKey === "WIN" ? "2L" : "1L") : "1c";
    const netCol = dayNetBrl >= 0 ? "#4cc38a" : "#e5484d";

    const manualEmbeddedHeader = manualMode ? (
        isSideBySide ? (
            <div
                style={{
                    borderLeft: `2px solid ${series.length > 0 ? winCol : "var(--mw-text-3)"}`,
                    padding: "12px 14px",
                    borderBottom: "1px solid var(--mw-hairline)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    backgroundColor: "var(--mw-card)",
                }}
            >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 10, minWidth: 0, overflow: "hidden", whiteSpace: "nowrap" }}>
                        <span className="mw-mono" style={{
                            fontSize: 12,
                            fontWeight: 600,
                            lineHeight: "18px",
                            padding: "2px 8px",
                            borderRadius: 6,
                            backgroundColor: "var(--mw-accent-soft)",
                            border: "1px solid var(--mw-accent-border)",
                            color: "var(--mw-accent-ink)",
                            flexShrink: 0,
                        }}>
                            {contractLabel}
                        </span>
                        <span className="mw-mono" style={{ fontSize: 24, fontWeight: 500, lineHeight: 1, letterSpacing: "-0.02em", color: "var(--mw-text-1)" }}>
                            {lastPriceNum > 0 ? fmtNum(lastPriceNum, dec) : "—"}
                        </span>
                        {vwapNum > 0 && (
                            <span className="mw-mono" style={{ fontSize: 12, color: "var(--mw-text-2)" }}>
                                VWAP {fmtNum(vwapNum, dec)}
                                {vwapDiffPct !== null && (
                                    <span style={{ color: vwapDiffPct >= 0 ? "var(--mw-pos)" : "var(--mw-neg)", marginLeft: 4 }}>
                                        ({vwapDiffPct >= 0 ? "+" : "−"}{fmtNum(Math.abs(vwapDiffPct), 2)}%)
                                    </span>
                                )}
                            </span>
                        )}
                    </div>
                    {series.length > 0 && (
                        <span style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            padding: "2px 8px",
                            borderRadius: 6,
                            backgroundColor: "var(--mw-raised)",
                            border: "1px solid var(--mw-hairline)",
                            fontSize: 11.5,
                            color: "var(--mw-text-1)",
                            whiteSpace: "nowrap",
                            flexShrink: 0,
                        }}>
                            <span style={{ width: 6, height: 6, borderRadius: 999, backgroundColor: winCol, display: "inline-block" }} />
                            <span>{winDir >= 0 ? "Janela comprada" : "Janela vendida"} · {asgHud.window_start_time || "09:00"}</span>
                        </span>
                    )}
                </div>

                <div
                    className="mw-mono"
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 14,
                        fontSize: 11.5,
                        lineHeight: "16px",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                    }}
                >
                    {sup0 && (
                        <span style={{ color: "var(--mw-text-3)" }}>
                            Sup Wall <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(sup0.price, dec)}</strong>
                        </span>
                    )}
                    {res0 && (
                        <span style={{ color: "var(--mw-text-3)" }}>
                            Res Wall <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(res0.price, dec)}</strong>
                        </span>
                    )}
                    {flipWall && (
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--mw-text-3)" }}>
                            <span style={{ width: 7, height: 2, backgroundColor: "var(--mw-flip)", display: "inline-block" }} />
                            FlipWall <strong style={{ fontWeight: 500, color: "var(--mw-flip)" }}>{fmtNum(flipWall.price, dec)}</strong>
                        </span>
                    )}
                    {localCallWall && (!flipWall || Math.abs(Number(localCallWall.price) - Number(flipWall.price)) > (symKey === "WDO" ? 0.5 : 5)) && (
                        <span style={{ color: "var(--mw-text-3)" }}>
                            CallWall <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(localCallWall.price, dec)}</strong>
                        </span>
                    )}
                    {localPutWall && (!flipWall || Math.abs(Number(localPutWall.price) - Number(flipWall.price)) > (symKey === "WDO" ? 0.5 : 5)) && (
                        <span style={{ color: "var(--mw-text-3)" }}>
                            PutWall <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(localPutWall.price, dec)}</strong>
                        </span>
                    )}
                </div>

                <div
                    className="mw-mono"
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        fontSize: 11,
                        lineHeight: "16px",
                        color: "var(--mw-text-3)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                    }}
                >
                    <span>
                        Makers <strong style={{ fontWeight: 500, color: makersPct >= 0 ? "var(--mw-pos)" : "var(--mw-neg)" }}>{makersPct >= 0 ? "+" : ""}{fmtNum(makersPct, 1)}%</strong>
                    </span>
                    <span>
                        Inst <strong style={{ fontWeight: 500, color: sessInstAggr >= 0 ? "var(--mw-pos)" : "var(--mw-neg)" }}>{fmtNum(sessInstAggr, 0, true)}L</strong>/{fmtNum(sessInstPass, 0, true)}L
                    </span>
                    <span>
                        Varejo <strong style={{ fontWeight: 500, color: "var(--mw-text-2)" }}>{fmtNum(sessRetDelta, 0, true)}L</strong>
                    </span>
                    <span>
                        HFT <strong style={{ fontWeight: 500, color: "var(--mw-text-2)" }}>{fmtNum(sessHftDelta, 0, true)}L ({fmtNum(sessHftChurn, 0)}%)</strong>
                    </span>
                    <span>
                        RLP <strong style={{ fontWeight: 500, color: "var(--mw-text-2)" }}>{fmtNum(sessRlpDelta, 0, true)}L ({fmtNum(sessRlpPct, 0)}%)</strong>
                    </span>
                </div>
            </div>
        ) : (
            <div
                style={{
                    borderLeft: `2px solid ${series.length > 0 ? winCol : "var(--mw-text-3)"}`,
                    padding: "16px 20px",
                    borderBottom: "1px solid var(--mw-hairline)",
                    display: "flex",
                    flexWrap: "wrap",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 16,
                    backgroundColor: "var(--mw-card)",
                }}
            >
                <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 220 }}>
                    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                        <span className="mw-mono" style={{
                            fontSize: 13,
                            fontWeight: 600,
                            lineHeight: "18px",
                            padding: "2px 8px",
                            borderRadius: 6,
                            backgroundColor: "var(--mw-accent-soft)",
                            border: "1px solid var(--mw-accent-border)",
                            color: "var(--mw-accent-ink)",
                        }}>
                            {contractLabel}
                        </span>
                        <span style={{ fontSize: 13, color: "var(--mw-text-3)" }}>{assetSubtitle}</span>
                        {series.length > 0 && (
                            <span style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 6,
                                padding: "2px 8px",
                                borderRadius: 6,
                                backgroundColor: "var(--mw-raised)",
                                border: "1px solid var(--mw-hairline)",
                                fontSize: 12,
                                color: "var(--mw-text-1)",
                            }}>
                                <span style={{ width: 6, height: 6, borderRadius: 999, backgroundColor: winCol, display: "inline-block" }} />
                                <span>{winDir >= 0 ? "Janela comprada" : "Janela vendida"} · {asgHud.window_start_time || "09:00"}</span>
                            </span>
                        )}
                    </div>
                    <div style={{ display: "flex", alignItems: "baseline", flexWrap: "wrap", gap: 12 }}>
                        <span className="mw-mono" style={{ fontSize: 28, fontWeight: 500, lineHeight: 1, letterSpacing: "-0.02em", color: "var(--mw-text-1)" }}>
                            {lastPriceNum > 0 ? fmtNum(lastPriceNum, dec) : "—"}
                        </span>
                        {vwapNum > 0 && (
                            <span className="mw-mono" style={{ fontSize: 13, color: "var(--mw-text-2)" }}>
                                VWAP {fmtNum(vwapNum, dec)}
                                {vwapDiffPct !== null && (
                                    <span style={{ color: vwapDiffPct >= 0 ? "var(--mw-pos)" : "var(--mw-neg)", marginLeft: 5 }}>
                                        ({vwapDiffPct >= 0 ? "+" : "−"}{fmtNum(Math.abs(vwapDiffPct), 2)}%)
                                    </span>
                                )}
                            </span>
                        )}
                    </div>
                </div>

                <div
                    className="mw-mono"
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-end",
                        gap: 8,
                        fontSize: 12,
                        lineHeight: "16px",
                    }}
                >
                    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 16 }}>
                        {sup0 && (
                            <span style={{ color: "var(--mw-text-3)" }}>
                                Sup Wall <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(sup0.price, dec)}</strong>
                            </span>
                        )}
                        {res0 && (
                            <span style={{ color: "var(--mw-text-3)" }}>
                                Res Wall <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(res0.price, dec)}</strong>
                            </span>
                        )}
                        {flipWall && (
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--mw-text-3)" }}>
                                <span style={{ width: 8, height: 2, backgroundColor: "var(--mw-flip)", display: "inline-block" }} />
                                FlipWall <strong style={{ fontWeight: 500, color: "var(--mw-flip)" }}>{fmtNum(flipWall.price, dec)}</strong>
                            </span>
                        )}
                        {localCallWall && (!flipWall || Math.abs(Number(localCallWall.price) - Number(flipWall.price)) > (symKey === "WDO" ? 0.5 : 5)) && (
                            <span style={{ color: "var(--mw-text-3)" }}>
                                CallWall <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(localCallWall.price, dec)}</strong>
                            </span>
                        )}
                        {localPutWall && (!flipWall || Math.abs(Number(localPutWall.price) - Number(flipWall.price)) > (symKey === "WDO" ? 0.5 : 5)) && (
                            <span style={{ color: "var(--mw-text-3)" }}>
                                PutWall <strong style={{ fontWeight: 500, color: "var(--mw-text-1)" }}>{fmtNum(localPutWall.price, dec)}</strong>
                            </span>
                        )}
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, color: "var(--mw-text-3)" }}>
                        <span>
                            Makers GEX <strong style={{ fontWeight: 500, color: makersPct >= 0 ? "var(--mw-pos)" : "var(--mw-neg)" }}>{makersPct >= 0 ? "+" : ""}{fmtNum(makersPct, 1)}%</strong>
                        </span>
                        <span>
                            Inst <strong style={{ fontWeight: 500, color: sessInstAggr >= 0 ? "var(--mw-pos)" : "var(--mw-neg)" }}>{fmtNum(sessInstAggr, 0, true)}L</strong> / {fmtNum(sessInstPass, 0, true)}L
                        </span>
                        <span>
                            Varejo <strong style={{ fontWeight: 500, color: "var(--mw-text-2)" }}>{fmtNum(sessRetDelta, 0, true)}L</strong>
                        </span>
                        <span>
                            HFT <strong style={{ fontWeight: 500, color: "var(--mw-text-2)" }}>{fmtNum(sessHftDelta, 0, true)}L ({fmtNum(sessHftChurn, 0)}%)</strong>
                        </span>
                        <span>
                            RLP <strong style={{ fontWeight: 500, color: "var(--mw-text-2)" }}>{fmtNum(sessRlpDelta, 0, true)}L ({fmtNum(sessRlpPct, 0)}%)</strong>
                        </span>
                    </div>
                </div>
            </div>
        )
    ) : null;

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0, width: "100%", height: "100%" }}>
            <div style={{
                display: "grid",
                gridTemplateColumns: manualMode ? "minmax(0, 1fr)" : (drawerCollapsedActive ? "minmax(0, 1fr) 44px" : "2.1fr 1fr"),
                gap: drawerCollapsedActive ? 10 : 14,
                alignItems: "stretch",
                flex: 1,
                minWidth: 0,
            }}>
                {/* Esquerda (68% padrão | ~97% modo expandido | 100% modo manual): Gráfico Preço + Fluxo Smart Money */}
                <FluxoRealAsgChart
                    symKey={symKey}
                    series={series}
                    flowWindows={flowWindows}
                    signalsLog={allFilteredSignals}
                    asgHud={asgHud}
                    wallsRadar={radar}
                    allWalls={allWalls}
                    volumeProfile={payload.volume_profile || null}
                    vwap={payload.vwap}
                    selectedSigId={manualMode ? null : selectedSigId}
                    showSignalsMarkers={!manualMode}
                    wideMode={manualMode || drawerCollapsedActive}
                    sessionDate={sessionDateOverride || payload.session_date || ca.ref_date || ""}
                    payloadDate={payload.session_date || ca.ref_date || ""}
                    precomputedDivs={ca.engine_divs_v32}
                    compassData={compassData}
                    embeddedHeader={manualEmbeddedHeader}
                    isSideBySide={isSideBySide}
                    contractName={contractLabel}
                    capitalDrawerInfo={!manualMode && isWallsFlow ? {
                        isCollapsed: isCapitalCollapsed,
                        netBrl: dayNetBrl,
                        netPts: dayNetPts,
                        onToggle: () => setIsCapitalCollapsed((v) => !v),
                    } : null}
                    onSelectSignal={manualMode ? undefined : (id) => {
                        setSelectedSigId(id);
                        if (id) setShowHistory(true);
                    }}
                />

                {/* Direita: Gaveta Retrátil (oculta no modo manual) */}
                {!manualMode && (drawerCollapsedActive ? (
                    <div
                        className="mw-card"
                        onClick={() => setIsCapitalCollapsed(false)}
                        title={`Clique para expandir o painel de Capital e HUD do ${symKey} (${dayNetBrl >= 0 ? "+" : "−"}R$ ${fmtNum(Math.abs(dayNetBrl), 0)} hoje)`}
                        style={{
                            borderLeft: `2px solid ${netCol}`,
                            padding: "10px 4px",
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 8,
                            minHeight: 0,
                            overflow: "hidden",
                            cursor: "pointer",
                            userSelect: "none",
                        }}
                    >
                        <div
                            style={{
                                width: 28,
                                height: 28,
                                flexShrink: 0,
                                borderRadius: 6,
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                background: "var(--mw-accent-soft)",
                                border: "1px solid var(--mw-accent-border)",
                                color: "var(--mw-accent-ink)",
                            }}
                        >
                            <IconChevLeft />
                        </div>

                        <div
                            className="mw-mono"
                            style={{
                                flex: 1,
                                minHeight: 0,
                                overflow: "hidden",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                            }}
                        >
                            <div
                                style={{
                                    writingMode: "vertical-rl",
                                    transform: "rotate(180deg)",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 10,
                                    fontSize: 11,
                                    whiteSpace: "nowrap",
                                }}
                            >
                                <span style={{ color: "var(--mw-text-3)", fontWeight: 500 }}>
                                    Capital {symKey} ({lotBaseTag})
                                </span>
                                <span style={{ color: netCol, fontWeight: 600 }}>
                                    {dayNetBrl >= 0 ? "+" : "−"}R$ {fmtNum(Math.abs(dayNetBrl), 0)}
                                </span>
                                <span style={{ color: "var(--mw-text-2)", fontSize: 10.5 }}>
                                    {sc.valid_signals || 0}W/{sc.invalid_signals || 0}L · {fmtNum(sc.win_rate_pct, 0)}%
                                </span>
                            </div>
                        </div>

                        <button
                            type="button"
                            onClick={(e) => {
                                e.stopPropagation();
                                setShowHistory((s) => !s);
                            }}
                            title={showHistory ? "Ocultar tabela de sinais do dia" : "Ver tabela de sinais do dia"}
                            style={{
                                width: 28,
                                height: 28,
                                flexShrink: 0,
                                borderRadius: 6,
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                background: showHistory ? "var(--mw-accent-soft)" : "var(--mw-chrome)",
                                border: showHistory ? "1px solid var(--mw-accent-border)" : "1px solid var(--mw-hairline)",
                                color: showHistory ? "var(--mw-accent-ink)" : "var(--mw-text-2)",
                                cursor: "pointer",
                            }}
                        >
                            <IconList />
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
                ))}
            </div>

            {/* Tabela retrátil de janelas e sinais */}
            {!manualMode && showHistory && (
                <div className="mw-card" style={{
                    padding: "12px 14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--mw-text-1)" }}>
                            Histórico de sinais do dia · {symKey} ({signalsLog.length} emitidos)
                        </span>
                        <button
                            type="button"
                            className="mw-btn mw-btn-secondary"
                            onClick={() => setShowHistory(false)}
                            style={{ height: 24, padding: "0 8px", fontSize: 11 }}
                        >
                            Fechar
                        </button>
                    </div>
                    <div style={{ maxHeight: 220, overflowY: "auto", overflowX: "auto" }}>
                        <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                            <thead>
                                <tr style={{ color: "var(--mw-text-3)", borderBottom: "1px solid var(--mw-hairline)", textAlign: "right" }}>
                                    <th style={{ textAlign: "left", padding: "6px 6px", fontWeight: 500 }}>Hora</th>
                                    <th style={{ textAlign: "left", padding: "6px 6px", fontWeight: 500 }}>Direção</th>
                                    <th style={{ padding: "6px 6px", fontWeight: 500 }}>Preço</th>
                                    <th style={{ textAlign: "left", padding: "6px 6px", fontWeight: 500 }}>Gatilho</th>
                                    <th style={{ padding: "6px 6px", color: "#4cc38a", fontWeight: 500 }}>Máx a favor</th>
                                    <th style={{ padding: "6px 6px", color: "#e5484d", fontWeight: 500 }}>Máx contra</th>
                                    <th style={{ textAlign: "right", padding: "6px 6px", fontWeight: 500 }}>Resultado</th>
                                </tr>
                            </thead>
                            <tbody>
                                {signalsLog.map((sig) => {
                                    const isBuy = sig.dir_num > 0;
                                    const vColor = sig.is_valid === true ? "#4cc38a" : sig.is_valid === false ? "#e5484d" : "#d4a259";
                                    return (
                                        <tr
                                            key={sig.id}
                                            onClick={() => setSelectedSigId(sig.id)}
                                            style={{
                                                borderBottom: "1px solid rgba(255,255,255,0.04)",
                                                textAlign: "right",
                                                cursor: "pointer",
                                                background: selectedSigId === sig.id ? "var(--mw-accent-soft)" : "transparent",
                                            }}
                                        >
                                            <td style={{ textAlign: "left", padding: "5px 6px", fontWeight: 500, color: "var(--mw-text-1)", whiteSpace: "nowrap" }}>{sig.time}</td>
                                            <td style={{ textAlign: "left", padding: "5px 6px", fontWeight: 600, color: isBuy ? "#4cc38a" : "#e5484d", whiteSpace: "nowrap" }}>
                                                {isBuy ? "Compra" : "Venda"}
                                            </td>
                                            <td style={{ padding: "5px 6px", color: "var(--mw-text-1)", whiteSpace: "nowrap" }}>{fmtNum(sig.entry_price, dec)}</td>
                                            <td style={{ textAlign: "left", padding: "5px 6px", color: "var(--mw-text-2)" }}>{sig.type}</td>
                                            <td style={{ padding: "5px 6px", color: "#4cc38a", fontWeight: 500, whiteSpace: "nowrap" }}>+{fmtNum(sig.mfe_30m, dec)}p</td>
                                            <td style={{ padding: "5px 6px", color: "#e5484d", whiteSpace: "nowrap" }}>{fmtNum(sig.mae_30m, dec)}p</td>
                                            <td style={{ padding: "5px 6px", fontWeight: 600, color: vColor, whiteSpace: "nowrap" }}>{stripUiEmoji(sig.validation_label)}</td>
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
            <div className="mw-mono" style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--mw-text-3)", fontSize: 11, background: "var(--mw-chrome)", borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
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
        <div style={{ background: "var(--mw-chrome)", borderRadius: 8, border: "1px solid var(--mw-hairline)", padding: "8px 10px" }}>
            <div className="mw-mono" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6, flexWrap: "wrap", gap: 8 }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                    {keys.map((k, idx) => {
                        const lastV = Number(series[series.length - 1]?.[k] || 0);
                        return (
                            <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10.5 }}>
                                <span style={{ width: 8, height: 2.5, background: colors[idx], display: "inline-block", borderRadius: 1 }} />
                                <span style={{ color: "var(--mw-text-3)" }}>{labels[idx]}:</span>
                                <span style={{ color: colors[idx], fontWeight: 600 }}>{fmtNum(lastV, 0, true)}</span>
                            </span>
                        );
                    })}
                </div>
                <span style={{ fontSize: 10, color: "var(--mw-text-3)" }}>{series.length} barras M5</span>
            </div>
            <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: height, display: "block" }}>
                <line x1={padL} y1={yZero} x2={width - padR} y2={yZero} stroke="#2a3346" strokeDasharray="3,3" strokeWidth="1" />
                {keys.map((k, idx) => (
                    <polyline
                        key={k}
                        fill="none"
                        stroke={colors[idx]}
                        strokeWidth={idx === 0 ? "2" : "1.4"}
                        points={makePoints(k)}
                    />
                ))}
                <text x={padL + 2} y={height - 3} fill="#6b7489" fontSize="9" fontFamily="IBM Plex Mono, monospace">{firstTime}</text>
                <text x={width / 2 - 14} y={height - 3} fill="#6b7489" fontSize="9" fontFamily="IBM Plex Mono, monospace">{midTime}</text>
                <text x={width - padR - 28} y={height - 3} fill="#6b7489" fontSize="9" fontFamily="IBM Plex Mono, monospace">{lastTime}</text>
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
    const topBuyers = (payload.top_buyers || []).slice(0, 5);
    const topSellers = (payload.top_sellers || []).slice(0, 5);
    const isWf = isWallsFlowLocalhost();

    return (
        <div className="mw-card" style={{
            flex: 1,
            minWidth: 460,
            padding: "14px 16px",
            display: "flex",
            flexDirection: "column",
            gap: 12,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, borderBottom: "1px solid var(--mw-hairline)", paddingBottom: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="mw-mono" style={{
                        fontSize: 11,
                        fontWeight: 600,
                        padding: "2px 7px",
                        borderRadius: 5,
                        background: symKey === "WIN" ? "var(--mw-accent-soft)" : "rgba(212, 162, 89, 0.12)",
                        border: symKey === "WIN" ? "1px solid var(--mw-accent-border)" : "1px solid rgba(212, 162, 89, 0.30)",
                        color: symKey === "WIN" ? "var(--mw-accent-ink)" : "#d4a259",
                    }}>
                        {payload.active_contract || symKey}
                    </span>
                    <span style={{ fontSize: 13.5, fontWeight: 600, color: "var(--mw-text-1)" }}>
                        Raio-X de microestrutura · {symKey}
                    </span>
                </div>
                {payload.source && (
                    <span className="mw-mono" style={{ fontSize: 10.5, color: "var(--mw-text-2)", background: "var(--mw-chrome)", padding: "2px 8px", borderRadius: 5, border: "1px solid var(--mw-hairline)" }}>
                        {payload.source}
                    </span>
                )}
            </div>

            {/* Tabela de Janelas Temporais (1m, 5m, 15m, 60m, Sessão) */}
            <div style={{ overflowX: "auto" }}>
                <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                    <thead>
                        <tr style={{ color: "var(--mw-text-3)", borderBottom: "1px solid var(--mw-hairline)", textAlign: "right" }}>
                            <th style={{ textAlign: "left", padding: "5px 4px", fontWeight: 500 }}>Janela</th>
                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>Delta total</th>
                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>Lote grande ({symKey === "WIN" ? "≥50L" : "≥20L"})</th>
                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>Varejo</th>
                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>Desequilíbrio</th>
                            <th style={{ textAlign: "right", padding: "5px 4px", fontWeight: 500 }}>Absorção</th>
                        </tr>
                    </thead>
                    <tbody>
                        {["1m", "5m", "15m", "60m"].map(wk => {
                            const w = wins[wk] || {};
                            const hasAbs = String(w.absorption_state || "").includes("ABSORCAO");
                            return (
                                <tr key={wk} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)", textAlign: "right" }}>
                                    <td style={{ textAlign: "left", padding: "5px 4px", fontWeight: 500, color: "var(--mw-text-2)" }}>{wk}</td>
                                    <td style={{ padding: "5px 4px", color: Number(w.delta || 0) >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 600, whiteSpace: "nowrap" }}>{fmtNum(w.delta, 0, true)}</td>
                                    <td style={{ padding: "5px 4px", color: Number(w.inst_delta || 0) >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 600, whiteSpace: "nowrap" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                                    <td style={{ padding: "5px 4px", color: Number(w.ret_delta || 0) >= 0 ? "#38bdf8" : "#d4a259", whiteSpace: "nowrap" }}>{fmtNum(w.ret_delta, 0, true)}</td>
                                    <td style={{ padding: "5px 4px", color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>{fmtNum(w.imbalance_pct, 1, true)}%</td>
                                    <td style={{ padding: "5px 4px", fontSize: 10.5, color: hasAbs ? "#d4a259" : "var(--mw-text-3)", whiteSpace: "nowrap" }}>
                                        {fmtAbsorptionState(w.absorption_state)}
                                    </td>
                                </tr>
                            );
                        })}
                        <tr style={{ textAlign: "right", background: "var(--mw-chrome)", fontWeight: 600 }}>
                            <td style={{ textAlign: "left", padding: "6px 4px", color: "#d4a259" }}>Sessão</td>
                            <td style={{ padding: "6px 4px", color: Number(tot.total_delta || 0) >= 0 ? "#4cc38a" : "#e5484d", whiteSpace: "nowrap" }}>{fmtNum(tot.total_delta, 0, true)}</td>
                            <td style={{ padding: "6px 4px", color: Number(tot.inst_delta || 0) >= 0 ? "#4cc38a" : "#e5484d", whiteSpace: "nowrap" }}>{fmtNum(tot.inst_delta, 0, true)}</td>
                            <td style={{ padding: "6px 4px", color: Number(tot.retail_delta || 0) >= 0 ? "#38bdf8" : "#d4a259", whiteSpace: "nowrap" }}>{fmtNum(tot.retail_delta, 0, true)}</td>
                            <td style={{ padding: "6px 4px", color: "var(--mw-text-2)", fontWeight: 500, whiteSpace: "nowrap" }}>RLP {fmtNum(tot.rlp_vol, 0)}L</td>
                            <td style={{ padding: "6px 4px", fontSize: 10.5, color: "var(--mw-text-3)", fontWeight: 500, whiteSpace: "nowrap" }}>{fmtNum(tot.total_deals, 0)} negócios</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            {/* Top Compradores vs Top Vendedores no Profit */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div style={{ background: "var(--mw-chrome)", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                    <div style={{ fontSize: 11, color: "#4cc38a", fontWeight: 600, marginBottom: 6 }}>Top compradores líquidos</div>
                    {topBuyers.length === 0 ? (
                        <div style={{ fontSize: 11, color: "var(--mw-text-3)", padding: "6px 0" }}>
                            Sem ranking de corretoras no replay histórico.
                        </div>
                    ) : topBuyers.map(b => (
                        <div key={b.broker} className="mw-mono" style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, padding: "3px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", gap: 6 }}>
                            <span style={{ color: b.is_institutional ? "var(--mw-text-1)" : "var(--mw-text-2)", fontWeight: b.is_institutional ? 600 : 400 }}>
                                {b.broker}{b.is_institutional ? " · Inst" : ""}
                            </span>
                            <span style={{ color: "#4cc38a", whiteSpace: "nowrap" }}>
                                +{fmtNum(b.net, 0)} <span style={{ color: "var(--mw-text-3)", fontSize: 9.5 }}>(Agr {fmtNum((b.aggr_buy || 0) - (b.aggr_sell || 0), 0, true)} · Pas {fmtNum((b.passive_buy || 0) - (b.passive_sell || 0), 0, true)})</span>
                            </span>
                        </div>
                    ))}
                </div>
                <div style={{ background: "var(--mw-chrome)", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                    <div style={{ fontSize: 11, color: "#e5484d", fontWeight: 600, marginBottom: 6 }}>Top vendedores líquidos</div>
                    {topSellers.length === 0 ? (
                        <div style={{ fontSize: 11, color: "var(--mw-text-3)", padding: "6px 0" }}>
                            Sem ranking de corretoras no replay histórico.
                        </div>
                    ) : topSellers.map(b => (
                        <div key={b.broker} className="mw-mono" style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, padding: "3px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", gap: 6 }}>
                            <span style={{ color: b.is_institutional ? "var(--mw-text-1)" : "var(--mw-text-2)", fontWeight: b.is_institutional ? 600 : 400 }}>
                                {b.broker}{b.is_institutional ? " · Inst" : ""}
                            </span>
                            <span style={{ color: "#e5484d", whiteSpace: "nowrap" }}>
                                {fmtNum(b.net, 0)} <span style={{ color: "var(--mw-text-3)", fontSize: 9.5 }}>(Agr {fmtNum((b.aggr_buy || 0) - (b.aggr_sell || 0), 0, true)} · Pas {fmtNum((b.passive_buy || 0) - (b.passive_sell || 0), 0, true)})</span>
                            </span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Escada Completa de MagicWalls Próximas */}
            <div style={{ overflowX: "auto" }}>
                <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 10.5 }}>
                    <thead>
                        <tr style={{ color: "var(--mw-text-3)", borderBottom: "1px solid var(--mw-hairline)", textAlign: "right" }}>
                            <th style={{ textAlign: "left", padding: "4px", fontWeight: 500 }}>Parede</th>
                            <th style={{ padding: "4px", fontWeight: 500 }}>Preço</th>
                            <th style={{ padding: "4px", fontWeight: 500 }}>Dist.</th>
                            {isWf ? (
                                <>
                                    <th style={{ padding: "4px", fontWeight: 500 }}>Inst (Agr / Pas)</th>
                                    <th style={{ padding: "4px", fontWeight: 500 }}>Var</th>
                                    <th style={{ padding: "4px", fontWeight: 500 }}>HFT / RLP</th>
                                    <th style={{ textAlign: "right", padding: "4px", fontWeight: 500 }}>Assinatura 4-players</th>
                                </>
                            ) : (
                                <>
                                    <th style={{ padding: "4px", fontWeight: 500 }}>GEX</th>
                                    <th style={{ padding: "4px", fontWeight: 500 }}>Delta Inst</th>
                                    <th style={{ padding: "4px", fontWeight: 500 }}>Status</th>
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
                                <tr key={`r-${i}`} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)", textAlign: "right" }}>
                                    <td style={{ textAlign: "left", padding: "4px", color: "#e5484d", fontWeight: 600, whiteSpace: "nowrap" }}>Res · {w.type}</td>
                                    <td style={{ padding: "4px", color: "var(--mw-text-1)", fontWeight: 600, whiteSpace: "nowrap" }}>{fmtNum(w.price, dec)}</td>
                                    <td style={{ padding: "4px", color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>{fmtNum(w.dist_pts, dec, true)}p</td>
                                    {isWf ? (
                                        <>
                                            <td style={{ padding: "4px", color: (w.inst_aggr_delta ?? w.inst_delta ?? 0) >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 500, whiteSpace: "nowrap" }}>
                                                {fmtNum(w.inst_aggr_delta ?? w.inst_delta ?? 0, 0, true)} / <span style={{ color: (w.inst_pass_delta ?? 0) >= 0 ? "#38bdf8" : "#e5484d" }}>{fmtNum(w.inst_pass_delta ?? 0, 0, true)}</span>
                                            </td>
                                            <td style={{ padding: "4px", color: (w.ret_delta ?? 0) >= 0 ? "#38bdf8" : "#d4a259", whiteSpace: "nowrap" }}>{fmtNum(w.ret_delta ?? 0, 0, true)}</td>
                                            <td style={{ padding: "4px", color: "#a78bfa", whiteSpace: "nowrap" }} title={`Giro Bruto HFT: ${fmtNum(w.hft_churn_pct ?? 0, 0)}% | Participação RLP: ${fmtNum(w.rlp_share_pct ?? w.rlp_pct ?? 0, 0)}%`}>
                                                {fmtNum(w.hft_delta ?? 0, 0, true)} / <span style={{ color: "#d4a259" }}>{fmtNum(w.rlp_delta ?? Math.round(-Number(w.ret_delta ?? 0) * (Number(w.rlp_share_pct ?? w.rlp_pct ?? 0) / 100.0)), 0, true)}</span>
                                            </td>
                                            <td style={{ padding: "4px", color: "var(--mw-text-2)", fontSize: 10 }}>
                                                {stripUiEmoji(w.player_verdict || w.status)} {topB ? <span style={{ color: "#d4a259" }}>({topB})</span> : null}
                                            </td>
                                        </>
                                    ) : (
                                        <>
                                            <td style={{ padding: "4px", color: "#38bdf8" }}>{w.gex_formatted || "—"}</td>
                                            <td style={{ padding: "4px", color: (w.inst_delta || 0) >= 0 ? "#4cc38a" : "#e5484d" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                                            <td style={{ padding: "4px", color: "var(--mw-text-2)" }}>{w.status}</td>
                                        </>
                                    )}
                                </tr>
                            );
                        })}
                        <tr style={{ background: "var(--mw-accent-soft)", textAlign: "center", fontWeight: 600 }}>
                            <td colSpan={isWf ? 7 : 6} style={{ padding: "5px 6px", color: "var(--mw-accent-ink)" }}>
                                Preço spot: {fmtNum(payload.last_price, dec)} · VWAP {fmtNum(payload.vwap, dec)}
                            </td>
                        </tr>
                        {supWalls.map((w, i) => {
                            const topB = Array.isArray(w.top_wall_brokers) && w.top_wall_brokers.length > 0
                                ? w.top_wall_brokers.slice(0, 2).map(b => `${b.broker}(${b.net >= 0 ? "+" : ""}${Math.round(b.net)})`).join(" ")
                                : "";
                            return (
                                <tr key={`s-${i}`} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)", textAlign: "right" }}>
                                    <td style={{ textAlign: "left", padding: "4px", color: "#4cc38a", fontWeight: 600, whiteSpace: "nowrap" }}>Sup · {w.type}</td>
                                    <td style={{ padding: "4px", color: "var(--mw-text-1)", fontWeight: 600, whiteSpace: "nowrap" }}>{fmtNum(w.price, dec)}</td>
                                    <td style={{ padding: "4px", color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>{fmtNum(w.dist_pts, dec, true)}p</td>
                                    {isWf ? (
                                        <>
                                            <td style={{ padding: "4px", color: (w.inst_aggr_delta ?? w.inst_delta ?? 0) >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 500, whiteSpace: "nowrap" }}>
                                                {fmtNum(w.inst_aggr_delta ?? w.inst_delta ?? 0, 0, true)} / <span style={{ color: (w.inst_pass_delta ?? 0) >= 0 ? "#38bdf8" : "#e5484d" }}>{fmtNum(w.inst_pass_delta ?? 0, 0, true)}</span>
                                            </td>
                                            <td style={{ padding: "4px", color: (w.ret_delta ?? 0) >= 0 ? "#38bdf8" : "#d4a259", whiteSpace: "nowrap" }}>{fmtNum(w.ret_delta ?? 0, 0, true)}</td>
                                            <td style={{ padding: "4px", color: "#a78bfa", whiteSpace: "nowrap" }} title={`Giro Bruto HFT: ${fmtNum(w.hft_churn_pct ?? 0, 0)}% | Participação RLP: ${fmtNum(w.rlp_share_pct ?? w.rlp_pct ?? 0, 0)}%`}>
                                                {fmtNum(w.hft_delta ?? 0, 0, true)} / <span style={{ color: "#d4a259" }}>{fmtNum(w.rlp_delta ?? Math.round(-Number(w.ret_delta ?? 0) * (Number(w.rlp_share_pct ?? w.rlp_pct ?? 0) / 100.0)), 0, true)}</span>
                                            </td>
                                            <td style={{ padding: "4px", color: "var(--mw-text-2)", fontSize: 10 }}>
                                                {stripUiEmoji(w.player_verdict || w.status)} {topB ? <span style={{ color: "#d4a259" }}>({topB})</span> : null}
                                            </td>
                                        </>
                                    ) : (
                                        <>
                                            <td style={{ padding: "4px", color: "#38bdf8" }}>{w.gex_formatted || "—"}</td>
                                            <td style={{ padding: "4px", color: (w.inst_delta || 0) >= 0 ? "#4cc38a" : "#e5484d" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                                            <td style={{ padding: "4px", color: "var(--mw-text-2)" }}>{w.status}</td>
                                        </>
                                    )}
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* Gráfico CVD 4-Players */}
            <MiniSvgChart
                series={ca.m5_dealer_vs_flow_series || []}
                keys={isWf
                    ? ["cvd_inst_aggr", "cvd_inst_pass", "cvd_retail", "cvd_hft", "cvd_rlp_delta"]
                    : ["cvd_inst", "cum_dealer_hedge", "cvd_retail"]}
                colors={isWf
                    ? ["#4cc38a", "#38bdf8", "#e09153", "#a78bfa", "#d4a259"]
                    : ["#4cc38a", "#d4a259", "#38bdf8"]}
                labels={isWf
                    ? ["Inst Agressor (L)", "Inst Passivo (L)", "Varejo (L)", "HFT (L)", "RLP (L)"]
                    : ["CVD Institucional", "Hedge Dealers (GEX)", "CVD Varejo"]}
                height={110}
            />
        </div>
    );
}

/* ── COMPONENTE PRINCIPAL EXPORTADO ────────────────────────────────────────── */
function IntradayCompassPanel({
    compassData,
    mode = "COCKPIT",
    onChangeMode,
    selectedDate = "",
    onSelectDate,
    selectedAssetProp,
    onSelectAssetProp,
    dualLayout = "stacked",
}) {
    const [internalSelectedAsset, setInternalSelectedAsset] = useState(() => (isWallsFlowLocalhost() ? "DUAL" : "WIN")); // "WIN" | "WDO" | "DUAL"
    const selectedAsset = selectedAssetProp !== undefined ? selectedAssetProp : internalSelectedAsset;
    const setSelectedAsset = onSelectAssetProp || setInternalSelectedAsset;

    if (!compassData || !compassData.WIN) {
        return (
            <div className="mw-card" style={{ padding: 24, color: "var(--mw-text-2)", fontSize: 13, textAlign: "center" }}>
                Inicializando painel Magic Walls...
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
    const activeDate = selectedDate || "";
    const activeDisplayDate = activeDate || compassData.selected_date || todayDateStr || "";
    const isHistView = Boolean(activeDate && activeDate !== todayDateStr) || Boolean(compassData.is_historical);
    const winHasBars = (winP?.caminho_a?.m5_dealer_vs_flow_series?.length || 0) > 0;
    const wdoHasBars = (wdoP?.caminho_a?.m5_dealer_vs_flow_series?.length || 0) > 0;
    const hasAnySessionBars = winHasBars || wdoHasBars;

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

    // Cartão Seletor de Ativo no Topo (apenas fora do modo manual, onde os controles vivem na Topbar unificada)
    const renderAssetSelectorButton = (symKey, p) => {
        if (!p) return null;
        const isSel = selectedAsset === symKey;
        const dec = symKey === "WDO" ? 1 : 0;
        const ca = p.caminho_a || {};
        const hud = ca.asg_hud || {};
        const cmd = hud.command || "NEUTRALIZADO";
        const cmdColor = cmd === "COMPRA" ? "var(--mw-pos)" : cmd === "VENDA" ? "var(--mw-neg)" : "var(--mw-accent-ink)";

        return (
            <div
                key={symKey}
                className="mw-card"
                onClick={() => setSelectedAsset(symKey)}
                style={{
                    flex: 1,
                    minWidth: 280,
                    background: isSel ? "var(--mw-raised)" : "var(--mw-card)",
                    border: isSel ? "1px solid var(--mw-accent-border)" : "1px solid var(--mw-hairline)",
                    padding: "12px 16px",
                    cursor: "pointer",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 12,
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span className="mw-mono" style={{
                        fontSize: 12,
                        fontWeight: 600,
                        color: isSel ? "var(--mw-accent-on)" : "var(--mw-accent-ink)",
                        background: isSel ? "var(--mw-accent)" : "var(--mw-accent-soft)",
                        border: "1px solid var(--mw-accent-border)",
                        padding: "4px 8px",
                        borderRadius: 6,
                    }}>
                        {symKey === "WIN" ? "Índice" : "Dólar"} · {p.active_contract}
                    </span>
                    <div>
                        <div className="mw-mono" style={{ fontSize: 20, fontWeight: 500, color: "var(--mw-text-1)", lineHeight: 1.15 }}>
                            {fmtNum(p.last_price, dec)}
                        </div>
                        <div className="mw-mono" style={{ fontSize: 12, color: "var(--mw-text-3)", marginTop: 2 }}>
                            VWAP {fmtNum(p.vwap, dec)}
                        </div>
                    </div>
                </div>

                <div style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    background: "var(--mw-chrome)",
                    border: "1px solid var(--mw-hairline)",
                    padding: "4px 10px",
                    borderRadius: 6,
                }}>
                    <span style={{ width: 6, height: 6, borderRadius: 999, background: cmdColor, display: "inline-block" }} />
                    <span style={{ fontSize: 12, fontWeight: 500, color: "var(--mw-text-1)" }}>
                        {cmd === "COMPRA" ? "Compra" : cmd === "VENDA" ? "Venda" : "Neutro"}
                    </span>
                </div>
            </div>
        );
    };

    const isManualHost = isManualChartMode();
    const curDateIdx = availableDates.indexOf(activeDisplayDate);
    const prevAvailableDates = availableDates
        .filter((d, idx) => d !== activeDisplayDate && (curDateIdx < 0 || idx > curDateIdx))
        .slice(0, 3);
    const primaryFallbackDate = prevAvailableDates[0] || availableDates.find((d) => d !== activeDisplayDate) || "";

    return (
        <div className="rb-fade-up" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* ── SELETOR RÁPIDO DE ATIVO NO TOPO (apenas modos não-manual; datas vivem na Topbar unificada) ── */}
            {mode === "COCKPIT" && !isManualHost && (
                <div style={{ display: "flex", gap: 10, alignItems: "stretch", flexWrap: "wrap" }}>
                    {renderAssetSelectorButton("WIN", winP)}
                    {renderAssetSelectorButton("WDO", wdoP)}
                    <button
                        type="button"
                        className="mw-btn mw-btn-top"
                        data-active={selectedAsset === "DUAL" ? "true" : "false"}
                        onClick={() => setSelectedAsset(selectedAsset === "DUAL" ? "WIN" : "DUAL")}
                        style={{ height: "auto", padding: "0 18px", borderRadius: 10, border: "1px solid var(--mw-hairline)", fontWeight: 500 }}
                    >
                        {selectedAsset === "DUAL" ? "Visão dupla ativa" : "WIN + WDO"}
                    </button>
                </div>
            )}

            {/* Banner discreto de replay (apenas fora do modo manual, pois a topbar manual já sinaliza Replay) */}
            {isHistView && !isManualHost && (
                <div
                    className="mw-card"
                    style={{
                        padding: "8px 16px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        flexWrap: "wrap",
                        gap: 8,
                    }}
                >
                    <span className="mw-mono" style={{ fontSize: 12, color: "var(--mw-text-2)" }}>
                        Replay histórico · Pregão de <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{fmtDateFull(activeDisplayDate)}</strong>
                    </span>
                    <button
                        type="button"
                        className="mw-btn mw-btn-secondary"
                        onClick={() => handleDatePick("")}
                    >
                        Voltar para hoje
                    </button>
                </div>
            )}

            {/* ── MODO 1: COCKPIT OPERACIONAL ──────────── */}
            {mode === "COCKPIT" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    {!hasAnySessionBars ? (
                        <section
                            className="mw-card"
                            style={{
                                padding: "48px 24px",
                                display: "flex",
                                flexDirection: "column",
                                alignItems: "center",
                                textAlign: "center",
                                gap: 16,
                            }}
                        >
                            <div style={{
                                width: 40,
                                height: 40,
                                borderRadius: 10,
                                backgroundColor: "var(--mw-accent-soft)",
                                border: "1px solid var(--mw-accent-border)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                color: "var(--mw-accent-ink)",
                            }}>
                                <IconCalendar />
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 460 }}>
                                <h1 style={{ margin: 0, fontSize: 20, fontWeight: 500, lineHeight: 1.25, color: "var(--mw-text-1)" }}>
                                    Sem barras no pregão de {fmtDateFull(activeDisplayDate)}
                                </h1>
                                <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5, color: "var(--mw-text-2)" }}>
                                    A B3 pode estar fechada (fim de semana ou feriado) ou o pregão ainda não possui barras M5 registradas.
                                </p>
                            </div>
                            {primaryFallbackDate && (
                                <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 8, alignItems: "center" }}>
                                    <button
                                        type="button"
                                        className="mw-btn-primary"
                                        onClick={() => handleDatePick(primaryFallbackDate)}
                                    >
                                        <span>Abrir pregão anterior · {fmtDateShort(primaryFallbackDate)}</span>
                                        <IconArrowRight />
                                    </button>
                                    {prevAvailableDates.slice(1).map((d) => (
                                        <button
                                            key={d}
                                            type="button"
                                            className="mw-btn mw-btn-secondary mw-mono"
                                            style={{ height: 36, padding: "0 12px" }}
                                            onClick={() => handleDatePick(d)}
                                        >
                                            {fmtDateShort(d)}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </section>
                    ) : selectedAsset === "DUAL" ? (
                        <div className={isManualHost && dualLayout === "split" ? "mw-grid-dual-split" : "mw-grid-stacked"}>
                            {!isManualHost && <CombinedPortfolioDayCard winPayload={winP} wdoPayload={wdoP} />}
                            <SingleAssetCockpitView
                                symKey="WIN"
                                payload={winP}
                                manualMode={isManualHost}
                                isSideBySide={isManualHost && dualLayout === "split"}
                                sessionDateOverride={activeDate || compassData.selected_date || todayDateStr || ""}
                                compassData={compassData}
                            />
                            <SingleAssetCockpitView
                                symKey="WDO"
                                payload={wdoP}
                                manualMode={isManualHost}
                                isSideBySide={isManualHost && dualLayout === "split"}
                                sessionDateOverride={activeDate || compassData.selected_date || todayDateStr || ""}
                                compassData={compassData}
                            />
                        </div>
                    ) : (
                        <SingleAssetCockpitView
                            symKey={selectedAsset}
                            payload={selectedAsset === "WIN" ? winP : wdoP}
                            manualMode={isManualHost}
                            isSideBySide={false}
                            sessionDateOverride={activeDate || compassData.selected_date || todayDateStr || ""}
                            compassData={compassData}
                        />
                    )}
                    {!isManualHost && (
                        <Portfolio4SistematicasPanel
                            portfolioData={compassData?.portfolio_4_sistematicas}
                            winPayload={winP}
                            wdoPayload={wdoP}
                            onSelectDate={handleDatePick}
                        />
                    )}
                </div>
            )}

            {/* ── MODO 2: RAIO-X DE DADOS (TABELAS COMPLETAS PROFIT + GRADE OPÇÕES) ── */}
            {mode === "RAIO_X" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                        <RaioXAssetCard symKey="WIN" payload={winP} />
                        <RaioXAssetCard symKey="WDO" payload={wdoP} />
                    </div>

                    {/* Grade Completa de Opções BOVA11 */}
                    {cb && cb.ok && (
                        <div className="mw-card" style={{
                            padding: "14px 16px",
                            display: "flex",
                            flexDirection: "column",
                            gap: 12,
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, borderBottom: "1px solid var(--mw-hairline)", paddingBottom: 10 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                                    <span style={{
                                        fontSize: 13,
                                        fontWeight: 600,
                                        color: "var(--mw-text-1)",
                                    }}>
                                        Grade de opções · BOVA11 → WIN
                                    </span>
                                    <span className="mw-mono" style={{ fontSize: 12, color: "var(--mw-text-1)", fontWeight: 500 }}>
                                        BOVA11 R$ {fmtNum(bova.spot, 2)} ({fmtNum(bova.change_pct, 2, true)}%)
                                    </span>
                                    <span className="mw-mono" style={{ fontSize: 11, color: "var(--mw-text-3)" }}>
                                        Fator {fmtNum(bova.win_ibov_ratio, 1)}x · {optComp.monitored_series_count} séries líquidas
                                    </span>
                                </div>
                                <span className="mw-mono" style={{
                                    fontSize: 11,
                                    fontWeight: 600,
                                    padding: "3px 9px",
                                    borderRadius: 6,
                                    background: `${scoreColor(optComp.score)}18`,
                                    border: `1px solid ${scoreColor(optComp.score)}44`,
                                    color: scoreColor(optComp.score),
                                }}>
                                    Score {fmtNum(optComp.score, 1, true)} · {optComp.verdict}
                                </span>
                            </div>

                            <div className="mw-mono" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 }}>
                                <div style={{ background: "var(--mw-chrome)", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                                    <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>IV ATM</div>
                                    <div style={{ fontSize: 15, fontWeight: 600, color: "#38bdf8", marginTop: 2 }}>{fmtNum(volSurf.atm_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "var(--mw-chrome)", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                                    <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>IV Put 25Δ (OTM)</div>
                                    <div style={{ fontSize: 15, fontWeight: 600, color: "#e5484d", marginTop: 2 }}>{fmtNum(volSurf.put_25d_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "var(--mw-chrome)", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                                    <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>IV Call 25Δ (OTM)</div>
                                    <div style={{ fontSize: 15, fontWeight: 600, color: "#4cc38a", marginTop: 2 }}>{fmtNum(volSurf.call_25d_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "var(--mw-chrome)", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                                    <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>Skew 25Δ (Put − Call)</div>
                                    <div style={{ fontSize: 15, fontWeight: 600, color: "#d4a259", marginTop: 2 }}>{fmtNum(volSurf.skew_25d_pct, 2, true)}%</div>
                                </div>
                                <div style={{ background: "var(--mw-chrome)", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                                    <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>PCR volume total</div>
                                    <div style={{ fontSize: 15, fontWeight: 600, color: "var(--mw-text-1)", marginTop: 2 }}>{fmtNum(optComp.pcr_total_volume, 2)}</div>
                                </div>
                                <div style={{ background: "var(--mw-chrome)", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                                    <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>PCR compra agressiva</div>
                                    <div style={{ fontSize: 15, fontWeight: 600, color: (optComp.pcr_aggressive_buy || 0) > 1.15 ? "#e5484d" : "#4cc38a", marginTop: 2 }}>
                                        {fmtNum(optComp.pcr_aggressive_buy, 2)}
                                    </div>
                                </div>
                            </div>

                            <div style={{ overflowX: "auto" }}>
                                <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 10.5 }}>
                                    <thead>
                                        <tr style={{ color: "var(--mw-text-3)", borderBottom: "1px solid var(--mw-hairline)", textAlign: "right" }}>
                                            <th style={{ textAlign: "left", padding: "5px 4px", fontWeight: 500 }}>Série</th>
                                            <th style={{ textAlign: "center", padding: "5px 4px", fontWeight: 500 }}>Tipo</th>
                                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>Strike BOVA</th>
                                            <th style={{ padding: "5px 4px", color: "#38bdf8", fontWeight: 500 }}>≈ Strike WIN</th>
                                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>Bid / Ask</th>
                                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>IV%</th>
                                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>Delta (Δ)</th>
                                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>Negócios</th>
                                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>Saldo agressão</th>
                                            <th style={{ padding: "5px 4px", fontWeight: 500 }}>Fluxo delta equiv.</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(cb.most_active_options || []).slice(0, 12).map(row => {
                                            const isCall = row.type === "CALL";
                                            const isBullImpact = (row.delta_equiv_flow || 0) > 0;
                                            return (
                                                <tr key={row.symbol} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)", textAlign: "right" }}>
                                                    <td style={{ textAlign: "left", padding: "5px 4px", fontWeight: 600, color: "var(--mw-text-1)" }}>{row.symbol}</td>
                                                    <td style={{ textAlign: "center", padding: "5px 4px", color: isCall ? "#38bdf8" : "#e5484d", fontWeight: 600 }}>{row.type}</td>
                                                    <td style={{ padding: "5px 4px", color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>R$ {fmtNum(row.strike_bova, 1)}</td>
                                                    <td style={{ padding: "5px 4px", color: "#38bdf8", fontWeight: 600, whiteSpace: "nowrap" }}>{fmtNum(row.equiv_win_strike, 0)}</td>
                                                    <td style={{ padding: "5px 4px", color: "var(--mw-text-3)", whiteSpace: "nowrap" }}>{fmtNum(row.bid, 2)} / {fmtNum(row.ask, 2)}</td>
                                                    <td style={{ padding: "5px 4px", color: "#d4a259", whiteSpace: "nowrap" }}>{fmtNum(row.iv_pct, 1)}%</td>
                                                    <td style={{ padding: "5px 4px", color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>{fmtNum(row.delta, 2, true)}</td>
                                                    <td style={{ padding: "5px 4px", color: "var(--mw-text-3)", whiteSpace: "nowrap" }}>{fmtNum(row.deals, 0)}</td>
                                                    <td style={{ padding: "5px 4px", color: row.net_aggr_vol >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 600, whiteSpace: "nowrap" }}>
                                                        {fmtNum(row.net_aggr_vol, 0, true)} ({fmtNum(row.imbalance_pct, 1, true)}%)
                                                    </td>
                                                    <td style={{ padding: "5px 4px", color: isBullImpact ? "#4cc38a" : "#e5484d", fontWeight: 600, whiteSpace: "nowrap" }}>
                                                        {fmtNum(row.delta_equiv_flow, 0, true)}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default memo(IntradayCompassPanel);
