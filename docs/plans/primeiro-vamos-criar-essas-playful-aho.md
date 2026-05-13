# Plano: Fidelidade MT5 no Replay + Parametrização do Engine + Sweep de Otimização

## Princípio inegociável

**Replay/backtest e live rodam o MESMO código de engine.** Toda regra de negócio (signals, gates,
SL/TP/BE, force-close, custos) vive num único lugar (`core/trade_engine.py` + `core/signals.py` +
`core/risk_gate.py`). Quando essas regras melhoram, replay/sweep enxergam de imediato — **sem PR
paralelo, sem código duplicado**.

Como isso é garantido na prática:
- **Live**: chama `TradeEngine.evaluate(..., simulation_profile=None, engine_params=<live>)`.
  - `simulation_profile=None` → **nenhuma simulação de mercado**; preço e fills vêm do MT5 real
    (quando `LIVE_ORDERS=1`) ou do `win_price` polado (paper). O live NÃO inventa slippage —
    ele *recebe* a condição real do mercado.
  - `engine_params` → params operacionais do perfil `live` no `runtime_config.json`.
- **Replay/sweep**: chama o mesmo método com `simulation_profile={...}` (que **modela** o que o
  MT5 cobraria — slippage, intra-bar, custos) e `engine_params=<replay ou trial>`.

`SimulationProfile` é **input do engine**, não um caminho de código alternativo. `engine_params`
idem. Live e replay convergem para o mesmo `evaluate()`.

> Observação do usuário (registrada): "No modo live eu **não quero simular** condições — eu quero
> *saber* a condição. Simulação fica restrita a replay/backtest." Esse plano respeita isso.

---

## Context

Gaps medidos hoje (vide exploração):

1. **Fidelidade MT5 no paper/replay** — `_check_exits` em `core/trade_engine.py:557` calcula
   `pts_favor` contra `win_price` (close polado) e fecha nesse preço, não no nível do SL/TP. Wicks
   intra-bar invisíveis (`bar_history` é close-only). `WIN_SLIPPAGE_PTS=5` e
   `B3_COST_PER_CONTRACT_RT=1.00` em `core/config.py:110-111` existem mas o engine não usa.
2. **Engine acoplado a globais** — `BUY_SL/TP/BE_*`, `Z_ENTRY`, `WINDOW`, `ENTRY_*`, `FORCE_CLOSE_*`
   são importados como constante em `core/trade_engine.py:19-21` e usados como global.
   Qualquer otimização paralela com ThreadPool contamina trials porque eles compartilham processo +
   módulos. Isso é o trabalho de **TASK-16** ([[project_deployment_systemd]] já listou).
3. **Sem OHLC** — `bar_history` (`core/bar_history_db.py:32`) só tem `*_price` (close). Sem H/L não
   há detecção intra-bar.
4. **`fetch_bars()` é close-only** — `core/mt5_client.py:fetch_bars()` devolve `(closes, times)`.
   Para popular OHLC precisamos de uma função paralela que devolva o array OHLC completo.

---

## Fase A — Fidelidade MT5 no engine (replay/backtest only, live no-op)

### A.1 — `fetch_rates()` em `core/mt5_client.py`

- Manter `fetch_bars(symbol, count) → (closes, times)` intacto (caller existente).
- Adicionar `fetch_rates(symbol, count) → np.ndarray` (ou tuple de arrays) devolvendo OHLC + volume
  + spread quando disponível. Wrapper fino sobre `mt5.copy_rates_from_pos`.
- Adicionar `fetch_rates_range(symbol, dt_start, dt_end) → np.ndarray` para backfill.
- Testes: mock do `mt5` module, assert shape/keys.

### A.2 — Schema OHLC em `bar_history` (migração real, idempotente)

**Arquivo:** `core/bar_history_db.py`

- `BAR_COLUMNS` (linha 32): adicionar `win_open, win_high, win_low, wdo_open, wdo_high, wdo_low,
  di_open, di_high, di_low`.
- `_SQLITE_SCHEMA` e `_POSTGRES_SCHEMA`: declarar colunas novas (REAL / DOUBLE PRECISION nullable).
- **Migração explícita** (não confiar em `CREATE TABLE IF NOT EXISTS`):
  - SQLite: `PRAGMA table_info(bar_history)`; para cada coluna nova ausente, `ALTER TABLE ADD COLUMN`.
  - Postgres: `INFORMATION_SCHEMA.columns`; para cada ausente, `ALTER TABLE ADD COLUMN IF NOT EXISTS`.
  - Função utilitária `_ensure_ohlc_columns(conn, backend)` executada no boot do módulo. Idempotente.
