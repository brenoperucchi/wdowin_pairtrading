# Sistema de Simulação e Gerência de Stop Diário Máximo — Robôs Jumba

> [!IMPORTANT]
> **Atualização Oficial de Produção (19/11/2026 — Atualizado em 22/11/2026):**
> - **Migração para a Carteira Top 10 (`Campeões + EST-09/10`):** em **19/11/2026**, a conta de produção XP (`2004051`) migrou oficialmente para os **10 robôs elite**:
>   - **7 WIN:** `EST-04` (`88004`), `EST-07` (`88007`), `EST-09` (`88009`), `EST-10` (`88010`), `EST-13` (`88013`), `EST-14` (`88014`), `EST-15` (`88015`)
>   - **3 WDO:** `WDO-01` (`89001`), `WDO-05` (`89005`), `WDO-07` (`89007`)
> - **Stop Diário Oficial em Produção (`Jumba_Portfolio_Live_Monitor.mq5` v4.20):**
>   - **`InpMaxDailyLossGlobal = 950.0`** (Global `WIN + WDO`: `-R$ 950`)
>   - **`InpMaxDailyLossWin = 400.0`** (Sub-limite isolado `WIN`: `-R$ 400`)
>   - **`InpMaxDailyLossWdo = 0.0`** (Sub-limite isolado `WDO`: desativado — controlado pelo Global)
>   - **`InpSendPushOnStop = true`** (notificação Push habilitada ao disparar trava)
> - **Acompanhamento Diário:** reconciliação automatizada Live vs Backtest via `scripts/reconcile_mt5_vs_bt.py` (lendo `jumba_portfolio_live_monitor_<login>.csv`, `jumba_daily_stop_state_<login>.csv`, `jumba_live_deals_<login>.csv` e `jumba_live_trades_audit_<login>.csv`).
> - *O estudo histórico comparativo original das 4 carteiras (`Proposta B · 11 Robôs`, `XP M5 · 11 Robôs`, `Campeões · 8 Robôs` e `Campeões + EST-09/10 · 10 Robôs`) permanece preservado integralmente abaixo para referência.*

---

## Estudo Histórico Original (Base 212 Pregões · 11 Robôs & Comparativo)

- **Carteira Padrão do Estudo Original:** Proposta B · 11 Robôs (Oficial) (8 WIN (EST-01, 03, 04, 05, 07, 13, 14, 15) + 3 WDO (WDO-01, 05, 07))
- **Base Auditada:** Deals reais do MT5 Strategy Tester (`OHLC 1-Min`, `data/reports/mt5_tester_ohlc_2026/*_P1.htm`) + séries M1 reais de WIN e WDO (2026-01-02 a 2026-11-06, **212 pregões**).
- **Divisão OOS / IS:** **OOS cego** (`02/01`–`06/05/2026`, 84 pregões) · **IS** (`07/05`–`06/11/2026`, 128 pregões).
- **Custos B3 embutidos:** WIN `R\$ 2,00/contrato` (`-R\$ 1,00/lote` adicional sobre o spread MT5) · WDO `R\$ 5,00/contrato`.
- **Motor Live MT5:** `Jumba_Portfolio_Live_Monitor.mq5` (v4.00) + `Jumba_SafetyGuard.mqh` + `Jumba_GEX_NWE_Core.mqh` + `Jumba_WDO_GEX_NWE_Core.mqh`.

## 1. Resumo Executivo das Carteiras

