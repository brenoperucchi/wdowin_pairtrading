import { useState } from "react";

const STRAT_LABELS = {
    CONS_BASE: { label: "Consenso", color: "#00e87a" },
    WDO_NWE: { label: "WDO + NWE", color: "#c8a444" },
    DI_NWE: { label: "DI + NWE", color: "#8a6dff" },
};

function StrategyCard({ label, color, stats, isSelected, onClick }) {
    if (!stats) return null;
    const pnl = stats.accumulated_pnl || 0;
    const isOpen = stats.open_trades > 0;
    return (
        <div
            onClick={onClick}
            style={{
                flex: 1, padding: "10px 14px", background: isSelected ? `${color}12` : "#111c24",
                border: `1px solid ${isSelected ? color : "#1c2e3a"}`,
                borderRadius: 6, cursor: "pointer", transition: "all 0.2s",
                minWidth: 130,
            }}
        >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 9, color, letterSpacing: 2, fontWeight: "bold" }}>{label}</span>
                {isOpen && (
                    <span style={{
                        fontSize: 8, padding: "2px 6px", borderRadius: 3,
                        background: "rgba(245,166,35,0.2)", color: "#f5a623",
                        fontWeight: "bold", letterSpacing: 1,
                    }}>POSICIONADO</span>
                )}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                <div>
                    <div style={{ fontSize: 8, color: "#3a5060", marginBottom: 2 }}>PnL</div>
                    <div style={{ fontSize: 16, fontWeight: "bold", color: pnl > 0 ? "#00e87a" : pnl < 0 ? "#ff3860" : "#5a7080" }}>
                        R${pnl.toFixed(0)}
                    </div>
                </div>
                <div>
                    <div style={{ fontSize: 8, color: "#3a5060", marginBottom: 2 }}>WR</div>
                    <div style={{ fontSize: 16, fontWeight: "bold", color: stats.win_rate_pct >= 50 ? "#00e87a" : "#ff3860" }}>
                        {stats.win_rate_pct}%
                    </div>
                </div>
                <div>
                    <div style={{ fontSize: 8, color: "#3a5060", marginBottom: 2 }}>TRADES</div>
                    <div style={{ fontSize: 16, fontWeight: "bold", color: "#cdd8de" }}>
                        {stats.total_closed}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default function PerformancePanel({ perf }) {
    const [showTrades, setShowTrades] = useState(false);
    const [selectedStrat, setSelectedStrat] = useState(null); // null = portfolio view
    const [globalDateFilter, setGlobalDateFilter] = useState("");
    const [colFilters, setColFilters] = useState({
        direction: "",
        strategy: "",
        exit_reason: ""
    });

    if (!perf) return null;

    const strategies = perf.strategies || {};

    const allTrades = perf.trades || [];
    const uniqueDates = Array.from(new Set(allTrades.map(t => t.date_in).filter(Boolean)));

    // Filter trades by selected strategy and all other filters
    let filteredTrades = selectedStrat
        ? allTrades.filter(t => t.strategy === selectedStrat)
        : allTrades;

    if (globalDateFilter) {
        filteredTrades = filteredTrades.filter(t => t.date_in === globalDateFilter);
    }
    if (colFilters.direction) {
        filteredTrades = filteredTrades.filter(t => t.direction === colFilters.direction);
    }
    if (colFilters.strategy) {
        filteredTrades = filteredTrades.filter(t => t.strategy === colFilters.strategy);
    }
    if (colFilters.exit_reason) {
        filteredTrades = filteredTrades.filter(t => {
            if (colFilters.exit_reason === "ABERTO") return t.status === "OPEN";
            return t.exit_reason === colFilters.exit_reason;
        });
    }

    // Stats to display (selected strategy or portfolio total)
    const displayStats = selectedStrat && strategies[selectedStrat]
        ? strategies[selectedStrat]
        : {
            total_closed: perf.total_closed_trades,
            open_trades: perf.open_trades,
            wins: perf.wins,
            losses: perf.losses,
            win_rate_pct: perf.win_rate_pct,
            accumulated_pnl: perf.accumulated_pnl,
        };

    return (
        <div style={{
            background: "#0a0e12", border: "1px solid #1c2e3a", borderRadius: 8,
            padding: "14px 18px", marginTop: 4, display: "flex", flexDirection: "column",
            resize: "vertical", overflow: "hidden", minHeight: 180,
        }}>

            {/* ── Header ── */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, flexShrink: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ fontSize: 9, color: "#3a5060", letterSpacing: 3 }}>PORTFOLIO MATADOR</span>
                    {/* Portfolio / strategy selector */}
                    <button
                        onClick={() => setSelectedStrat(null)}
                        style={{
                            background: !selectedStrat ? "rgba(0,232,122,0.15)" : "transparent",
                            border: `1px solid ${!selectedStrat ? "#00e87a55" : "#1c2e3a"}`,
                            borderRadius: 4, color: !selectedStrat ? "#00e87a" : "#5a7080",
                            fontSize: 9, cursor: "pointer", padding: "3px 8px", fontFamily: "monospace",
                        }}
                    >PORTFOLIO</button>
                    {Object.entries(STRAT_LABELS).map(([key, { label, color }]) => (
                        <button
                            key={key}
                            onClick={() => setSelectedStrat(key)}
                            style={{
                                background: selectedStrat === key ? `${color}22` : "transparent",
                                border: `1px solid ${selectedStrat === key ? color + "55" : "#1c2e3a"}`,
                                borderRadius: 4, color: selectedStrat === key ? color : "#5a7080",
                                fontSize: 9, cursor: "pointer", padding: "3px 8px", fontFamily: "monospace",
                            }}
                        >{label}</button>
                    ))}
                </div>
                <button
                    onClick={() => setShowTrades(!showTrades)}
                    style={{
                        background: "transparent", border: "1px solid #1c2e3a", borderRadius: 4,
                        color: "#cdd8de", fontSize: 9, cursor: "pointer", padding: "3px 8px",
                        fontFamily: "monospace",
                    }}
                >{showTrades ? "OCULTAR TRADES" : "VER TRADES"}</button>
            </div>

            {/* ── Strategy cards row ── */}
            {!selectedStrat && (
                <div style={{ display: "flex", gap: 10, marginBottom: 12, flexShrink: 0, flexWrap: "wrap" }}>
                    {Object.entries(STRAT_LABELS).map(([key, { label, color }]) => (
                        <StrategyCard
                            key={key}
                            label={label}
                            color={color}
                            stats={strategies[key]}
                            isSelected={selectedStrat === key}
                            onClick={() => setSelectedStrat(key)}
                        />
                    ))}
                </div>
            )}

            {/* ── Main stats row ── */}
            <div className="perf-grid">
                <div style={{ padding: "8px", background: "#111c24", borderRadius: 4, textAlign: "center" }}>
                    <div className="text-xs text-muted" style={{ marginBottom: 4 }}>TAXA DE ACERTO</div>
                    <div className="text-xl font-bold" style={{ color: displayStats.win_rate_pct >= 50 ? "#00e87a" : "#ff3860" }}>
                        {displayStats.win_rate_pct}%
                    </div>
                </div>
                <div style={{ padding: "8px", background: "#111c24", borderRadius: 4, textAlign: "center" }}>
                    <div className="text-xs text-muted" style={{ marginBottom: 4 }}>
                        {selectedStrat ? STRAT_LABELS[selectedStrat]?.label.toUpperCase() : "PORTFOLIO"}
                    </div>
                    <div className="text-base font-bold" style={{ color: selectedStrat ? STRAT_LABELS[selectedStrat]?.color : "#00e87a", letterSpacing: 1 }}>
                        {selectedStrat ? "ISOLADO" : "AGREGADO"}
                    </div>
                </div>
                <div style={{ padding: "8px", background: "#111c24", borderRadius: 4, textAlign: "center" }}>
                    <div className="text-xs text-muted" style={{ marginBottom: 4 }}>OPERAÇÕES (W/L)</div>
                    <div className="text-xl font-bold" style={{ color: "#cdd8de" }}>
                        {displayStats.total_closed} <span className="text-sm text-secondary">({displayStats.wins}/{displayStats.losses})</span>
                    </div>
                </div>
                <div style={{ padding: "8px", background: "#111c24", borderRadius: 4, textAlign: "center" }}>
                    <div className="text-xs text-muted" style={{ marginBottom: 4 }}>STATUS OPERACIONAL</div>
                    <div className="text-lg font-bold" style={{ marginTop: 4, color: displayStats.open_trades > 0 ? "#f5a623" : "#6f8a9c" }}>
                        {displayStats.open_trades > 0 ? `${displayStats.open_trades} ABERTO` : "AGUARDANDO"}
                    </div>
                </div>
                <div style={{ padding: "8px", background: "#111c24", borderRadius: 4, textAlign: "center" }}>
                    <div className="text-xs text-muted" style={{ marginBottom: 4 }}>RESULTADO ACUM.</div>
                    <div className="text-xl font-bold" style={{ color: displayStats.accumulated_pnl > 0 ? "#00e87a" : (displayStats.accumulated_pnl < 0 ? "#ff3860" : "#cdd8de") }}>
                        R$ {(displayStats.accumulated_pnl || 0).toFixed(2)}
                    </div>
                </div>
            </div>

            {/* TABELA DE OPERAÇÕES */}
            {showTrades && filteredTrades.length > 0 && (
                <div style={{ marginTop: 14, borderTop: "1px solid #1c2e3a", paddingTop: 14, display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexShrink: 0 }}>
                        <div className="text-xs text-muted" style={{ letterSpacing: 2 }}>
                            {selectedStrat ? `SINAIS — ${STRAT_LABELS[selectedStrat]?.label}` : "TODOS OS SINAIS"}
                        </div>
                        <select
                            value={globalDateFilter}
                            onChange={e => setGlobalDateFilter(e.target.value)}
                            className="text-xs"
                            style={{ background: "#111c24", color: "#cdd8de", border: "1px solid #1c2e3a", borderRadius: 4, padding: "2px 6px", outline: "none", cursor: "pointer" }}
                        >
                            <option value="">TODOS OS DIAS</option>
                            {uniqueDates.map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                    </div>
                    <div className="table-container">
                        <table style={{ width: "100%", fontSize: 10, textAlign: "left", borderCollapse: "collapse" }}>
                            <thead>
                                <tr className="text-secondary" style={{ borderBottom: "1px solid #1c2e3a" }}>
                                    <th style={{ paddingBottom: 6, fontWeight: "normal" }}>DATA</th>
                                    <th style={{ paddingBottom: 6, fontWeight: "normal" }}>ABERTURA</th>
                                    <th style={{ paddingBottom: 6, fontWeight: "normal" }}>FECHAMENTO</th>
                                    <th style={{ paddingBottom: 6, fontWeight: "normal", textAlign: "center" }}>DIR</th>
                                    <th style={{ paddingBottom: 6, fontWeight: "normal", textAlign: "center" }}>SETUP</th>
                                    <th style={{ paddingBottom: 6, fontWeight: "normal", textAlign: "right" }}>QTY</th>
                                    <th style={{ paddingBottom: 6, fontWeight: "normal", textAlign: "center" }}>Zw / Zd</th>
                                    <th style={{ paddingBottom: 6, fontWeight: "normal", textAlign: "right" }}>RESULTADO / PnL (R$)</th>
                                </tr>
                                <tr style={{ background: "#0a0e12" }}>
                                    <th style={{ padding: "0 0 6px 0", fontWeight: "normal" }}></th>
                                    <th colSpan={2}></th>
                                    <th style={{ padding: "0 0 6px 0", fontWeight: "normal", textAlign: "center" }}>
                                        <select value={colFilters.direction} onChange={e => setColFilters({ ...colFilters, direction: e.target.value })} style={{ background: "#111c24", color: "#8ca5b5", border: "1px solid #1c2e3a", borderRadius: 3, fontSize: 9, outline: "none", cursor: "pointer" }}>
                                            <option value="">(Todos)</option>
                                            <option value="BUY">BUY</option>
                                            <option value="SELL">SELL</option>
                                        </select>
                                    </th>
                                    <th style={{ padding: "0 0 6px 0", fontWeight: "normal", textAlign: "center" }}>
                                        <select value={colFilters.strategy} onChange={e => setColFilters({ ...colFilters, strategy: e.target.value })} style={{ background: "#111c24", color: "#8ca5b5", border: "1px solid #1c2e3a", borderRadius: 3, fontSize: 9, outline: "none", cursor: "pointer" }}>
                                            <option value="">(Todos)</option>
                                            {Object.keys(STRAT_LABELS).map(k => <option key={k} value={k}>{STRAT_LABELS[k].label}</option>)}
                                        </select>
                                    </th>
                                    <th colSpan={2}></th>
                                    <th style={{ padding: "0 0 6px 0", fontWeight: "normal", textAlign: "right" }}>
                                        <select value={colFilters.exit_reason} onChange={e => setColFilters({ ...colFilters, exit_reason: e.target.value })} style={{ background: "#111c24", color: "#8ca5b5", border: "1px solid #1c2e3a", borderRadius: 3, fontSize: 9, outline: "none", cursor: "pointer" }}>
                                            <option value="">(Todos)</option>
                                            <option value="TARGET">ALVO</option>
                                            <option value="STOP_LOSS">STOP LOSS</option>
                                            <option value="BE_STOP">BREAKEVEN</option>
                                            <option value="FORCE_CLOSE">FORCE CLOSE</option>
                                            <option value="ABERTO">ABERTO</option>
                                        </select>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredTrades.map((t) => {
                                    const isWin = t.exit_reason === "TARGET";
                                    const rc = isWin ? "#00e87a" : (t.status === "OPEN" ? "#f5a623" : "#ff3860");
                                    const dirColor = t.direction === "BUY" ? "#00e87a" : t.direction === "SELL" ? "#ff3860" : "#5a7080";
                                    const stratInfo = STRAT_LABELS[t.strategy] || { label: t.strategy, color: "#5a7080" };
                                    return (
                                        <tr key={t.id} style={{ borderBottom: "1px solid #0d1a22", color: "#8a9aaa" }}>
                                            <td style={{ padding: "6px 0", color: "#00d4ff", fontWeight: "bold", fontSize: 9 }}>{t.date_in || "-"}</td>
                                            <td>{t.time_in || "-"}</td>
                                            <td>{t.time_out || "-"}</td>
                                            <td style={{ textAlign: "center", fontWeight: "bold", color: dirColor }}>{t.direction || "-"}</td>
                                            <td style={{ textAlign: "center", fontSize: 9, color: stratInfo.color, fontWeight: "bold" }}>{stratInfo.label}</td>
                                            <td style={{ textAlign: "right" }}>{t.qty_win || 0}x</td>
                                            <td style={{ textAlign: "center" }}>{t.z_in > 0 ? `+${t.z_in}` : t.z_in} / {t.rho_in}</td>
                                            <td style={{ textAlign: "right", fontWeight: "bold", color: rc }}>
                                                {t.status === "OPEN" ? "ABERTO" : `${(t.exit_reason || "").replace("_", " ")} (R$ ${(t.pnl_brl || 0).toFixed(2)})`}
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
    );
}
