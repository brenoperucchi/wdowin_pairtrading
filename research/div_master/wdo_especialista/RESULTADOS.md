# Busca de Setup no WDO (Divergência + Walls)

**Período completo avaliado:** `2026-01-02` a `2026-11-11` (`211` pregões alinhados Profit M5 + MT5 M1)  
**Execução:** simulação tick-a-tick M1 (`bt.sim`), 1 contrato (`R$ 10/pt`), custo `0,5 pt/trade`, slippage de stop `1 tick` (`0,5 pt`), EOD `17:25`, gestão `UM_POR_VEZ` (e comparação com `LIVRE`).  
**Subperíodos de estabilidade:** `H1` (`jan–abr`), `H2` (`mai–jul`), `OOS` (`ago–nov`, `IS = jan–jul`).  
**Observação metodológica:** como a seleção das regras e parâmetros foi feita sobre a base completa até `11/11/2026`, `ago–nov` aqui mede estabilidade temporal e **não** é OOS virgem; a confiança vem do platô de vizinhos, placebo sem divergência, inversão e estresse pesado de execução.

---

## 0. Busca Exclusiva `v3.2` + `>= 100` Trades (Pedido Atual)

### Correção de bug nos filtros horários das fases anteriores
Nos scripts iniciais (`busca_phase1.py` / `busca_phase2.py`), o campo `tm` já estava armazenado em **minutos** (`540..1020`), mas o filtro calculava `hh = tm // 100` em vez de `tm // 60`. Corrigido para `hh = tm // 60` (`540..720` = `09h–12h`, etc.) em `busca_v32_100.py`, revelando os setups `v3.2` com `>= 100` trades.

### Campeão `v3.2` + `>= 100` trades: **`V1a`** (`M.V32` padrão: `open_module=True`, `184` ops, `Ret/DD 7,62`, `11/11` meses)

#### Regra exata (`V1a`)
- **Motor:** `engine_v32` com `M.V32` (`f1="flow"`, `reset=False`, `rep=True`, `used=False`, **`open_module=True`** + `abertura=M.V22_ABERTURA`, isto é, inclui `zz08`, `lr` e `seed` na abertura).
- **Parâmetros e níveis:** `PARAMS["WDO"]` inalterado (`zone = 3,5 pts`, `pierce_max = 6,0 pts`, `elig = "common"`), alimentado por **`Wall`** (`lv="wall"`). *(Com `Wall + MidWall`, `lv="all"`, também mantém `179` ops, **`Ret/DD 7,49`**, `11/11` meses.)*
- **Modo de entrada (`CONF`):** na abertura da barra M5 `conf + 1`, dentro de `09:00–17:00` (`540–1020` min), excluindo a faixa **`11:00–11:59` (`hh != 11`)**.
- **Âncora na Wall:** distância do pivô `px2` até a `Wall` mais próxima `<= 3,5 pts` (`d_wall <= 3,5`).
- **Filtro de contexto:** `ext30 > 0,0` (fechamento da barra de sinal além do centro causal da NWE30 a favor de reversão à média, sem corte decimal arbitrário).
- **Saída (duas variantes igualmente sólidas):**
  - **`V1a (ProxWall)` — Principal:** `SL = 14,0 pts`, `TP = min(max(nw_d, 4,0), 22,0)` onde `nw_d = dir * (next_wall - ep) - 0,5` (aborta se `nw_d < 2,5`), `tmax = 24` barras (`2h`), sem BE, `UM_POR_VEZ`.
  - **`V1a (TP fixo 12)` — Simplificada:** `SL = 14,0 pts`, `TP = 12,0 pts`, `tmax = 24` barras, sem depender de alvo por Wall (`190` ops, **`Ret/DD 6,87`**, `11/11` meses).

#### Métricas no período completo (`02/01–11/11/2026`, 1 contrato)
- **`V1a (ProxWall)`:** `184` ops (`95` COMPRA / `89` VENDA), `WR 66,3%` (`122` gains; `36` stops cheios; `11` EOD), `PF 1,72`, **Net `+R$ 4.498`**, **DD `R$ 590`**, **`Ret/DD 7,62`**, máx. `5` losses seguidos, pior dia `-R$ 300`.
- **Meses positivos (`11/11`):** jan `+155,0 (69,6%)`, fev `+1.070,0 (78,6%)`, mar `+327,5 (60,9%)`, abr `+80,0 (52,9%)`, mai `+200,0 (75,0%)`, jun `+400,0 (64,7%)`, jul `+780,0 (73,7%)`, ago `+105,0 (55,0%)`, set `+390,0 (75,0%)`, out `+325,0 (56,2%)`, nov `+665,0 (81,8%)`.
- **Estabilidade por subperíodo:** `H1 (jan–abr) = +R$ 1.632` | `H2 (mai–jul) = +R$ 1.380` | `IS = +R$ 3.012` (`Ret/DD 5,11`) | `OOS (ago–nov) = +R$ 1.485` (`Ret/DD 4,12`).
- **Correlação diária vs sinais brutos `WIN v3.2` (`bt.signals('WIN','v3.2')`, `ok==1`):** `+0,037` vs Saída A / `+0,056` vs Saída B (praticamente zero correlação).

