# PRD — WIN×WDO Pair Trading System
## Product Requirements Document

**Projeto**: Desafio SQX — Statistical Arbitrage  
**Ativos**: WIN$N (Mini Índice Bovespa) × WDO$N (Mini Dólar)  
**Versão**: 2.0 (Pós-Reorganização)  
**Data**: Abril 2026  

---

## 1. Visão do Produto

Sistema de monitoramento e execução automatizada de trades de **arbitragem estatística** (pairs trading) entre WIN e WDO na B3. O sistema detecta desvios na relação de preços dos dois ativos usando Z-Score (Filtro de Kalman + OLS) e executa trades de reversão à média com gerenciamento de risco assimétrico.

### 1.1 Proposta de Valor

O par WIN×WDO possui correlação negativa historicamente forte (ρ ≈ -0.70 a -0.90). Quando essa relação se distorce temporariamente (z-score > ±1.8σ), existe oportunidade de lucro na reversão à média — desde que a relação estrutural permaneça intacta.

### 1.2 Público-Alvo

- Trader individual operando day trade na B3 com conta no MetaTrader 5.

---

## 2. Funcionalidades Core

### 2.1 Monitoramento de Regime (Dashboard)

| Funcionalidade | Descrição | Status |
|---|---|---|
| Z-Score em tempo real | Kalman filter + OLS rolling, janela 40 barras | ✅ Produção |
| Gráfico intraday | Z-Score do dia com linhas de referência ±1.8 e ±4.0 | ✅ Produção |
| Saúde da relação | Correlação ρ rolling + Δβ(20d) com semáforos | ✅ Produção |
| Cointegração Engle-Granger | Teste horário, p-value no topbar | ✅ Produção |
| HMM Regime (IA M30) | Classificação BULL/BEAR/CHOP via Gaussian HMM | ✅ Produção |
| Alerta sonoro | Beep ao cruzar zona de trade | ✅ Produção |
| Performance histórica | Win rate, PnL acumulado, tabela de trades | ✅ Produção |

### 2.2 Engine de Execução (Setup Matador)

| Funcionalidade | Descrição | Status |
|---|---|---|
| Dual Z-Score routing | BUY via Kalman, SELL via OLS | ✅ Produção |
| SL/TP assimétrico | Parâmetros diferentes por direção | ✅ Produção |
| Break-even automático | Ativação e lock por direção | ✅ Produção |
| Filtro HMM | Bloqueia entrada em regime BULL | ✅ Produção |
| Filtro de correlação | Bloqueia se ρ > -0.40 | ✅ Produção |
| Filtro de cointegração | Size zero se p-value > 0.10 | ✅ Produção |
| Force close | Encerra posição às 17:40 | ✅ Produção |

### 2.3 Research Pipeline (Offline)

| Funcionalidade | Descrição | Status |
|---|---|---|
| Backtests | WDO, WIN, par combinado (2021-2026) | ✅ Disponível |
| Otimização SL/TP | Grid search por direção | ✅ Disponível |
| Otimização Break-Even | Heatmap de ativação × lock | ✅ Disponível |
| HMM strategy filter | Avaliação de regimes no backtest | ✅ Disponível |
| Equity curves | Gráficos de performance acumulada | ✅ Disponível |

---

## 3. Requisitos Não-Funcionais

| Requisito | Especificação |
|---|---|
| Latência de análise | < 3s por ciclo (polling frontend) |
| Disponibilidade | Depende de MT5 Desktop aberto e logado |
| Persistência | SQLite local (trades.db) |
| Segurança | Execução local apenas, sem exposição de rede |
| Observabilidade | Dashboard React com status em tempo real |

---

## 4. Requisitos de Dados

| Dado | Fonte | Frequência |
|---|---|---|
| Preços live M5 | MT5 `copy_rates_from_pos` | A cada 2.5s |
| HMM features M30 | MT5 (WIN$N 1500 barras M30) | A cada 15 min |
| Histórico backtest M1 | CSVs em `data/historical/` | Estático (até Mar/2026) |
| Trades executados | SQLite `trades.db` | Em tempo real |
| Beta persistido | `beta_ultimo.json` | Salvo às 17h |

---

## 5. Restrições e Dependências

- **MetaTrader 5 Desktop** deve estar aberto e logado no broker
- **Símbolos WIN$N e WDO$N** devem estar visíveis no Market Watch
- **Python 3.10+** com pacotes: fastapi, uvicorn, MetaTrader5, numpy, pandas, hmmlearn, statsmodels, ta
- **Node.js 18+** para o dashboard React/Vite
- Operação restrita ao **horário da B3** (10:00-16:00 para entradas, force close 17:40)
