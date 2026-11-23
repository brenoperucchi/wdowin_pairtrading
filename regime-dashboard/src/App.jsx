import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { ref, onValue, get } from "firebase/database";
import { db } from "./firebase";
import ZScoreChart from "./components/ZScoreChart";
import RegimeHealthPanel from "./components/RegimeHealthPanel";
import SignalHistogram from "./components/SignalHistogram";
import IndexChart from "./components/IndexChart";
import SetupMatadorPanel from "./components/SetupMatadorPanel";
import IntradayCompassPanel from "./components/IntradayCompassPanel";
import LiveTradingCalendar from "./components/LiveTradingCalendar";
import StatArbBacktest2026Panel from "./components/StatArbBacktest2026Panel";
import StatArbLiveTradePanel from "./components/StatArbLiveTradePanel";
import MorningWallsVideoModal from "./components/MorningWallsVideoModal";
import MagicWallsMark from "./components/MagicWallsMark";
import { API_BASE, isManualChartMode, isWallsFlowMode } from "./apiBase";
import { authFetch, canAccessMediaStudio, isSaasAuthEnabled } from "./utils/saasAuth";
import { simulateDayStatArbTradesJs, normalizeStatArbTrade } from "./utils/statArbDayTrades";

const STRAT_LABELS = {
    CONS_BASE: { label: "CONS", color: "#38bdf8" },
    WDO_NWE: { label: "WDO", color: "#d4a259" },
    DI_NWE: { label: "DI", color: "#a78bfa" },
};

const API_URL = `${API_BASE}/api/v2/regime`;
const API_PERF_URL = `${API_BASE}/api/performance`;
const API_DI_URL = `${API_BASE}/api/di-regime`;
const API_HISTORY_URL = `${API_BASE}/api/history`;
const API_COMPASS_URL = `${API_BASE}/api/compass/etapa1`;
const POLL_MS = 2500;
// Quando compilado com VITE_API_BASE definido (ex: "" para túnel cloudflared + proxy somente-leitura),
// usa a API relativa (/api/...) em vez do Firebase Hosting estático.
const USE_FIREBASE = Boolean(db) && import.meta.env.PROD && import.meta.env.VITE_API_BASE === undefined && !isSaasAuthEnabled();

function alignTimestampTo2025(epochSeconds) {
    if (!epochSeconds) return 0;
    const d = new Date(epochSeconds * 1000);
    const h = d.getHours();
    const m = d.getMinutes();
    const s = d.getSeconds();
    return Math.floor(Date.UTC(2025, 0, 1, h, m, s) / 1000);
}

function timeStrToTimestamp(timeStr) {
    if (!timeStr) return 0;
    const [h, m] = timeStr.split(':').map(Number);
    return Math.floor(new Date(Date.UTC(2025, 0, 1, h, m)).getTime() / 1000);
}

// ── Fallback: gera dados simulados se a API não responder ────────────────────
function marketBarTimes(n, barMinutes = 5) {
    const SESSION_START = 9 * 60;
    const SESSION_END = 18 * 60 + 20;
    const SESSION_MINS = SESSION_END - SESSION_START;
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    let anchorMin = Math.min(nowMin, SESSION_END);
    if (nowMin < SESSION_START) anchorMin = SESSION_END;
    const times = [];
    for (let i = n - 1; i >= 0; i--) {
        let t = anchorMin - i * barMinutes;
        while (t < SESSION_START) t += SESSION_MINS;
        t = SESSION_START + ((t - SESSION_START) % SESSION_MINS);
        const h = String(Math.floor(t / 60)).padStart(2, "0");
        const m = String(t % 60).padStart(2, "0");
        times.push(`${h}:${m}`);
    }
    return times;
}

function genFallback(n = 120) {
    const arr = [];
    let s = 0;
    const times = marketBarTimes(n, 5);
    for (let i = 0; i < n; i++) {
        const spike = Math.random() < 0.015 ? (Math.random() > 0.5 ? 3.2 : -3.2) : 0;
        s = s + 0.07 * -s + spike + (Math.random() - 0.5) * 1.2;
        const win = 130000 + Math.sin(i / 10) * 1000 + Math.random() * 200;
        arr.push({ i, spread: +s.toFixed(3), bar_time: times[i], win_price: win });
    }
    const W = 40;
    return arr.map((d, idx) => {
        if (idx < W) return { ...d, z: 0 };
        const sl = arr.slice(idx - W, idx).map(x => x.spread);
        const mu = sl.reduce((a, b) => a + b, 0) / W;
        const sd = Math.sqrt(sl.map(v => (v - mu) ** 2).reduce((a, b) => a + b, 0) / W) || 0.01;
        return { ...d, z: +((d.spread - mu) / sd).toFixed(3) };
    });
}

function getSignal(z) {
    const az = Math.abs(z);
    if (az >= 4) return { id: "anomalia", label: "ANOMALIA", sub: "Não operar — possível breakdown", wdo: null, win: null, color: "#e5484d" };
    if (z >= 1.4) return { id: "compraWdo", label: "VENDE WIN", sub: "Z-Score positivo — spread revertendo", wdo: "IGNORAR", win: "VENDER", color: "#e5484d" };
    if (z <= -1.4) return { id: "compraWin", label: "COMPRA WIN", sub: "Z-Score negativo — spread revertendo", wdo: "IGNORAR", win: "COMPRAR", color: "#4cc38a" };
    if (az >= 1.2) return { id: "atencao", label: "ZONA DE DIVERGENCIA", sub: "Aguardar Z atingir +/-1.4 para entrar", wdo: null, win: null, color: "#d4a259" };
    return { id: "neutro", label: "AGUARDAR", sub: "Spread em equilibrio — sem setup no momento", wdo: null, win: null, color: "#848da2" };
}

// ── Main App ────────────────────────────────────────────────────────────────

// Limite máximo de barras no histórico completo para evitar OOM
const MAX_FULL_HISTORY = 3000;

function TopbarClock() {
    const [clock, setClock] = useState(() => new Date().toLocaleTimeString("pt-BR", { hour12: false }));
    useEffect(() => {
        const t = setInterval(() => setClock(new Date().toLocaleTimeString("pt-BR", { hour12: false })), 1000);
        return () => clearInterval(t);
    }, []);
    return <span className="mw-mono" style={{ fontSize: 12, fontWeight: 400, color: "var(--mw-text-3)", minWidth: 60, textAlign: "right" }}>{clock}</span>;
}

function fmtDateShortBr(dStr) {
    if (!dStr || typeof dStr !== "string" || !dStr.includes("-")) return dStr || "";
    const [, m, d] = dStr.split("-");
    return `${d}/${m}`;
}

function fmtDateFullBr(dStr) {
    if (!dStr || typeof dStr !== "string" || !dStr.includes("-")) return dStr || "";
    const [y, m, d] = dStr.split("-");
    return `${d}/${m}/${y}`;
}

