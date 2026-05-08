// RegimeHealthPanel — Shows regime health for WDO and DI
function Gauge({ label, value, status, color }) {
    return (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "3px 0" }}>
            <span style={{ fontSize: 9, color: "#6f8a9c", letterSpacing: 1 }}>{label}</span>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 13, fontWeight: "bold", color: color || "#8ca5b5", fontFamily: "monospace" }}>
                    {typeof value === "number" ? value.toFixed(3) : value ?? "—"}
                </span>
                {status && (
                    <span style={{
                        fontSize: 8, color: "#0c1218", background: color, fontWeight: "bold",
                        padding: "1px 5px", borderRadius: 3, letterSpacing: 0.5,
                    }}>{status}</span>
                )}
            </div>
        </div>
    );
}

function Gate({ label, gate }) {
    if (!gate) return null;
    const isOpen = gate.open;
    const c = isOpen ? "#00e87a" : "#ff3860";
    return (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "3px 0" }}>
            <span style={{ fontSize: 9, color: "#6f8a9c", letterSpacing: 1 }}>{label}</span>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{
                    display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: c,
                    boxShadow: `0 0 6px ${c}66`,
                }} />
                <span style={{ fontSize: 10, fontWeight: "bold", color: c }}>
                    {isOpen ? "ABERTO" : "FECHADO"}
                </span>
                <span style={{ fontSize: 8, color: "#4a6070" }}>({gate.trace_ratio}x)</span>
            </div>
        </div>
    );
}

export default function RegimeHealthPanel({ kalmanZ, kalmanBetaHealth, diZ, diBetaHealth, diRhoHealth, johWdoGate, johDiGate }) {
    return (
        <div style={{
            display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0,
            background: "#0c1218", borderRadius: 8, overflow: "hidden",
            border: "1px solid #1a2530",
        }}>
            {/* WDO column */}
            <div style={{ padding: "10px 14px", borderRight: "1px solid #1a2530" }}>
                <div style={{
                    fontSize: 9, color: "#c8a444", fontWeight: "bold", letterSpacing: 3,
                    marginBottom: 8, paddingBottom: 4, borderBottom: "1px solid #1a253066",
                }}>WDO</div>
                <Gauge
                    label="Z-SCORE"
                    value={kalmanZ}
                    color={Math.abs(kalmanZ || 0) >= 1.4 ? (kalmanZ > 0 ? "#ff3860" : "#00e87a") : "#8ca5b5"}
                />
                {kalmanBetaHealth && (
                    <Gauge label="BETA Δ%" value={kalmanBetaHealth.delta_pct} status={kalmanBetaHealth.status} color={kalmanBetaHealth.color} />
                )}
                <Gate label="JOHANSEN" gate={johWdoGate} />
            </div>

            {/* DI column */}
            <div style={{ padding: "10px 14px" }}>
                <div style={{
                    fontSize: 9, color: "#8a6dff", fontWeight: "bold", letterSpacing: 3,
                    marginBottom: 8, paddingBottom: 4, borderBottom: "1px solid #1a253066",
                }}>DI</div>
                <Gauge
                    label="Z-SCORE"
                    value={diZ}
                    color={Math.abs(diZ || 0) >= 1.4 ? (diZ > 0 ? "#ff3860" : "#00e87a") : "#8ca5b5"}
                />
                {diBetaHealth && (
                    <Gauge label="BETA Δ%" value={diBetaHealth.delta_pct} status={diBetaHealth.status} color={diBetaHealth.color} />
                )}
                {diRhoHealth && (
                    <Gauge label="ρ" value={diRhoHealth.value} status={diRhoHealth.status} color={diRhoHealth.color} />
                )}
                <Gate label="JOHANSEN" gate={johDiGate} />
            </div>
        </div>
    );
}