- Cell-level checksum no backfill (padrão [[feedback_migration_cell_checksum]]).

### A.3 — Captura OHLC no live

**Arquivo:** `server.py` (lines ~1073-1212 em `regime_v2` / `_save_bar_history` caller)

- Substituir `fetch_bars()` por `fetch_rates()` para `WIN$N`, `WDO$N`, `DI1$N`.
- Ao chamar `save_bar_history()`, preencher os 9 campos novos.
- Manter cálculos atuais (close-based) iguais — OHLC é só captura adicional, não muda lógica.
- AC: 1 barra fechada após deploy tem `win_open/high/low` no banco.

### A.4 — Backfill histórico

**Arquivo novo:** `scripts/backfill_bar_history_ohlc.py`
- CLI: `--start YYYY-MM-DD --end YYYY-MM-DD --symbols WIN,WDO,DI [--commit]`.
- Para cada barra existente sem OHLC, `fetch_rates_range` no MT5 → UPSERT só nos campos novos.
- Idempotente (cell checksum). Roda Windows-only (`py.exe -3.12`).

### A.5 — `SimulationProfile` dentro de cada perfil

**Arquivo:** `core/runtime_config.py`

Codex tem razão: top-level `simulation` quebra o schema atual (live/replay com campos estritos).
**Decisão:** colocar `simulation` **dentro** de cada perfil:

```json
{
  "live":   { ...campos atuais..., "simulation": { "enabled": false, ... } },
  "replay": { ...campos atuais..., "simulation": { "enabled": true, "entry_slippage_pts": 5, ... } }
}
```

Campos:
- `enabled` (bool, default `false` em ambos os perfis — preserva paridade até habilitar explicit).
- `entry_slippage_pts` (float, default 5.0)
- `exit_slippage_pts` (float, default 5.0)
- `cost_per_contract_rt_brl` (float, default 1.00)
- `intra_bar_sl_tp` (bool, default true; fallback graceful pra close-only se OHLC ausente)
- `exit_at_sl_tp_level` (bool, default true)
- `conflict_rule` (enum: `sl_first` | `tp_first` | `worst`; default `sl_first` — conservador)

Validators: bounds defensivos. `_backfill_missing_fields` adiciona `simulation` desativado em
perfis legados (backward compat).

### A.6 — Aplicar profile no engine

**Arquivo:** `core/trade_engine.py`

- `evaluate()`: aceitar `simulation_profile=None` opcional, propagar para `_open_trade` e
  `_check_exits`. Quando `None` ou `enabled=False` → no-op (paridade bit-exata).

- **`_open_trade` (linha 405)** — quando profile ativo e `LIVE_ORDERS=0`:
  - BUY: `entry_price = win_price + entry_slippage_pts`
  - SELL: `entry_price = win_price - entry_slippage_pts`
  - Log no `EXECUTION_FILLED.payload_json` o slippage aplicado.

- **`_check_exits` (linha 557)** — aceitar `win_high=None, win_low=None`:
  - Se `intra_bar_sl_tp` ativo **e** H/L presentes:
    - Computar `pts_favor_high` (BUY: high-entry; SELL: entry-low) e `pts_favor_low` (espelho).
    - Detectar trigger TP (lado favorável atinge TP) e SL (lado desfavorável atinge SL).
    - **TP+SL no mesmo candle**: aplicar `conflict_rule`. Default `sl_first` → registra `STOP_LOSS`,
      preço de saída no nível do SL. Conservador, evita inflar performance.
  - Se `exit_at_sl_tp_level` ativo e trigger por TP/SL: `exit_price = entry_price ± nível`
    (não usa `win_price`). BE/`FORCE_CLOSE` continuam em `win_price` (live também é assim).
  - Aplicar `exit_slippage_pts` no preço final (BUY exit toma bid → subtrair slippage do PnL;
    SELL exit toma ask → idem espelho).
  - Sem H/L disponível: cai pra lógica close-only atual + log de degraded fidelity.

- **`_close_trade` (linha 676)**: após `pnl = pts_favor * WIN_CONTRACTS * WIN_PV`, descontar
  `cost_per_contract_rt_brl * WIN_CONTRACTS` (round-trip já no aberto do trade). Persistir `cost_brl`
  em `matador_ops` (coluna nova) ou no `payload_json` do timeline.

### A.7 — Replay propaga OHLC + profile

**Arquivo:** `scripts/replay_execution_timeline.py`