| Carteira | Robôs | Trades | Sem Stop (Lucro / DD / Ret/DD) | Stop Ret/DD Ótimo | Resultado c/ Stop Ret/DD | Stop Max Lucro | Combo (Global / WIN / WDO) |
| :--- | :---: | :---: | :--- | :---: | :--- | :---: | :--- |
| **Proposta B · 11 Robôs (Oficial)** | 11 | 8.431 | +R\$ 42.769 / R\$ 3.284 / **13,02x** | R\$ 850 | +R\$ 43.133 / R\$ 3.143 / **13,72x** (6d) | R\$ 1.100 (13,17x) | G R\$ 0 / W R\$ 400 / D R\$ 350 → +R\$ 36.679 (DD R\$ 1.878, **19,53x**) |
| **XP M5 · 11 Robôs** | 11 | 6.755 | +R\$ 48.061 / R\$ 4.331 / **11,10x** | R\$ 1.150 | +R\$ 48.622 / R\$ 4.331 / **11,23x** (2d) | R\$ 1.150 (11,23x) | G R\$ 1.050 / W R\$ 400 / D R\$ 0 → +R\$ 47.041 (DD R\$ 3.807, **12,36x**) |
| **Campeões · 8 Robôs** | 8 | 4.951 | +R\$ 41.490 / R\$ 2.411 / **17,21x** | R\$ 900 | +R\$ 41.923 / R\$ 2.411 / **17,39x** (2d) | R\$ 900 (17,39x) | G R\$ 0 / W R\$ 425 / D R\$ 350 → +R\$ 36.484 (DD R\$ 1.480, **24,65x**) |
| **Campeões + EST-09/10 · 10 Robôs** | 10 | 5.492 | +R\$ 45.400 / R\$ 1.958 / **23,19x** | R\$ 1.000 | +R\$ 45.652 / R\$ 1.958 / **23,32x** (1d) | R\$ 1.000 (23,32x) | G R\$ 0 / W R\$ 425 / D R\$ 350 → +R\$ 39.700 (DD R\$ 1.352, **29,36x**) |

---

## 2. Análise Detalhada — Proposta B · 11 Robôs (Oficial)

> 8 WIN (EST-01, 03, 04, 05, 07, 13, 14, 15) + 3 WDO (WDO-01, 05, 07)

### 2.1. Perfil de Excursão Adversa Diária (MAE M1 vs Trades Fechados)

| Escopo | MAE Médio | σ | P50 | P75 | P90 | P95 | MAE Máximo |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Global Intraday (M1)** | R\$ 310 | R\$ 264 | R\$ 244 | R\$ 469 | R\$ 653 | R\$ 778 | R\$ 1.830 |
| **Global Fechado (Trades)** | R\$ 297 | — | — | R\$ 426 | R\$ 612 | — | R\$ 1.763 |
| **WIN Isolado (M1)** | R\$ 223 | — | — | R\$ 323 | R\$ 433 | — | R\$ 961 |
| **WDO Isolado (M1)** | R\$ 246 | — | — | R\$ 370 | R\$ 530 | — | R\$ 1.310 |

### 2.2. Comparativo Baseline vs Stops (Total 2026 · OOS · IS)

| Cenário | Config Stop | Lucro Total | Max DD Diário | Max DD M1 Intra | Ret/DD | Sharpe | Pior Dia | Dias Parados | OOS (Jan-Mai) | IS (Mai-Nov) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Sem Stop (Baseline)** | — | +R\$ 42.769 | R\$ 3.284 | R\$ 3.852 | **13,02x** | 6,56 | -R\$ 1.588 | 0d (0,0%) | +R\$ 12.970 (3,95x) | +R\$ 29.799 (18,77x) |
| **Stop Global Ret/DD ★** | R\$ 850 | +R\$ 43.133 | R\$ 3.143 | R\$ 3.711 | **13,72x** | 6,72 | -R\$ 850 | 6d (2,8%) | +R\$ 12.739 (4,05x) | +R\$ 30.394 (26,95x) |
| **Stop Global Máx Lucro 💰** | R\$ 1.100 | +R\$ 43.257 | R\$ 3.284 | R\$ 3.852 | **13,17x** | 6,74 | -R\$ 1.100 | 1d (0,5%) | +R\$ 12.970 (3,95x) | +R\$ 30.287 (26,45x) |
| **Combo Multi-Escopo ⚡** | G R\$ 0 · W R\$ 400 · D R\$ 350 | +R\$ 36.679 | R\$ 1.878 | R\$ 2.059 | **19,53x** | 5,68 | -R\$ 750 | 75d (35,4%) | +R\$ 11.506 (6,13x) | +R\$ 25.173 (21,50x) |

### 2.3. Robustez Estatística (Walk-Forward & Monte Carlo)

