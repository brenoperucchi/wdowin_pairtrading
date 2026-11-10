# Documentação Consolidada — Sistema Stat-Arb WIN × WDO × DI (2026)

*Última atualização: 09/11/2026*

Este documento registra a arquitetura em execução, regras operacionais, parâmetros matemáticos auditados e métricas de performance do sistema de Arbitragem Estatística (**WIN × WDO × DI**) e do Dashboard Multi-Abas.

---

## 1. Infraestrutura, Portas e Regras de Ambiente

| Serviço | Porta / Caminho | Descrição | Regra Crítica |
| :--- | :--- | :--- | :--- |
| **Backend API (`server.py`)** | `http://localhost:8080` | Servidor FastAPI conectado ao Profit (SQLite M1 + RTD) e ao MetaTrader 5 (`terminal64.exe`). | Usa `_single_mt5_executor` (`max_workers=1`) + `core.mt5_client.mt5_lock` para serializar 100% das chamadas C++ ao MT5 em uma única thread de SO. |
| **Frontend Dashboard A** | `http://localhost:5174` | Instância Vite do `regime-dashboard`. | Manter sempre ativo e sincronizado. |
| **Frontend Dashboard B** | `http://localhost:5176` | Instância Vite espelhada do `regime-dashboard`. | Manter sempre ativo e sincronizado. |
| **Porta Proibida** | `http://localhost:5175` | Outro projeto independente na máquina. | **JAMAIS encerrar, reiniciar ou modificar processos na porta `5175`.** |

---

## 2. Organização das 3 Abas do Dashboard (`regime-dashboard`)

1. **Aba 1 — `🎯 1. Cockpit Intraday (GEX + Fluxo)` (`COCKPIT`)**:
   - Exibe o [`IntradayCompassPanel.jsx`](regime-dashboard/src/components/IntradayCompassPanel.jsx) (Bússola Intraday GEX + 6 Estratégias Campeãs) e o [`LiveTradingCalendar.jsx`](regime-dashboard/src/components/LiveTradingCalendar.jsx) (Calendário Auditado e robôs que operaram nas 6 Estratégias Campeãs).
2. **Aba 2 — `🏦 2. Raio-X Corretoras (WIN)` (`RAIO_X`)**:
   - Exibe o [`FlowDeltaChart.jsx`](regime-dashboard/src/components/FlowDeltaChart.jsx) e o [`BrokerFlowPanel.jsx`](regime-dashboard/src/components/BrokerFlowPanel.jsx) (Saldo líquido, agressão institucional e eficiência direcional por corretora).
3. **Aba 3 — `📐 3. Arbitragem WIN×WDO×DI` (`STAT_ARB`)**:
   - **Exclusiva para a Arbitragem Estatística WIN × WDO × DI** (sem mistura com as 6 estratégias da Aba 1 e sem os antigos painéis `PerformancePanel`/`TradingGuide`).
   - Componentes em exibição:
     1. [`ZScoreChart.jsx`](regime-dashboard/src/components/ZScoreChart.jsx) — Z-Score Kalman em tempo real (`WDOFUT` em dourado e `DIFUT` em roxo, janela `W=40`).
     2. [`SignalHistogram.jsx`](regime-dashboard/src/components/SignalHistogram.jsx) — Matriz de disparo das 3 estratégias (`WDO NWE`, `DI NWE`, `WDO+DI`), congelada após o fechamento de cada barra M5 (sem repintura).
     3. [`IndexChart.jsx`](regime-dashboard/src/components/IndexChart.jsx) — Gráfico de **Candles M5 do WINFUT** + Envelope Nadaraya-Watson (NWE) + GEX Walls + **Caixas de Posição estilo TradingView** (delimitando início, degrau de Break-Even e fim exato de cada trade).
     4. [`StatArbLiveTradePanel.jsx`](regime-dashboard/src/components/StatArbLiveTradePanel.jsx) — Acompanhamento Ao Vivo dos 3 setups (`POSICIONADO AO VIVO`, `ENCERRADO`, `AGUARDANDO GATILHO`), tabela de operações do pregão atual e histórico auditado completo de 2026 (`488+ trades`) clicável para replay no gráfico.
     5. [`StatArbBacktest2026Panel.jsx`](regime-dashboard/src/components/StatArbBacktest2026Panel.jsx) — Curvas de capital comparativas (Janeiro a Novembro/2026), Matriz de Correlação & Hedge, Frequência de Dias Operados e Histórico dos 212 Pregões.

