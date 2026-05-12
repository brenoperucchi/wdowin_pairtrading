# Handoff para Claude — TASK-11 / Replay Miqueias / Runtime Config

Data: 2026-05-11

## Objetivo

Alinhar o replay do nosso sistema WDOWIN com o comportamento do repo de referência do Miqueias, separando claramente:

- perfil de reproducao do gestor;
- perfil permissivo/experimental para investigar dias mornos;
- comportamento live operacional.

## Estado do repo de referência

Clone local atualizado:

```text
/tmp/miqueias-wdowin
origin: https://github.com/miqueiasa1/wdowin_pairtrading.git
branch: main
HEAD: 7fce5bc0534d71de7c4c8d2e7498b8486338f898
commit: test: add python backtesting engine for Matador setup
status: clean
```

O `git pull --ff-only origin main` retornou `Already up to date`.

## Ajuste aplicado no nosso sistema

Arquivos alterados:

```text
config/runtime.json
core/runtime_config.py
```

Mudanca executada:

- `replay.beta_delta_max`: `25.0` -> `15.0`
- `live.beta_delta_max`: permanece `25.0`
- `core.runtime_config.DEFAULTS["replay"]["beta_delta_max"]`: `25.0` -> `15.0`

Motivo:

No repo do Miqueias existe `core/config.py:BETA_DELTA_MAX = 25.0`, mas o gate efetivo do endpoint usa `get_beta_status(beta_delta_pct).level < 2`. Pela tabela de `get_beta_status`, `level >= 2` comeca em `15%`. Logo, para reproduzir a decisao do gestor, o replay deve bloquear em `15%`, nao em `25%`.

Perfil de replay atual, confirmado via `GET /api/runtime-config`:

```json
{
  "eg_threshold": 0.1,
  "eg_bars": 2240,
  "eg_recalc": "daily",
  "rho_breakdown_level": 2,
  "beta_delta_max": 15.0,
  "eg_strategies": ["CONS_BASE", "WDO_NWE"]
}
```

O live foi mantido sem mudanca operacional para evitar alterar ordens reais/demo sem decisao explicita.

## Evidencia de replay apos ajuste

Comando:

```bash
python3 scripts/replay_execution_timeline.py \
  --date 2026-05-08 \
  --source trades.db \
  --out replays
```

Resultado:

```text
Replay summary — 2026-05-08
bars_total:           115
bars_processed:       108
bars_skipped_missing: 7
blockers:
  ELIGIBILITY:EG_NOT_COINTEGRATED 108
  ELIGIBILITY:OUT_OF_SESSION      35
  ELIGIBILITY:RHO_BREAKDOWN       30
  ELIGIBILITY:Z_ANOMALY           1
trades_opened:        1
trades_closed:        1
pnl_paper_brl:        -34.0
profile: EG<0.1 bars=2240 recalc=daily rho<L2 beta<15.0% eg_for=[CONS_BASE,WDO_NWE]
```

Trade gerado:

```text
id=1
strategy=DI_NWE
direction=SELL
timestamp_in=2026-05-08T10:15:00
timestamp_out=2026-05-08T10:35:00
exit_reason=BE_STOP
pnl_brl=-34.0
z_in=2.803
rho_in=-0.639502537405696
beta_in=38.1960257390816
```

DB regenerado:

```text
replays/execution_timeline_2026-05-08.db
```

Tambem rodei 2026-05-07 em diretorio temporario para nao sobrescrever:

```bash
python3 scripts/replay_execution_timeline.py \
  --date 2026-05-07 \
  --source trades.db \
  --out /tmp/wdowin_replay_2026-05-07_miqueias_profile
```

Resultado 05-07:

```text
trades_opened: 0
trades_closed: 0
pnl_paper_brl: 0.0
profile: EG<0.1 bars=2240 recalc=daily rho<L2 beta<15.0% eg_for=[CONS_BASE,WDO_NWE]
```

## Comparacao com perfil permissivo

Para entender o efeito de afrouxar rho, rodei antes um replay temporario com:

```text
rho_breakdown_level=3
beta_delta_max=25.0
```

Resultado 2026-05-08:

```text
DI_NWE SELL 09:45 -> STOP_LOSS 10:10
pnl_brl=-130.0
```

Conclusao: `rho_breakdown_level=3` destrava trades mais cedo em rho fraco, mas esse e um experimento permissivo, nao reproducao estrita do Miqueias.

## Estado live local capturado

Capturei o JSON do nosso live:

```bash
curl -sS http://127.0.0.1:8080/api/v2/regime \
  | python3 -m json.tool > /tmp/wdowin_ours_live_regime.json
```

Resumo do snapshot:

```text
current_z=-0.669
current_rho=-0.216
beta_delta_pct=-1.33
beta_unstable=False
last_update=13:28:21
risk_gate.allowed=False
risk_gate.reasons=[
  "BAR_NOT_CLOSED",
  "RHO_BREAKDOWN",
  "EG_NOT_COINTEGRATED"
]
eg_pvalue=0.14589524148002586
trade_engine.actions={
  CONS_BASE: WAIT,
  WDO_NWE: WAIT,
  DI_NWE: WAIT
}
```

