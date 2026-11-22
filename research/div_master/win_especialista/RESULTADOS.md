# Estudo WIN (`v3.2` + `>= 100` trades) e Portfólio WIN + WDO

**Período completo avaliado:** `2026-01-02` a `2026-11-11` (`213` pregões alinhados no WIN)  
**Execução:** simulação tick-a-tick M1 (`bt.sim`), 1 contrato (`R$ 0,20/pt`), custo `10 pts/trade`, slippage de stop `1 tick` (`5 pts`), EOD `17:25`, gestão `UM_POR_VEZ` (e comparação com `LIVRE`).  
**Subperíodos:** `H1` (`jan–abr`), `H2` (`mai–jul`), `OOS` (`ago–nov`, `IS = jan–jul`).

---

## 1. Diagnóstico do `ESP_DIV_V22_WIN` atual (`core/especialista_v22.py`)

O especialista de índice que **já está em produção** continua sendo o **#1 absoluto** em toda a busca `v3.2 >= 100` trades (`89` combinações encontradas com `Ret/DD >= 5,0` e `H1/H2/OOS > 0`):

- **Regra atual:** `V32_PROD` (`open_module=False`, `f1="flow"`), `Wall + MidWall` (`z=150, p=220`), `OPC`, sem `super`, `seq <= 1`, `10:00–15:55`, `ext50 > -0,5` e `slope50 > -0,5`, `SL 200`, sem alvo fixo, `BE +180 -> +20`, `tmax 12`.
- **Métricas (1 contrato / 2 contratos de produção):**
  - `266` ops, `WR 54,9%`, `PF 1,98`, **Net `+R$ 4.946`** (`1 ct`) / **`+R$ 9.892`** (`2 ct`), **DD `R$ 328`** (`1 ct`) / **`R$ 656`** (`2 ct`), **`Ret/DD 15,08`**, **`11/11` meses positivos** (`H1 +1.647 / H2 +1.191 / OOS +2.108` em 1 ct).
- **Auditoria pesada (1 ct):**
  - `LIVRE`: `281 ops`, `Net +R$ 4.663`, **`Ret/DD 12,57`** (`11/11`)
  - `Stop 2 ticks (10/10)`: `Net +R$ 4.742`, `PF 1,92`, **`Ret/DD 13,87`** (`11/11`; `WR` cai para `22,2%` apenas porque saídas no `BE +20` com `10` pts de custo + `10` pts de slip zeram em `0,0`)
  - `Custo 2x (20/5)`: `Net +R$ 4.414`, `PF 1,82`, **`Ret/DD 12,26`** (`11/11`)
  - `Estresse pesado (20/10/+5e)`: `Net +R$ 2.661`, `PF 1,46`, **`Ret/DD 7,04`** (`10/11`, `IS +2.072 / OOS +589`)
  - `Invertida (-dir)`: **`-R$ 1.849`** (`Ret/DD -0,80`)
  - `Placebo SEM divergência`: `193 ops`, `Net +R$ 1.770`, `Ret/DD 1,62` (`IS -R$ 431`, `6/11` meses)
  - **Platô `SL x tmax`:** todo o bloco `SL 180..250 × tmax 8..20` fica entre `Ret/DD 8,98` e `20,42` (`10–11/11` meses).

---

## 2. Novos Candidatos Complementares no WIN (`v3.2` + `>= 100` trades, baixa correlação com `E22`)

