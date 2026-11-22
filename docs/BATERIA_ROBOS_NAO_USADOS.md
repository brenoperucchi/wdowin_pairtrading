# Bateria de Validação & Inclusão — 24 Robôs Não Utilizados (vs Top 8 da 2004051)

> **Período:** `2026-01-02` a `2026-11-06` (`212` pregões) · **Treino (IS):** `Jan–Jul` (`145d`) · **Validação Cega (OOS):** `Ago–Nov` (`67d`) · **Custos B3 reais:** `R\$ 2/lote` WIN · `R\$ 5/lote` WDO

## 1. Resumo Executivo

- **Robôs analisados:** `24` não ativos na conta `2004051` (`11 WIN` + `13 WDO`).
- **Antes dos ajustes (Baseline atual do EA):** `0` aprovados nos 5 gates.
- **Após ajustes controlados (selecionados 100% no IS `Jan–Jul` e testados às cegas no OOS `Ago–Nov`):**
  - **`5` APROVADOS** (passam nos **5/5 gates**: Qualidade IS + OOS Cego + Ambos Semestres + `>=7/11` Meses + Stress `+50%` custo)
  - **`1` RESERVAS** (passam no OOS Cego e Stress `+50%`, com 3–4/5 gates)
  - **`18` REPROVADOS** (não sustentam OOS cego ou stress de custo mesmo após ajustes)

### Portfólio Base Atual (`2004051` — Top 8: `EST-04, 07, 13, 14, 15 + WDO-01, 05, 07`)

| Regime de Stop | Retorno 2026 | Max DD | Ret/DD | Sharpe | IS Ret/DD | OOS Cego Ret/DD | Pior Dia | Dias Cortados |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Sem Stop | +R\$ 41.490 | R\$ 2.411 | **17.21x** | 7.25 | 10.29x | **27.22x** | -R\$ 1.268 | 0 |
| Stop Atual (`G 850 + WIN 400 + WDO 550`) | +R\$ 37.388 | R\$ 2.203 | **16.97x** | 6.32 | 9.96x | **19.88x** | -R\$ 850 | 33 |
| Stop Indep (`WIN 400 + WDO 550`, `G=0`) | +R\$ 38.410 | R\$ 2.203 | **17.44x** | 6.60 | 10.42x | **19.88x** | -R\$ 950 | 33 |

---

## 2. Resultado da Bateria nos 24 Robôs (Original vs Ajustado IS → OOS Cego)

