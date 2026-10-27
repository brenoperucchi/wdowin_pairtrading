import React, { useState } from "react";

function fmtNum(v, decimals = 0, showSign = false) {
    if (v === undefined || v === null || Number.isNaN(Number(v))) return "—";
    const n = Number(v);
    const sign = showSign && n > 0 ? "+" : "";
    return sign + n.toLocaleString("pt-BR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function scoreColor(score) {
    const s = Number(score || 0);
    if (s >= 20) return "#00e87a";
    if (s <= -20) return "#ff3860";
    return "#f5a623";
}

function stateBadgeStyle(state) {
    const st = String(state || "");
    if (st.includes("SUPORTE") || st.includes("ALTISTA")) {
        return { bg: "rgba(0, 232, 122, 0.14)", border: "#00e87a", color: "#00e87a" };
    }
    if (st.includes("RESISTENCIA") || st.includes("BAIXISTA")) {
        return { bg: "rgba(255, 56, 96, 0.14)", border: "#ff3860", color: "#ff3860" };
    }
    if (st.includes("CONFLITO")) {
        return { bg: "rgba(245, 166, 35, 0.15)", border: "#f5a623", color: "#f5a623" };
    }
    return { bg: "rgba(0, 212, 255, 0.12)", border: "#00d4ff", color: "#00d4ff" };
}

/* ── BARRA BIPOLAR HORIZONTAL (VENDEDORES ◄ 0 ► COMPRADORES) ─────────────────── */
function BipolarForceBar({ score, leftLabel = "Vendedora", rightLabel = "Compradora" }) {
    const s = Math.max(-100, Math.min(100, Number(score || 0)));
    const col = scoreColor(s);
    const pct = Math.abs(s) / 2;
    const leftPct = s >= 0 ? 50 : 50 - pct;

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <div style={{ position: "relative", height: 8, background: "#070c11", borderRadius: 4, border: "1px solid #1c2d3d", overflow: "hidden" }}>
                <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1.5, background: "#4a6478", zIndex: 2 }} />
                <div
                    style={{
                        position: "absolute",
                        left: `${leftPct}%`,
                        width: `${pct}%`,
                        top: 0,
                        bottom: 0,
                        background: col,
                        boxShadow: `0 0 8px ${col}88`,
                        transition: "all 0.25s ease",
                    }}
                />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, color: "#5c768a" }}>
                <span>◄ {leftLabel}</span>
                <span>Neutro (0)</span>
                <span>{rightLabel} ►</span>
            </div>
        </div>
    );
}