- **Walk-Forward Rolling (60d treino → 20d teste):** 0/7 folds melhoraram Ret/DD OOS · Stop Mediano = **R\$ 550**.
- **Treino IS (Mai-Nov) -> Teste OOS Cego (Jan-Mai):** Stop calibrado `R\$ 825` → Base +R\$ 12.970 (3,95x) vs Stop +R\$ 12.814 (4,08x, 3d).
- **Treino OOS (Jan-Mai) -> Teste IS (Mai-Nov):** Stop calibrado `R\$ 825` → Base +R\$ 29.799 (18,77x) vs Stop +R\$ 30.469 (27,01x, 3d).
- **Monte Carlo IID (2.000 sims, stop R\$ 850):** Vence em Ret/DD **64,8%** · Reduz MaxDD **58,1%** · MaxDD P95 R\$ 3.894 → **R\$ 3.568**.
- **Monte Carlo Block Bootstrap 5d (2.000 sims):** Vence em Ret/DD **68,1%** · Reduz MaxDD **52,6%** · MaxDD P95 R\$ 3.508 → **R\$ 3.320**.

### 2.4. Análise Individual por Robô (MAE/MFE Real M1)

| Robô | Ativo | TF | Magic | Trades | Lucro Líq. | WR% | PF | Payoff | MAE P90 | MFE Méd | Eff% | Stop/Trade Sug. | Pior Dia | Stop/Dia Sug. | % Piores 15d |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **EST-13** | WIN | M5 | `88013` | 681 | +R\$ 8.626 | 55,8% | 1,62 | 1,27 | R\$ 74 | R\$ 60 | -7,3% | R\$ 87 | -R\$ 411 | R\$ 234 | 5,0% |
| **WDO-05** | WDO | M5 | `89005` | 759 | +R\$ 6.400 | 62,7% | 1,25 | 0,72 | R\$ 140 | R\$ 63 | -2,8% | R\$ 164 | -R\$ 480 | R\$ 262 | 24,3% |
| **WDO-01** | WDO | M5 | `89001` | 731 | +R\$ 6.370 | 61,8% | 1,28 | 0,75 | R\$ 130 | R\$ 56 | -0,3% | R\$ 152 | -R\$ 410 | R\$ 265 | 24,6% |
| **EST-14** | WIN | M5 | `88014` | 725 | +R\$ 5.782 | 55,3% | 1,36 | 1,09 | R\$ 74 | R\$ 55 | -7,1% | R\$ 87 | -R\$ 362 | R\$ 241 | 4,6% |
| **EST-15** | WIN | M5 | `88015` | 654 | +R\$ 5.355 | 61,2% | 1,41 | 0,90 | R\$ 74 | R\$ 49 | 10,0% | R\$ 87 | -R\$ 359 | R\$ 203 | 6,9% |
| **WDO-07** | WDO | M5 | `89007` | 474 | +R\$ 3.950 | 54,6% | 1,28 | 0,96 | R\$ 115 | R\$ 72 | -14,1% | R\$ 135 | -R\$ 470 | R\$ 232 | 15,6% |
| **EST-04** | WIN | M5 | `88004` | 359 | +R\$ 2.608 | 43,5% | 1,37 | 1,79 | R\$ 50 | R\$ 55 | -51,7% | R\$ 59 | -R\$ 204 | R\$ 144 | 1,8% |
| **EST-01** | WIN | M5 | `88001` | 876 | +R\$ 2.428 | 32,6% | 1,13 | 2,32 | R\$ 50 | R\$ 59 | -53,9% | R\$ 59 | -R\$ 328 | R\$ 208 | 5,3% |
| **EST-07** | WIN | M5 | `88007` | 568 | +R\$ 2.399 | 34,0% | 1,18 | 2,30 | R\$ 54 | R\$ 56 | -37,2% | R\$ 64 | -R\$ 213 | R\$ 170 | 5,2% |
| **EST-05** | WIN | M15 | `88005` | 212 | -R\$ 352 | 17,0% | 0,84 | 4,12 | R\$ 16 | R\$ 25 | -92,1% | R\$ 18 | -R\$ 55 | R\$ 91 | 0,0% |
| **EST-03** | WIN | M15 | `88003` | 2392 | -R\$ 797 | 42,4% | 0,98 | 1,33 | R\$ 52 | R\$ 38 | -58,8% | R\$ 61 | -R\$ 389 | R\$ 357 | 8,4% |

---

## 2. Análise Detalhada — XP M5 · 11 Robôs

> 7 WIN M5 (EST-01, 04, 07, 13, 14, 15, 16) + 4 WDO M5 (WDO-01, 05, 07, 09)

### 2.1. Perfil de Excursão Adversa Diária (MAE M1 vs Trades Fechados)

