import React, { useState, useMemo } from "react";

const BROKER_LABELS = {
    "XP": { name: "XP Investimentos", desc: "Varejo majoritário" },
    "UBS": { name: "UBS", desc: "Institucional Gringo" },
    "BTG": { name: "BTG Pactual", desc: "Institucional Nacional" },
    "IDEAL": { name: "Ideal Corretora", desc: "HFT / Market Maker" },
    "GENIAL": { name: "Genial", desc: "Varejo secundário" },
    "JPMORGAN": { name: "JP Morgan", desc: "Gringo Institucional" },
    "TULLETT": { name: "Tullett Prebon", desc: "Brokerage de Vol" },
    "MERRILL": { name: "Merrill Lynch", desc: "Gringo HFT" },
    "GOLDMAN": { name: "Goldman Sachs", desc: "HFT Global" },
    "MORGAN": { name: "Morgan Stanley", desc: "Gringo Institucional" },
    "CITI": { name: "Citigroup", desc: "Gringo Institucional" },
    "ITAU": { name: "Itaú Corretora", desc: "Institucional/Varejo" },
    "BRADESCO": { name: "Bradesco", desc: "Institucional/Varejo" }
};

const getFlowValue = (metrics, mode) => {
    if (!metrics) return 0;
    if (typeof metrics === "object") {
        const net = metrics.net || 0;
        const buy = metrics.buy || 0;
        const sell = metrics.sell || 0;
        if (mode === "agg") return buy - sell;
        if (mode === "abs") return net - (buy - sell);
        return net;
    }
    if (mode === "agg") return metrics;
    if (mode === "abs") return 0;
    return metrics;
};

const renderEfficiencyBar = (val) => {
    const absVal = Math.min(100, Math.abs(val));
    const isPositive = val >= 0;
    
    return (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: "100%", gap: 2, padding: "0 5px" }}>
            <span style={{ fontSize: 10, color: val === 0 ? "#8ca5b5" : (isPositive ? "#00e87a" : "#ff3860"), fontWeight: "bold" }}>
                {val === 0 ? "0.0%" : (isPositive ? `+${val}%` : `${val}%`)}
            </span>
            <div style={{ width: 90, height: 4, background: "#21262d", borderRadius: 2, position: "relative", overflow: "hidden" }}>
                <div 
                    style={{ 
                        position: "absolute",
                        left: isPositive ? "50%" : "auto",
                        right: isPositive ? "auto" : "50%",
                        width: `${absVal / 2}%`,
                        height: "100%",
                        background: isPositive ? "#00e87a" : "#ff3860",
                        borderRadius: 1
                    }}
                />
                <div style={{ position: "absolute", left: "50%", top: 0, width: 1, height: "100%", background: "#8ca5b5", opacity: 0.4 }} />
            </div>
        </div>
    );
};

