import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { ref, onValue } from "firebase/database";
import { db } from "./firebase";
import ZScoreChart from "./components/ZScoreChart";
import RegimeHealthPanel from "./components/RegimeHealthPanel";
import PerformancePanel from "./components/PerformancePanel";
import TradingGuide from "./components/TradingGuide";
import SignalHistogram from "./components/SignalHistogram";
import IndexChart, { calcNWE, BANDWIDTH, MULT_MAE } from "./components/IndexChart";

const STRAT_LABELS = {
    CONS_BASE: { label: "CONS", color: "#00d4ff" },
    WDO_NWE: { label: "WDO", color: "#c8a444" },
    DI_NWE: { label: "DI", color: "#8a6dff" },
};

const API_URL = "http://localhost:8080/api/v2/regime";
const API_PERF_URL = "http://localhost:8080/api/performance";
const API_DI_URL = "http://localhost:8080/api/di-regime";
const API_HISTORY_URL = "http://localhost:8080/api/history";
const POLL_MS = 2500;

// â”€â”€ Fallback: gera dados simulados se a API nÃ£o responder â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    if (az >= 4) return { id: "anomalia", label: "ANOMALIA", sub: "Nao operar â€” possivel breakdown", wdo: null, win: null, color: "#ff3860" };
    if (z >= 1.4) return { id: "compraWdo", label: "VENDE WIN", sub: "Z-Score positivo â€” spread revertendo", wdo: "IGNORAR", win: "VENDER", color: "#ff3860" };
    if (z <= -1.4) return { id: "compraWin", label: "COMPRA WIN", sub: "Z-Score negativo â€” spread revertendo", wdo: "IGNORAR", win: "COMPRAR", color: "#00e87a" };
    if (az >= 1.2) return { id: "atencao", label: "ZONA DE DIVERGENCIA", sub: "Aguardar Z atingir +/-1.4 para entrar", wdo: null, win: null, color: "#f5a623" };
    return { id: "neutro", label: "AGUARDAR", sub: "Spread em equilibrio â€” sem setup no momento", wdo: null, win: null, color: "#445560" };
}

