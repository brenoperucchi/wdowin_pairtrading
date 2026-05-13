import { useEffect, useState, useCallback, useMemo } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL
    || (typeof window !== "undefined" ? `${window.location.protocol}//${window.location.hostname}:8080` : "http://localhost:8080");
const CONFIG_URL = `${API_BASE}/api/runtime-config`;
const REPLAY_URL = `${API_BASE}/api/execution-timeline/generate`;

const STRATEGY_KEYS = ["CONS_BASE", "WDO_NWE", "DI_NWE"];
const RECALC_OPTIONS = ["bar", "daily"];

const FIELD_META = {
    eg_threshold: { label: "EG threshold", hint: "Block when pvalue ≥ this (0–1].", kind: "float", min: 0, max: 1, step: "0.01", exclusiveMin: true },
    eg_bars: { label: "EG bars", hint: "Cointegration window in bars (60–100000).", kind: "int", min: 60, max: 100000, step: "1" },
    eg_recalc: { label: "EG recalc", hint: "'bar' = per bar · 'daily' = first bar of date_str.", kind: "select", options: RECALC_OPTIONS },
    rho_breakdown_level: { label: "Rho level", hint: "Block when rho_status.level ≥ this (1–3).", kind: "int", min: 1, max: 3, step: "1" },
    beta_delta_max: { label: "Beta Δ max (%)", hint: "Block when |beta_delta_pct| ≥ this (0–100].", kind: "float", min: 0, max: 100, step: "0.01", exclusiveMin: true },
    eg_strategies: { label: "EG strategies", hint: "Strategies that gate on EG — others bypass it.", kind: "strategies" },
    z_anomaly: { label: "Z anomaly", hint: "Block when max(|z_wdo|, |z_di|) ≥ this (0–10].", kind: "float", min: 0, max: 10, step: "0.01", exclusiveMin: true },
    window: { label: "Window", hint: "Rolling signal/regime window in bars (30–1000).", kind: "int", min: 30, max: 1000, step: "1" },
    z_entry: { label: "Z entry", hint: "Entry threshold. Must be above Z attention.", kind: "float", min: 0.1, max: 5, step: "0.01", exclusiveMin: true },
    z_attention: { label: "Z attention", hint: "Attention threshold. Must be below Z entry.", kind: "float", min: 0.1, max: 5, step: "0.01", exclusiveMin: true },
    entry_start_h: { label: "Start H", hint: "Entry window start hour (0–23).", kind: "int", min: 0, max: 23, step: "1" },
    entry_start_m: { label: "Start M", hint: "Entry window start minute (0–59).", kind: "int", min: 0, max: 59, step: "1" },
    entry_end_h: { label: "End H", hint: "Entry window end hour (0–23).", kind: "int", min: 0, max: 23, step: "1" },
    entry_end_m: { label: "End M", hint: "Entry window end minute (0–59).", kind: "int", min: 0, max: 59, step: "1" },
    force_close_h: { label: "Close H", hint: "Force-close hour (0–23).", kind: "int", min: 0, max: 23, step: "1" },
    force_close_m: { label: "Close M", hint: "Force-close minute (0–59).", kind: "int", min: 0, max: 59, step: "1" },
    buy_sl: { label: "BUY SL", hint: "BUY stop-loss in WIN points (10–5000).", kind: "int", min: 10, max: 5000, step: "1" },
    buy_tp: { label: "BUY TP", hint: "BUY target in WIN points (10–5000).", kind: "int", min: 10, max: 5000, step: "1" },
    buy_be_act: { label: "BUY BE act", hint: "BUY breakeven activation in WIN points (0–5000).", kind: "int", min: 0, max: 5000, step: "1" },
    buy_be_lock: { label: "BUY BE lock", hint: "BUY breakeven lock in WIN points (0–5000).", kind: "int", min: 0, max: 5000, step: "1" },
    sell_sl: { label: "SELL SL", hint: "SELL stop-loss in WIN points (10–5000).", kind: "int", min: 10, max: 5000, step: "1" },
    sell_tp: { label: "SELL TP", hint: "SELL target in WIN points (10–5000).", kind: "int", min: 10, max: 5000, step: "1" },
    sell_be_act: { label: "SELL BE act", hint: "SELL breakeven activation in WIN points (0–5000).", kind: "int", min: 0, max: 5000, step: "1" },
    sell_be_lock: { label: "SELL BE lock", hint: "SELL breakeven lock in WIN points (0–5000).", kind: "int", min: 0, max: 5000, step: "1" },
};

const FIELD_GROUPS = [
    { title: "COINTEGRAÇÃO", fields: ["eg_threshold", "eg_bars", "eg_recalc", "rho_breakdown_level", "beta_delta_max", "eg_strategies", "z_anomaly"] },
    { title: "JANELA & THRESHOLDS", fields: ["window", "z_entry", "z_attention"] },
    { title: "JANELA DE SESSÃO", fields: ["entry_start_h", "entry_start_m", "entry_end_h", "entry_end_m", "force_close_h", "force_close_m"] },
    { title: "RISK BUY", fields: ["buy_sl", "buy_tp", "buy_be_act", "buy_be_lock"] },
    { title: "RISK SELL", fields: ["sell_sl", "sell_tp", "sell_be_act", "sell_be_lock"] },
];

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


