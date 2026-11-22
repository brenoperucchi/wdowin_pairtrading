# Project Requirements

## REQ-001: Player Price Influence (Directional Efficiency)
- **Description**: The system must calculate the daily directional efficiency of each broker/player for the active symbols (WIN and WDO) to measure their direct influence on price displacement.
- **Formula**: $DDE_{i} = \frac{\sum dPrice_t \cdot dNet_{i, t}}{\sum |dPrice_t \cdot dNet_{i, t}|} \times 100$, where $dPrice_t$ is the price change and $dNet_{i, t}$ is the change in the net position of broker $i$ at bar $t$.
- **Aggregation**: Accumulated from the beginning of the current trading session (09:00 AM) to the current closed bar.
- **Visualization**: Displayed as an "EFICIÊNCIA" column in the B3 brokers table of the dashboard, using a premium dual-directional balance bar centered at 0% (-100% on the left in red, +100% on the right in green).

## REQ-002: Indicador Sintético de Fluxo Institucional em Tempo Real (WIN) — **[INATIVO NA UI]**
- **Status (22/11/2026):**
  - Backend implementado em `server.py` (`GET /api/flow/realtime`, com atualização via `POST /api/flow/update` e `POST /api/flow/inject-history` bloqueado por padrão sem `MW_ALLOW_FLOW_INJECT=1`).
  - **UI inativa:** o componente `regime-dashboard/src/components/FlowScoreChart.jsx` existe no repositório, mas **não está importado nem conectado ao `App.jsx` atual**. O indicador permanece inativo na interface até decisão explícita de reativação.
  - **Pesos em código:** tanto `server.py` (`_calculate_window_score` e `_calculate_combined_flow_score`) quanto o estado default de `FlowScoreChart.jsx` permanecem com os pesos **`20 / 40 / 30 / 10`** (`0.20 * FLN + 0.40 * PERS + 0.30 * CONC_DIR + 0.10 * ABS_DIR`) até eventual reativação.
- **O que medem os 4 fatores (em linguagem acessível):**
  - **`FLN` (Direção Líquida / Fluxo Normalizado — peso atual 20%):** compara quanto entrou de compra versus venda na janela em relação ao volume total negociado. Valores perto de `+1` indicam fluxo quase todo comprador; perto de `-1`, quase todo vendedor; perto de `0`, equilíbrio.
  - **`PERS` (Persistência — peso atual 40%):** mede se a pressão compradora ou vendedora se manteve firme na mesma direção ao longo dos ticks da janela (a cada 5s), em vez de ficar indo e voltando sem convicção.
  - **`CONC_DIR` (Concentração Direcional — peso atual 30%):** mede quanto do saldo da janela está concentrado nas **3 corretoras mais atuantes** e para qual lado elas estão puxando — ajuda a separar movimento coordenado de grandes participantes de ruído pulverizado.
  - **`ABS_DIR` (Absorção Direcional — peso atual 10%):** identifica situações em que entra um volume muito alto de agressão para um lado, mas o preço quase não se desloca (indicando defesa/absorção passiva na ponta contrária, sinalizando pressão oculta contra o agressor).
- **Fórmula consolidada (código atual em `server.py`):**
  - $ScoreFluxo_t = 100 \times (0.20 \times FLN_t + 0.40 \times PERS_t + 0.30 \times CONC\_DIR_t + 0.10 \times ABS\_DIR_t)$
  - Combinação multi-janela: $0.50 \times Fator_{5s} + 0.30 \times Fator_{15s} + 0.20 \times Fator_{60s}$
  - *(Nota histórica: a especificação inicial previa pesos `40/30/20/10`; o código foi implementado e mantido com `20/40/30/10` até eventual reativação do painel.)*
- **Aggregation**: Janela móvel de atualizações de alta frequência (5s), retendo os últimos 60 minutos em memória (`_realtime_flow_cache`, iniciado vazio sem semente sintética).
- **Visualization (quando reativado)**: Gráfico de linha único (`FlowScoreChart.jsx`) variando de `-100` a `+100`, com cor dinâmica: Verde ($\ge 40$), Vermelho ($\le -40$) ou Amarelo (zona neutra/conflito entre `-40` e `+40`).

## REQ-003: Cálculo de Dominância e Eficiência do IAF em Janela Móvel de 25 Minutos
- **Description**: The system must calculate the player dominance and Kyle's Lambda for the IAF (Acelerador de Pressão) using a rolling window of the last 5 bars (25 minutes) instead of accumulating from the beginning of the daily session. This avoids volume anchoring from the opening period and keeps the indicator highly responsive to current participants.
- **Aggregation**: Rolling window of the last 5 bars (25 minutes).
- **Impact**: Dynamic updates of dominant player weights and Kyle's Lambda throughout the trading session.
