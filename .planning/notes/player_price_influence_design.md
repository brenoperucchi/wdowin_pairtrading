# Player Price Influence (Directional Efficiency) Design

## Overview
Many times, order flow (aggression or cumulative position) does not translate into price displacement due to absorption (liquidity icebergs or passive counterparties). To filter out this noise, this indicator measures how much each broker's flow is aligned with or driving the price displacement for the day.

## Mathematical Formulation
For each broker $i$ and symbol $S \in \{WIN, WDO\}$:
At each bar $t$ of the current day (starting from the 09:00 AM opening bar):
1. **Price Change**: $dPrice_t = Price_t - Price_{t-1}$
2. **Broker Net Position Change**: $dNet_{i, t} = Net_{i, t} - Net_{i, t-1}$

We compute the **Daily Directional Efficiency (DDE)** as:
$$DDE_{i} = \frac{\sum_{t} dPrice_t \cdot dNet_{i, t}}{\sum_{t} |dPrice_t \cdot dNet_{i, t}|} \times 100$$

### Interpretation
- **$+50\%$ to $+100\%$**: High positive efficiency. The player's flow is strongly driving price displacement. When they buy, the price rises; when they sell, it falls (Smart Money/Aggressive Drivers).
- **$-30\%$ to $-100\%$**: High negative efficiency. The player's flow is opposing the price displacement (getting absorbed by icebergs or acting as passive counterparty).
- **Near $0\%$**: Neutral/No clear influence.

## Implementation Plan

### Backend
1. Create a helper function in `server.py` to fetch today's closed bars from `trades.db`.
2. Extract prices (`win_price` or `wdo_price`) and broker net positions from `flow_json`.
3. Compute the $DDE$ for each broker.
4. Inject the calculated efficiencies into the `/api/flow` endpoint payload:
   ```json
   "efficiency": {
       "WIN": { "XP": -24.5, "UBS": 68.2, ... },
       "WDO": { ... }
   }
   ```

### Frontend
1. Retrieve `efficiency` from `/api/flow`.
2. Add an **"EFICIÊNCIA"** column to the B3 brokers table in `BrokerFlowPanel.jsx` (between *Gráfico 2 (Diretriz)* and *Saldo/Agressão*).
3. Display the values using a premium dual-directional balance bar centered at $0\%$:
   - Left side: Red bar representing negative efficiency (absorption).
   - Right side: Green bar representing positive efficiency (driving force).
