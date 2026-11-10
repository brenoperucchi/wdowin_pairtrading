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
            bg: "rgba(251, 191, 36, 0.16)",
            border: "rgba(251, 191, 36, 0.55)",
            color: "#fbbf24",
            icon: "⏳",
            label: "EM ABERTO (LIVE)",
        };
    }
    const r = String(reason || "").toUpperCase();
    if (r.includes("GAIN") || r.includes("ALVO")) {
        return {
            bg: "rgba(8, 153, 129, 0.22)",
            border: "rgba(45, 212, 191, 0.55)",
            color: "#2dd4bf",
            icon: "🎯",
            label: reason || "ALVO WALL",
        };
    }
    if (r.includes("BE")) {
        return {
            bg: "rgba(251, 191, 36, 0.16)",
            border: "rgba(251, 191, 36, 0.5)",
            color: "#fbbf24",
            icon: "🛡️",
            label: reason || "STOP BE (+15p)",
        };
    }
    if (r.includes("STOP")) {
        return {
            bg: "rgba(242, 54, 69, 0.2)",
            border: "rgba(251, 113, 133, 0.55)",
            color: "#fb7185",
            icon: "🛑",
            label: reason || "STOP WALL",
        };
    }
    return {
        bg: "rgba(148, 163, 184, 0.16)",
        border: "rgba(148, 163, 184, 0.4)",
        color: "#cbd5e1",
        icon: "⏰",
        label: reason || "SAÍDA 16:50",
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
        <div
            style={{
                background: "linear-gradient(180deg, #0b111a 0%, #070b10 100%)",
                border: "1px solid #1e293b",
                borderRadius: 12,
                padding: "16px 18px",
                marginTop: 10,
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                color: "#e2e8f0",
                boxShadow: "0 10px 30px rgba(0,0,0,0.45)",
            }}
        >
            {/* ── Cabeçalho: Monitoramento Ao Vivo & Caixas de Posição ── */}
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: 12,
                    paddingBottom: 12,
                    borderBottom: "1px solid #1e293b",
                    marginBottom: 14,
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span
                        style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            padding: "4px 10px",
                            borderRadius: 6,
                            fontSize: 10,
                            fontWeight: 900,
                            letterSpacing: 1,
                            background: isViewingHistory
                                ? "rgba(56, 189, 248, 0.14)"
                                : daySummary.openOps > 0
                                ? "rgba(251, 191, 36, 0.18)"
                                : "rgba(16, 185, 129, 0.14)",
                            border: `1px solid ${
                                isViewingHistory
                                    ? "rgba(56, 189, 248, 0.45)"
                                    : daySummary.openOps > 0
                                    ? "rgba(251, 191, 36, 0.55)"
                                    : "rgba(16, 185, 129, 0.4)"
                            }`,
                            color: isViewingHistory
                                ? "#38bdf8"
                                : daySummary.openOps > 0
                                ? "#fbbf24"
                                : "#10b981",
                        }}
                    >
                        <span
                            style={{
                                width: 7,
                                height: 7,
                                borderRadius: "50%",
                                background: isViewingHistory
                                    ? "#38bdf8"
                                    : daySummary.openOps > 0
                                    ? "#fbbf24"
                                    : "#10b981",
                                boxShadow: `0 0 8px ${
                                    isViewingHistory
                                        ? "#38bdf8"
                                        : daySummary.openOps > 0
                                        ? "#fbbf24"
                                        : "#10b981"
                                }`,
                            }}
                        />
                        {isViewingHistory
                            ? `REPLAY DE PREGÃO · ${displayDateLabel}`
                            : daySummary.openOps > 0
                            ? `OPERAÇÃO EM ABERTO AO VIVO (${daySummary.openOps})`
                            : `MONITORAMENTO LIVE TRADE · ${displayDateLabel}`}
                    </span>

                    <div>
                        <div style={{ fontSize: 13, fontWeight: 800, color: "#f8fafc" }}>
                            Acompanhamento de Operações Stat-Arb (WIN × WDO × DI)
                        </div>
                        <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>
                            Marcações no gráfico seguem o padrão TradingView (Caixa Verde = Alvo Wall · Caixa Vermelha = Stop atrás da Wall · Degrau Amarelo = Break-Even +150p → +15p · Linha Tracejada = Início ao Fim da Operação)
                        </div>
                    </div>
                </div>

                {/* Resumo Rápido do Pregão */}
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        background: "#0f172a",
                        border: "1px solid #1e293b",
                        borderRadius: 8,
                        padding: "6px 12px",
                    }}
                >
                    <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 9, color: "#64748b", textTransform: "uppercase" }}>
                            1x p/ Horário ({daySummary.dedupCount} op)
                        </div>
                        <div
                            style={{
                                fontSize: 13,
                                fontWeight: 900,
                                color:
                                    daySummary.dedupPts > 0
                                        ? "#10b981"
                                        : daySummary.dedupPts < 0
                                        ? "#f43f5e"
                                        : "#94a3b8",
                            }}
                        >
                            {fmtBrl(daySummary.dedupBrl)}{" "}
                            <span style={{ fontSize: 10, fontWeight: 700, opacity: 0.85 }}>
                                ({fmtPts(daySummary.dedupPts)})
                            </span>
                        </div>
                    </div>
                    <div style={{ width: 1, height: 24, background: "#1e293b" }} />
                    <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 9, color: "#64748b", textTransform: "uppercase" }}>
                            Soma 3 Setups ({daySummary.totalOps} ops)
                        </div>
                        <div
                            style={{
                                fontSize: 13,
                                fontWeight: 900,
                                color:
                                    daySummary.grossPts > 0
                                        ? "#10b981"
                                        : daySummary.grossPts < 0
                                        ? "#f43f5e"
                                        : "#94a3b8",
                            }}
                        >
                            {fmtBrl(daySummary.grossBrl)}{" "}
                            <span style={{ fontSize: 10, fontWeight: 700, opacity: 0.85 }}>
                                ({fmtPts(daySummary.grossPts)})
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            {/* ── 3 Cards de Status Ao Vivo por Estratégia ── */}
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
                                background: isOpen
                                    ? "linear-gradient(180deg, rgba(251,191,36,0.09) 0%, rgba(15,23,42,0.95) 100%)"
                                    : "#0f172a",
                                border: `1px solid ${
                                    isOpen ? "#fbbf24" : hasTraded ? `${meta.color}55` : "#1e293b"
                                }`,
                                borderTop: `3px solid ${isOpen ? "#fbbf24" : meta.color}`,
                                borderRadius: 10,
                                padding: "12px 14px",
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                gap: 8,
                            }}
                        >
                            {/* Linha 1: Nome da Estratégia + Status Badge */}
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                                <span style={{ fontSize: 11, fontWeight: 900, color: meta.color, letterSpacing: 0.4 }}>
                                    {meta.label}
                                </span>
                                {isOpen ? (
                                    <span
                                        style={{
                                            fontSize: 9,
                                            fontWeight: 900,
                                            padding: "2px 8px",
                                            borderRadius: 4,
                                            background: "rgba(251, 191, 36, 0.2)",
                                            border: "1px solid #fbbf24",
                                            color: "#fbbf24",
                                        }}
                                    >
                                        ⏳ POSICIONADO AO VIVO
                                    </span>
                                ) : hasTraded ? (
                                    <span
                                        style={{
                                            fontSize: 9,
                                            fontWeight: 800,
                                            padding: "2px 8px",
                                            borderRadius: 4,
                                            background:
                                                totalPts > 0
                                                    ? "rgba(16, 185, 129, 0.16)"
                                                    : "rgba(244, 63, 94, 0.16)",
                                            border: `1px solid ${totalPts > 0 ? "#10b98166" : "#f43f5e66"}`,
                                            color: totalPts > 0 ? "#10b981" : "#fb7185",
                                        }}
                                    >
                                        ✅ ENCERRADO ({trades.length} {trades.length === 1 ? "op" : "ops"})
                                    </span>
                                ) : (
                                    <span
                                        style={{
                                            fontSize: 9,
                                            fontWeight: 700,
                                            padding: "2px 8px",
                                            borderRadius: 4,
                                            background: "rgba(148, 163, 184, 0.1)",
                                            border: "1px solid #334155",
                                            color: "#94a3b8",
                                        }}
                                    >
                                        {inEntryWindow ? "⚪ AGUARDANDO GATILHO" : `⏸️ FORA DA JANELA (${lastTime})`}
                                    </span>
                                )}
                            </div>

                            {/* Corpo do Card: Se estiver posicionado ao vivo, mostra detalhes da posição aberta */}
                            {isOpen ? (
                                <div
                                    style={{
                                        background: "rgba(2, 6, 23, 0.65)",
                                        border: "1px solid rgba(251, 191, 36, 0.35)",
                                        borderRadius: 8,
                                        padding: "8px 10px",
                                        fontSize: 10,
                                    }}
                                >
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                        <span
                                            style={{
                                                fontWeight: 900,
                                                color: openTrade.dir === "BUY" ? "#2dd4bf" : "#fb7185",
                                            }}
                                        >
                                            {openTrade.dir === "BUY" ? "▲ COMPRA" : "▼ VENDA"} @{" "}
                                            {fmtPrice(openTrade.entry_price)} ({openTrade.entry_time})
                                        </span>
                                        <span
                                            style={{
                                                fontWeight: 900,
                                                color: openTrade.pnl_pts >= 0 ? "#10b981" : "#f43f5e",
                                            }}
                                        >
                                            {fmtPts(openTrade.pnl_pts)} ({fmtBrl(openTrade.pnl_brl)})
                                        </span>
                                    </div>
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            color: "#94a3b8",
                                            fontSize: 9.5,
                                        }}
                                    >
                                        <span>
                                            🎯 Alvo Wall:{" "}
                                            <strong style={{ color: "#2dd4bf" }}>{fmtPrice(openTrade.tp_price)}</strong>
                                        </span>
                                        <span>
                                            🛑 Stop:{" "}
                                            <strong
                                                style={{
                                                    color: openTrade.be_triggered ? "#fbbf24" : "#fb7185",
                                                }}
                                            >
                                                {fmtPrice(openTrade.sl_price)}
                                                {openTrade.be_triggered ? " (BE +15p 🔒)" : " (Wall Ant.)"}
                                            </strong>
                                        </span>
                                    </div>
                                </div>
                            ) : hasTraded && lastTrade ? (
                                <div
                                    style={{
                                        background: "rgba(2, 6, 23, 0.55)",
                                        border: "1px solid #1e293b",
                                        borderRadius: 8,
                                        padding: "8px 10px",
                                        fontSize: 10,
                                    }}
                                >
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                        <span style={{ color: "#cbd5e1", fontWeight: 700 }}>
                                            Última:{" "}
                                            <strong
                                                style={{
                                                    color: lastTrade.dir === "BUY" ? "#2dd4bf" : "#fb7185",
                                                }}
                                            >
                                                {lastTrade.dir === "BUY" ? "COMPRA" : "VENDA"}
                                            </strong>{" "}
                                            ({lastTrade.entry_time} → {lastTrade.exit_time})
                                        </span>
                                        <span
                                            style={{
                                                fontWeight: 900,
                                                color: totalPts >= 0 ? "#10b981" : "#f43f5e",
                                            }}
                                        >
                                            Dia: {fmtBrl(totalBrl)} ({fmtPts(totalPts)})
                                        </span>
                                    </div>
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: 9.5,
                                            color: "#94a3b8",
                                        }}
                                    >
                                        <span>
                                            Entrada <strong style={{ color: "#e2e8f0" }}>{fmtPrice(lastTrade.entry_price)}</strong> → Saída{" "}
                                            <strong style={{ color: "#e2e8f0" }}>{fmtPrice(lastTrade.exit_price)}</strong>
                                        </span>
                                        <span
                                            style={{
                                                color: outcomeBadgeStyle(lastTrade.reason, lastTrade.status).color,
                                                fontWeight: 800,
                                            }}
                                        >
                                            {outcomeBadgeStyle(lastTrade.reason, lastTrade.status).icon} {lastTrade.reason}
                                        </span>
                                    </div>
                                </div>
                            ) : (
                                <div
                                    style={{
                                        background: "rgba(2, 6, 23, 0.4)",
                                        border: "1px dashed #1e293b",
                                        borderRadius: 8,
                                        padding: "8px 10px",
                                        fontSize: 10,
                                        color: "#64748b",
                                    }}
                                >
                                    Nenhuma operação disparada neste pregão até o momento.
                                </div>
                            )}

                            {/* Rodapé do Card: Leitura atual dos filtros */}
                            <div
                                style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    fontSize: 9.5,
                                    color: "#64748b",
                                    borderTop: "1px solid rgba(30,41,59,0.6)",
                                    paddingTop: 6,
                                }}
                            >
                                <span>{liveSignalDesc}</span>
                                <span style={{ color: "#475569" }}>09:05–13:55</span>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* ── Seletor de Abas da Tabela: Operações do Pregão vs Histórico Auditado 2026 ── */}
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
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button
                        onClick={() => setActiveView("DAY")}
                        style={{
                            padding: "7px 14px",
                            borderRadius: 7,
                            fontSize: 11,
                            fontWeight: 800,
                            cursor: "pointer",
                            border:
                                activeView === "DAY"
                                    ? "1px solid #38bdf8"
                                    : "1px solid #1e293b",
                            background:
                                activeView === "DAY"
                                    ? "rgba(56, 189, 248, 0.16)"
                                    : "#0f172a",
                            color: activeView === "DAY" ? "#38bdf8" : "#94a3b8",
                        }}
                    >
                        🟢 Operações do Pregão ({sessionTrades.length})
                    </button>
                    <button
                        onClick={() => {
                            setActiveView("ALL");
                            setPage(0);
                        }}
                        style={{
                            padding: "7px 14px",
                            borderRadius: 7,
                            fontSize: 11,
                            fontWeight: 800,
                            cursor: "pointer",
                            border:
                                activeView === "ALL"
                                    ? "1px solid #a78bfa"
                                    : "1px solid #1e293b",
                            background:
                                activeView === "ALL"
                                    ? "rgba(167, 139, 250, 0.16)"
                                    : "#0f172a",
                            color: activeView === "ALL" ? "#c4b5fd" : "#94a3b8",
                        }}
                    >
                        📋 Histórico Auditado Completo 2026 + Live ({allAuditedTrades.length} ops)
                    </button>
                </div>

                {/* Filtros da aba Histórico Completo */}
                {activeView === "ALL" && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                        {[
                            { id: "ALL", label: "Todas" },
                            { id: "CONS", label: "1. CONSENSO", color: "#38bdf8" },
                            { id: "DI_NWE", label: "2. DI_NWE", color: "#a855f7" },
                            { id: "WDO_NWE", label: "3. WDO_NWE", color: "#f59e0b" },
                        ].map((b) => (
                            <button
                                key={b.id}
                                onClick={() => {
                                    setStratFilter(b.id);
                                    setPage(0);
                                }}
                                style={{
                                    padding: "4px 9px",
                                    borderRadius: 5,
                                    fontSize: 10,
                                    fontWeight: 800,
                                    cursor: "pointer",
                                    border:
                                        stratFilter === b.id
                                            ? `1px solid ${b.color || "#38bdf8"}`
                                            : "1px solid #1e293b",
                                    background:
                                        stratFilter === b.id
                                            ? "rgba(30, 41, 59, 0.9)"
                                            : "#090d14",
                                    color:
                                        stratFilter === b.id
                                            ? b.color || "#f8fafc"
                                            : "#64748b",
                                }}
                            >
                                {b.label}
                            </button>
                        ))}
                        <span style={{ color: "#334155" }}>|</span>
                        {[
                            { id: "ALL", label: "Todos Desfechos" },
                            { id: "GAIN", label: "🎯 Gain Wall", color: "#2dd4bf" },
                            { id: "BE", label: "🛡️ Stop BE (+15p)", color: "#fbbf24" },
                            { id: "STOP", label: "🛑 Stop Wall", color: "#fb7185" },
                        ].map((b) => (
                            <button
                                key={b.id}
                                onClick={() => {
                                    setOutcomeFilter(b.id);
                                    setPage(0);
                                }}
                                style={{
                                    padding: "4px 9px",
                                    borderRadius: 5,
                                    fontSize: 10,
                                    fontWeight: 800,
                                    cursor: "pointer",
                                    border:
                                        outcomeFilter === b.id
                                            ? `1px solid ${b.color || "#38bdf8"}`
                                            : "1px solid #1e293b",
                                    background:
                                        outcomeFilter === b.id
                                            ? "rgba(30, 41, 59, 0.9)"
                                            : "#090d14",
                                    color:
                                        outcomeFilter === b.id
                                            ? b.color || "#f8fafc"
                                            : "#64748b",
                                }}
                            >
                                {b.label}
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {/* ── TABELA 1: OPERAÇÕES DO PREGÃO ATUAL / SELECIONADO ── */}
            {activeView === "DAY" && (
                <div style={{ overflowX: "auto" }}>
                    {sessionTrades.length === 0 ? (
                        <div
                            style={{
                                padding: "24px 16px",
                                textAlign: "center",
                                color: "#64748b",
                                fontSize: 11,
                                background: "#090d14",
                                border: "1px dashed #1e293b",
                                borderRadius: 8,
                            }}
                        >
                            Nenhuma operação disparada no pregão ({displayDateLabel}). Assim que um gatilho Z-Score + Wall for acionado entre 09:05 e 13:55, a caixa de posição e o acompanhamento em tempo real aparecerão aqui e no gráfico acima.
                        </div>
                    ) : (
                        <table
                            style={{
                                width: "100%",
                                borderCollapse: "collapse",
                                fontSize: 11,
                            }}
                        >
                            <thead>
                                <tr
                                    style={{
                                        background: "#090d14",
                                        color: "#64748b",
                                        fontSize: 9.5,
                                        textTransform: "uppercase",
                                        letterSpacing: 0.6,
                                        borderBottom: "1px solid #1e293b",
                                    }}
                                >
                                    <th style={{ padding: "8px 10px", textAlign: "left" }}>Janela (Início → Fim)</th>
                                    <th style={{ padding: "8px 10px", textAlign: "left" }}>Estratégia</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center" }}>Lado</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Entrada</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Stop Wall Ant.</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center" }}>Break-Even (+150p)</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Alvo Próx. Wall</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Saída / Atual</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Resultado (Pts)</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>R$ (2 Cts)</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center" }}>Status / Desfecho</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sessionTrades.map((tr, idx) => {
                                    const meta = STATARB_STRAT_META[tr.strat] || {
                                        label: tr.strat,
                                        color: "#38bdf8",
                                    };
                                    const badge = outcomeBadgeStyle(tr.reason, tr.status);
                                    const isBuy = tr.dir === "BUY";
                                    return (
                                        <tr
                                            key={`${tr.strat}_${tr.entry_time}_${idx}`}
                                            style={{
                                                borderBottom: "1px solid rgba(30,41,59,0.65)",
                                                background:
                                                    tr.status === "ABERTA"
                                                        ? "rgba(251, 191, 36, 0.06)"
                                                        : idx % 2 === 0
                                                        ? "transparent"
                                                        : "rgba(15, 23, 42, 0.4)",
                                            }}
                                        >
                                            <td style={{ padding: "9px 10px", fontWeight: 800, color: "#f8fafc" }}>
                                                {tr.entry_time}{" "}
                                                <span style={{ color: "#64748b" }}>→</span>{" "}
                                                <span
                                                    style={{
                                                        color:
                                                            tr.status === "ABERTA"
                                                                ? "#fbbf24"
                                                                : "#cbd5e1",
                                                    }}
                                                >
                                                    {tr.status === "ABERTA"
                                                        ? `${tr.exit_time} (Ao Vivo)`
                                                        : tr.exit_time}
                                                </span>
                                            </td>
                                            <td style={{ padding: "9px 10px" }}>
                                                <span
                                                    style={{
                                                        color: meta.color,
                                                        fontWeight: 900,
                                                        fontSize: 10.5,
                                                    }}
                                                >
                                                    {meta.label}
                                                </span>
                                            </td>
                                            <td style={{ padding: "9px 10px", textAlign: "center" }}>
                                                <span
                                                    style={{
                                                        padding: "2px 7px",
                                                        borderRadius: 4,
                                                        fontSize: 9.5,
                                                        fontWeight: 900,
                                                        background: isBuy
                                                            ? "rgba(8, 153, 129, 0.2)"
                                                            : "rgba(242, 54, 69, 0.2)",
                                                        border: `1px solid ${
                                                            isBuy ? "#2dd4bf66" : "#fb718566"
                                                        }`,
                                                        color: isBuy ? "#2dd4bf" : "#fb7185",
                                                    }}
                                                >
                                                    {isBuy ? "▲ COMPRA" : "▼ VENDA"}
                                                </span>
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 10px",
                                                    textAlign: "right",
                                                    fontWeight: 800,
                                                    color: "#f8fafc",
                                                }}
                                            >
                                                {fmtPrice(tr.entry_price)}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 10px",
                                                    textAlign: "right",
                                                    color: "#fb7185",
                                                }}
                                            >
                                                {fmtPrice(tr.initial_sl_price || tr.sl_price)}{" "}
                                                <span style={{ fontSize: 9.5, color: "#64748b" }}>
                                                    (-{Math.round(tr.sl_dist || 0)}p)
                                                </span>
                                            </td>
                                            <td style={{ padding: "9px 10px", textAlign: "center" }}>
                                                {tr.be_triggered ? (
                                                    <span
                                                        style={{
                                                            color: "#fbbf24",
                                                            fontWeight: 800,
                                                            fontSize: 10,
                                                        }}
                                                    >
                                                        🔒 Ativado às {tr.be_time} ({fmtPrice(tr.sl_price)})
                                                    </span>
                                                ) : (
                                                    <span style={{ color: "#475569", fontSize: 10 }}>
                                                        Não atingiu +150p
                                                    </span>
                                                )}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 10px",
                                                    textAlign: "right",
                                                    color: "#2dd4bf",
                                                }}
                                            >
                                                {fmtPrice(tr.tp_price)}{" "}
                                                <span style={{ fontSize: 9.5, color: "#64748b" }}>
                                                    (+{Math.round(tr.tp_dist || 0)}p)
                                                </span>
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 10px",
                                                    textAlign: "right",
                                                    fontWeight: 800,
                                                    color: "#e2e8f0",
                                                }}
                                            >
                                                {fmtPrice(tr.exit_price)}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 10px",
                                                    textAlign: "right",
                                                    fontWeight: 900,
                                                    color:
                                                        tr.pnl_pts > 0
                                                            ? "#10b981"
                                                            : tr.pnl_pts < 0
                                                            ? "#f43f5e"
                                                            : "#94a3b8",
                                                }}
                                            >
                                                {fmtPts(tr.pnl_pts)}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 10px",
                                                    textAlign: "right",
                                                    fontWeight: 900,
                                                    color:
                                                        tr.pnl_brl > 0
                                                            ? "#10b981"
                                                            : tr.pnl_brl < 0
                                                            ? "#f43f5e"
                                                            : "#94a3b8",
                                                }}
                                            >
                                                {fmtBrl(tr.pnl_brl)}
                                            </td>
                                            <td style={{ padding: "9px 10px", textAlign: "center" }}>
                                                <span
                                                    style={{
                                                        display: "inline-flex",
                                                        alignItems: "center",
                                                        gap: 4,
                                                        padding: "3px 8px",
                                                        borderRadius: 5,
                                                        fontSize: 9.5,
                                                        fontWeight: 900,
                                                        background: badge.bg,
                                                        border: `1px solid ${badge.border}`,
                                                        color: badge.color,
                                                    }}
                                                >
                                                    {badge.icon} {badge.label}
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

            {/* ── TABELA 2: HISTÓRICO COMPLETO AUDITADO (488+ TRADES DE 2026 + LIVE) ── */}
            {activeView === "ALL" && (
                <div>
                    <div
                        style={{
                            fontSize: 10,
                            color: "#94a3b8",
                            marginBottom: 8,
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            flexWrap: "wrap",
                            gap: 8,
                        }}
                    >
                        <span>
                            💡 <strong>Clique em qualquer operação abaixo</strong> para carregar o pregão correspondente no gráfico M5 acima com a Caixa de Posição (Entrada, Break-Even e Saída).
                        </span>
                        <span>
                            Exibindo <strong>{filteredAllTrades.length}</strong> operações filtradas · Página{" "}
                            <strong>{page + 1}</strong> de <strong>{totalPages}</strong>
                        </span>
                    </div>

                    <div style={{ overflowX: "auto" }}>
                        <table
                            style={{
                                width: "100%",
                                borderCollapse: "collapse",
                                fontSize: 11,
                            }}
                        >
                            <thead>
                                <tr
                                    style={{
                                        background: "#090d14",
                                        color: "#64748b",
                                        fontSize: 9.5,
                                        textTransform: "uppercase",
                                        letterSpacing: 0.6,
                                        borderBottom: "1px solid #1e293b",
                                    }}
                                >
                                    <th style={{ padding: "8px 10px", textAlign: "left" }}>Data</th>
                                    <th style={{ padding: "8px 10px", textAlign: "left" }}>Janela (Início → Fim)</th>
                                    <th style={{ padding: "8px 10px", textAlign: "left" }}>Estratégia</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center" }}>Lado</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Entrada</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Stop Inicial</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center" }}>Break-Even</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Alvo Wall</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Saída</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Pontos</th>
                                    <th style={{ padding: "8px 10px", textAlign: "right" }}>R$ (2 Cts)</th>
                                    <th style={{ padding: "8px 10px", textAlign: "center" }}>Desfecho</th>
                                </tr>
                            </thead>
                            <tbody>
                                {pagedAllTrades.map((tr, idx) => {
                                    const meta = STATARB_STRAT_META[tr.strat] || {
                                        label: tr.strat,
                                        color: "#38bdf8",
                                    };
                                    const badge = outcomeBadgeStyle(tr.reason, tr.status);
                                    const isBuy = tr.dir === "BUY";
                                    const isSelectedDate = selectedDate && tr.date === selectedDate;
                                    return (
                                        <tr
                                            key={`${tr.date}_${tr.strat}_${tr.entry_time}_${idx}`}
                                            onClick={() => {
                                                if (onSelectDate && tr.date) {
                                                    onSelectDate(tr.date);
                                                }
                                            }}
                                            style={{
                                                cursor: "pointer",
                                                borderBottom: "1px solid rgba(30,41,59,0.6)",
                                                background: isSelectedDate
                                                    ? "rgba(56, 189, 248, 0.12)"
                                                    : idx % 2 === 0
                                                    ? "transparent"
                                                    : "rgba(15, 23, 42, 0.4)",
                                                transition: "background 0.15s",
                                            }}
                                        >
                                            <td
                                                style={{
                                                    padding: "8px 10px",
                                                    fontWeight: 800,
                                                    color: "#38bdf8",
                                                }}
                                            >
                                                📅 {tr.date_br || tr.date}
                                            </td>
                                            <td style={{ padding: "8px 10px", fontWeight: 700, color: "#e2e8f0" }}>
                                                {tr.entry_time} <span style={{ color: "#64748b" }}>→</span>{" "}
                                                {tr.exit_time}
                                            </td>
                                            <td style={{ padding: "8px 10px" }}>
                                                <span
                                                    style={{
                                                        color: meta.color,
                                                        fontWeight: 900,
                                                        fontSize: 10.5,
                                                    }}
                                                >
                                                    {meta.label}
                                                </span>
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "center" }}>
                                                <span
                                                    style={{
                                                        padding: "2px 7px",
                                                        borderRadius: 4,
                                                        fontSize: 9.5,
                                                        fontWeight: 900,
                                                        background: isBuy
                                                            ? "rgba(8, 153, 129, 0.2)"
                                                            : "rgba(242, 54, 69, 0.2)",
                                                        color: isBuy ? "#2dd4bf" : "#fb7185",
                                                    }}
                                                >
                                                    {isBuy ? "▲ COMPRA" : "▼ VENDA"}
                                                </span>
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700 }}>
                                                {fmtPrice(tr.entry_price)}
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "right", color: "#fb7185" }}>
                                                {fmtPrice(tr.initial_sl_price || tr.sl_price)}
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "center", fontSize: 10 }}>
                                                {tr.be_triggered ? (
                                                    <span style={{ color: "#fbbf24", fontWeight: 800 }}>
                                                        🔒 {tr.be_time || "Sim"}
                                                    </span>
                                                ) : (
                                                    <span style={{ color: "#475569" }}>—</span>
                                                )}
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "right", color: "#2dd4bf" }}>
                                                {fmtPrice(tr.tp_price)}
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700 }}>
                                                {fmtPrice(tr.exit_price)}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "8px 10px",
                                                    textAlign: "right",
                                                    fontWeight: 900,
                                                    color: tr.pnl_pts >= 0 ? "#10b981" : "#f43f5e",
                                                }}
                                            >
                                                {fmtPts(tr.pnl_pts)}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "8px 10px",
                                                    textAlign: "right",
                                                    fontWeight: 900,
                                                    color: tr.pnl_brl >= 0 ? "#10b981" : "#f43f5e",
                                                }}
                                            >
                                                {fmtBrl(tr.pnl_brl)}
                                            </td>
                                            <td style={{ padding: "8px 10px", textAlign: "center" }}>
                                                <span
                                                    style={{
                                                        display: "inline-flex",
                                                        alignItems: "center",
                                                        gap: 4,
                                                        padding: "2px 8px",
                                                        borderRadius: 5,
                                                        fontSize: 9.5,
                                                        fontWeight: 800,
                                                        background: badge.bg,
                                                        border: `1px solid ${badge.border}`,
                                                        color: badge.color,
                                                    }}
                                                >
                                                    {badge.icon} {badge.label}
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
                        <div
                            style={{
                                display: "flex",
                                justifyContent: "center",
                                alignItems: "center",
                                gap: 10,
                                marginTop: 12,
                            }}
                        >
                            <button
                                onClick={() => setPage((p) => Math.max(0, p - 1))}
                                disabled={page === 0}
                                style={{
                                    padding: "5px 12px",
                                    borderRadius: 6,
                                    fontSize: 10,
                                    fontWeight: 800,
                                    cursor: page === 0 ? "not-allowed" : "pointer",
                                    background: "#0f172a",
                                    border: "1px solid #1e293b",
                                    color: page === 0 ? "#475569" : "#e2e8f0",
                                }}
                            >
                                ◀ Anterior
                            </button>
                            <span style={{ fontSize: 10, color: "#94a3b8" }}>
                                Página <strong>{page + 1}</strong> de <strong>{totalPages}</strong>
                            </span>
                            <button
                                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                                disabled={page >= totalPages - 1}
                                style={{
                                    padding: "5px 12px",
                                    borderRadius: 6,
                                    fontSize: 10,
                                    fontWeight: 800,
                                    cursor: page >= totalPages - 1 ? "not-allowed" : "pointer",
                                    background: "#0f172a",
                                    border: "1px solid #1e293b",
                                    color: page >= totalPages - 1 ? "#475569" : "#e2e8f0",
                                }}
                            >
                                Próxima ▶
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