---

## 3. Regras Operacionais das 3 Estratégias Stat-Arb (Auditadas em M1 Fechado → M5)

### 3.1 Precificação e Filtros Base
- **Ativo Operado**: `WINFUT` (Mini-Índice B3, lote padrão de referência: `2 contratos`, onde `1 ponto = R$ 0,40` para 2 contratos).
- **Cointegração / Spread Dinâmico**:
  - `WINFUT × WDOFUT`: Filtro de Kalman (`Q = 1e-5`, `R = 1e-2`), Z-Score rolante de `40 barras` M5 (`z_wdo`).
  - `WINFUT × DI1FUT` (`DI1F28`/`DI1F29` com ajuste automático de roll `> 0.35` pts de taxa): Filtro de Kalman (`Q = 1e-4`, `R = 1e-2`), Z-Score rolante de `40 barras` M5 (`z_di`).
- **Filtro de Exaustão Nadaraya-Watson Envelope (NWE)**:
  - Calculado sobre os fechamentos M5 (`lookback = 300`, `bandwidth = 8.0`, `mult_mae = 2.0`).
  - **Compra permitida** apenas quando a inclinação NWE é de baixa (`!is_up`) e o preço está na zona inferior do canal (`px <= nwe_lower + bw * nwe_prox`).
  - **Venda permitida** apenas quando a inclinação NWE é de alta (`is_up`) e o preço está na zona superior do canal (`px >= nwe_upper - bw * nwe_prox`).
- **Bloqueio de Anomalia**: Não opera se `|z_wdo| >= 4.0` ou `|z_di| >= 4.0`.

### 3.2 Parâmetros de Entrada por Estratégia

| Estratégia | Gatilho de Entrada (Barra M5 Fechada) | Proximidade NWE (`nwe_prox`) | Ativação Break-Even (`be_act`) | Trava Break-Even (`be_lock`) | Cooldown Pós-Saída |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`1. CONSENSO (WDO+DI)`** | `(±1.8 WDO e ±1.2 DI)` **ou** `(±2.2 DI e ±1.2 WDO)` na mesma direção | `15%` da banda (`0.15`) | `+150 pts` | `+15 pts` | `4 barras` (`20 min`) |
| **`2. DI_NWE (ISOLADO)`** | `|Z_DI| >= 2.2` | `10%` da banda (`0.10`) | `+200 pts` | `+15 pts` | `4 barras` (`20 min`) |
| **`3. WDO_NWE (ISOLADO)`** | `|Z_WDO| >= 1.4` | `15%` da banda (`0.15`) | `+150 pts` | `+15 pts` | `4 barras` (`20 min`) |

### 3.3 Posicionamento de Stop Loss, Alvo (GEX Walls) e Saídas
1. **Stop Loss Sempre Atrás da Wall Anterior (`calc_wall_tp_sl` em [`core/trade_engine.py`](core/trade_engine.py))**:
   - Na **Compra**: busca a Wall imediatamente abaixo do preço de entrada e posiciona o Stop **`30 pts` abaixo da Wall** (respeitando distância mínima de `200 pts`).
   - Na **Venda**: busca a Wall imediatamente acima do preço de entrada e posiciona o Stop **`30 pts` acima da Wall** (respeitando distância mínima de `200 pts`).
   - **Trava de Risco Máximo (`300 pts`)**: Se a distância até atrás da Wall anterior ultrapassar `300 pts`, **o stop NÃO é encurtado para antes da Wall** — a operação simplesmente **é filtrada (não entra)**.
2. **Alvo de Ganho (Próxima Wall) e Filtro Risco/Retorno (`R/R >= 1.4x`)**:
   - Posicionado `10 pts` antes da próxima GEX Wall a favor do trade (distância mínima de `200 pts`).
   - A operação só é aberta se `tp_dist / sl_dist >= 1.4`.
