import { useEffect, useState, useCallback, useMemo } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL
    || (typeof window !== "undefined" ? `${window.location.protocol}//${window.location.hostname}:8080` : "http://localhost:8080");
const CONFIG_URL = `${API_BASE}/api/runtime-config`;
const REPLAY_URL = `${API_BASE}/api/execution-timeline/generate`;

const STRATEGY_KEYS = ["CONS_BASE", "WDO_NWE", "DI_NWE"];
const RECALC_OPTIONS = ["bar", "daily"];

const FIELD_LABELS = {
    eg_threshold: "EG threshold",
    eg_bars: "EG bars",
    eg_recalc: "EG recalc",
    rho_breakdown_level: "Rho level",
    beta_delta_max: "Beta Δ max (%)",
    eg_strategies: "EG strategies",
    z_anomaly: "Z anomaly",
};

const FIELD_HINTS = {
    eg_threshold: "Block when pvalue ≥ this (0–1].",
    eg_bars: "Cointegration window in bars (≥ 60).",
    eg_recalc: "'bar' = per bar · 'daily' = first bar of date_str.",
    rho_breakdown_level: "Block when rho_status.level ≥ this (1–3).",
    beta_delta_max: "Block when |beta_delta_pct| ≥ this (0–100].",
    eg_strategies: "Strategies that gate on EG — others bypass it.",
    z_anomaly: "Block when max(|z_wdo|, |z_di|) ≥ this (0–10].",
};

const COLOR = {
    bg: "#0d1117",
    card: "#161b22",
    border: "#21262d",
    borderStrong: "#2f3b48",
    text: "#c9d1d9",
    muted: "#6f8a9c",
    accent: "#c8a444",
    accentSoft: "rgba(200,164,68,0.18)",
    ok: "#00e87a",
    warn: "#f5a623",
    err: "#ff3860",
    blue: "#00d4ff",
};


function NumberInput({ value, onChange, step = "any", min, max, disabled }) {
    return (
        <input
            type="number"
            value={value === null || value === undefined ? "" : value}
            step={step}
            min={min}
            max={max}
            disabled={disabled}
            onChange={(e) => {
                const raw = e.target.value;
                if (raw === "") { onChange(""); return; }
                const num = Number(raw);
                onChange(Number.isFinite(num) ? num : raw);
            }}
            style={{
                width: "100%", padding: "5px 8px", fontSize: 12, fontFamily: "monospace",
                background: "#0d1820", border: `1px solid ${COLOR.borderStrong}`,
                borderRadius: 4, color: COLOR.text, outline: "none",
            }}
        />
    );
}


function SelectInput({ value, onChange, options, disabled }) {
    return (
        <select
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
            style={{
                width: "100%", padding: "5px 8px", fontSize: 12, fontFamily: "monospace",
                background: "#0d1820", border: `1px solid ${COLOR.borderStrong}`,
                borderRadius: 4, color: COLOR.text, outline: "none",
            }}
        >
            {options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
        </select>
    );
}


function StrategiesInput({ value, onChange, disabled }) {
    const current = Array.isArray(value) ? value : [];
    const toggle = (key) => {
        if (current.includes(key)) onChange(current.filter((k) => k !== key));
        else onChange([...current, key]);
    };
    return (
        <div style={{ display: "flex", gap: 6 }}>
            {STRATEGY_KEYS.map((key) => {
                const on = current.includes(key);
                return (
                    <button
                        key={key} type="button" disabled={disabled}
                        onClick={() => toggle(key)}
                        style={{
                            flex: 1, padding: "5px 6px", fontSize: 10, fontFamily: "monospace",
                            cursor: disabled ? "default" : "pointer",
                            background: on ? COLOR.accentSoft : "#0d1820",
                            border: `1px solid ${on ? COLOR.accent : COLOR.borderStrong}`,
                            borderRadius: 4, color: on ? COLOR.accent : COLOR.muted,
                            letterSpacing: 1, fontWeight: "bold",
                        }}
                    >
                        {key}
                    </button>
                );
            })}
        </div>
    );
}


function ProfileForm({ profile, onChange, disabled }) {
    if (!profile) return null;
    const set = (field, val) => onChange({ ...profile, [field]: val });

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {Object.keys(FIELD_LABELS).map((field) => (
                <div key={field}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                        <label style={{ fontSize: 11, letterSpacing: 1, color: COLOR.text, fontWeight: "bold" }}>
                            {FIELD_LABELS[field]}
                        </label>
                        <span style={{ fontSize: 9, color: COLOR.muted }}>{field}</span>
                    </div>
                    {field === "eg_recalc" && (
                        <SelectInput value={profile[field]} onChange={(v) => set(field, v)} options={RECALC_OPTIONS} disabled={disabled} />
                    )}
                    {field === "eg_strategies" && (
                        <StrategiesInput value={profile[field]} onChange={(v) => set(field, v)} disabled={disabled} />
                    )}
                    {(field === "eg_threshold" || field === "beta_delta_max" || field === "z_anomaly") && (
                        <NumberInput value={profile[field]} onChange={(v) => set(field, v)} step="0.01" disabled={disabled} />
                    )}
                    {(field === "eg_bars" || field === "rho_breakdown_level") && (
                        <NumberInput value={profile[field]} onChange={(v) => set(field, v)} step="1" disabled={disabled} />
                    )}
                    <div style={{ fontSize: 9, color: COLOR.muted, marginTop: 3 }}>{FIELD_HINTS[field]}</div>
                </div>
            ))}
        </div>
    );
}