export default function App() {

    const [data, setData] = useState(null);
    const [history, setHistory] = useState(() => genFallback());
    const blink = true;
    const [status, setStatus] = useState("connecting");
    const [error, setError] = useState(null);
    const [perf, setPerf] = useState(null);
    const [lastUpdate, setLastUpdate] = useState(null);
    const [flash, setFlash] = useState(false);
    const [lastSignalId, setLastSignalId] = useState("neutro");
    const [diData, setDiData] = useState(null);
    const [realtimeIafData, setRealtimeIafData] = useState([]);
    const [iafSmoothing, setIafSmoothing] = useState(3); // Default 3 periods
    const [selectedDate, setSelectedDate] = useState("");  // "" = HOJE (live)
    const [showMorningVideoModal, setShowMorningVideoModal] = useState(false);
    const [canUseMediaStudio, setCanUseMediaStudio] = useState(() => canAccessMediaStudio());
    useEffect(() => {
        const sync = (ev) => setCanUseMediaStudio(canAccessMediaStudio(ev?.detail?.user));
        window.addEventListener("mw-saas-auth-updated", sync);
        return () => window.removeEventListener("mw-saas-auth-updated", sync);
    }, []);
    const [histDates, setHistDates] = useState([]);
    const [histDayData, setHistDayData] = useState(null);
    const [histLoading, setHistLoading] = useState(false);
    const [fullHistory, setFullHistory] = useState([]);
    const flashTimerRef = useRef(null);
    const audioCtxRef = useRef(null);
    const zScoreChartRef = useRef(null);
    const histogramChartRef = useRef(null);
    const indexChartRef = useRef(null);
    const flowAccelerationChartRef = useRef(null);
    const [showSetup, setShowSetup] = useState(false);
    const [workspaceTab, setWorkspaceTab] = useState("COCKPIT"); // "COCKPIT" | "RAIO_X" | "STAT_ARB"
    const [compassData, setCompassData] = useState(null);
    const [compassError, setCompassError] = useState(null);
    const btDaysRef = useRef(null);
    const btComparisonRef = useRef([]);
    const cachedPortfolioRef = useRef(null);
    const cachedPortfolioSigRef = useRef("");
    const [gexWalls, setGexWalls] = useState([]);
    const [assetView, setAssetView] = useState(() => (typeof window !== "undefined" && window.innerWidth < 760 ? "WIN" : "DUAL"));
    const [dualLayout, setDualLayout] = useState("stacked"); // "stacked" | "split"
    const [winWidth, setWinWidth] = useState(() => (typeof window !== "undefined" ? window.innerWidth : 1440));

    useEffect(() => {
        const onResize = () => setWinWidth(window.innerWidth || 1440);
        window.addEventListener("resize", onResize);
        return () => window.removeEventListener("resize", onResize);
    }, []);

    const isNarrowScreen = winWidth < 760;
    const canSplitDual = winWidth >= 1120;
    const effectiveAssetView = isNarrowScreen && assetView === "DUAL" ? "WIN" : assetView;

    const isManual = isManualChartMode();
    const isWallsFlow = isWallsFlowMode();
    const isViewingHistory = selectedDate !== "";

    // Listener or Fetcher for GEX Walls
    useEffect(() => {
        if (isManual) return undefined;
        if (USE_FIREBASE) {
            const wallsRef = ref(db, 'daily_levels/win_gex');
            const unsub = onValue(wallsRef, (snapshot) => {
                const data = snapshot.val();
                if (data) {
                    const list = Array.isArray(data) ? data : (data.walls ? Object.values(data.walls) : Object.values(data));
                    setGexWalls(list.filter(w => w && typeof w === 'object' && w.price !== undefined));
                } else {
                    setGexWalls([]);
                }
            });
            return () => unsub();
        } else {
            let active = true;
            async function fetchLocalWalls() {
                try {
                    const res = await authFetch(`${API_BASE}/api/gex-walls`);
                    if (res.ok) {
                        const data = await res.json();
                        if (active) setGexWalls(data || []);
                    }
                } catch (e) {
                    console.error("Erro ao carregar GEX walls locais:", e);
                }
            }
            fetchLocalWalls();
            const t = setInterval(fetchLocalWalls, 10000); // Poll local server every 10s
            return () => { active = false; clearInterval(t); };
        }
    }, [isManual]);


    // Polling da API (Local) ou Listener (Firebase Produção)
    useEffect(() => {
        if (isManual) return undefined;
        let active = true;
        let pollInFlight = false;

        if (USE_FIREBASE && !isViewingHistory) {
            // Em produÃ§Ã£o (Firebase Hosting), ouvir o Realtime Database
            const dashboardRef = ref(db, 'dashboard');
            const unsub = onValue(dashboardRef, (snapshot) => {
                if (!active) return;
                const val = snapshot.val();
                if (val) {
                    if (val.error) {
                        setError(val.error);
                        setStatus("fallback");
                    } else {
                        setData(val.regime);
                        setHistory(val.regime?.history || []);
                        if (val.performance && !val.performance.error) setPerf(val.performance);
                        if (val.di_regime && !val.di_regime.error) setDiData(val.di_regime);
                        if (val.compass && val.compass.ok) setCompassData(val.compass);
                        setStatus("live");
                        setError(null);
                        if (val.regime?.last_update) {
                            setLastUpdate(val.regime.last_update);
                            setFlash(true);
                            if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
                            flashTimerRef.current = setTimeout(() => setFlash(false), 600);
                        }
                    }
                } else {
                    setStatus("fallback");
                    setError("Aguardando dados do Firebase...");
                }
            }, (err) => {
                if (!active) return;
                setStatus("fallback");
                setError("Erro ao conectar no Firebase.");
            });
            return () => { active = false; unsub(); };
        } else {
            // Em localhost ou modo histórico, fazer polling da API
            async function poll() {
                if (pollInFlight) return;
                pollInFlight = true;
                const ctrl = new AbortController();
                const timer = setTimeout(() => ctrl.abort(), 8000);
                try {
                    const currentApiUrl = API_URL;
                    const [res, resPerf, resDi] = await Promise.all([
                        authFetch(currentApiUrl, { signal: ctrl.signal }).catch(() => null),
                        authFetch(API_PERF_URL, { signal: ctrl.signal }).catch(() => null),
                        authFetch(API_DI_URL, { signal: ctrl.signal }).catch(() => null),
                    ]);
                    if (!res || !res.ok) throw new Error(`HTTP ${res?.status}`);
                    const json = await res.json();
                    const jsonPerf = resPerf && resPerf.ok ? await resPerf.json() : null;
                    if (!active) return;
                    if (json.error) {
                        setError(json.error);
                        setStatus("fallback");
                    } else {
                        setData(json);
                        setHistory(json.history || []);
                        if (jsonPerf && !jsonPerf.error) setPerf(jsonPerf);
                        // DI data
                        const jsonDi = resDi && resDi.ok ? await resDi.json() : null;
                        if (jsonDi && !jsonDi.error) setDiData(jsonDi);
                        setStatus("live");
                        setError(null);
                        if (json.last_update) {
                            setLastUpdate(json.last_update);
                            setFlash(true);
                            if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
                            flashTimerRef.current = setTimeout(() => setFlash(false), 600);
                        }
                    }
                } catch (e) {
                    if (!active) return;
                    setStatus("fallback");
                    setError("Conexão ao vivo indisponível no momento. Exibindo dados em modo offline.");
                } finally {
                    clearTimeout(timer);
                    pollInFlight = false;
                }
            }
            poll();
            const t = setInterval(poll, POLL_MS);
            return () => { active = false; clearInterval(t); };
        }
    }, [isManual, selectedDate, isViewingHistory]);

    useEffect(() => {
        if (USE_FIREBASE) return;
        let active = true;
        let compassInFlight = false;
        async function pollCompass(force = false) {
            if (!force && typeof document !== "undefined" && document.hidden) return;
            if (compassInFlight) return;
            compassInFlight = true;
            const ctrl = new AbortController();
            const timer = setTimeout(() => ctrl.abort(), selectedDate ? 45000 : 12000);
            try {
                const hasBtCache = Array.isArray(btDaysRef.current) && btDaysRef.current.length > 0;
                const params = new URLSearchParams();
                if (selectedDate) params.set("date_str", selectedDate);
                if (isManual || hasBtCache) params.set("lite", "1");
                const qs = params.toString();
                const url = qs ? `${API_COMPASS_URL}?${qs}` : API_COMPASS_URL;
                const res = await authFetch(url, { signal: ctrl.signal });
                if (res.ok) {
                    const json = await res.json();
                    if (active && json && json.ok) {
                        const p4 = json.portfolio_4_sistematicas;
                        if (p4 && Array.isArray(p4.days)) {
                            if (!p4.is_lite) {
                                btDaysRef.current = p4.days.filter(d => !d.is_live);
                                btComparisonRef.current = p4.all_11_comparison || [];
                            } else if (btDaysRef.current) {
                                p4.days = [...btDaysRef.current, ...(p4.live_days || [])];
                                p4.all_11_comparison = btComparisonRef.current;
                            }
                            const liveSig = JSON.stringify({
                                v: p4.version,
                                bt: btDaysRef.current ? btDaysRef.current.length : 0,
                                ld: p4.live_days || [],
                            });
                            if (liveSig === cachedPortfolioSigRef.current && cachedPortfolioRef.current) {
                                json.portfolio_4_sistematicas = cachedPortfolioRef.current;
                            } else {
                                cachedPortfolioSigRef.current = liveSig;
                                cachedPortfolioRef.current = p4;
                            }
                        }
                        setCompassData(json);
                        setCompassError(null);
                    } else if (active) {
                        setCompassError("Dados do pregão indisponíveis no momento.");
                    }
                } else if (active) {
                    const errBody = await res.json().catch(() => ({}));
                    setCompassError(errBody?.detail || `HTTP ${res.status}: aguardando publicação do produtor ao vivo.`);
                }
            } catch (e) {
                if (active) {
                    setCompassError("Aguardando publicação do produtor ao vivo.");
                }
            } finally {
                clearTimeout(timer);
                compassInFlight = false;
            }
        }
        pollCompass(true);
        if (!selectedDate) {
            const t = setInterval(() => pollCompass(false), 2500);
            const onVisibility = () => {
                if (typeof document !== "undefined" && !document.hidden) pollCompass(true);
            };
            if (typeof document !== "undefined") {
                document.addEventListener("visibilitychange", onVisibility);
            }
            return () => {
                active = false;
                clearInterval(t);
                if (typeof document !== "undefined") {
                    document.removeEventListener("visibilitychange", onVisibility);
                }
            };
        }
        return () => { active = false; };
    }, [selectedDate, isManual]);

    // Simulação quando offline
    useEffect(() => {
        if (status !== "fallback") return;
        const t = setInterval(() => {
            setHistory(prev => {
                const last = prev[prev.length - 1];
                const ns = last.spread + 0.07 * -last.spread + (Math.random() - 0.5) * 1.2;
                const nwin = (last.win_price || 130000) + (Math.random() - 0.5) * 150;
                const hhmm = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
                const next = { i: last.i + 1, spread: +ns.toFixed(3), bar_time: hhmm, win_price: nwin };
                const arr = [...prev.slice(1), next];
                const W = 40;
                return arr.map((d, idx) => {
                    if (idx < W) return { ...d, z: 0 };
                    const sl = arr.slice(idx - W, idx).map(x => x.spread);
                    const mu = sl.reduce((a, b) => a + b, 0) / W;
                    const sd = Math.sqrt(sl.map(v => (v - mu) ** 2).reduce((a, b) => a + b, 0) / W) || 0.01;
                    return { ...d, z: +((d.spread - mu) / sd).toFixed(3) };
                });
            });
        }, 2000);
        return () => clearInterval(t);
    }, [status]);

    // ── Fetch available dates on mount ───────────────────────────────────
    useEffect(() => {
        if (isManual) return;
        async function loadDates() {
            try {
                let jsonHistory = [];
                if (USE_FIREBASE) {
                    const histRef = ref(db, 'history_30d');
                    const snapshot = await get(histRef);
                    jsonHistory = snapshot.val() || [];
                } else {
                    const res = await authFetch(`${API_HISTORY_URL}?days=30`);
                    const json = await res.json();
                    jsonHistory = json.history || [];
                }

                if (jsonHistory.length) {
                    // Limitar tamanho do histórico para evitar OOM
                    const trimmed = jsonHistory.length > MAX_FULL_HISTORY
                        ? jsonHistory.slice(-MAX_FULL_HISTORY)
                        : jsonHistory;
                    setFullHistory(trimmed);
                    const dates = [...new Set(trimmed.map(h => h.date))].sort().reverse();
                    const today = new Date(new Date().getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
                    setHistDates(dates.filter(d => d !== today));
                }
            } catch (e) { /* ignore */ }
        }
        loadDates();
    }, [isManual]);

    // ── Fetch data for selected historical date ──────────────────────────
    const fetchDayData = useCallback(async (date) => {
        if (isManual || !date) { setHistDayData(null); return; }
        setHistLoading(true);
        try {
            let jsonHistory = fullHistory;
            if (!jsonHistory || jsonHistory.length === 0) {
                if (USE_FIREBASE) {
                    const histRef = ref(db, 'history_30d');
                    const snapshot = await get(histRef);
                    jsonHistory = snapshot.val() || [];
                } else {
                    const res = await authFetch(`${API_HISTORY_URL}?days=30`);
                    const json = await res.json();
                    jsonHistory = json.history || [];
                }
            }

            if (jsonHistory.length) {
                const dayBars = jsonHistory.filter(h => h.date === date).map(h => ({
                    ...h,
                    z_raw_wdo: h.z,
                    z_raw_di: h.z_di ?? 0,
                }));
                setHistDayData(dayBars);
            }
        } catch (e) { /* ignore */ }
        setHistLoading(false);
    }, [fullHistory]);

    useEffect(() => { fetchDayData(selectedDate); }, [selectedDate, fetchDayData]);

    // (isViewingHistory foi movido para cima)

    // ── Derived state ──────────────────────────────────────────────────────────
    const currentZ = data ? data.current_z : (history.length > 0 ? history[history.length - 1].z : 0);
    const currentRho = data ? data.current_rho : -0.67;
    const sig = data ? data.signal : getSignal(currentZ);
    const meta = data ? data.meta : { symbol_a: "WINFUT", symbol_b: "WDOFUT", di_symbol: "DIFUT", source: "PROFIT", beta: -22.5, window: 40, timeframe: "M5" };
    const betaOls = data ? data.beta_ols : -22.5;
    const betaChangePct = data ? data.beta_change_pct : 0;
    const betaUnstable = data ? data.beta_unstable : false;
    const betaRef20d = data ? data.beta_ref_20d : -22.5;
    const betaDeltaPct = data ? data.beta_delta_pct : 0;
    const rh = data ? data.regime_health : null;
    const safeToTrade = rh ? rh.safe_to_trade : true;
    const rhoStatus = rh ? rh.rho : { value: currentRho, status: "—", action: "", color: "#3a5060", level: 0 };
    const betaHealth = rh ? rh.beta : { current: betaOls, ref_20d: betaRef20d, delta_pct: betaDeltaPct, status: "—", action: "", color: "#3a5060", level: 0 };
    const cointEg = data ? data.coint_eg : { is_coint: false, pvalue: 1.0 };

    // ── Merged signal data for histogram ───────────────────────────────────────
    const mergedSignals = useMemo(() => {
        const sourceData = isViewingHistory && histDayData ? histDayData : (isViewingHistory ? [] : history);

        return sourceData.map((h) => {
            return {
                ...h,
                z_raw_wdo: h.z_raw_wdo ?? h.z,
                z_raw_di: h.z_raw_di ?? h.z_di ?? 0,
                z_unfiltered_wdo: h.z_unfiltered_wdo ?? h.z,
                z_unfiltered_di: h.z_unfiltered_di ?? h.z_di ?? 0,
                sig_wdo: h.sig_wdo ?? 0,
                sig_di: h.sig_di ?? 0,
                cons_wdo_sig: h.cons_wdo_sig ?? 0,
                cons_di_sig: h.cons_di_sig ?? 0,
            };
        });
    }, [history, histDayData, isViewingHistory]);

    const paddedSignals = useMemo(() => {
        if (!mergedSignals || mergedSignals.length === 0) return mergedSignals;

        const SESSION_START = 9 * 60; // 09:00
        const SESSION_END = 18 * 60 + 20; // 18:20
        const BAR_MINS = 5;

        const signalsMap = new Map();
        mergedSignals.forEach(s => {
            if (s.bar_time) signalsMap.set(s.bar_time, s);
        });

        const result = [];

        // Bars before 09:00
        mergedSignals.forEach(s => {
            if (s.bar_time) {
                const [h, m] = s.bar_time.split(':').map(Number);
                const t = h * 60 + m;
                if (t < SESSION_START) result.push(s);
            }
        });

        // Main session 09:00 to 18:20
        for (let t = SESSION_START; t <= SESSION_END; t += BAR_MINS) {
            const h = String(Math.floor(t / 60)).padStart(2, "0");
            const m = String(t % 60).padStart(2, "0");
            const timeStr = `${h}:${m}`;
            if (signalsMap.has(timeStr)) {
                result.push(signalsMap.get(timeStr));
            } else {
                result.push({ bar_time: timeStr });
            }
        }

        // Bars after 18:20
        mergedSignals.forEach(s => {
            if (s.bar_time) {
                const [h, m] = s.bar_time.split(':').map(Number);
                const t = h * 60 + m;
                if (t > SESSION_END) result.push(s);
            }
        });

        result.sort((a, b) => {
            if (!a.bar_time || !b.bar_time) return 0;
            return a.bar_time.localeCompare(b.bar_time);
        });

        const unique = [];
        const seen = new Set();
        result.forEach(s => {
            if (!seen.has(s.bar_time)) {
                seen.add(s.bar_time);
                unique.push(s);
            }
        });

        return unique;
    }, [mergedSignals]);

    // Deterministic trades for the current/selected day (synced across SignalHistogram, IndexChart, and StatArbLiveTradePanel)
    const currentDayTrades = useMemo(() => {
        if (!isViewingHistory && Array.isArray(data?.day_trades) && data.day_trades.length > 0) {
            return data.day_trades.map(normalizeStatArbTrade);
        }
        return simulateDayStatArbTradesJs(paddedSignals, gexWalls, !isViewingHistory, selectedDate);
    }, [data?.day_trades, paddedSignals, gexWalls, isViewingHistory, selectedDate]);

    // Sync Time Scales & Crosshairs (ZScoreChart, SignalHistogram, IndexChart)
    useEffect(() => {
        const zChart = zScoreChartRef.current?.getChart();
        const hChart = histogramChartRef.current?.getChart();
        const iChart = indexChartRef.current?.getChart();

        const zSeries = zScoreChartRef.current?.getMainSeries?.();
        const hSeries = histogramChartRef.current?.getMainSeries?.();
        const iSeries = indexChartRef.current?.getMainSeries?.();

        if (!zChart || !hChart || !iChart) return;

        const charts = [
            { chart: zChart, series: zSeries },
            { chart: hChart, series: hSeries },
            { chart: iChart, series: iSeries }
        ];

        // TIME SCALE SYNC
        let isSyncingTime = false;

        function getLogicalSyncHandler(sourceChart) {
            return (logicalRange) => {
                if (!logicalRange || isSyncingTime) return;
                if (logicalRange.from < -5 && paddedSignals && paddedSignals.length > 10) return;
                isSyncingTime = true;
                charts.forEach(c => {
                    if (c.chart !== sourceChart) {
                        try {
                            c.chart.timeScale().setVisibleLogicalRange(logicalRange);
                        } catch (e) { }
                    }
                });
                isSyncingTime = false;
            };
        }

        if (paddedSignals && paddedSignals.length > 0) {
            isSyncingTime = true;
            const fullRange = { from: 0, to: Math.max(10, paddedSignals.length - 1) };
            charts.forEach(c => {
                try {
                    c.chart.timeScale().fitContent();
                    c.chart.timeScale().setVisibleLogicalRange(fullRange);
                } catch (e) { }
            });
            isSyncingTime = false;
        }

        const zTimeHandler = getLogicalSyncHandler(zChart);
        const hTimeHandler = getLogicalSyncHandler(hChart);
        const iTimeHandler = getLogicalSyncHandler(iChart);

        zChart.timeScale().subscribeVisibleLogicalRangeChange(zTimeHandler);
        hChart.timeScale().subscribeVisibleLogicalRangeChange(hTimeHandler);
        iChart.timeScale().subscribeVisibleLogicalRangeChange(iTimeHandler);

        const timeToZPrice = new Map();
        const timeToIPrice = new Map();
        const timeToHPrice = new Map();

        paddedSignals.forEach(s => {
            if (!s.bar_time) return;
            const t = timeStrToTimestamp(s.bar_time);
            if (t === 0) return;
            timeToZPrice.set(t, s.z_raw_wdo ?? s.z ?? 0);
            timeToIPrice.set(t, s.win_price ?? 0);
            timeToHPrice.set(t, 3);
        });

        function getClosestTimestampForSeries(map, t) {
            if (map.size === 0) return t;
            let closestKey = t;
            let minDiff = Infinity;
            for (let k of map.keys()) {
                let diff = Math.abs(k - t);
                if (diff < minDiff) {
                    minDiff = diff;
                    closestKey = k;
                }
            }
            return closestKey;
        }

        // CROSSHAIR SYNC
        let isSyncingCrosshair = false;
        function getCrosshairHandler(sourceChart) {
            return (param) => {
                if (isSyncingCrosshair) return;
                isSyncingCrosshair = true;

                if (!param.time) {
                    charts.forEach(c => {
                        if (c.chart !== sourceChart) c.chart.clearCrosshairPosition();
                    });
                } else {
                    const t = param.time;
                    charts.forEach(c => {
                        if (c.chart !== sourceChart && c.series) {
                            let price = 0;
                            let targetTime = t;

                            if (c.chart === zChart) {
                                targetTime = getClosestTimestampForSeries(timeToZPrice, t);
                                price = timeToZPrice.get(targetTime) ?? 0;
                            } else if (c.chart === iChart) {
                                targetTime = getClosestTimestampForSeries(timeToIPrice, t);
                                price = timeToIPrice.get(targetTime) ?? 0;
                            } else if (c.chart === hChart) {
                                targetTime = getClosestTimestampForSeries(timeToHPrice, t);
                                price = timeToHPrice.get(targetTime) ?? 3;
                            }

                            try {
                                c.chart.setCrosshairPosition(price, targetTime, c.series);
                            } catch (e) { }
                        }
                    });
                }
                isSyncingCrosshair = false;
            };
        }

        const zCrosshairHandler = getCrosshairHandler(zChart);
        const hCrosshairHandler = getCrosshairHandler(hChart);
        const iCrosshairHandler = getCrosshairHandler(iChart);

        zChart.subscribeCrosshairMove(zCrosshairHandler);
        hChart.subscribeCrosshairMove(hCrosshairHandler);
        iChart.subscribeCrosshairMove(iCrosshairHandler);

        return () => {
            zChart.timeScale().unsubscribeVisibleLogicalRangeChange(zTimeHandler);
            hChart.timeScale().unsubscribeVisibleLogicalRangeChange(hTimeHandler);
            iChart.timeScale().unsubscribeVisibleLogicalRangeChange(iTimeHandler);

            zChart.unsubscribeCrosshairMove(zCrosshairHandler);
            hChart.unsubscribeCrosshairMove(hCrosshairHandler);
            iChart.unsubscribeCrosshairMove(iCrosshairHandler);
        };
    }, [paddedSignals, meta, workspaceTab, isViewingHistory]);

    // Alerta Sonoro — reutiliza um único AudioContext para evitar memory leak
    useEffect(() => {
        if (sig && sig.id !== lastSignalId) {
            if ((sig.id === "compraWdo" || sig.id === "compraWin") && safeToTrade) {
                try {
                    if (!audioCtxRef.current || audioCtxRef.current.state === "closed") {
                        audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
                    }
                    const ctx = audioCtxRef.current;
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.type = "square";
                    osc.frequency.setValueAtTime(880, ctx.currentTime);
                    gain.gain.setValueAtTime(0.05, ctx.currentTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
                    osc.start(ctx.currentTime);
                    osc.stop(ctx.currentTime + 0.3);
                } catch (e) { }
            }
            setLastSignalId(sig.id);
        }
    }, [sig, safeToTrade, lastSignalId]);

    // Cleanup: fechar AudioContext e limpar timers ao desmontar
    useEffect(() => {
        return () => {
            if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
            if (audioCtxRef.current) {
                try { audioCtxRef.current.close(); } catch (e) { }
            }
        };
    }, []);

    const isActive = sig.id === "compraWdo" || sig.id === "compraWin";
    const isAnom = sig.id === "anomalia";

    const getCointStatus = (p) => {
        if (p < 0.01) return { label: "FORTE", color: "#4cc38a" };
        if (p < 0.05) return { label: "PRESENTE", color: "#d4a259" };
        if (p < 0.10) return { label: "FRACA", color: "#d4a259" };
        return { label: "QUEBRADA", color: "#e5484d" };
    };
    const cointInfo = getCointStatus(cointEg.pvalue);

    // ── Count active signals for consensus badge (WDO + DI) ────────────────────
    const lastBar = mergedSignals.length > 0 ? mergedSignals[mergedSignals.length - 1] : {};
    const buyCount = [lastBar.cons_wdo_sig, lastBar.cons_di_sig].filter(v => v < 0).length;
    const sellCount = [lastBar.cons_wdo_sig, lastBar.cons_di_sig].filter(v => v > 0).length;
    const consensusCount = Math.max(buyCount, sellCount);
    const consensusDir = buyCount > sellCount ? "COMPRA" : sellCount > buyCount ? "VENDA" : null;
    const consensusColor = consensusDir === "COMPRA" ? "#4cc38a" : consensusDir === "VENDA" ? "#e5484d" : "#848da2";

    // ── Johansen gate data ─────────────────────────────────────────────────────
    const johWdoGate = data?.johansen_gate || null;
    const johDiGate = diData?.johansen_gate || null;

    const liveStatus = isManual ? (compassData?.ok ? "live" : status) : status;
    const availableDates = compassData?.available_dates || [];
    const todayDateStr = availableDates[0] || "";
    const activeCompassDate = selectedDate || compassData?.selected_date || todayDateStr || "";
    const winBarsCount = compassData?.WIN?.caminho_a?.m5_dealer_vs_flow_series?.length || 0;
    const wdoBarsCount = compassData?.WDO?.caminho_a?.m5_dealer_vs_flow_series?.length || 0;
    const hasCompassBars = winBarsCount > 0 || wdoBarsCount > 0;
    const isHistoricalCompass = Boolean(isViewingHistory || compassData?.is_historical);
    const isClosedEmpty = Boolean(compassData?.ok && !hasCompassBars);
    const updatedAtClock = compassData?.updated_at && /^\d{2}:\d{2}/.test(String(compassData.updated_at).trim())
        ? String(compassData.updated_at).trim().slice(0, 5)
        : "";

    const handleQuickDatePick = (dStr) => {
        setSelectedDate(dStr === todayDateStr ? "" : dStr);
    };

    const quickDates = availableDates.slice(0, 3);
    const viewOptions = isNarrowScreen
        ? [
            { id: "WIN", label: "WIN" },
            { id: "WDO", label: "WDO" },
        ]
        : [
            { id: "DUAL", label: "Dupla" },
            { id: "WIN", label: "WIN" },
            { id: "WDO", label: "WDO" },
        ];

    const footerStatusText = isClosedEmpty
        ? `Sem barras no pregão de ${fmtDateFullBr(activeCompassDate)}`
        : isHistoricalCompass
        ? `Replay histórico de ${fmtDateFullBr(activeCompassDate)}`
        : liveStatus === "live"
        ? "Dados B3 ao vivo"
        : "Modo offline";

    const waitingInitialData = isManual ? !compassData : (!data && !compassData && !isViewingHistory);
    const feedUnavailableNow = waitingInitialData && (Boolean(compassError) || status === "fallback");

    return (
        <>
            {/* Loading / Aguardando Publicação Overlay */}
            {waitingInitialData && (
                <div
                    className="skeleton-loader"
                    style={isSaasAuthEnabled() ? { top: 33, padding: 24 } : { padding: 24 }}
                >
                    {feedUnavailableNow ? (
                        <div
                            data-testid="saas-feed-waiting"
                            style={{
                                width: "100%",
                                maxWidth: 480,
                                background: "var(--mw-surface, #131720)",
                                border: "1px solid var(--mw-hairline, rgba(238,240,245,0.1))",
                                borderRadius: 12,
                                padding: 24,
                                display: "flex",
                                flexDirection: "column",
                                gap: 12,
                            }}
                        >
                            <div style={{ fontSize: 16, fontWeight: 500, color: "var(--mw-text-1, #eef0f5)", lineHeight: 1.3 }}>
                                Aguardando publicação dos dados do pregão
                            </div>
                            <div style={{ fontSize: 13, color: "var(--mw-text-2, #a3a9b8)", lineHeight: 1.55 }}>
                                O servidor cloud está ativo, mas ainda não há snapshot recente publicado. Assim que o produtor local enviar os dados, o terminal abrirá automaticamente.
                            </div>
                            <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--mw-text-3, #848da2)" }}>
                                {compassError || error || "Aguardando publicação do produtor ao vivo."}
                            </div>
                            <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 4 }}>
                                <button
                                    type="button"
                                    className="mw-btn mw-btn-secondary"
                                    style={{ height: 32, padding: "0 12px" }}
                                    onClick={() => window.location.reload()}
                                >
                                    Tentar novamente
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="skeleton-pulse">Carregando painel Magic Walls...</div>
                    )}
                </div>
            )}
            <div className="mw-app-shell" style={{ background: "var(--mw-bg)", minHeight: "100svh", color: "var(--mw-text-1)", fontFamily: "var(--sans)", display: "flex", flexDirection: "column", overflowX: "hidden", maxWidth: "100%" }}>

                {/* ── Topbar Unificada Ink Azul + Flip Strata ──────────────────────────── */}
                <header className="topbar">
                    <div className="topbar-left" style={{ gap: 12 }}>
                        <span className="mw-topbar-title" style={{
                            display: "inline-flex", alignItems: "center", gap: 10,
                            fontSize: 15, fontWeight: 600, letterSpacing: 0,
                            color: "var(--mw-text-1)",
                            lineHeight: 1,
                            flex: "0 1 auto",
                            minWidth: 0,
                        }}>
                            <MagicWallsMark size={20} variant="small" />
                            <span>{isManual ? "Magic Walls" : isWallsFlow ? "Robôs Magic Walls" : "Magic Walls · MT5"}</span>
                        </span>
                        <span style={{ display: "inline-block", width: 1, height: 14, background: "var(--mw-hairline-strong)" }} />
                        <span className="mw-topbar-sub" style={{ fontSize: 13, color: "var(--mw-text-3)", letterSpacing: 0, fontWeight: 400, whiteSpace: "nowrap" }}>
                            {isManual || isWallsFlow
                                ? "WIN × WDO · B3"
                                : `${meta.symbol_a} × ${meta.symbol_b} · ${meta.timeframe}`}
                        </span>
                        {!isManual && !isWallsFlow && (
                            <button
                                type="button"
                                className="mw-btn mw-btn-secondary"
                                data-active={showSetup ? "true" : "false"}
                                onClick={() => setShowSetup(s => !s)}
                                title="Ver regras"
                            >
                                Matador
                            </button>
                        )}
                    </div>

                    {isManual && compassData && (
                        <div className="topbar-center">
                            <div className="mw-track" role="group" aria-label="Ativos visíveis">
                                {viewOptions.map((opt) => (
                                    <button
                                        key={opt.id}
                                        type="button"
                                        className="mw-btn mw-btn-top"
                                        data-active={effectiveAssetView === opt.id ? "true" : "false"}
                                        onClick={() => setAssetView(opt.id)}
                                    >
                                        {opt.label}
                                    </button>
                                ))}
                            </div>

                            {canSplitDual && effectiveAssetView === "DUAL" && (
                                <div className="mw-track" role="group" aria-label="Disposição da visão dupla">
                                    <button
                                        type="button"
                                        className="mw-btn mw-btn-top"
                                        data-active={dualLayout === "stacked" ? "true" : "false"}
                                        onClick={() => setDualLayout("stacked")}
                                        title="WIN acima, WDO abaixo"
                                    >
                                        Empilhado
                                    </button>
                                    <button
                                        type="button"
                                        className="mw-btn mw-btn-top"
                                        data-active={dualLayout === "split" ? "true" : "false"}
                                        onClick={() => setDualLayout("split")}
                                        title="WIN e WDO lado a lado"
                                    >
                                        Lado a lado
                                    </button>
                                </div>
                            )}

                            {quickDates.length > 0 && (
                                <div className="mw-track" role="group" aria-label="Atalhos de pregão">
                                    {quickDates.map((d, idx) => {
                                        const isActive = activeCompassDate === d;
                                        const label = idx === 0
                                            ? `Hoje (${fmtDateShortBr(d)})`
                                            : fmtDateShortBr(d);
                                        return (
                                            <button
                                                key={d}
                                                type="button"
                                                className="mw-btn mw-btn-top mw-mono"
                                                data-active={isActive ? "true" : "false"}
                                                onClick={() => handleQuickDatePick(d)}
                                            >
                                                {label}
                                            </button>
                                        );
                                    })}
                                </div>
                            )}

                            {availableDates.length > 0 && (
                                <select
                                    className="mw-select"
                                    aria-label="Selecionar pregão"
                                    value={activeCompassDate}
                                    onChange={(e) => handleQuickDatePick(e.target.value)}
                                >
                                    {availableDates.map((d, idx) => (
                                        <option key={d} value={d}>
                                            {idx === 0 ? `Hoje (${fmtDateShortBr(d)})` : idx === 1 ? `Ontem (${fmtDateShortBr(d)})` : fmtDateFullBr(d)}
                                        </option>
                                    ))}
                                </select>
                            )}
                        </div>
                    )}

                    {!isManual && (
                        <div className="topbar-center">
                            <div className="mw-track" role="tablist" aria-label="Seções do terminal">
                                {[
                                    { id: "COCKPIT", label: "Cockpit" },
                                    { id: "RAIO_X", label: "Raio-X" },
                                    { id: "STAT_ARB", label: "Stat-Arb" },
                                ].map((tab) => (
                                    <button
                                        key={tab.id}
                                        type="button"
                                        role="tab"
                                        aria-selected={workspaceTab === tab.id}
                                        className="mw-btn mw-btn-top"
                                        data-active={workspaceTab === tab.id ? "true" : "false"}
                                        onClick={() => setWorkspaceTab(tab.id)}
                                    >
                                        {workspaceTab === tab.id && <span className="mw-dot-accent" />}
                                        <span>{tab.label}</span>
                                    </button>
                                ))}
                            </div>

                            {quickDates.length > 0 && (
                                <div className="mw-track" role="group" aria-label="Atalhos de pregão">
                                    {quickDates.map((d, idx) => {
                                        const isActive = activeCompassDate === d;
                                        const label = idx === 0
                                            ? `Hoje (${fmtDateShortBr(d)})`
                                            : fmtDateShortBr(d);
                                        return (
                                            <button
                                                key={d}
                                                type="button"
                                                className="mw-btn mw-btn-top mw-mono"
                                                data-active={isActive ? "true" : "false"}
                                                onClick={() => handleQuickDatePick(d)}
                                            >
                                                {label}
                                            </button>
                                        );
                                    })}
                                </div>
                            )}

                            {availableDates.length > 0 ? (
                                <select
                                    className="mw-select"
                                    aria-label="Selecionar pregão"
                                    value={activeCompassDate}
                                    onChange={(e) => handleQuickDatePick(e.target.value)}
                                >
                                    {availableDates.map((d, idx) => (
                                        <option key={d} value={d}>
                                            {idx === 0 ? `Hoje (${fmtDateShortBr(d)})` : idx === 1 ? `Ontem (${fmtDateShortBr(d)})` : fmtDateFullBr(d)}
                                        </option>
                                    ))}
                                </select>
                            ) : (
                                <select
                                    className="mw-select"
                                    aria-label="Selecionar pregão histórico"
                                    value={selectedDate}
                                    onChange={(e) => setSelectedDate(e.target.value)}
                                >
                                    <option value="">Hoje (ao vivo)</option>
                                    {histDates.map((d) => {
                                        const [y, m, day] = d.split("-");
                                        const wd = new Date(y, m - 1, day).toLocaleDateString("pt-BR", { weekday: "short" });
                                        return <option key={d} value={d}>{wd} {day}/{m}</option>;
                                    })}
                                </select>
                            )}
                        </div>
                    )}

                    <div className="topbar-right" style={{ gap: 10 }}>
                        {(!isManual || isSaasAuthEnabled()) && canUseMediaStudio && (
                            <button
                                type="button"
                                className="mw-btn mw-btn-secondary"
                                data-testid="topbar-morning-video-btn"
                                onClick={() => setShowMorningVideoModal(true)}
                                title="Abrir Estúdio de Vídeo Animado Pré-Pregão 08h30 (Reels 9:16 e YouTube 16:9)"
                            >
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                    <rect x="2" y="4" width="20" height="16" rx="2" />
                                    <path d="m10 9 5 3-5 3V9z" />
                                </svg>
                                <span>Vídeo 08h30</span>
                            </button>
                        )}

                        {/* Status verdadeiro do feed (estático, zero pulsar falso) */}
                        <div style={{
                            display: "inline-flex", alignItems: "center", gap: 8,
                            height: 28, padding: "0 10px", borderRadius: 6,
                            background: "var(--mw-card)",
                            border: "1px solid var(--mw-hairline)",
                            fontSize: 12, color: "var(--mw-text-2)",
                            whiteSpace: "nowrap",
                        }}>
                            {isClosedEmpty ? (
                                <>
                                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--mw-text-3)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                        <circle cx="12" cy="12" r="9" />
                                        <polyline points="12 7 12 12 15 14" />
                                    </svg>
                                    <span>Sem pregão{activeCompassDate ? ` · ${fmtDateShortBr(activeCompassDate)}` : ""}</span>
                                </>
                            ) : isHistoricalCompass ? (
                                <>
                                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--mw-accent-ink)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                        <rect x="3" y="4" width="18" height="18" rx="2" />
                                        <line x1="16" y1="2" x2="16" y2="6" />
                                        <line x1="8" y1="2" x2="8" y2="6" />
                                        <line x1="3" y1="10" x2="21" y2="10" />
                                    </svg>
                                    <span>Replay{activeCompassDate ? ` · ${fmtDateShortBr(activeCompassDate)}` : ""}</span>
                                </>
                            ) : liveStatus === "live" ? (
                                <>
                                    <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "var(--mw-pos)" }} />
                                    <span className="mw-mono">Ao vivo{updatedAtClock ? ` · ${updatedAtClock}` : ""}</span>
                                </>
                            ) : (
                                <>
                                    <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "var(--mw-text-3)" }} />
                                    <span>{liveStatus === "fallback" ? "Offline" : "Conectando"}</span>
                                </>
                            )}
                        </div>
                        <TopbarClock />
                    </div>
                </header>

                {/* ── Banners ─────────────────────────────────────────────────────────── */}
                {!isManual && error && (
                    <div style={{ background: "var(--mw-chrome)", borderBottom: "1px solid var(--mw-hairline)", padding: "8px 24px", fontSize: 12, color: "var(--mw-accent-ink)" }}>
                        {error}
                    </div>
                )}
                {!isManual && workspaceTab === "STAT_ARB" && betaUnstable && (
                    <div style={{
                        background: "var(--mw-neg-bg)",
                        borderBottom: "1px solid rgba(229, 72, 77, 0.28)",
                        padding: "8px 24px", fontSize: 12, color: "var(--mw-neg)",
                        display: "flex", alignItems: "center", gap: 10,
                    }}>
                        <span>
                            <strong style={{ fontWeight: 600 }}>Beta instável</strong> — variação de <span className="mw-mono" style={{ fontWeight: 600 }}>{betaChangePct > 0 ? "+" : ""}{betaChangePct.toFixed(1)}%</span> em relação à leitura anterior. Relação WIN × WDO pode estar em ruptura.
                        </span>
                    </div>
                )}

                {/* ——— Main content ———————————————————————————————————————————————————————————— */}
                <div className="mw-main" style={{ flex: 1, padding: "16px 24px 20px 24px", display: "flex", flexDirection: "column", gap: 16, minWidth: 0, maxWidth: "100%", boxSizing: "border-box" }}>

                    {!isManual && !isWallsFlow && showSetup && <SetupMatadorPanel tradeEngine={data?.trade_engine} />}

                    {(isManual || workspaceTab === "COCKPIT" || workspaceTab === "RAIO_X") && (
                        <IntradayCompassPanel
                            compassData={compassData}
                            mode={isManual ? "COCKPIT" : workspaceTab}
                            onChangeMode={setWorkspaceTab}
                            selectedDate={selectedDate}
                            onSelectDate={setSelectedDate}
                            selectedAssetProp={isManual ? effectiveAssetView : undefined}
                            onSelectAssetProp={isManual ? setAssetView : undefined}
                            dualLayout={canSplitDual ? dualLayout : "stacked"}
                        />
                    )}

                    {/* History mode banner (Stat-Arb) */}
                    {!isManual && isViewingHistory && workspaceTab === "STAT_ARB" && (
                        <div className="mw-card" style={{
                            padding: "8px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12,
                        }}>
                            <span className="mw-mono" style={{ fontSize: 12, color: "var(--mw-text-2)" }}>
                                Replay Z-Score · Pregão de <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{(() => { const [y, m, d] = selectedDate.split("-"); return `${d}/${m}/${y}`; })()}</strong>
                                {histDayData && ` · ${histDayData.length} barras`}
                            </span>
                            <button type="button" className="mw-btn mw-btn-secondary" onClick={() => setSelectedDate("")}>
                                Voltar para hoje
                            </button>
                        </div>
                    )}

                    {!isManual && workspaceTab === "STAT_ARB" && (
                        <>
                            {/* Compact Regime Health Strip — above charts */}
                            {(() => {
                                const zWdo = isViewingHistory ? lastBar.z : currentZ;
                                const zDi = isViewingHistory ? (lastBar.z_di ?? lastBar.z_unfiltered_di ?? 0) : (diData?.current_z ?? 0);
                                const betaH = data?.regime_health?.beta;
                                const diBetaH = diData?.regime_health?.beta;
                                const diRhoH = diData?.regime_health?.rho;
                                const zColor = (v) => Math.abs(v || 0) >= 1.4 ? (v > 0 ? "#e5484d" : "#4cc38a") : "var(--mw-text-2)";
                                const mapHealthColor = (c) => {
                                    if (!c) return "var(--mw-text-2)";
                                    const lc = String(c).toLowerCase();
                                    if (lc === "#00e87a" || lc === "#22c55e" || lc === "#10b981") return "#4cc38a";
                                    if (lc === "#ff3860" || lc === "#ef4444" || lc === "#f43f5e") return "#e5484d";
                                    if (lc === "#ffd600" || lc === "#f5a623" || lc === "#f59e0b" || lc === "#c8a444") return "#d4a259";
                                    if (lc === "#00d4ff" || lc === "#00e5ff") return "#38bdf8";
                                    return c;
                                };
                                const Pill = ({ label, value, color, badge }) => {
                                    const col = mapHealthColor(color);
                                    const isHex = typeof col === "string" && col.startsWith("#");
                                    return (
                                        <span className="mw-mono" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                                            <span style={{ fontSize: 10.5, color: "var(--mw-text-3)" }}>{label}</span>
                                            <span style={{ fontSize: 11.5, fontWeight: 600, color: col }}>
                                                {typeof value === "number" ? value.toFixed(3) : value ?? "—"}
                                            </span>
                                            {badge && (
                                                <span style={{
                                                    fontSize: 9.5,
                                                    color: col,
                                                    background: isHex ? `${col}1a` : "var(--mw-surface-2)",
                                                    border: `1px solid ${isHex ? `${col}4d` : "var(--mw-hairline)"}`,
                                                    fontWeight: 600,
                                                    padding: "1px 6px",
                                                    borderRadius: 4,
                                                }}>
                                                    {badge}
                                                </span>
                                            )}
                                        </span>
                                    );
                                };
                                const Dot = ({ gate, label }) => {
                                    if (!gate) return null;
                                    const c = gate.open ? "#4cc38a" : "#e5484d";
                                    return (
                                        <span className="mw-mono" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                                            <span style={{ fontSize: 10.5, color: "var(--mw-text-3)" }}>{label}</span>
                                            <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: c }} />
                                            <span style={{ fontSize: 10.5, color: c, fontWeight: 600 }}>
                                                {gate.open ? "aberto" : "fechado"}{gate.trace_ratio !== undefined ? ` (${gate.trace_ratio}x)` : ""}
                                            </span>
                                        </span>
                                    );
                                };
                                return (
                                    <div style={{
                                        display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
                                        padding: "8px 14px", marginBottom: -2,
                                        background: "var(--mw-card)", borderRadius: "10px 10px 0 0",
                                        border: "1px solid var(--mw-hairline)", borderBottom: "none",
                                    }}>
                                        <span className="mw-mono" style={{ fontSize: 10.5, color: "var(--mw-accent-ink)", fontWeight: 600, background: "var(--mw-accent-soft)", border: "1px solid var(--mw-accent-border)", padding: "2px 7px", borderRadius: 5 }}>Profit · WINFUT</span>
                                        <span className="mw-mono" style={{ fontSize: 11, color: "#d4a259", fontWeight: 600 }}>WDOFUT</span>
                                        <Pill label="Z" value={zWdo} color={zColor(zWdo)} />
                                        {betaH && <Pill label="β" value={betaH.delta_pct} color={betaH.color} badge={betaH.status} />}
                                        <Dot gate={johWdoGate} label="Joh" />

                                        <span style={{ display: "inline-block", width: 1, height: 14, background: "var(--mw-hairline-strong)" }} />

                                        <span className="mw-mono" style={{ fontSize: 11, color: "#a78bfa", fontWeight: 600 }}>DIFUT</span>
                                        <Pill label="Z" value={zDi} color={zColor(zDi)} />
                                        {diBetaH && <Pill label="β" value={diBetaH.delta_pct} color={diBetaH.color} badge={diBetaH.status} />}
                                        {diRhoH && <Pill label="ρ" value={diRhoH.value} color={diRhoH.color} badge={diRhoH.status} />}
                                        <Dot gate={johDiGate} label="Joh" />

                                        {data?.nwe && (
                                            <>
                                                <span style={{ display: "inline-block", width: 1, height: 14, background: "var(--mw-hairline-strong)" }} />
                                                <span className="mw-mono" style={{ fontSize: 11, fontWeight: 600, color: data.nwe.is_up ? "#4cc38a" : "#e5484d" }}>
                                                    Gauss {data.nwe.is_up ? "↑" : "↓"}
                                                </span>
                                            </>
                                        )}
                                    </div>
                                );
                            })()}

                            {/* Z-Score Chart + Signal Histogram + WINFUT Price/NWE Chart (grouped) */}
                            <div style={{ marginTop: 0 }}>
                                <ZScoreChart
                                    ref={zScoreChartRef}
                                    history={paddedSignals}
                                    sigColor={isViewingHistory ? "#4cc38a" : sig.color}
                                    currentZ={isViewingHistory ? 0 : currentZ}
                                    useV2={true}
                                    hideXAxis={true}
                                />
                                <SignalHistogram
                                    ref={histogramChartRef}
                                    data={paddedSignals}
                                    trades={currentDayTrades}
                                />
                                <IndexChart
                                    ref={indexChartRef}
                                    history={paddedSignals}
                                    walls={gexWalls}
                                    tradeEngine={data?.trade_engine}
                                    dayTrades={currentDayTrades}
                                    isViewingHistory={isViewingHistory}
                                    hideXAxis={false}
                                />
                            </div>

                            <StatArbLiveTradePanel
                                history={paddedSignals}
                                walls={gexWalls}
                                dayTrades={currentDayTrades}
                                selectedDate={selectedDate}
                                isViewingHistory={isViewingHistory}
                                onSelectDate={(d) => {
                                    setSelectedDate(d);
                                    window.scrollTo({ top: 0, behavior: "smooth" });
                                }}
                            />

                            <StatArbBacktest2026Panel
                                onSelectDate={(d) => {
                                    setSelectedDate(d);
                                    window.scrollTo({ top: 0, behavior: "smooth" });
                                }}
                            />

                            {/* Alert Banner */}
                            {!safeToTrade && isActive && (
                                <div className="mw-card" style={{
                                    background: "var(--mw-neg-bg)", border: "1px solid rgba(229,72,77,0.3)",
                                    padding: "10px 16px", display: "flex", alignItems: "center", gap: 10,
                                }}>
                                    <div style={{ fontSize: 12, color: "var(--mw-neg)", lineHeight: 1.5 }}>
                                        <strong style={{ fontWeight: 600 }}>Z-Score alto com relação instável</strong> — ρ ou Δβ fora da faixa segura invalida o sinal de z={currentZ > 0 ? `+${currentZ.toFixed(2)}` : currentZ.toFixed(2)}.
                                    </div>
                                </div>
                            )}
                        </>
                    )}

                    {/* Calendário do Live Trading (exclusivo da Aba 1 - Cockpit) */}
                    {!isManual && workspaceTab === "COCKPIT" && (
                        <LiveTradingCalendar
                            portfolioData={compassData?.portfolio_4_sistematicas}
                            onSelectDate={setSelectedDate}
                        />
                    )}
                </div>

                {/* ── Footer ──────────────────────────────────────────────────────────── */}
                <footer className="mw-footer" style={{ borderTop: "1px solid var(--mw-hairline)", padding: "12px 24px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, fontSize: 12, color: "var(--mw-text-3)", background: "var(--mw-chrome)", letterSpacing: 0 }}>
                    <span>{footerStatusText} — uso informativo, não constitui recomendação de investimento</span>
                    <span className="mw-mono">
                        {isManual
                            ? "Magic Walls · WIN × WDO · Canal Gauss, Sinais Numerados & Fluxo · B3"
                            : isWallsFlow
                            ? "Robôs Magic Walls · Carteira 5176 · WIN × WDO · B3"
                            : `Magic Walls · MT5 · beta ${meta.beta} · ${String(meta.window || "").toUpperCase() === "KALMAN" ? "Kalman" : `janela ${meta.window}b`} · ${meta.symbol_a} × ${meta.symbol_b} · B3`}
                    </span>
                </footer>
            </div>
            {canUseMediaStudio && showMorningVideoModal && (
                <MorningWallsVideoModal
                    isOpen={showMorningVideoModal}
                    onClose={() => setShowMorningVideoModal(false)}
                    selectedDate={activeCompassDate}
                    compassData={compassData}
                />
            )}
        </>
    );
}