| Escopo | MAE Médio | σ | P50 | P75 | P90 | P95 | MAE Máximo |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Global Intraday (M1)** | R\$ 340 | R\$ 292 | R\$ 286 | R\$ 514 | R\$ 701 | R\$ 844 | R\$ 2.061 |
| **Global Fechado (Trades)** | R\$ 351 | — | — | R\$ 473 | R\$ 728 | — | R\$ 1.994 |
| **WIN Isolado (M1)** | R\$ 218 | — | — | R\$ 304 | R\$ 449 | — | R\$ 903 |
| **WDO Isolado (M1)** | R\$ 284 | — | — | R\$ 445 | R\$ 622 | — | R\$ 1.550 |

### 2.2. Comparativo Baseline vs Stops (Total 2026 · OOS · IS)

| Cenário | Config Stop | Lucro Total | Max DD Diário | Max DD M1 Intra | Ret/DD | Sharpe | Pior Dia | Dias Parados | OOS (Jan-Mai) | IS (Mai-Nov) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Sem Stop (Baseline)** | — | +R\$ 48.061 | R\$ 4.331 | R\$ 4.650 | **11,10x** | 6,83 | -R\$ 1.742 | 0d (0,0%) | +R\$ 11.499 (2,66x) | +R\$ 36.562 (15,55x) |
| **Stop Global Ret/DD ★** | R\$ 1.150 | +R\$ 48.622 | R\$ 4.331 | R\$ 4.650 | **11,23x** | 7,03 | -R\$ 1.150 | 2d (0,9%) | +R\$ 11.468 (2,65x) | +R\$ 37.154 (21,11x) |
| **Stop Global Máx Lucro 💰** | R\$ 1.150 | +R\$ 48.622 | R\$ 4.331 | R\$ 4.650 | **11,23x** | 7,03 | -R\$ 1.150 | 2d (0,9%) | +R\$ 11.468 (2,65x) | +R\$ 37.154 (21,11x) |
| **Combo Multi-Escopo ⚡** | G R\$ 1.050 · W R\$ 400 · D R\$ 0 | +R\$ 47.041 | R\$ 3.807 | R\$ 4.126 | **12,36x** | 6,87 | -R\$ 1.050 | 28d (13,2%) | +R\$ 11.790 (3,10x) | +R\$ 35.251 (19,32x) |

### 2.3. Robustez Estatística (Walk-Forward & Monte Carlo)

- **Walk-Forward Rolling (60d treino → 20d teste):** 0/7 folds melhoraram Ret/DD OOS · Stop Mediano = **R\$ 550**.
- **Treino IS (Mai-Nov) -> Teste OOS Cego (Jan-Mai):** Stop calibrado `R\$ 725` → Base +R\$ 11.499 (2,66x) vs Stop +R\$ 10.076 (2,29x, 15d).
- **Treino OOS (Jan-Mai) -> Teste IS (Mai-Nov):** Stop calibrado `R\$ 0` → Base +R\$ 36.562 (15,55x) vs Stop +R\$ 36.562 (15,55x, 0d).
- **Monte Carlo IID (2.000 sims, stop R\$ 1.150):** Vence em Ret/DD **59,0%** · Reduz MaxDD **40,6%** · MaxDD P95 R\$ 4.012 → **R\$ 3.692**.
- **Monte Carlo Block Bootstrap 5d (2.000 sims):** Vence em Ret/DD **61,9%** · Reduz MaxDD **35,6%** · MaxDD P95 R\$ 4.728 → **R\$ 4.484**.

### 2.4. Análise Individual por Robô (MAE/MFE Real M1)