function isNumeric(value) {
    return typeof value === "number" && Number.isFinite(value);
}


function formatClock(profile, hField, mField) {
    const h = Number.isInteger(profile[hField]) ? String(profile[hField]).padStart(2, "0") : "??";
    const m = Number.isInteger(profile[mField]) ? String(profile[mField]).padStart(2, "0") : "??";
    return `${h}:${m}`;
}


function validateField(profile, field) {
    const meta = FIELD_META[field];
    if (!meta) return null;
    const value = profile[field];

    if (meta.kind === "select") {
        return meta.options.includes(value) ? null : `${meta.label} deve ser um de: ${meta.options.join(", ")}.`;
    }
    if (meta.kind === "strategies") {
        if (!Array.isArray(value)) return `${meta.label} deve ser uma lista.`;
        const seen = new Set();
        for (const item of value) {
            if (!STRATEGY_KEYS.includes(item)) return `${meta.label} tem estratégia inválida: ${item}.`;
            if (seen.has(item)) return `${meta.label} tem estratégia duplicada: ${item}.`;
            seen.add(item);
        }
        return null;
    }
    if (!isNumeric(value)) return `${meta.label} deve ser numérico.`;
    if (meta.kind === "int" && !Number.isInteger(value)) return `${meta.label} deve ser inteiro.`;
    if (meta.exclusiveMin ? value <= meta.min : value < meta.min) {
        return `${meta.label} deve ser ${meta.exclusiveMin ? ">" : ">="} ${meta.min}.`;
    }
    if (value > meta.max) return `${meta.label} deve ser <= ${meta.max}.`;
    return null;
}