#### Auditoria de Robustez (`V1a`)
| Teste | `ProxWall` (`ops / WR / PF / Net / DD / Ret/DD / H1·H2·OOS`) | `TP fixo 12` (`ops / Net / Ret/DD / Meses`) |
|---|---|---|
| Base (`custo 0,5 / slip 0,5`) | `184 / 66,3% / 1,72 / +4.498 / 590 / `**`7,62`**` / +1.632·+1.380·+1.485` | `190 / +3.985 / `**`6,87`**` / 11/11` |
| `LIVRE` (sem `UM_POR_VEZ`) | `210 / 63,3% / 1,48 / +3.728 / 860 / `**`4,33`**` (9/11)` | `218 / +3.855 / `**`4,59`**` / 9/11` |
| Pior caminho M1 | `184 / 66,3% / 1,72 / +4.498 / 590 / `**`7,62`** | `190 / +3.985 / `**`6,87`**` / 11/11` |
| Stop 2 ticks (`0,5 / 1,0`) | `184 / 66,3% / 1,67 / +4.318 / 615 / `**`7,02`**` (11/11)` | `190 / +3.785 / `**`6,31`**` / 10/11` |
| Custo 2x (`1,0 / 0,5`) | `184 / 66,3% / 1,55 / +3.578 / 640 / `**`5,59`**` (10/11)` | `190 / +3.035 / `**`4,93`**` / 9/11` |
| Estresse pesado (`1,0 / 1,0 / +0,5e`) | `183 / 63,4% / 1,25 / +1.892 / 682 / `**`2,77`**` (+492·+855·+545)` | `188 / +1.545 / `**`2,09`**` / 7/11` |
| **Placebo SEM divergência** | `415 / 61,4% / 1,29 / +4.538 / 985 / 4,61 (8/11)` | `416 / +3.085 / 3,18 / 7/11` |
| **Direção invertida (`-dir`)** | `185 / 53,0% / 0,62 / -3.842 / 4.178 / `**`-0,92`**` (1/11)` | `188 / -5.245 / `**`-0,96`**` / 1/11` |

#### Platô de Vizinhos (`V1a`)
- **`SL` × `TP` (`tm=24`):**
  - `SL 12`: `NW 6,76 (10/11)` | `TP10 4,28` | `TP12 3,20` | `TP15 2,86`
  - `SL 13`: `NW 7,91 (11/11)` | `TP10 5,99` | `TP12 5,93` | `TP15 5,96`
  - `SL 14`: `NW 7,62 (11/11)` | `TP10 6,87` | `TP12 6,87 (11/11)` | `TP15 6,95`
  - `SL 15`: `NW 6,61 (10/11)` | `TP10 6,12` | `TP12 5,94` | `TP15 5,86`
  - `SL 16`: `NW 5,86 (10/11)` | `TP10 5,42` | `TP12 5,23` | `TP15 4,89`
- **Níveis (`Wall` vs `All`):** `lv="wall"` -> `184 ops, 7,62 (11/11)` | `lv="all"` (`Wall+MidWall`) -> `179 ops, 7,49 (11/11)`.
- **Zona (`zone/pierce`):** `2,0/3,5 -> 7,85 (122 ops)`; `2,5/4,0 -> 6,86 (144 ops)`; `3,0/5,0 -> 7,75 (162 ops)`; `3,5/6,0 -> 7,62 (184 ops)`; `5,0/8,0 -> 4,37 (228 ops)`.
- **Limiar `ext30` (`SL=14`):** `>-0,2 -> 6,82 (204 ops)`; `>0,0 -> 7,62 (184 ops)`; `>+0,1 -> 7,82 (169 ops)`; `>+0,2 -> 8,11 (158 ops)`; `>+0,3 -> 5,70 (143 ops)`.

