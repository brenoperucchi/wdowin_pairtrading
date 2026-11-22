// SetupMatadorPanel.jsx — Configuração ativa do Setup Matador V6 (Ink Azul · Magic Walls)
export default function SetupMatadorPanel({ tradeEngine }) {
  const action = tradeEngine?.action || "WAIT";
  const holding = tradeEngine?.holding || false;
  const exitReason = tradeEngine?.exit_reason;
  const pnl = tradeEngine?.pnl;

  const statusLabel = holding ? "Posição aberta"
    : action === "HMM_BLOCKED" ? "IA bloqueando"
      : action === "ANOMALY" ? "Anomalia"
        : action === "BUY_WIN" ? "Compra WIN aberta"
          : action === "SELL_WIN" ? "Venda WIN aberta"
            : action === "CLOSE" ? `Fechado (${exitReason})`
              : "Aguardando sinais M5";

  const statusColor = holding ? "#d4a259"
    : action === "HMM_BLOCKED" ? "#d4a259"
      : action === "ANOMALY" ? "#e5484d"
        : (action === "BUY_WIN" || action === "SELL_WIN") ? "#4cc38a"
          : action === "CLOSE" ? "#38bdf8"
            : "var(--mw-text-3)";

  return (
    <section
      className="mw-card"
      style={{
        borderLeft: "2px solid #d4a259",
        padding: "14px 18px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 8,
        borderBottom: "1px solid var(--mw-hairline)",
        paddingBottom: 10,
      }}>
        <span style={{ fontSize: 13.5, fontWeight: 600, color: "var(--mw-text-1)" }}>
          Setup Matador V6 · Portfólio híbrido (3 setups)
        </span>
        <span className="mw-mono" style={{ fontSize: 11, color: "var(--mw-text-3)" }}>
          Backtest 126k barras M5 (2021–2026)
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
        {/* WDO_NWE */}
        <div style={{ background: "var(--mw-chrome)", border: "1px solid var(--mw-hairline)", borderLeft: "2px solid #d4a259", borderRadius: 8, padding: "12px 14px" }}>
          <div className="mw-mono" style={{ fontSize: 11.5, color: "#d4a259", fontWeight: 600, marginBottom: 8 }}>
            WDO_NWE (OLS)
          </div>
          <div className="mw-mono" style={{ fontSize: 11.5, color: "var(--mw-text-3)", lineHeight: 1.85 }}>
            <div>Z Entry: <span style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>≥ ±2.2σ</span></div>
            <div>SL: <span style={{ color: "#e5484d", fontWeight: 500 }}>300 pts</span> · TP: <span style={{ color: "#4cc38a", fontWeight: 500 }}>600 pts</span></div>
            <div>Horário: <span style={{ color: "var(--mw-text-2)" }}>10:00–16:00</span></div>
            <div>Cooldown: <span style={{ color: "#d4a259" }}>3 barras (15m)</span></div>
            <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px solid var(--mw-hairline)" }}>
              NWE: <span style={{ color: "#38bdf8" }}>BW=1, MAE=2.0 (15%)</span>
            </div>
          </div>
        </div>

        {/* DI_NWE */}
        <div style={{ background: "var(--mw-chrome)", border: "1px solid var(--mw-hairline)", borderLeft: "2px solid #a78bfa", borderRadius: 8, padding: "12px 14px" }}>
          <div className="mw-mono" style={{ fontSize: 11.5, color: "#a78bfa", fontWeight: 600, marginBottom: 8 }}>
            DI_NWE (Kalman)
          </div>
          <div className="mw-mono" style={{ fontSize: 11.5, color: "var(--mw-text-3)", lineHeight: 1.85 }}>
            <div>Z Entry: <span style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>≥ ±1.8σ</span></div>
            <div>SL: <span style={{ color: "#e5484d", fontWeight: 500 }}>300 pts</span> · TP: <span style={{ color: "#4cc38a", fontWeight: 500 }}>400 pts</span></div>
            <div>Horário: <span style={{ color: "var(--mw-text-2)" }}>09:00–15:00</span></div>
            <div>Cooldown: <span style={{ color: "#d4a259" }}>2 barras (10m)</span></div>
            <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px solid var(--mw-hairline)" }}>
              NWE: <span style={{ color: "#38bdf8" }}>Unificado c/ WDO</span>
            </div>
          </div>
        </div>

        {/* CONSENSO */}
        <div style={{ background: "var(--mw-chrome)", border: "1px solid var(--mw-hairline)", borderLeft: "2px solid #38bdf8", borderRadius: 8, padding: "12px 14px" }}>
          <div className="mw-mono" style={{ fontSize: 11.5, color: "#38bdf8", fontWeight: 600, marginBottom: 8 }}>
            Consenso (V5)
          </div>
          <div className="mw-mono" style={{ fontSize: 11.5, color: "var(--mw-text-3)", lineHeight: 1.85 }}>
            <div>Z Entry: <span style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>≥ ±2.2σ</span> · Z Att: <span style={{ color: "var(--mw-text-1)", fontWeight: 500 }}>1.6σ</span></div>
            <div>SL: <span style={{ color: "#e5484d", fontWeight: 500 }}>300 pts</span> · TP: <span style={{ color: "#4cc38a", fontWeight: 500 }}>500 pts</span></div>
            <div>Horário: <span style={{ color: "var(--mw-text-2)" }}>09:00–16:00</span></div>
            <div>Filtro NWE: <span style={{ color: "#e5484d" }}>Desligado</span></div>
          </div>
        </div>
      </div>

      {/* Barra de status da engine */}
      <div
        className="mw-mono"
        style={{
          borderTop: "1px solid var(--mw-hairline)",
          paddingTop: 10,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 10,
        }}
      >
        <div style={{ fontSize: 11, color: "var(--mw-text-3)", display: "flex", gap: 14, flexWrap: "wrap" }}>
          <span>Filtro de tendência: <strong style={{ color: "#e5484d", fontWeight: 500 }}>is_up desligado</strong></span>
          <span>Break-even: <strong style={{ color: "#e5484d", fontWeight: 500 }}>desligado</strong></span>
          <span>Force close: <strong style={{ color: "#d4a259", fontWeight: 500 }}>17:30</strong></span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {action === "CLOSE" && pnl != null && Number.isFinite(Number(pnl)) && (
            <span style={{
              fontSize: 11.5,
              fontWeight: 600,
              padding: "3px 8px",
              borderRadius: 6,
              background: Number(pnl) >= 0 ? "rgba(76, 195, 138, 0.12)" : "rgba(229, 72, 77, 0.12)",
              color: Number(pnl) >= 0 ? "#4cc38a" : "#e5484d",
              border: `1px solid ${Number(pnl) >= 0 ? "rgba(76, 195, 138, 0.35)" : "rgba(229, 72, 77, 0.35)"}`,
              whiteSpace: "nowrap",
            }}>
              {Number(pnl) >= 0 ? "+" : "−"}R$ {Math.abs(Number(pnl)).toFixed(2)}
            </span>
          )}
          <div style={{
            fontSize: 11.5,
            fontWeight: 500,
            padding: "3px 10px",
            borderRadius: 6,
            background: "var(--mw-chrome)",
            color: statusColor,
            border: "1px solid var(--mw-hairline-strong)",
          }}>
            {statusLabel}
          </div>
        </div>
      </div>
    </section>
  );
}
