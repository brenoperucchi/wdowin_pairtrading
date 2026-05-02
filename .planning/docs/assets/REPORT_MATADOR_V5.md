# 📊 Relatório de Backtest — Setup Matador V5

Período: **35,000 barras M5** (~1.2 anos de pregão intraday)

Motor: `run_matador_v5_johansen.py` | Kalman + NWE + Johansen Gate

## 1. Desempenho por Setup Individual (Bateria 1 — V4 Puro)

| Setup | PnL (R$) | Max DD (R$) | Ret/DD | Profit Factor | Trades | Win Rate |
|-------|----------|-------------|--------|---------------|--------|----------|
| WDO Kalman (+NWE) | R$6830 | R$859 | 7.95x | 1.45 | 411 | 37.7% |
| DI Kalman (+NWE) | R$7224 | R$1207 | 5.99x | 1.33 | 576 | 35.6% |
| Consenso COM NWE | R$6966 | R$540 | 12.90x | 1.47 | 402 | 38.1% |
| Consenso SEM NWE (puro) | R$9588 | R$1192 | 8.04x | 1.44 | 598 | 38.1% |

## 2. Desempenho do Portfólio (Bateria 1 — V4 Puro)

| Portfólio | PnL (R$) | Max DD (R$) | Ret/DD | Profit Factor | Trades | Win Rate |
|-----------|----------|-------------|--------|---------------|--------|----------|
| PORT WDO+DI (sem cons) | R$14054 | R$1605 | 8.76x | 1.38 | 710 | 36.3% |
| PORT WDO+DI+CONS(NWE) | R$21020 | R$1847 | 11.38x | 1.41 | 729 | 36.8% |
| PORT WDO+DI+CONS(puro) | R$23642 | R$1659 | 14.25x | 1.41 | 964 | 37.4% |

## 3. Desempenho com Johansen Gate (Bateria 2)

Johansen aberto: WDO=16.8% | DI=17.0%

| Setup | PnL (R$) | Max DD (R$) | Ret/DD | Profit Factor | Trades | Win Rate |
|-------|----------|-------------|--------|---------------|--------|----------|
| WDO Kalman (+NWE+JOH) | R$20 | R$120 | 0.17x | 1.07 | 7 | 28.6% |
| DI Kalman (+NWE+JOH) | R$458 | R$240 | 1.91x | 1.69 | 20 | 45.0% |
| Consenso COM NWE+JOH | R$-107 | R$120 | -0.89x | 0.41 | 4 | 25.0% |
| Consenso SEM NWE+JOH | R$-241 | R$194 | -1.24x | 0.33 | 8 | 25.0% |

## 4. Conclusão

O Johansen Gate **sufoca** o setup, reduzindo de 964 trades para 30 e o PnL de R$23642 para R$237. A configuração V4 Pura (Kalman + NWE) continua sendo a melhor abordagem.

## 5. Curva de Capital (Equity Curve)

![Equity Curve V5](./portfolio_v5_advanced.png)