// â”€â”€ Main App â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// Limite mÃ¡ximo de barras no histÃ³rico completo para evitar OOM
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
    const [histLoading, setHistLoading] = useState(false);
    const [fullHistory, setFullHistory] = useState([]);
    const flashTimerRef = useRef(null);
    const audioCtxRef = useRef(null);

    const isViewingHistory = selectedDate !== "";

    // RelÃ³gio
    useEffect(() => {
        const t = setInterval(() => setClock(new Date().toLocaleTimeString("pt-BR")), 1000);
        return () => clearInterval(t);
    }, []);

    // Blink
    useEffect(() => {
        const t = setInterval(() => setBlink(b => !b), 700);
        return () => clearInterval(t);
    }, []);

    // Polling da API (Local) ou Listener (Firebase ProduÃ§Ã£o)
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
                        setHistory(val.history || []);
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
            // Em localhost ou modo histÃ³rico, fazer polling da API
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
                    setError("Servidor Python nÃ£o encontrado em localhost:8080. Mostrando dados simulados.");
                }
            }
            poll();
            const t = setInterval(poll, POLL_MS);
            return () => { active = false; clearInterval(t); };
        }
    }, [selectedDate, isViewingHistory]);

    // SimulaÃ§Ã£o quando offline
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

    // â”€â”€ Fetch available dates on mount â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    useEffect(() => {
        async function loadDates() {
            try {
                const res = await fetch(`${API_HISTORY_URL}?days=30`);
                const json = await res.json();
                if (json.history?.length) {
                    // Limitar tamanho do histÃ³rico para evitar OOM
                    const trimmed = json.history.length > MAX_FULL_HISTORY
                        ? json.history.slice(-MAX_FULL_HISTORY)
                        : json.history;
                    setFullHistory(trimmed);
                    const dates = [...new Set(trimmed.map(h => h.date))].sort().reverse();
                    const today = new Date(new Date().getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
                    setHistDates(dates.filter(d => d !== today));
                }
            } catch (e) { /* ignore */ }
        }
        loadDates();
    }, []);

    // â”€â”€ Fetch data for selected historical date â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    const fetchDayData = useCallback(async (date) => {
        if (!date) { setHistDayData(null); return; }
        setHistLoading(true);
        try {
            const res = await fetch(`${API_HISTORY_URL}?days=30`);
            const json = await res.json();
            if (json.history?.length) {
                const dayBars = json.history.filter(h => h.date === date).map(h => ({
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

    // â”€â”€ Derived state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    const rhoStatus = rh ? rh.rho : { value: currentRho, status: "â€”", action: "", color: "#3a5060", level: 0 };
    const betaHealth = rh ? rh.beta : { current: betaOls, ref_20d: betaRef20d, delta_pct: betaDeltaPct, status: "â€”", action: "", color: "#3a5060", level: 0 };
    const cointEg = data ? data.coint_eg : { is_coint: false, pvalue: 1.0 };

    // â”€â”€ Merged signal data for histogram â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    const mergedSignals = useMemo(() => {
        const sourceData = isViewingHistory && histDayData ? histDayData : (isViewingHistory ? [] : history);
        const diMap = new Map((diData?.history || []).map(h => [h.bar_time, h.z]));

        // Seed NWE with previous day data to avoid cone effect at start of day
        let prependedPrices = [];
        if (sourceData.length > 0 && fullHistory.length > 0) {
            const firstDate = sourceData[0].date;
            if (firstDate) {
                const pastData = fullHistory.filter(h => h.date < firstDate);
                prependedPrices = pastData.slice(-100).map(h => h.win_price).filter(v => v != null && isFinite(v));
            } else {
                const todayStr = new Date(new Date().getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
                const pastData = fullHistory.filter(h => h.date < todayStr);
                prependedPrices = pastData.slice(-100).map(h => h.win_price).filter(v => v != null && isFinite(v));
            }
        }

        // Build prices array â€” forward-fill missing values to keep NWE index-aligned with sourceData
        const rawPrices = sourceData.map(h => h.win_price);
        const prices = [];
        let lastValid = prependedPrices.length > 0 ? prependedPrices[prependedPrices.length - 1] : null;
        for (const p of rawPrices) {
            if (p != null && isFinite(p)) {
                lastValid = p;
                prices.push(p);
            } else {
                prices.push(lastValid); // forward-fill
            }
        }
        // If no valid prices at all, return basic data without NWE
        if (lastValid == null) {
            return sourceData.map(h => ({ ...h, z_di: h.z_di ?? null, z_raw_wdo: h.z ?? 0, z_raw_di: h.z_di ?? 0, sig_wdo: 0, sig_di: 0 }));
        }
        // Back-fill any leading nulls
        for (let i = 0; i < prices.length; i++) {
            if (prices[i] == null) prices[i] = lastValid;
            else break;
        }
        const nweDataRaw = calcNWE([...prependedPrices, ...prices], BANDWIDTH, MULT_MAE);
        const nweData = nweDataRaw.slice(prependedPrices.length);

        return sourceData.map((h, i) => {
            // Para histÃ³rico, z_di jÃ¡ vem da API (h.z_di), para live pegamos do diMap
            const zDi = h.z_di ?? diMap.get(h.bar_time) ?? null;
            const nweObj = nweData[i] || {};

                        const winPrice = h.win_price;

            let consWdoSig = h.z <= -1.4 ? -1 : h.z >= 1.4 ? 1 : 0;
            let consDiSig = (zDi ?? 0) <= -1.4 ? -1 : (zDi ?? 0) >= 1.4 ? 1 : 0;

            let sW = consWdoSig;
            let sD = consDiSig;

            let rW = h.z;
            let rD = zDi ?? 0;

            if (nweObj.nwe !== null && winPrice != null) {
                const isBuyBlocked = nweObj.isUp || winPrice > nweObj.nweProxLower;
                const isSellBlocked = !nweObj.isUp || winPrice < nweObj.nweProxUpper;

                if (isBuyBlocked) {
                    if (rW < 0) { sW = 0; rW = 0; }
                    if (rD < 0) { sD = 0; rD = 0; }
                }
                if (isSellBlocked) {
                    if (rW > 0) { sW = 0; rW = 0; }
                    if (rD > 0) { sD = 0; rD = 0; }
                }
            }

            return {
                ...h,
                ...nweObj,
                z_di: zDi,
                z_raw_wdo: rW,
                z_raw_di: rD,
                z_unfiltered_wdo: h.z,
                z_unfiltered_di: zDi ?? 0,
                sig_wdo: sW,
                sig_di: sD,
                cons_wdo_sig: consWdoSig,
                cons_di_sig: consDiSig,
            };
        });
    }, [history, histDayData, isViewingHistory, diData, fullHistory]);

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

    // Alerta Sonoro â€” reutiliza um Ãºnico AudioContext para evitar memory leak
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

    // â”€â”€ Count active signals for consensus badge (WDO + DI) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    const lastBar = mergedSignals.length > 0 ? mergedSignals[mergedSignals.length - 1] : {};
    const buyCount = [lastBar.cons_wdo_sig, lastBar.cons_di_sig].filter(v => v < 0).length;
    const sellCount = [lastBar.cons_wdo_sig, lastBar.cons_di_sig].filter(v => v > 0).length;
    const consensusCount = Math.max(buyCount, sellCount);
    const consensusDir = buyCount > sellCount ? "COMPRA" : sellCount > buyCount ? "VENDA" : null;
    const consensusColor = consensusDir === "COMPRA" ? "#00e87a" : consensusDir === "VENDA" ? "#ff3860" : "#3a5060";

    // â”€â”€ Johansen gate data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

            {/* â”€â”€ Topbar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
            <div className="topbar">
                <div className="topbar-left">
                    <span className="text-sm text-highlight font-bold" style={{ letterSpacing: 4 }}>PAIR TRADING</span>
                    <span style={{ display: "inline-block", width: 1, height: 14, background: "#1c2e3a" }} />
                    <span className="text-xs text-muted" style={{ letterSpacing: 2 }}>
                        {meta.symbol_a} x {meta.symbol_b}  Â·  STAT ARB  Â·  {meta.timeframe}
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
                                NWE {data.nwe.is_up ? "â–²" : "â–¼"}
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
                                            {isHolding ? (val.open_trade?.direction === "BUY" ? "C" : "V") : isEntry ? (isBuy ? "C!" : "V!") : "â€”"}
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
                            {isViewingHistory ? "HISTÃ“RICO" : status === "live" ? "MT5 LIVE" : status === "fallback" ? "SIMULADO" : "CONECTANDO"}
                        </span>
                    </div>
                    <span style={{ fontSize: 13, color: "#c8a444", minWidth: 70, textAlign: "right" }}>{clock}</span>
                </div>
            </div>

            {/* â”€â”€ Banners â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
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
                        sigColor={isViewingHistory ? "#00e87a" : sig.color}
                        currentZ={isViewingHistory ? 0 : currentZ}
                        useV2={true}
                        hideXAxis={true}
                    />
                    <SignalHistogram data={paddedSignals} />
                    <IndexChart
                        history={paddedSignals}
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
                        <span style={{ fontSize: 18 }}>ðŸš¨</span>
                        <div style={{ fontSize: 11, color: "#ff3860", lineHeight: 1.5 }}>
                            <strong>Z-SCORE ALTO COM RELAÃ‡ÃƒO INSTÃVEL</strong> â€” Parece oportunidade mas Ã© ruÃ­do.
                            Ï ou Î”Î² fora da zona verde invalida o sinal de z={currentZ > 0 ? `+${currentZ.toFixed(2)}` : currentZ.toFixed(2)}.
                        </div>
                    </div>
                )}

                {/* Trading Guide */}
                <TradingGuide />
            </div>

            {/* â”€â”€ Footer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
            <div style={{ borderTop: "1px solid #21262d", padding: "7px 20px", display: "flex", justifyContent: "space-between", fontSize: 8, color: "#3d444d", background: "#161b22" }}>
                <span>{status === "live" ? "DADOS REAIS MT5" : "DADOS SIMULADOS"} â€” NAO CONSTITUI RECOMENDACAO DE INVESTIMENTO Â· PAIR TRADING 2025</span>
                <span>beta = {meta.beta}  Â·  janela {meta.window} barras  Â·  {meta.symbol_a} x {meta.symbol_b}  Â·  B3</span>
            </div>
        </div>
        </>
    );
}