const renderIAFGauge = (val) => {
    const angle = 270 + val * 0.9;
    const rad = (angle * Math.PI) / 180;
    const needleX = 50 + 28 * Math.cos(rad);
    const needleY = 50 + 28 * Math.sin(rad);
    
    let label = "NEUTRO";
    let color = "#8ca5b5";
    if (val > 50.0) {
        label = "FORTE COMPRA";
        color = "#00e87a";
    } else if (val > 20.0) {
        label = "COMPRA";
        color = "#a3e28c";
    } else if (val < -50.0) {
        label = "FORTE VENDA";
        color = "#ff3860";
    } else if (val < -20.0) {
        label = "VENDA";
        color = "#ff7b88";
    }
    
    return (
        <div style={{ background: "#0d1117", border: "1px solid #21262d", borderRadius: 6, padding: "10px 14px", display: "flex", flexDirection: "column", alignItems: "center", gap: 4, height: 110, position: "relative" }}>
            <span style={{ fontSize: 9, color: "#8ca5b5", fontWeight: "bold", letterSpacing: 0.5 }}>ACELERADOR DE PRESSÃO (IAF)</span>
            <div style={{ width: 110, height: 55, position: "relative", overflow: "hidden", marginTop: 5 }}>
                <svg viewBox="0 0 100 60" style={{ width: "100%", height: "100%" }}>
                    <path d="M 15 50 A 35 35 0 0 1 85 50" fill="none" stroke="#21262d" strokeWidth="6" strokeLinecap="round" />
                    <path d="M 15 50 A 35 35 0 0 1 36 26" fill="none" stroke="#ff3860" strokeWidth="3" opacity="0.3" />
                    <path d="M 36 26 A 35 35 0 0 1 64 26" fill="none" stroke="#8ca5b5" strokeWidth="3" opacity="0.3" />
                    <path d="M 64 26 A 35 35 0 0 1 85 50" fill="none" stroke="#00e87a" strokeWidth="3" opacity="0.3" />
                    <line x1="50" y1="50" x2={needleX.toFixed(1)} y2={needleY.toFixed(1)} stroke={color} strokeWidth="2.5" strokeLinecap="round" />
                    <circle cx="50" cy="50" r="4" fill="#f3f4f6" stroke="#0d1117" strokeWidth="1" />
                </svg>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1, marginTop: -5 }}>
                <span style={{ fontSize: 13, fontWeight: "bold", color: color }}>
                    {val > 0 ? `+${val}%` : `${val}%`}
                </span>
                <span style={{ fontSize: 8, color: "#6f8a9c", letterSpacing: 0.5, fontWeight: "bold" }}>
                    {label}
                </span>
            </div>
        </div>
    );
};