| ID | Regra resumida | `ops` | `WR` | `PF` | `Net 1ct` | `DD` | `Ret/DD` | `Meses` | `H1 / H2 / OOS` | `Pesado` | `Placebo` | `Corr E22` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| **`I3`** | `V32_PROD` \| `OPC ALL` \| `09h–11h` \| `ext50>0` \| `SL250 TP250 t24` | 116 | 65,5% | 1,72 | `+1.528` | 217 | **7,04** | 10/11 | `+602 / +708 / +218` | **5,37** (`10/11`) | **-0,19** (`-222`) | **-0,006** |
| **`I5`** | `V32 (open=True)` \| `CONF d_wall<=150` \| `09h–12h` \| `pass>0` \| `SL200 TP300 t24` | 119 | 52,9% | 1,52 | `+1.246` | 228 | **5,46** | 9/11 | `+577 / +326 / +343` | **3,72** (`8/11`) | **-0,50** (`-594`) | **-0,041** |
| **`I2`** | `V32_PROD` \| `OPC WALL` \| `09h–12h` \| `ext50>-0,5 & sl>-0,5` \| `SL200 TP300 t24` | 150 | 53,3% | 1,54 | `+1.630` | 215 | **7,58** | **11/11** | `+218 / +663 / +749` | **4,20** (`10/11`) | `1,15` (`+1.332`) | `+0,120` |
| **`I1`** | `V32 (open=True, wall)` \| `CONF` \| `09h–12h` \| `candle_fav` \| `SL250 TP200 t18` | 344 | 66,0% | 1,39 | `+2.425` | 371 | **6,54** | 9/11 | `+444 / +1.259 / +722` | `3,32` (`7/11`) | `2,50` (`OOS -294`) | `+0,022` |

### Platô dos melhores complementares (`I3` e `I5`)
- **`I3` (`SL 220..300 × TP 220..280`, `tm=24`):** faixa ampla de **`5,28` a `9,14`** (`10/11` meses); `z=100/150 -> 5,76 (106 ops)` e `z=150/220 -> 7,04 (116 ops)`; `tm<690 -> 6,53 (175 ops)`.
- **`I5` (`SL 200..250 × TP 250..300`, `tm=24`):** `200/300 -> 5,46`, `220/300 -> 6,14`, `250/250 -> 5,38`, `250/300 -> 7,95 (10/11)`; `tm<=690 -> 5,26 (106 ops)` e `lv="wall" -> 5,01 (122 ops)`. *(Nota: `I1` é mais sensível em `SL=200/220` (`1,32 / 3,07`) e sem `candle_fav` cai para `0,86`.)*

---

## 3. Portfólio Conjunto WIN (`ESP_DIV_V22_WIN` 2 ct + opcional WIN 1 ct) + WDO (`V1a` 1 ct)

| Carteira | `ops` | `WR` | `PF` | `Net (R$)` | `DD (R$)` | **`Ret/DD`** | `Meses +` | `H1 / H2 / OOS` |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **`E22 WIN (2ct)` isolado** | 266 | 54,9% | 1,98 | `+9.892` | `656` | **`15,08`** | `11/11` | `+3.294 / +2.382 / +4.216` |
| **`E22 WIN (2ct) + V1a WDO (1ct)`** | 450 | 59,6% | 1,88 | `+14.390` | `872` | **`16,50`** | `11/11` | `+4.926 / +3.762 / +5.701` |
| **`E22 WIN (2ct) + I3 WIN (1ct) + V1a WDO (1ct)`** | 566 | 60,8% | 1,86 | `+15.918` | `829` | **`19,20`** | `11/11` | `+5.528 / +4.470 / +5.919` |
| **`E22 WIN (2ct) + I5 WIN (1ct) + V1a WDO (1ct)`** | 569 | 58,2% | 1,83 | `+15.636` | **`784`** | **`19,94`** | `11/11` | `+5.504 / +4.088 / +6.044` |
| `E22 WIN (2ct) + I2 WIN (1ct) + V1a WDO (1ct)` | 600 | 58,0% | 1,83 | `+16.020` | `1.044` | `15,34` | `11/11` | `+5.144 / +4.425 / +6.450` |

- Correlação diária entre `E22 WIN (2ct)` e `V1a WDO (1ct)`: **`0,008`** (`0,037` nos `100` dias em que ambos operaram).

---

## 4. Scripts desta pesquisa

- `research/div_master/win_especialista/audit_e22_win.py`
- `research/div_master/win_especialista/busca_win_v32.py` (`win_v32_hits.pkl`)
- `research/div_master/win_especialista/robustez_win_v32.py`
- `research/div_master/win_especialista/check_i2_i3_i5.py`
