import { useEffect, useMemo, useState } from "react";

const POLL_MS = 2500;
const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const TIMELINE_URL = `${API_BASE}/api/execution-timeline`;

const PHASES = ["DATA", "INDICATORS", "ELIGIBILITY", "RISK", "SIGNAL", "ORDER", "EXECUTION", "EXIT"];
const STATUSES = ["OK", "BLOCKED", "SKIPPED", "FAILED", "INFO"];
const STRATEGIES = ["CONS_BASE", "WDO_NWE", "DI_NWE"];

const STATUS_STYLE = {
    OK: { color: "#00e87a", bg: "rgba(0,232,122,0.08)", border: "rgba(0,232,122,0.28)" },
    BLOCKED: { color: "#ff3860", bg: "rgba(255,56,96,0.08)", border: "rgba(255,56,96,0.28)" },
    FAILED: { color: "#ff3860", bg: "rgba(255,56,96,0.12)", border: "rgba(255,56,96,0.38)" },
    SKIPPED: { color: "#6f8a9c", bg: "rgba(111,138,156,0.08)", border: "rgba(111,138,156,0.24)" },
    INFO: { color: "#00d4ff", bg: "rgba(0,212,255,0.08)", border: "rgba(0,212,255,0.24)" },
};

const PHASE_COLOR = {
    DATA: "#00d4ff",
    INDICATORS: "#8ca5b5",
    ELIGIBILITY: "#c8a444",
    RISK: "#f5a623",
    SIGNAL: "#8a6dff",
    ORDER: "#4fb4ff",
    EXECUTION: "#00e87a",
    EXIT: "#ff8b6b",
};

function fmtNumber(value, digits = 3) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toFixed(digits);
}

