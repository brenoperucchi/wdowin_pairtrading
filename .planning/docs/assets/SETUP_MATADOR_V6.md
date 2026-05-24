# Setup Matador V6 — Arquitetura Hibrida de 3 Setups

> **Versao:** V6 (Mai 2026)
> **Motor de Backtest:** `run_backtest_cooldown()` validado M1 (99.2% concordancia)
> **Periodo de Teste:** 126.770 barras M5 (~5 anos, Mar/2021 - Mar/2026)

---

## 1. Arquitetura do Portfolio

A V6 evolui a arquitetura de um sistema monolitico (Consenso unico) para um portfolio modular de **3 setups independentes** operando em paralelo:

| Setup | Modelo WDO | Modelo DI | Filtro NWE | Status |
|-------|------------|-----------|------------|--------|
| **Consenso** | OLS Rolling 40 | Kalman (1e-4, 1e-3) | Nao | Validado (Hibrido V1) |
| **WDO_NWE** | OLS Rolling 40 | N/A (isolado) | Sim (BW=1) | **Otimizado** |
| **DI_NWE** | N/A (isolado) | Kalman (1e-4, 1e-3) | Sim (BW=1, =WDO) | **Otimizado** |

### Racional
Cada setup captura um regime diferente do mercado:
- **Consenso:** Opera quando WDO e DI convergem (alta conviccao, baixa frequencia)
- **WDO_NWE:** Captura distorcoes do dolar quando o DI nao confirma (fluxo puro)
- **DI_NWE:** Captura movimentos macro de juros sem depender do dolar

---

## 2. Setup WDO_NWE (Otimizado)

### 2.1 Modelo Estatistico
| Parametro | Valor |
|-----------|-------|
| Modelo | OLS Rolling |
| Window | 40 barras M5 |
| Par | WIN x WDO |

### 2.2 Filtro Nadaraya-Watson (NWE)
Aplicado ao preco do WIN para filtrar entradas contra a tendencia.

| Parametro | Valor V5 (legado) | **Valor V6 (otimizado)** |
|-----------|-------------------|--------------------------|
| Bandwidth | 8 | **1** |
| Lookback | 95 | **100** |
| MAE Multiplier | 3.0 | **2.0** |
| Proximity | 10% | **15%** |
| is_up filter | Sim | **Nao (desligado)** |

> **Nota:** O BW=1 cria um envelope ultra-colado ao preco. Combinado com Proximity=15%, o filtro permite entradas quando o preco esta proximo da banda inferior/superior, sem exigir cruzamento completo. O filtro direcional (`is_up`) foi desligado pois nao adicionou valor estatistico.

### 2.3 Regras de Trade

| Parametro | Valor |
|-----------|-------|
| Z-Score de Entrada | **2.2** |
| Stop Loss | **300 pts** |
| Take Profit | **600 pts** |
| Horario de Entrada | **10:00 - 16:00** |
| Fechamento Forcado | 17:30 |
| Cooldown | **3 barras (15 min)** |
| Break-Even | Nao utilizado (TP <= 600) |

### 2.4 Performance (5 anos, 126.770 barras M5)

| Metrica | Valor |
|---------|-------|
| **Trades** | **700** (~11.7/mes) |
| **Win Rate** | **45.0%** |
| **PnL Total** | **+37.890 pts** |
| **Max Drawdown** | **3.275 pts** |
| **Ret/DD** | **11.57** |
| PnL Medio/Trade | +54.1 pts |

### 2.5 Evolucao Anual (setup com NWE BW=1 LB=100 MAE=2.0 antes do fine-tuning de exits)

| Ano | Trades | WR | PnL |
|-----|--------|----|-----|
| 2021 | ~80 | ~42% | Positivo |
| 2022 | ~120 | ~43% | Positivo |
| 2023 | ~160 | ~44% | Positivo |
| 2024 | ~150 | ~46% | Positivo |
| 2025 | ~220 | ~47% | Forte positivo |
| 2026 | ~30 | ~50% | Positivo |

---

## 3. Setup DI_NWE (Otimizado)

