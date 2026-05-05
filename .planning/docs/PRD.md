# PRD — WIN×WDO Pair Trading System
## Product Requirements Document

**Projeto**: Desafio SQX — Statistical Arbitrage  
**Ativos**: WIN$N (Mini Índice Bovespa) × WDO$N (Mini Dólar)  
**Versão**: 2.0 (Pós-Reorganização)  
**Data**: Abril 2026  

---

## 1. Visão do Produto

Sistema de monitoramento e execução automatizada de trades de **arbitragem estatística** (pairs trading) entre WIN e WDO na B3. O sistema detecta desvios na relação de preços dos dois ativos usando Z-Score (Filtro de Kalman), cointegração de Johansen e envelope Nadaraya-Watson (NWE), executando trades de reversão à média com gerenciamento de risco assimétrico.

### 1.1 Proposta de Valor

O par WIN×WDO possui correlação negativa historicamente forte (ρ ≈ -0.70 a -0.90). Quando essa relação se distorce temporariamente (z-score > ±1.8σ), existe oportunidade de lucro na reversão à média — desde que a relação estrutural permaneça intacta.

### 1.2 Público-Alvo

- Trader individual operando day trade na B3 com conta no MetaTrader 5.

---

## 2. Funcionalidades Core

### 2.1 Monitoramento de Regime (Dashboard)

| Funcionalidade | Descrição | Status |
|---|---|---|
| Z-Score em tempo real | Kalman filter para WDO e DI, janela 40/60 barras | ✅ Produção |
| Gráfico intraday | Z-Score WDO e DI com linhas de referência ±1.2 e ±1.4 | ✅ Produção |
| Nadaraya-Watson | Envelope não-repintável de preços do WIN para confirmação direcional | ✅ Produção |
| Cointegração Johansen | Teste contínuo (Eigen Statistic) entre WIN e WDO para validação de reversão | ✅ Produção |
| Alerta sonoro | Beep ao cruzar zona de trade | ✅ Produção |
| Performance histórica | Win rate, PnL acumulado, tabela de trades | ✅ Produção |

### 2.2 Engine de Execução (Setup Matador)

| Funcionalidade | Descrição | Status |
|---|---|---|
| Dual Z-Score routing | BUY via DI Kalman, SELL via WDO Kalman | ✅ Produção |
| NWE Filter | Exige confluência de preço extremo vs NWE Band | ✅ Produção |
| SL/TP | Parâmetros otimizados por direção (BUY DI vs SELL WDO) | ✅ Produção |
| Break-even automático | Ativação e lock por direção | ✅ Produção |
| Filtro de Johansen | Bloqueia entradas caso o teste falhe (Eigen Stat < 90%) | ✅ Produção |
| Force close | Encerra posição às 17:40 | ✅ Produção |

### 2.3 Research Pipeline (Offline)

| Funcionalidade | Descrição | Status |
|---|---|---|
| Backtests | WDO, WIN, par combinado (2021-2026) | ✅ Disponível |
| Otimização SL/TP | Grid search por direção | ✅ Disponível |
| Otimização Break-Even | Heatmap de ativação × lock | ✅ Disponível |
| Equity curves | Gráficos de performance acumulada | ✅ Disponível |

---

## 3. Requisitos Não-Funcionais

| Requisito | Especificação |
|---|---|
| Latência de análise | < 3s por ciclo (polling frontend) |
| Disponibilidade | Depende de MT5 Desktop aberto e logado |
| Persistência | SQLite local (trades.db) e Firebase RTDB (nuvem) |
| Segurança | Backend local; leitura apenas no Firebase via regras de segurança |
| Observabilidade | Dashboard React (Firebase Hosting) acessível externamente |

---

## 4. Requisitos de Dados

| Dado | Fonte | Frequência |
|---|---|---|
| Preços live M5 | MT5 `copy_rates_from_pos` | A cada 2.5s |
| Histórico backtest M1 | CSVs em `data/historical/` | Estático (até Mar/2026) |
| Trades executados | SQLite `trades.db` | Em tempo real |
| Beta persistido | `beta_ultimo.json` | Salvo às 17h |

---

## 5. Restrições e Dependências

- **MetaTrader 5 Desktop** aberto com os ativos WIN$N, WDO$N e DI1$N
- **Acesso à Internet** para sincronização Firebase (`wdo-win-dashboard-firebase-adminsdk.json` requerido)
- **Node.js 18+** (se rodando o dashboard localmente)
- Operação restrita ao **horário da B3** (10:00-16:00 para entradas, force close 17:40)
