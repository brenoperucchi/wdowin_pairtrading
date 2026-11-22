import React, { useMemo, useState } from "react";
import {
    STATARB_STRAT_META,
    simulateDayStatArbTradesJs,
    getAllAudited2026Trades,
    normalizeStatArbTrade,
} from "../utils/statArbDayTrades";

function fmtPts(v) {
    const n = Number(v || 0);
    const sign = n > 0 ? "+" : "";
    return `${sign}${Math.round(n).toLocaleString("pt-BR")} pts`;
}

function fmtBrl(v) {
    const n = Number(v || 0);
    const sign = n > 0 ? "+" : n < 0 ? "-" : "";
    return `${sign}R$ ${Math.abs(Math.round(n)).toLocaleString("pt-BR")}`;
}

function fmtPrice(v) {
    if (v == null || isNaN(v)) return "—";
    return Math.round(Number(v)).toLocaleString("pt-BR");
}

function outcomeBadgeStyle(reason, status) {
    if (status === "ABERTA") {
        return {
            bg: "rgba(212, 162, 89, 0.14)",
            border: "rgba(212, 162, 89, 0.42)",
            color: "#d4a259",
            label: "Em aberto (Live)",
        };
    }
    const r = String(reason || "").toUpperCase();
    if (r.includes("GAIN") || r.includes("ALVO")) {
        return {
            bg: "rgba(76, 195, 138, 0.12)",
            border: "rgba(76, 195, 138, 0.38)",
            color: "#4cc38a",
            label: reason || "Alvo Wall",
        };
    }
    if (r.includes("BE")) {
        return {
            bg: "rgba(212, 162, 89, 0.12)",
            border: "rgba(212, 162, 89, 0.38)",
            color: "#d4a259",
            label: reason || "Stop BE (+15p)",
        };
    }
    if (r.includes("STOP")) {
        return {
            bg: "rgba(229, 72, 77, 0.12)",
            border: "rgba(229, 72, 77, 0.38)",
            color: "#e5484d",
            label: reason || "Stop Wall",
        };
    }
    return {
        bg: "var(--mw-chrome)",
        border: "var(--mw-hairline)",
        color: "var(--mw-text-2)",
        label: reason || "Saída 16:50",
    };
}