#### Observação crítica: papel do `open_module=True` (`M.V32` vs `M.V32_PROD`)
- O ganho do **`V1a`** concentra-se fortemente na manhã: **`09h` (`62 ops, +R$ 2.620, WR 72,6%`)** e **`10h` (`41 ops, +R$ 1.672,5, WR 75,6%`)**, com `zz` (`150 ops, +R$ 2.957,5`), `zz08` (`33 ops, +R$ 1.500`) e `lr` (`1 op, +R$ 40`).
- Com **`open_module=False` (`M.V32_PROD`)**, o mesmo filtro cai para `141 ops`, **`Ret/DD 1,04` (`+R$ 942`, `6/11` meses, `IS -R$ 308`)** porque `09h` perde tanto os sinais `zz08/lr` quanto o preenchimento antecipado do pool `F1` na abertura.

### Alternativa caso exija `open_module=False` (`M.V32_PROD` estrito): **`V3`**
- **`V3_flow` (`M.V32_PROD`, `f1="flow"`, `open_module=False`):** `Wall` `z=3,5/p=6,0`, `CONF`, âncora `COMMON` (`has_w or has_d`), janela `09:00–12:00` (`tm <= 720`), `inst_pass_delta > 0`, `SL 14 / TP 12 / tmax 12`, `UM_POR_VEZ`: **`229 ops`**, `WR 59,0%`, `PF 1,41`, `Net +R$ 3.655`, `DD R$ 615`, **`Ret/DD 5,94`**, `9/11` meses (`H1 +2.245 / H2 +430 / OOS +980`); Placebo SEM div `1,95`; Invertida `-R$ 6.195 (-0,97)`; porém cai bem em estresse (`Custo 2x = 2,92`, `Pesado = 0,92` com `OOS -R$ 55`, `LIVRE = 1,13`).
- **`V3_k1` (mesma regra trocando apenas `f1="flow_k1"`):** **`271 ops`**, `WR 59,8%`, `PF 1,45`, `Net +R$ 4.720`, `DD R$ 530`, **`Ret/DD 8,91`**, `11/11` meses (`H1 +1.595 / H2 +1.520 / OOS +1.605`), `Custo 2x 5,75`, `Stop 2t 8,09`, `Pesado 2,34`, `Placebo 1,95`, `Invertida -R$ 7.115`, platô contínuo em `tm<=690..780` (`6,48..8,91..6,22`) e `SL/TP 12/12..14/15` (`6,60 / 8,91 / 5,85`).
- **`V2` (`M.V32_PROD`, `Wall z=5,0`, `CONF`, `ANY_WALL`, `09h–12h`, `ext30>0,2`, `14/12t8`):** `115 ops`, `Ret/DD 10,64`, `8/11` meses, porém sensível ao `zone` (`z=3,5` com `e30>0,2` cai abaixo de 100 ops e `12/8t8` cai para `2,78`).
- **`V4` (`M.V32_PROD`, `Wall+Mid z=2,5/p=4,0`, `OPC EXT_OR_FURO`, `09h–15h`, `pass>0`, `12/12t24`):** `247 ops`, `Ret/DD 6,85`, porém `Pesado 0,60 (h2 -645)`.

---

## 1. Resposta sobre o Especialista 3.2 (`core/especialista_v22.py`)

O especialista em produção (`ESP_DIV_V22_WIN` em `core/especialista_v22.py`) opera **somente WIN**, usando `PARAMS["WIN"]`, motor `v3.2` (`V32_PROD`), gatilhos Opção C (`WALL` e `EXTREMO`) e saída `exit_A`. Nos testes anteriores (`research/div_master/especialistas/RESULTADOS.md`), o WDO havia chegado no máximo a `Ret/DD 1,3` robusto (platô zero) porque:
1. Os testes anteriores (`r1`/`r2`) **não** simularam `v3.2` em M1 no WDO nem testaram `CONF`;
2. `PARAMS["WDO"]` em `modulo.py` estava marcado como provisório (`zone=3.5, pierce_max=6.0`), e misturava `Wall` e `MidWall` como âncoras equivalentes (`LEVEL_TYPES = ("Wall", "MidWall")`).

---

## 2. Achado Estrutural no WDO: `Wall` pura vs `MidWall`

No WDO, `MidWall` fica intermediário entre `Wall` principais (`20–50 pts` de distância) e dilui fortemente a seletividade dos pivôs ancorados. Filtrar ou alimentar o motor apenas com níveis `Wall` (`type == "Wall"`, sem `MidWall`) e calibrar a banda da Wall (`zone=2.5, pierce_max=4.0`) elevou drasticamente a consistência entre todos os subperíodos (`H1`, `H2` e `ago–nov`).