export default function RuntimeConfigSlideover({ isOpen, onClose, defaultReplayDate = "" }) {
    const [activeTab, setActiveTab] = useState("live");
    const [config, setConfig] = useState(null);
    const [original, setOriginal] = useState(null);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const [status, setStatus] = useState(null);
    const [replayDate, setReplayDate] = useState(defaultReplayDate);
    // Track whether the operator has explicitly edited the replay date in the
    // slideover. Until that happens we mirror the topbar's selected date so
    // changing the date picker and reopening CONFIG shows the fresh value.
    const [replayDateTouched, setReplayDateTouched] = useState(false);

    const dirtyByProfile = useMemo(() => {
        if (!config || !original) return { live: false, replay: false };
        return {
            live: JSON.stringify(config.live) !== JSON.stringify(original.live),
            replay: JSON.stringify(config.replay) !== JSON.stringify(original.replay),
        };
    }, [config, original]);
    const otherTab = activeTab === "live" ? "replay" : "live";
    const otherDirty = dirtyByProfile[otherTab];

    const loadConfig = useCallback(async () => {
        setLoading(true); setError(null); setStatus(null);
        try {
            const resp = await fetch(CONFIG_URL);
            const body = await resp.json();
            if (!resp.ok) throw new Error(body?.detail || body?.error || `HTTP ${resp.status}`);
            setConfig(body);
            setOriginal(JSON.parse(JSON.stringify(body)));
        } catch (exc) {
            setError(`Falha ao carregar: ${exc.message}`);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (isOpen && !config) loadConfig();
    }, [isOpen, config, loadConfig]);

    // Reset the touched flag each time the slideover reopens so a stale local
    // edit doesn't override the topbar's freshly-picked date on the next view.
    useEffect(() => {
        if (isOpen) setReplayDateTouched(false);
    }, [isOpen]);

    // Mirror the topbar's date into the slideover whenever it changes, as long
    // as the operator hasn't manually edited the field in this session.
    useEffect(() => {
        if (replayDateTouched) return;
        if (defaultReplayDate !== undefined) setReplayDate(defaultReplayDate);
    }, [defaultReplayDate, replayDateTouched]);

    useEffect(() => {
        if (!isOpen) return;
        const onKey = (e) => { if (e.key === "Escape") onClose(); };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [isOpen, onClose]);

    const postConfig = useCallback(async (next) => {
        const resp = await fetch(CONFIG_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(next),
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body?.detail || body?.error || `HTTP ${resp.status}`);
        return body;
    }, []);

    const handleSave = useCallback(async (profileKey, runReplay = false) => {
        if (!config) return;
        setSaving(true); setError(null); setStatus(null);
        // Whole-document replace: keep the other profile as-is from the on-disk
        // original so an unrelated edit can't bleed across tabs.
        const payload = {
            live: profileKey === "live" ? config.live : original.live,
            replay: profileKey === "replay" ? config.replay : original.replay,
        };
        try {
            const saved = await postConfig(payload);
            setConfig(saved);
            setOriginal(JSON.parse(JSON.stringify(saved)));
            setStatus(`✓ Perfil ${profileKey} salvo.`);

            if (runReplay) {
                if (!replayDate) {
                    setError("Defina a data do replay antes de rodar.");
                    return;
                }
                setStatus(`✓ Perfil replay salvo. Rodando replay ${replayDate}…`);
                const resp = await fetch(`${REPLAY_URL}?date=${encodeURIComponent(replayDate)}`, { method: "POST" });
                const body = await resp.json();
                if (!resp.ok) throw new Error(body?.message || body?.error || `HTTP ${resp.status}`);
                const opened = body?.summary?.trades_opened ?? "?";
                const pnl = body?.summary?.pnl_paper_brl ?? "?";
                setStatus(`✓ Replay ${replayDate} concluído — trades=${opened}, pnl=${pnl}`);
            }
        } catch (exc) {
            setError(exc.message);
        } finally {
            setSaving(false);
        }
    }, [config, original, postConfig, replayDate]);

    if (!isOpen) return null;

    const activeProfile = config?.[activeTab];

    return (
        <>
            <div onClick={onClose} style={{
                position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 998,
            }} />
            <aside style={{
                position: "fixed", top: 0, right: 0, bottom: 0, width: 420, zIndex: 999,
                background: COLOR.bg, borderLeft: `1px solid ${COLOR.border}`,
                color: COLOR.text, fontFamily: "monospace",
                display: "flex", flexDirection: "column",
                boxShadow: "-8px 0 24px rgba(0,0,0,0.4)",
            }}>
                <header style={{
                    padding: "12px 18px", borderBottom: `1px solid ${COLOR.border}`,
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    background: COLOR.card,
                }}>
                    <div>
                        <div style={{ fontSize: 12, letterSpacing: 3, color: COLOR.accent, fontWeight: "bold" }}>
                            RUNTIME CONFIG
                        </div>
                        <div style={{ fontSize: 9, color: COLOR.muted, marginTop: 2 }}>
                            Hot-reload aplicado no próximo poll · ESC para fechar
                        </div>
                    </div>
                    <button onClick={onClose} style={{
                        background: "transparent", border: `1px solid ${COLOR.borderStrong}`,
                        color: COLOR.muted, fontSize: 14, fontFamily: "monospace",
                        cursor: "pointer", padding: "2px 9px", borderRadius: 4,
                    }}>×</button>
                </header>

                <nav style={{ display: "flex", borderBottom: `1px solid ${COLOR.border}` }}>
                    {["live", "replay"].map((tab) => {
                        const on = activeTab === tab;
                        return (
                            <button key={tab} type="button" onClick={() => setActiveTab(tab)} style={{
                                flex: 1, padding: "9px 0", fontSize: 11, letterSpacing: 2,
                                fontFamily: "monospace", fontWeight: "bold", cursor: "pointer",
                                background: on ? COLOR.bg : COLOR.card,
                                color: on ? COLOR.accent : COLOR.muted,
                                border: "none",
                                borderBottom: on ? `2px solid ${COLOR.accent}` : "2px solid transparent",
                            }}>
                                {tab.toUpperCase()}
                            </button>
                        );
                    })}
                </nav>

                <div style={{ flex: 1, overflowY: "auto", padding: 18 }}>
                    {loading && <div style={{ color: COLOR.muted, fontSize: 11 }}>Carregando…</div>}
                    {!loading && activeProfile && (
                        <ProfileForm
                            profile={activeProfile}
                            disabled={saving}
                            onChange={(next) => setConfig({ ...config, [activeTab]: next })}
                        />
                    )}
                    {activeTab === "replay" && (
                        <div style={{ marginTop: 18, paddingTop: 14, borderTop: `1px dashed ${COLOR.borderStrong}` }}>
                            <label style={{ fontSize: 11, letterSpacing: 1, color: COLOR.text, fontWeight: "bold" }}>
                                Replay date
                            </label>
                            <div style={{ fontSize: 9, color: COLOR.muted, margin: "3px 0 6px" }}>
                                Usado por "Salvar e Rodar Replay". Formato YYYY-MM-DD.
                            </div>
                            <input
                                type="date"
                                value={replayDate}
                                disabled={saving}
                                onChange={(e) => { setReplayDate(e.target.value); setReplayDateTouched(true); }}
                                style={{
                                    width: "100%", padding: "5px 8px", fontSize: 12, fontFamily: "monospace",
                                    background: "#0d1820", border: `1px solid ${COLOR.borderStrong}`,
                                    borderRadius: 4, color: COLOR.text, outline: "none",
                                }}
                            />
                        </div>
                    )}
                </div>

                {(error || status) && (
                    <div style={{
                        padding: "8px 18px", fontSize: 10,
                        borderTop: `1px solid ${COLOR.border}`,
                        background: error ? "rgba(255,56,96,0.08)" : "rgba(0,232,122,0.06)",
                        color: error ? COLOR.err : COLOR.ok,
                    }}>
                        {error || status}
                    </div>
                )}

                <footer style={{
                    padding: "12px 18px", borderTop: `1px solid ${COLOR.border}`,
                    background: COLOR.card, display: "flex", flexDirection: "column", gap: 6,
                }}>
                    <div style={{ display: "flex", gap: 6 }}>
                        <button
                            type="button" disabled={saving || loading}
                            onClick={() => handleSave("live")}
                            style={{
                                flex: 1, padding: "7px 0", fontSize: 10, fontFamily: "monospace",
                                fontWeight: "bold", letterSpacing: 1, cursor: saving ? "default" : "pointer",
                                background: "rgba(0,212,255,0.12)", border: `1px solid ${COLOR.blue}55`,
                                borderRadius: 4, color: COLOR.blue,
                                opacity: saving ? 0.5 : 1,
                            }}
                        >
                            SALVAR LIVE
                        </button>
                        <button
                            type="button" disabled={saving || loading}
                            onClick={() => handleSave("replay")}
                            style={{
                                flex: 1, padding: "7px 0", fontSize: 10, fontFamily: "monospace",
                                fontWeight: "bold", letterSpacing: 1, cursor: saving ? "default" : "pointer",
                                background: COLOR.accentSoft, border: `1px solid ${COLOR.accent}55`,
                                borderRadius: 4, color: COLOR.accent,
                                opacity: saving ? 0.5 : 1,
                            }}
                        >
                            SALVAR REPLAY
                        </button>
                    </div>
                    {activeTab === "replay" && (
                        <button
                            type="button" disabled={saving || loading || !replayDate}
                            onClick={() => handleSave("replay", true)}
                            title={!replayDate ? "Defina uma data primeiro" : ""}
                            style={{
                                width: "100%", padding: "8px 0", fontSize: 10, fontFamily: "monospace",
                                fontWeight: "bold", letterSpacing: 2, cursor: (saving || !replayDate) ? "default" : "pointer",
                                background: "rgba(0,232,122,0.12)", border: `1px solid ${COLOR.ok}55`,
                                borderRadius: 4, color: COLOR.ok,
                                opacity: (saving || !replayDate) ? 0.4 : 1,
                            }}
                        >
                            SALVAR E RODAR REPLAY
                        </button>
                    )}
                    {otherDirty && (
                        <div style={{ fontSize: 9, color: COLOR.warn, textAlign: "center" }}>
                            • Mudanças não salvas em {otherTab.toUpperCase()} — serão descartadas se você salvar {activeTab.toUpperCase()}
                        </div>
                    )}
                    {dirtyByProfile[activeTab] && (
                        <div style={{ fontSize: 9, color: COLOR.warn, textAlign: "center" }}>
                            • Mudanças não salvas em {activeTab.toUpperCase()}
                        </div>
                    )}
                </footer>
            </aside>
        </>
    );
}