| Robô | Ativo | Veredito | Gates | Ajuste Escolhido (100% IS) | Base Ret/DD | Ajust. Ret/DD | Líq. 2026 | PF | Trades | OOS Cego (Ago–Nov) | Stress +50% PF | Platô IS |
| :--- | :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **EST-06** | WIN M5 | 🟢 **APROVADO** | ✅IS ✅OOS ✅2Sem ✅Mes ✅Str | `Ordem=CURRENT + WallBE=BE_ZERO + TP=TP_MIDWALL` | -0.83x | **6.34x** | +R\$ 2.886 | 1.16 | 883 | +R\$ 979 (PF 1.16) | 1.11 | 26% |
| **WDO-04** | WDO M5 | 🟢 **APROVADO** | ✅IS ✅OOS ✅2Sem ✅Mes ✅Str | `Ordem=MARKET + TP=TP_MIDWALL + Janela=MORNING_09_12` | 0.05x | **4.28x** | +R\$ 2.910 | 1.49 | 146 | +R\$ 980 (PF 1.54) | 1.42 | 42% |
| **WDO-16** | WDO M5 | 🟢 **APROVADO** | ✅IS ✅OOS ✅2Sem ✅Mes ✅Str | `Ordem=MARKET + TP=TP_MIDWALL + Janela=NO_LUNCH` | 0.74x | **3.78x** | +R\$ 3.875 | 1.47 | 148 | +R\$ 1.245 (PF 1.49) | 1.42 | 41% |
| **EST-10** | WIN M5 | 🟢 **APROVADO** | ✅IS ✅OOS ✅2Sem ✅Mes ✅Str | `MaxTr=1/d` | 1.25x | **3.64x** | +R\$ 1.495 | 1.47 | 170 | +R\$ 864 (PF 2.04) | 1.41 | 18% |
| **EST-09** | WIN M5 | 🟢 **APROVADO** | ✅IS ✅OOS ✅2Sem ✅Mes ✅Str | `MaxTr=2/d` | 1.81x | **3.40x** | +R\$ 2.385 | 1.31 | 373 | +R\$ 1.110 (PF 1.52) | 1.26 | 8% |
| **EST-01** | WIN M5 | 🟡 RESERVA | ❌IS ✅OOS ✅2Sem ✅Mes ✅Str | `WallBE=BE_WALL_2STAGE(15) + TP=TP_MIDWALL` | 2.07x | **3.54x** | +R\$ 2.434 | 1.14 | 852 | +R\$ 771 (PF 1.13) | 1.09 | 9% |
| **WDO-10** | WDO M5 | 🔴 REPROVADO | ✅IS ❌OOS ✅2Sem ✅Mes ✅Str | `Ordem=LIMIT_B1_EXT + WallBE=BE_WALL_2STAGE(1) + MaxTr=1/d` | 1.71x | **7.58x** | +R\$ 2.425 | 1.61 | 162 | +R\$ 185 (PF 1.15) | 1.48 | 68% |
| **WDO-03** | WDO M5 | 🔴 REPROVADO | ✅IS ❌OOS ✅2Sem ✅Mes ✅Str | `Ordem=LIMIT_B1_EXT + WallBE=BE_ZERO + MaxLoss=1/d` | 1.43x | **6.59x** | +R\$ 3.260 | 1.66 | 175 | -R\$ 165 (PF 0.91) | 1.56 | 92% |
| **WDO-15** | WDO M5 | 🔴 REPROVADO | ✅IS ❌OOS ✅2Sem ✅Mes ✅Str | `Ordem=LIMIT_B1_MID + WallBE=BE_ZERO + MaxTr=1/d + Janela=MORNING_09_12` | -0.42x | **4.16x** | +R\$ 2.455 | 1.63 | 122 | +R\$ 325 (PF 1.32) | 1.54 | 22% |
| **WDO-08** | WDO M5 | 🔴 REPROVADO | ✅IS ❌OOS ✅2Sem ✅Mes ✅Str | `Ordem=LIMIT_B1_EXT + WallBE=BE_ZERO` | 1.51x | **3.60x** | +R\$ 1.205 | 1.40 | 86 | +R\$ 190 (PF 1.21) | 1.32 | 86% |
| **WDO-02** | WDO M5 | 🔴 REPROVADO | ✅IS ❌OOS ✅2Sem ✅Mes ✅Str | `Ordem=LIMIT_B1_EXT + WallBE=BE_WALL_2STAGE(1) + MaxTr=1/d` | 2.31x | **2.54x** | +R\$ 1.765 | 1.21 | 205 | +R\$ 275 (PF 1.10) | 1.15 | 41% |
| **EST-02** | WIN M5 | 🔴 REPROVADO | ✅IS ❌OOS ✅2Sem ✅Mes ✅Str | `WallBE=BE_WALL_2STAGE(15) + TP=TP_MIDWALL + MaxTr=2/d + Janela=MORNING_09_12` | -0.05x | **2.40x** | +R\$ 741 | 1.27 | 120 | +R\$ 91 (PF 1.10) | 1.22 | 33% |
| **WDO-11** | WDO M5 | 🔴 REPROVADO | ✅IS ❌OOS ✅2Sem ✅Mes ✅Str | `Janela=NY_1000_1630` | 1.82x | **0.92x** | +R\$ 3.090 | 1.22 | 333 | -R\$ 1.465 (PF 0.74) | 1.13 | 86% |
| **WDO-12** | WDO M5 | 🔴 REPROVADO | ✅IS ❌OOS ✅2Sem ❌Mes ✅Str | `Ordem=LIMIT_B1_MID + WallBE=BE_ZERO + TP=TP_MIDWALL + Janela=NY_1000_1630` | -0.14x | **3.26x** | +R\$ 2.675 | 1.24 | 358 | +R\$ 425 (PF 1.13) | 1.14 | 43% |
| **WDO-06** | WDO M5 | 🔴 REPROVADO | ❌IS ❌OOS ✅2Sem ✅Mes ✅Str | `Ordem=LIMIT_B1_EXT + WallBE=BE_ZERO + TP=TP_MIDWALL + MaxTr=1/d + Janela=NY_1000_1630` | 0.93x | **1.66x** | +R\$ 580 | 1.41 | 46 | -R\$ 80 (PF 0.79) | 1.32 | 67% |
| **EST-03** | WIN M15 | 🔴 REPROVADO | ✅IS ❌OOS ✅2Sem ❌Mes ✅Str | `Ordem=LIMIT_WALL + WallBE=BE_WALL_SHIELD(25) + TP=TP_MAIN_WALL + MaxTr=1/d + Janela=NY_1000_1630` | -1.00x | **1.52x** | +R\$ 668 | 1.28 | 202 | -R\$ 98 (PF 0.87) | 1.18 | 48% |
| **WDO-14** | WDO M5 | 🔴 REPROVADO | ✅IS ❌OOS ❌2Sem ✅Mes ✅Str | `MaxTr=1/d + Janela=NY_1000_1630` | 0.74x | **0.52x** | +R\$ 1.090 | 1.15 | 170 | -R\$ 1.250 (PF 0.64) | 1.06 | 82% |
| **EST-11** | WIN M5 | 🔴 REPROVADO | ❌IS ✅OOS ❌2Sem ❌Mes ✅Str | `Ordem=CURRENT + WallBE=BE_ZERO + TP=TP_MAIN_WALL + MaxLoss=1/d + Janela=NY_1000_1630` | 0.85x | **4.53x** | +R\$ 2.088 | 1.71 | 141 | +R\$ 1.408 (PF 25.28) | 1.63 | 22% |
| **WDO-09** | WDO M5 | 🔴 REPROVADO | ✅IS ❌OOS ❌2Sem ❌Mes ✅Str | `Ordem=LIMIT_B1_EXT + WallBE=BE_ZERO` | 1.99x | **2.42x** | +R\$ 2.120 | 1.17 | 394 | -R\$ 230 (PF 0.94) | 1.09 | 56% |
| **WDO-13** | WDO M5 | 🔴 REPROVADO | ❌IS ❌OOS ❌2Sem ✅Mes ❌Str | `Janela=MORNING_09_12` | 0.42x | **0.52x** | +R\$ 1.415 | 1.13 | 248 | -R\$ 1.350 (PF 0.69) | 1.04 | 82% |
| **EST-12** | WIN M5 | 🔴 REPROVADO | ❌IS ❌OOS ✅2Sem ❌Mes ❌Str | `TP=TP_MIDWALL + MaxLoss=1/d + Janela=MORNING_09_12` | -0.63x | **0.46x** | +R\$ 293 | 1.09 | 141 | -R\$ 166 (PF 0.83) | 1.03 | 1% |
| **EST-16** | WIN M5 | 🔴 REPROVADO | ❌IS ❌OOS ❌2Sem ❌Mes ❌Str | `Ordem=LIMIT_B1_EXT + WallBE=BE_ZERO + MaxTr=1/d` | -0.05x | **0.18x** | +R\$ 113 | 1.04 | 78 | -R\$ 302 (PF 0.69) | 0.98 | 32% |
| **EST-05** | WIN M15 | 🔴 REPROVADO | ❌IS ❌OOS ❌2Sem ❌Mes ❌Str | `MaxLoss=2/d + Janela=NY_1000_1630` | -0.75x | **-0.34x** | -R\$ 159 | 0.91 | 158 | -R\$ 465 (PF 0.17) | 0.84 | 8% |
| **EST-08** | WIN M5 | 🔴 REPROVADO | ❌IS ❌OOS ❌2Sem ❌Mes ❌Str | `ORIGINAL (sem ajuste)` | -0.37x | **-0.37x** | -R\$ 656 | 0.95 | 656 | +R\$ 546 (PF 1.14) | 0.90 | 0% |

