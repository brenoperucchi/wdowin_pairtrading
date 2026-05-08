// TradingGuide — Reference guide for the pair trading signals
function Row({ signal, label, color }) {
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "2px 0" }}>
            <span style={{
                display: "inline-block", width: 8, height: 8, borderRadius: 2,
                background: color, flexShrink: 0, boxShadow: `0 0 4px ${color}44`,
            }} />
            <span style={{ fontSize: 9, color: "#6f8a9c", width: 60, flexShrink: 0 }}>{signal}</span>
            <span style={{ fontSize: 9, color: "#8ca5b5" }}>{label}</span>
        </div>
    );
}

export default function TradingGuide() {
    return (
        <div style={{
            background: "#0c1218", borderRadius: 8, padding: "10px 14px",
            border: "1px solid #1a2530",
        }}>
            <div style={{
                fontSize: 9, color: "#c8a444", fontWeight: "bold", letterSpacing: 3,
                marginBottom: 8, paddingBottom: 4, borderBottom: "1px solid #1a253066",
            }}>
                GUIA RÁPIDO
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div>
                    <div style={{ fontSize: 8, color: "#4a6070", letterSpacing: 2, marginBottom: 4 }}>ENTRADAS</div>
                    <Row signal="Z ≥ +1.4" label="VENDE WIN" color="#ff3860" />
                    <Row signal="Z ≤ −1.4" label="COMPRA WIN" color="#00e87a" />
                    <Row signal="|Z| ≥ 1.2" label="Zona de Divergência" color="#f5a623" />
                    <Row signal="|Z| < 1.2" label="Neutro (aguardar)" color="#4a6070" />
                    <Row signal="|Z| ≥ 4.0" label="Anomalia (não operar)" color="#ff3860" />
                </div>
                <div>
                    <div style={{ fontSize: 8, color: "#4a6070", letterSpacing: 2, marginBottom: 4 }}>SAÍDAS</div>
                    <Row signal="ALVO" label="Z retorna ao zero" color="#00e87a" />
                    <Row signal="STOP" label="Z expande contra" color="#ff3860" />
                    <Row signal="B/E" label="Proteção após lucro" color="#f5a623" />
                    <Row signal="FORCE" label="Fechamento 15:00" color="#8ca5b5" />
                </div>
            </div>
            <div style={{ marginTop: 6, fontSize: 8, color: "#2a3a4a", borderTop: "1px solid #1a253044", paddingTop: 4 }}>
                Consenso = WDO + DI atingem gatilho simultaneamente · NWE = filtro de tendência intraday
            </div>
        </div>
    );
}