/* ── GRÁFICO PRINCIPAL DE PREÇO M5 + MAGICWALLS + SINAIS NO TEMPO ───────────── */
function IntradayPriceSignalsChart({
    symKey,
    series,
    wallsRadar,
    vwap,
    selectedSigId,
    onSelectSignal,
    height = 280,
}) {
    const dec = symKey === "WDO" ? 1 : 0;

    if (!series || series.length < 2) {
        return (
            <div style={{
                height,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#5c768a",
                fontSize: 12,
                background: "#070c12",
                borderRadius: 8,
                border: "1px solid #162432",
            }}>
                Aguardando histórico M5 da sessão para plotar o mapa de preço e sinais...
            </div>
        );
    }

    const width = 760;
    const padL = 14;
    const padR = 68;
    const padT = 24;
    const padB = 26;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;

    let minP = Infinity;
    let maxP = -Infinity;
    series.forEach(pt => {
        const l = Number(pt.low || pt.close || 0);
        const h = Number(pt.high || pt.close || 0);
        if (l > 0 && l < minP) minP = l;
        if (h > 0 && h > maxP) maxP = h;
    });

    // Inclui a 1ª parede de suporte e 1ª de resistência no cálculo do zoom para o corredor ficar sempre visível
    const sup0 = wallsRadar?.support_walls?.[0]?.price;
    const res0 = wallsRadar?.resistance_walls?.[0]?.price;
    if (sup0 && sup0 > 0 && (minP - sup0) <= (maxP - minP) * 0.45) {
        minP = Math.min(minP, sup0);
    }
    if (res0 && res0 > 0 && (res0 - maxP) <= (maxP - minP) * 0.45) {
        maxP = Math.max(maxP, res0);
    }

    if (!Number.isFinite(minP) || !Number.isFinite(maxP) || maxP <= minP) {
        minP = 0;
        maxP = 100;
    }
    const padRange = (maxP - minP) * 0.10 || 10;
    minP -= padRange;
    maxP += padRange;
    const rangeP = maxP - minP;

    const toX = (idx) => padL + (idx / Math.max(1, series.length - 1)) * plotW;
    const toY = (p) => padT + plotH - ((Number(p) - minP) / rangeP) * plotH;

    const closePoints = series
        .map((pt, idx) => `${toX(idx).toFixed(1)},${toY(pt.close).toFixed(1)}`)
        .join(" ");

    const areaPoints = `${toX(0).toFixed(1)},${(padT + plotH).toFixed(1)} ${closePoints} ${toX(series.length - 1).toFixed(1)},${(padT + plotH).toFixed(1)}`;

    // Paredes dentro da janela de preço do gráfico
    const nearbyWalls = [
        ...((wallsRadar?.resistance_walls || []).map(w => ({ ...w, role: "RES" }))),
        ...((wallsRadar?.support_walls || []).map(w => ({ ...w, role: "SUP" }))),
    ].filter(w => w.price >= minP && w.price <= maxP);

    // Sinais presentes na série M5
    const plottedSignals = [];
    series.forEach((pt, idx) => {
        if (pt.signal) {
            plottedSignals.push({
                ...pt.signal,
                idx,
                x: toX(idx),
                y: toY(pt.signal.entry_price),
            });
        }
    });

    const activeSig =
        plottedSignals.find(s => s.id === selectedSigId) ||
        (plottedSignals.length > 0 ? plottedSignals[plottedSignals.length - 1] : null);

    const lastPt = series[series.length - 1];
    const lastX = toX(series.length - 1);
    const lastY = toY(lastPt.close);

    const firstTime = series[0]?.time || "";
    const q1Time = series[Math.floor(series.length * 0.25)]?.time || "";
    const midTime = series[Math.floor(series.length * 0.5)]?.time || "";
    const q3Time = series[Math.floor(series.length * 0.75)]?.time || "";
    const lastTime = series[series.length - 1]?.time || "";

    return (
        <div style={{
            background: "#070c12",
            borderRadius: 8,
            border: "1px solid #18293a",
            padding: "10px 12px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
        }}>
            {/* Topo do Gráfico: Legenda Limpa */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, fontWeight: "bold", color: "#e6edf3", letterSpacing: 0.4 }}>
                        📈 MAPA DO PREÇO M5 ({firstTime} → {lastTime}) + PAREDES + SINAIS
                    </span>
                    <span style={{ fontSize: 9.5, color: "#00e87a", fontWeight: "bold" }}>▲ Sinal Compra</span>
                    <span style={{ fontSize: 9.5, color: "#ff3860", fontWeight: "bold" }}>▼ Sinal Venda</span>
                    <span style={{ fontSize: 9, color: "#8ca5b5" }}>
                        ⭕ Borda Verde = <strong style={{ color: "#00e87a" }}>✅ Válido</strong> · Borda Vermelha = <strong style={{ color: "#ff3860" }}>❌ Stop</strong>
                    </span>
                </div>
                <span style={{ fontSize: 9, color: "#00d4ff" }}>
                    💡 Clique em qualquer seta ▲/▼ para ver o detalhe
                </span>
            </div>

            <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height, display: "block", userSelect: "none" }}>
                <defs>
                    <linearGradient id={`priceGrad-${symKey}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#00d4ff" stopOpacity="0.16" />
                        <stop offset="100%" stopColor="#00d4ff" stopOpacity="0.0" />
                    </linearGradient>
                </defs>

                {/* Grade horizontal de referência */}
                {[0.2, 0.5, 0.8].map((r, i) => {
                    const yG = padT + plotH * r;
                    const pG = maxP - r * rangeP;
                    return (
                        <g key={`grid-${i}`}>
                            <line x1={padL} y1={yG} x2={width - padR} y2={yG} stroke="#111d28" strokeWidth="1" />
                            <text x={width - padR + 5} y={yG + 3} fill="#3d5466" fontSize="8" fontFamily="monospace">
                                {fmtNum(pG, dec)}
                            </text>
                        </g>
                    );
                })}

                {/* Linha de VWAP da Sessão */}
                {vwap >= minP && vwap <= maxP && (
                    <g>
                        <line
                            x1={padL}
                            y1={toY(vwap)}
                            x2={width - padR}
                            y2={toY(vwap)}
                            stroke="#c8a444"
                            strokeWidth="1"
                            strokeDasharray="2,3"
                            opacity="0.65"
                        />
                        <text x={padL + 4} y={toY(vwap) - 4} fill="#c8a444" fontSize="8" fontFamily="monospace" opacity="0.85">
                            VWAP {fmtNum(vwap, dec)}
                        </text>
                    </g>
                )}

                {/* Linhas Horizontais das MagicWalls (Teto / Piso) */}
                {nearbyWalls.map((w, i) => {
                    const yW = toY(w.price);
                    const isRes = w.role === "RES";
                    const col = isRes ? "#ff6b8b" : "#00e87a";
                    return (
                        <g key={`wall-${i}`}>
                            <line
                                x1={padL}
                                y1={yW}
                                x2={width - padR}
                                y2={yW}
                                stroke={col}
                                strokeWidth="1.2"
                                strokeDasharray="5,4"
                                opacity="0.65"
                            />
                            <rect
                                x={width - padR + 2}
                                y={yW - 7}
                                width={padR - 4}
                                height={14}
                                rx="3"
                                fill={isRes ? "rgba(255,56,96,0.18)" : "rgba(0,232,122,0.18)"}
                                stroke={col}
                                strokeWidth="0.7"
                            />
                            <text
                                x={width - padR + 6}
                                y={yW + 3}
                                fill={col}
                                fontSize="8.5"
                                fontWeight="bold"
                                fontFamily="monospace"
                            >
                                {fmtNum(w.price, dec)}
                            </text>
                        </g>
                    );
                })}

                {/* Área sombreada sob a curva de preço */}
                <polygon points={areaPoints} fill={`url(#priceGrad-${symKey})`} />

                {/* Velas M5 (High-Low + Corpo Open-Close) */}
                {series.map((pt, idx) => {
                    const x = toX(idx);
                    const yH = toY(pt.high || pt.close);
                    const yL = toY(pt.low || pt.close);
                    const yO = toY(pt.open || pt.close);
                    const yC = toY(pt.close);
                    const isUp = Number(pt.close) >= Number(pt.open);
                    const wickCol = isUp ? "#00e87a55" : "#ff386055";
                    const bodyTop = Math.min(yO, yC);
                    const bodyH = Math.max(1.5, Math.abs(yC - yO));
                    return (
                        <g key={`bar-${idx}`}>
                            <line x1={x} y1={yH} x2={x} y2={yL} stroke={wickCol} strokeWidth="1.4" />
                            <rect
                                x={x - 2}
                                y={bodyTop}
                                width={4}
                                height={bodyH}
                                fill={isUp ? "#00e87a88" : "#ff386088"}
                                rx="0.5"
                            />
                        </g>
                    );
                })}

                {/* Linha contínua de Fechamento M5 */}
                <polyline
                    fill="none"
                    stroke="#00d4ff"
                    strokeWidth="2.0"
                    points={closePoints}
                />

                {/* Ponto Pulsante do Preço Atual */}
                <circle cx={lastX} cy={lastY} r="4" fill="#00d4ff" stroke="#ffffff" strokeWidth="1.5" />

                {/* Marcadores dos Sinais no Tempo (▲ COMPRA / ▼ VENDA) */}
                {plottedSignals.map((sig) => {
                    const isBuy = sig.dir_num > 0;
                    const col = isBuy ? "#00e87a" : "#ff3860";
                    const ringCol = sig.is_valid === true ? "#00e87a" : sig.is_valid === false ? "#ff3860" : "#f5a623";
                    const isSelected = activeSig && activeSig.id === sig.id;
                    const x = sig.x;
                    const y = sig.y;
                    const triPoints = isBuy
                        ? `${x},${y - 8} ${x - 7},${y + 5} ${x + 7},${y + 5}`
                        : `${x},${y + 8} ${x - 7},${y - 5} ${x + 7},${y - 5}`;

                    const mfeStr = sig.is_valid === true
                        ? `+${fmtNum(sig.mfe_30m, dec)}p ✅`
                        : sig.is_valid === false
                            ? `STOP ❌`
                            : `⏳`;

                    return (
                        <g
                            key={sig.id}
                            onClick={() => onSelectSignal && onSelectSignal(sig.id)}
                            style={{ cursor: "pointer" }}
                        >
                            {isSelected && (
                                <line
                                    x1={x}
                                    y1={padT}
                                    x2={x}
                                    y2={height - padB}
                                    stroke="#c8a444"
                                    strokeWidth="1.3"
                                    strokeDasharray="3,3"
                                />
                            )}
                            <circle
                                cx={x}
                                cy={y}
                                r={isSelected ? 12 : 9.5}
                                fill="#070c12"
                                stroke={ringCol}
                                strokeWidth={isSelected ? "2.6" : "1.8"}
                                strokeDasharray={sig.is_valid === false ? "2,2" : "none"}
                            />
                            <polygon points={triPoints} fill={col} />
                            <text
                                x={x}
                                y={isBuy ? y + 20 : y - 13}
                                textAnchor="middle"
                                fill={isSelected ? "#ffffff" : ringCol}
                                fontSize="8.5"
                                fontWeight="bold"
                                fontFamily="monospace"
                            >
                                {sig.time} ({mfeStr})
                            </text>
                        </g>
                    );
                })}

                {/* Eixo de Tempo Inferior */}
                <text x={padL} y={height - 5} fill="#6b8599" fontSize="9.5" fontFamily="monospace">{firstTime}</text>
                <text x={padL + plotW * 0.25 - 14} y={height - 5} fill="#6b8599" fontSize="9.5" fontFamily="monospace">{q1Time}</text>
                <text x={padL + plotW * 0.50 - 14} y={height - 5} fill="#6b8599" fontSize="9.5" fontFamily="monospace">{midTime}</text>
                <text x={padL + plotW * 0.75 - 14} y={height - 5} fill="#6b8599" fontSize="9.5" fontFamily="monospace">{q3Time}</text>
                <text x={width - padR - 30} y={height - 5} fill="#6b8599" fontSize="9.5" fontFamily="monospace">{lastTime}</text>
            </svg>

            {/* Cartão em Destaque do Sinal Selecionado no Gráfico */}
            {activeSig && (
                <div style={{
                    background: "#0c1622",
                    border: `1px solid ${activeSig.is_valid === true ? "#00e87a66" : activeSig.is_valid === false ? "#ff386066" : "#f5a62366"}`,
                    borderRadius: 7,
                    padding: "9px 12px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: 10,
                }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                            <span style={{
                                fontSize: 11,
                                fontWeight: "bold",
                                padding: "3px 8px",
                                borderRadius: 4,
                                background: activeSig.dir_num > 0 ? "rgba(0,232,122,0.18)" : "rgba(255,56,96,0.18)",
                                color: activeSig.dir_num > 0 ? "#00e87a" : "#ff3860",
                                border: `1px solid ${activeSig.dir_num > 0 ? "#00e87a" : "#ff3860"}`,
                            }}>
                                {activeSig.dir_num > 0 ? "▲ SINAL DE COMPRA" : "▼ SINAL DE VENDA"} · {activeSig.time} @ {fmtNum(activeSig.entry_price, dec)}
                            </span>
                            <span style={{ fontSize: 10.5, fontWeight: "bold", color: "#c8a444" }}>
                                {activeSig.type}
                            </span>
                        </div>
                        <div style={{ fontSize: 10, color: "#b1c4d4" }}>
                            <strong>Por que disparou:</strong> {activeSig.reason}
                        </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                        <div style={{ display: "flex", gap: 10, fontSize: 10, background: "#081018", padding: "5px 10px", borderRadius: 5, border: "1px solid #162636" }}>
                            <span>
                                Após 5m: <strong style={{ color: (activeSig.pnl_5m || 0) >= 0 ? "#00e87a" : "#ff6b8b" }}>{fmtNum(activeSig.pnl_5m, dec, true)}p</strong>
                            </span>
                            <span>
                                Após 15m: <strong style={{ color: (activeSig.pnl_15m || 0) >= 0 ? "#00e87a" : "#ff6b8b" }}>{fmtNum(activeSig.pnl_15m, dec, true)}p</strong>
                            </span>
                            <span>
                                Máx a Favor (30m): <strong style={{ color: "#00e87a" }}>+{fmtNum(activeSig.mfe_30m, dec)}p</strong>
                            </span>
                            <span>
                                Máx Contra: <strong style={{ color: "#ff6b8b" }}>{fmtNum(activeSig.mae_30m, dec)}p</strong>
                            </span>
                        </div>
                        <span style={{
                            fontSize: 11,
                            fontWeight: "bold",
                            padding: "4px 10px",
                            borderRadius: 5,
                            background: activeSig.is_valid === true ? "rgba(0,232,122,0.18)" : activeSig.is_valid === false ? "rgba(255,56,96,0.18)" : "rgba(245,166,35,0.18)",
                            color: activeSig.is_valid === true ? "#00e87a" : activeSig.is_valid === false ? "#ff3860" : "#f5a623",
                            border: `1px solid ${activeSig.is_valid === true ? "#00e87a66" : activeSig.is_valid === false ? "#ff386066" : "#f5a62366"}`,
                        }}>
                            {activeSig.validation_label}
                        </span>
                    </div>
                </div>
            )}
        </div>
    );
}

/* ── COMPONENTE DO COCKPIT DE 1 ATIVO (ESQUERDA: GRÁFICO+SINAIS | DIREITA: BÚSSOLA) ── */
function SingleAssetCockpitView({ symKey, payload, cbData, onOpenRaioX }) {
    const [selectedSigId, setSelectedSigId] = useState(null);
    if (!payload) return null;

    const dec = symKey === "WDO" ? 1 : 0;
    const ca = payload.caminho_a || {};
    const loc = ca.local_gex || {};
    const hh = ca.hedge_horizons || {};
    const cm = ca.confluence_matrix || {};
    const sc = ca.signals_scorecard || {};
    const signalsLog = ca.signals_log || [];
    const series = ca.m5_dealer_vs_flow_series || [];

    const comp = payload.flow_compass || {};
    const w5m = comp.windows?.["5m"] || {};
    const tot = payload.session_totals || {};
    const book = payload.top_of_book || {};
    const radar = payload.walls_radar || {};
    const supWalls = radar.support_walls || [];
    const resWalls = radar.resistance_walls || [];
    const nearestSup = supWalls[0];
    const nearestRes = resWalls[0];
    const sup2 = supWalls[1];
    const res2 = resWalls[1];
    const activeWall = radar.active_wall_alert;

    const isPosGamma = loc.local_regime === "POSITIVE_GAMMA";
    const badge = stateBadgeStyle(cm.operational_state);

    // Posição percentual do preço entre o Suporte 1 e a Resistência 1
    let corridorPct = 50;
    if (nearestSup && nearestRes && nearestRes.price > nearestSup.price) {
        corridorPct = Math.max(
            2,
            Math.min(98, ((payload.last_price - nearestSup.price) / (nearestRes.price - nearestSup.price)) * 100)
        );
    }

    const wr = Number(sc.win_rate_pct || 0);
    const wrColor = wr >= 60 ? "#00e87a" : wr >= 50 ? "#f5a623" : "#ff3860";

    // Dados dos 3 Semáforos da Direita
    const instNet = Number(tot.inst_broker_net || 0);
    const instAggr = Number(tot.inst_broker_aggr_delta || 0);
    const instPass = Number(tot.inst_broker_passive_delta || 0);
    const delta5m = Number(w5m.inst_delta || 0);
    const flowScore = Number(comp.score || 0);

    const dealer5m = Number(hh["5m"]?.dealer_hedge_contracts || 0);
    const dealer15m = Number(hh["15m"]?.dealer_hedge_contracts || 0);
    const dealerScore = Number(ca.dealer_pressure_score || 0);

    const optScore = Number(cbData?.options_compass?.score || 0);
    const opt15m = cbData?.windows?.["15m"] || {};
    const optSkew = Number(cbData?.volatility_surface?.skew_25d_pct || 0);

    return (
        <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 14, alignItems: "start" }}>
            {/* ══════════════════════════════════════════════════════════════════════════
                COLUNA ESQUERDA (62%): PLACAR DO DIA + GRÁFICO NO TEMPO + DIÁRIO DE SINAIS
               ══════════════════════════════════════════════════════════════════════════ */}
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {/* 1. Faixa de KPIs do Placar de Assertividade do Dia */}
                <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(4, 1fr)",
                    gap: 10,
                    background: "#0b121a",
                    border: "1px solid #18293a",
                    borderRadius: 8,
                    padding: "9px 12px",
                }}>
                    <div style={{ borderRight: "1px solid #162534", paddingRight: 8 }}>
                        <div style={{ fontSize: 8.5, color: "#7f96a8", fontWeight: "bold" }}>🎯 ASSERTIVIDADE HOJE ({symKey})</div>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 2 }}>
                            <span style={{ fontSize: 18, fontWeight: "bold", color: wrColor }}>{fmtNum(wr, 1)}%</span>
                            <span style={{ fontSize: 10, color: "#b1c4d4" }}>
                                ({sc.valid_signals || 0} ✅ / {sc.invalid_signals || 0} ❌)
                            </span>
                        </div>
                    </div>

                    <div style={{ borderRight: "1px solid #162534", paddingRight: 8 }}>
                        <div style={{ fontSize: 8.5, color: "#7f96a8", fontWeight: "bold" }}>🚀 MÉDIA MÁX. A FAVOR (30m)</div>
                        <div style={{ fontSize: 17, fontWeight: "bold", color: "#00e87a", marginTop: 2 }}>
                            +{fmtNum(sc.avg_max_favor_pts, dec)} pts
                        </div>
                    </div>

                    <div style={{ borderRight: "1px solid #162534", paddingRight: 8 }}>
                        <div style={{ fontSize: 8.5, color: "#7f96a8", fontWeight: "bold" }}>⏱️ RESULTADO MÉDIO EM 15m</div>
                        <div style={{
                            fontSize: 17,
                            fontWeight: "bold",
                            color: (sc.avg_15m_pts || 0) >= 0 ? "#00d4ff" : "#f5a623",
                            marginTop: 2,
                        }}>
                            {fmtNum(sc.avg_15m_pts, dec, true)} pts
                        </div>
                    </div>

                    <div>
                        <div style={{ fontSize: 8.5, color: "#7f96a8", fontWeight: "bold" }}>📏 CRITÉRIO DE VALIDAÇÃO</div>
                        <div style={{ fontSize: 12, fontWeight: "bold", color: "#e6edf3", marginTop: 4 }}>
                            Alvo +{fmtNum(sc.target_ref_pts, dec)}p / Stop -{fmtNum(sc.stop_ref_pts, dec)}p
                        </div>
                    </div>
                </div>

                {/* 2. Gráfico Grande de Preço M5 + Paredes + Sinais Marcados no Tempo */}
                <IntradayPriceSignalsChart
                    symKey={symKey}
                    series={series}
                    wallsRadar={radar}
                    vwap={payload.vwap}
                    selectedSigId={selectedSigId}
                    onSelectSignal={setSelectedSigId}
                    height={275}
                />

                {/* 3. Tabela Limpa e Clicável: Linha do Tempo dos Sinais de Hoje */}
                <div style={{
                    background: "#0b121a",
                    border: "1px solid #18293a",
                    borderRadius: 8,
                    padding: "10px 12px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 10.5, fontWeight: "bold", color: "#c8a444", letterSpacing: 0.5 }}>
                            📋 LINHA DO TEMPO DOS SINAIS DE HOJE ({signalsLog.length} sinais emitidos — clique numa linha para destacar no gráfico)
                        </span>
                    </div>

                    <div style={{ maxHeight: 235, overflowY: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 9.5 }}>
                            <thead>
                                <tr style={{ color: "#6b8599", borderBottom: "1px solid #18293a", textAlign: "right", position: "sticky", top: 0, background: "#0b121a" }}>
                                    <th style={{ textAlign: "left", padding: "5px 6px" }}>HORA</th>
                                    <th style={{ textAlign: "left", padding: "5px 6px" }}>SINAL</th>
                                    <th style={{ padding: "5px 6px" }}>ENTRADA</th>
                                    <th style={{ textAlign: "left", padding: "5px 6px" }}>MOTIVO / GATILHO</th>
                                    <th style={{ padding: "5px 6px" }}>+5m</th>
                                    <th style={{ padding: "5px 6px" }}>+15m</th>
                                    <th style={{ padding: "5px 6px", color: "#00e87a" }}>MÁX A FAVOR</th>
                                    <th style={{ padding: "5px 6px", color: "#ff6b8b" }}>MÁX CONTRA</th>
                                    <th style={{ textAlign: "right", padding: "5px 6px" }}>VALIDAÇÃO</th>
                                </tr>
                            </thead>
                            <tbody>
                                {signalsLog.map((sig) => {
                                    const isBuy = sig.dir_num > 0;
                                    const isSel = selectedSigId === sig.id;
                                    const vColor = sig.is_valid === true ? "#00e87a" : sig.is_valid === false ? "#ff3860" : "#f5a623";
                                    return (
                                        <tr
                                            key={sig.id}
                                            onClick={() => setSelectedSigId(sig.id)}
                                            style={{
                                                borderBottom: "1px solid #121e2b",
                                                textAlign: "right",
                                                cursor: "pointer",
                                                background: isSel ? "rgba(0, 212, 255, 0.12)" : "transparent",
                                            }}
                                        >
                                            <td style={{ textAlign: "left", padding: "6px", fontWeight: "bold", color: "#ffffff" }}>{sig.time}</td>
                                            <td style={{ textAlign: "left", padding: "6px", fontWeight: "bold", color: isBuy ? "#00e87a" : "#ff3860" }}>
                                                {isBuy ? "▲ COMPRA" : "▼ VENDA"}
                                            </td>
                                            <td style={{ padding: "6px", fontWeight: "bold", color: "#e6edf3" }}>{fmtNum(sig.entry_price, dec)}</td>
                                            <td style={{ textAlign: "left", padding: "6px", color: "#9fb4c4", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={sig.reason}>
                                                <strong style={{ color: "#c8a444" }}>{sig.type}</strong>
                                            </td>
                                            <td style={{ padding: "6px", color: (sig.pnl_5m || 0) >= 0 ? "#00e87a" : "#ff6b8b", fontWeight: "bold" }}>
                                                {sig.pnl_5m !== null && sig.pnl_5m !== undefined ? fmtNum(sig.pnl_5m, dec, true) : "—"}
                                            </td>
                                            <td style={{ padding: "6px", color: (sig.pnl_15m || 0) >= 0 ? "#00e87a" : "#ff6b8b", fontWeight: "bold" }}>
                                                {sig.pnl_15m !== null && sig.pnl_15m !== undefined ? fmtNum(sig.pnl_15m, dec, true) : "—"}
                                            </td>
                                            <td style={{ padding: "6px", color: "#00e87a", fontWeight: "bold" }}>
                                                +{fmtNum(sig.mfe_30m, dec)}p
                                            </td>
                                            <td style={{ padding: "6px", color: "#ff6b8b" }}>
                                                {fmtNum(sig.mae_30m, dec)}p
                                            </td>
                                            <td style={{ padding: "6px", fontWeight: "bold", color: vColor }}>
                                                {sig.validation_label}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            {/* ══════════════════════════════════════════════════════════════════════════
                COLUNA DIREITA (38%): OS 3 BLOCOS VISUAIS DE DECISÃO IMEDIATA
               ══════════════════════════════════════════════════════════════════════════ */}
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {/* BLOCO 1: TERMÔMETRO DE FORÇA AGORA (OS 3 PILARES COM BARRAS VISUAIS) */}
                <div style={{
                    background: "#0b121a",
                    border: "1px solid #18293a",
                    borderRadius: 8,
                    padding: "11px 14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 10.5, fontWeight: "bold", color: "#00d4ff", letterSpacing: 0.7 }}>
                            1️⃣ QUEM ESTÁ COMPRANDO OU VENDENDO AGORA?
                        </span>
                        <span style={{ fontSize: 9, color: "#7f96a8" }}>Score Fluxo: <strong style={{ color: scoreColor(flowScore) }}>{fmtNum(flowScore, 0, true)}</strong></span>
                    </div>

                    {/* Medidor 1: Bancos Profit */}
                    <div style={{ background: "#070c12", border: "1px solid #152331", borderRadius: 6, padding: "8px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: 9.5, fontWeight: "bold", color: "#e6edf3" }}>🏦 BANCOS NO PROFIT (Dia / 5m)</span>
                            <span style={{ fontSize: 11, fontWeight: "bold", color: scoreColor(instNet) }}>
                                {instNet >= 0 ? "🟢 COMPRADOS" : "🔴 VENDIDOS"} ({fmtNum(instNet, 0, true)} L)
                            </span>
                        </div>
                        <BipolarForceBar score={flowScore} leftLabel="Bancos Vendendo" rightLabel="Bancos Comprando" />
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#9fb4c4", paddingTop: 2 }}>
                            <span>Agressão Tela: <strong style={{ color: instAggr >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(instAggr, 0, true)}</strong></span>
                            <span>Defesa Fila: <strong style={{ color: instPass >= 0 ? "#00d4ff" : "#f5a623" }}>{fmtNum(instPass, 0, true)}</strong></span>
                            <span>Últimos 5m: <strong style={{ color: delta5m >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(delta5m, 0, true)}L</strong></span>
                        </div>
                    </div>

                    {/* Medidor 2: Market Makers / Dealers GEX */}
                    <div style={{ background: "#070c12", border: "1px solid #152331", borderRadius: 6, padding: "8px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: 9.5, fontWeight: "bold", color: "#e6edf3" }}>⚙️ MARKET MAKERS (HEDGE GEX)</span>
                            <span style={{
                                fontSize: 9.5,
                                fontWeight: "bold",
                                padding: "2px 6px",
                                borderRadius: 4,
                                background: isPosGamma ? "rgba(0,212,255,0.15)" : "rgba(255,56,96,0.15)",
                                color: isPosGamma ? "#00d4ff" : "#ff3860",
                            }}>
                                {isPosGamma ? "🛡️ AMORTECEDOR (GAMMA +)" : "⚡ ACELERADOR (GAMMA −)"}
                            </span>
                        </div>
                        <BipolarForceBar score={dealerScore} leftLabel="Dealers Vendendo" rightLabel="Dealers Comprando" />
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#9fb4c4", paddingTop: 2 }}>
                            <span>Hedge 5m: <strong style={{ color: dealer5m >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(dealer5m, 0, true)} c.</strong></span>
                            <span>Hedge 15m: <strong style={{ color: dealer15m >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(dealer15m, 0, true)} c.</strong></span>
                            <span>Força: <strong>{fmtNum(loc.dealer_contracts_per_step, 0)}c/{fmtNum(loc.step_pts, 0)}p</strong></span>
                        </div>
                    </div>

                    {/* Medidor 3: Opções BOVA11 (para WIN) ou Fila do Book (para WDO) */}
                    {symKey === "WIN" && cbData?.ok ? (
                        <div style={{ background: "#070c12", border: "1px solid #152331", borderRadius: 6, padding: "8px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span style={{ fontSize: 9.5, fontWeight: "bold", color: "#e6edf3" }}>🎯 OPÇÕES AO VIVO (BOVA11)</span>
                                <span style={{ fontSize: 11, fontWeight: "bold", color: scoreColor(optScore) }}>
                                    {optScore >= 18 ? "🟢 FLUXO ALTISTA" : optScore <= -18 ? "🔴 FLUXO BAIXISTA" : "🟡 EQUILÍBRIO"} ({fmtNum(optScore, 0, true)})
                                </span>
                            </div>
                            <BipolarForceBar score={optScore} leftLabel="Compra Put / Venda Call" rightLabel="Compra Call / Venda Put" />
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#9fb4c4", paddingTop: 2 }}>
                                <span>Saldo 15m: <strong style={{ color: (opt15m.bull_bear_imbalance_pct || 0) >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(opt15m.bull_bear_imbalance_pct, 1, true)}%</strong></span>
                                <span>Delta Equiv: <strong>{fmtNum(opt15m.net_delta_equivalent, 0, true)}</strong></span>
                                <span>Skew Put−Call: <strong>{fmtNum(optSkew, 2, true)}%</strong></span>
                            </div>
                        </div>
                    ) : (
                        <div style={{ background: "#070c12", border: "1px solid #152331", borderRadius: 6, padding: "8px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span style={{ fontSize: 9.5, fontWeight: "bold", color: "#e6edf3" }}>📚 FILA DO TOPO DO BOOK</span>
                                <span style={{ fontSize: 10, fontWeight: "bold", color: (book.book_imbalance_pct || 0) >= 0 ? "#00e87a" : "#ff3860" }}>
                                    Imbalance: {fmtNum(book.book_imbalance_pct, 1, true)}%
                                </span>
                            </div>
                            <BipolarForceBar score={book.book_imbalance_pct} leftLabel="Oferta Ask" rightLabel="Demanda Bid" />
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#9fb4c4" }}>
                                <span>BID: <strong style={{ color: "#00e87a" }}>{fmtNum(book.best_bid_price, dec)} ({fmtNum(book.best_bid_qty, 0)}L)</strong></span>
                                <span>ASK: <strong style={{ color: "#ff3860" }}>{fmtNum(book.best_ask_price, dec)} ({fmtNum(book.best_ask_qty, 0)}L)</strong></span>
                            </div>
                        </div>
                    )}
                </div>

                {/* BLOCO 2: ELEVADOR DE PAREDES (MAPA VERTICAL DO CORREDOR ATUAL) */}
                <div style={{
                    background: "#0b121a",
                    border: "1px solid #18293a",
                    borderRadius: 8,
                    padding: "11px 14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 10.5, fontWeight: "bold", color: "#00e87a", letterSpacing: 0.7 }}>
                            2️⃣ ELEVADOR DE PAREDES (ONDE ESTOU NO CORREDOR?)
                        </span>
                        {activeWall && (
                            <span style={{ fontSize: 8.5, background: "rgba(200,164,68,0.25)", color: "#c8a444", border: "1px solid #c8a444", padding: "2px 6px", borderRadius: 4, fontWeight: "bold" }}>
                                ⚡ NA PAREDE AGORA!
                            </span>
                        )}
                    </div>

                    {/* Escada Vertical Visual: Teto 2 -> Teto 1 -> PREÇO ATUAL -> Piso 1 -> Piso 2 */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                        {/* Teto 2 */}
                        {res2 && (
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#070c12", padding: "5px 10px", borderRadius: 5, borderLeft: "3px solid #ff386066", fontSize: 9.5 }}>
                                <span style={{ color: "#ff6b8b" }}>▲ Teto 2 · {res2.type}</span>
                                <span style={{ color: "#e6edf3", fontWeight: "bold" }}>
                                    {fmtNum(res2.price, dec)} <span style={{ color: "#ff6b8b", fontSize: 8.5 }}>({fmtNum(res2.dist_pts, dec, true)} pts)</span>
                                </span>
                            </div>
                        )}

                        {/* Teto 1 (Resistência Imediata) */}
                        {nearestRes && (
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(255,56,96,0.09)", padding: "7px 10px", borderRadius: 6, border: "1px solid #ff386055", borderLeft: "4px solid #ff3860" }}>
                                <div>
                                    <div style={{ fontSize: 9.5, fontWeight: "bold", color: "#ff6b8b" }}>🔴 TETO IMEDIATO · {nearestRes.type}</div>
                                    <div style={{ fontSize: 8.5, color: "#9fb4c4" }}>{nearestRes.status} · GEX {nearestRes.gex_formatted || "Mid"}</div>
                                </div>
                                <div style={{ textAlign: "right" }}>
                                    <div style={{ fontSize: 14, fontWeight: "bold", color: "#ffffff" }}>{fmtNum(nearestRes.price, dec)}</div>
                                    <div style={{ fontSize: 9.5, fontWeight: "bold", color: "#ff6b8b" }}>Faltam {fmtNum(nearestRes.dist_pts, dec, true)} pts</div>
                                </div>
                            </div>
                        )}

                        {/* PREÇO ATUAL NO MEIO + RÉGUA DE POSIÇÃO ENTRE PISO E TETO */}
                        <div style={{ background: "rgba(0, 212, 255, 0.12)", border: "1px solid #00d4ff66", borderRadius: 6, padding: "8px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span style={{ fontSize: 9.5, fontWeight: "bold", color: "#00d4ff" }}>🔵 PREÇO SPOT ATUAL</span>
                                <span style={{ fontSize: 16, fontWeight: "bold", color: "#ffffff" }}>{fmtNum(payload.last_price, dec)}</span>
                            </div>
                            {/* Barra Piso 0% <---> Teto 100% */}
                            <div style={{ position: "relative", height: 9, background: "linear-gradient(90deg, rgba(0,232,122,0.35), rgba(0,212,255,0.15), rgba(255,56,96,0.35))", borderRadius: 5, border: "1px solid #1e3448" }}>
                                <div
                                    style={{
                                        position: "absolute",
                                        left: `calc(${corridorPct}% - 5px)`,
                                        top: -2,
                                        width: 10,
                                        height: 11,
                                        borderRadius: "50%",
                                        background: "#ffffff",
                                        border: "2px solid #00d4ff",
                                        boxShadow: "0 0 8px #00d4ff",
                                    }}
                                />
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8.5, color: "#9fb4c4" }}>
                                <span>🟢 Piso ({fmtNum(corridorPct, 0)}% do corredor)</span>
                                <span>VWAP: {fmtNum(payload.vwap, dec)}</span>
                                <span>Teto 🔴</span>
                            </div>
                        </div>

                        {/* Piso 1 (Suporte Imediato) */}
                        {nearestSup && (
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(0,232,122,0.09)", padding: "7px 10px", borderRadius: 6, border: "1px solid #00e87a55", borderLeft: "4px solid #00e87a" }}>
                                <div>
                                    <div style={{ fontSize: 9.5, fontWeight: "bold", color: "#00e87a" }}>🟢 PISO IMEDIATO · {nearestSup.type}</div>
                                    <div style={{ fontSize: 8.5, color: "#9fb4c4" }}>{nearestSup.status} · GEX {nearestSup.gex_formatted || "Mid"}</div>
                                </div>
                                <div style={{ textAlign: "right" }}>
                                    <div style={{ fontSize: 14, fontWeight: "bold", color: "#ffffff" }}>{fmtNum(nearestSup.price, dec)}</div>
                                    <div style={{ fontSize: 9.5, fontWeight: "bold", color: "#00e87a" }}>Distância {fmtNum(nearestSup.dist_pts, dec, true)} pts</div>
                                </div>
                            </div>
                        )}

                        {/* Piso 2 */}
                        {sup2 && (
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#070c12", padding: "5px 10px", borderRadius: 5, borderLeft: "3px solid #00e87a66", fontSize: 9.5 }}>
                                <span style={{ color: "#00e87a" }}>▼ Piso 2 · {sup2.type}</span>
                                <span style={{ color: "#e6edf3", fontWeight: "bold" }}>
                                    {fmtNum(sup2.price, dec)} <span style={{ color: "#00e87a", fontSize: 8.5 }}>({fmtNum(sup2.dist_pts, dec, true)} pts)</span>
                                </span>
                            </div>
                        )}
                    </div>
                </div>

                {/* BLOCO 3: PLANO DE AÇÃO DIRETO (SEM PARÁGRAFOS LONGOS) */}
                <div style={{
                    background: "#0b121a",
                    border: `1px solid ${badge.border}66`,
                    borderRadius: 8,
                    padding: "11px 14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 10.5, fontWeight: "bold", color: "#c8a444", letterSpacing: 0.7 }}>
                            3️⃣ PLANO DE AÇÃO DIRETO ({symKey})
                        </span>
                        <span style={{
                            fontSize: 9.5,
                            fontWeight: "bold",
                            background: badge.bg,
                            color: badge.color,
                            border: `1px solid ${badge.border}`,
                            padding: "2px 8px",
                            borderRadius: 4,
                        }}>
                            {cm.operational_bias || "AGUARDANDO"}
                        </span>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 10 }}>
                        <div style={{ background: "rgba(0,232,122,0.08)", borderLeft: "3px solid #00e87a", padding: "6px 9px", borderRadius: "0 5px 5px 0", color: "#e6edf3" }}>
                            <strong style={{ color: "#00e87a" }}>🟢 Onde Comprar:</strong>{" "}
                            {nearestSup
                                ? `Defesa / Absorção no Piso ${fmtNum(nearestSup.price, dec)} (${fmtNum(nearestSup.dist_pts, dec, true)}p) ou retomada institucional na base.`
                                : "Aguardar formação de suporte com fluxo institucional comprador."}
                        </div>
                        <div style={{ background: "rgba(255,56,96,0.08)", borderLeft: "3px solid #ff3860", padding: "6px 9px", borderRadius: "0 5px 5px 0", color: "#e6edf3" }}>
                            <strong style={{ color: "#ff6b8b" }}>🔴 Onde Vender:</strong>{" "}
                            {nearestRes
                                ? `Rejeição / Absorção no Teto ${fmtNum(nearestRes.price, dec)} (${fmtNum(nearestRes.dist_pts, dec, true)}p) ou perda de parede com fluxo vendedor.`
                                : "Aguardar teste de resistência com rejeição institucional."}
                        </div>
                        <div style={{ background: "#070c12", borderLeft: "3px solid #c8a444", padding: "6px 9px", borderRadius: "0 5px 5px 0", color: "#b1c4d4", fontSize: 9.5 }}>
                            <strong style={{ color: "#c8a444" }}>⚠️ Regra do Regime Atual:</strong>{" "}
                            {isPosGamma
                                ? "Mercado em Gamma Positivo (Amortecedor): evite comprar topo esticado ou vender fundo esticado. Opere nas paredes."
                                : "Mercado em Gamma Negativo (Acelerador): os Dealers operam a favor do rompimento. Acompanhe o fluxo institucional."}
                        </div>
                    </div>

                    {onOpenRaioX && (
                        <button
                            onClick={onOpenRaioX}
                            style={{
                                marginTop: 2,
                                width: "100%",
                                padding: "6px 10px",
                                fontSize: 9.5,
                                fontFamily: "monospace",
                                fontWeight: "bold",
                                background: "#0d1824",
                                border: "1px solid #233b52",
                                color: "#00d4ff",
                                borderRadius: 5,
                                cursor: "pointer",
                            }}
                        >
                            🔬 Abrir Raio-X Completo (Ranking Corretoras Profit + Grade Opções BOVA11) →
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

/* ── GRÁFICO COMPACTO AUXILIAR PARA O MODO RAIO-X ───────────────────────────── */
function MiniSvgChart({ series, keys, colors, labels, height = 115 }) {
    if (!series || series.length < 2) {
        return (
            <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#4a6070", fontSize: 10, background: "#090e14", borderRadius: 6, border: "1px solid #16222c" }}>
                Aguardando barras M5 da sessão...
            </div>
        );
    }

    const width = 560;
    const padL = 8;
    const padR = 8;
    const padT = 12;
    const padB = 18;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;

    let minVal = 0;
    let maxVal = 0;
    keys.forEach(k => {
        series.forEach(pt => {
            const v = Number(pt[k] || 0);
            if (v < minVal) minVal = v;
            if (v > maxVal) maxVal = v;
        });
    });
    if (maxVal === minVal) {
        maxVal += 1;
        minVal -= 1;
    }
    const range = maxVal - minVal;
    const yZero = padT + plotH - ((0 - minVal) / range) * plotH;

    const makePoints = (k) =>
        series
            .map((pt, idx) => {
                const x = padL + (idx / Math.max(1, series.length - 1)) * plotW;
                const v = Number(pt[k] || 0);
                const y = padT + plotH - ((v - minVal) / range) * plotH;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            })
            .join(" ");

    const firstTime = series[0]?.time || "";
    const midTime = series[Math.floor(series.length / 2)]?.time || "";
    const lastTime = series[series.length - 1]?.time || "";

    return (
        <div style={{ background: "#090e14", borderRadius: 6, border: "1px solid #16222c", padding: "6px 8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, flexWrap: "wrap", gap: 8 }}>
                <div style={{ display: "flex", gap: 10 }}>
                    {keys.map((k, idx) => {
                        const lastV = Number(series[series.length - 1]?.[k] || 0);
                        return (
                            <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 9 }}>
                                <span style={{ width: 8, height: 3, background: colors[idx], display: "inline-block", borderRadius: 1 }} />
                                <span style={{ color: "#7f96a8" }}>{labels[idx]}:</span>
                                <span style={{ color: colors[idx], fontWeight: "bold" }}>{fmtNum(lastV, 0, true)}</span>
                            </span>
                        );
                    })}
                </div>
                <span style={{ fontSize: 8, color: "#4a6070" }}>{series.length} barras M5</span>
            </div>
            <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: height, display: "block" }}>
                <line x1={padL} y1={yZero} x2={width - padR} y2={yZero} stroke="#1f3140" strokeDasharray="3,3" strokeWidth="1" />
                {keys.map((k, idx) => (
                    <polyline
                        key={k}
                        fill="none"
                        stroke={colors[idx]}
                        strokeWidth={idx === 0 ? "2.2" : "1.5"}
                        points={makePoints(k)}
                    />
                ))}
                <text x={padL + 2} y={height - 3} fill="#4a6070" fontSize="9" fontFamily="monospace">{firstTime}</text>
                <text x={width / 2 - 14} y={height - 3} fill="#4a6070" fontSize="9" fontFamily="monospace">{midTime}</text>
                <text x={width - padR - 28} y={height - 3} fill="#4a6070" fontSize="9" fontFamily="monospace">{lastTime}</text>
            </svg>
        </div>
    );
}

/* ── CARD DETALHADO DE RAIO-X (CORRETORAS PROFIT, JANELAS E ESCADA DE WALLS) ── */
function RaioXAssetCard({ symKey, payload }) {
    if (!payload) return null;
    const dec = symKey === "WDO" ? 1 : 0;
    const ca = payload.caminho_a || {};
    const comp = payload.flow_compass || {};
    const wins = comp.windows || {};
    const tot = payload.session_totals || {};
    const radar = payload.walls_radar || {};
    const supWalls = radar.support_walls || [];
    const resWalls = [...(radar.resistance_walls || [])].reverse();

    return (
        <div style={{
            flex: 1,
            minWidth: 460,
            background: "#0b121a",
            border: "1px solid #18293a",
            borderRadius: 8,
            padding: 12,
            display: "flex",
            flexDirection: "column",
            gap: 10,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #162433", paddingBottom: 8 }}>
                <span style={{ fontSize: 13, fontWeight: "bold", color: symKey === "WIN" ? "#00d4ff" : "#c8a444" }}>
                    🔬 RAIO-X DE MICROESTRUTURA · {symKey} ({payload.active_contract})
                </span>
                <span style={{ fontSize: 9, color: "#00e87a", background: "rgba(0,232,122,0.12)", padding: "2px 8px", borderRadius: 4, border: "1px solid #00e87a44" }}>
                    {payload.source}
                </span>
            </div>

            {/* Tabela de Janelas Temporais (1m, 5m, 15m, 60m, Sessão) */}
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 9 }}>
                <thead>
                    <tr style={{ color: "#5c7487", borderBottom: "1px solid #16232f", textAlign: "right" }}>
                        <th style={{ textAlign: "left", padding: "4px" }}>JANELA</th>
                        <th style={{ padding: "4px" }}>DELTA TOTAL</th>
                        <th style={{ padding: "4px" }}>LOTE GRANDE ({symKey === "WIN" ? "≥50L" : "≥20L"})</th>
                        <th style={{ padding: "4px" }}>VAREJO</th>
                        <th style={{ padding: "4px" }}>DESEQUILÍBRIO</th>
                        <th style={{ textAlign: "right", padding: "4px" }}>ABSORÇÃO</th>
                    </tr>
                </thead>
                <tbody>
                    {["1m", "5m", "15m", "60m"].map(wk => {
                        const w = wins[wk] || {};
                        return (
                            <tr key={wk} style={{ borderBottom: "1px solid #111b24", textAlign: "right" }}>
                                <td style={{ textAlign: "left", padding: "4px", fontWeight: "bold", color: "#9fb4c4" }}>{wk}</td>
                                <td style={{ padding: "4px", color: w.delta >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>{fmtNum(w.delta, 0, true)}</td>
                                <td style={{ padding: "4px", color: w.inst_delta >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                                <td style={{ padding: "4px", color: w.ret_delta >= 0 ? "#00d4ff" : "#f5a623" }}>{fmtNum(w.ret_delta, 0, true)}</td>
                                <td style={{ padding: "4px", color: "#b1c4d4" }}>{fmtNum(w.imbalance_pct, 1, true)}%</td>
                                <td style={{ padding: "4px", fontSize: 8.5, color: String(w.absorption_state || "").includes("ABSORCAO") ? "#c8a444" : "#566d7e" }}>
                                    {w.absorption_state || "NEUTRO"}
                                </td>
                            </tr>
                        );
                    })}
                    <tr style={{ textAlign: "right", background: "#070c12", fontWeight: "bold" }}>
                        <td style={{ textAlign: "left", padding: "5px 4px", color: "#c8a444" }}>SESSÃO</td>
                        <td style={{ padding: "5px 4px", color: tot.total_delta >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(tot.total_delta, 0, true)}</td>
                        <td style={{ padding: "5px 4px", color: tot.inst_delta >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(tot.inst_delta, 0, true)}</td>
                        <td style={{ padding: "5px 4px", color: tot.retail_delta >= 0 ? "#00d4ff" : "#f5a623" }}>{fmtNum(tot.retail_delta, 0, true)}</td>
                        <td style={{ padding: "5px 4px", color: "#b1c4d4" }}>RLP: {fmtNum(tot.rlp_vol, 0)}L</td>
                        <td style={{ padding: "5px 4px", fontSize: 8.5, color: "#8ca5b5" }}>{fmtNum(tot.total_deals, 0)} negócios</td>
                    </tr>
                </tbody>
            </table>

            {/* Top Compradores vs Top Vendedores no Profit */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div style={{ background: "#070c12", padding: "7px 9px", borderRadius: 5, border: "1px solid #142430" }}>
                    <div style={{ fontSize: 8.5, color: "#00e87a", fontWeight: "bold", marginBottom: 4 }}>🏦 TOP COMPRADORES LÍQUIDOS (PROFIT)</div>
                    {(payload.top_buyers || []).slice(0, 5).map(b => (
                        <div key={b.broker} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, padding: "2px 0", borderBottom: "1px solid #0f1922" }}>
                            <span style={{ color: b.is_institutional ? "#ffffff" : "#8ca5b5", fontWeight: b.is_institutional ? "bold" : "normal" }}>
                                {b.broker} {b.is_institutional ? "🏦" : ""}
                            </span>
                            <span style={{ color: "#00e87a", fontFamily: "monospace" }}>
                                +{fmtNum(b.net, 0)} <span style={{ color: "#657d8f", fontSize: 8 }}>(Agr:{fmtNum((b.aggr_buy || 0) - (b.aggr_sell || 0), 0, true)} | Pas:{fmtNum((b.passive_buy || 0) - (b.passive_sell || 0), 0, true)})</span>
                            </span>
                        </div>
                    ))}
                </div>
                <div style={{ background: "#070c12", padding: "7px 9px", borderRadius: 5, border: "1px solid #142430" }}>
                    <div style={{ fontSize: 8.5, color: "#ff3860", fontWeight: "bold", marginBottom: 4 }}>🏦 TOP VENDEDORES LÍQUIDOS (PROFIT)</div>
                    {(payload.top_sellers || []).slice(0, 5).map(b => (
                        <div key={b.broker} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, padding: "2px 0", borderBottom: "1px solid #0f1922" }}>
                            <span style={{ color: b.is_institutional ? "#ffffff" : "#8ca5b5", fontWeight: b.is_institutional ? "bold" : "normal" }}>
                                {b.broker} {b.is_institutional ? "🏦" : ""}
                            </span>
                            <span style={{ color: "#ff3860", fontFamily: "monospace" }}>
                                {fmtNum(b.net, 0)} <span style={{ color: "#657d8f", fontSize: 8 }}>(Agr:{fmtNum((b.aggr_buy || 0) - (b.aggr_sell || 0), 0, true)} | Pas:{fmtNum((b.passive_buy || 0) - (b.passive_sell || 0), 0, true)})</span>
                            </span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Escada Completa de 6 MagicWalls Próximas */}
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 8.5 }}>
                <thead>
                    <tr style={{ color: "#5c7487", borderBottom: "1px solid #16232f", textAlign: "right" }}>
                        <th style={{ textAlign: "left", padding: "3px 4px" }}>PAREDE</th>
                        <th style={{ padding: "3px 4px" }}>PREÇO</th>
                        <th style={{ padding: "3px 4px" }}>DIST.</th>
                        <th style={{ padding: "3px 4px" }}>GEX</th>
                        <th style={{ padding: "3px 4px" }}>DELTA INST NA LINHA</th>
                        <th style={{ padding: "3px 4px" }}>STATUS</th>
                    </tr>
                </thead>
                <tbody>
                    {resWalls.map((w, i) => (
                        <tr key={`r-${i}`} style={{ borderBottom: "1px solid #111b24", textAlign: "right" }}>
                            <td style={{ textAlign: "left", padding: "3px 4px", color: "#ff6b8b", fontWeight: "bold" }}>▲ RES · {w.type}</td>
                            <td style={{ padding: "3px 4px", color: "#e6edf3", fontWeight: "bold" }}>{fmtNum(w.price, dec)}</td>
                            <td style={{ padding: "3px 4px", color: "#8ca5b5" }}>{fmtNum(w.dist_pts, dec, true)}p</td>
                            <td style={{ padding: "3px 4px", color: "#00d4ff" }}>{w.gex_formatted || "—"}</td>
                            <td style={{ padding: "3px 4px", color: (w.inst_delta || 0) >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                            <td style={{ padding: "3px 4px", color: "#9fb4c4" }}>{w.status}</td>
                        </tr>
                    ))}
                    <tr style={{ background: "rgba(0, 212, 255, 0.12)", textAlign: "center", fontWeight: "bold" }}>
                        <td colSpan={6} style={{ padding: "4px", color: "#00d4ff" }}>
                            ◄ PREÇO SPOT ATUAL: {fmtNum(payload.last_price, dec)} (VWAP: {fmtNum(payload.vwap, dec)}) ►
                        </td>
                    </tr>
                    {supWalls.map((w, i) => (
                        <tr key={`s-${i}`} style={{ borderBottom: "1px solid #111b24", textAlign: "right" }}>
                            <td style={{ textAlign: "left", padding: "3px 4px", color: "#00e87a", fontWeight: "bold" }}>▼ SUP · {w.type}</td>
                            <td style={{ padding: "3px 4px", color: "#e6edf3", fontWeight: "bold" }}>{fmtNum(w.price, dec)}</td>
                            <td style={{ padding: "3px 4px", color: "#8ca5b5" }}>{fmtNum(w.dist_pts, dec, true)}p</td>
                            <td style={{ padding: "3px 4px", color: "#00d4ff" }}>{w.gex_formatted || "—"}</td>
                            <td style={{ padding: "3px 4px", color: (w.inst_delta || 0) >= 0 ? "#00e87a" : "#ff3860" }}>{fmtNum(w.inst_delta, 0, true)}</td>
                            <td style={{ padding: "3px 4px", color: "#9fb4c4" }}>{w.status}</td>
                        </tr>
                    ))}
                </tbody>
            </table>

            {/* Gráfico CVD Institucional vs Varejo vs Dealers */}
            <MiniSvgChart
                series={ca.m5_dealer_vs_flow_series || []}
                keys={["cvd_inst", "cum_dealer_hedge", "cvd_retail"]}
                colors={["#00e87a", "#c8a444", "#00d4ff"]}
                labels={["CVD Institucional", "Hedge Acum. Dealers (GEX)", "CVD Varejo"]}
                height={110}
            />
        </div>
    );
}

/* ── COMPONENTE PRINCIPAL EXPORTADO ────────────────────────────────────────── */
export default function IntradayCompassPanel({ compassData, mode = "COCKPIT", onChangeMode }) {
    const [selectedAsset, setSelectedAsset] = useState("WIN"); // "WIN" | "WDO" | "DUAL"

    if (!compassData || !compassData.WIN) {
        return (
            <div style={{
                background: "#0b121a",
                border: "1px solid #1c2c3b",
                borderRadius: 8,
                padding: 20,
                color: "#8ca5b5",
                fontSize: 12,
                textAlign: "center",
            }}>
                Inicializando Cockpit Operacional Intradiário (ProfitChart CSV + MT5 Live Ticks + GEX Dealers + Opções Ao Vivo)...
            </div>
        );
    }

    const winP = compassData.WIN;
    const wdoP = compassData.WDO;
    const cb = compassData.caminho_b || winP?.caminho_b || {};
    const optComp = cb.options_compass || {};
    const volSurf = cb.volatility_surface || {};
    const optWins = cb.windows || {};
    const bova = cb.bova11 || {};

    // Cartão Seletor de Ativo no Topo (WINZ26 vs WDOX26)
    const renderAssetSelectorButton = (symKey, p) => {
        if (!p) return null;
        const isSel = selectedAsset === symKey;
        const dec = symKey === "WDO" ? 1 : 0;
        const ca = p.caminho_a || {};
        const cm = ca.confluence_matrix || {};
        const sc = ca.signals_scorecard || {};
        const badge = stateBadgeStyle(cm.operational_state);
        const accent = symKey === "WIN" ? "#00d4ff" : "#c8a444";

        return (
            <div
                key={symKey}
                onClick={() => setSelectedAsset(symKey)}
                style={{
                    flex: 1,
                    minWidth: 300,
                    background: isSel ? "rgba(0, 212, 255, 0.09)" : "#0b121a",
                    border: isSel ? `2px solid ${accent}` : "1px solid #18293a",
                    borderRadius: 9,
                    padding: "10px 14px",
                    cursor: "pointer",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: 10,
                    transition: "all 0.2s ease",
                    boxShadow: isSel ? `0 0 16px ${accent}22` : "none",
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{
                        fontSize: 13,
                        fontWeight: "bold",
                        color: isSel ? "#081018" : accent,
                        background: isSel ? accent : `${accent}1a`,
                        border: `1px solid ${accent}`,
                        padding: "4px 10px",
                        borderRadius: 5,
                    }}>
                        {symKey === "WIN" ? "🇧🇷 MINI ÍNDICE" : "💵 MINI DÓLAR"} · {p.active_contract}
                    </span>
                    <div>
                        <div style={{ fontSize: 20, fontWeight: "bold", color: "#ffffff", lineHeight: 1.1 }}>
                            {fmtNum(p.last_price, dec)}
                        </div>
                        <div style={{ fontSize: 9, color: "#7f96a8" }}>
                            VWAP: {fmtNum(p.vwap, dec)}
                        </div>
                    </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <div style={{ textAlign: "right" }}>
                        <div style={{
                            fontSize: 10,
                            fontWeight: "bold",
                            color: badge.color,
                            background: badge.bg,
                            border: `1px solid ${badge.border}66`,
                            padding: "3px 8px",
                            borderRadius: 4,
                            display: "inline-block",
                        }}>
                            {cm.operational_bias || "AGUARDANDO"}
                        </div>
                        <div style={{ fontSize: 9, color: "#9fb4c4", marginTop: 3 }}>
                            Placar Hoje: <strong style={{ color: "#00e87a" }}>{sc.valid_signals || 0}✅</strong> / <strong style={{ color: "#ff6b8b" }}>{sc.invalid_signals || 0}❌</strong> ({fmtNum(sc.win_rate_pct, 1)}%)
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    return (
        <div style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
        }}>
            {/* ── SELETOR RÁPIDO DE ATIVO NO TOPO (WINZ26 vs WDOX26) ──────────────── */}
            {mode === "COCKPIT" && (
                <div style={{ display: "flex", gap: 12, alignItems: "stretch", flexWrap: "wrap" }}>
                    {renderAssetSelectorButton("WIN", winP)}
                    {renderAssetSelectorButton("WDO", wdoP)}
                    <button
                        onClick={() => setSelectedAsset(selectedAsset === "DUAL" ? "WIN" : "DUAL")}
                        style={{
                            padding: "0 16px",
                            fontSize: 10,
                            fontFamily: "monospace",
                            fontWeight: "bold",
                            background: selectedAsset === "DUAL" ? "rgba(0, 232, 122, 0.18)" : "#0b121a",
                            border: selectedAsset === "DUAL" ? "2px solid #00e87a" : "1px solid #18293a",
                            color: selectedAsset === "DUAL" ? "#00e87a" : "#8ca5b5",
                            borderRadius: 9,
                            cursor: "pointer",
                        }}
                        title="Ver WIN e WDO simultaneamente"
                    >
                        ⚖️ {selectedAsset === "DUAL" ? "Visão Dupla Ativa" : "Ver WIN + WDO Juntos"}
                    </button>
                </div>
            )}

            {/* ── MODO 1: COCKPIT OPERACIONAL (1 TELA LIMPA E INTUITIVA) ──────────── */}
            {mode === "COCKPIT" && (
                selectedAsset === "DUAL" ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                        <SingleAssetCockpitView
                            symKey="WIN"
                            payload={winP}
                            cbData={cb}
                            onOpenRaioX={() => onChangeMode && onChangeMode("RAIO_X")}
                        />
                        <SingleAssetCockpitView
                            symKey="WDO"
                            payload={wdoP}
                            cbData={null}
                            onOpenRaioX={() => onChangeMode && onChangeMode("RAIO_X")}
                        />
                    </div>
                ) : (
                    <SingleAssetCockpitView
                        symKey={selectedAsset}
                        payload={selectedAsset === "WIN" ? winP : wdoP}
                        cbData={selectedAsset === "WIN" ? cb : null}
                        onOpenRaioX={() => onChangeMode && onChangeMode("RAIO_X")}
                    />
                )
            )}

            {/* ── MODO 2: RAIO-X DE DADOS (TABELAS COMPLETAS PROFIT + GRADE OPÇÕES) ── */}
            {mode === "RAIO_X" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                        <RaioXAssetCard symKey="WIN" payload={winP} />
                        <RaioXAssetCard symKey="WDO" payload={wdoP} />
                    </div>

                    {/* Grade Completa de Opções BOVA11 */}
                    {cb && cb.ok && (
                        <div style={{
                            background: "#0b121a",
                            border: "1px solid #18293a",
                            borderRadius: 8,
                            padding: 12,
                            display: "flex",
                            flexDirection: "column",
                            gap: 10,
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, borderBottom: "1px solid #16232f", paddingBottom: 8 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                    <span style={{
                                        fontSize: 11,
                                        fontWeight: "bold",
                                        color: "#00e87a",
                                        background: "rgba(0,232,122,0.12)",
                                        border: "1px solid #00e87a44",
                                        padding: "3px 8px",
                                        borderRadius: 4,
                                    }}>
                                        🎯 RADAR AO VIVO DA GRADE DE OPÇÕES (BOVA11 → WIN)
                                    </span>
                                    <span style={{ fontSize: 11, color: "#e6edf3", fontWeight: "bold" }}>
                                        BOVA11 Spot: R$ {fmtNum(bova.spot, 2)} ({fmtNum(bova.change_pct, 2, true)}%)
                                    </span>
                                    <span style={{ fontSize: 9, color: "#7f96a8" }}>
                                        Fator WIN/BOVA11: <strong>{fmtNum(bova.win_ibov_ratio, 1)}x</strong> · {optComp.monitored_series_count} séries líquidas
                                    </span>
                                </div>
                                <span style={{
                                    fontSize: 10,
                                    fontWeight: "bold",
                                    padding: "2px 8px",
                                    borderRadius: 4,
                                    background: `${scoreColor(optComp.score)}1a`,
                                    border: `1px solid ${scoreColor(optComp.score)}66`,
                                    color: scoreColor(optComp.score),
                                }}>
                                    Score Opções: {fmtNum(optComp.score, 1, true)} · {optComp.verdict}
                                </span>
                            </div>

                            {/* Superfície de Volatilidade Implícita (Black-Scholes) + PCR */}
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8 }}>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>IV ATM (NO DINHEIRO)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#00d4ff" }}>{fmtNum(volSurf.atm_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>IV PUT 25Δ (OTM)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#ff6b8b" }}>{fmtNum(volSurf.put_25d_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>IV CALL 25Δ (OTM)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#00e87a" }}>{fmtNum(volSurf.call_25d_iv_pct, 2)}%</div>
                                </div>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>SKEW 25Δ (PUT − CALL)</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#c8a444" }}>{fmtNum(volSurf.skew_25d_pct, 2, true)}%</div>
                                </div>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>PCR VOLUME TOTAL</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: "#e6edf3" }}>{fmtNum(optComp.pcr_total_volume, 2)}</div>
                                </div>
                                <div style={{ background: "#070c12", padding: "6px 8px", borderRadius: 5, border: "1px solid #15222e" }}>
                                    <div style={{ fontSize: 8, color: "#657d8f" }}>PCR COMPRA AGRESSIVA</div>
                                    <div style={{ fontSize: 13, fontWeight: "bold", color: (optComp.pcr_aggressive_buy || 0) > 1.15 ? "#ff3860" : "#00e87a" }}>
                                        {fmtNum(optComp.pcr_aggressive_buy, 2)}
                                    </div>
                                </div>
                            </div>

                            {/* Top 12 Séries de Opções Mais Ativas */}
                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 8.5 }}>
                                <thead>
                                    <tr style={{ color: "#5c7487", borderBottom: "1px solid #16232f", textAlign: "right" }}>
                                        <th style={{ textAlign: "left", padding: "4px" }}>SÉRIE</th>
                                        <th style={{ textAlign: "center", padding: "4px" }}>TIPO</th>
                                        <th style={{ padding: "4px" }}>STRIKE BOVA</th>
                                        <th style={{ padding: "4px", color: "#00d4ff" }}>≈ STRIKE WIN</th>
                                        <th style={{ padding: "4px" }}>BID / ASK</th>
                                        <th style={{ padding: "4px" }}>IV%</th>
                                        <th style={{ padding: "4px" }}>DELTA (Δ)</th>
                                        <th style={{ padding: "4px" }}>NEGÓCIOS</th>
                                        <th style={{ padding: "4px" }}>SALDO AGRESSÃO</th>
                                        <th style={{ padding: "4px" }}>FLUXO DELTA EQUIV.</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(cb.most_active_options || []).slice(0, 12).map(row => {
                                        const isCall = row.type === "CALL";
                                        const isBullImpact = (row.delta_equiv_flow || 0) > 0;
                                        return (
                                            <tr key={row.symbol} style={{ borderBottom: "1px solid #111b24", textAlign: "right" }}>
                                                <td style={{ textAlign: "left", padding: "4px", fontWeight: "bold", color: "#e6edf3" }}>{row.symbol}</td>
                                                <td style={{ textAlign: "center", padding: "4px", color: isCall ? "#00d4ff" : "#ff6b8b", fontWeight: "bold" }}>{row.type}</td>
                                                <td style={{ padding: "4px", color: "#b1c4d4" }}>R$ {fmtNum(row.strike_bova, 1)}</td>
                                                <td style={{ padding: "4px", color: "#00d4ff", fontWeight: "bold" }}>{fmtNum(row.equiv_win_strike, 0)}</td>
                                                <td style={{ padding: "4px", color: "#8ca5b5" }}>{fmtNum(row.bid, 2)} / {fmtNum(row.ask, 2)}</td>
                                                <td style={{ padding: "4px", color: "#c8a444" }}>{fmtNum(row.iv_pct, 1)}%</td>
                                                <td style={{ padding: "4px", color: "#b1c4d4" }}>{fmtNum(row.delta, 2, true)}</td>
                                                <td style={{ padding: "4px", color: "#8ca5b5" }}>{fmtNum(row.deals, 0)}</td>
                                                <td style={{ padding: "4px", color: row.net_aggr_vol >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                                    {fmtNum(row.net_aggr_vol, 0, true)} ({fmtNum(row.imbalance_pct, 1, true)}%)
                                                </td>
                                                <td style={{ padding: "4px", color: isBullImpact ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                                                    {fmtNum(row.delta_equiv_flow, 0, true)}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