---

## 3. Teste de Inclusão 1-a-1 no Portfólio Atual (`Top 8 + 1 Candidato`)

Avaliado com o motor M1 intraday real (`G 850 + WIN 400 + WDO 550` e `Sem Stop`).

| Candidato | Veredito | Ajuste | Corr. Top8 | Corr. Ativo | PnL Piores 15d | ΔRet (Stop Live) | ΔDD (Stop Live) | Ret/DD (Stop Live) | ΔOOS Ret/DD | Ret/DD (Sem Stop) |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **WDO-16** (WDO) | APROVADO | `Ordem=MARKET + TP=TP_MIDWALL + Janela=NO_LUNCH` | +0.23 | +0.28 | -R\$ 690 | +R\$ 4.065 | -R\$ 320 | **22.01x** (+5,04x) | -5,41x | 18.81x (+1,60x) |
| **EST-09** (WIN) | APROVADO | `MaxTr=2/d` | -0.03 | -0.00 | -R\$ 96 | +R\$ 2.738 | -R\$ 361 | **21.78x** (+4,81x) | +10,00x | 21.42x (+4,21x) |
| **EST-10** (WIN) | APROVADO | `MaxTr=1/d` | +0.01 | +0.04 | -R\$ 105 | +R\$ 1.884 | -R\$ 69 | **18.40x** (+1,43x) | +3,03x | 18.37x (+1,16x) |
| **EST-06** (WIN) | APROVADO | `Ordem=CURRENT + WallBE=BE_ZERO + TP=TP_MIDWALL` | +0.10 | +0.09 | -R\$ 625 | +R\$ 2.280 | +R\$ 88 | **17.31x** (+0,34x) | -0,27x | 18.24x (+1,03x) |
| **WDO-04** (WDO) | APROVADO | `Ordem=MARKET + TP=TP_MIDWALL + Janela=MORNING_09_12` | +0.18 | +0.20 | -R\$ 55 | +R\$ 2.510 | +R\$ 371 | **15.50x** (-1,47x) | -2,77x | 19.20x (+1,99x) |
| **WDO-06 (ORIG)** (WDO) | RESERVA | `ORIGINAL (sem ajuste)` | +0.05 | +0.03 | +R\$ 150 | +R\$ 1.095 | -R\$ 165 | **18.88x** (+1,91x) | -1,85x | 17.56x (+0,35x) |
| **EST-01** (WIN) | RESERVA | `WallBE=BE_WALL_2STAGE(15) + TP=TP_MIDWALL` | +0.10 | +0.14 | -R\$ 694 | +R\$ 2.478 | +R\$ 379 | **15.44x** (-1,53x) | +3,02x | 15.75x (-1,46x) |
| **WDO-09 (ORIG)** (WDO) | RESERVA | `ORIGINAL (sem ajuste)` | +0.28 | +0.30 | -R\$ 695 | +R\$ 782 | +R\$ 406 | **14.63x** (-2,34x) | -6,33x | 14.91x (-2,30x) |
| **WDO-10 (ORIG)** (WDO) | RESERVA | `ORIGINAL (sem ajuste)` | +0.06 | -0.00 | -R\$ 150 | +R\$ 192 | +R\$ 675 | **13.06x** (-3,91x) | -4,92x | 15.39x (-1,82x) |
| **WDO-02 (ORIG)** (WDO) | RESERVA | `ORIGINAL (sem ajuste)` | +0.48 | +0.55 | -R\$ 2.005 | +R\$ 902 | +R\$ 1.081 | **11.66x** (-5,31x) | -7,19x | 12.63x (-4,58x) |