Top-level keys atuais do nosso `/api/v2/regime`:

```text
beta_change_pct
beta_delta_pct
beta_drift_5d
beta_kalman
beta_ols
beta_ols_real
beta_ref_20d
beta_ref_5d
beta_unstable
current_rho
current_z
error
half_life
history
johansen_gate
last_update
last_update_iso
meta
nwe
regime_health
risk_gate
signal
strength
trade_engine
trades_today
```

## Diferencas relevantes contra Miqueias

O repo do Miqueias nao tem `runtime_config`. As decisoes estao no codigo.

Pontos equivalentes:

- WDO/CONS usa EG em WIN/WDO.
- DI endpoint calcula coint de DI para display/cache, mas `safe_to_trade` de DI nao usa EG.
- Nosso `eg_strategies=["CONS_BASE","WDO_NWE"]` reproduz esse bypass do DI.
- `rho_status.level < 2` equivale a bloquear `FRACA` e `QUEBRADA`.
- `get_beta_status(...).level < 2` equivale a bloquear `abs(beta_delta_pct) >= 15%`.

Pontos diferentes:

- Nosso sistema tem `risk_gate` centralizado e timeline; o Miqueias passa `beta_safe` para o `TradeEngine`.
- Nosso `/api/v2/regime` publica `risk_gate` e `trades_today`; o Miqueias nao.
- Nosso live ainda usa `beta_delta_max=25.0` no runtime profile; o replay agora usa `15.0`.
- Nosso sistema tem hot-reload por `/api/runtime-config`; o Miqueias nao.

## Sobre comparar JSON live com a ultima versao do Miqueias

Boa ideia. Para comparar de forma correta, precisamos dos dois servidores vivos contra o mesmo MT5/feed, em portas diferentes:

- nosso server: `http://127.0.0.1:8080`
- Miqueias reference: sugerido `http://127.0.0.1:8081`

Em WSL nao consegui/nao devo iniciar diretamente o server do Miqueias porque ele importa `MetaTrader5` no import inicial e foi escrito para rodar no Windows. A comparacao live real deve ser feita no ambiente Windows/MT5.

Comandos sugeridos quando o reference estiver rodando:

```bash
curl -sS http://127.0.0.1:8080/api/v2/regime | python3 -m json.tool > /tmp/ours_v2_live.json
curl -sS http://127.0.0.1:8081/api/v2/regime | python3 -m json.tool > /tmp/miqueias_v2_live.json

curl -sS http://127.0.0.1:8080/api/di-regime | python3 -m json.tool > /tmp/ours_di_live.json
curl -sS http://127.0.0.1:8081/api/di-regime | python3 -m json.tool > /tmp/miqueias_di_live.json
```

Depois comparar:

```bash
python3 - <<'PY'
import json

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

ours = load("/tmp/ours_v2_live.json")
ref = load("/tmp/miqueias_v2_live.json")

print("Only ours:", sorted(set(ours) - set(ref)))
print("Only ref:", sorted(set(ref) - set(ours)))

for key in [
    "current_z", "current_rho", "beta_delta_pct", "beta_unstable",
    "last_update", "meta", "regime_health", "trade_engine"
]:
    print("\\n==", key, "==")
    print("OURS:", ours.get(key))
    print("REF :", ref.get(key))
PY
```

## Pedido para Claude

1. Revisar se a inferencia `beta_delta_max=15.0` no replay esta correta para reproduzir o gate real do Miqueias, apesar de `core/config.py:BETA_DELTA_MAX=25.0`.
2. Validar se devemos tambem mudar o perfil `live.beta_delta_max` para `15.0`, ou manter `25.0` ate terminar a paridade de replay.
3. Sugerir a melhor forma de rodar o server do Miqueias em paralelo no Windows em outra porta para capturar `/api/v2/regime` e `/api/di-regime` live.
4. Revisar se o replay 2026-05-07 zerado e o replay 2026-05-08 com 1 trade estao coerentes com a referencia atual do Miqueias.

## Atualizacao — headless compare implementado

Ferramentas adicionadas:

```text
scripts/launch_miqueias_reference.py
scripts/compare_miqueias_live.py
docs/MIQUEIAS_HEADLESS_COMPARE.md
tests/test_compare_miqueias_live.py
```

Smoke real executado:

```text
reference repo Windows-readable:
C:\Users\brenoperucchi\devs\miqueias\miqueias-wdowin-reference

reference server:
http://127.0.0.1:8081

audit:
audits/live_compare/20260511-134344-miqueias-ref-live
```

Resultado:

```text
ref /health OK, conectado ao mesmo MT5:
E:\MetaTraders\MT5-Python\Ticks\terminal64.exe

strategy_actions:
ours = WAIT/WAIT/WAIT
ref  = WAIT/WAIT/WAIT

principais diferencas:
current_z_wdo: ours=0.023, ref=0.074
eg_pvalue: ours=0.145895..., ref=1.0
di_eg_pvalue: ours=0.1316, ref=0.1486
```

Conclusao: a comparacao headless esta operacional. O proximo passo tecnico e investigar por que o `eg_pvalue` do Miqueias veio `1.0` no snapshot live, enquanto o nosso `risk_gate` computou `0.145895...`.