| Robô | Ativo | TF | Magic | Trades | Lucro Líq. | WR% | PF | Payoff | MAE P90 | MFE Méd | Eff% | Stop/Trade Sug. | Pior Dia | Stop/Dia Sug. | % Piores 15d |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **EST-13** | WIN | M5 | `88013` | 681 | +R\$ 8.626 | 55,8% | 1,62 | 1,27 | R\$ 74 | R\$ 60 | -7,3% | R\$ 87 | -R\$ 411 | R\$ 234 | 6,4% |
| **WDO-05** | WDO | M5 | `89005` | 759 | +R\$ 6.400 | 62,7% | 1,25 | 0,72 | R\$ 140 | R\$ 63 | -2,8% | R\$ 164 | -R\$ 480 | R\$ 262 | 22,0% |
| **WDO-01** | WDO | M5 | `89001` | 731 | +R\$ 6.370 | 61,8% | 1,28 | 0,75 | R\$ 130 | R\$ 56 | -0,3% | R\$ 152 | -R\$ 410 | R\$ 265 | 15,3% |
| **EST-14** | WIN | M5 | `88014` | 725 | +R\$ 5.782 | 55,3% | 1,36 | 1,09 | R\$ 74 | R\$ 55 | -7,1% | R\$ 87 | -R\$ 362 | R\$ 241 | 8,8% |
| **EST-15** | WIN | M5 | `88015` | 654 | +R\$ 5.355 | 61,2% | 1,41 | 0,90 | R\$ 74 | R\$ 49 | 10,0% | R\$ 87 | -R\$ 359 | R\$ 203 | 4,6% |
| **WDO-07** | WDO | M5 | `89007` | 474 | +R\$ 3.950 | 54,6% | 1,28 | 0,96 | R\$ 115 | R\$ 72 | -14,1% | R\$ 135 | -R\$ 470 | R\$ 232 | 11,1% |
| **EST-04** | WIN | M5 | `88004` | 359 | +R\$ 2.608 | 43,5% | 1,37 | 1,79 | R\$ 50 | R\$ 55 | -51,7% | R\$ 59 | -R\$ 204 | R\$ 144 | 0,0% |
| **EST-01** | WIN | M5 | `88001` | 876 | +R\$ 2.428 | 32,6% | 1,13 | 2,32 | R\$ 50 | R\$ 59 | -53,9% | R\$ 59 | -R\$ 328 | R\$ 208 | 5,5% |
| **WDO-09** | WDO | M5 | `89009` | 338 | +R\$ 2.400 | 50,9% | 1,18 | 1,13 | R\$ 120 | R\$ 79 | -41,6% | R\$ 142 | -R\$ 240 | R\$ 243 | 11,7% |
| **EST-07** | WIN | M5 | `88007` | 568 | +R\$ 2.399 | 34,0% | 1,18 | 2,30 | R\$ 54 | R\$ 56 | -37,2% | R\$ 64 | -R\$ 213 | R\$ 170 | 4,9% |
| **EST-16** | WIN | M5 | `88016` | 590 | +R\$ 1.743 | 55,9% | 1,13 | 0,89 | R\$ 74 | R\$ 51 | -12,9% | R\$ 87 | -R\$ 353 | R\$ 244 | 10,3% |

---

## 2. Análise Detalhada — Campeões · 8 Robôs

> 5 WIN (EST-04, 07, 13, 14, 15) + 3 WDO (WDO-01, 05, 07)

### 2.1. Perfil de Excursão Adversa Diária (MAE M1 vs Trades Fechados)

| Escopo | MAE Médio | σ | P50 | P75 | P90 | P95 | MAE Máximo |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Global Intraday (M1)** | R\$ 271 | R\$ 243 | R\$ 220 | R\$ 382 | R\$ 585 | R\$ 758 | R\$ 1.594 |
| **Global Fechado (Trades)** | R\$ 286 | — | — | R\$ 397 | R\$ 600 | — | R\$ 1.527 |
| **WIN Isolado (M1)** | R\$ 166 | — | — | R\$ 232 | R\$ 366 | — | R\$ 725 |
| **WDO Isolado (M1)** | R\$ 246 | — | — | R\$ 370 | R\$ 530 | — | R\$ 1.310 |

### 2.2. Comparativo Baseline vs Stops (Total 2026 · OOS · IS)