---

## 4. Expansão Forward Stepwise (Guiada 100% no IS → Validada no OOS Cego)

### 4.1 Apenas Candidatos `APROVADO` — Com Stop Atual (`G 850 + WIN 400 + WDO 550`)

| Passo | Robôs | Adicionado | Ajuste | Retorno 2026 | Max DD | Ret/DD | Sharpe | IS Ret/DD | OOS Cego Ret/DD | OOS Cego Líq. | Dias Cortados |
| :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0 | **8** | BASE Top 8 (2004051) | `EST-04,07,13,14,15 + WDO-01,05,07` | +R\$ 37.388 | R\$ 2.203 | **16.97x** | 6.32 | 9.96x | **19.88x** | +R\$ 15.445 | 33 |
| 1 | **9** | WDO-16 | `Ordem=MARKET + TP=TP_MIDWALL + Janela=NO_LUNCH` | +R\$ 41.453 | R\$ 1.883 | **22.01x** | 6.46 | 13.78x | **14.47x** | +R\$ 15.500 | 45 |
| 2 | **10** | EST-09 | `MaxTr=2/d` | +R\$ 44.191 | R\$ 1.767 | **25.01x** | 6.83 | 15.24x | **14.68x** | +R\$ 17.266 | 45 |
| 3 | **11** | WDO-04 | `Ordem=MARKET + TP=TP_MIDWALL + Janela=MORNING_09_12` | +R\$ 47.106 | R\$ 1.749 | **26.93x** | 6.76 | 16.65x | **13.15x** | +R\$ 17.991 | 52 |
| 4 | **12** | EST-06 | `Ordem=CURRENT + WallBE=BE_ZERO + TP=TP_MIDWALL` | +R\$ 48.382 | R\$ 1.804 | **26.82x** | 6.75 | 17.05x | **12.27x** | +R\$ 17.631 | 58 |
| 5 | **13** | EST-10 | `MaxTr=1/d` | +R\$ 49.431 | R\$ 2.233 | **22.14x** | 6.74 | 15.76x | **7.95x** | +R\$ 17.761 | 58 |

