// SetupMatadorPanel.jsx — Shows the active Setup Matador configuration
export default function SetupMatadorPanel({ tradeEngine }) {
  const action = tradeEngine?.action || "WAIT";
  const holding = tradeEngine?.holding || false;
  const exitReason = tradeEngine?.exit_reason;
  const pnl = tradeEngine?.pnl;

  const statusLabel = holding ? "POSIÇÃO ABERTA"
    : action === "HMM_BLOCKED" ? "IA BLOQUEANDO"
      : action === "ANOMALY" ? "ANOMALIA"
        : action === "BUY_WIN" ? "COMPRA WIN ABERTA"
          : action === "SELL_WIN" ? "VENDA WIN ABERTA"
            : action === "CLOSE" ? `FECHADO (${exitReason})`
              : "AGUARDANDO";

  const statusColor = holding ? "#f5a623"
    : action === "HMM_BLOCKED" ? "#ff9800"
      : action === "ANOMALY" ? "#ff3860"
        : (action === "BUY_WIN" || action === "SELL_WIN") ? "#00e87a"
          : action === "CLOSE" ? "#00d4ff"
            : "#5a7080";

  return (
    <div style={{
      background: "#0a0e12",
      border: "1px solid #c8a44433",
      borderTop: "2px solid #c8a444",
      borderRadius: 8,
      padding: "14px 18px",
      marginTop: 16,
      resize: "vertical",
      overflow: "hidden",
      minHeight: 150
    }}>
      <div style={{
        fontSize: 9, color: "#c8a444", letterSpacing: 3, marginBottom: 12,
        display: "flex", justifyContent: "space-between", alignItems: "center"
      }}>
        <span>SETUP MATADOR — CONFIGURAÇÃO ATIVA</span>
        <span style={{ fontSize: 8, color: "#5a7080", letterSpacing: 1 }}>BACKTEST VALIDADO 2021-2026</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        {/* BUY Side */}
        <div style={{ background: "#111c24", borderRadius: 6, padding: "10px 14px" }}>
          <div style={{ fontSize: 9, color: "#00e87a", letterSpacing: 2, marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "#00e87a" }} />
            COMPRA WIN (V2 KALMAN)
          </div>
          <div style={{ fontSize: 10, color: "#5a7080", lineHeight: 2 }}>
            <div>Z Entry: <span style={{ color: "#cdd8de", fontWeight: "bold" }}>≤ -1.8σ</span></div>
            <div>SL: <span style={{ color: "#ff3860", fontWeight: "bold" }}>350 pts</span> <span style={{ color: "#1c2e3a" }}>|</span> TP: <span style={{ color: "#00e87a", fontWeight: "bold" }}>500 pts</span></div>
            <div>BE: ativa em <span style={{ color: "#f5a623" }}>400pts</span> → trava em <span style={{ color: "#f5a623" }}>50pts</span></div>
            <div>Qty: <span style={{ color: "#cdd8de" }}>2 WIN × R$0.20</span></div>
          </div>
        </div>

        {/* SELL Side */}
        <div style={{ background: "#111c24", borderRadius: 6, padding: "10px 14px" }}>
          <div style={{ fontSize: 9, color: "#ff3860", letterSpacing: 2, marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "#ff3860" }} />
            VENDA WIN (V1 OLS)
          </div>
          <div style={{ fontSize: 10, color: "#5a7080", lineHeight: 2 }}>
            <div>Z Entry: <span style={{ color: "#cdd8de", fontWeight: "bold" }}>≥ +1.8σ</span></div>
            <div>SL: <span style={{ color: "#ff3860", fontWeight: "bold" }}>300 pts</span> <span style={{ color: "#1c2e3a" }}>|</span> TP: <span style={{ color: "#00e87a", fontWeight: "bold" }}>1400 pts</span></div>
            <div>BE: ativa em <span style={{ color: "#f5a623" }}>800pts</span> → trava em <span style={{ color: "#f5a623" }}>200pts</span></div>
            <div>Qty: <span style={{ color: "#cdd8de" }}>2 WIN × R$0.20</span></div>
          </div>
        </div>
      </div>

      {/* Engine Status Bar */}
      <div style={{
        marginTop: 12,
        borderTop: "1px solid #1c2e3a",
        paddingTop: 10,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 8,
      }}>
        <div style={{ fontSize: 10, color: "#5a7080", display: "flex", gap: 12, flexWrap: "wrap" }}>
          <span>Filtro HMM: <span style={{ color: "#ff9800", fontWeight: "bold" }}>M30 BULL → Bloqueia</span></span>
          <span>Horário: <span style={{ color: "#cdd8de" }}>10:00–16:00</span></span>
          <span>Force Close: <span style={{ color: "#f5a623" }}>17:40</span></span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {action === "CLOSE" && pnl !== null && (
            <span style={{
              fontSize: 11, fontWeight: "bold", padding: "3px 8px", borderRadius: 4,
              background: pnl >= 0 ? "rgba(0,232,122,0.15)" : "rgba(255,56,96,0.15)",
              color: pnl >= 0 ? "#00e87a" : "#ff3860",
              border: `1px solid ${pnl >= 0 ? "#00e87a44" : "#ff386044"}`,
            }}>
              {pnl >= 0 ? "+" : ""}R${pnl.toFixed(2)}
            </span>
          )}
          <div style={{
            fontSize: 11,
            fontWeight: "bold",
            padding: "3px 10px",
            borderRadius: 4,
            background: `${statusColor}15`,
            color: statusColor,
            border: `1px solid ${statusColor}44`,
            letterSpacing: 1,
          }}>
            {statusLabel}
          </div>
        </div>
      </div>
    </div>
  );
}
