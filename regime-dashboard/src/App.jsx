import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { ref, onValue, get } from "firebase/database";
import { db } from "./firebase";
import ZScoreChart from "./components/ZScoreChart";
import RegimeHealthPanel from "./components/RegimeHealthPanel";
import PerformancePanel from "./components/PerformancePanel";
import TradingGuide from "./components/TradingGuide";
import SignalHistogram from "./components/SignalHistogram";
import IndexChart from "./components/IndexChart";
import SetupMatadorPanel from "./components/SetupMatadorPanel";
import BrokerFlowPanel from "./components/BrokerFlowPanel";
import FlowDeltaChart from "./components/FlowDeltaChart";
import FlowScoreChart from "./components/FlowScoreChart";
import FlowAccelerationChart from "./components/FlowAccelerationChart";
import IntradayCompassPanel from "./components/IntradayCompassPanel";

const STRAT_LABELS = {
    CONS_BASE: { label: "CONS", color: "#00d4ff" },
    WDO_NWE: { label: "WDO", color: "#c8a444" },
    DI_NWE: { label: "DI", color: "#8a6dff" },
};

const API_URL = "http://localhost:8080/api/v2/regime";
const API_PERF_URL = "http://localhost:8080/api/performance";
const API_DI_URL = "http://localhost:8080/api/di-regime";
const API_HISTORY_URL = "http://localhost:8080/api/history";
const API_FLOW_URL = "http://localhost:8080/api/flow";
const API_FLOW_REALTIME_URL = "http://localhost:8080/api/flow/realtime";
const API_COMPASS_URL = "http://localhost:8080/api/compass/etapa1";
const POLL_MS = 2500;

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
    if (az >= 4) return { id: "anomalia", label: "ANOMALIA", sub: "Não operar — possível breakdown", wdo: null, win: null, color: "#ff3860" };
    if (z >= 1.4) return { id: "compraWdo", label: "VENDE WIN", sub: "Z-Score positivo — spread revertendo", wdo: "IGNORAR", win: "VENDER", color: "#ff3860" };
    if (z <= -1.4) return { id: "compraWin", label: "COMPRA WIN", sub: "Z-Score negativo — spread revertendo", wdo: "IGNORAR", win: "COMPRAR", color: "#00e87a" };
    if (az >= 1.2) return { id: "atencao", label: "ZONA DE DIVERGENCIA", sub: "Aguardar Z atingir +/-1.4 para entrar", wdo: null, win: null, color: "#f5a623" };
    return { id: "neutro", label: "AGUARDAR", sub: "Spread em equilibrio — sem setup no momento", wdo: null, win: null, color: "#445560" };
}

// ── Main App ────────────────────────────────────────────────────────────────

// Limite máximo de barras no histórico completo para evitar OOM
const MAX_FULL_HISTORY = 3000;