function validateProfile(profile) {
    if (!profile) return [];
    const errors = [];
    for (const group of FIELD_GROUPS) {
        for (const field of group.fields) {
            const error = validateField(profile, field);
            if (error) errors.push(error);
        }
    }

    if (isNumeric(profile.z_attention) && isNumeric(profile.z_entry) && profile.z_attention >= profile.z_entry) {
        errors.push("Z attention deve ser menor que Z entry.");
    }

    const startMin = isNumeric(profile.entry_start_h) && isNumeric(profile.entry_start_m)
        ? profile.entry_start_h * 60 + profile.entry_start_m : null;
    const endMin = isNumeric(profile.entry_end_h) && isNumeric(profile.entry_end_m)
        ? profile.entry_end_h * 60 + profile.entry_end_m : null;
    const closeMin = isNumeric(profile.force_close_h) && isNumeric(profile.force_close_m)
        ? profile.force_close_h * 60 + profile.force_close_m : null;
    if (startMin !== null && endMin !== null && startMin >= endMin) {
        errors.push(`Entrada ${formatClock(profile, "entry_start_h", "entry_start_m")} deve ser antes de ${formatClock(profile, "entry_end_h", "entry_end_m")}.`);
    }
    if (endMin !== null && closeMin !== null && endMin > closeMin) {
        errors.push(`Fim de entrada ${formatClock(profile, "entry_end_h", "entry_end_m")} deve ser até o force-close ${formatClock(profile, "force_close_h", "force_close_m")}.`);
    }

    for (const side of ["buy", "sell"]) {
        const label = side.toUpperCase();
        const tp = profile[`${side}_tp`];
        const beAct = profile[`${side}_be_act`];
        const beLock = profile[`${side}_be_lock`];
        if (isNumeric(tp) && isNumeric(beAct) && isNumeric(beLock)) {
            if (beLock > beAct) errors.push(`${label} BE lock deve ser <= ${label} BE act.`);
            if (beLock >= tp) errors.push(`${label} BE lock deve ser < ${label} TP.`);
            if (beAct > tp) errors.push(`${label} BE act deve ser <= ${label} TP.`);
        }
    }
    return errors;
}


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
    const renderField = (field) => {
        const meta = FIELD_META[field];
        if (!meta) return null;
        return (
            <div key={field} style={{ gridColumn: meta.kind === "strategies" ? "1 / -1" : "auto" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
                    <label style={{ fontSize: 10, letterSpacing: 0.8, color: COLOR.text, fontWeight: "bold" }}>
                        {meta.label}
                    </label>
                    <span style={{ fontSize: 8, color: COLOR.muted, whiteSpace: "nowrap" }}>{field}</span>
                </div>
                {meta.kind === "select" && (
                    <SelectInput value={profile[field]} onChange={(v) => set(field, v)} options={meta.options} disabled={disabled} />
                )}
                {meta.kind === "strategies" && (
                    <StrategiesInput value={profile[field]} onChange={(v) => set(field, v)} disabled={disabled} />
                )}
                {(meta.kind === "float" || meta.kind === "int") && (
                    <NumberInput
                        value={profile[field]}
                        onChange={(v) => set(field, v)}
                        step={meta.step}
                        min={meta.min}
                        max={meta.max}
                        disabled={disabled}
                    />
                )}
                <div style={{ fontSize: 8, color: COLOR.muted, marginTop: 3, lineHeight: 1.35 }}>{meta.hint}</div>
            </div>
        );
    };

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {FIELD_GROUPS.map((group) => (
                <section key={group.title} style={{
                    paddingTop: 10,
                    borderTop: `1px dashed ${COLOR.borderStrong}`,
                }}>
                    <div style={{
                        fontSize: 9, letterSpacing: 1.5, color: COLOR.accent,
                        fontWeight: "bold", marginBottom: 9,
                    }}>
                        {group.title}
                    </div>
                    <div style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                        gap: "10px 9px",
                    }}>
                        {group.fields.map(renderField)}
                    </div>
                </section>
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
    const validationByProfile = useMemo(() => ({
        live: validateProfile(config?.live),
        replay: validateProfile(config?.replay),
    }), [config]);
    const activeProfile = config?.[activeTab];
    const activeValidationErrors = validationByProfile[activeTab] || [];

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
        setError(null); setStatus(null);
        const validationErrors = validateProfile(config[profileKey]);
        if (validationErrors.length) {
            setError(`Corrija ${profileKey.toUpperCase()}: ${validationErrors[0]}`);
            return;
        }
        setSaving(true);
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
                    {!loading && activeValidationErrors.length > 0 && (
                        <div style={{
                            marginTop: 14, padding: "9px 10px",
                            border: `1px solid ${COLOR.err}55`,
                            background: "rgba(255,56,96,0.08)",
                            borderRadius: 4,
                        }}>
                            <div style={{ fontSize: 10, color: COLOR.err, fontWeight: "bold", letterSpacing: 1, marginBottom: 5 }}>
                                VALIDATION
                            </div>
                            {activeValidationErrors.slice(0, 4).map((msg) => (
                                <div key={msg} style={{ fontSize: 9, color: COLOR.err, lineHeight: 1.4 }}>
                                    • {msg}
                                </div>
                            ))}
                            {activeValidationErrors.length > 4 && (
                                <div style={{ fontSize: 9, color: COLOR.err, marginTop: 3 }}>
                                    +{activeValidationErrors.length - 4} outros erros
                                </div>
                            )}
                        </div>
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
                            type="button" disabled={saving || loading || validationByProfile.live.length > 0}
                            onClick={() => handleSave("live")}
                            title={validationByProfile.live[0] || ""}
                            style={{
                                flex: 1, padding: "7px 0", fontSize: 10, fontFamily: "monospace",
                                fontWeight: "bold", letterSpacing: 1, cursor: (saving || validationByProfile.live.length > 0) ? "default" : "pointer",
                                background: "rgba(0,212,255,0.12)", border: `1px solid ${COLOR.blue}55`,
                                borderRadius: 4, color: COLOR.blue,
                                opacity: (saving || validationByProfile.live.length > 0) ? 0.5 : 1,
                            }}
                        >
                            SALVAR LIVE
                        </button>
                        <button
                            type="button" disabled={saving || loading || validationByProfile.replay.length > 0}
                            onClick={() => handleSave("replay")}
                            title={validationByProfile.replay[0] || ""}
                            style={{
                                flex: 1, padding: "7px 0", fontSize: 10, fontFamily: "monospace",
                                fontWeight: "bold", letterSpacing: 1, cursor: (saving || validationByProfile.replay.length > 0) ? "default" : "pointer",
                                background: COLOR.accentSoft, border: `1px solid ${COLOR.accent}55`,
                                borderRadius: 4, color: COLOR.accent,
                                opacity: (saving || validationByProfile.replay.length > 0) ? 0.5 : 1,
                            }}
                        >
                            SALVAR REPLAY
                        </button>
                    </div>
                    {activeTab === "replay" && (
                        <button
                            type="button" disabled={saving || loading || !replayDate || validationByProfile.replay.length > 0}
                            onClick={() => handleSave("replay", true)}
                            title={!replayDate ? "Defina uma data primeiro" : (validationByProfile.replay[0] || "")}
                            style={{
                                width: "100%", padding: "8px 0", fontSize: 10, fontFamily: "monospace",
                                fontWeight: "bold", letterSpacing: 2, cursor: (saving || !replayDate || validationByProfile.replay.length > 0) ? "default" : "pointer",
                                background: "rgba(0,232,122,0.12)", border: `1px solid ${COLOR.ok}55`,
                                borderRadius: 4, color: COLOR.ok,
                                opacity: (saving || !replayDate || validationByProfile.replay.length > 0) ? 0.4 : 1,
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
