# Project Requirements

## REQ-001: Player Price Influence (Directional Efficiency)
- **Description**: The system must calculate the daily directional efficiency of each broker/player for the active symbols (WIN and WDO) to measure their direct influence on price displacement.
- **Formula**: $DDE_{i} = \frac{\sum dPrice_t \cdot dNet_{i, t}}{\sum |dPrice_t \cdot dNet_{i, t}|} \times 100$, where $dPrice_t$ is the price change and $dNet_{i, t}$ is the change in the net position of broker $i$ at bar $t$.
- **Aggregation**: Accumulated from the beginning of the current trading session (09:00 AM) to the current closed bar.
- **Visualization**: Displayed as an "EFICIÊNCIA" column in the B3 brokers table of the dashboard, using a premium dual-directional balance bar centered at 0% (-100% on the left in red, +100% on the right in green).

## REQ-002: Indicador Sintético de Fluxo Institucional em Tempo Real (WIN)
- **Description**: The system must calculate a consolidated, high-frequency synthetic institutional flow score for WIN based on direction, persistence, concentration, and absorption.
- **Formulas**: 
  - $ScoreFluxo_t = 100 \times (0.40 \times FLN_t + 0.30 \times PERS_t + 0.20 \times CONC\_DIR_t + 0.10 \times ABS\_DIR_t)$
  - $ScoreFinal_t = 0.50 \times Score_{5s} + 0.30 \times Score_{15s} + 0.20 \times Score_{60s}$
- **Aggregation**: Rolling window cache of high-frequency 5-second updates, retaining the last 60 minutes of history (720 points).
- **Visualization**: Displayed as a single line chart below the FlowDeltaChart on the dashboard. The line must dynamically change color: Green ($\ge 40$), Red ($\le -40$), or Yellow (neutral/conflito between -40 and +40).