| Cenário | Config Stop | Lucro Total | Max DD Diário | Max DD M1 Intra | Ret/DD | Sharpe | Pior Dia | Dias Parados | OOS (Jan-Mai) | IS (Mai-Nov) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Sem Stop (Baseline)** | — | +R\$ 41.490 | R\$ 2.411 | R\$ 2.947 | **17,21x** | 7,25 | -R\$ 1.268 | 0d (0,0%) | +R\$ 11.405 (4,73x) | +R\$ 30.085 (17,97x) |
| **Stop Global Ret/DD ★** | R\$ 900 | +R\$ 41.923 | R\$ 2.411 | R\$ 2.947 | **17,39x** | 7,43 | -R\$ 900 | 2d (0,9%) | +R\$ 11.470 (4,76x) | +R\$ 30.453 (23,32x) |
| **Stop Global Máx Lucro 💰** | R\$ 900 | +R\$ 41.923 | R\$ 2.411 | R\$ 2.947 | **17,39x** | 7,43 | -R\$ 900 | 2d (0,9%) | +R\$ 11.470 (4,76x) | +R\$ 30.453 (23,32x) |
| **Combo Multi-Escopo ⚡** | G R\$ 0 · W R\$ 425 · D R\$ 350 | +R\$ 36.484 | R\$ 1.480 | R\$ 1.752 | **24,65x** | 6,49 | -R\$ 775 | 62d (29,2%) | +R\$ 10.048 (6,79x) | +R\$ 26.436 (32,48x) |

### 2.3. Robustez Estatística (Walk-Forward & Monte Carlo)

- **Walk-Forward Rolling (60d treino → 20d teste):** 1/7 folds melhoraram Ret/DD OOS · Stop Mediano = **R\$ 450**.
- **Treino IS (Mai-Nov) -> Teste OOS Cego (Jan-Mai):** Stop calibrado `R\$ 600` → Base +R\$ 11.405 (4,73x) vs Stop +R\$ 9.871 (3,74x, 12d).
- **Treino OOS (Jan-Mai) -> Teste IS (Mai-Nov):** Stop calibrado `R\$ 875` → Base +R\$ 30.085 (17,97x) vs Stop +R\$ 30.478 (23,79x, 1d).
- **Monte Carlo IID (2.000 sims, stop R\$ 900):** Vence em Ret/DD **86,8%** · Reduz MaxDD **54,8%** · MaxDD P95 R\$ 3.111 → **R\$ 2.911**.
- **Monte Carlo Block Bootstrap 5d (2.000 sims):** Vence em Ret/DD **85,8%** · Reduz MaxDD **49,6%** · MaxDD P95 R\$ 2.941 → **R\$ 2.707**.

### 2.4. Análise Individual por Robô (MAE/MFE Real M1)

| Robô | Ativo | TF | Magic | Trades | Lucro Líq. | WR% | PF | Payoff | MAE P90 | MFE Méd | Eff% | Stop/Trade Sug. | Pior Dia | Stop/Dia Sug. | % Piores 15d |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **EST-13** | WIN | M5 | `88013` | 681 | +R\$ 8.626 | 55,8% | 1,62 | 1,27 | R\$ 74 | R\$ 60 | -7,3% | R\$ 87 | -R\$ 411 | R\$ 234 | 8,0% |
| **WDO-05** | WDO | M5 | `89005` | 759 | +R\$ 6.400 | 62,7% | 1,25 | 0,72 | R\$ 140 | R\$ 63 | -2,8% | R\$ 164 | -R\$ 480 | R\$ 262 | 24,9% |
| **WDO-01** | WDO | M5 | `89001` | 731 | +R\$ 6.370 | 61,8% | 1,28 | 0,75 | R\$ 130 | R\$ 56 | -0,3% | R\$ 152 | -R\$ 410 | R\$ 265 | 31,2% |
| **EST-14** | WIN | M5 | `88014` | 725 | +R\$ 5.782 | 55,3% | 1,36 | 1,09 | R\$ 74 | R\$ 55 | -7,1% | R\$ 87 | -R\$ 362 | R\$ 241 | 8,0% |
| **EST-15** | WIN | M5 | `88015` | 654 | +R\$ 5.355 | 61,2% | 1,41 | 0,90 | R\$ 74 | R\$ 49 | 10,0% | R\$ 87 | -R\$ 359 | R\$ 203 | 4,1% |
| **WDO-07** | WDO | M5 | `89007` | 474 | +R\$ 3.950 | 54,6% | 1,28 | 0,96 | R\$ 115 | R\$ 72 | -14,1% | R\$ 135 | -R\$ 470 | R\$ 232 | 20,2% |
| **EST-04** | WIN | M5 | `88004` | 359 | +R\$ 2.608 | 43,5% | 1,37 | 1,79 | R\$ 50 | R\$ 55 | -51,7% | R\$ 59 | -R\$ 204 | R\$ 144 | 0,0% |
| **EST-07** | WIN | M5 | `88007` | 568 | +R\$ 2.399 | 34,0% | 1,18 | 2,30 | R\$ 54 | R\$ 56 | -37,2% | R\$ 64 | -R\$ 213 | R\$ 170 | 4,0% |