### 4.2 Apenas Candidatos `APROVADO` — Sem Stop Diário

| Passo | Robôs | Adicionado | Retorno 2026 | Max DD | Ret/DD | Sharpe | IS Ret/DD | OOS Cego Ret/DD | OOS Cego Líq. |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0 | **8** | BASE Top 8 (2004051) | +R\$ 41.490 | R\$ 2.411 | **17.21x** | 7.25 | 10.29x | **27.22x** | +R\$ 16.687 |
| 1 | **9** | EST-09 | +R\$ 43.875 | R\$ 2.048 | **21.42x** | 7.60 | 12.73x | **30.90x** | +R\$ 17.797 |
| 2 | **10** | WDO-04 | +R\$ 46.785 | R\$ 1.908 | **24.52x** | 7.65 | 14.68x | **26.82x** | +R\$ 18.777 |
| 3 | **11** | WDO-16 | +R\$ 50.660 | R\$ 1.868 | **27.12x** | 7.37 | 16.40x | **17.61x** | +R\$ 20.022 |
| 4 | **12** | EST-10 | +R\$ 52.155 | R\$ 1.797 | **29.02x** | 7.52 | 17.40x | **17.97x** | +R\$ 20.886 |
| 5 | **13** | EST-06 | +R\$ 55.041 | R\$ 1.819 | **30.26x** | 7.66 | 18.24x | **19.66x** | +R\$ 21.865 |