export default function BrokerFlowPanel({ flowData, dbHistory, activeSymbol, weights, setWeights, classifications, setClassifications, flowMode, setFlowMode }) {
    const symbol = activeSymbol ? (activeSymbol.includes("WDO") ? "WDO" : "WIN") : "WIN";
    const brokersList = [...new Set([...Object.keys(BROKER_LABELS), ...(flowData?.brokers || [])])];
    const flowMap = flowData?.flow?.[symbol] || {};
    const history = flowData?.history || [];
    const lastUpdate = flowData?.last_update?.[symbol] || "SIMULADO";
    const efficiencyMap = useMemo(() => flowData?.efficiency?.[symbol] || {}, [flowData, symbol]);
    const acceleratorVal = flowData?.accelerator?.[symbol] ?? 0.0;


    const [showGuide, setShowGuide] = useState(false);
    const [sortField, setSortField] = useState("none"); // "none", "net", "avg"
    const [sortAsc, setSortAsc] = useState(false);

    const handleSort = (field) => {
        if (sortField === field) {
            setSortAsc(!sortAsc);
        } else {
            setSortField(field);
            setSortAsc(false); // default to descending (highest balance/price first)
        }
    };

    const changeClassification = (broker, value) => {
        setClassifications(prev => ({
            ...prev,
            [broker]: value
        }));
        // Auto-link: smart -> CONTRA (-1), dummy -> A FAVOR (1), none -> OFF (0)
        const newWeight = value === "smart" ? -1 : (value === "dummy" ? 1 : 0);
        setWeights(prev => ({
            ...prev,
            [broker]: newWeight
        }));
    };

    const changeWeight = (broker, value) => {
        setWeights(prev => ({
            ...prev,
            [broker]: value
        }));
    };

    const sortedBrokersList = useMemo(() => {
        const list = [...brokersList];
        if (sortField === "none") return list;
        return list.sort((a, b) => {
            const metricsA = flowMap[a] || { net: 0, avg: 0.0 };
            const metricsB = flowMap[b] || { net: 0, avg: 0.0 };
            
            let valA = 0;
            let valB = 0;
            if (sortField === "net") {
                valA = getFlowValue(metricsA, flowMode);
                valB = getFlowValue(metricsB, flowMode);
            } else if (sortField === "avg") {
                valA = metricsA.avg;
                valB = metricsB.avg;
            } else if (sortField === "efficiency") {
                valA = efficiencyMap[a] || 0;
                valB = efficiencyMap[b] || 0;
            }
            
            if (valA < valB) return sortAsc ? -1 : 1;
            if (valA > valB) return sortAsc ? 1 : -1;
            return 0;
        });
    }, [brokersList, flowMap, sortField, sortAsc, flowMode, efficiencyMap]);

    // Calcular o fluxo atual líquido ponderado
    const currentDelta = useMemo(() => {
        let sum = 0;
        Object.keys(flowMap).forEach(b => {
            const val = getFlowValue(flowMap[b], flowMode);
            const w = weights[b] ?? 0;
            sum += val * w;
        });
        return sum;
    }, [flowMap, weights, flowMode]);

    // Calcular histórico de Delta Acumulado
    const deltaHistory = useMemo(() => {
        if (!dbHistory || dbHistory.length === 0) return [];

        // Build a time-indexed map from flowData.history snapshots
        const flowSnapMap = new Map();
        const flowHistArr = flowData?.history || [];
        flowHistArr.forEach(snap => {
            if (snap.time) flowSnapMap.set(snap.time, snap);
        });
        const flowTimes = [...flowSnapMap.keys()].sort();

        function findFlowForTime(barTime) {
            if (flowSnapMap.has(barTime)) return flowSnapMap.get(barTime);
            let best = null;
            for (let i = flowTimes.length - 1; i >= 0; i--) {
                if (flowTimes[i] <= barTime) {
                    best = flowSnapMap.get(flowTimes[i]);
                    break;
                }
            }
            return best;
        }

        const res = [];
        dbHistory.forEach((d, idx) => {
            if (!d.bar_time) return;

            // If this is a future empty bar (no price or z-score data)
            if (d.win_price == null && d.z == null) {
                res.push({
                    time: d.bar_time,
                    value: null,
                    idx: idx
                });
                return;
            }

            let snapFlow = null;
            const apiSnap = findFlowForTime(d.bar_time);
            if (apiSnap) {
                snapFlow = apiSnap[symbol] || {};
            }
            if (!snapFlow || Object.keys(snapFlow).length === 0) {
                snapFlow = d.flow?.[symbol] || {};
            }

            let sum = 0;
            Object.keys(snapFlow).forEach(b => {
                const val = getFlowValue(snapFlow[b], flowMode);
                const w = weights[b] ?? 0;
                sum += val * w;
            });
            
            res.push({
                time: d.bar_time,
                value: sum,
                idx: idx
            });
        });
        return res;
    }, [dbHistory, flowData, symbol, weights, flowMode]);

    // Determinar o regime de fluxo
    const flowRegime = useMemo(() => {
        const absVal = Math.abs(currentDelta);
        const limit = symbol === "WIN" ? 15000 : 1500;
        if (currentDelta > limit) {
            return { label: "FORTE COMPRADOR", color: "#00e87a", bg: "rgba(0, 232, 122, 0.1)" };
        } else if (currentDelta < -limit) {
            return { label: "FORTE VENDEDOR", color: "#ff3860", bg: "rgba(255, 56, 96, 0.1)" };
        }
        return { label: "FLUXO NEUTRO", color: "#8a9aaa", bg: "rgba(138, 154, 170, 0.08)" };
    }, [currentDelta, symbol]);

    // Renderização do gráfico SVG do Delta Acumulado
    const svgChart = useMemo(() => {
        const validHistory = deltaHistory.filter(d => d.value !== null);
        if (validHistory.length < 2) return null;
        
        const width = 500;
        const height = 110;
        const padding = 12;
        
        const values = validHistory.map(d => d.value);
        const maxVal = Math.max(...values, 5000);
        const minVal = Math.min(...values, -5000);
        const range = maxVal - minVal || 1;
        
        const totalBars = deltaHistory.length;
        
        const points = validHistory.map((d) => {
            const x = padding + (d.idx / (totalBars - 1)) * (width - 2 * padding);
            const y = padding + (1 - (d.value - minVal) / range) * (height - 2 * padding);
            return { x, y, val: d.value };
        });
        
        const pathData = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
        
        // Linha do zero
        const zeroY = padding + (1 - (0 - minVal) / range) * (height - 2 * padding);
        
        return (
            <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "100%", overflow: "visible" }}>
                {/* Linha do zero */}
                {zeroY >= padding && zeroY <= height - padding && (
                    <line x1={padding} y1={zeroY} x2={width - padding} y2={zeroY} stroke="#21262d" strokeDasharray="3,3" strokeWidth={1} />
                )}
                {/* Linha do Delta */}
                <path d={pathData} fill="none" stroke={currentDelta >= 0 ? "#00e87a" : "#ff3860"} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
                {/* Círculo do ponto mais recente */}
                {points.length > 0 && (
                    <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r={4.5} fill={currentDelta >= 0 ? "#00e87a" : "#ff3860"} />
                )}
            </svg>
        );
    }, [deltaHistory, currentDelta]);

    return (
        <div style={{ background: "#161b22", border: "1px solid #21262d", borderRadius: 8, padding: "16px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
            {/* Cabeçalho */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #21262d", paddingBottom: 10, flexWrap: "wrap", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 16, fontWeight: "bold", color: "#f3f4f6", letterSpacing: 1 }}>📊 FLUXO DE ORDENS & CORRETORAS</span>
                    <span style={{ fontSize: 10, background: "#0d1117", border: "1px solid #21262d", borderRadius: 4, padding: "2px 8px", color: "#8ca5b5" }}>
                        FONTE: {lastUpdate}
                    </span>
                </div>

                {/* Seletor de Modo de Fluxo */}
                <div style={{ display: "inline-flex", background: "#0d1117", border: "1px solid #21262d", borderRadius: 6, padding: 3, gap: 4 }}>
                    {[
                        { id: "agg", label: "Agressão" },
                        { id: "abs", label: "Absorção" },
                        { id: "net", label: "Saldo Líquido" }
                    ].map(mode => (
                        <button
                            key={mode.id}
                            onClick={() => setFlowMode(mode.id)}
                            style={{
                                background: flowMode === mode.id ? "rgba(200, 164, 68, 0.12)" : "transparent",
                                border: "none",
                                borderRadius: 4,
                                color: flowMode === mode.id ? "#c8a444" : "#8ca5b5",
                                fontSize: 10,
                                fontWeight: flowMode === mode.id ? "bold" : "normal",
                                padding: "5px 12px",
                                cursor: "pointer",
                                transition: "all 0.2s"
                            }}
                        >
                            {mode.label}
                        </button>
                    ))}
                </div>

                <button 
                    onClick={() => setShowGuide(!showGuide)} 
                    style={{ background: "transparent", border: "1px solid #38444d", borderRadius: 4, color: "#8ca5b5", fontSize: 10, padding: "5px 10px", cursor: "pointer", fontFamily: "monospace" }}
                >
                    {showGuide ? "FECHAR GUIA RTD" : "CONEXÃO PROFIT RTD"}
                </button>
            </div>

            {/* Guia do Profit RTD */}
            {showGuide && (
                <div style={{ background: "#0d1117", border: "1px solid #f5a62344", borderRadius: 6, padding: 14, fontSize: 11, display: "flex", flexDirection: "column", gap: 8, color: "#8ca5b5" }}>
                    <strong style={{ color: "#f5a623" }}>🔗 COMO CONECTAR AO SEU PROFIT SCALPER PRO</strong>
                    <p>Você pode sincronizar os saldos de corretoras do Profit em tempo real com este painel usando o nosso script de ponte.</p>
                    <div style={{ padding: "8px 12px", background: "#161b22", borderRadius: 4, border: "1px solid #21262d", fontFamily: "monospace", lineHeight: 1.5 }}>
                        <strong>Passo 1:</strong> Abra o Excel e crie a seguinte estrutura:<br/>
                        · Coluna A: Nome da Corretora (A2: <code>XP</code>, A3: <code>UBS</code>, etc.)<br/>
                        · Coluna B: WIN Saldo Líquido &rarr; <code>=RTD("Nelogica.Profit.RTD"; ; "WIN$N"; "XP"; "NET")</code><br/>
                        · Coluna C: WDO Saldo Líquido &rarr; <code>=RTD("Nelogica.Profit.RTD"; ; "WDO$N"; "XP"; "NET")</code><br/>
                        · Coluna D: WIN Vol. Compra &rarr; <code>=RTD("Nelogica.Profit.RTD"; ; "WIN$N"; "XP"; "COMPRAS")</code><br/>
                        · Coluna E: WIN Vol. Venda &rarr; <code>=RTD("Nelogica.Profit.RTD"; ; "WIN$N"; "XP"; "VENDAS")</code><br/>
                        · Coluna F: WDO Vol. Compra &rarr; <code>=RTD("Nelogica.Profit.RTD"; ; "WDO$N"; "XP"; "COMPRAS")</code><br/>
                        · Coluna G: WDO Vol. Venda &rarr; <code>=RTD("Nelogica.Profit.RTD"; ; "WDO$N"; "XP"; "VENDAS")</code><br/>
                        <em>(Nas fórmulas acima, substitua <code>WIN$N</code> / <code>WDO$N</code> pelo vencimento ativo, ex: <code>WINM26</code> / <code>WDON26</code>, e arraste as fórmulas para as linhas das outras corretoras)</em>
                    </div>
                    <div style={{ padding: "8px 12px", background: "#161b22", borderRadius: 4, border: "1px solid #21262d", fontFamily: "monospace" }}>
                        <strong>Passo 2:</strong> Deixe a planilha do Excel aberta no mesmo computador do Profit e rode o script no terminal:<br/>
                        <code style={{ color: "#00e87a" }}>.\.venv\Scripts\python.exe gex/engine/profit_rtd_bridge.py --mode excel</code>
                    </div>
                    <p style={{ fontSize: 10, color: "#f5a623" }}>* Enquanto o script não estiver rodando, o servidor rodará no modo de **Simulação de Fluxo** para manter o dashboard ativo.</p>
                </div>
            )}

            {/* Painel do Gráfico de Delta e Consenso */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 16 }}>
                {/* Gráfico SVG de Delta Acumulado */}
                <div style={{ background: "#0d1117", border: "1px solid #21262d", borderRadius: 6, padding: 12, display: "flex", flexDirection: "column", gap: 8, minHeight: 140 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#8ca5b5" }}>
                        <span>📈 DELTA ACUMULADO DO FLUXO (PONDERADO)</span>
                        <span style={{ color: currentDelta >= 0 ? "#00e87a" : "#ff3860", fontWeight: "bold" }}>
                            {currentDelta >= 0 ? `+${currentDelta.toLocaleString()}` : currentDelta.toLocaleString()}
                        </span>
                    </div>
                    <div style={{ flex: 1, position: "relative" }}>
                        {deltaHistory.length < 2 ? (
                            <div style={{ height: "100%", display: "flex", justifyContent: "center", alignItems: "center", fontSize: 10, color: "#3a5060" }}>
                                AGUARDANDO DADOS DE HISTÓRICO DE FLUXO...
                            </div>
                        ) : svgChart}
                    </div>
                </div>

                {/* Banner de Consenso */}
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {renderIAFGauge(acceleratorVal)}
                    <div style={{ flex: 1, background: flowRegime.bg, border: `1px solid ${flowRegime.color}33`, borderRadius: 6, padding: 16, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 10, color: "#8ca5b5", letterSpacing: 1 }}>
                            {flowMode === "agg" ? "REGIME DE AGRESSÃO" : flowMode === "abs" ? "REGIME DE ABSORÇÃO" : "REGIME DE SALDO LÍQUIDO"}
                        </span>
                        <span style={{ fontSize: 20, fontWeight: "bold", color: flowRegime.color, letterSpacing: 1, textAlign: "center" }}>
                            {flowRegime.label}
                        </span>
                        <span style={{ fontSize: 9, color: "#6f8a9c", textAlign: "center" }}>
                            Baseado no saldo acumulado das corretoras ativas
                        </span>
                    </div>
                </div>
            </div>

            {/* Tabela de Corretoras B3 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <span style={{ fontSize: 10, color: "#8ca5b5" }}>👥 CORRETORAS B3 - POSICIONAMENTO E AGRESSÃO (CONTRATOS LÍQUIDOS)</span>
                <div style={{ overflowX: "auto", border: "1px solid #21262d", borderRadius: 6, background: "#0d1117" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, textAlign: "left", minWidth: 600 }}>
                        <thead>
                            <tr style={{ borderBottom: "1px solid #21262d", background: "#161b22", color: "#8ca5b5" }}>
                                <th style={{ padding: "8px 14px", width: 140 }}>CORRETORA</th>
                                <th style={{ padding: "8px 10px", width: 130 }}>GRÁFICO 1 (GRUPO)</th>
                                <th style={{ padding: "8px 10px", width: 130 }}>GRÁFICO 2 (DIRETRIZ)</th>
                                <th 
                                    onClick={() => handleSort("efficiency")} 
                                    style={{ padding: "8px 10px", textAlign: "center", width: 125, cursor: "pointer", userSelect: "none" }}
                                >
                                    EFICIÊNCIA {sortField === "efficiency" ? (sortAsc ? "▲" : "▼") : "⇅"}
                                </th>
                                <th 
                                    onClick={() => handleSort("net")} 
                                    style={{ padding: "8px 10px", textAlign: "right", width: 120, cursor: "pointer", userSelect: "none" }}
                                >
                                    {flowMode === "agg" ? "AGRESSÃO LÍQ." : flowMode === "abs" ? "ABSORÇÃO LÍQ." : "SALDO LÍQUIDO"} {sortField === "net" ? (sortAsc ? "▲" : "▼") : "⇅"}
                                </th>
                                <th 
                                    onClick={() => handleSort("avg")} 
                                    style={{ padding: "8px 14px", textAlign: "right", width: 120, cursor: "pointer", userSelect: "none" }}
                                >
                                    MÉDIO {sortField === "avg" ? (sortAsc ? "▲" : "▼") : "⇅"}
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {sortedBrokersList.map(b => {
                                const info = BROKER_LABELS[b] || { name: b, desc: "Outra corretora" };
                                const metrics = flowMap[b] || { net: 0, avg: 0.0, vol: 0, buy: 0, sell: 0 };
                                const weight = weights[b] ?? 0;
                                const classification = classifications?.[b] || "none";
                                const brokerVal = getFlowValue(metrics, flowMode);
                                const efficiency = efficiencyMap[b] ?? 0;

                                return (
                                    <tr key={b} style={{ borderBottom: "1px solid #21262d", height: 36, transition: "background 0.2s" }}>
                                        {/* Nome */}
                                        <td style={{ padding: "6px 14px" }}>
                                            <div style={{ display: "flex", flexDirection: "column" }}>
                                                <strong style={{ color: "#f3f4f6" }}>{b}</strong>
                                                <span style={{ fontSize: 9, color: "#6f8a9c" }}>{info.name}</span>
                                            </div>
                                        </td>
                                        {/* Gráfico 1 (Grupo) */}
                                        <td style={{ padding: "6px 10px" }}>
                                            <div style={{ display: "inline-flex", background: "#0d1117", border: "1px solid #30363d", borderRadius: 4, padding: 2, gap: 2 }}>
                                                <button
                                                    onClick={() => changeClassification(b, "smart")}
                                                    style={{
                                                        background: classification === "smart" ? "rgba(0, 232, 122, 0.15)" : "transparent",
                                                        border: "none",
                                                        borderRadius: 3,
                                                        color: classification === "smart" ? "#00e87a" : "#4b5b6c",
                                                        fontSize: 8,
                                                        fontWeight: "bold",
                                                        padding: "4px 6px",
                                                        cursor: "pointer",
                                                        transition: "all 0.2s"
                                                    }}
                                                >
                                                    SMART
                                                </button>
                                                <button
                                                    onClick={() => changeClassification(b, "dummy")}
                                                    style={{
                                                        background: classification === "dummy" ? "rgba(255, 56, 96, 0.15)" : "transparent",
                                                        border: "none",
                                                        borderRadius: 3,
                                                        color: classification === "dummy" ? "#ff3860" : "#4b5b6c",
                                                        fontSize: 8,
                                                        fontWeight: "bold",
                                                        padding: "4px 6px",
                                                        cursor: "pointer",
                                                        transition: "all 0.2s"
                                                    }}
                                                >
                                                    DUMMY
                                                </button>
                                                <button
                                                    onClick={() => changeClassification(b, "none")}
                                                    style={{
                                                        background: classification === "none" ? "rgba(138, 154, 170, 0.15)" : "transparent",
                                                        border: "none",
                                                        borderRadius: 3,
                                                        color: classification === "none" ? "#f3f4f6" : "#4b5b6c",
                                                        fontSize: 8,
                                                        fontWeight: "bold",
                                                        padding: "4px 6px",
                                                        cursor: "pointer",
                                                        transition: "all 0.2s"
                                                    }}
                                                >
                                                    OFF
                                                </button>
                                            </div>
                                        </td>
                                        {/* Gráfico 2 (Diretriz) */}
                                        <td style={{ padding: "6px 10px" }}>
                                            <div style={{ display: "inline-flex", background: "#0d1117", border: "1px solid #30363d", borderRadius: 4, padding: 2, gap: 2 }}>
                                                <button
                                                    onClick={() => changeWeight(b, 1)}
                                                    style={{
                                                        background: weight === 1 ? "rgba(0, 232, 122, 0.15)" : "transparent",
                                                        border: "none",
                                                        borderRadius: 3,
                                                        color: weight === 1 ? "#00e87a" : "#4b5b6c",
                                                        fontSize: 8,
                                                        fontWeight: "bold",
                                                        padding: "4px 6px",
                                                        cursor: "pointer",
                                                        transition: "all 0.2s"
                                                    }}
                                                >
                                                    FAVOR
                                                </button>
                                                <button
                                                    onClick={() => changeWeight(b, -1)}
                                                    style={{
                                                        background: weight === -1 ? "rgba(255, 56, 96, 0.15)" : "transparent",
                                                        border: "none",
                                                        borderRadius: 3,
                                                        color: weight === -1 ? "#ff3860" : "#4b5b6c",
                                                        fontSize: 8,
                                                        fontWeight: "bold",
                                                        padding: "4px 6px",
                                                        cursor: "pointer",
                                                        transition: "all 0.2s"
                                                    }}
                                                >
                                                    CONTRA
                                                </button>
                                                <button
                                                    onClick={() => changeWeight(b, 0)}
                                                    style={{
                                                        background: weight === 0 ? "rgba(138, 154, 170, 0.15)" : "transparent",
                                                        border: "none",
                                                        borderRadius: 3,
                                                        color: weight === 0 ? "#f3f4f6" : "#4b5b6c",
                                                        fontSize: 8,
                                                        fontWeight: "bold",
                                                        padding: "4px 6px",
                                                        cursor: "pointer",
                                                        transition: "all 0.2s"
                                                    }}
                                                >
                                                    OFF
                                                </button>
                                            </div>
                                        </td>
                                        {/* Eficiência */}
                                        <td style={{ padding: "6px 10px", textAlign: "center" }}>
                                            {renderEfficiencyBar(efficiency)}
                                        </td>
                                        {/* Valor do Fluxo (Modo Ativo) */}
                                        <td style={{ padding: "6px 10px", textAlign: "right", color: brokerVal > 0 ? "#00e87a" : brokerVal < 0 ? "#ff3860" : "#8ca5b5", fontWeight: "bold" }}>
                                            {brokerVal > 0 ? `+${brokerVal.toLocaleString()}` : brokerVal.toLocaleString()}
                                        </td>
                                        {/* Média */}
                                        <td style={{ padding: "6px 14px", textAlign: "right", color: "#8ca5b5" }}>
                                            {metrics.avg > 0 ? metrics.avg.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
