# SPEC — ML Direction Models + Z-Score Timing
## Technical Specification: Ensemble Hierárquico para WIN

**Versão**: 1.0  
**Data**: Abril 2026  
**Status**: Aprovado  

---

## 1. Objetivo

Evoluir o sistema de **"HMM filtra se opera ou não"** para **"modelos ML indicam a direção mais provável (BUY/SELL/FLAT)"**, usando o Z-Score como mecanismo de timing refinado para entrar na direção indicada.

### 1.1 Hipótese

> Se um modelo ML consegue prever a direção do WIN nos próximos 30-60 minutos com acurácia > 55%, e usarmos o Z-Score como gatilho de entrada apenas na direção prevista, o resultado será superior ao Setup Matador atual (Z-Score + HMM filtro binário).

### 1.2 Baseline (Setup Matador Atual)

- Z-Score ≤ -1.8 → BUY (qualquer direção, exceto BULL)
- Z-Score ≥ +1.8 → SELL (qualquer direção, exceto BULL)
- HMM apenas bloqueia regime BULL

---

## 2. Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│  Camada 1: Modelos Direcionais (M30, independentes)         │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐        │
│  │ HMM 3-est.  │  │ LSTM seq    │  │ XGBoost cls  │        │
│  │ regime→dir  │  │ 20bars→ret  │  │ features→cls │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘        │
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          ▼                                  │
│              Previsão: BUY / SELL / FLAT                    │
│              (cada modelo testado separado)                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│  Camada 2: Timing (M5 Z-Score)                              │
│                           ▼                                 │
│  ML=BUY  + Kalman z ≤ -threshold → ABRE COMPRA WIN         │
│  ML=SELL + OLS z ≥ +threshold    → ABRE VENDA WIN          │
│  ML=FLAT                         → NÃO OPERA               │
│  ML ≠ Z-Score direção            → NÃO OPERA               │
│                                                             │
│  threshold ∈ {1.5, 1.8, 2.0, 2.2} (grid search)            │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Dados

### 3.1 Fontes

| Ativo | Fonte | Timeframe | Período | Tamanho aprox. |
|---|---|---|---|---|
| WIN$N | MT5 B3 (CSV existente) | M1 → resample M30 | 2021.03 - 2026.03 | ~43 MB (M1) |
| WDO$N | MT5 B3 (CSV existente) | M1 → resample M30 | 2021.03 - 2026.03 | ~49 MB (M1) |
| VIX | MT5 Internacional (exportar) | M30 | 2021.03 - 2026.03 | ~5 MB |
| DXY | MT5 Internacional (exportar) | M30 | 2021.03 - 2026.03 | ~5 MB |

### 3.2 Preparação

1. Resample M1 → M30 (OHLCV) para WIN e WDO
2. Importar VIX e DXY M30 (exportação manual do segundo MT5)
3. Sincronizar timestamps (inner join por datetime)
4. Tratar gaps de horário (VIX/DXY operam fora do horário B3)

### 3.3 Schema do DataFrame Unificado

```python
columns = [
    # WIN M30
    "dt", "open", "high", "low", "close", "volume",
    # WDO M30
    "wdo_close",
    # VIX M30
    "vix_close", "vix_high", "vix_low",
    # DXY M30
    "dxy_close", "dxy_high", "dxy_low",
]
```

---

## 4. Feature Engineering

### 4.1 Features Locais (WIN)

| Feature | Cálculo | Categoria |
|---|---|---|
| `log_ret` | log(close / close[-1]) | Retorno |
| `log_ret_2h` | log(close / close[-4]) | Retorno longo |
| `atr_14` | ATR(14) | Volatilidade |
| `norm_vol` | ATR / close | Volatilidade |
| `rsi_14` | RSI(14) | Momentum |
| `macd_signal` | MACD(12,26,9) signal | Momentum |
| `adx_14` | ADX(14) | Tendência |
| `trend_pos` | (close - trail_level) / ATR | Posição no trend |
| `wma_cross` | WMA(20) - WMA(40) normalizado | Direção |
| `hour` | Hora do dia (0-23) | Temporal |
| `dow` | Dia da semana (0-4) | Temporal |