export default function App() {

    const [data, setData] = useState(null);
    const [history, setHistory] = useState(() => genFallback());
    const [clock, setClock] = useState("");
    const [blink, setBlink] = useState(true);
    const [status, setStatus] = useState("connecting");
    const [error, setError] = useState(null);
    const [perf, setPerf] = useState(null);
    const [lastUpdate, setLastUpdate] = useState(null);
    const [flash, setFlash] = useState(false);
    const [lastSignalId, setLastSignalId] = useState("neutro");
    const [diData, setDiData] = useState(null);
    const [flowData, setFlowData] = useState(null);
    const [realtimeFlowData, setRealtimeFlowData] = useState([]);
    const [realtimeIafData, setRealtimeIafData] = useState([]);
    const [flowMode, setFlowMode] = useState("agg"); // "agg" = agressão, "abs" = absorção, "net" = saldo líquido
    const [flowSmoothing, setFlowSmoothing] = useState(3); // Default 3 periods
    const [iafSmoothing, setIafSmoothing] = useState(3); // Default 3 periods
    const [flowWeights, setFlowWeights] = useState({ fln: 20, pers: 40, conc: 30, abs: 10 });
    const [selectedDate, setSelectedDate] = useState("");  // "" = HOJE (live)
    const [histDates, setHistDates] = useState([]);
    const [histDayData, setHistDayData] = useState(null);
    const [histLoading, setHistLoading] = useState(false);
    const [fullHistory, setFullHistory] = useState([]);
    const flashTimerRef = useRef(null);
    const audioCtxRef = useRef(null);
    const zScoreChartRef = useRef(null);
    const histogramChartRef = useRef(null);
    const indexChartRef = useRef(null);
    const flowDeltaChartRef = useRef(null);
    const flowScoreChartRef = useRef(null);
    const flowAccelerationChartRef = useRef(null);
    const [showSetup, setShowSetup] = useState(false);
    const [workspaceTab, setWorkspaceTab] = useState("COCKPIT"); // "COCKPIT" | "RAIO_X" | "STAT_ARB"
    const [compassData, setCompassData] = useState(null);
    const [gexWalls, setGexWalls] = useState([]);
    const [weights, setWeights] = useState({
        "XP": -1,
        "UBS": 1,
        "BTG": -1,
        "IDEAL": 1,
        "GENIAL": -1,
        "JPMORGAN": 1,
        "TULLETT": 1,
        "MERRILL": 1,
        "GOLDMAN": 1,
        "MORGAN": 1,
        "CITI": 1,
        "ITAU": 0,
        "BRADESCO": 1
    });
    const [classifications, setClassifications] = useState({
        "XP": "dummy",
        "UBS": "smart",
        "BTG": "dummy",
        "IDEAL": "smart",
        "GENIAL": "dummy",
        "JPMORGAN": "smart",
        "TULLETT": "smart",
        "MERRILL": "smart",
        "GOLDMAN": "smart",
        "MORGAN": "smart",
        "CITI": "smart",
        "ITAU": "none",
        "BRADESCO": "smart"
    });

    const isViewingHistory = selectedDate !== "";

    // Listener or Fetcher for GEX Walls
    useEffect(() => {
        if (import.meta.env.PROD) {
            const wallsRef = ref(db, 'daily_levels/win_gex/walls');
            const unsub = onValue(wallsRef, (snapshot) => {
                const data = snapshot.val();
                if (data) {
                    setGexWalls(data);
                } else {
                    setGexWalls([]);
                }
            });
            return () => unsub();
        } else {
            let active = true;
            async function fetchLocalWalls() {
                try {
                    const res = await fetch("http://localhost:8080/api/gex-walls");
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
    }, []);


    // Relógio
    useEffect(() => {
        const t = setInterval(() => setClock(new Date().toLocaleTimeString("pt-BR")), 1000);
        return () => clearInterval(t);
    }, []);

    // Blink
    useEffect(() => {
        const t = setInterval(() => setBlink(b => !b), 700);
        return () => clearInterval(t);
    }, []);

    // Polling da API (Local) ou Listener (Firebase Produção)
    useEffect(() => {
        let active = true;

        if (import.meta.env.PROD && !isViewingHistory) {
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
                        // FIXED: Firebase dashboard now no longer contains a massive 30-day history array.
                        // Instead we use val.regime.history which has the current day's bars, 
                        // exactly like localhost endpoint behavior.
                        setHistory(val.regime?.history || []);
                        if (val.performance && !val.performance.error) setPerf(val.performance);
                        if (val.di_regime && !val.di_regime.error) setDiData(val.di_regime);
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
                try {
                    const currentApiUrl = API_URL;
                    const [res, resPerf, resDi] = await Promise.all([
                        fetch(currentApiUrl).catch(() => null),
                        fetch(API_PERF_URL).catch(() => null),
                        fetch(API_DI_URL).catch(() => null),
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
                    setError("Servidor Python não encontrado em localhost:8080. Mostrando dados simulados.");
                }
            }
            poll();
            const t = setInterval(poll, POLL_MS);
            return () => { active = false; clearInterval(t); };
        }
    }, [selectedDate, isViewingHistory]);

    // Polling rápido do fluxo (apenas local)
    useEffect(() => {
        if (import.meta.env.PROD || isViewingHistory) return;
        
        let active = true;
        async function pollFlow() {
            try {
                const res = await fetch(API_FLOW_URL);
                if (res.ok) {
                    const json = await res.json();
                    if (active && json && !json.error) {
                        setFlowData(json);
                    }
                }
            } catch (e) {
                // Silencioso para não poluir o console
            }
        }
        pollFlow();
        const t = setInterval(pollFlow, 250); // atualiza a cada 250ms (4x por segundo)
        return () => { active = false; clearInterval(t); };
    }, [isViewingHistory]);

    useEffect(() => {
        if (import.meta.env.PROD || isViewingHistory) return;
        let active = true;
        async function pollCompass() {
            try {
                const res = await fetch(API_COMPASS_URL);
                if (res.ok) {
                    const json = await res.json();
                    if (active && json && json.ok) setCompassData(json);
                }
            } catch (e) {}
        }
        pollCompass();
        const t = setInterval(pollCompass, 1800);
        return () => { active = false; clearInterval(t); };
    }, [isViewingHistory]);

    // Polling do indicador sintético de fluxo em tempo real (apenas local e live)
    useEffect(() => {
        if (isViewingHistory) return;
        
        let active = true;
        async function pollRealtimeFlow() {
            try {
                const url = `${API_FLOW_REALTIME_URL}?w_fln=${flowWeights.fln / 100}&w_pers=${flowWeights.pers / 100}&w_conc=${flowWeights.conc / 100}&w_abs=${flowWeights.abs / 100}`;
                const res = await fetch(url);
                if (res.ok) {
                    const json = await res.json();
                    if (active && json && Array.isArray(json)) {
                        const aligned = json.map(pt => ({
                            ...pt,
                            time: alignTimestampTo2025(pt.time)
                        }));
                        setRealtimeFlowData(aligned);
                    }
                }
            } catch (e) {
                // Silencioso
            }
        }
        pollRealtimeFlow();
        const t = setInterval(pollRealtimeFlow, 2500); // 2.5s update frequency
        return () => { active = false; clearInterval(t); };
    }, [isViewingHistory, flowWeights]);

    // Fetch IAF history (both live and historical date)
    useEffect(() => {
        let active = true;
        async function fetchIafHistory() {
            try {
                const url = isViewingHistory 
                    ? `http://localhost:8080/api/flow/iaf-history?date_str=${selectedDate}`
                    : `http://localhost:8080/api/flow/iaf-history`;
                const res = await fetch(url);
                if (res.ok) {
                    const json = await res.json();
                    if (active && json && Array.isArray(json)) {
                        const aligned = json.map(pt => ({
                            ...pt,
                            time: alignTimestampTo2025(pt.time)
                        }));
                        setRealtimeIafData(aligned);
                    }
                }
            } catch (e) {
                // Silencioso
            }
        }
        fetchIafHistory();
        if (!isViewingHistory) {
            const t = setInterval(fetchIafHistory, 5000);
            return () => { active = false; clearInterval(t); };
        }
        return () => { active = false; };
    }, [selectedDate, isViewingHistory]);

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
        async function loadDates() {
            try {
                let jsonHistory = [];
                if (import.meta.env.PROD) {
                    const histRef = ref(db, 'history_30d');
                    const snapshot = await get(histRef);
                    jsonHistory = snapshot.val() || [];
                } else {
                    const res = await fetch(`${API_HISTORY_URL}?days=30`);
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
    }, []);

    // ── Fetch data for selected historical date ──────────────────────────
    const fetchDayData = useCallback(async (date) => {
        if (!date) { setHistDayData(null); return; }
        setHistLoading(true);
        try {
            let jsonHistory = [];
            if (import.meta.env.PROD) {
                const histRef = ref(db, 'history_30d');
                const snapshot = await get(histRef);
                jsonHistory = snapshot.val() || [];
            } else {
                const res = await fetch(`${API_HISTORY_URL}?days=30`);
                const json = await res.json();
                jsonHistory = json.history || [];
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
    }, []);

    useEffect(() => { fetchDayData(selectedDate); }, [selectedDate, fetchDayData]);

    // (isViewingHistory foi movido para cima)

    // ── Derived state ──────────────────────────────────────────────────────────
    const currentZ = data ? data.current_z : (history.length > 0 ? history[history.length - 1].z : 0);
    const currentRho = data ? data.current_rho : -0.67;
    const sig = data ? data.signal : getSignal(currentZ);
    const meta = data ? data.meta : { symbol_a: "WIN$N", symbol_b: "WDO$N", beta: -22.5, window: 40, timeframe: "M5" };
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

    // Group/downsample the 5-second realtimeFlowData to 5-minute bars matching paddedSignals
    const flowScore5mData = useMemo(() => {
        if (!paddedSignals || paddedSignals.length === 0) return [];
        
        // 1. Group and average intra-bar ticks
        const rawBars = paddedSignals.map(s => {
            if (!s.bar_time) return null;
            const t = timeStrToTimestamp(s.bar_time);
            if (t === 0) return null;
            
            // If this is a future empty bar (no price or z-score data), plot whitespace to align timescales
            if (s.win_price == null && s.z == null && s.z_raw_wdo == null) {
                return { time: t, value: null, isPlaceholder: true };
            }
            
            // Find ticks in realtimeFlowData that fall into the 5-minute range: [t, t + 300)
            const ticksInBar = realtimeFlowData.filter(pt => pt.time >= t && pt.time < t + 300);
            
            let value = null;
            
            if (ticksInBar.length > 0) {
                // Compute the average of all ticks in this 5-minute interval
                const sum = ticksInBar.reduce((acc, pt) => acc + pt.value, 0);
                value = sum / ticksInBar.length;
            } else {
                // Fallback: find the last available tick before t
                const ticksBefore = realtimeFlowData.filter(pt => pt.time < t);
                if (ticksBefore.length > 0) {
                    value = ticksBefore[ticksBefore.length - 1].value;
                }
            }
            
            return {
                time: t,
                value: value,
                isPlaceholder: false
            };
        }).filter(Boolean);

        // 2. Apply Simple Moving Average (SMA) smoothing
        return rawBars.map((bar, idx) => {
            if (bar.isPlaceholder || bar.value === null) {
                return { time: bar.time };
            }
            
            if (flowSmoothing <= 1) {
                // No SMA smoothing, just classify color based on raw average
                const val = bar.value;
                let color = "#f5a623"; // Yellow
                if (val >= 40.0) color = "#00e87a"; // Green
                else if (val <= -40.0) color = "#ff3860"; // Red
                
                return {
                    time: bar.time,
                    value: parseFloat(val.toFixed(2)),
                    color: color
                };
            }
            
            // Calculate SMA of period flowSmoothing
            let sum = 0;
            let count = 0;
            for (let i = Math.max(0, idx - (flowSmoothing - 1)); i <= idx; i++) {
                if (rawBars[i] && rawBars[i].value !== null && !rawBars[i].isPlaceholder) {
                    sum += rawBars[i].value;
                    count++;
                }
            }
            
            const avgVal = count > 0 ? sum / count : bar.value;
            
            let color = "#f5a623"; // Yellow
            if (avgVal >= 40.0) color = "#00e87a"; // Green
            else if (avgVal <= -40.0) color = "#ff3860"; // Red
            
            return {
                time: bar.time,
                value: parseFloat(avgVal.toFixed(2)),
                color: color
            };
        });
    }, [paddedSignals, realtimeFlowData, flowSmoothing]);

    // Align IAF history data to paddedSignals timeline
    const iafChartData = useMemo(() => {
        if (!paddedSignals || paddedSignals.length === 0) return [];
        return paddedSignals.map(s => {
            if (!s.bar_time) return null;
            const t = timeStrToTimestamp(s.bar_time);
            if (t === 0) return null;
            
            if (s.win_price == null && s.z == null && s.z_raw_wdo == null) {
                return { time: t, value: null, isPlaceholder: true };
            }
            
            const matched = realtimeIafData.find(pt => pt.time === t || pt.bar_time === s.bar_time);
            return {
                time: t,
                value: matched ? matched.value : null,
                isPlaceholder: false
            };
        }).filter(Boolean);
    }, [paddedSignals, realtimeIafData]);

    // Sync Time Scales & Crosshairs
    useEffect(() => {
        const zChart = zScoreChartRef.current?.getChart();
        const hChart = histogramChartRef.current?.getChart();
        const iChart = indexChartRef.current?.getChart();
        const fChart = flowDeltaChartRef.current?.getChart();
        const fsChart = flowScoreChartRef.current?.getChart();
        const faChart = flowAccelerationChartRef.current?.getChart();

        const zSeries = zScoreChartRef.current?.getMainSeries?.();
        const hSeries = histogramChartRef.current?.getMainSeries?.();
        const iSeries = indexChartRef.current?.getMainSeries?.();
        const fSeries = flowDeltaChartRef.current?.getMainSeries?.();
        const fsSeries = flowScoreChartRef.current?.getMainSeries?.();
        const faSeries = flowAccelerationChartRef.current?.getMainSeries?.();

        if (!zChart || !hChart || !iChart) return;

        const charts = [
            { chart: zChart, series: zSeries },
            { chart: hChart, series: hSeries },
            { chart: iChart, series: iSeries }
        ];
        if (fChart) charts.push({ chart: fChart, series: fSeries });
        if (fsChart) charts.push({ chart: fsChart, series: fsSeries });
        if (faChart) charts.push({ chart: faChart, series: faSeries });

        // TIME SCALE SYNC
        let isSyncingTime = false;

        // Logical range handler for all 5-minute charts
        function getLogicalSyncHandler(sourceChart) {
            return (logicalRange) => {
                if (!logicalRange || isSyncingTime) return;
                isSyncingTime = true;
                
                // Sync logical range among all charts
                charts.forEach(c => {
                    if (c.chart !== sourceChart) {
                        try {
                            c.chart.timeScale().setVisibleLogicalRange(logicalRange);
                        } catch (e) {}
                    }
                });
                
                isSyncingTime = false;
            };
        }

        const zTimeHandler = getLogicalSyncHandler(zChart);
        const hTimeHandler = getLogicalSyncHandler(hChart);
        const iTimeHandler = getLogicalSyncHandler(iChart);
        const fTimeHandler = fChart ? getLogicalSyncHandler(fChart) : null;
        const fsTimeHandler = fsChart ? getLogicalSyncHandler(fsChart) : null;
        const faTimeHandler = faChart ? getLogicalSyncHandler(faChart) : null;

        zChart.timeScale().subscribeVisibleLogicalRangeChange(zTimeHandler);
        hChart.timeScale().subscribeVisibleLogicalRangeChange(hTimeHandler);
        iChart.timeScale().subscribeVisibleLogicalRangeChange(iTimeHandler);
        if (fChart && fTimeHandler) fChart.timeScale().subscribeVisibleLogicalRangeChange(fTimeHandler);
        if (fsChart && fsTimeHandler) fsChart.timeScale().subscribeVisibleLogicalRangeChange(fsTimeHandler);
        if (faChart && faTimeHandler) faChart.timeScale().subscribeVisibleLogicalRangeChange(faTimeHandler);

        // MAP DATA FOR CROSSHAIR PRICES

        function findFlowSnapshotForTime(flowHistory, targetTime) {
            if (!flowHistory || flowHistory.length === 0) return null;
            let bestSnap = null;
            for (let i = flowHistory.length - 1; i >= 0; i--) {
                const snap = flowHistory[i];
                if (snap.time <= targetTime) {
                    bestSnap = snap;
                    break;
                }
            }
            return bestSnap || flowHistory[0];
        }

        const symbol = meta?.symbol_a ? (meta.symbol_a.includes("WDO") ? "WDO" : "WIN") : "WIN";
        const timeToZPrice = new Map();
        const timeToIPrice = new Map();
        const timeToHPrice = new Map();
        const timeToFPrice = new Map();
        const timeToFsPrice = new Map();
        const timeToFaPrice = new Map();

        paddedSignals.forEach(s => {
            if (!s.bar_time) return;
            const t = timeStrToTimestamp(s.bar_time);
            if (t === 0) return;
            timeToZPrice.set(t, s.z_raw_wdo ?? s.z ?? 0);
            timeToIPrice.set(t, s.win_price ?? 0);
            timeToHPrice.set(t, 3);

            const snap = findFlowSnapshotForTime(flowData?.history, s.bar_time);
            if (snap) {
                const snapFlow = snap[symbol] || {};
                let followedSum = 0;
                Object.keys(snapFlow).forEach(b => {
                    const brokerVal = snapFlow[b];
                    let val = 0;
                    if (brokerVal !== undefined && brokerVal !== null) {
                        if (typeof brokerVal === 'object') {
                            const net = brokerVal.net || 0;
                            const buy = brokerVal.buy || 0;
                            const sell = brokerVal.sell || 0;
                            if (flowMode === 'agg') val = buy - sell;
                            else if (flowMode === 'abs') val = net - (buy - sell);
                            else val = net;
                        } else {
                            if (flowMode === 'agg') val = brokerVal;
                            else if (flowMode === 'abs') val = 0;
                            else val = brokerVal;
                        }
                    }
                    const cls = classifications[b] || "none";
                    if (cls === "smart") followedSum += val;
                });
                timeToFPrice.set(t, followedSum);
            } else {
                timeToFPrice.set(t, 0);
            }
        });

        if (flowScore5mData && flowScore5mData.length > 0) {
            flowScore5mData.forEach(pt => {
                timeToFsPrice.set(pt.time, pt.value);
            });
        }

        if (iafChartData && iafChartData.length > 0) {
            iafChartData.forEach(pt => {
                timeToFaPrice.set(pt.time, pt.value);
            });
        }

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
                            } else if (c.chart === fChart) {
                                targetTime = getClosestTimestampForSeries(timeToFPrice, t);
                                price = timeToFPrice.get(targetTime) ?? 0;
                            } else if (c.chart === fsChart) {
                                targetTime = getClosestTimestampForSeries(timeToFsPrice, t);
                                price = timeToFsPrice.get(targetTime) ?? 0;
                            } else if (c.chart === faChart) {
                                targetTime = getClosestTimestampForSeries(timeToFaPrice, t);
                                price = timeToFaPrice.get(targetTime) ?? 0;
                            }
                            
                            try {
                                c.chart.setCrosshairPosition(price, targetTime, c.series);
                            } catch(e) {}
                        }
                    });
                }
                isSyncingCrosshair = false;
            };
        }

        const zCrosshairHandler = getCrosshairHandler(zChart);
        const hCrosshairHandler = getCrosshairHandler(hChart);
        const iCrosshairHandler = getCrosshairHandler(iChart);
        const fCrosshairHandler = fChart ? getCrosshairHandler(fChart) : null;
        const fsCrosshairHandler = fsChart ? getCrosshairHandler(fsChart) : null;
        const faCrosshairHandler = faChart ? getCrosshairHandler(faChart) : null;

        zChart.subscribeCrosshairMove(zCrosshairHandler);
        hChart.subscribeCrosshairMove(hCrosshairHandler);
        iChart.subscribeCrosshairMove(iCrosshairHandler);
        if (fChart && fCrosshairHandler) fChart.subscribeCrosshairMove(fCrosshairHandler);
        if (fsChart && fsCrosshairHandler) fsChart.subscribeCrosshairMove(fsCrosshairHandler);
        if (faChart && faCrosshairHandler) faChart.subscribeCrosshairMove(faCrosshairHandler);

        return () => {
            zChart.timeScale().unsubscribeVisibleLogicalRangeChange(zTimeHandler);
            hChart.timeScale().unsubscribeVisibleLogicalRangeChange(hTimeHandler);
            iChart.timeScale().unsubscribeVisibleLogicalRangeChange(iTimeHandler);
            if (fChart && fTimeHandler) fChart.timeScale().unsubscribeVisibleLogicalRangeChange(fTimeHandler);
            if (fsChart && fsTimeHandler) fsChart.timeScale().unsubscribeVisibleLogicalRangeChange(fsTimeHandler);
            if (faChart && faTimeHandler) faChart.timeScale().unsubscribeVisibleLogicalRangeChange(faTimeHandler);

            zChart.unsubscribeCrosshairMove(zCrosshairHandler);
            hChart.unsubscribeCrosshairMove(hCrosshairHandler);
            iChart.unsubscribeCrosshairMove(iCrosshairHandler);
            if (fChart && fCrosshairHandler) fChart.unsubscribeCrosshairMove(fCrosshairHandler);
            if (fsChart && fsCrosshairHandler) fsChart.unsubscribeCrosshairMove(fsCrosshairHandler);
            if (faChart && faCrosshairHandler) faChart.unsubscribeCrosshairMove(faCrosshairHandler);
        };
    }, [paddedSignals, flowData, flowScore5mData, iafChartData, weights, classifications, meta, flowMode, workspaceTab]); // Re-bind when data, weights, or classifications update

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
        if (p < 0.01) return { label: "FORTE", color: "#00e87a" };
        if (p < 0.05) return { label: "PRESENTE", color: "#c8a444" };
        if (p < 0.10) return { label: "FRACA", color: "#f5a623" };
        return { label: "QUEBRADA", color: "#ff3860" };
    };
    const cointInfo = getCointStatus(cointEg.pvalue);

    // ── Count active signals for consensus badge (WDO + DI) ────────────────────
    const lastBar = mergedSignals.length > 0 ? mergedSignals[mergedSignals.length - 1] : {};
    const buyCount = [lastBar.cons_wdo_sig, lastBar.cons_di_sig].filter(v => v < 0).length;
    const sellCount = [lastBar.cons_wdo_sig, lastBar.cons_di_sig].filter(v => v > 0).length;
    const consensusCount = Math.max(buyCount, sellCount);
    const consensusDir = buyCount > sellCount ? "COMPRA" : sellCount > buyCount ? "VENDA" : null;
    const consensusColor = consensusDir === "COMPRA" ? "#00e87a" : consensusDir === "VENDA" ? "#ff3860" : "#3a5060";

    // ── Johansen gate data ─────────────────────────────────────────────────────
    const johWdoGate = data?.johansen_gate || null;
    const johDiGate = diData?.johansen_gate || null;

    return (
        <>
            {/* Loading Overlay */}
            {(!data && !isViewingHistory) && (
                <div className="skeleton-loader">
                    <div className="skeleton-pulse">AGUARDANDO MODELO MATADOR V4...</div>
                </div>
            )}
        <div style={{ background: "#0d1117", minHeight: "100vh", color: "#c9d1d9", fontFamily: "monospace", display: "flex", flexDirection: "column" }}>

            {/* ── Topbar ──────────────────────────────────────────────────────────── */}
            <div className="topbar">
                <div className="topbar-left">
                    <span className="text-sm text-highlight font-bold" style={{ letterSpacing: 4 }}>PAIR TRADING</span>
                    <span style={{ display: "inline-block", width: 1, height: 14, background: "#1c2e3a" }} />
                    <span className="text-xs text-muted" style={{ letterSpacing: 2 }}>
                        {meta.symbol_a} x {meta.symbol_b}  ·  STAT ARB  ·  {meta.timeframe}
                    </span>
                    <span 
                        className="text-xxs text-highlight font-bold" 
                        style={{ 
                            background: showSetup ? "rgba(200,164,68,0.3)" : "rgba(200,164,68,0.15)", 
                            border: "1px solid #c8a44455", 
                            borderRadius: 4, 
                            padding: "3px 8px", 
                            marginLeft: 15, 
                            letterSpacing: 1,
                            cursor: "pointer",
                            transition: "background 0.2s"
                        }}
                        onClick={() => setShowSetup(s => !s)}
                        title="Ver regras do Setup Matador V6"
                    >
                        MATADOR
                    </span>
                </div>
                <div className="topbar-right">
                    {lastUpdate && (
                        <div style={{
                            display: "flex", alignItems: "center", gap: 6,
                            background: flash ? "rgba(200,164,68,0.18)" : "transparent",
                            border: `1px solid ${flash ? "#c8a444" : "#1c2e3a"}`,
                            borderRadius: 4, padding: "3px 10px",
                            transition: "background 0.3s, border-color 0.3s"
                        }}>
                            <span className="text-xxs text-muted" style={{ letterSpacing: 2 }}>ANÃLISE</span>
                            <span className="text-sm font-bold" style={{ color: flash ? "#c8a444" : "#8ca5b5", letterSpacing: 1, transition: "color 0.3s" }}>
                                {lastUpdate}
                            </span>
                        </div>
                    )}
                    {/* Johansen Gate badge */}
                    {johWdoGate && (
                        <div style={{
                            display: "flex", alignItems: "center", gap: 6,
                            background: johWdoGate.open ? "rgba(0,232,122,0.15)" : "rgba(255,56,96,0.15)",
                            border: `1px solid ${johWdoGate.open ? "#00e87a55" : "#ff386055"}`,
                            borderRadius: 4, padding: "3px 10px"
                        }}>
                            <span style={{ fontSize: 8, color: johWdoGate.open ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                JOH: {johWdoGate.open ? "ABERTO" : "FECHADO"} ({johWdoGate.trace_ratio}x)
                            </span>
                        </div>
                    )}

                    {/* Consensus badge */}
                    {consensusCount >= 2 && (
                        <div style={{
                            display: "flex", alignItems: "center", gap: 5,
                            background: `${consensusColor}18`,
                            border: `1px solid ${consensusColor}55`,
                            borderRadius: 4, padding: "3px 10px",
                            opacity: blink && consensusCount === 2 ? 1 : 0.85,
                            transition: "opacity 0.3s"
                        }}>
                            <span style={{ fontSize: 9, fontWeight: "bold", color: consensusColor, letterSpacing: 1 }}>
                                {consensusDir} {consensusCount}/2
                            </span>
                        </div>
                    )}
                    {/* NWE state badge */}
                    {data?.nwe && (
                        <div style={{
                            display: "flex", alignItems: "center", gap: 5,
                            background: data.nwe.is_up ? "rgba(0,232,122,0.12)" : "rgba(255,56,96,0.12)",
                            border: `1px solid ${data.nwe.is_up ? "#00e87a33" : "#ff386033"}`,
                            borderRadius: 4, padding: "3px 10px",
                        }}>
                            <span style={{ fontSize: 8, fontWeight: "bold", color: data.nwe.is_up ? "#00e87a" : "#ff3860", letterSpacing: 1 }}>
                                NWE {data.nwe.is_up ? "▲" : "▼"}
                            </span>
                        </div>
                    )}
                    {/* Per-strategy status badges */}
                    {data?.trade_engine?.strategies && (
                        <div style={{ display: "flex", gap: 4 }}>
                            {Object.entries(data.trade_engine.strategies).map(([key, val]) => {
                                const info = STRAT_LABELS[key];
                                if (!info) return null;
                                const isHolding = val?.open_trade != null;
                                const action = val?.action || "WAIT";
                                const isBuy = action === "BUY_WIN";
                                const isSell = action === "SELL_WIN";
                                const isEntry = isBuy || isSell;
                                const bg = isHolding ? "rgba(245,166,35,0.15)" : isEntry ? (isBuy ? "rgba(0,232,122,0.15)" : "rgba(255,56,96,0.15)") : "rgba(58,80,96,0.08)";
                                const fg = isHolding ? "#f5a623" : isEntry ? (isBuy ? "#00e87a" : "#ff3860") : "#3a5060";
                                return (
                                    <div key={key} style={{
                                        display: "flex", alignItems: "center", gap: 3,
                                        background: bg, border: `1px solid ${fg}33`, borderRadius: 3, padding: "2px 6px",
                                    }}>
                                        <span style={{ fontSize: 7, color: info.color, fontWeight: "bold" }}>{info.label}</span>
                                        <span style={{ fontSize: 7, color: fg, fontWeight: "bold" }}>
                                            {isHolding ? (val.open_trade?.direction === "BUY" ? "C" : "V") : isEntry ? (isBuy ? "C!" : "V!") : "—"}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                    {/* Date picker */}
                    <select
                        value={selectedDate}
                        onChange={e => setSelectedDate(e.target.value)}
                        style={{
                            padding: "4px 10px", fontSize: 11, fontFamily: "monospace",
                            background: isViewingHistory ? "#1a2530" : "#0d1820",
                            border: `1px solid ${isViewingHistory ? "#c8a444" : "#1c2e3a"}`,
                            borderRadius: 6, color: isViewingHistory ? "#c8a444" : "#8a9aaa",
                            cursor: "pointer", outline: "none", minWidth: 130,
                            appearance: "none",
                            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%233a5060'/%3E%3C/svg%3E")`,
                            backgroundRepeat: "no-repeat", backgroundPosition: "right 8px center",
                            paddingRight: 24,
                        }}
                    >
                        <option value="">HOJE (LIVE)</option>
                        {histDates.map(d => {
                            const [y, m, day] = d.split("-");
                            const wd = new Date(y, m - 1, day).toLocaleDateString("pt-BR", { weekday: "short" });
                            return <option key={d} value={d}>{wd} {day}/{m}</option>;
                        })}
                    </select>
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                        <span style={{
                            display: "inline-block", width: 6, height: 6, borderRadius: "50%",
                            background: isViewingHistory ? "#c8a444" : status === "live" ? "#00e87a" : status === "fallback" ? "#f5a623" : "#3a5060",
                            opacity: blink ? 1 : 0.2, transition: "opacity 0.3s"
                        }} />
                        <span style={{
                            fontSize: 9, letterSpacing: 2,
                            color: isViewingHistory ? "#c8a444" : status === "live" ? "#00e87a" : status === "fallback" ? "#f5a623" : "#3a5060"
                        }}>
                            {isViewingHistory ? "HISTÓRICO" : status === "live" ? "MT5 LIVE" : status === "fallback" ? "SIMULADO" : "CONECTANDO"}
                        </span>
                    </div>
                    <span style={{ fontSize: 13, color: "#c8a444", minWidth: 70, textAlign: "right" }}>{clock}</span>
                </div>
            </div>

            {/* ── Banners ─────────────────────────────────────────────────────────── */}
            {error && (
                <div style={{ background: "rgba(245,166,35,0.08)", borderBottom: "1px solid rgba(245,166,35,0.3)", padding: "6px 20px", fontSize: 10, color: "#f5a623" }}>
                    {error}
                </div>
            )}
            {betaUnstable && (
                <div style={{
                    background: "rgba(255,56,96,0.08)",
                    borderBottom: "1px solid rgba(255,56,96,0.4)",
                    padding: "7px 20px", fontSize: 11, color: "#ff3860",
                    display: "flex", alignItems: "center", gap: 10,
                    opacity: blink ? 1 : 0.6, transition: "opacity 0.3s"
                }}>
                    <span style={{ fontSize: 16 }}>⚠️</span>
                    <span>
                        <strong>BETA INSTÁVEL</strong> — variação de <span style={{ fontWeight: 900 }}>{betaChangePct > 0 ? "+" : ""}{betaChangePct.toFixed(1)}%</span> em relação à leitura anterior.
                        Relação WIN×WDO pode estar em ruptura.
                    </span>
                </div>
            )}

            {/* ——— Barra Principal de Seleção de Tela (3 Modos Limpos) ———————————————————— */}
            <div style={{
                background: "#090f16",
                borderBottom: "1px solid #18293a",
                padding: "8px 20px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 10,
            }}>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {[
                        { id: "COCKPIT", label: "🧭 1. COCKPIT OPERACIONAL (SINAIS NO TEMPO & PAREDES)", accent: "#00e87a" },
                        { id: "RAIO_X", label: "🔬 2. RAIO-X DE DADOS (CORRETORAS PROFIT & GRADE OPÇÕES)", accent: "#00d4ff" },
                        { id: "STAT_ARB", label: "📐 3. STAT-ARB & Z-SCORE (GRÁFICOS WIN × WDO × DI)", accent: "#c8a444" },
                    ].map(tab => {
                        const active = !isViewingHistory && workspaceTab === tab.id;
                        return (
                            <button
                                key={tab.id}
                                onClick={() => {
                                    if (isViewingHistory) setSelectedDate("");
                                    setWorkspaceTab(tab.id);
                                }}
                                style={{
                                    padding: "7px 14px",
                                    fontSize: 10.5,
                                    fontFamily: "monospace",
                                    fontWeight: "bold",
                                    letterSpacing: 0.6,
                                    borderRadius: 6,
                                    cursor: "pointer",
                                    border: active ? `1.5px solid ${tab.accent}` : "1px solid #1c2d3e",
                                    background: active ? `${tab.accent}22` : "#0d151e",
                                    color: active ? tab.accent : "#8ca5b5",
                                    transition: "all 0.2s ease",
                                }}
                            >
                                {tab.label}
                            </button>
                        );
                    })}
                </div>
                {compassData?.updated_at && (
                    <span style={{ fontSize: 10, color: "#7f96a8" }}>
                        Fluxo Profit/MT5 atualizado às <strong style={{ color: "#00e87a" }}>{compassData.updated_at}</strong>
                    </span>
                )}
            </div>

            {/* ——— Main content ———————————————————————————————————————————————————————————— */}
            <div style={{ flex: 1, padding: "14px 20px", display: "flex", flexDirection: "column", gap: 12 }}>

                {showSetup && <SetupMatadorPanel tradeEngine={data?.trade_engine} />}

                {!isViewingHistory && (workspaceTab === "COCKPIT" || workspaceTab === "RAIO_X") && (
                    <IntradayCompassPanel
                        compassData={compassData}
                        mode={workspaceTab}
                        onChangeMode={setWorkspaceTab}
                    />
                )}

                {/* History mode banner */}
                {isViewingHistory && (
                    <div style={{
                        background: "rgba(200,164,68,0.08)", border: "1px solid rgba(200,164,68,0.3)",
                        borderRadius: 8, padding: "6px 16px", display: "flex", justifyContent: "space-between", alignItems: "center",
                    }}>
                        <span style={{ fontSize: 10, color: "#c8a444" }}>
                            📅 Visualizando Z-Score de <strong>{(() => { const [y, m, d] = selectedDate.split("-"); return `${d}/${m}/${y}`; })()}</strong>
                            {histDayData && ` — ${histDayData.length} barras`}
                        </span>
                        <button onClick={() => setSelectedDate("")} style={{
                            fontSize: 9, padding: "3px 10px", background: "rgba(0,232,122,0.15)",
                            border: "1px solid #00e87a55", borderRadius: 4, color: "#00e87a",
                            cursor: "pointer", fontFamily: "monospace", letterSpacing: 1,
                        }}>VOLTAR AO LIVE</button>
                    </div>
                )}

                {(isViewingHistory || workspaceTab === "STAT_ARB") && (
                <>
                {/* Compact Regime Health Strip — above charts */}
                {(() => {
                    const zWdo = isViewingHistory ? lastBar.z : currentZ;
                    const zDi = isViewingHistory ? (lastBar.z_di ?? lastBar.z_unfiltered_di ?? 0) : (diData?.current_z ?? 0);
                    const betaH = data?.regime_health?.beta;
                    const diBetaH = diData?.regime_health?.beta;
                    const diRhoH = diData?.regime_health?.rho;
                    const zColor = (v) => Math.abs(v || 0) >= 1.4 ? (v > 0 ? "#ff3860" : "#00e87a") : "#6f8a9c";
                    const Pill = ({ label, value, color, badge }) => (
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                            <span style={{ fontSize: 8, color: "#4a6070", letterSpacing: 0.5 }}>{label}</span>
                            <span style={{ fontSize: 10, fontWeight: "bold", color: color || "#6f8a9c", fontFamily: "monospace" }}>
                                {typeof value === "number" ? value.toFixed(3) : value ?? "—"}
                            </span>
                            {badge && (
                                <span style={{ fontSize: 7, color: "#0c1218", background: color, fontWeight: "bold", padding: "0px 4px", borderRadius: 2 }}>{badge}</span>
                            )}
                        </span>
                    );
                    const Dot = ({ gate, label }) => {
                        if (!gate) return null;
                        const c = gate.open ? "#00e87a" : "#ff3860";
                        return (
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                                <span style={{ fontSize: 8, color: "#4a6070", letterSpacing: 0.5 }}>{label}</span>
                                <span style={{ display: "inline-block", width: 5, height: 5, borderRadius: "50%", background: c, boxShadow: `0 0 4px ${c}55` }} />
                                <span style={{ fontSize: 8, color: c, fontWeight: "bold" }}>{gate.open ? "A" : "F"}</span>
                            </span>
                        );
                    };
                    return (
                        <div style={{
                            display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap",
                            padding: "5px 10px", marginBottom: -2,
                            background: "#0c1218", borderRadius: "8px 8px 0 0",
                            border: "1px solid #1a2530", borderBottom: "none",
                        }}>
                            {/* WDO section */}
                            <span style={{ fontSize: 8, color: "#c8a444", fontWeight: "bold", letterSpacing: 2 }}>WDO</span>
                            <Pill label="Z" value={zWdo} color={zColor(zWdo)} />
                            {betaH && <Pill label="β" value={betaH.delta_pct} color={betaH.color} badge={betaH.status} />}
                            <Dot gate={johWdoGate} label="JOH" />

                            <span style={{ display: "inline-block", width: 1, height: 12, background: "#1c2e3a", margin: "0 4px" }} />

                            {/* DI section */}
                            <span style={{ fontSize: 8, color: "#8a6dff", fontWeight: "bold", letterSpacing: 2 }}>DI</span>
                            <Pill label="Z" value={zDi} color={zColor(zDi)} />
                            {diBetaH && <Pill label="β" value={diBetaH.delta_pct} color={diBetaH.color} badge={diBetaH.status} />}
                            {diRhoH && <Pill label="ρ" value={diRhoH.value} color={diRhoH.color} badge={diRhoH.status} />}
                            <Dot gate={johDiGate} label="JOH" />
                        </div>
                    );
                })()}

                {/* Z-Score Chart + Signal Histogram (grouped) */}
                <div style={{ marginTop: 0 }}>
                    <ZScoreChart
                        ref={zScoreChartRef}
                        history={paddedSignals}
                        sigColor={isViewingHistory ? "#00e87a" : sig.color}
                        currentZ={isViewingHistory ? 0 : currentZ}
                        useV2={true}
                        hideXAxis={true}
                    />
                    <SignalHistogram ref={histogramChartRef} data={paddedSignals} />
                    <IndexChart ref={indexChartRef} history={paddedSignals} walls={gexWalls} hideXAxis={true} />
                    <FlowDeltaChart
                        ref={flowDeltaChartRef}
                        history={paddedSignals}
                        flowData={flowData}
                        classifications={classifications}
                        activeSymbol={meta?.symbol_a}
                        flowMode={flowMode}
                    />
                    <FlowScoreChart
                        ref={flowScoreChartRef}
                        history={flowScore5mData}
                        smoothing={flowSmoothing}
                        onSmoothingChange={setFlowSmoothing}
                        weights={flowWeights}
                        onWeightsChange={setFlowWeights}
                        hideXAxis={true}
                    />
                    <FlowAccelerationChart
                        ref={flowAccelerationChartRef}
                        history={iafChartData}
                        smoothing={iafSmoothing}
                        onSmoothingChange={setIafSmoothing}
                    />
                </div>

                {/* Order Flow / RTD Broker Monitor */}
                <BrokerFlowPanel
                    flowData={flowData}
                    dbHistory={paddedSignals}
                    weights={weights}
                    setWeights={setWeights}
                    classifications={classifications}
                    setClassifications={setClassifications}
                    flowMode={flowMode}
                    setFlowMode={setFlowMode}
                />






                {/* Alert Banner */}
                {!safeToTrade && isActive && (
                    <div style={{
                        background: "rgba(255,56,96,0.06)", border: "1px solid rgba(255,56,96,0.3)",
                        borderRadius: 8, padding: "10px 16px", display: "flex", alignItems: "center", gap: 10,
                        opacity: blink ? 1 : 0.7, transition: "opacity 0.3s"
                    }}>
                        <span style={{ fontSize: 18 }}>🚨</span>
                        <div style={{ fontSize: 11, color: "#ff3860", lineHeight: 1.5 }}>
                            <strong>Z-SCORE ALTO COM RELAÇÃO INSTÁVEL</strong> — Parece oportunidade mas é ruído.
                            ρ ou Δβ fora da zona verde invalida o sinal de z={currentZ > 0 ? `+${currentZ.toFixed(2)}` : currentZ.toFixed(2)}.
                        </div>
                    </div>
                )}

                {/* Trading Guide */}
                <TradingGuide />
                </>
                )}
            </div>

            {/* ── Footer ──────────────────────────────────────────────────────────── */}
            <div style={{ borderTop: "1px solid #21262d", padding: "7px 20px", display: "flex", justifyContent: "space-between", fontSize: 8, color: "#3d444d", background: "#161b22" }}>
                <span>{status === "live" ? "DADOS REAIS MT5" : "DADOS SIMULADOS"} — NÃO CONSTITUI RECOMENDAÇÃO DE INVESTIMENTO · PAIR TRADING 2025</span>
                <span>beta = {meta.beta}  ·  janela {meta.window} barras  ·  {meta.symbol_a} x {meta.symbol_b}  ·  B3</span>
            </div>
        </div>
        </>
    );
}
