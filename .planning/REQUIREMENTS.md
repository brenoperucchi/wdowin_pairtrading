# Project Requirements

## REQ-001: Player Price Influence (Directional Efficiency)
- **Description**: The system must calculate the daily directional efficiency of each broker/player for the active symbols (WIN and WDO) to measure their direct influence on price displacement.
- **Formula**: $DDE_{i} = \frac{\sum dPrice_t \cdot dNet_{i, t}}{\sum |dPrice_t \cdot dNet_{i, t}|} \times 100$, where $dPrice_t$ is the price change and $dNet_{i, t}$ is the change in the net position of broker $i$ at bar $t$.
- **Aggregation**: Accumulated from the beginning of the current trading session (09:00 AM) to the current closed bar.
- **Visualization**: Displayed as an "EFICIÊNCIA" column in the B3 brokers table of the dashboard, using a premium dual-directional balance bar centered at 0% (-100% on the left in red, +100% on the right in green).

## REQ-003: Cálculo de Dominância e Eficiência do IAF em Janela Móvel de 25 Minutos
- **Description**: The system must calculate the player dominance and Kyle's Lambda for the IAF (Acelerador de Pressão) using a rolling window of the last 5 bars (25 minutes) instead of accumulating from the beginning of the daily session. This avoids volume anchoring from the opening period and keeps the indicator highly responsive to current participants.
- **Aggregation**: Rolling window of the last 5 bars (25 minutes).
- **Impact**: Dynamic updates of dominant player weights and Kyle's Lambda throughout the trading session.