### 3.1 Modelo Estatistico
| Parametro | Valor |
|-----------|-------|
| Modelo | **Kalman Filter** |
| `delta` (trans_cov) | `1e-4` |
| `vt` (obs_cov) | `1e-3` |
| Z-Score Window | 40 barras M5 |
| Par | WIN x DI |

> O DI usa Kalman (nao OLS) por heranca do Hibrido V1, onde o Kalman demonstrou melhor adaptacao ao spread WIN x DI.

### 3.2 Filtro Nadaraya-Watson (NWE)
**Unificado com o WDO** — mesmo filtro para ambos os setups isolados.

| Parametro | Valor |
|-----------|-------|
| Bandwidth | **1** |
| Lookback | **100** |
| MAE Multiplier | **2.0** |
| Proximity | **15%** |
| is_up filter | **Nao (desligado)** |

> O NWE unificado simplifica a calibracao em producao (um unico filtro de tendencia para ambos os setups).

### 3.3 Regras de Trade

| Parametro | Valor |
|-----------|-------|
| Z-Score de Entrada | **1.8** |
| Stop Loss | **300 pts** |
| Take Profit | **400 pts** |
| Horario de Entrada | **09:00 - 15:00** |
| Fechamento Forcado | 17:30 |
| Cooldown | **2 barras (10 min)** |
| Break-Even | Nao utilizado (TP <= 600) |

> Nota: O DI opera com Z=1.8 (mais agressivo que o WDO com Z=2.2) e TP=400 (mais curto). Isso reflete o carater "scalper" do Kalman — sinais mais frequentes e saidas mais rapidas. O horario fecha as 15h (1h antes do WDO) porque o spread WIN x DI perde qualidade no fim do pregao.

### 3.4 Performance (5 anos, 126.770 barras M5)

| Metrica | Valor |
|---------|-------|
| **Trades** | **3.192** (~53/mes) |
| **Win Rate** | **45.05%** |
| **PnL Total** | **+39.710 pts** |
| **Max Drawdown** | **8.790 pts** |
| **Ret/DD** | **4.52** |
| PnL Medio/Trade | +12.4 pts |

### 3.5 Comparativo WDO_NWE vs DI_NWE

| Metrica | WDO_NWE | DI_NWE |
|---------|---------|--------|
| Modelo | OLS | Kalman |
| Z-Score | 2.2 | 1.8 |
| SL / TP | 300 / 600 | 300 / 400 |
| Horario | 10-16h | 09-15h |
| Trades | 700 | 3.192 |
| PnL | +37.890 | +39.710 |
| DD | 3.275 | 8.790 |
| Ret/DD | 11.57 | 4.52 |
| Perfil | Sniper (baixa freq) | Scalper (alta freq) |

---

## 4. Setup Consenso (Referencia V5)

Mantido inalterado da V5 como baseline do portfolio.

| Parametro | Valor |
|-----------|-------|
| Modelo WDO | OLS Window 40 |
| Modelo DI | OLS Window 40 |
| Z_ENTRY | 2.2 |
| Z_ATTENTION | 1.6 |
| SL | 300 |
| TP | 500 |
| Horario | 09:00 - 16:00 |
| NWE | Nao utilizado |

---

## 5. Auditoria do Motor de Backtest

O motor `run_backtest_cooldown()` foi auditado em Mai/2026:

- **M5 vs M1:** 128/129 trades concordantes (99.2%)
- **Vies TP/SL:** 0 barras ambiguas no setup WDO_NWE (SL+TP < range M5 tipico)
- **Unico trade divergente:** 2022-10-07 14:55 (BUY), M5=TP, M1=SL (delta -800 pts)
- **Impacto total do vies:** -715 pts em 5 anos (desprezivel)

> A entrada ocorre no CLOSE da barra de sinal M5. Os exits sao verificados via High/Low das barras subsequentes. EOD forcado as 17:30.

---

## 6. Historico de Versoes

| Versao | Data | Mudanca Principal |
|--------|------|-------------------|
| V4 | 2026-04 | Kalman duplo + NWE + Consenso |
| V5 | 2026-05 | Johansen Gate eliminado, 35k barras |
| **V6** | **2026-05** | **Portfolio 3 setups, WDO_NWE otimizado (BW=1), 5 anos de dados** |