---

## 3. Setup Campeão Aprovado na Auditoria (`C2`: `v3.1` + `Wall` pura + `ext30 > 0`)

### Regra exata
- **Motor:** `v3.1` (`engine_v31`, `elig="common"`), alimentado **apenas por níveis `Wall`** (sem `MidWall`).
- **Parâmetros WDO da Wall:** `zone = 2.5 pts`, `pierce_max = 4.0 pts` (demais parâmetros iguais a `PARAMS["WDO"]`: `tick=0.5`, `zz_floor=2.5`, `tol_v21=2.0`, `tol_v3=1.5`, `day_tol=1.0`).
- **Âncora / Gatilho:** Opção C (`M.triggers`) sobre candidatos com âncora em `Wall` (`c1 is not None or c2 is not None`, incluindo casos `SUPER` com `day`).
- **Filtro de contexto:** `ext30 > 0.0` (preço do fechamento anterior além do centro causal do NWE30 — ou seja, a favor de reversão à média, sem limiar decimal arbitrário).
- **Janela:** `09:00–17:00` (`540–1020` min), gestão `UM_POR_VEZ`.
- **Saída:** `SL = 12,0 pts`, `TP = 6,5 pts`, `tmax = 24` barras (`120 min`), sem Break-Even.

### Métricas no período completo (`02/01–11/11/2026`, 1 contrato)
- **Trades (`ops`):** `74` (`35` COMPRA / `39` VENDA)
- **Win Rate / Profit Factor:** `71,6%` / `2,05` (`53` gains, média `+R$ 59,1`; `19` losses, média `-R$ 80,3`, pior trade `-R$ 130`, máx. `3` losses seguidos; expectativa `+R$ 21,69/op`)
- **Lucro Líquido:** `+R$ 1.605` | **Drawdown máx.:** `R$ 205` | **`Ret/DD`: `7,83`**
- **Meses positivos:** `10/11` (`jan +85`, `fev +360`, `mar -20`, `abr +35`, `mai +180`, `jun +395`, `jul +155`, `ago +85`, `set +135`, `out +15`, `nov +180`)
- **Estabilidade por subperíodo:** `H1 (jan–abr) = +R$ 460`, `H2 (mai–jul) = +R$ 730`, `IS = +R$ 1.190` (`Ret/DD IS 5,80`), `OOS (ago–nov) = +R$ 415` (`Ret/DD OOS 2,08`).
- **Gestão `LIVRE` (sem trava de 1 por vez):** `77 ops`, `WR 72,7%`, `PF 2,17`, `Net +R$ 1.785`, `DD R$ 205`, **`Ret/DD 8,71` (`11/11` meses positivos)**.
- **Correlação diária com `ESP_DIV_V22_WIN`:** `-0,024` (praticamente zero correlação).

### Auditoria de Robustez (`C2`)
| Teste | `ops` | `WR` | `PF` | `Net (R$)` | `DD (R$)` | `Ret/DD` | `H1 / H2 / OOS` |
|---|---:|---:|---:|---:|---:|---:|---|
| Base (`custo 0,5 / slip 0,5`) | 74 | 71,6% | 2,05 | +1.605 | 205 | **7,83** | `+460 / +730 / +415` |
| Pior caminho intra-minuto M1 | 74 | 71,6% | 2,05 | +1.605 | 205 | **7,83** | `+460 / +730 / +415` |
| Stop 2 ticks (`custo 0,5 / slip 1,0`) | 74 | 71,6% | 1,99 | +1.560 | 210 | **7,43** | `+440 / +725 / +395` |
| Custo 2x (`custo 1,0 / slip 0,5`) | 74 | 71,6% | 1,76 | +1.235 | 220 | **5,61** | `+320 / +635 / +280` |
| Estresse pesado (`custo 1,0 / slip 1,0 / +0,5 entrada`) | 74 | 67,6% | 1,43 | +825 | 235 | **3,51** | `+170 / +420 / +235` |
| **Placebo SEM divergência** (mesmos pivôs/Wall/OPC/`ext30>0`) | 300 | 63,0% | 1,05 | +495 | 870 | **0,57** | `+30 / +650 / -185` |
| **Direção invertida (`-dir`)** | 76 | 59,2% | 0,74 | -915 | 915 | **-1,00** | `-170 / -150 / -595` |