3. **Saída por Reversão de Z-Score (`ALVO Z-REV`)**:
   - Se a barra M5 fechar com o Z-Score revertido (`>= +0.2` na compra ou `<= -0.2` na venda para setups isolados; `>= 0.0` / `<= 0.0` em ambos para o Consenso) **e** o lucro aberto for `>= 200 pts`, encerra no fechamento da barra.
4. **Horários Operacionais**:
   - Janela de novas entradas: `09:05` às `15:30` (13:55 no motor live conservador).
   - Zeragem compulsória de fim de dia: `17:40`.

---

## 4. Performance Auditada 2026 (02/01/2026 a 06/11/2026 — 212 Pregões)

Baseada em barras M1 reais fechadas (sem lookahead bias):

| Portfólio / Estratégia | Lucro Líquido (`2 cts`) | Pontos Acumulados | Max Drawdown | Retorno / DD | Total de Trades | Dias Operados (`/ 212`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **PORTFÓLIO SOMA BRUTA (3 Setups)** | **+R\$ 10.135** | **+25.338 pts** | **R\$ 764** (`1.910 pts`) | **13,27x** | `488 trades` | `184 dias` (`86,8%` — `116 Pos / 68 Neg`) |
| **PORTFÓLIO DEDUPLICADO (1x p/ Horário)** | **+R\$ 6.322** | **+15.805 pts** | **R\$ 752** (`1.879 pts`) | **8,41x** | `328 trades` | `184 dias` (`86,8%` — `115 Pos / 69 Neg`) |
| **`1. CONSENSO (WDO+DI)`** | **+R\$ 4.277** | **+10.693 pts** | **R\$ 463** (`1.158 pts`) | **9,23x** | `135 trades` | `102 dias` (`48,1%` — `59 Pos / 43 Neg`) |
| **`2. DI_NWE (ISOLADO)`** | **+R\$ 3.252** | **+8.131 pts** | **R\$ 592** (`1.481 pts`) | **5,49x** | `204 trades` | `152 dias` (`71,7%` — `79 Pos / 73 Neg`) |
| **`3. WDO_NWE (ISOLADO)`** | **+R\$ 2.606** | **+6.515 pts** | **R\$ 384** (`960 pts`) | **6,79x** | `149 trades` | `110 dias` (`51,9%` — `63 Pos / 47 Neg`) |

### 4.1 Correlação Diária e Efeito de Diversificação
- **`DI_NWE` × `WDO_NWE`**: Correlação diária baixa (**`r = +0,207`**). Nos `182` pregões em que ao menos uma das duas operou:
  - Em **`102 pregões (56,0%)`** apenas uma operou enquanto a outra ficou de fora.
  - Em **`18 pregões (9,9%)`** operaram em direções/resultados opostos servindo de **Hedge Direto**.
  - Apenas em **`18 pregões (9,9%)`** perderam juntas.

### 4.2 Estudo Comparativo de Saídas (Break-Even vs. Linha Central NWE)
- **Sistema Atual (`BE +150/200p → +15p` + Alvo Wall/Z-Rev)**: Entrega o **melhor índice Retorno/Drawdown (`13,27x`)** e o **menor Drawdown (`R$ 764`)**, pois o Break-Even salva **66 operações** no ano que andaram `+150 pts` a favor e depois reverteram para o Stop cheio da Wall (`+R$ 1.611` de economia líquida frente ao sistema sem BE).
- **Saída na Linha Central da NWE (`nwe_mid`) com BE (`+150p`)**: Entrega o **maior lucro bruto (`+R$ 12.308` / `+30.769 pts`)**, porém aumenta as saídas no BE (`141` vs `101`) e eleva o Max Drawdown para `R$ 1.716` (`Ret/DD = 7,17x`). Por decisão operacional, **mantemos o Sistema Atual (`13,27x Ret/DD`)**.
- **Saída na Banda Oposta da NWE**: Descartada (`Ret/DD = 0,72x` com BE e `-0,46x` sem BE), pois a largura média do canal NWE (~`1.300 pts`) faz a maioria das operações devolver o lucro antes de atravessar a banda inteira.