export default function StatArbLiveTradePanel({
    history = [],
    walls = [],
    dayTrades = null,
    selectedDate = "",
    isViewingHistory = false,
    onSelectDate,
}) {
    const [activeView, setActiveView] = useState("DAY"); // "DAY" | "ALL"
    const [stratFilter, setStratFilter] = useState("ALL"); // "ALL" | "CONS" | "DI_NWE" | "WDO_NWE"
    const [outcomeFilter, setOutcomeFilter] = useState("ALL"); // "ALL" | "GAIN" | "BE" | "STOP"
    const [page, setPage] = useState(0);
    const PAGE_SIZE = 35;

    // 1. Trades da sessão atual ou histórica selecionada (normalizados com todos os aliases)
    const sessionTrades = useMemo(() => {
        if (!isViewingHistory && Array.isArray(dayTrades) && dayTrades.length > 0) {
            return dayTrades.map(normalizeStatArbTrade);
        }
        return simulateDayStatArbTradesJs(history, walls, !isViewingHistory, selectedDate).map(normalizeStatArbTrade);
    }, [dayTrades, history, walls, isViewingHistory, selectedDate]);

    // Última barra real da sessão para status de Z-Score, NWE e horário
    const latestBar = useMemo(() => {
        const real = (history || []).filter((d) => !d.isPadding && (d.win_price != null || d.win != null));
        return real.length > 0 ? real[real.length - 1] : null;
    }, [history]);

    // 2. Resumo por estratégia no pregão atual/selecionado
    const stratCards = useMemo(() => {
        const keys = ["CONS", "DI_NWE", "WDO_NWE"];
        const rawWdo = latestBar?.z_raw_wdo ?? latestBar?.z;
        const rawDi = latestBar?.z_raw_di ?? latestBar?.z_di;
        const zWdo = rawWdo != null ? Number(rawWdo) : null;
        const zDi = rawDi != null ? Number(rawDi) : null;
        const nweColor = latestBar?.nwe_color ?? 0;
        const lastTime = latestBar?.bar_time || latestBar?.time || "--:--";
        const inEntryWindow = lastTime >= "09:05" && lastTime <= "13:55";

        return keys.map((key) => {
            const meta = STATARB_STRAT_META[key];
            const trades = sessionTrades.filter((t) => t.strat === key || t.strategy_id === key);
            const openTrade = trades.find((t) => t.status === "ABERTA") || null;
            const closedTrades = trades.filter((t) => t.status !== "ABERTA");
            const totalPts = trades.reduce((acc, t) => acc + Number(t.pnl_pts ?? t.pts ?? 0), 0);
            const totalBrl = trades.reduce((acc, t) => acc + Number(t.pnl_brl ?? t.brl_2c ?? 0), 0);
            const lastTrade = trades.length > 0 ? trades[trades.length - 1] : null;

            let liveSignalDesc = "";
            if (key === "CONS") {
                liveSignalDesc = `Z_WDO: ${zWdo != null ? (zWdo >= 0 ? `+${zWdo.toFixed(2)}` : zWdo.toFixed(2)) : "—"} (gatilho ±1.20) · Z_DI: ${zDi != null ? (zDi >= 0 ? `+${zDi.toFixed(2)}` : zDi.toFixed(2)) : "—"} (±1.20)`;
            } else if (key === "DI_NWE") {
                const nweTxt = nweColor === 1 ? "NWE ALTA (filtra Compra)" : nweColor === -1 ? "NWE BAIXA (filtra Venda)" : "NWE Neutro";
                liveSignalDesc = `Z_DI: ${zDi != null ? (zDi >= 0 ? `+${zDi.toFixed(2)}` : zDi.toFixed(2)) : "—"} (gatilho ±2.20) · ${nweTxt}`;
            } else {
                const nweTxt = nweColor === 1 ? "NWE ALTA (filtra Compra)" : nweColor === -1 ? "NWE BAIXA (filtra Venda)" : "NWE Neutro";
                liveSignalDesc = `Z_WDO: ${zWdo != null ? (zWdo >= 0 ? `+${zWdo.toFixed(2)}` : zWdo.toFixed(2)) : "—"} (gatilho ±1.40) · ${nweTxt}`;
            }

            return {
                key,
                meta,
                trades,
                openTrade,
                closedTrades,
                totalPts,
                totalBrl,
                lastTrade,
                liveSignalDesc,
                inEntryWindow,
                lastTime,
            };
        });
    }, [sessionTrades, latestBar]);

    // 3. Resumo agregado do dia (Bruto vs Deduplicado 1x por horário)
    const daySummary = useMemo(() => {
        const totalOps = sessionTrades.length;
        const openOps = sessionTrades.filter((t) => t.status === "ABERTA").length;
        const gains = sessionTrades.filter((t) => {
            const r = String(t.reason || t.exit_reason || "").toUpperCase();
            return r.includes("GAIN") || r.includes("ALVO") || Number(t.pnl_pts ?? t.pts ?? 0) > 0;
        }).length;
        const bes = sessionTrades.filter((t) => String(t.reason || t.exit_reason || "").toUpperCase().includes("BE")).length;
        const stops = sessionTrades.filter((t) => {
            const r = String(t.reason || t.exit_reason || "").toUpperCase();
            return r.includes("STOP") && !r.includes("BE");
        }).length;
        const grossPts = sessionTrades.reduce((a, t) => a + Number(t.pnl_pts ?? t.pts ?? 0), 0);
        const grossBrl = sessionTrades.reduce((a, t) => a + Number(t.pnl_brl ?? t.brl_2c ?? 0), 0);

        // Deduplicado por entry_time (priorizando CONS > DI_NWE > WDO_NWE)
        const priority = { CONS: 1, DI_NWE: 2, WDO_NWE: 3 };
        const byTime = new Map();
        sessionTrades.forEach((tr) => {
            const strat = tr.strat || tr.strategy_id;
            const dir = tr.dir || tr.direction;
            const k = `${tr.entry_time}_${dir}`;
            const prev = byTime.get(k);
            const prevStrat = prev ? (prev.strat || prev.strategy_id) : null;
            if (!prev || (priority[strat] || 9) < (priority[prevStrat] || 9)) {
                byTime.set(k, tr);
            }
        });
        const dedupList = Array.from(byTime.values());
        const dedupPts = dedupList.reduce((a, t) => a + Number(t.pnl_pts ?? t.pts ?? 0), 0);
        const dedupBrl = dedupList.reduce((a, t) => a + Number(t.pnl_brl ?? t.brl_2c ?? 0), 0);

        return {
            totalOps,
            openOps,
            gains,
            bes,
            stops,
            grossPts,
            grossBrl,
            dedupCount: dedupList.length,
            dedupPts,
            dedupBrl,
        };
    }, [sessionTrades]);

    // 4. Histórico Completo Auditado 2026 + Trades da Sessão Atual (se não estiverem duplicados)
    const allAuditedTrades = useMemo(() => {
        const base = getAllAudited2026Trades();
        const todayIso = new Date().toISOString().slice(0, 10);
        const activeDate = selectedDate || todayIso;

        // Mescla operações do pregão atual se ainda não constarem no JSON estático
        const hasDateInBase = base.some((t) => t.date === activeDate);
        let merged = base;
        if (!hasDateInBase && sessionTrades.length > 0) {
            const liveRows = sessionTrades.map((t) => normalizeStatArbTrade({
                ...t,
                date: activeDate,
                date_br: activeDate.includes("-") ? activeDate.split("-").reverse().join("/") : activeDate,
            }));
            merged = [...liveRows, ...base];
        }
        return merged;
    }, [sessionTrades, selectedDate]);

    const filteredAllTrades = useMemo(() => {
        return allAuditedTrades.filter((tr) => {
            const strat = tr.strat || tr.strategy_id;
            if (stratFilter !== "ALL" && strat !== stratFilter) return false;
            if (outcomeFilter !== "ALL") {
                const r = String(tr.reason || tr.exit_reason || "").toUpperCase();
                if (outcomeFilter === "GAIN" && !r.includes("GAIN") && !r.includes("ALVO")) return false;
                if (outcomeFilter === "BE" && !r.includes("BE")) return false;
                if (outcomeFilter === "STOP" && (!r.includes("STOP") || r.includes("BE"))) return false;
            }
            return true;
        });
    }, [allAuditedTrades, stratFilter, outcomeFilter]);

    const totalPages = Math.max(1, Math.ceil(filteredAllTrades.length / PAGE_SIZE));
    const pagedAllTrades = useMemo(() => {
        const start = page * PAGE_SIZE;
        return filteredAllTrades.slice(start, start + PAGE_SIZE);
    }, [filteredAllTrades, page]);

    const displayDateLabel = useMemo(() => {
        if (selectedDate) {
            return selectedDate.includes("-") ? selectedDate.split("-").reverse().join("/") : selectedDate;
        }
        return "HOJE (AO VIVO)";
    }, [selectedDate]);

    return (
        <section
            className="mw-card"
            style={{
                padding: "16px 18px",
                marginTop: 4,
                color: "var(--mw-text-1)",
            }}
        >
            {/* Cabeçalho */}
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: 12,
                    paddingBottom: 12,
                    borderBottom: "1px solid var(--mw-hairline)",
                    marginBottom: 14,
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span
                        className="mw-mono"
                        style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            padding: "4px 10px",
                            borderRadius: 6,
                            fontSize: 11,
                            fontWeight: 600,
                            background: isViewingHistory
                                ? "var(--mw-accent-soft)"
                                : daySummary.openOps > 0
                                ? "rgba(212, 162, 89, 0.14)"
                                : "rgba(76, 195, 138, 0.10)",
                            border: `1px solid ${
                                isViewingHistory
                                    ? "var(--mw-accent-border)"
                                    : daySummary.openOps > 0
                                    ? "rgba(212, 162, 89, 0.4)"
                                    : "rgba(76, 195, 138, 0.35)"
                            }`,
                            color: isViewingHistory
                                ? "var(--mw-accent-ink)"
                                : daySummary.openOps > 0
                                ? "#d4a259"
                                : "#4cc38a",
                        }}
                    >
                        <span
                            style={{
                                width: 6,
                                height: 6,
                                borderRadius: "50%",
                                background: isViewingHistory
                                    ? "#38bdf8"
                                    : daySummary.openOps > 0
                                    ? "#d4a259"
                                    : "#4cc38a",
                            }}
                        />
                        {isViewingHistory
                            ? `Replay · ${displayDateLabel}`
                            : daySummary.openOps > 0
                            ? `Operação em aberto (${daySummary.openOps})`
                            : `Monitor live · ${displayDateLabel}`}
                    </span>

                    <div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--mw-text-1)" }}>
                            Acompanhamento de operações Stat-Arb (WIN × WDO × DI)
                        </div>
                        <div className="mw-mono" style={{ fontSize: 11, color: "var(--mw-text-3)", marginTop: 2 }}>
                            Caixa verde = alvo Wall · caixa vermelha = stop atrás da Wall · degrau âmbar = BE +150p → +15p
                        </div>
                    </div>
                </div>

                {/* Resumo Rápido do Pregão */}
                <div
                    className="mw-mono"
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 12,
                        background: "var(--mw-chrome)",
                        border: "1px solid var(--mw-hairline)",
                        borderRadius: 8,
                        padding: "7px 12px",
                    }}
                >
                    <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>
                            1x p/ horário ({daySummary.dedupCount} op)
                        </div>
                        <div
                            style={{
                                fontSize: 13,
                                fontWeight: 600,
                                color:
                                    daySummary.dedupPts > 0
                                        ? "#4cc38a"
                                        : daySummary.dedupPts < 0
                                        ? "#e5484d"
                                        : "var(--mw-text-2)",
                                whiteSpace: "nowrap",
                            }}
                        >
                            {fmtBrl(daySummary.dedupBrl)}{" "}
                            <span style={{ fontSize: 10.5, fontWeight: 500, opacity: 0.85 }}>
                                ({fmtPts(daySummary.dedupPts)})
                            </span>
                        </div>
                    </div>
                    <div style={{ width: 1, height: 26, background: "var(--mw-hairline-strong)" }} />
                    <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 10, color: "var(--mw-text-3)" }}>
                            Soma 3 setups ({daySummary.totalOps} ops)
                        </div>
                        <div
                            style={{
                                fontSize: 13,
                                fontWeight: 600,
                                color:
                                    daySummary.grossPts > 0
                                        ? "#4cc38a"
                                        : daySummary.grossPts < 0
                                        ? "#e5484d"
                                        : "var(--mw-text-2)",
                                whiteSpace: "nowrap",
                            }}
                        >
                            {fmtBrl(daySummary.grossBrl)}{" "}
                            <span style={{ fontSize: 10.5, fontWeight: 500, opacity: 0.85 }}>
                                ({fmtPts(daySummary.grossPts)})
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            {/* 3 Cards de Status por Estratégia */}
            <div
                style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
                    gap: 12,
                    marginBottom: 16,
                }}
            >
                {stratCards.map((sc) => {
                    const { key, meta, trades, openTrade, totalPts, totalBrl, lastTrade, liveSignalDesc, inEntryWindow, lastTime } = sc;
                    const isOpen = !!openTrade;
                    const hasTraded = trades.length > 0;

                    return (
                        <div
                            key={key}
                            style={{
                                background: "var(--mw-chrome)",
                                border: "1px solid var(--mw-hairline)",
                                borderLeft: `2px solid ${isOpen ? "#d4a259" : meta.color}`,
                                borderRadius: 8,
                                padding: "12px 14px",
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                gap: 8,
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                                <span className="mw-mono" style={{ fontSize: 11.5, fontWeight: 600, color: meta.color }}>
                                    {meta.label}
                                </span>
                                {isOpen ? (
                                    <span
                                        className="mw-mono"
                                        style={{
                                            fontSize: 10,
                                            fontWeight: 600,
                                            padding: "2px 8px",
                                            borderRadius: 5,
                                            background: "rgba(212, 162, 89, 0.14)",
                                            border: "1px solid rgba(212, 162, 89, 0.45)",
                                            color: "#d4a259",
                                        }}
                                    >
                                        Posicionado ao vivo
                                    </span>
                                ) : hasTraded ? (
                                    <span
                                        className="mw-mono"
                                        style={{
                                            fontSize: 10,
                                            fontWeight: 600,
                                            padding: "2px 8px",
                                            borderRadius: 5,
                                            background: totalPts > 0 ? "rgba(76, 195, 138, 0.12)" : "rgba(229, 72, 77, 0.12)",
                                            border: `1px solid ${totalPts > 0 ? "rgba(76, 195, 138, 0.35)" : "rgba(229, 72, 77, 0.35)"}`,
                                            color: totalPts > 0 ? "#4cc38a" : "#e5484d",
                                        }}
                                    >
                                        Encerrado ({trades.length} {trades.length === 1 ? "op" : "ops"})
                                    </span>
                                ) : (
                                    <span
                                        className="mw-mono"
                                        style={{
                                            fontSize: 10,
                                            fontWeight: 500,
                                            padding: "2px 8px",
                                            borderRadius: 5,
                                            background: "var(--mw-card)",
                                            border: "1px solid var(--mw-hairline)",
                                            color: "var(--mw-text-3)",
                                        }}
                                    >
                                        {inEntryWindow ? "Aguardando gatilho" : `Fora da janela (${lastTime})`}
                                    </span>
                                )}
                            </div>

                            {isOpen ? (
                                <div
                                    className="mw-mono"
                                    style={{
                                        background: "var(--mw-card)",
                                        border: "1px solid rgba(212, 162, 89, 0.32)",
                                        borderRadius: 8,
                                        padding: "8px 10px",
                                        fontSize: 11,
                                    }}
                                >
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, gap: 6 }}>
                                        <span style={{ fontWeight: 600, color: openTrade.dir === "BUY" ? "#4cc38a" : "#e5484d" }}>
                                            {openTrade.dir === "BUY" ? "Compra" : "Venda"} @ {fmtPrice(openTrade.entry_price)} ({openTrade.entry_time})
                                        </span>
                                        <span style={{ fontWeight: 600, color: openTrade.pnl_pts >= 0 ? "#4cc38a" : "#e5484d", whiteSpace: "nowrap" }}>
                                            {fmtPts(openTrade.pnl_pts)} ({fmtBrl(openTrade.pnl_brl)})
                                        </span>
                                    </div>
                                    <div style={{ display: "flex", justifyContent: "space-between", color: "var(--mw-text-3)", fontSize: 10.5, gap: 6 }}>
                                        <span>
                                            Alvo Wall: <strong style={{ color: "#4cc38a", fontWeight: 500 }}>{fmtPrice(openTrade.tp_price)}</strong>
                                        </span>
                                        <span>
                                            Stop:{" "}
                                            <strong style={{ color: openTrade.be_triggered ? "#d4a259" : "#e5484d", fontWeight: 500 }}>
                                                {fmtPrice(openTrade.sl_price)}
                                                {openTrade.be_triggered ? " (BE +15p)" : " (Wall ant.)"}
                                            </strong>
                                        </span>
                                    </div>
                                </div>
                            ) : hasTraded && lastTrade ? (
                                <div
                                    className="mw-mono"
                                    style={{
                                        background: "var(--mw-card)",
                                        border: "1px solid var(--mw-hairline)",
                                        borderRadius: 8,
                                        padding: "8px 10px",
                                        fontSize: 11,
                                    }}
                                >
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, gap: 6 }}>
                                        <span style={{ color: "var(--mw-text-2)", fontWeight: 500 }}>
                                            Última:{" "}
                                            <strong style={{ color: lastTrade.dir === "BUY" ? "#4cc38a" : "#e5484d", fontWeight: 600 }}>
                                                {lastTrade.dir === "BUY" ? "Compra" : "Venda"}
                                            </strong>{" "}
                                            ({lastTrade.entry_time} → {lastTrade.exit_time})
                                        </span>
                                        <span style={{ fontWeight: 600, color: totalPts >= 0 ? "#4cc38a" : "#e5484d", whiteSpace: "nowrap" }}>
                                            Dia: {fmtBrl(totalBrl)} ({fmtPts(totalPts)})
                                        </span>
                                    </div>
                                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "var(--mw-text-3)", gap: 6 }}>
                                        <span>
                                            Entrada <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{fmtPrice(lastTrade.entry_price)}</strong> → Saída{" "}
                                            <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{fmtPrice(lastTrade.exit_price)}</strong>
                                        </span>
                                        <span style={{ color: outcomeBadgeStyle(lastTrade.reason, lastTrade.status).color, fontWeight: 600 }}>
                                            {outcomeBadgeStyle(lastTrade.reason, lastTrade.status).label}
                                        </span>
                                    </div>
                                </div>
                            ) : (
                                <div
                                    className="mw-mono"
                                    style={{
                                        background: "var(--mw-card)",
                                        border: "1px dashed var(--mw-hairline)",
                                        borderRadius: 8,
                                        padding: "9px 10px",
                                        fontSize: 11,
                                        color: "var(--mw-text-3)",
                                    }}
                                >
                                    Nenhuma operação disparada neste pregão até o momento.
                                </div>
                            )}

                            <div
                                className="mw-mono"
                                style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    fontSize: 10.5,
                                    color: "var(--mw-text-3)",
                                    borderTop: "1px solid var(--mw-hairline)",
                                    paddingTop: 6,
                                    gap: 6,
                                }}
                            >
                                <span>{liveSignalDesc}</span>
                                <span style={{ whiteSpace: "nowrap" }}>09:05–13:55</span>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Seletor de abas da tabela */}
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: 10,
                    marginBottom: 12,
                }}
            >
                <div className="mw-track">
                    <button
                        type="button"
                        className="mw-btn mw-mono"
                        data-active={activeView === "DAY" ? "true" : "false"}
                        onClick={() => setActiveView("DAY")}
                        style={{ height: 28, padding: "0 12px", fontSize: 11.5 }}
                    >
                        Operações do pregão ({sessionTrades.length})
                    </button>
                    <button
                        type="button"
                        className="mw-btn mw-mono"
                        data-active={activeView === "ALL" ? "true" : "false"}
                        onClick={() => {
                            setActiveView("ALL");
                            setPage(0);
                        }}
                        style={{ height: 28, padding: "0 12px", fontSize: 11.5 }}
                    >
                        Histórico auditado 2026 + Live ({allAuditedTrades.length} ops)
                    </button>
                </div>

                {/* Filtros da aba Histórico Completo */}
                {activeView === "ALL" && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                        <div className="mw-track">
                            {[
                                { id: "ALL", label: "Todas" },
                                { id: "CONS", label: "Consenso" },
                                { id: "DI_NWE", label: "DI_NWE" },
                                { id: "WDO_NWE", label: "WDO_NWE" },
                            ].map((b) => (
                                <button
                                    key={b.id}
                                    type="button"
                                    className="mw-btn mw-mono"
                                    data-active={stratFilter === b.id ? "true" : "false"}
                                    onClick={() => {
                                        setStratFilter(b.id);
                                        setPage(0);
                                    }}
                                    style={{ height: 24, padding: "0 8px", fontSize: 10.5 }}
                                >
                                    {b.label}
                                </button>
                            ))}
                        </div>
                        <div className="mw-track">
                            {[
                                { id: "ALL", label: "Todos desfechos" },
                                { id: "GAIN", label: "Gain Wall" },
                                { id: "BE", label: "Stop BE (+15p)" },
                                { id: "STOP", label: "Stop Wall" },
                            ].map((b) => (
                                <button
                                    key={b.id}
                                    type="button"
                                    className="mw-btn mw-mono"
                                    data-active={outcomeFilter === b.id ? "true" : "false"}
                                    onClick={() => {
                                        setOutcomeFilter(b.id);
                                        setPage(0);
                                    }}
                                    style={{ height: 24, padding: "0 8px", fontSize: 10.5 }}
                                >
                                    {b.label}
                                </button>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* TABELA 1: OPERAÇÕES DO PREGÃO ATUAL / SELECIONADO */}
            {activeView === "DAY" && (
                <div style={{ overflowX: "auto" }}>
                    {sessionTrades.length === 0 ? (
                        <div
                            className="mw-mono"
                            style={{
                                padding: "22px 16px",
                                textAlign: "center",
                                color: "var(--mw-text-3)",
                                fontSize: 11.5,
                                background: "var(--mw-chrome)",
                                border: "1px dashed var(--mw-hairline)",
                                borderRadius: 8,
                            }}
                        >
                            Nenhuma operação disparada no pregão ({displayDateLabel}). Assim que um gatilho Z-Score + Wall for acionado entre 09:05 e 13:55, o acompanhamento aparecerá aqui e no gráfico acima.
                        </div>
                    ) : (
                        <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                            <thead>
                                <tr style={{ background: "var(--mw-chrome)", color: "var(--mw-text-3)", fontSize: 10.5, borderBottom: "1px solid var(--mw-hairline)" }}>
                                    <th style={{ padding: "8px 10px", textAlign: "left", fontWeight: 500 }}>Janela</th>
                                    <th style={{ padding: "8px 10px", textAlign: "left", fontWeight: 500 }}>Estratégia</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center", fontWeight: 500 }}>Lado</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>Entrada</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>Stop Wall</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center", fontWeight: 500 }}>Break-even (+150p)</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>Alvo Wall</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>Saída / atual</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>Pontos</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>R$ (2 cts)</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center", fontWeight: 500 }}>Desfecho</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sessionTrades.map((tr, idx) => {
                                    const meta = STATARB_STRAT_META[tr.strat] || { label: tr.strat, color: "#38bdf8" };
                                    const badge = outcomeBadgeStyle(tr.reason, tr.status);
                                    const isBuy = tr.dir === "BUY";
                                    return (
                                        <tr
                                            key={`${tr.strat}_${tr.entry_time}_${idx}`}
                                            style={{
                                                borderBottom: "1px solid rgba(255,255,255,0.04)",
                                                background: tr.status === "ABERTA" ? "rgba(212, 162, 89, 0.06)" : "transparent",
                                            }}
                                        >
                                            <td style={{ padding: "8px 10px", fontWeight: 500, color: "var(--mw-text-1)", whiteSpace: "nowrap" }}>
                                                {tr.entry_time} <span style={{ color: "var(--mw-text-3)" }}>→</span>{" "}
                                                <span style={{ color: tr.status === "ABERTA" ? "#d4a259" : "var(--mw-text-2)" }}>
                                                    {tr.status === "ABERTA" ? `${tr.exit_time} (Live)` : tr.exit_time}
                                                </span>
                                            </td>
                                            <td style={{ padding: "8px 10px", color: meta.color, fontWeight: 600, whiteSpace: "nowrap" }}>{meta.label}</td>
                                            <td style={{ padding: "8px 10px", textAlign: "center" }}>
                                                <span style={{
                                                    padding: "2px 7px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                                                    background: isBuy ? "rgba(76, 195, 138, 0.12)" : "rgba(229, 72, 77, 0.12)",
                                                    border: `1px solid ${isBuy ? "rgba(76, 195, 138, 0.35)" : "rgba(229, 72, 77, 0.35)"}`,
                                                    color: isBuy ? "#4cc38a" : "#e5484d",
                                                }}>
                                                    {isBuy ? "Compra" : "Venda"}
                                                </span>
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500, color: "var(--mw-text-1)", whiteSpace: "nowrap" }}>{fmtPrice(tr.entry_price)}</td>
                                            <td style={{ padding: "8px 10px", textAlign: "right", color: "#e5484d", whiteSpace: "nowrap" }}>
                                                {fmtPrice(tr.initial_sl_price || tr.sl_price)} <span style={{ fontSize: 10, color: "var(--mw-text-3)" }}>(-{Math.round(tr.sl_dist || 0)}p)</span>
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "center", whiteSpace: "nowrap" }}>
                                                {tr.be_triggered ? (
                                                    <span style={{ color: "#d4a259", fontWeight: 500, fontSize: 10.5 }}>
                                                        Ativado às {tr.be_time} ({fmtPrice(tr.sl_price)})
                                                    </span>
                                                ) : (
                                                    <span style={{ color: "var(--mw-text-3)", fontSize: 10.5 }}>Não atingiu +150p</span>
                                                )}
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "right", color: "#4cc38a", whiteSpace: "nowrap" }}>
                                                {fmtPrice(tr.tp_price)} <span style={{ fontSize: 10, color: "var(--mw-text-3)" }}>(+{Math.round(tr.tp_dist || 0)}p)</span>
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500, color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>{fmtPrice(tr.exit_price)}</td>
                                            <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 600, color: tr.pnl_pts > 0 ? "#4cc38a" : tr.pnl_pts < 0 ? "#e5484d" : "var(--mw-text-3)", whiteSpace: "nowrap" }}>
                                                {fmtPts(tr.pnl_pts)}
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 600, color: tr.pnl_brl > 0 ? "#4cc38a" : tr.pnl_brl < 0 ? "#e5484d" : "var(--mw-text-3)", whiteSpace: "nowrap" }}>
                                                {fmtBrl(tr.pnl_brl)}
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "center", whiteSpace: "nowrap" }}>
                                                <span style={{
                                                    display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 5,
                                                    fontSize: 10, fontWeight: 600, background: badge.bg, border: `1px solid ${badge.border}`, color: badge.color,
                                                }}>
                                                    {badge.label}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                </div>
            )}

            {/* TABELA 2: HISTÓRICO COMPLETO AUDITADO (488+ TRADES DE 2026 + LIVE) */}
            {activeView === "ALL" && (
                <div>
                    <div
                        className="mw-mono"
                        style={{
                            fontSize: 11,
                            color: "var(--mw-text-3)",
                            marginBottom: 8,
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            flexWrap: "wrap",
                            gap: 8,
                        }}
                    >
                        <span>
                            Clique em qualquer operação abaixo para carregar o pregão correspondente no gráfico M5 acima.
                        </span>
                        <span>
                            Exibindo <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{filteredAllTrades.length}</strong> operações · Página{" "}
                            <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{page + 1}</strong> de{" "}
                            <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{totalPages}</strong>
                        </span>
                    </div>

                    <div style={{ overflowX: "auto" }}>
                        <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                            <thead>
                                <tr style={{ background: "var(--mw-chrome)", color: "var(--mw-text-3)", fontSize: 10.5, borderBottom: "1px solid var(--mw-hairline)" }}>
                                    <th style={{ padding: "8px 10px", textAlign: "left", fontWeight: 500 }}>Data</th>
                                    <th style={{ padding: "8px 10px", textAlign: "left", fontWeight: 500 }}>Janela</th>
                                    <th style={{ padding: "8px 10px", textAlign: "left", fontWeight: 500 }}>Estratégia</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center", fontWeight: 500 }}>Lado</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>Entrada</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>Stop inicial</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center", fontWeight: 500 }}>Break-even</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>Alvo Wall</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>Saída</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>Pontos</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right", fontWeight: 500 }}>R$ (2 cts)</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center", fontWeight: 500 }}>Desfecho</th>
                                </tr>
                            </thead>
                            <tbody>
                                {pagedAllTrades.map((tr, idx) => {
                                    const meta = STATARB_STRAT_META[tr.strat] || { label: tr.strat, color: "#38bdf8" };
                                    const badge = outcomeBadgeStyle(tr.reason, tr.status);
                                    const isBuy = tr.dir === "BUY";
                                    const isSelectedDate = selectedDate && tr.date === selectedDate;
                                    return (
                                        <tr
                                            key={`${tr.date}_${tr.strat}_${tr.entry_time}_${idx}`}
                                            onClick={() => {
                                                if (onSelectDate && tr.date) onSelectDate(tr.date);
                                            }}
                                            style={{
                                                cursor: "pointer",
                                                borderBottom: "1px solid rgba(255,255,255,0.04)",
                                                background: isSelectedDate ? "var(--mw-accent-soft)" : "transparent",
                                            }}
                                        >
                                            <td style={{ padding: "7px 10px", fontWeight: 600, color: "#38bdf8", whiteSpace: "nowrap" }}>
                                                {tr.date_br || tr.date}
                                            </td>
                                            <td style={{ padding: "7px 10px", color: "var(--mw-text-2)", whiteSpace: "nowrap" }}>
                                                {tr.entry_time} <span style={{ color: "var(--mw-text-3)" }}>→</span> {tr.exit_time}
                                            </td>
                                            <td style={{ padding: "7px 10px", color: meta.color, fontWeight: 600, whiteSpace: "nowrap" }}>{meta.label}</td>
                                            <td style={{ padding: "7px 10px", textAlign: "center" }}>
                                                <span style={{
                                                    padding: "2px 7px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                                                    background: isBuy ? "rgba(76, 195, 138, 0.12)" : "rgba(229, 72, 77, 0.12)",
                                                    color: isBuy ? "#4cc38a" : "#e5484d",
                                                }}>
                                                    {isBuy ? "Compra" : "Venda"}
                                                </span>
                                            </td>
                                            <td style={{ padding: "7px 10px", textAlign: "right", fontWeight: 500, whiteSpace: "nowrap" }}>{fmtPrice(tr.entry_price)}</td>
                                            <td style={{ padding: "7px 10px", textAlign: "right", color: "#e5484d", whiteSpace: "nowrap" }}>{fmtPrice(tr.initial_sl_price || tr.sl_price)}</td>
                                            <td style={{ padding: "7px 10px", textAlign: "center", fontSize: 10.5, whiteSpace: "nowrap" }}>
                                                {tr.be_triggered ? (
                                                    <span style={{ color: "#d4a259", fontWeight: 500 }}>{tr.be_time || "Sim"}</span>
                                                ) : (
                                                    <span style={{ color: "var(--mw-text-3)" }}>—</span>
                                                )}
                                            </td>
                                            <td style={{ padding: "7px 10px", textAlign: "right", color: "#4cc38a", whiteSpace: "nowrap" }}>{fmtPrice(tr.tp_price)}</td>
                                            <td style={{ padding: "7px 10px", textAlign: "right", fontWeight: 500, whiteSpace: "nowrap" }}>{fmtPrice(tr.exit_price)}</td>
                                            <td style={{ padding: "7px 10px", textAlign: "right", fontWeight: 600, color: tr.pnl_pts >= 0 ? "#4cc38a" : "#e5484d", whiteSpace: "nowrap" }}>{fmtPts(tr.pnl_pts)}</td>
                                            <td style={{ padding: "7px 10px", textAlign: "right", fontWeight: 600, color: tr.pnl_brl >= 0 ? "#4cc38a" : "#e5484d", whiteSpace: "nowrap" }}>{fmtBrl(tr.pnl_brl)}</td>
                                            <td style={{ padding: "7px 10px", textAlign: "center", whiteSpace: "nowrap" }}>
                                                <span style={{
                                                    display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 5,
                                                    fontSize: 10, fontWeight: 600, background: badge.bg, border: `1px solid ${badge.border}`, color: badge.color,
                                                }}>
                                                    {badge.label}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>

                    {/* Paginação */}
                    {totalPages > 1 && (
                        <div className="mw-mono" style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 10, marginTop: 12 }}>
                            <button
                                type="button"
                                className="mw-btn mw-btn-secondary"
                                onClick={() => setPage((p) => Math.max(0, p - 1))}
                                disabled={page === 0}
                                style={{ height: 28, padding: "0 12px", fontSize: 11 }}
                            >
                                Anterior
                            </button>
                            <span style={{ fontSize: 11, color: "var(--mw-text-3)" }}>
                                Página <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{page + 1}</strong> de{" "}
                                <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{totalPages}</strong>
                            </span>
                            <button
                                type="button"
                                className="mw-btn mw-btn-secondary"
                                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                                disabled={page >= totalPages - 1}
                                style={{ height: 28, padding: "0 12px", fontSize: 11 }}
                            >
                                Próxima
                            </button>
                        </div>
                    )}
                </div>
            )}
        </section>
    );
}