- `resolve_replay_profile()` (linha 138): ler `simulation` de `replay` profile, permitir overrides
  CLI (`--sim-enabled`, `--sim-entry-slip`, `--sim-exit-slip`, `--sim-cost-rt`,
  `--sim-intra-bar/--no-sim-intra-bar`, `--sim-exit-at-level/--no-sim-exit-at-level`,
  `--sim-conflict-rule sl_first|tp_first|worst`).
- `run_replay()` (linha 533): passar `win_high`, `win_low` (do `bar_history`) e `simulation_profile`
  ao `engine.evaluate()`. META event do timeline DB carrega o profile usado.

### A.8 — Testes de fidelidade

**Arquivo novo:** `tests/test_replay_simulation_fidelity.py`

1. **Slippage entrada/saída**: BUY com `entry_slippage_pts=5, exit_slippage_pts=5` → entrada em
   `close+5`, saída em `nivel-5`.
2. **Exit at SL level**: BUY com SL=60, bar com low ≤ entry-60 e close > entry-60 → exit em
   `entry-60`, não no close.
3. **Intra-bar TP a partir de wick**: BUY com TP=80, bar.high ≥ entry+80, close < entry+80 → exit
   em `entry+80` no mesmo bar.
4. **TP+SL no mesmo candle (conflict rule)**: bar onde high e low cruzam ambos →
   `conflict_rule=sl_first` → STOP_LOSS. Caso simétrico para `tp_first`.
5. **Custo round-trip**: `pnl_brl` final desconta `cost_per_contract_rt_brl * WIN_CONTRACTS`.
6. **No-op com `enabled=False`**: bit-exato à baseline (regressão zero).
7. **OHLC ausente + `intra_bar_sl_tp=True`**: graceful degradation com log warn.

Reusar fixtures de `tests/test_replay_execution_timeline.py`. Estender `_seed_bar` para aceitar
`win_high`/`win_low` opcionais (default `None`).

---

## Fase A' — Parametrização segura do engine (pré-requisito do sweep)