function fmtTimestamp(value) {
    if (!value) return "-";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return String(value).replace("T", " ");
    return dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function shortCorrelation(value) {
    if (!value) return "-";
    const text = String(value).replace(/^attempt:/, "");
    return text.length <= 8 ? text : text.slice(0, 8);
}

function eventLabel(event) {
    return String(event || "-").replaceAll("_", " ");
}

function statusStyle(status) {
    return STATUS_STYLE[status] || STATUS_STYLE.INFO;
}

function buildQuery(filters) {
    const params = new URLSearchParams({ limit: "180" });
    if (filters.phase) params.set("phase", filters.phase);
    if (filters.status) params.set("status", filters.status);
    if (filters.strategy) params.set("strategy", filters.strategy);
    if (filters.event.trim()) params.set("event", filters.event.trim());
    return `${TIMELINE_URL}?${params.toString()}`;
}

function MetricBox({ label, value, color = "#cdd8de" }) {
    return (
        <div style={{ background: "#111c24", border: "1px solid #1c2e3a", borderRadius: 4, padding: "8px 10px", minWidth: 110 }}>
            <div style={{ fontSize: 8, color: "#6f8a9c", letterSpacing: 1.5, marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 13, color, fontWeight: "bold", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {value}
            </div>
        </div>
    );
}

function Summary({ bottleneck, liveIssue, loading, error }) {
    const issue = liveIssue || bottleneck;
    const isLiveIssue = Boolean(liveIssue);
    const style = statusStyle(issue?.status);

    if (loading && !issue) {
        return (
            <div style={{ color: "#6f8a9c", fontSize: 11, padding: "8px 0" }}>
                Carregando timeline operacional...
            </div>
        );
    }

    if (error && !issue) {
        return (
            <div style={{
                background: "rgba(255,56,96,0.08)", border: "1px solid rgba(255,56,96,0.28)",
                borderRadius: 6, padding: "10px 12px", color: "#ff3860", fontSize: 11,
            }}>
                Falha ao carregar timeline: {error}
            </div>
        );
    }

    if (!issue) {
        return (
            <div style={{
                background: "rgba(0,232,122,0.06)", border: "1px solid rgba(0,232,122,0.22)",
                borderRadius: 6, padding: "10px 12px", display: "flex", justifyContent: "space-between", gap: 12,
                alignItems: "center", flexWrap: "wrap",
            }}>
                <div>
                    <div style={{ fontSize: 9, color: "#00e87a", letterSpacing: 2, fontWeight: "bold" }}>FUNIL OK</div>
                    <div style={{ fontSize: 11, color: "#8ca5b5", marginTop: 3 }}>Ultima barra fechada sem bloqueio atual.</div>
                </div>
                <div style={{ fontSize: 9, color: "#3a5060", letterSpacing: 1 }}>SEM GARGALO ATIVO</div>
            </div>
        );
    }

    return (
        <div style={{
            background: style.bg, border: `1px solid ${style.border}`, borderRadius: 6,
            padding: "10px 12px", display: "flex", flexDirection: "column", gap: 10,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <div>
                    <div style={{ fontSize: 9, color: style.color, letterSpacing: 2, fontWeight: "bold" }}>
                        {isLiveIssue ? "FALHA AO VIVO" : "GARGALO ATUAL"}
                    </div>
                    <div style={{ fontSize: 13, color: "#cdd8de", fontWeight: "bold", marginTop: 3 }}>
                        {issue.phase || "-"} / {eventLabel(issue.event)}
                    </div>
                    <div style={{ fontSize: 10, color: "#8ca5b5", marginTop: 3 }}>
                        {issue.message || issue.metric || "Sem detalhe adicional"}
                    </div>
                </div>
                <div style={{
                    border: `1px solid ${style.border}`, color: style.color, borderRadius: 4,
                    padding: "4px 8px", fontSize: 9, fontWeight: "bold", letterSpacing: 1,
                }}>
                    {issue.status || "-"}
                </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 8 }}>
                <MetricBox label="FASE" value={issue.phase || "-"} color={PHASE_COLOR[issue.phase] || "#cdd8de"} />
                <MetricBox label="SETUP" value={issue.strategy || "GLOBAL"} />
                <MetricBox label="VALOR" value={fmtNumber(issue.value)} />
                <MetricBox label="LIMIAR" value={`${issue.operator || ""} ${fmtNumber(issue.threshold)}`.trim() || "-"} />
                <MetricBox label="DIST" value={fmtNumber(issue.distance)} color={Number(issue.distance) > 0 ? "#ff3860" : "#00e87a"} />
                <MetricBox label="RATIO" value={fmtNumber(issue.ratio_to_threshold, 2)} />
            </div>
        </div>
    );
}

function FilterSelect({ value, onChange, children, label }) {
    return (
        <label style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 110 }}>
            <span style={{ fontSize: 8, color: "#3a5060", letterSpacing: 1.5 }}>{label}</span>
            <select
                value={value}
                onChange={event => onChange(event.target.value)}
                style={{
                    background: "#111c24", color: "#cdd8de", border: "1px solid #1c2e3a",
                    borderRadius: 4, padding: "5px 8px", fontSize: 10, outline: "none", fontFamily: "monospace",
                }}
            >
                {children}
            </select>
        </label>
    );
}

function TimelineRow({ event }) {
    const style = statusStyle(event.status);
    const isProblem = event.status === "BLOCKED" || event.status === "FAILED";
    const metricText = event.value !== null && event.value !== undefined
        ? `${fmtNumber(event.value)} ${event.operator || ""} ${fmtNumber(event.threshold)}`
        : event.message || "-";

    return (
        <tr style={{
            borderBottom: "1px solid #0d1a22",
            background: isProblem ? style.bg : "transparent",
            color: "#8ca5b5",
        }}>
            <td style={{ padding: "7px 8px", whiteSpace: "nowrap", color: "#cdd8de" }}>{fmtTimestamp(event.timestamp)}</td>
            <td style={{ padding: "7px 8px", color: PHASE_COLOR[event.phase] || "#8ca5b5", fontWeight: "bold" }}>{event.phase || "-"}</td>
            <td style={{ padding: "7px 8px", color: "#cdd8de", fontWeight: "bold" }}>{eventLabel(event.event)}</td>
            <td style={{ padding: "7px 8px" }}>
                <span style={{
                    display: "inline-block", minWidth: 58, textAlign: "center", padding: "2px 6px",
                    border: `1px solid ${style.border}`, borderRadius: 3, color: style.color, background: style.bg,
                    fontSize: 9, fontWeight: "bold",
                }}>
                    {event.status || "-"}
                </span>
            </td>
            <td style={{ padding: "7px 8px", color: "#c8a444" }}>{event.strategy || "GLOBAL"}</td>
            <td style={{ padding: "7px 8px" }}>{event.symbol || "-"}</td>
            <td style={{ padding: "7px 8px", maxWidth: 260, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {metricText}
            </td>
            <td style={{ padding: "7px 8px", color: "#6f8a9c" }}>{shortCorrelation(event.correlation_id)}</td>
        </tr>
    );
}

export default function ExecutionTimelinePanel() {
    const [filters, setFilters] = useState({ phase: "", status: "", strategy: "", event: "" });
    const [events, setEvents] = useState([]);
    const [summary, setSummary] = useState({ current_bottleneck: null, current_live_issue: null });
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastLoadedAt, setLastLoadedAt] = useState(null);

    const url = useMemo(() => buildQuery(filters), [filters]);

    useEffect(() => {
        let active = true;

        async function load() {
            try {
                const response = await fetch(url);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const payload = await response.json();
                if (!active) return;
                setEvents(Array.isArray(payload.events) ? payload.events : []);
                setSummary(payload.summary || { current_bottleneck: null, current_live_issue: null });
                setLastLoadedAt(new Date());
                setError(null);
            } catch (err) {
                if (active) setError(err?.message || "erro desconhecido");
            } finally {
                if (active) setLoading(false);
            }
        }

        load();
        const timer = setInterval(load, POLL_MS);
        return () => {
            active = false;
            clearInterval(timer);
        };
    }, [url]);

    const updateFilter = (key, value) => {
        setFilters(current => ({ ...current, [key]: value }));
    };

    return (
        <div style={{
            background: "#0a0e12", border: "1px solid #1c2e3a", borderRadius: 8,
            padding: "14px 18px", marginTop: 4, display: "flex", flexDirection: "column",
            gap: 12, minHeight: 260,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <div>
                    <div style={{ fontSize: 9, color: "#3a5060", letterSpacing: 3 }}>EXECUTION TIMELINE</div>
                </div>
                <div style={{ fontSize: 9, color: error ? "#ff3860" : "#6f8a9c", letterSpacing: 1 }}>
                    {error ? `ERRO: ${error}` : lastLoadedAt ? `ATUALIZADO ${fmtTimestamp(lastLoadedAt.toISOString())}` : "AGUARDANDO"}
                </div>
            </div>

            <Summary
                bottleneck={summary.current_bottleneck}
                liveIssue={summary.current_live_issue}
                loading={loading}
                error={error}
            />

            <div style={{ display: "flex", gap: 10, alignItems: "end", flexWrap: "wrap" }}>
                <FilterSelect label="FASE" value={filters.phase} onChange={value => updateFilter("phase", value)}>
                    <option value="">ALL</option>
                    {PHASES.map(phase => <option key={phase} value={phase}>{phase}</option>)}
                </FilterSelect>
                <FilterSelect label="STATUS" value={filters.status} onChange={value => updateFilter("status", value)}>
                    <option value="">ALL</option>
                    {STATUSES.map(status => <option key={status} value={status}>{status}</option>)}
                </FilterSelect>
                <FilterSelect label="SETUP" value={filters.strategy} onChange={value => updateFilter("strategy", value)}>
                    <option value="">ALL</option>
                    {STRATEGIES.map(strategy => <option key={strategy} value={strategy}>{strategy}</option>)}
                </FilterSelect>
                <label style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 180, flex: "1 1 180px" }}>
                    <span style={{ fontSize: 8, color: "#3a5060", letterSpacing: 1.5 }}>EVENTO</span>
                    <input
                        value={filters.event}
                        onChange={event => updateFilter("event", event.target.value)}
                        placeholder="EG_NOT_COINTEGRATED"
                        style={{
                            background: "#111c24", color: "#cdd8de", border: "1px solid #1c2e3a",
                            borderRadius: 4, padding: "5px 8px", fontSize: 10, outline: "none", fontFamily: "monospace",
                        }}
                    />
                </label>
            </div>

            <div className="table-container" style={{ borderTop: "1px solid #1c2e3a", paddingTop: 10, minHeight: 160 }}>
                <table style={{ width: "100%", minWidth: 980, borderCollapse: "collapse", fontSize: 10 }}>
                    <thead>
                        <tr style={{ color: "#6f8a9c", borderBottom: "1px solid #1c2e3a" }}>
                            <th style={{ textAlign: "left", padding: "0 8px 7px", fontWeight: "normal" }}>HORA</th>
                            <th style={{ textAlign: "left", padding: "0 8px 7px", fontWeight: "normal" }}>FASE</th>
                            <th style={{ textAlign: "left", padding: "0 8px 7px", fontWeight: "normal" }}>EVENTO</th>
                            <th style={{ textAlign: "left", padding: "0 8px 7px", fontWeight: "normal" }}>STATUS</th>
                            <th style={{ textAlign: "left", padding: "0 8px 7px", fontWeight: "normal" }}>SETUP</th>
                            <th style={{ textAlign: "left", padding: "0 8px 7px", fontWeight: "normal" }}>SYMBOL</th>
                            <th style={{ textAlign: "left", padding: "0 8px 7px", fontWeight: "normal" }}>VALOR / MSG</th>
                            <th style={{ textAlign: "left", padding: "0 8px 7px", fontWeight: "normal" }}>CORR</th>
                        </tr>
                    </thead>
                    <tbody>
                        {events.map(event => <TimelineRow key={event.id || event.dedupe_key} event={event} />)}
                        {!loading && events.length === 0 && (
                            <tr>
                                <td colSpan={8} style={{ padding: "14px 8px", color: "#6f8a9c", textAlign: "center" }}>
                                    Nenhum evento encontrado para os filtros atuais.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
