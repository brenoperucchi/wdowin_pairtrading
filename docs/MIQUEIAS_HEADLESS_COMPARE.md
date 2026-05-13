# Miqueias Headless Compare

Objetivo: comparar o nosso motor WDOWIN com o repo de referencia do Miqueias sem depender do frontend e sem alterar a regra operacional dele.

## Modos

### 1. Live MT5 compartilhado

Uso principal para comparar decisao em tempo real.

- Nosso server roda em `8080`.
- Server do Miqueias roda em `8081`.
- Ambos apontam para o mesmo terminal MT5/mesmos simbolos.
- O comparador captura `/api/v2/regime` e `/api/di-regime` dos dois.

Esse modo responde:

- os dois motores recebem os mesmos dados de mercado?
- `z_wdo`, `z_di`, `rho`, `beta`, NWE e a decisao de cada estrategia batem?
- quando diverge, em qual campo a divergencia aparece primeiro?

### 2. DB adapter / replay deterministico

Uso secundario para comparar regra pura sem depender do MT5 ao vivo.

Ideia: monkeypatchar o `fetch_bars(symbol, count)` do Miqueias para ler do nosso `trades.db/bar_history`.

Vantagem:

- mesma base historica para os dois motores;
- reproducao de datas passadas;
- sem depender do terminal aberto.

Cuidado:

- o endpoint do Miqueias assume "agora" e usa caches por data/hora;
- para replay fiel, o adapter precisa simular relogio/barra corrente;
- portanto nao deve ser a primeira camada de comparacao live.

## Subir o Miqueias em 8081

Rodar com Windows Python que tenha `MetaTrader5` instalado:

```powershell
py -3.12 scripts\launch_miqueias_reference.py
```

Defaults já apontam para o repo do Miqueias e para a instalação portátil dedicada `E:\MetaTradersWSL\wdowin\pairtrading_miqueias\terminal64.exe`, que roda lado a lado com o terminal do server principal (`E:\MetaTradersWSL\wdowin\pairtrading\terminal64.exe`). Sobrescreva com `--mt5-path` ou `MIQUEIAS_MT5_PATH` apenas se quiser apontar para outra instalação.

O script nao edita o repo do Miqueias. Ele faz patch runtime de:

- `core.config.MT5_PATH`;
- `core.mt5_client.MT5_PATH`;
- `server.MT5_PATH`;
- `connect_mt5()` para aceitar `portable=True`, quando solicitado.

## Comparar JSON live

Com os dois servidores rodando:

```bash
python3 scripts/compare_miqueias_live.py \
  --ours http://127.0.0.1:8080 \
  --ref http://127.0.0.1:8081 \
  --out audits/live_compare \
  --tag live
```

Saidas:

```text
audits/live_compare/<timestamp>/ours_v2.json
audits/live_compare/<timestamp>/ours_di.json
audits/live_compare/<timestamp>/ours_health.json
audits/live_compare/<timestamp>/ref_v2.json
audits/live_compare/<timestamp>/ref_di.json
audits/live_compare/<timestamp>/ref_health.json
audits/live_compare/<timestamp>/summary.json
audits/live_compare/<timestamp>/audit.jsonl
```

`summary.json` contem o diff de negocio. `audit.jsonl` cria uma timeline externa aproximada:

- `DATA/FETCH_*`
- `INDICATORS/REGIME_SNAPSHOT`
- `ELIGIBILITY/GATE_STATE`
- `SIGNAL/<action>`
- `COMPARE/MISMATCH`

Como o Miqueias nao tem `execution_timeline`, a timeline dele e inferida do JSON publico. Isso e suficiente para diagnostico comparativo sem tocar na regra operacional.

## Pagina comparativa

Com o nosso server rodando em `8080` e o reference em `8081`, abra:

```text
http://127.0.0.1:8080/comparative
```

A pagina chama `/api/comparative`, grava um snapshot em `audits/live_compare` a cada refresh e mostra:

- sinais por estrategia (`CONS_BASE`, `WDO_NWE`, `DI_NWE`);
- `z_wdo`, `z_di`, `rho`, `eg_pvalue`;
- reasons do nosso risk gate;
- diff campo a campo entre nosso JSON e o reference.

O refresh padrao e 300 segundos. Para alterar:

```text
http://127.0.0.1:8080/comparative?refresh=60
```

Cada snapshot tambem fica persistido no mesmo formato do CLI:

```text
audits/live_compare/<timestamp>-comparative-page/
```

## Loop CLI

Para rodar sem navegador e coletar o resto do dia em barras M5:

```bash
python3 scripts/compare_miqueias_live.py \
  --loop \
  --align-m5 \
  --out audits/live_compare \
  --tag m5-watch
```

O loop cria uma pasta por amostra e acrescenta uma linha resumida em:

```text
audits/live_compare/index.jsonl
```

## Interpretacao

Diferenças esperadas:

- Nosso JSON tem `risk_gate`, `trades_today`, runtime config e execution timeline.
- Miqueias nao tem esses campos.

Diferenças criticas:

- `current_z_wdo`
- `current_z_di`
- `current_rho`
- `beta_delta_pct`
- `safe_to_trade`
- `strategy_actions.*`
- `eg_pvalue`

Quando uma diferenca aparece primeiro em indicador (`z`, `rho`, `beta`), o problema e dado/calculo. Quando indicadores batem e `strategy_actions` diverge, o problema e regra/gate/engine.

## Primeiro smoke real

Executado em 2026-05-11:

```text
ours: http://127.0.0.1:8080
ref:  http://127.0.0.1:8081
out:  audits/live_compare/20260511-134344-miqueias-ref-live
```

`/health` do reference confirmou:

```text
mt5_connected=true
terminal_path=E:\MetaTraders\MT5-Python\Ticks
configured_path=E:\MetaTraders\MT5-Python\Ticks\terminal64.exe
symbol_a=WIN$N
symbol_b=WDO$N
di_symbol=DI1$N
```

Resumo do diff inicial:

```text
strategy_actions: iguais (WAIT/WAIT/WAIT)
current_rho: igual (-0.29)
current_z_di: igual (0.195)
current_z_wdo: diferente pequeno (ours=0.023, ref=0.074)
eg_pvalue: diferente grande (ours=0.145895..., ref=1.0)
di_eg_pvalue: diferente (ours=0.1316, ref=0.1486)
```

Leitura: o pipeline headless funciona. A diferenca mais relevante no snapshot foi `eg_pvalue`, provavelmente porque o Miqueias ainda usa cache interno/default em vez do nosso `risk_gate` explicito. A decisao final naquele momento continuou igual: nenhuma estrategia entrou.