### Platô de Vizinhos (`C2`)
- **SL × TP (`tm=24`):** `SL 10,0/6,5 -> 6,09`; `SL 10,5/6,5 -> 6,04`; `SL 11,0/6,5 -> 7,90`; `SL 12,0/6,0 -> 6,56`; `SL 12,0/6,5 -> 7,83`; `SL 12,0/7,0 -> 7,63`; `SL 12,0/8,0 -> 7,54`; `SL 13,0/6,5 -> 6,89`; `SL 14,0/6,5 -> 5,94`.
- **`tmax` (`SL=12, TP=6,5`):** `tm=12 -> 7,07`; `tm=18 -> 7,88`; `tm=24 -> 7,83`.
- **Zona da Wall (`zone/pierce`):** `2,0/3,5 -> 6,95 (10/11)`; `2,5/4,0 -> 7,83 (10/11)`; `3,0/5,0 -> 4,29 (9/11)`; `3,5/6,0 -> 3,33 (9/11)`.
- **Limiar `ext30` (`SL=12, TP=6,5`):** `>-0,2 -> 3,29`; `>0,0 -> 7,83`; `>+0,1 -> 6,83`; `>+0,2 -> 6,53`.

---

## 4. Alternativa de Maior Frequência (`C3`: `v3.1` + `Wall` + `inst_pass_delta > 0`)

Para quem quiser ~2x mais trades mantendo apenas divergência + Wall + fluxo passivo:
- **Regra:** `v3.1` (`Wall+MidWall`, `elig="all"`, `zone=3.5, pierce=6.0`), `OPC`, pivô próximo à `Wall` (`d_wall <= 3.5`), `inst_pass_delta` acumulado em `j..conf > 0`, `SL 12 / TP 6,5 / tmax 24`, `UM_POR_VEZ`.
- **Métricas Base:** `136 ops`, `WR 70,6%`, `PF 1,59`, `Net +R$ 2.085`, `DD R$ 400`, **`Ret/DD 5,21`**, `10/11` meses positivos (`H1 +585`, `H2 +715`, `OOS +785`, `Ret/DD IS 3,25`, `OOS 2,38`).
- **Robustez:** Custo 2x `Ret/DD 3,19` (`+R$ 1.405`); Stop 2t `Ret/DD 4,68`; Placebo sem divergência `Ret/DD 0,10`; Invertida `-R$ 1.020`. Platô mais estreito do que `C2` (`SL 12/8,0 -> 4,86`, `SL 12/5,5 -> 3,24`, `SL 14/6,5 -> 3,99`; sensível a `elig="all"` vs `"common"` `3,37`).

---

## 5. Candidatos Rejeitados na Auditoria (armadilhas evitadas)

- **`C4` (`v3.2 Wall-only z=2.5/p=4.0 | OPC | EXT_OR_FURO | ext50 > 0.3 | SL12 TP12 tm12`):** atingiu `Ret/DD 7,17` (`126 ops, 10/11 meses`), **porém foi reprovado no teste de platô de limiar**: `ext50 > 0,2` cai para `Ret/DD 1,19` e `ext50 > 0,4` cai para `Ret/DD 1,98`, além de a parcela `FURO_WALL` ter perdido `-R$ 185` enquanto todo o ganho veio de `EXTREMO`.
- **`C1` (`v3.1 Wall-only z=3.5 | OPC | ext50 > 0.3 | SL12 TP6.5`):** `Ret/DD 6,67 (93 ops)`, porém `ext50 > 0,2` cai para `2,40` e estresse pesado cai para `0,77` (`H1 -310`). Inferior a `C2`, que não usa corte decimal e resiste a tudo.
- **`v3.2 CONF FURO_WALL CANDLE_FAV` com `N30`:** apenas `41 ops` e `SL 12` vs alvo curto (`~1,7 pt` líquido médio), amostra pequena demais para risco de cauda.

---

## 6. Scripts desta pesquisa

- `research/div_master/wdo_especialista/estudo_wdo.py` (`wdo_cands.pkl`)
- `research/div_master/wdo_especialista/busca_phase1.py` (`phase1_hits.pkl`)
- `research/div_master/wdo_especialista/busca_phase2.py` (`phase2_hits.pkl`)
- `research/div_master/wdo_especialista/robustez_final.py`
- `research/div_master/wdo_especialista/check_overlap_plateau.py`
- `research/div_master/wdo_especialista/check_c3_and_details.py`
- `research/div_master/wdo_especialista/busca_v32_100.py` (`v32_100_hits.pkl`)
- `research/div_master/wdo_especialista/robustez_v32_100.py`
- `research/div_master/wdo_especialista/check_v1a_v2_v3.py`
