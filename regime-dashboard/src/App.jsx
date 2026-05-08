import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { ref, onValue, get } from "firebase/database";
import { db } from "./firebase";
import ZScoreChart from "./components/ZScoreChart";
import RegimeHealthPanel from "./components/RegimeHealthPanel";
import PerformancePanel from "./components/PerformancePanel";
import TradingGuide from "./components/TradingGuide";
import SignalHistogram from "./components/SignalHistogram";
import IndexChart from "./components/IndexChart";

const STRAT_LABELS = {
    CONS_BASE: { label: "CONS", color: "#00d4ff" },
    WDO_NWE: { label: "WDO", color: "#c8a444" },
    DI_NWE: { label: "DI", color: "#8a6dff" },
};

// API base: same host as the page (lets LAN/127.0.0.1/localhost all work). Override with VITE_API_BASE_URL.
const API_BASE = import.meta.env.VITE_API_BASE_URL
    || (typeof window !== "undefined" ? `${window.location.protocol}//${window.location.hostname}:8080` : "http://localhost:8080");
const API_URL = `${API_BASE}/api/v2/regime`;
const API_PERF_URL = `${API_BASE}/api/performance`;
const API_DI_URL = `${API_BASE}/api/di-regime`;
const API_HISTORY_URL = `${API_BASE}/api/history`;
const POLL_MS = 2500;

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

// ── Trade alignment helper ───────────────────────────────────────────────────

function toBarMinutes(timeStr) {
    const [h, m] = timeStr.split(":").map(Number);
    return h * 60 + m;
}

function alignTradesToBars(trades, history) {
    if (!trades?.length || !history?.length) return [];
    const barTimes = history.map(b => b.bar_time).filter(Boolean);

    function findBar(timeHHMMSS) {
        if (!timeHHMMSS) return null;
        const tMin = toBarMinutes(timeHHMMSS); // HH:MM:SS → uses first two parts
        let best = null;
        for (const bt of barTimes) {
            if (toBarMinutes(bt) <= tMin) best = bt;
            else break;
        }
        return best; // null if trade is before first available bar
    }

    return trades.map(t => ({
        ...t,
        bar_time_in: findBar(t.time_in),
        bar_time_out: t.time_out ? findBar(t.time_out) : null,
    }));
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
    const [selectedDate, setSelectedDate] = useState("");  // "" = HOJE (live)
    const [histDates, setHistDates] = useState([]);
    const [histDayData, setHistDayData] = useState(null);
    const [, setHistLoading] = useState(false);
    const [, setFullHistory] = useState([]);
    const [todayTrades, setTodayTrades] = useState([]);
    const flashTimerRef = useRef(null);
    const audioCtxRef = useRef(null);

    const isViewingHistory = selectedDate !== "";

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
            if (!db) {
                setStatus("fallback");
                setError("Configuração do Firebase indisponível.");
                setTodayTrades([]);
                return () => { active = false; };
            }

            // Em produÃ§Ã£o (Firebase Hosting), ouvir o Realtime Database
            const dashboardRef = ref(db, 'dashboard');
            const unsub = onValue(dashboardRef, (snapshot) => {
                if (!active) return;
                const val = snapshot.val();
                if (val) {
                    if (val.error) {
                        setError(val.error);
                        setStatus("fallback");
                        setTodayTrades([]);
                    } else {
                        setData(val.regime);
                        // FIXED: Firebase dashboard now no longer contains a massive 30-day history array.
                        // Instead we use val.regime.history which has the current day's bars,
                        // exactly like localhost endpoint behavior.
                        setHistory(val.regime?.history || []);
                        setTodayTrades(val.regime?.trades_today ?? []);
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
                    setTodayTrades([]);
                }
            }, () => {
                if (!active) return;
                setStatus("fallback");
                setError("Erro ao conectar no Firebase.");
                setTodayTrades([]);
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
                        setTodayTrades([]);
                    } else {
                        setData(json);
                        setHistory(json.history || []);
                        setTodayTrades(json.trades_today ?? []);
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
                } catch {
                    if (!active) return;
                    setStatus("fallback");
                    setError("Servidor Python não encontrado em localhost:8080. Mostrando dados simulados.");
                    setTodayTrades([]);
                }
            }
            poll();
            const t = setInterval(poll, POLL_MS);
            return () => { active = false; clearInterval(t); };
        }
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
            } catch { /* ignore */ }
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
        } catch { /* ignore */ }
        setHistLoading(false);
    }, []);

    useEffect(() => { fetchDayData(selectedDate); }, [selectedDate, fetchDayData]);

    // (isViewingHistory foi movido para cima)

    // ── Derived state ──────────────────────────────────────────────────────────
    const currentZ = data ? data.current_z : (history.length > 0 ? history[history.length - 1].z : 0);
    const sig = data ? data.signal : getSignal(currentZ);
    const meta = data ? data.meta : { symbol_a: "WIN$N", symbol_b: "WDO$N", beta: -22.5, window: 40, timeframe: "M5" };
    const betaChangePct = data ? data.beta_change_pct : 0;
    const betaUnstable = data ? data.beta_unstable : false;
    const rh = data ? data.regime_health : null;
    const safeToTrade = rh ? rh.safe_to_trade : true;
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

    const alignedTrades = useMemo(
        () => alignTradesToBars(todayTrades, paddedSignals),
        [todayTrades, paddedSignals]
    );

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
                } catch { /* AudioContext may be blocked by autoplay policy */ }
            }
            setLastSignalId(sig.id);
        }
    }, [sig, safeToTrade, lastSignalId]);

    // Cleanup: fechar AudioContext e limpar timers ao desmontar
    useEffect(() => {
        return () => {
            if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
            if (audioCtxRef.current) {
                try { audioCtxRef.current.close(); } catch { /* AudioContext.close may throw on already-closed */ }
            }
        };
    }, []);

    const isActive = sig.id === "compraWdo" || sig.id === "compraWin";

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
                    <span className="text-xxs text-highlight font-bold" style={{ background: "rgba(200,164,68,0.15)", border: "1px solid #c8a44455", borderRadius: 4, padding: "3px 8px", marginLeft: 15, letterSpacing: 1 }}>MATADOR</span>
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

            {/* ——— Main content ———————————————————————————————————————————————————————————— */}
            <div style={{ flex: 1, padding: "14px 20px", display: "flex", flexDirection: "column", gap: 12 }}>

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

                {/* Z-Score Chart + Signal Histogram (grouped) */}
                <div>
                    <ZScoreChart
                        history={paddedSignals}
                        useV2={true}
                        trades={isViewingHistory ? [] : alignedTrades}
                    />
                    <SignalHistogram
                        data={paddedSignals}
                        trades={isViewingHistory ? [] : alignedTrades}
                    />
                    <IndexChart
                        history={paddedSignals}
                        trades={isViewingHistory ? [] : alignedTrades}
                    />
                </div>

                {/* Regime Health */}
                {/* Regime Health */}
                <RegimeHealthPanel
                    kalmanZ={isViewingHistory ? lastBar.z_raw_wdo : currentZ}
                    kalmanBetaHealth={data?.regime_health?.beta}
                    diZ={lastBar.z_raw_di}
                    diBetaHealth={diData?.regime_health?.beta}
                    diRhoHealth={diData?.regime_health?.rho}
                    johWdoGate={johWdoGate}
                    johDiGate={johDiGate}
                    riskGate={data?.risk_gate}
                />

                {/* Performance */}
                <PerformancePanel perf={perf} />



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