---

## 2. Análise Detalhada — Campeões + EST-09/10 · 10 Robôs

> 7 WIN (EST-04, 07, 09, 10, 13, 14, 15) + 3 WDO (WDO-01, 05, 07)

### 2.1. Perfil de Excursão Adversa Diária (MAE M1 vs Trades Fechados)

| Escopo | MAE Médio | σ | P50 | P75 | P90 | P95 | MAE Máximo |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Global Intraday (M1)** | R\$ 271 | R\$ 248 | R\$ 209 | R\$ 398 | R\$ 622 | R\$ 750 | R\$ 1.578 |
| **Global Fechado (Trades)** | R\$ 297 | — | — | R\$ 399 | R\$ 610 | — | R\$ 1.511 |
| **WIN Isolado (M1)** | R\$ 170 | — | — | R\$ 243 | R\$ 354 | — | R\$ 764 |
| **WDO Isolado (M1)** | R\$ 246 | — | — | R\$ 370 | R\$ 530 | — | R\$ 1.310 |

### 2.2. Comparativo Baseline vs Stops (Total 2026 · OOS · IS)

| Cenário | Config Stop | Lucro Total | Max DD Diário | Max DD M1 Intra | Ret/DD | Sharpe | Pior Dia | Dias Parados | OOS (Jan-Mai) | IS (Mai-Nov) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Sem Stop (Baseline)** | — | +R\$ 45.400 | R\$ 1.958 | R\$ 2.531 | **23,19x** | 7,68 | -R\$ 1.252 | 0d (0,0%) | +R\$ 11.753 (6,00x) | +R\$ 33.647 (20,55x) |
| **Stop Global Ret/DD ★** | R\$ 1.000 | +R\$ 45.652 | R\$ 1.958 | R\$ 2.531 | **23,32x** | 7,79 | -R\$ 1.000 | 1d (0,5%) | +R\$ 11.753 (6,00x) | +R\$ 33.899 (24,48x) |
| **Stop Global Máx Lucro 💰** | R\$ 1.000 | +R\$ 45.652 | R\$ 1.958 | R\$ 2.531 | **23,32x** | 7,79 | -R\$ 1.000 | 1d (0,5%) | +R\$ 11.753 (6,00x) | +R\$ 33.899 (24,48x) |
| **Combo Multi-Escopo ⚡** | G R\$ 0 · W R\$ 425 · D R\$ 350 | +R\$ 39.700 | R\$ 1.352 | R\$ 1.650 | **29,36x** | 6,77 | -R\$ 775 | 64d (30,2%) | +R\$ 9.914 (7,33x) | +R\$ 29.786 (28,13x) |

### 2.3. Robustez Estatística (Walk-Forward & Monte Carlo)

- **Walk-Forward Rolling (60d treino → 20d teste):** 2/7 folds melhoraram Ret/DD OOS · Stop Mediano = **R\$ 375**.
- **Treino IS (Mai-Nov) -> Teste OOS Cego (Jan-Mai):** Stop calibrado `R\$ 475` → Base +R\$ 11.753 (6,00x) vs Stop +R\$ 7.515 (3,36x, 24d).
- **Treino OOS (Jan-Mai) -> Teste IS (Mai-Nov):** Stop calibrado `R\$ 0` → Base +R\$ 33.647 (20,55x) vs Stop +R\$ 33.647 (20,55x, 0d).
- **Monte Carlo IID (2.000 sims, stop R\$ 1.000):** Vence em Ret/DD **61,9%** · Reduz MaxDD **34,0%** · MaxDD P95 R\$ 3.029 → **R\$ 2.892**.
- **Monte Carlo Block Bootstrap 5d (2.000 sims):** Vence em Ret/DD **62,5%** · Reduz MaxDD **38,0%** · MaxDD P95 R\$ 2.750 → **R\$ 2.648**.

### 2.4. Análise Individual por Robô (MAE/MFE Real M1)