### 4.2 Features Macro

| Feature | Cálculo | Categoria |
|---|---|---|
| `vix_level` | VIX close | Medo global |
| `vix_ret` | log(vix / vix[-1]) | Variação do medo |
| `vix_zscore` | Z-Score rolling(20) do VIX | Regime de medo |
| `dxy_ret` | log(dxy / dxy[-1]) | Força do dólar |
| `dxy_trend` | DXY WMA(10) - WMA(20) | Tendência dólar |
| `win_dxy_corr` | Correlação rolling(20) WIN×DXY | Relação macro |

### 4.3 Features do Spread (para backtest combinado)

| Feature | Cálculo |
|---|---|
| `spread` | WIN - β × WDO |
| `zscore_ols` | Z-Score OLS rolling(40) |
| `zscore_kalman` | Z-Score Kalman rolling(40) |
| `rho` | Correlação rolling(40) WIN×WDO |

---

## 5. Modelos

### 5.1 HMM Direcional

**Evolução do HMM filtro atual** → agora classifica direção em vez de só bloquear.

- **Tipo**: GaussianHMM, 3 componentes, covariance=full
- **Features**: trend_pos, log_ret, norm_vol, adx, vix_zscore, dxy_ret
- **Target**: Não supervisionado — a direção é inferida do retorno médio de cada estado:
  - Estado com mean(log_ret) > +threshold → BUY
  - Estado com mean(log_ret) < -threshold → SELL
  - Estado intermediário → FLAT
- **Prior**: transmat_prior = I + eye×5 (inércia)

### 5.2 LSTM Direcional

**Rede recorrente** que processa sequências temporais.

- **Arquitetura**: LSTM(64) → Dropout(0.3) → Dense(32) → Dense(3, softmax)
- **Input**: Sequência de 20 barras M30, com todas as features (locais + macro)
- **Target**: Classe {BUY=0, FLAT=1, SELL=2}
  - BUY: retorno acumulado das próximas 4 barras > +100 pts
  - SELL: retorno acumulado das próximas 4 barras < -100 pts
  - FLAT: entre -100 e +100 pts
- **Loss**: Categorical cross-entropy com class weights (FLAT é mais frequente)
- **Framework**: PyTorch (ou Keras/TF se preferir)

### 5.3 XGBoost Direcional

**Gradient boosting** em features tabulares.

- **Tipo**: XGBClassifier, 3 classes
- **Features**: Todas as 17+ features (locais + macro), sem sequência
- **Target**: Mesma definição do LSTM (BUY/FLAT/SELL por retorno futuro)
- **Hiperparâmetros base**: max_depth=5, n_estimators=300, learning_rate=0.05
- **Tuning**: Optuna ou grid search básico dentro de cada janela WFA

---

## 6. Metodologia de Validação e Otimização (70/30 Split)

Em substituição ao tradicional Walk-Forward Analysis (WFA), a validação adota uma busca exaustiva de hiperparâmetros (Grid Search) otimizada para o **Calmar Ratio**, usando um sólido **split 70% In-Sample / 30% Out-of-Sample**.

### 6.1 Configuração do Split

```
Dataset: WIN M30 (Feature space) + WIN M5 (Execução Z-Score)
Train (In-Sample):     70% dos dados iniciais
Test (Out-of-Sample):  30% dos dados finais (cronológicos)
```
Critério principal: O modelo é treinado nos 70% e todas as métricas publicadas refletem estritamente a performance obtida no período de teste (30%).

### 6.2 Otimização Paralela e Checkpoints (Anti-OOM)

Para evitar exaustão de memória (*ArrayMemoryError*) durante simulações com múltiplos nós (ex: 30 `workers`), o pipeline transporta a computação do backtest e do dataset M5 da *Main thread* para a área restrita do *Worker*. Assim, evita-se a transferência de grandes de tensores via IPC.

---

## 7. Espaço Hierárquico do Grid Search (1800 configs)

O espaço de otimização foca estritamente nos hiperparâmetros dos Modelos de ML. O gatilho Z-Score de execução M5 fica **fixo** para garantir máxima densidade de amostragem perante o mercado limitando viés estatístico.