**Por que essa fase existe:** o sweep não pode mutar globais (`core/config.py` constants
importadas em `core/trade_engine.py:19-21`). Solução: o engine recebe params como **input**, idem
ao `simulation_profile`. Isso é também o objetivo de **TASK-16** ([[#]] backlog) — então essa fase
e TASK-16 são a mesma coisa, alinhadas.

### A'.1 — `EngineParams` (ou consolidação com `RuntimeProfile`)

**Arquivo:** `core/runtime_config.py`

Adicionar a cada perfil os campos que hoje vivem em `core/config.py`:
- `window`, `z_entry`, `z_attention`
- `buy_sl`, `buy_tp`, `buy_be_act`, `buy_be_lock`
- `sell_sl`, `sell_tp`, `sell_be_act`, `sell_be_lock`
- `entry_start_h/m`, `entry_end_h/m`, `force_close_h/m`

Validators idem TASK-16 (bounds defensivos).

### A'.2 — `TradeEngine` consome params

**Arquivo:** `core/trade_engine.py`

- Remover imports diretos de `core/config.py` para esses params; passar via `evaluate(params=...)`.
- `_open_trade` lê `params.buy_sl/tp/be_*` no momento da abertura e **grava no trade dict** —
  mudanças mid-position não afetam slots já abertos (CAR4 de TASK-16).
- `core/config.py` continua exportando os mesmos valores como **default** (para CLI tools e
  scripts legados), mas o engine prefere `params` se passado.

### A'.3 — `signals.py` consome `window` / `z_entry`

**Arquivo:** `core/signals.py`

- `calc_zscore`, `get_signal`: aceitar `window` e `z_entry` como argumento. Default = constante atual.
- Replay/sweep passam `params.window/z_entry`. Live passa do `live` profile.

### A'.4 — Testes

- `tests/test_runtime_config_engine_params.py`: schema aceita config legado (backfill), valida bounds.
- Estender `tests/test_replay_execution_timeline.py`: rodar com profile customizado, asserir que
  trade.buy_sl é o do profile, não o do `core/config.py`.

---

## Fase B — Sweep de Otimização (somente após A + A')

### B.1 — Runner

**Arquivo novo:** `scripts/optimize_strategy_sweep.py`

- CLI: `--dates`, `--strategies`, `--grid grids/v1.yaml`, `--workers N`, `--out reports/sweep_<ts>/`.
- Após A' o engine não tem mais estado global mutável → **ThreadPoolExecutor seguro**.
  - Cada worker chama `run_replay()` in-process com um `engine_params` e `simulation_profile`
    dict próprio do trial. Sem patch em `core.config`.
- Fallback alternativo (cinto + suspensório, opcional): flag `--isolation subprocess` que executa
  `run_replay` como subprocess (`py.exe -3.12 scripts/replay_execution_timeline.py ...`) com
  os params via CLI. Mais lento mas blindado contra qualquer global que sobreviva.
- Cada trial escreve em SQLite próprio dentro de `reports/sweep_<ts>/trial_<hash>/`.

### B.2 — Grid v1

`grids/v1.yaml` — **WINDOW removido** porque os z-scores em `bar_history` já estão materializados:
variar `window` no sweep sem recomputar Kalman/OLS é placebo.

```yaml
z_entry: [1.5, 1.8, 2.0, 2.2]
buy_sl: [40, 60, 80]
buy_tp: [60, 100, 140]
buy_be_act: [40, 60]
eg_threshold: [0.10, 0.15, 0.25]
# 4 × 3 × 3 × 2 × 3 = 216 combos
```

`WINDOW` fica para v2 (exige recomputar indicadores por trial — ver §Robustez Futura).

### B.3 — Reporter

**Outputs em `reports/sweep_<ts>/`:**
- `manifest.json`, `trials.csv` (params + métricas: pnl_brl, n_trades, win_rate, max_drawdown,
  sharpe_aprox, avg_pts_favor, blockers_top3)
- `top_k_by_pnl.md`, `top_k_by_sharpe.md`, `top_k_by_dd_adjusted.md`
- `aggregate_by_param.csv` (sensibilidade univariada — média de PnL por valor de cada param)
- `report.md` (sumário executivo: best overall, sensibilidades, anomalias).

### B.4 — Testes

`tests/test_optimize_sweep.py`:
- 1 trial single-thread = `run_replay()` direto (regressão zero).
- Grid 2×2×2 com 2 workers → 8 trials no manifest, sem race conditions.
- Reporter agrega corretamente (mock 3 trials com PnL conhecido → top_k ordena right).
- **Cross-trial leakage test**: rodar 2 trials com `buy_sl` diferentes em paralelo, asserir que cada
  trial DB tem o `buy_sl` correto persistido em `matador_ops` (prova que A'.2 funciona).

---

## Robustez Futura (notes para a backlog task)

Capturar como notes na task do MCP backlog:

- **Walk-forward / OOS**: split temporal (train D1..Dn → validate Dn+1..Dm). Holdout 20% das datas
  nunca tocado no sweep.
- **Bayesian (optuna/skopt)**: substituir grid quando espaço > 10k combos.
- **K-fold de regimes**: agrupar dias por regime HMM (BULL/BEAR/CHOP) e validar cross-regime.
- **Slippage probabilístico**: modelar slippage com distribuição (uniforme 3-7 ou função de
  `spread_wdo`) — exige captura de bid/ask no live (task separada).
- **WINDOW no sweep**: exige recomputar Kalman/OLS por trial; criar pipeline que parte de barras
  raw (não dos z's persistidos). Custo: 5-10× mais lento por trial.
- **Multi-objective (Pareto)**: otimizar PnL + Sharpe + DD simultaneamente, expor fronteira.
- **Tick-level fidelity**: validar que H/L M5 é proxy suficiente do tick path; usar `copy_ticks_from`
  do MT5.
- **Live: condição real de mercado** — captura de bid/ask + spread no `bar_history` para que o
  live tenha *medição* (não simulação) das condições. Task separada.

---

## Verificação (end-to-end)

### Fase A
1. `pytest tests/test_mt5_client.py` (mock) — `fetch_rates` devolve OHLC.
2. Migração: rodar `_ensure_ohlc_columns` num clone do `trades.db`; `PRAGMA table_info` mostra
   colunas novas. Idem em Postgres clone (`information_schema.columns`).
3. **Live OHLC capture**: deploy A.1-A.3 em DEV; 1 barra fechada via
   `journalctl --user -u pairtrading-server -f` deve preencher H/L.
4. Backfill: `scripts/backfill_bar_history_ohlc.py --start 2026-04-01 --end 2026-05-09 --commit`
   (Windows); count antes/depois.
5. **No-op regressão**: `run_replay()` para um dia com `simulation.enabled=False` antes e depois
   das mudanças A.6 — saída idêntica (mesmo summary, mesmo `matador_ops`).
6. **Fidelity ativa**: mesmo dia com `enabled=True` — PnL líquido menor (slippage + custos);
   auditar 1-2 trades manualmente vs MT5 expectations.
7. `pytest tests/test_replay_simulation_fidelity.py -v`.

### Fase A'
1. `pytest tests/test_runtime_config_engine_params.py -v` (schema, validators, backfill).
2. `pytest tests/test_replay_execution_timeline.py -v` (regressão; profile customizado lê do
   replay profile, não do `core/config.py`).
3. **Hot-reload smoke**: POST `/api/runtime-config` com `buy_sl` diferente; próxima barra fechada
   reflete sem restart (CAR3 de TASK-16).
4. **Position immutability**: abrir trade A → POST muda `buy_sl` → fechar; conferir que A foi
   fechado com o SL original (CAR4 de TASK-16).

### Fase B
1. `pytest tests/test_optimize_sweep.py -v`.
2. **Cross-trial leakage**: o teste da B.4 deve passar com 2+ workers.
3. Sweep dry-run: grid mini (2×2 = 4 combos × 1 dia × 1 estratégia) com `--workers 2`. Conferir
   `reports/sweep_*/trials.csv` tem 4 linhas, manifest íntegro.
4. Sweep real: grid v1 × 5 dias × 3 estratégias = 216 × 5 × 3 = 3240 trials. Inspecionar `report.md`
   — top-3 fazem sentido qualitativo (não tudo no canto do espaço).
5. **Reality check**: pegar top-1, configurar via `/api/runtime-config`, rodar 1 dia em paper live,
   comparar com replay do mesmo dia → divergência < 5%.

---

## Arquivos críticos

**Modificar:**
- `core/mt5_client.py` (adicionar `fetch_rates`, `fetch_rates_range`)
- `core/bar_history_db.py` (schema + `_ensure_ohlc_columns` migração)
- `core/trade_engine.py` (profile + params em `_open_trade`/`_check_exits`/`_close_trade`)
- `core/signals.py` (window/z_entry como argumento)
- `core/runtime_config.py` (SIMULATION_FIELDS dentro de live/replay + EngineParams)
- `scripts/replay_execution_timeline.py` (propagar OHLC + profile + params)
- `server.py` (usar `fetch_rates` em vez de `fetch_bars` para salvar OHLC)
- `core/config.py` (manter como defaults, sem mais ser fonte única)

**Criar:**
- `scripts/backfill_bar_history_ohlc.py`
- `scripts/optimize_strategy_sweep.py`
- `tests/test_replay_simulation_fidelity.py`
- `tests/test_runtime_config_engine_params.py`
- `tests/test_optimize_sweep.py`
- `grids/v1.yaml`

**Mexer minimamente em testes existentes:**
- `tests/test_replay_execution_timeline.py` — `_seed_bar` aceita `win_high`/`win_low` opcionais.
- `tests/test_mt5_client.py` — cobrir `fetch_rates`.

---

## Slices (para tracking via MCP backlog — criar ao sair do plan mode)

### Fase A — Fidelidade MT5
1. `A.1` — `fetch_rates()` + testes (mock).
2. `A.2` — Schema OHLC + migração idempotente SQLite/PG + testes.
3. `A.3` — Live captura OHLC (`server.py`).
4. `A.4` — `scripts/backfill_bar_history_ohlc.py`.
5. `A.5` — `simulation` block dentro de cada perfil em `runtime_config` + validators.
6. `A.6` — `TradeEngine` aplica profile (slippage / intra-bar / exit-at-level / custos / conflict).
7. `A.7` — Replay propaga OHLC + profile + CLI flags.
8. `A.8` — `tests/test_replay_simulation_fidelity.py`.

### Fase A' — Parametrização (substitui/absorve TASK-16)
9. `A'.1` — `EngineParams` em `runtime_config` (campos operacionais).
10. `A'.2` — `TradeEngine` consome params (sem global).
11. `A'.3` — `signals.py` aceita window/z_entry como argumento.
12. `A'.4` — Tests + hot-reload smoke + position immutability.

### Fase B — Sweep (só depois de A + A' verdes)
13. `B.1` — `optimize_strategy_sweep.py` runner (ThreadPool + opcional subprocess).
14. `B.2` — `grids/v1.yaml`.
15. `B.3` — Reporter.
16. `B.4` — Tests (inclui cross-trial leakage).
17. `B.5` — Reality check em paper live.

**Janelas de execução:**
- A.1, A.2, A.4, A.5, A.8, A'.1, A'.4, B.1-B.4 — seguros durante mercado.
- A.3, A.6, A.7, A'.2, A'.3, B.5 — fora de mercado (mexem no engine usado pelo `trade_eval_loop`).
