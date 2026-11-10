import React, { useState, useMemo, useRef } from "react";
import RAW from "../data/statarb2026Data.json";

const MONTH_NAMES = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
};

export default function StatArbBacktest2026Panel({ onSelectDate }) {
    const [activeTab, setActiveTab] = useState("chart"); // "chart" | "corr" | "monthly" | "daily"
    const [unit, setUnit] = useState("brl"); // "brl" | "pts"
    const [dailyFilter, setDailyFilter] = useState("all"); // "all" | "active" | "win" | "loss" | "flat"
    const [hoverIdx, setHoverIdx] = useState(null);
    const svgRef = useRef(null);

    const fmt = (valBrl) => {
        if (unit === "brl") {
            const sign = valBrl > 0 ? "+" : valBrl < 0 ? "-" : "";
            return `${sign}R$ ${Math.abs(Math.round(valBrl)).toLocaleString("pt-BR")}`;
        } else {
            const pts = Math.round(valBrl / 0.4);
            const sign = pts > 0 ? "+" : pts < 0 ? "-" : "";
            return `${sign}${Math.abs(pts).toLocaleString("pt-BR")} pts`;
        }
    };

    const days = RAW.days;
    const monthly = RAW.monthly;
    const N = days.length;
    const mult = unit === "brl" ? 1 : 2.5;

    const chartData = useMemo(() => {
        let cumC = 0, cumW = 0, cumD = 0;
        const series = days.map((d) => {
            cumC += d[2];
            cumW += d[3];
            cumD += d[4];
            return {
                date: d[0],
                nT: d[1],
                cDay: d[2] * mult,
                wDay: d[3] * mult,
                dDay: d[4] * mult,
                totDay: d[5] * mult,
                cumC: cumC * mult,
                cumW: cumW * mult,
                cumD: cumD * mult,
                cumTot: d[6] * mult,
                dd: d[7] * mult,
                raw: d,
            };
        });
        const maxEq = Math.max(...series.map((s) => s.cumTot), 1000) * 1.06;
        const minEq = Math.min(0, ...series.map((s) => Math.min(s.cumC, s.cumW, s.cumD)));
        const minDD = Math.min(...series.map((s) => s.dd), -100) * 1.15;
        return { series, maxEq, minEq, minDD };
    }, [days, mult]);

    const W = 920, H = 390;
    const padL = 68, padR = 24, padT = 18;
    const eqH = 245, gapH = 22, ddT = padT + eqH + gapH, ddH = 72;
    const plotW = W - padL - padR;

    const xOf = (i) => padL + (i / (N - 1)) * plotW;
    const yOfEq = (v) => padT + eqH - ((v - chartData.minEq) / (chartData.maxEq - chartData.minEq)) * eqH;
    const yOfDD = (v) => ddT + ((0 - v) / (0 - chartData.minDD)) * ddH;

    const makePath = (key) =>
        chartData.series
            .map((s, i) => `${i === 0 ? "M" : "L"}${xOf(i).toFixed(1)},${yOfEq(s[key]).toFixed(1)}`)
            .join(" ");

    const pTot = makePath("cumTot");
    const pC = makePath("cumC");
    const pD = makePath("cumD");
    const pW = makePath("cumW");
    const areaTot = `${pTot} L${xOf(N - 1).toFixed(1)},${yOfEq(0).toFixed(1)} L${xOf(0).toFixed(1)},${yOfEq(0).toFixed(1)} Z`;

    const pDD = chartData.series
        .map((s, i) => `${i === 0 ? "M" : "L"}${xOf(i).toFixed(1)},${yOfDD(s.dd).toFixed(1)}`)
        .join(" ");
    const areaDD = `${pDD} L${xOf(N - 1).toFixed(1)},${ddT} L${xOf(0).toFixed(1)},${ddT} Z`;

    const monthMarkers = useMemo(() => {
        const out = [];
        let lastYm = "";
        chartData.series.forEach((s, i) => {
            const ym = s.date.slice(0, 7);
            if (ym !== lastYm) {
                lastYm = ym;
                out.push({ i, x: xOf(i), label: `${MONTH_NAMES[ym.slice(5)]}/26` });
            }
        });
        return out;
    }, [chartData.series]);

    const handleMouseMove = (e) => {
        const svg = svgRef.current;
        if (!svg) return;
        const pt = svg.createSVGPoint();
        pt.x = e.clientX;
        pt.y = e.clientY;
        const loc = pt.matrixTransform(svg.getScreenCTM().inverse());
        const idx = Math.max(0, Math.min(N - 1, Math.round(((loc.x - padL) / plotW) * (N - 1))));
        setHoverIdx(idx);
    };

    const filteredDays = useMemo(() => {
        return days.filter((d) => {
            if (dailyFilter === "active") return d[1] > 0;
            if (dailyFilter === "win") return d[5] > 0;
            if (dailyFilter === "loss") return d[5] < 0;
            if (dailyFilter === "flat") return d[1] === 0;
            return true;
        });
    }, [days, dailyFilter]);

    const kpiCards = [
        {
            id: "port",
            title: "PORTFÓLIO CONSOLIDADO",
            badge: "RET/DD 17,1X",
            badgeBg: "rgba(16,185,129,0.14)",
            badgeColor: "#34d399",
            badgeBorder: "rgba(16,185,129,0.35)",
            topColor: "#10b981",
            valBrl: 10135,
            valPts: 25338,
            ddBrl: 592,
            ddPts: 1481,
            daysText: "163 / 212 (76,9%)",
            wWin: 38.7,
            wLoss: 38.2,
            wFlat: 23.1,
            posText: "82 Pos (50,3%)",
            negText: "81 Neg",
            flatText: "49 Sem Op",
            tradesTotal: "488 trades",
            tradesAvg: "2,99/dia op (2,30/pregão)",
        },
        {
            id: "cons",
            title: "1. CONSENSO (WDO+DI)",
            badge: "RET/DD 13,6X",
            badgeBg: "rgba(56,189,248,0.14)",
            badgeColor: "#38bdf8",
            badgeBorder: "rgba(56,189,248,0.35)",
            topColor: "#38bdf8",
            valBrl: 4277,
            valPts: 10693,
            ddBrl: 313,
            ddPts: 783,
            daysText: "103 / 212 (48,6%)",
            wWin: 30.7,
            wLoss: 17.9,
            wFlat: 51.4,
            posText: "65 Pos (63,1%)",
            negText: "38 Neg",
            flatText: "109 Sem Op",
            tradesTotal: "135 trades",
            tradesAvg: "1,31/dia op (0,64/pregão)",
        },
        {
            id: "di",
            title: "2. DI_NWE (ISOLADO)",
            badge: "RET/DD 5,5X",
            badgeBg: "#1e293b",
            badgeColor: "#e2e8f0",
            badgeBorder: "#334155",
            topColor: "#a855f7",
            valBrl: 3252,
            valPts: 8131,
            ddBrl: 592,
            ddPts: 1481,
            daysText: "152 / 212 (71,7%)",
            wWin: 37.3,
            wLoss: 34.4,
            wFlat: 28.3,
            posText: "79 Pos (52,0%)",
            negText: "73 Neg",
            flatText: "60 Sem Op",
            tradesTotal: "204 trades",
            tradesAvg: "1,34/dia op (0,96/pregão)",
        },
        {
            id: "wdo",
            title: "3. WDO_NWE (ISOLADO)",
            badge: "RET/DD 6,8X",
            badgeBg: "#1e293b",
            badgeColor: "#e2e8f0",
            badgeBorder: "#334155",
            topColor: "#f59e0b",
            valBrl: 2606,
            valPts: 6515,
            ddBrl: 384,
            ddPts: 960,
            daysText: "110 / 212 (51,9%)",
            wWin: 29.7,
            wLoss: 22.2,
            wFlat: 48.1,
            posText: "63 Pos (57,3%)",
            negText: "47 Neg",
            flatText: "102 Sem Op",
            tradesTotal: "149 trades",
            tradesAvg: "1,35/dia op (0,70/pregão)",
        },
    ];

    const hoveredDay = hoverIdx !== null ? chartData.series[hoverIdx] : null;

    return (
        <div style={{
            background: "#0b0f19",
            border: "1px solid #1e293b",
            borderRadius: 12,
            padding: 16,
            color: "#f8fafc",
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif',
        }}>
            {/* Header */}
            <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                gap: 12,
                flexWrap: "wrap",
                marginBottom: 14,
                paddingBottom: 12,
                borderBottom: "1px solid #1e293b",
            }}>
                <div>
                    <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.01em", color: "#f8fafc" }}>
                        📈 Curvas de Capital, Dias Operados & Correlação — Histórico Completo 2026 (212 Pregões)
                    </div>
                    <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 3 }}>
                        Dados 100% Reais do Profit (WINFUT + WDOFUT + DI1FUT • 119.019 Barras M1 OHLC Fechadas Auditadas) • 02/01/2026 a 06/11/2026 • GEX Walls (SL/TP ≥ 200 pts, RR ≥ 1.4, BE +150→+15) • 2 Contratos WIN
                    </div>
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <span style={{
                        fontSize: 11, fontWeight: 700, padding: "4px 9px", borderRadius: 6,
                        background: "rgba(16,185,129,0.14)", color: "#34d399", border: "1px solid rgba(16,185,129,0.35)",
                    }}>
                        ✓ Auditado em 119.019 Barras M1 OHLC
                    </span>
                    <span style={{
                        fontSize: 11, fontWeight: 700, padding: "4px 9px", borderRadius: 6,
                        background: "rgba(16,185,129,0.14)", color: "#34d399", border: "1px solid rgba(16,185,129,0.35)",
                    }}>
                        10 de 11 Meses Positivos
                    </span>
                    <span style={{
                        fontSize: 11, fontWeight: 700, padding: "4px 9px", borderRadius: 6,
                        background: "rgba(56,189,248,0.14)", color: "#38bdf8", border: "1px solid rgba(56,189,248,0.35)",
                    }}>
                        Operou em 163 / 212 Pregões (76,9%)
                    </span>
                </div>
            </div>

            {/* 4 KPI Cards */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: 10,
                marginBottom: 14,
            }}>
                {kpiCards.map((c) => (
                    <div key={c.id} style={{
                        background: "#111827",
                        border: "1px solid #1e293b",
                        borderRadius: 10,
                        padding: 12,
                        position: "relative",
                        overflow: "hidden",
                    }}>
                        <div style={{
                            position: "absolute", top: 0, left: 0, right: 0, height: 3, background: c.topColor,
                        }} />
                        <div style={{
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                            fontSize: 11, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6,
                        }}>
                            <span style={{ color: c.topColor }}>{c.title}</span>
                            <span style={{
                                fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 6,
                                background: c.badgeBg, color: c.badgeColor, border: `1px solid ${c.badgeBorder}`,
                            }}>
                                {c.badge}
                            </span>
                        </div>
                        <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em", color: c.topColor }}>
                            {unit === "brl"
                                ? `+R$ ${c.valBrl.toLocaleString("pt-BR")}`
                                : `+${c.valPts.toLocaleString("pt-BR")} pts`}
                        </div>
                        <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 2 }}>
                            {unit === "brl"
                                ? `+${c.valPts.toLocaleString("pt-BR")} pts • Max DD: R$ ${c.ddBrl.toLocaleString("pt-BR")} (${c.ddPts.toLocaleString("pt-BR")} pts)`
                                : `+R$ ${c.valBrl.toLocaleString("pt-BR")} • Max DD: ${c.ddPts.toLocaleString("pt-BR")} pts (R$ ${c.ddBrl.toLocaleString("pt-BR")})`}
                        </div>
                        <div style={{
                            marginTop: 9, paddingTop: 8, borderTop: "1px dashed #263248", fontSize: 11.5,
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                <span>📅 <b>Dias Operados:</b></span>
                                <span style={{ color: "#f8fafc", fontWeight: 800 }}>{c.daysText}</span>
                            </div>
                            <div style={{
                                height: 6, background: "#1e293b", borderRadius: 999, overflow: "hidden", display: "flex", margin: "5px 0",
                            }}>
                                <div style={{ width: `${c.wWin}%`, background: "#10b981", height: "100%" }} />
                                <div style={{ width: `${c.wLoss}%`, background: "#f43f5e", height: "100%" }} />
                                <div style={{ width: `${c.wFlat}%`, background: "#334155", height: "100%" }} />
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "#94a3b8" }}>
                                <span>🟢 {c.posText}</span>
                                <span>🔴 {c.negText}</span>
                                <span>⚪ {c.flatText}</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "#cbd5e1", marginTop: 3 }}>
                                <span>Total: <b>{c.tradesTotal}</b></span>
                                <span><b>{c.tradesAvg}</b></span>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Sub-Tabs & Unit Toggle */}
            <div style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                gap: 8, flexWrap: "wrap", marginBottom: 12,
            }}>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {[
                        { id: "chart", label: "📈 4 Curvas de Capital & Drawdown" },
                        { id: "corr", label: "🔗 Matriz de Correlação & Hedge" },
                        { id: "monthly", label: "📊 Resultado Mensal & Dias Operados (Jan–Nov)" },
                        { id: "daily", label: "📅 Histórico dos 212 Pregões" },
                    ].map((t) => {
                        const isAct = activeTab === t.id;
                        return (
                            <button
                                key={t.id}
                                onClick={() => setActiveTab(t.id)}
                                style={{
                                    background: isAct ? "#1e293b" : "#111827",
                                    color: isAct ? "#38bdf8" : "#94a3b8",
                                    border: `1px solid ${isAct ? "#38bdf8" : "#1e293b"}`,
                                    padding: "7px 13px",
                                    borderRadius: 8,
                                    fontSize: 12,
                                    fontWeight: 700,
                                    cursor: "pointer",
                                }}
                            >
                                {t.label}
                            </button>
                        );
                    })}
                </div>
                <div style={{
                    display: "flex", gap: 4, background: "#111827", padding: 3, borderRadius: 8, border: "1px solid #1e293b",
                }}>
                    <button
                        onClick={() => setUnit("brl")}
                        style={{
                            background: unit === "brl" ? "#38bdf8" : "transparent",
                            color: unit === "brl" ? "#0b0f19" : "#94a3b8",
                            border: "none", padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: "pointer",
                        }}
                    >
                        R$ (2 Contratos)
                    </button>
                    <button
                        onClick={() => setUnit("pts")}
                        style={{
                            background: unit === "pts" ? "#38bdf8" : "transparent",
                            color: unit === "pts" ? "#0b0f19" : "#94a3b8",
                            border: "none", padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: "pointer",
                        }}
                    >
                        Pontos (WIN)
                    </button>
                </div>
            </div>

            {/* TAB 1: EQUITY CURVES */}
            {activeTab === "chart" && (
                <div style={{ background: "#111827", border: "1px solid #1e293b", borderRadius: 10, padding: 14 }}>
                    <div style={{
                        display: "flex", justifyContent: "space-between", alignItems: "center",
                        flexWrap: "wrap", gap: 8, marginBottom: 10,
                    }}>
                        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12, fontWeight: 600 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ width: 12, height: 4, borderRadius: 2, background: "#10b981", display: "inline-block" }} />
                                Portfólio Consolidado (163 dias op)
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ width: 12, height: 4, borderRadius: 2, background: "#38bdf8", display: "inline-block" }} />
                                CONSENSO WDO+DI (103 dias op)
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ width: 12, height: 4, borderRadius: 2, background: "#a855f7", display: "inline-block" }} />
                                DI_NWE Isolado (152 dias op)
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ width: 12, height: 4, borderRadius: 2, background: "#f59e0b", display: "inline-block" }} />
                                WDO_NWE Isolado (110 dias op)
                            </div>
                        </div>

                        <div style={{
                            fontSize: 11.5, color: "#cbd5e1", background: "#161f33",
                            padding: "5px 10px", borderRadius: 6, border: "1px solid #263248",
                            minHeight: 28, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
                        }}>
                            {hoveredDay ? (
                                <>
                                    <b>📅 {hoveredDay.date.split("-").reverse().join("/")}</b>
                                    <span style={{ color: "#94a3b8" }}>(#{hoverIdx + 1}/212)</span>
                                    {hoveredDay.raw[1] === 0 ? (
                                        <span style={{ color: "#94a3b8" }}>⚪ Sem Operação</span>
                                    ) : hoveredDay.raw[5] > 0 ? (
                                        <span style={{ color: "#34d399", fontWeight: 700 }}>🟢 Dia Positivo ({hoveredDay.raw[1]} trades)</span>
                                    ) : (
                                        <span style={{ color: "#fb7185", fontWeight: 700 }}>🔴 Dia Negativo ({hoveredDay.raw[1]} trades)</span>
                                    )}
                                    <span>• <b>Dia:</b> <span style={{ color: hoveredDay.raw[5] >= 0 ? "#34d399" : "#fb7185", fontWeight: 700 }}>{fmt(hoveredDay.raw[5])}</span></span>
                                    <span>• <b style={{ color: "#10b981" }}>Acum Portfólio: {fmt(hoveredDay.raw[6])}</b></span>
                                    <span style={{ color: "#38bdf8" }}>Cons: {fmt(hoveredDay.cumC / mult)}</span>
                                    <span style={{ color: "#a855f7" }}>DI: {fmt(hoveredDay.cumD / mult)}</span>
                                    <span style={{ color: "#f59e0b" }}>WDO: {fmt(hoveredDay.cumW / mult)}</span>
                                </>
                            ) : (
                                <span>Passe o mouse sobre o gráfico para inspecionar cada um dos 212 pregões (clique para abrir o pregão no gráfico acima).</span>
                            )}
                        </div>
                    </div>

                    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
                        {/* Grid lines Equity */}
                        {[0, 1, 2, 3, 4].map((k) => {
                            const val = chartData.minEq + (k / 4) * (chartData.maxEq - chartData.minEq);
                            const y = yOfEq(val);
                            const lbl = unit === "brl" ? `R$ ${Math.round(val).toLocaleString("pt-BR")}` : Math.round(val).toLocaleString("pt-BR");
                            return (
                                <g key={k}>
                                    <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="#1e293b" strokeDasharray="3,3" />
                                    <text x={padL - 8} y={y + 4} fill="#94a3b8" fontSize="10" textAnchor="end">{lbl}</text>
                                </g>
                            );
                        })}

                        {/* Grid lines DD */}
                        <line x1={padL} y1={ddT} x2={W - padR} y2={ddT} stroke="#334155" />
                        <line x1={padL} y1={ddT + ddH} x2={W - padR} y2={ddT + ddH} stroke="#1e293b" strokeDasharray="3,3" />
                        <text x={padL - 8} y={ddT + 8} fill="#94a3b8" fontSize="9.5" textAnchor="end">DD 0</text>
                        <text x={padL - 8} y={ddT + ddH} fill="#fb7185" fontSize="9.5" textAnchor="end">
                            {unit === "brl" ? `R$ ${Math.round(chartData.minDD).toLocaleString("pt-BR")}` : Math.round(chartData.minDD).toLocaleString("pt-BR")}
                        </text>

                        {/* Month lines */}
                        {monthMarkers.map((m) => (
                            <g key={m.label}>
                                <line x1={m.x} y1={padT} x2={m.x} y2={ddT + ddH} stroke="#1e293b" strokeWidth="1" />
                                <text x={m.x + 4} y={H - 8} fill="#94a3b8" fontSize="10" fontWeight="600">{m.label}</text>
                            </g>
                        ))}

                        {/* Equity paths */}
                        <path d={areaTot} fill="rgba(16,185,129,0.10)" />
                        <path d={pW} fill="none" stroke="#f59e0b" strokeWidth="1.8" />
                        <path d={pD} fill="none" stroke="#a855f7" strokeWidth="1.8" />
                        <path d={pC} fill="none" stroke="#38bdf8" strokeWidth="2.2" />
                        <path d={pTot} fill="none" stroke="#10b981" strokeWidth="2.8" />

                        {/* Drawdown path */}
                        <path d={areaDD} fill="rgba(244,63,94,0.22)" />
                        <path d={pDD} fill="none" stroke="#f43f5e" strokeWidth="1.5" />

                        {/* Active day dots */}
                        {chartData.series.map((s, i) => {
                            const col = s.nT === 0 ? "#334155" : s.totDay > 0 ? "#10b981" : "#f43f5e";
                            return <circle key={s.date} cx={xOf(i)} cy={padT + eqH + 8} r="1.9" fill={col} />;
                        })}

                        {/* Crosshair */}
                        {hoverIdx !== null && (
                            <line
                                x1={xOf(hoverIdx)}
                                y1={padT}
                                x2={xOf(hoverIdx)}
                                y2={ddT + ddH}
                                stroke="#e2e8f0"
                                strokeWidth="1"
                                strokeDasharray="2,2"
                            />
                        )}

                        <rect
                            x={padL}
                            y={padT}
                            width={plotW}
                            height={ddT + ddH - padT}
                            fill="transparent"
                            style={{ cursor: "crosshair" }}
                            onMouseMove={handleMouseMove}
                            onMouseLeave={() => setHoverIdx(null)}
                            onClick={() => {
                                if (hoverIdx !== null && onSelectDate) {
                                    onSelectDate(chartData.series[hoverIdx].date);
                                }
                            }}
                        />
                    </svg>
                </div>
            )}

            {/* TAB 2: CORRELATION MATRICES & HEDGE */}
            {activeTab === "corr" && (
                <div style={{ background: "#111827", border: "1px solid #1e293b", borderRadius: 10, padding: 14 }}>
                    <div style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(270px, 1fr))",
                        gap: 12,
                        marginBottom: 12,
                    }}>
                        {/* Matrix 1: Daily PnL */}
                        <div style={{ background: "#161f33", border: "1px solid #1e293b", borderRadius: 8, padding: 12 }}>
                            <div style={{ fontSize: 12, fontWeight: 800, color: "#38bdf8", marginBottom: 4 }}>
                                1. Correlação Diária de PnL (212 Pregões)
                            </div>
                            <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8 }}>
                                Correlação de Pearson do resultado financeiro dia a dia
                            </div>
                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                                <thead>
                                    <tr style={{ borderBottom: "1px solid #263248", color: "#cbd5e1" }}>
                                        <th style={{ textAlign: "left", padding: "6px 8px" }}>Estratégia</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>CONS</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>WDO</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>DI</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>PORT</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr style={{ borderBottom: "1px solid #192234" }}>
                                        <td style={{ padding: "6px 8px", color: "#38bdf8", fontWeight: 700 }}>CONSENSO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,74</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,59</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,91</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid #192234" }}>
                                        <td style={{ padding: "6px 8px", color: "#f59e0b", fontWeight: 700 }}>WDO_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,74</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(16,185,129,0.18)", color: "#34d399", fontWeight: 800 }}>+0,35</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,80</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid #192234" }}>
                                        <td style={{ padding: "6px 8px", color: "#a855f7", fontWeight: 700 }}>DI_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,59</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(16,185,129,0.18)", color: "#34d399", fontWeight: 800 }}>+0,35</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,81</td>
                                    </tr>
                                    <tr>
                                        <td style={{ padding: "6px 8px", color: "#10b981", fontWeight: 700 }}>PORTFÓLIO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,91</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,80</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,81</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>

                        {/* Matrix 2: Monthly PnL */}
                        <div style={{ background: "#161f33", border: "1px solid #1e293b", borderRadius: 8, padding: 12 }}>
                            <div style={{ fontSize: 12, fontWeight: 800, color: "#34d399", marginBottom: 4 }}>
                                2. Correlação Mensal (Jan–Nov/2026)
                            </div>
                            <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8 }}>
                                WDO e DI têm correlação mensal <b>levemente negativa (-0,05)</b>
                            </div>
                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                                <thead>
                                    <tr style={{ borderBottom: "1px solid #263248", color: "#cbd5e1" }}>
                                        <th style={{ textAlign: "left", padding: "6px 8px" }}>Estratégia</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>CONS</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>WDO</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>DI</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>PORT</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr style={{ borderBottom: "1px solid #192234" }}>
                                        <td style={{ padding: "6px 8px", color: "#38bdf8", fontWeight: 700 }}>CONSENSO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,77</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,36</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,92</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid #192234" }}>
                                        <td style={{ padding: "6px 8px", color: "#f59e0b", fontWeight: 700 }}>WDO_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,77</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(16,185,129,0.25)", color: "#34d399", fontWeight: 800 }}>-0,05</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,70</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid #192234" }}>
                                        <td style={{ padding: "6px 8px", color: "#a855f7", fontWeight: 700 }}>DI_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,36</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(16,185,129,0.25)", color: "#34d399", fontWeight: 800 }}>-0,05</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                    </tr>
                                    <tr>
                                        <td style={{ padding: "6px 8px", color: "#10b981", fontWeight: 700 }}>PORTFÓLIO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,92</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,70</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>

                        {/* Matrix 3: Drawdown Curve Correlation */}
                        <div style={{ background: "#161f33", border: "1px solid #1e293b", borderRadius: 8, padding: 12 }}>
                            <div style={{ fontSize: 12, fontWeight: 800, color: "#a855f7", marginBottom: 4 }}>
                                3. Correlação de Drawdown (Underwater)
                            </div>
                            <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8 }}>
                                Drawdowns do WDO e DI são <b>descorrelacionados (-0,10)</b>
                            </div>
                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                                <thead>
                                    <tr style={{ borderBottom: "1px solid #263248", color: "#cbd5e1" }}>
                                        <th style={{ textAlign: "left", padding: "6px 8px" }}>Estratégia</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>CONS</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>WDO</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>DI</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px" }}>PORT</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr style={{ borderBottom: "1px solid #192234" }}>
                                        <td style={{ padding: "6px 8px", color: "#38bdf8", fontWeight: 700 }}>CONSENSO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", color: "#34d399", fontWeight: 700 }}>+0,22</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid #192234" }}>
                                        <td style={{ padding: "6px 8px", color: "#f59e0b", fontWeight: 700 }}>WDO_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(16,185,129,0.25)", color: "#34d399", fontWeight: 800 }}>-0,10</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,41</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid #192234" }}>
                                        <td style={{ padding: "6px 8px", color: "#a855f7", fontWeight: 700 }}>DI_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", color: "#34d399", fontWeight: 700 }}>+0,22</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(16,185,129,0.25)", color: "#34d399", fontWeight: 800 }}>-0,10</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,69</td>
                                    </tr>
                                    <tr>
                                        <td style={{ padding: "6px 8px", color: "#10b981", fontWeight: 700 }}>PORTFÓLIO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,41</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,69</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Overlap & Natural Hedge */}
                    <div style={{ background: "#161f33", border: "1px solid #1e293b", borderRadius: 8, padding: 12, fontSize: 12 }}>
                        <div style={{ fontWeight: 800, color: "#f8fafc", marginBottom: 8 }}>
                            🛡️ Dinâmica de Sobreposição, Hedge Natural & Correlação M5 nos 212 Pregões (WDO_NWE vs. DI_NWE)
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10 }}>
                            <div style={{ background: "#111827", padding: 10, borderRadius: 6, border: "1px solid #1e293b" }}>
                                <div style={{ color: "#94a3b8", fontSize: 11 }}>Operaram Sozinhas (Desacopladas)</div>
                                <div style={{ fontSize: 16, fontWeight: 800, color: "#38bdf8", marginTop: 2 }}>64 pregões (39,3%)</div>
                                <div style={{ fontSize: 11, color: "#cbd5e1", marginTop: 2 }}>53 dias só DI operou • 11 dias só WDO operou</div>
                            </div>
                            <div style={{ background: "#111827", padding: 10, borderRadius: 6, border: "1px solid #1e293b" }}>
                                <div style={{ color: "#94a3b8", fontSize: 11 }}>Ambas Operaram & Ambas Ganharam</div>
                                <div style={{ fontSize: 16, fontWeight: 800, color: "#34d399", marginTop: 2 }}>37 pregões (37,4%)</div>
                                <div style={{ fontSize: 11, color: "#cbd5e1", marginTop: 2 }}>Nos 37 dias, as 3 estratégias ganharam juntas</div>
                            </div>
                            <div style={{ background: "#111827", padding: 10, borderRadius: 6, border: "1px solid #1e293b" }}>
                                <div style={{ color: "#94a3b8", fontSize: 11 }}>Hedge Natural (1 Ganha / 1 Perde)</div>
                                <div style={{ fontSize: 16, fontWeight: 800, color: "#f59e0b", marginTop: 2 }}>35 pregões (35,4%)</div>
                                <div style={{ fontSize: 11, color: "#cbd5e1", marginTop: 2 }}>O ganho de uma ponta amortiza o stop da outra</div>
                            </div>
                            <div style={{ background: "#111827", padding: 10, borderRadius: 6, border: "1px solid #1e293b" }}>
                                <div style={{ color: "#94a3b8", fontSize: 11 }}>Correlação M5 Z-Spread (22.320 barras)</div>
                                <div style={{ fontSize: 16, fontWeight: 800, color: "#a855f7", marginTop: 2 }}>r = +0,572 (2,56% Extremo)</div>
                                <div style={{ fontSize: 11, color: "#cbd5e1", marginTop: 2 }}>Gatilho simultâneo do Consenso em só 2,56% das barras</div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* TAB 3: MONTHLY BREAKDOWN */}
            {activeTab === "monthly" && (
                <div style={{ background: "#111827", border: "1px solid #1e293b", borderRadius: 10, padding: 14 }}>
                    <div style={{ maxHeight: 430, overflowY: "auto", border: "1px solid #1e293b", borderRadius: 8 }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                            <thead>
                                <tr style={{ background: "#161f33", color: "#cbd5e1", borderBottom: "1px solid #263248" }}>
                                    <th style={{ textAlign: "left", padding: "9px 10px" }}>Mês (2026)</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px" }}>Pregões</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px" }}>Dias Operados (%)</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px" }}>Dias Positivos</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px" }}>Sem Operar</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px" }}>Trades</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px", color: "#38bdf8" }}>CONSENSO</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px", color: "#f59e0b" }}>WDO_NWE</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px", color: "#a855f7" }}>DI_NWE</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px", color: "#10b981" }}>Portfólio Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                {monthly.map((m) => {
                                    const [ym, dTot, dAct, dPos, nTr, pC, pW, pD, , pBrl] = m;
                                    const dFlat = dTot - dAct;
                                    const pctAct = `${((dAct / dTot) * 100).toFixed(0)}%`;
                                    return (
                                        <tr key={ym} style={{ borderBottom: "1px solid #192234" }}>
                                            <td style={{ padding: "7px 10px", fontWeight: 700 }}>{ym}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px" }}>{dTot}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px" }}>
                                                <b>{dAct}</b> de {dTot} <span style={{ color: "#94a3b8" }}>({pctAct})</span>
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: "#34d399", fontWeight: 700 }}>{dPos} dias</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: "#64748b" }}>{dFlat} dias</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px" }}>{nTr}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: pC >= 0 ? "#34d399" : "#fb7185", fontWeight: 700 }}>{fmt(pC * 0.4)}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: pW >= 0 ? "#34d399" : "#fb7185", fontWeight: 700 }}>{fmt(pW * 0.4)}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: pD >= 0 ? "#34d399" : "#fb7185", fontWeight: 700 }}>{fmt(pD * 0.4)}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: pBrl >= 0 ? "#34d399" : "#fb7185", fontWeight: 800 }}>{fmt(pBrl)}</td>
                                        </tr>
                                    );
                                })}
                                <tr style={{ background: "#161f33", fontWeight: 800, borderTop: "2px solid #334155" }}>
                                    <td style={{ padding: "9px 10px" }}>TOTAL 2026</td>
                                    <td style={{ textAlign: "right", padding: "9px 10px" }}>212</td>
                                    <td style={{ textAlign: "right", padding: "9px 10px", color: "#38bdf8" }}>163 de 212 (76,9%)</td>
                                    <td style={{ textAlign: "right", padding: "9px 10px", color: "#34d399" }}>82 dias (50,3%)</td>
                                    <td style={{ textAlign: "right", padding: "9px 10px", color: "#64748b" }}>49 dias (23,1%)</td>
                                    <td style={{ textAlign: "right", padding: "9px 10px" }}>488</td>
                                    <td style={{ textAlign: "right", padding: "9px 10px", color: "#34d399" }}>{fmt(4277)}</td>
                                    <td style={{ textAlign: "right", padding: "9px 10px", color: "#34d399" }}>{fmt(2606)}</td>
                                    <td style={{ textAlign: "right", padding: "9px 10px", color: "#34d399" }}>{fmt(3252)}</td>
                                    <td style={{ textAlign: "right", padding: "9px 10px", color: "#34d399" }}>{fmt(10135)}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* TAB 4: DAILY 212 SESSIONS */}
            {activeTab === "daily" && (
                <div style={{ background: "#111827", border: "1px solid #1e293b", borderRadius: 10, padding: 14 }}>
                    <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
                        {[
                            { id: "all", label: "Todos os Pregões (212)" },
                            { id: "active", label: "Dias Operados (163)" },
                            { id: "win", label: "Dias Positivos (82)" },
                            { id: "loss", label: "Dias Negativos (81)" },
                            { id: "flat", label: "Dias Sem Operação (49)" },
                        ].map((f) => {
                            const isAct = dailyFilter === f.id;
                            return (
                                <button
                                    key={f.id}
                                    onClick={() => setDailyFilter(f.id)}
                                    style={{
                                        background: isAct ? "rgba(56,189,248,0.16)" : "#161f33",
                                        color: isAct ? "#38bdf8" : "#94a3b8",
                                        border: `1px solid ${isAct ? "#38bdf8" : "#1e293b"}`,
                                        padding: "5px 10px",
                                        borderRadius: 6,
                                        fontSize: 11,
                                        fontWeight: 700,
                                        cursor: "pointer",
                                    }}
                                >
                                    {f.label}
                                </button>
                            );
                        })}
                    </div>

                    <div style={{ maxHeight: 430, overflowY: "auto", border: "1px solid #1e293b", borderRadius: 8 }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                            <thead>
                                <tr style={{ background: "#161f33", color: "#cbd5e1", borderBottom: "1px solid #263248", position: "sticky", top: 0 }}>
                                    <th style={{ textAlign: "left", padding: "9px 10px" }}>Data</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px" }}>Status</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px" }}>Trades (C / W / D)</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px", color: "#38bdf8" }}>CONSENSO</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px", color: "#f59e0b" }}>WDO_NWE</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px", color: "#a855f7" }}>DI_NWE</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px" }}>Resultado Dia</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px", color: "#10b981" }}>Acumulado Portfólio</th>
                                    <th style={{ textAlign: "right", padding: "9px 10px", color: "#f43f5e" }}>Drawdown</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredDays.map((d) => {
                                    const [dt, nT, bC, bW, bD, bTot, bCum, bDD, tC, tW, tD] = d;
                                    return (
                                        <tr
                                            key={dt}
                                            onClick={() => onSelectDate && onSelectDate(dt)}
                                            style={{ borderBottom: "1px solid #192234", cursor: onSelectDate ? "pointer" : "default" }}
                                            title={onSelectDate ? `Clique para visualizar o pregão ${dt.split("-").reverse().join("/")}` : ""}
                                        >
                                            <td style={{ padding: "7px 10px", fontWeight: 700, color: "#38bdf8" }}>
                                                {dt.split("-").reverse().join("/")}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px" }}>
                                                {nT === 0 ? (
                                                    <span style={{ color: "#64748b" }}>⚪ Sem Operar</span>
                                                ) : bTot > 0 ? (
                                                    <span style={{ color: "#34d399", fontWeight: 700 }}>🟢 Positivo</span>
                                                ) : (
                                                    <span style={{ color: "#fb7185", fontWeight: 700 }}>🔴 Negativo</span>
                                                )}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px" }}>
                                                {nT} <span style={{ color: "#64748b", fontSize: 11 }}>({tC}/{tW}/{tD})</span>
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: bC > 0 ? "#34d399" : bC < 0 ? "#fb7185" : "#64748b", fontWeight: bC !== 0 ? 700 : 400 }}>
                                                {bC === 0 ? "—" : fmt(bC)}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: bW > 0 ? "#34d399" : bW < 0 ? "#fb7185" : "#64748b", fontWeight: bW !== 0 ? 700 : 400 }}>
                                                {bW === 0 ? "—" : fmt(bW)}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: bD > 0 ? "#34d399" : bD < 0 ? "#fb7185" : "#64748b", fontWeight: bD !== 0 ? 700 : 400 }}>
                                                {bD === 0 ? "—" : fmt(bD)}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: bTot > 0 ? "#34d399" : bTot < 0 ? "#fb7185" : "#64748b", fontWeight: nT > 0 ? 700 : 400 }}>
                                                {nT === 0 ? "—" : fmt(bTot)}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: "#34d399", fontWeight: 700 }}>
                                                {fmt(bCum)}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: bDD < 0 ? "#fb7185" : "#64748b", fontWeight: bDD < 0 ? 700 : 400 }}>
                                                {bDD === 0 ? "0" : fmt(bDD)}
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
