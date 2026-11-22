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
        <div className="mw-card" style={{
            padding: "16px 18px",
            color: "var(--mw-text-1)",
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
                borderBottom: "1px solid var(--mw-hairline)",
            }}>
                <div>
                    <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.01em", color: "var(--mw-text-1)" }}>
                        Curvas de capital, dias operados e correlação — Histórico 2026 (212 pregões)
                    </div>
                    <div className="mw-mono" style={{ fontSize: 11.5, color: "var(--mw-text-3)", marginTop: 4 }}>
                        Dados Profit (WINFUT + WDOFUT + DI1FUT · 119.019 barras M1 OHLC auditadas) · 02/01/2026 a 06/11/2026 · GEX Walls · 2 contratos WIN
                    </div>
                </div>
                <div className="mw-mono" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <span style={{
                        fontSize: 11, fontWeight: 500, padding: "3px 9px", borderRadius: 6,
                        background: "rgba(76, 195, 138, 0.08)", color: "#4cc38a", border: "1px solid rgba(76, 195, 138, 0.25)",
                    }}>
                        Auditado em 119.019 barras M1
                    </span>
                    <span style={{
                        fontSize: 11, fontWeight: 500, padding: "3px 9px", borderRadius: 6,
                        background: "rgba(76, 195, 138, 0.08)", color: "#4cc38a", border: "1px solid rgba(76, 195, 138, 0.25)",
                    }}>
                        10/11 meses positivos
                    </span>
                    <span style={{
                        fontSize: 11, fontWeight: 500, padding: "3px 9px", borderRadius: 6,
                        background: "var(--mw-accent-soft)", color: "var(--mw-accent-ink)", border: "1px solid var(--mw-accent-border)",
                    }}>
                        Operou em 163/212 pregões (76,9%)
                    </span>
                </div>
            </div>

            {/* 4 KPI Cards */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
                gap: 10,
                marginBottom: 14,
            }}>
                {kpiCards.map((c) => (
                    <div key={c.id} style={{
                        background: "var(--mw-chrome)",
                        border: "1px solid var(--mw-hairline)",
                        borderLeft: `2px solid ${c.topColor}`,
                        borderRadius: 8,
                        padding: "12px 14px",
                        position: "relative",
                        overflow: "hidden",
                    }}>
                        <div style={{
                            display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6,
                            fontSize: 11.5, fontWeight: 600, marginBottom: 6,
                        }}>
                            <span style={{ color: c.topColor }}>{c.title}</span>
                            <span className="mw-mono" style={{
                                fontSize: 10.5, fontWeight: 500, padding: "2px 7px", borderRadius: 5,
                                background: c.badgeBg, color: c.badgeColor, border: `1px solid ${c.badgeBorder}`,
                                whiteSpace: "nowrap",
                            }}>
                                {c.badge}
                            </span>
                        </div>
                        <div className="mw-mono" style={{ fontSize: 21, fontWeight: 600, letterSpacing: "-0.02em", color: "var(--mw-text-1)", whiteSpace: "nowrap" }}>
                            {unit === "brl"
                                ? `+R$ ${c.valBrl.toLocaleString("pt-BR")}`
                                : `+${c.valPts.toLocaleString("pt-BR")} pts`}
                        </div>
                        <div className="mw-mono" style={{ fontSize: 11, color: "var(--mw-text-3)", marginTop: 3 }}>
                            {unit === "brl"
                                ? `+${c.valPts.toLocaleString("pt-BR")} pts · Max DD R$ ${c.ddBrl.toLocaleString("pt-BR")} (${c.ddPts.toLocaleString("pt-BR")} pts)`
                                : `+R$ ${c.valBrl.toLocaleString("pt-BR")} · Max DD ${c.ddPts.toLocaleString("pt-BR")} pts (R$ ${c.ddBrl.toLocaleString("pt-BR")})`}
                        </div>
                        <div className="mw-mono" style={{
                            marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--mw-hairline)", fontSize: 11,
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 5 }}>
                                <span style={{ color: "var(--mw-text-2)", fontWeight: 500, whiteSpace: "nowrap" }}>Dias operados</span>
                                <span style={{ color: "var(--mw-text-1)", fontWeight: 600, whiteSpace: "nowrap" }}>{c.daysText}</span>
                            </div>
                            <div style={{
                                height: 5, background: "var(--mw-card)", borderRadius: 999, overflow: "hidden", display: "flex", margin: "5px 0",
                            }}>
                                <div style={{ width: `${c.wWin}%`, background: "#4cc38a", height: "100%" }} />
                                <div style={{ width: `${c.wLoss}%`, background: "#e5484d", height: "100%" }} />
                                <div style={{ width: `${c.wFlat}%`, background: "#2a3346", height: "100%" }} />
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "var(--mw-text-3)" }}>
                                <span style={{ color: "#4cc38a" }}>{c.posText}</span>
                                <span style={{ color: "#e5484d" }}>{c.negText}</span>
                                <span>{c.flatText}</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "var(--mw-text-2)", marginTop: 4 }}>
                                <span>Total: <strong style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{c.tradesTotal}</strong></span>
                                <span style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>{c.tradesAvg}</span>
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
                <div className="mw-track" style={{ flexWrap: "wrap" }}>
                    {[
                        { id: "chart", label: "4 curvas e drawdown" },
                        { id: "corr", label: "Correlação e hedge" },
                        { id: "monthly", label: "Mensal e dias operados" },
                        { id: "daily", label: "Histórico (212 pregões)" },
                    ].map((t) => (
                        <button
                            key={t.id}
                            type="button"
                            className="mw-btn"
                            data-active={activeTab === t.id ? "true" : "false"}
                            onClick={() => setActiveTab(t.id)}
                            style={{ height: 28, padding: "0 11px", fontSize: 12 }}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>
                <div className="mw-track">
                    <button
                        type="button"
                        className="mw-btn mw-mono"
                        data-active={unit === "brl" ? "true" : "false"}
                        onClick={() => setUnit("brl")}
                        style={{ height: 26, padding: "0 10px", fontSize: 11 }}
                    >
                        R$ (2 contratos)
                    </button>
                    <button
                        type="button"
                        className="mw-btn mw-mono"
                        data-active={unit === "pts" ? "true" : "false"}
                        onClick={() => setUnit("pts")}
                        style={{ height: 26, padding: "0 10px", fontSize: 11 }}
                    >
                        Pontos (WIN)
                    </button>
                </div>
            </div>

            {/* TAB 1: EQUITY CURVES */}
            {activeTab === "chart" && (
                <div style={{ background: "var(--mw-chrome)", border: "1px solid var(--mw-hairline)", borderRadius: 8, padding: 14 }}>
                    <div style={{
                        display: "flex", justifyContent: "space-between", alignItems: "center",
                        flexWrap: "wrap", gap: 8, marginBottom: 10,
                    }}>
                        <div className="mw-mono" style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11, color: "var(--mw-text-2)" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ width: 12, height: 3, borderRadius: 2, background: "#4cc38a", display: "inline-block" }} />
                                <strong style={{ color: "var(--mw-text-1)", fontWeight: 600 }}>Portfólio consolidado (163 dias op)</strong>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ width: 12, height: 3, borderRadius: 2, background: "#38bdf8", display: "inline-block" }} />
                                Consenso WDO+DI (103 dias op)
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ width: 12, height: 3, borderRadius: 2, background: "#a78bfa", display: "inline-block" }} />
                                DI_NWE isolado (152 dias op)
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ width: 12, height: 3, borderRadius: 2, background: "#d4a259", display: "inline-block" }} />
                                WDO_NWE isolado (110 dias op)
                            </div>
                        </div>

                        <div className="mw-mono" style={{
                            fontSize: 11, color: "var(--mw-text-2)", background: "var(--mw-card)",
                            padding: "6px 10px", borderRadius: 6, border: "1px solid var(--mw-hairline)",
                            minHeight: 28, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
                        }}>
                            {hoveredDay ? (
                                <>
                                    <strong style={{ color: "var(--mw-text-1)", fontWeight: 600 }}>{hoveredDay.date.split("-").reverse().join("/")}</strong>
                                    <span style={{ color: "var(--mw-text-3)" }}>(#{hoverIdx + 1}/212)</span>
                                    {hoveredDay.raw[1] === 0 ? (
                                        <span style={{ color: "var(--mw-text-3)" }}>Sem operação</span>
                                    ) : hoveredDay.raw[5] > 0 ? (
                                        <span style={{ color: "#4cc38a", fontWeight: 600 }}>Dia positivo ({hoveredDay.raw[1]} trades)</span>
                                    ) : (
                                        <span style={{ color: "#e5484d", fontWeight: 600 }}>Dia negativo ({hoveredDay.raw[1]} trades)</span>
                                    )}
                                    <span>· Dia: <strong style={{ color: hoveredDay.raw[5] >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 600 }}>{fmt(hoveredDay.raw[5])}</strong></span>
                                    <span>· <strong style={{ color: "#4cc38a", fontWeight: 600 }}>Acum: {fmt(hoveredDay.raw[6])}</strong></span>
                                    <span style={{ color: "#38bdf8" }}>Cons: {fmt(hoveredDay.cumC / mult)}</span>
                                    <span style={{ color: "#a78bfa" }}>DI: {fmt(hoveredDay.cumD / mult)}</span>
                                    <span style={{ color: "#d4a259" }}>WDO: {fmt(hoveredDay.cumW / mult)}</span>
                                </>
                            ) : (
                                <span style={{ color: "var(--mw-text-3)" }}>Passe o mouse sobre o gráfico para inspecionar cada um dos 212 pregões (clique para abrir no gráfico acima).</span>
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
                                    <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="#1b212e" strokeDasharray="3,3" />
                                    <text x={padL - 8} y={y + 4} fill="#848da2" fontSize="10" fontFamily="IBM Plex Mono, monospace" textAnchor="end">{lbl}</text>
                                </g>
                            );
                        })}

                        {/* Grid lines DD */}
                        <line x1={padL} y1={ddT} x2={W - padR} y2={ddT} stroke="#2a3346" />
                        <line x1={padL} y1={ddT + ddH} x2={W - padR} y2={ddT + ddH} stroke="#1b212e" strokeDasharray="3,3" />
                        <text x={padL - 8} y={ddT + 8} fill="#848da2" fontSize="9.5" fontFamily="IBM Plex Mono, monospace" textAnchor="end">DD 0</text>
                        <text x={padL - 8} y={ddT + ddH} fill="#e5484d" fontSize="9.5" fontFamily="IBM Plex Mono, monospace" textAnchor="end">
                            {unit === "brl" ? `R$ ${Math.round(chartData.minDD).toLocaleString("pt-BR")}` : Math.round(chartData.minDD).toLocaleString("pt-BR")}
                        </text>

                        {/* Month lines */}
                        {monthMarkers.map((m) => (
                            <g key={m.label}>
                                <line x1={m.x} y1={padT} x2={m.x} y2={ddT + ddH} stroke="#1b212e" strokeWidth="1" />
                                <text x={m.x + 4} y={H - 8} fill="#848da2" fontSize="10" fontFamily="IBM Plex Mono, monospace" fontWeight="500">{m.label}</text>
                            </g>
                        ))}

                        {/* Equity paths */}
                        <path d={areaTot} fill="rgba(76, 195, 138, 0.10)" />
                        <path d={pW} fill="none" stroke="#d4a259" strokeWidth="1.6" />
                        <path d={pD} fill="none" stroke="#a78bfa" strokeWidth="1.6" />
                        <path d={pC} fill="none" stroke="#38bdf8" strokeWidth="2.0" />
                        <path d={pTot} fill="none" stroke="#4cc38a" strokeWidth="2.5" />

                        {/* Drawdown path */}
                        <path d={areaDD} fill="rgba(229, 72, 77, 0.20)" />
                        <path d={pDD} fill="none" stroke="#e5484d" strokeWidth="1.4" />

                        {/* Active day dots */}
                        {chartData.series.map((s, i) => {
                            const col = s.nT === 0 ? "#2a3346" : s.totDay > 0 ? "#4cc38a" : "#e5484d";
                            return <circle key={s.date} cx={xOf(i)} cy={padT + eqH + 8} r="1.9" fill={col} />;
                        })}

                        {/* Crosshair */}
                        {hoverIdx !== null && (
                            <line
                                x1={xOf(hoverIdx)}
                                y1={padT}
                                x2={xOf(hoverIdx)}
                                y2={ddT + ddH}
                                stroke="#848da2"
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
                <div style={{ background: "var(--mw-chrome)", border: "1px solid var(--mw-hairline)", borderRadius: 8, padding: 14 }}>
                    <div style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(270px, 1fr))",
                        gap: 12,
                        marginBottom: 12,
                    }}>
                        {/* Matrix 1: Daily PnL */}
                        <div style={{ background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", borderRadius: 8, padding: 12 }}>
                            <div style={{ fontSize: 12, fontWeight: 600, color: "#38bdf8", marginBottom: 4 }}>
                                1. Correlação diária de PnL (212 pregões)
                            </div>
                            <div style={{ fontSize: 11, color: "var(--mw-text-3)", marginBottom: 8 }}>
                                Correlação de Pearson do resultado financeiro dia a dia
                            </div>
                            <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
                                <thead>
                                    <tr style={{ borderBottom: "1px solid var(--mw-hairline)", color: "var(--mw-text-3)" }}>
                                        <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 500 }}>Estratégia</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>CONS</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>WDO</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>DI</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>PORT</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                        <td style={{ padding: "6px 8px", color: "#38bdf8", fontWeight: 600 }}>CONSENSO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,74</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,59</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,91</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                        <td style={{ padding: "6px 8px", color: "#d4a259", fontWeight: 600 }}>WDO_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,74</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(76, 195, 138, 0.14)", color: "#4cc38a", fontWeight: 600 }}>+0,35</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,80</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                        <td style={{ padding: "6px 8px", color: "#a78bfa", fontWeight: 600 }}>DI_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,59</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(76, 195, 138, 0.14)", color: "#4cc38a", fontWeight: 600 }}>+0,35</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,81</td>
                                    </tr>
                                    <tr>
                                        <td style={{ padding: "6px 8px", color: "#4cc38a", fontWeight: 600 }}>PORTFÓLIO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,91</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,80</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,81</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>

                        {/* Matrix 2: Monthly PnL */}
                        <div style={{ background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", borderRadius: 8, padding: 12 }}>
                            <div style={{ fontSize: 12, fontWeight: 600, color: "#4cc38a", marginBottom: 4 }}>
                                2. Correlação mensal (Jan–Nov/2026)
                            </div>
                            <div style={{ fontSize: 11, color: "var(--mw-text-3)", marginBottom: 8 }}>
                                WDO e DI têm correlação mensal <strong style={{ color: "var(--mw-text-2)", fontWeight: 500 }}>levemente negativa (−0,05)</strong>
                            </div>
                            <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
                                <thead>
                                    <tr style={{ borderBottom: "1px solid var(--mw-hairline)", color: "var(--mw-text-3)" }}>
                                        <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 500 }}>Estratégia</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>CONS</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>WDO</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>DI</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>PORT</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                        <td style={{ padding: "6px 8px", color: "#38bdf8", fontWeight: 600 }}>CONSENSO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,77</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,36</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,92</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                        <td style={{ padding: "6px 8px", color: "#d4a259", fontWeight: 600 }}>WDO_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,77</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(76, 195, 138, 0.18)", color: "#4cc38a", fontWeight: 600 }}>−0,05</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,70</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                        <td style={{ padding: "6px 8px", color: "#a78bfa", fontWeight: 600 }}>DI_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,36</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(76, 195, 138, 0.18)", color: "#4cc38a", fontWeight: 600 }}>−0,05</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                    </tr>
                                    <tr>
                                        <td style={{ padding: "6px 8px", color: "#4cc38a", fontWeight: 600 }}>PORTFÓLIO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,92</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,70</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>

                        {/* Matrix 3: Drawdown Curve Correlation */}
                        <div style={{ background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", borderRadius: 8, padding: 12 }}>
                            <div style={{ fontSize: 12, fontWeight: 600, color: "#a78bfa", marginBottom: 4 }}>
                                3. Correlação de drawdown (subwater)
                            </div>
                            <div style={{ fontSize: 11, color: "var(--mw-text-3)", marginBottom: 8 }}>
                                Drawdowns do WDO e DI são <strong style={{ color: "var(--mw-text-2)", fontWeight: 500 }}>descorrelacionados (−0,10)</strong>
                            </div>
                            <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
                                <thead>
                                    <tr style={{ borderBottom: "1px solid var(--mw-hairline)", color: "var(--mw-text-3)" }}>
                                        <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 500 }}>Estratégia</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>CONS</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>WDO</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>DI</th>
                                        <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 500 }}>PORT</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                        <td style={{ padding: "6px 8px", color: "#38bdf8", fontWeight: 600 }}>CONSENSO</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", color: "#4cc38a", fontWeight: 500 }}>+0,22</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                        <td style={{ padding: "6px 8px", color: "#d4a259", fontWeight: 600 }}>WDO_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,65</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(76, 195, 138, 0.18)", color: "#4cc38a", fontWeight: 600 }}>−0,10</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,41</td>
                                    </tr>
                                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                        <td style={{ padding: "6px 8px", color: "#a78bfa", fontWeight: 600 }}>DI_NWE</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", color: "#4cc38a", fontWeight: 500 }}>+0,22</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px", background: "rgba(76, 195, 138, 0.18)", color: "#4cc38a", fontWeight: 600 }}>−0,10</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>1,00</td>
                                        <td style={{ textAlign: "right", padding: "6px 8px" }}>+0,69</td>
                                    </tr>
                                    <tr>
                                        <td style={{ padding: "6px 8px", color: "#4cc38a", fontWeight: 600 }}>PORTFÓLIO</td>
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
                    <div style={{ background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", borderRadius: 8, padding: 12, fontSize: 12 }}>
                        <div style={{ fontWeight: 600, color: "var(--mw-text-1)", marginBottom: 10 }}>
                            Dinâmica de sobreposição, hedge natural e correlação M5 nos 212 pregões (WDO_NWE vs. DI_NWE)
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 10 }}>
                            <div style={{ background: "var(--mw-chrome)", padding: 10, borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                                <div style={{ color: "var(--mw-text-3)", fontSize: 11 }}>Operaram sozinhas (desacopladas)</div>
                                <div className="mw-mono" style={{ fontSize: 15, fontWeight: 600, color: "#38bdf8", marginTop: 3 }}>64 pregões (39,3%)</div>
                                <div style={{ fontSize: 11, color: "var(--mw-text-2)", marginTop: 3 }}>53 dias só DI · 11 dias só WDO</div>
                            </div>
                            <div style={{ background: "var(--mw-chrome)", padding: 10, borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                                <div style={{ color: "var(--mw-text-3)", fontSize: 11 }}>Ambas operaram e ganharam</div>
                                <div className="mw-mono" style={{ fontSize: 15, fontWeight: 600, color: "#4cc38a", marginTop: 3 }}>37 pregões (37,4%)</div>
                                <div style={{ fontSize: 11, color: "var(--mw-text-2)", marginTop: 3 }}>Nos 37 dias, as 3 ganharam juntas</div>
                            </div>
                            <div style={{ background: "var(--mw-chrome)", padding: 10, borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                                <div style={{ color: "var(--mw-text-3)", fontSize: 11 }}>Hedge natural (1 ganha / 1 perde)</div>
                                <div className="mw-mono" style={{ fontSize: 15, fontWeight: 600, color: "#d4a259", marginTop: 3 }}>35 pregões (35,4%)</div>
                                <div style={{ fontSize: 11, color: "var(--mw-text-2)", marginTop: 3 }}>Ganho de uma ponta amortiza a outra</div>
                            </div>
                            <div style={{ background: "var(--mw-chrome)", padding: 10, borderRadius: 8, border: "1px solid var(--mw-hairline)" }}>
                                <div style={{ color: "var(--mw-text-3)", fontSize: 11 }}>Correlação M5 Z-Spread (22.320 barras)</div>
                                <div className="mw-mono" style={{ fontSize: 15, fontWeight: 600, color: "#a78bfa", marginTop: 3 }}>r = +0,572 (2,56%)</div>
                                <div style={{ fontSize: 11, color: "var(--mw-text-2)", marginTop: 3 }}>Gatilho simultâneo em 2,56% das barras</div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* TAB 3: MONTHLY BREAKDOWN */}
            {activeTab === "monthly" && (
                <div style={{ background: "var(--mw-chrome)", border: "1px solid var(--mw-hairline)", borderRadius: 8, padding: 14 }}>
                    <div style={{ maxHeight: 430, overflowY: "auto", overflowX: "auto", border: "1px solid var(--mw-hairline)", borderRadius: 8 }}>
                        <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
                            <thead>
                                <tr style={{ background: "var(--mw-card)", color: "var(--mw-text-3)", borderBottom: "1px solid var(--mw-hairline)" }}>
                                    <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 500 }}>Mês (2026)</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", fontWeight: 500 }}>Pregões</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", fontWeight: 500 }}>Dias operados</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", fontWeight: 500 }}>Positivos</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", fontWeight: 500 }}>Sem operar</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", fontWeight: 500 }}>Trades</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#38bdf8", fontWeight: 500 }}>CONSENSO</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#d4a259", fontWeight: 500 }}>WDO_NWE</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#a78bfa", fontWeight: 500 }}>DI_NWE</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#4cc38a", fontWeight: 600 }}>Portfólio</th>
                                </tr>
                            </thead>
                            <tbody>
                                {monthly.map((m) => {
                                    const [ym, dTot, dAct, dPos, nTr, pC, pW, pD, , pBrl] = m;
                                    const dFlat = dTot - dAct;
                                    const pctAct = `${((dAct / dTot) * 100).toFixed(0)}%`;
                                    return (
                                        <tr key={ym} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                            <td style={{ padding: "7px 10px", fontWeight: 600, color: "var(--mw-text-1)", whiteSpace: "nowrap" }}>{ym}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px" }}>{dTot}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", whiteSpace: "nowrap" }}>
                                                <strong style={{ fontWeight: 600 }}>{dAct}</strong>/{dTot} <span style={{ color: "var(--mw-text-3)" }}>({pctAct})</span>
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: "#4cc38a", fontWeight: 500, whiteSpace: "nowrap" }}>{dPos}d</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: "var(--mw-text-3)", whiteSpace: "nowrap" }}>{dFlat}d</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px" }}>{nTr}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: pC >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 500, whiteSpace: "nowrap" }}>{fmt(pC * 0.4)}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: pW >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 500, whiteSpace: "nowrap" }}>{fmt(pW * 0.4)}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: pD >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 500, whiteSpace: "nowrap" }}>{fmt(pD * 0.4)}</td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: pBrl >= 0 ? "#4cc38a" : "#e5484d", fontWeight: 600, whiteSpace: "nowrap" }}>{fmt(pBrl)}</td>
                                        </tr>
                                    );
                                })}
                                <tr style={{ background: "var(--mw-card)", fontWeight: 600, borderTop: "1px solid var(--mw-hairline-strong)" }}>
                                    <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>Total 2026</td>
                                    <td style={{ textAlign: "right", padding: "8px 10px" }}>212</td>
                                    <td style={{ textAlign: "right", padding: "8px 10px", color: "#38bdf8", whiteSpace: "nowrap" }}>163/212 (76,9%)</td>
                                    <td style={{ textAlign: "right", padding: "8px 10px", color: "#4cc38a", whiteSpace: "nowrap" }}>82d (50,3%)</td>
                                    <td style={{ textAlign: "right", padding: "8px 10px", color: "var(--mw-text-3)", whiteSpace: "nowrap" }}>49d (23,1%)</td>
                                    <td style={{ textAlign: "right", padding: "8px 10px" }}>488</td>
                                    <td style={{ textAlign: "right", padding: "8px 10px", color: "#4cc38a", whiteSpace: "nowrap" }}>{fmt(4277)}</td>
                                    <td style={{ textAlign: "right", padding: "8px 10px", color: "#4cc38a", whiteSpace: "nowrap" }}>{fmt(2606)}</td>
                                    <td style={{ textAlign: "right", padding: "8px 10px", color: "#4cc38a", whiteSpace: "nowrap" }}>{fmt(3252)}</td>
                                    <td style={{ textAlign: "right", padding: "8px 10px", color: "#4cc38a", whiteSpace: "nowrap" }}>{fmt(10135)}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* TAB 4: DAILY 212 SESSIONS */}
            {activeTab === "daily" && (
                <div style={{ background: "var(--mw-chrome)", border: "1px solid var(--mw-hairline)", borderRadius: 8, padding: 14 }}>
                    <div className="mw-track" style={{ marginBottom: 10, flexWrap: "wrap" }}>
                        {[
                            { id: "all", label: "Todos (212)" },
                            { id: "active", label: "Operados (163)" },
                            { id: "win", label: "Positivos (82)" },
                            { id: "loss", label: "Negativos (81)" },
                            { id: "flat", label: "Sem operação (49)" },
                        ].map((f) => (
                            <button
                                key={f.id}
                                type="button"
                                className="mw-btn mw-mono"
                                data-active={dailyFilter === f.id ? "true" : "false"}
                                onClick={() => setDailyFilter(f.id)}
                                style={{ height: 26, padding: "0 9px", fontSize: 11 }}
                            >
                                {f.label}
                            </button>
                        ))}
                    </div>

                    <div style={{ maxHeight: 430, overflowY: "auto", overflowX: "auto", border: "1px solid var(--mw-hairline)", borderRadius: 8 }}>
                        <table className="mw-mono" style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
                            <thead>
                                <tr style={{ background: "var(--mw-card)", color: "var(--mw-text-3)", borderBottom: "1px solid var(--mw-hairline)", position: "sticky", top: 0 }}>
                                    <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 500 }}>Data</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", fontWeight: 500 }}>Status</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", fontWeight: 500 }}>Trades (C/W/D)</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#38bdf8", fontWeight: 500 }}>CONSENSO</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#d4a259", fontWeight: 500 }}>WDO_NWE</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#a78bfa", fontWeight: 500 }}>DI_NWE</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", fontWeight: 500 }}>Dia</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#4cc38a", fontWeight: 500 }}>Acumulado</th>
                                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#e5484d", fontWeight: 500 }}>Drawdown</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredDays.map((d) => {
                                    const [dt, nT, bC, bW, bD, bTot, bCum, bDD, tC, tW, tD] = d;
                                    return (
                                        <tr
                                            key={dt}
                                            onClick={() => onSelectDate && onSelectDate(dt)}
                                            style={{ borderBottom: "1px solid rgba(255,255,255,0.04)", cursor: onSelectDate ? "pointer" : "default" }}
                                            title={onSelectDate ? `Clique para visualizar o pregão ${dt.split("-").reverse().join("/")}` : ""}
                                        >
                                            <td style={{ padding: "7px 10px", fontWeight: 600, color: "#38bdf8", whiteSpace: "nowrap" }}>
                                                {dt.split("-").reverse().join("/")}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", whiteSpace: "nowrap" }}>
                                                {nT === 0 ? (
                                                    <span style={{ color: "var(--mw-text-3)" }}>Sem operar</span>
                                                ) : bTot > 0 ? (
                                                    <span style={{ color: "#4cc38a", fontWeight: 600 }}>Positivo</span>
                                                ) : (
                                                    <span style={{ color: "#e5484d", fontWeight: 600 }}>Negativo</span>
                                                )}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", whiteSpace: "nowrap" }}>
                                                {nT} <span style={{ color: "var(--mw-text-3)", fontSize: 10.5 }}>({tC}/{tW}/{tD})</span>
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: bC > 0 ? "#4cc38a" : bC < 0 ? "#e5484d" : "var(--mw-text-3)", fontWeight: bC !== 0 ? 500 : 400, whiteSpace: "nowrap" }}>
                                                {bC === 0 ? "—" : fmt(bC)}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: bW > 0 ? "#4cc38a" : bW < 0 ? "#e5484d" : "var(--mw-text-3)", fontWeight: bW !== 0 ? 500 : 400, whiteSpace: "nowrap" }}>
                                                {bW === 0 ? "—" : fmt(bW)}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: bD > 0 ? "#4cc38a" : bD < 0 ? "#e5484d" : "var(--mw-text-3)", fontWeight: bD !== 0 ? 500 : 400, whiteSpace: "nowrap" }}>
                                                {bD === 0 ? "—" : fmt(bD)}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: bTot > 0 ? "#4cc38a" : bTot < 0 ? "#e5484d" : "var(--mw-text-3)", fontWeight: nT > 0 ? 600 : 400, whiteSpace: "nowrap" }}>
                                                {nT === 0 ? "—" : fmt(bTot)}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: "#4cc38a", fontWeight: 600, whiteSpace: "nowrap" }}>
                                                {fmt(bCum)}
                                            </td>
                                            <td style={{ textAlign: "right", padding: "7px 10px", color: bDD < 0 ? "#e5484d" : "var(--mw-text-3)", fontWeight: bDD < 0 ? 500 : 400, whiteSpace: "nowrap" }}>
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
