import { useState, useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import { createChart, LineSeries, LineStyle, CrosshairMode } from "lightweight-charts";

const Y_AXIS_WIDTH = 38;

const FlowScoreChart = forwardRef(({ history = [], smoothing = 3, onSmoothingChange, weights = { fln: 40, pers: 30, conc: 20, abs: 10 }, onWeightsChange }, ref) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRefs = useRef({});

    useImperativeHandle(ref, () => ({
        getChart: () => chartRef.current,
        getMainSeries: () => seriesRefs.current.flowSeries,
    }));

    const [showSettings, setShowSettings] = useState(false);

    const handleSliderChange = (factor, newValue) => {
        const otherFactors = ["fln", "pers", "conc", "abs"].filter(f => f !== factor);
        const otherSum = otherFactors.reduce((sum, f) => sum + weights[f], 0);
        const remainingValue = 100 - newValue;
        
        let newWeights = { ...weights, [factor]: newValue };
        
        if (otherSum > 0) {
            otherFactors.forEach(f => {
                newWeights[f] = Math.round((weights[f] / otherSum) * remainingValue);
            });
        } else {
            otherFactors.forEach(f => {
                newWeights[f] = Math.round(remainingValue / 3);
            });
        }
        
        const finalSum = newWeights.fln + newWeights.pers + newWeights.conc + newWeights.abs;
        const diff = 100 - finalSum;
        if (diff !== 0) {
            newWeights[otherFactors[0]] += diff;
        }
        
        if (onWeightsChange) {
            onWeightsChange(newWeights);
        }
    };

    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: "solid", color: "#0c1218" },
                textColor: "#4a6070",
                fontSize: 9,
            },
            localization: {
                timeFormatter: (time) => {
                    const d = new Date(time * 1000);
                    return String(d.getUTCHours()).padStart(2, "0") + ":" + String(d.getUTCMinutes()).padStart(2, "0");
                },
                priceFormatter: (price) => {
                    return Math.round(price).toString();
                }
            },
            grid: {
                vertLines: { visible: false },
                horzLines: { visible: false },
            },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: { color: "#c8a444", width: 1, style: LineStyle.Solid, labelBackgroundColor: "#c8a444" },
                horzLine: { visible: true, labelVisible: true, labelBackgroundColor: "#c8a444" },
            },
            timeScale: {
                visible: true,
                timeVisible: true,
                secondsVisible: false,
                tickMarkFormatter: (time) => {
                    const d = new Date(time * 1000);
                    return String(d.getUTCHours()).padStart(2, "0") + ":" + String(d.getUTCMinutes()).padStart(2, "0");
                },
            },
            rightPriceScale: {
                borderColor: "#1a2530",
                scaleMargins: { top: 0.1, bottom: 0.1 },
                minimumWidth: 60,
                autoScale: true,
            },
            autoSize: true,
        });
        chartRef.current = chart;

        const flowSeries = chart.addSeries(LineSeries, {
            color: "#f5a623",
            lineWidth: 2.5,
            crosshairMarkerVisible: true,
            priceLineVisible: false,
            autoscaleInfoProvider: () => ({
                priceRange: {
                    minValue: -105,
                    maxValue: 105,
                },
            }),
        });

        // Reference lines
        flowSeries.createPriceLine({
            price: 0,
            color: "#21262d",
            lineWidth: 1.0,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: "0",
        });

        flowSeries.createPriceLine({
            price: 40,
            color: "rgba(0,232,122,0.3)",
            lineWidth: 1.0,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "+40 COMPRA",
        });

        flowSeries.createPriceLine({
            price: -40,
            color: "rgba(255,56,96,0.3)",
            lineWidth: 1.0,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "-40 VENDA",
        });

        seriesRefs.current = { flowSeries };

        return () => {
            chart.remove();
        };
    }, []);

    useEffect(() => {
        if (!chartRef.current || !history || history.length === 0) return;

        const { flowSeries } = seriesRefs.current;

        // Ensure we filter out duplicates and sort by timestamp
        const formattedData = history.map(d => ({
            time: d.time,
            value: d.value,
            color: d.color
        }));

        const sortedData = formattedData
            .sort((a, b) => a.time - b.time)
            .filter((v, i, arr) => i === 0 || v.time > arr[i - 1].time);

        flowSeries.setData(sortedData);

    }, [history]);

    return (
        <div style={{ background: "#0c1218", borderRadius: "0 0 8px 8px", paddingBottom: 6, position: "relative" }}>
            <div style={{
                display: "flex", alignItems: "center", gap: 14, padding: "6px 12px 2px",
                paddingLeft: Y_AXIS_WIDTH,
                borderTop: "1px solid #1a2530", flexWrap: "wrap",
            }}>
                <span style={{ fontSize: 9, fontWeight: "bold", color: "#6f8a9c", letterSpacing: 2 }}>FLOW SCORE SINTÉTICO (WIN) (M5)</span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, background: "#00e87a", borderRadius: "50%" }} />
                    <span style={{ fontSize: 9, color: "#00e87a" }}>Compra (&gt;= 40)</span>
                </span>
                <span style={{ display: "inline-block", width: 1, height: 12, background: "#1c2e3a" }} />
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, background: "#ff3860", borderRadius: "50%" }} />
                    <span style={{ fontSize: 9, color: "#ff3860" }}>Venda (&lt;= -40)</span>
                </span>
                <span style={{ display: "inline-block", width: 1, height: 12, background: "#1c2e3a" }} />
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, background: "#f5a623", borderRadius: "50%" }} />
                    <span style={{ fontSize: 9, color: "#f5a623" }}>Neutro</span>
                </span>
                <span style={{ display: "inline-block", width: 1, height: 12, background: "#1c2e3a" }} />
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 8, color: "#6f8a9c", fontWeight: "bold", letterSpacing: 1 }}>SUAVIZAÇÃO:</span>
                    <div style={{ display: "flex", gap: 3 }}>
                        {[1, 3, 5, 10].map(val => (
                            <button
                                key={val}
                                onClick={() => onSmoothingChange && onSmoothingChange(val)}
                                style={{
                                    background: smoothing === val ? "#c8a444" : "rgba(200, 164, 68, 0.1)",
                                    border: `1px solid ${smoothing === val ? "#c8a444" : "rgba(200, 164, 68, 0.25)"}`,
                                    color: smoothing === val ? "#0c1218" : "#c8a444",
                                    fontSize: 8,
                                    fontWeight: "bold",
                                    padding: "2px 6px",
                                    borderRadius: 3,
                                    cursor: "pointer",
                                    transition: "all 0.2s",
                                }}
                            >
                                {val === 1 ? "OFF" : `${val} M5`}
                            </button>
                        ))}
                    </div>
                </span>
                <span style={{ display: "inline-block", width: 1, height: 12, background: "#1c2e3a" }} />
                <button
                    onClick={() => setShowSettings(!showSettings)}
                    style={{
                        background: showSettings ? "#c8a444" : "rgba(200, 164, 68, 0.1)",
                        border: `1px solid ${showSettings ? "#c8a444" : "rgba(200, 164, 68, 0.25)"}`,
                        color: showSettings ? "#0c1218" : "#c8a444",
                        fontSize: 8,
                        fontWeight: "bold",
                        padding: "2px 6px",
                        borderRadius: 3,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                        transition: "all 0.2s",
                    }}
                >
                    <span>⚙️</span> AJUSTAR PESOS
                </button>
            </div>
            {showSettings && (
                <div style={{
                    background: "#080c10",
                    borderBottom: "1px solid #1a2530",
                    padding: "10px 12px 12px",
                    paddingLeft: Y_AXIS_WIDTH,
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 8, fontWeight: "bold", color: "#6f8a9c", letterSpacing: 1 }}>AJUSTE DE PESOS DO SCORE SINTÉTICO (SOMA: 100%)</span>
                        <button 
                            onClick={() => onWeightsChange && onWeightsChange({ fln: 20, pers: 40, conc: 30, abs: 10 })}
                            style={{
                                background: "none", border: "none", color: "#8a6dff", fontSize: 8, fontWeight: "bold", cursor: "pointer", padding: 0
                            }}
                        >
                            RESTAURAR PADRÃO (20/40/30/10)
                        </button>
                    </div>
                    
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
                        {[
                            { key: "fln", label: "Fluxo Normalizado (FLN)", color: "#00e87a" },
                            { key: "pers", label: "Persistência (PERS)", color: "#8a6dff" },
                            { key: "conc", label: "Concentração (CONC)", color: "#00d4ff" },
                            { key: "abs", label: "Absorção (ABS)", color: "#ff3860" }
                        ].map(item => (
                            <div key={item.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, fontWeight: "bold" }}>
                                    <span style={{ color: "#4a6070" }}>{item.label}</span>
                                    <span style={{ color: item.color }}>{weights[item.key]}%</span>
                                </div>
                                <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    value={weights[item.key] || 0}
                                    onChange={(e) => handleSliderChange(item.key, parseInt(e.target.value))}
                                    style={{
                                        accentColor: item.color,
                                        width: "100%",
                                        height: 3,
                                        borderRadius: 2,
                                        cursor: "pointer",
                                    }}
                                />
                            </div>
                        ))}
                    </div>
                </div>
            )}
            <div ref={chartContainerRef} style={{ width: "100%", height: "220px", paddingLeft: Y_AXIS_WIDTH }} />
            {(!history || history.length === 0) && (
                <div style={{ position: "absolute", top: 25, left: 0, right: 0, bottom: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "#0c1218bb", zIndex: 10 }}>
                    <span style={{ color: "#4a6070", fontSize: 12, letterSpacing: 1 }}>AGUARDANDO DADOS DE FLUXO REAL-TIME</span>
                </div>
            )}
        </div>
    );
});

FlowScoreChart.displayName = "FlowScoreChart";
export default FlowScoreChart;