| Robô | Ativo | TF | Magic | Trades | Lucro Líq. | WR% | PF | Payoff | MAE P90 | MFE Méd | Eff% | Stop/Trade Sug. | Pior Dia | Stop/Dia Sug. | % Piores 15d |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **EST-13** | WIN | M5 | `88013` | 681 | +R\$ 8.626 | 55,8% | 1,62 | 1,27 | R\$ 74 | R\$ 60 | -7,3% | R\$ 87 | -R\$ 411 | R\$ 234 | 7,3% |
| **WDO-05** | WDO | M5 | `89005` | 759 | +R\$ 6.400 | 62,7% | 1,25 | 0,72 | R\$ 140 | R\$ 63 | -2,8% | R\$ 164 | -R\$ 480 | R\$ 262 | 27,1% |
| **WDO-01** | WDO | M5 | `89001` | 731 | +R\$ 6.370 | 61,8% | 1,28 | 0,75 | R\$ 130 | R\$ 56 | -0,3% | R\$ 152 | -R\$ 410 | R\$ 265 | 26,2% |
| **EST-14** | WIN | M5 | `88014` | 725 | +R\$ 5.782 | 55,3% | 1,36 | 1,09 | R\$ 74 | R\$ 55 | -7,1% | R\$ 87 | -R\$ 362 | R\$ 241 | 7,7% |
| **EST-15** | WIN | M5 | `88015` | 654 | +R\$ 5.355 | 61,2% | 1,41 | 0,90 | R\$ 74 | R\$ 49 | 10,0% | R\$ 87 | -R\$ 359 | R\$ 203 | 6,3% |
| **WDO-07** | WDO | M5 | `89007` | 474 | +R\$ 3.950 | 54,6% | 1,28 | 0,96 | R\$ 115 | R\$ 72 | -14,1% | R\$ 135 | -R\$ 470 | R\$ 232 | 17,1% |
| **EST-04** | WIN | M5 | `88004` | 359 | +R\$ 2.608 | 43,5% | 1,37 | 1,79 | R\$ 50 | R\$ 55 | -51,7% | R\$ 59 | -R\$ 204 | R\$ 144 | 0,0% |
| **EST-09** | WIN | M5 | `88009` | 370 | +R\$ 2.591 | 59,2% | 1,34 | 0,92 | R\$ 52 | R\$ 58 | -47,7% | R\$ 61 | -R\$ 104 | R\$ 137 | 3,4% |
| **EST-07** | WIN | M5 | `88007` | 568 | +R\$ 2.399 | 34,0% | 1,18 | 2,30 | R\$ 54 | R\$ 56 | -37,2% | R\$ 64 | -R\$ 213 | R\$ 170 | 4,2% |
| **EST-10** | WIN | M5 | `88010` | 171 | +R\$ 1.319 | 61,4% | 1,39 | 0,88 | R\$ 52 | R\$ 59 | -34,7% | R\$ 62 | -R\$ 52 | R\$ 108 | 3,0% |

---

## 3. Integração no MT5 (`Jumba_Portfolio_Live_Monitor` v4.00)

O gerenciador em tempo real roda dentro do próprio gráfico do **`Jumba_Portfolio_Live_Monitor.mq5`** (timer de **1 segundo** + `OnTradeTransaction`), somando o P&L fechado do dia + flutuante em aberto e gravando as travas baseadas em data (`YYYYMMDD`) nas GlobalVariables do terminal:

- `JUMBA_DAILY_STOP_GLOBAL`: trava todos os robôs `WIN` (`88000..88016`) e `WDO` (`89000..89016`).
- `JUMBA_DAILY_STOP_WIN`: trava apenas os robôs `WIN` mantendo o `WDO` operando normalmente.
- `JUMBA_DAILY_STOP_WDO`: trava apenas os robôs `WDO` mantendo o `WIN` operando normalmente.
- **Reset automático:** na virada do pregão (`YYYYMMDD` diferente), a `Jumba_SafetyGuard.mqh` limpa as variáveis do dia anterior e libera as entradas automaticamente.

### Presets Recomendados de Input no Monitor (`Proposta B · 11 Robôs`)

| Perfil de Risco | `InpMaxDailyLossGlobal` | `InpMaxDailyLossWin` | `InpMaxDailyLossWdo` |
| :--- | :---: | :---: | :---: |
| **Conservador (Global Ret/DD ★)** | `850.0` | `0.0` | `0.0` |
| **Máx Lucro Global 💰** | `1100.0` | `0.0` | `0.0` |
| **Combo Multi-Escopo ⚡** | `0.0` | `400.0` | `350.0` |