- **Fixo**: Z-Score `1.8`
- **Fixo**: Target_Pts `100`

### 7.1 HMM (300 combinações)
*(Fixo em n_components=3)*
- `ret_threshold`: [0.0001, 0.0005, 0.001, 0.002, 0.0025, 0.003, 0.0035, 0.004, 0.0045, 0.005] (10 steps)
- `covariance_type`: ["full", "diag", "tied"] (3 cases)
- `n_iter`: [50, 100, 150, 200, 250, 300, 350, 400, 450, 500] (10 steps)

### 7.2 LSTM (500 combinações)
- `seq_len`: [5, 10, 15, 20, 25, 30, 35, 40, 45, 50] (10 steps)
- `hidden_dim`: [32, 64, 96, 128, 160, 192, 224, 256, 288, 320] (10 steps)
- `dropout`: [0.1, 0.3, 0.5, 0.7, 0.9] (5 steps)

### 7.3 XGBoost (1000 combinações)
- `max_depth`: [3, 5, 7, 9, 11, 13, 15, 17, 19, 21] (10 steps)
- `n_estimators`: [100, 150, 200, 250, 300, 350, 400, 450, 500, 550] (10 steps)
- `learning_rate`: [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50] (10 steps)

Total: **1800 modelos simulados**. Para cada iteração no grid, é executado um backtest combinado (Modelo Direcional M30 + Entrada/Saída Z-Score M5) considerando os parâmetros do *Setup Matador*.

### 7.4 Parâmetros de Trade OoS (fixos do Setup Matador)

| Param | BUY | SELL |
|---|---|---|
| SL | 350 pts | 300 pts |
| TP | 500 pts | 1400 pts |
| BE Act | 400 pts | 800 pts |
| BE Lock | 50 pts | 200 pts |
| Sizing | 2 WIN | 2 WIN |
| Session | 10:00-16:00 | 10:00-16:00 |

---

## 8. Métricas de Comparação

Para cada combinação `(modelo, threshold)`:

| Métrica | Descrição |
|---|---|
| **Accuracy** | % acertos direcionais do modelo (standalone) |
| **PnL OOS** | Lucro acumulado out-of-sample (R$) |
| **Win Rate** | % trades TARGET vs STOP |
| **Profit Factor** | Soma(ganhos) / Soma(perdas) |
| **Max Drawdown** | Maior queda do equity |
| **Trades/mês** | Frequência de operação |
| **Alpha** | PnL(modelo) - PnL(baseline) |

**Baseline**: Setup Matador atual (Z-Score ±1.8, HMM filtro binário, sem ML direcional)

---

## 9. Estrutura de Arquivos

```
research/
├── models/
│   ├── features.py            # Feature engineering compartilhado
│   ├── hmm_direction.py       # HMM 3-estados → BUY/SELL/FLAT
│   ├── lstm_direction.py      # LSTM sequencial → BUY/SELL/FLAT
│   └── xgb_direction.py       # XGBoost tabular → BUY/SELL/FLAT
├── data_prep.py               # Resample M1→M30, merge VIX/DXY
├── wfa_runner.py              # Walk-Forward orchestrator
├── backtest_ml_zscore.py      # Backtest combinado ML+ZScore
└── compare_models.py          # Relatório comparativo + plots

data/
├── historical/
│   ├── WIN$N_M1_*.csv         # (já existe)
│   ├── WDO$N_M1_*.csv         # (já existe)
│   ├── VIX_M30_*.csv          # (exportar do MT5 internacional)
│   └── DXY_M30_*.csv          # (exportar do MT5 internacional)
└── processed/
    ├── dataset_m30.parquet     # DataFrame unificado
    └── wfa_results/            # Resultados por janela
        ├── hmm/
        ├── lstm/
        └── xgb/
```

---

## 10. Dependências Adicionais

```
torch>=2.0          # LSTM
xgboost>=2.0        # XGBoost
optuna>=3.0         # Hyperparameter tuning (opcional)
pyarrow>=15.0       # Parquet I/O
```
