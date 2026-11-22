# Pesquisa: Seguidoras de Fluxo e Rompimento de Wall (WIN e WDO)

**Período avaliado:** `2026-01-02` a `2026-11-11` (`213` pregões WIN / `211` pregões WDO)  
**Execução:** simulação tick-a-tick M1 (`bt.sim`), 1 contrato (`WIN`: `R$ 0,20/pt`, custo `10 pts`, slip `5 pts`; `WDO`: `R$ 10/pt`, custo `0,5 pt`, slip `0,5 pt`), EOD `17:25`, `UM_POR_VEZ`.

---

## 1. WDO (Dólar) — Resultado Negativo

Em `234` combinações testadas entre `16` famílias (**explosão de fluxo**, **pullback no fluxo**, **ORB 30m com fluxo**, **rompimento de `Wall` / `Wall+MidWall`** e **rompimento sob `GammaFlip` / gamma negativo**):
- **Nenhuma atingiu o critério mínimo** (`0` hits com `ops >= 100`, `Ret/DD >= 2,0` e `H1/H2/OOS > 0`).
- Melhor seguidora de fluxo ficou em `Ret/DD 0,31` (`71 ops`, `IS -R$ 520`); todas as famílias de rompimento de Wall deram `Ret/DD` negativo (`-0,18` a `-0,80`).
- **Conclusão no WDO:** em M5, o dólar é fortemente reversivo a picos de fluxo e rompimentos de Wall; não há edge operacional para seguimento de fluxo ou rompimento no WDO.

---

## 2. WIN (Índice) — Seguidora de Fluxo Puro (sem `Wall`)

Tem edge estatístico real sobre o placebo (`Placebo SEM fluxo = -R$ 1.228 / Ret/DD -0,29`) e correlação zero (`-0,023`) com o `ESP_DIV_V22_WIN`, porém **não atingiu `Ret/DD >= 5,0` nem resistiu ao estresse pesado**:
- **`A_ag15_ps10_vol12_dw` (`ALL`, `SL 250 / TP 250 / t18`):** `209 ops`, `WR 58,9%`, `PF 1,30`, `Net +R$ 1.346`, `DD R$ 328`, **`Ret/DD 4,10`**, `8/11` meses (`H1 +282 / H2 +734 / OOS +330`).
- **`A_ag15_ps10_vol12_sl0` (`10h–16h`, `SL 300 / TP 250 / t18`):** `115 ops`, `WR 63,5%`, `PF 1,32`, `Net +R$ 858`, `DD R$ 231`, **`Ret/DD 3,71`**, `7/11` meses; porém cai para `0,29` (`IS -168`) no estresse pesado (`20/10/+5e`).

---

## 3. WIN (Índice) — Rompimento de `Wall` Pura + Fluxo Institucional (Descoberta Positiva)

Diferente da antiga Frente 2 (`frente2/rompimento.py`, que misturava `Wall` e `MidWall` na mesma lista), isolar **apenas `Wall` principal (`type == "Wall"`)** + fechamento forte no extremo da barra + espaço livre até o próximo nível (`Wall` ou `MidWall`) + fluxo a favor revelou edge claro e validado contra placebo:

### Regra exata (`B_dw_ex10` / `B_dw_vol11`, 100% causal até barra `i`, entrada na abertura `i+1`)
1. **Cruzamento de `Wall`:** fechamento da barra `i` cruza uma `Wall` (`c[i-1] <= W < c[i]` na compra; espelhado na venda).
2. **Convicção no candle:** fechamento no terço extremo a favor (`close_ext >= 0,65`).
3. **Fluxo alinhado:** agressão institucional líquida a favor `>= 1,0 × mediana_causal(|inst_aggr_delta|)` do pregão (`ag_n >= 1,0`) e onda Smart Money subindo na direção do rompimento (`dir * (wave[i] - wave[i-1]) > 0`).
4. **Espaço livre:** próxima `Wall`/`MidWall` a favor a pelo menos `200 pts` livres além do front-run (`nwa_d >= 200`).
5. **Janela:** `09:00–15:00` (`tm <= 900`).
6. **Filtro adicional por variante:**
   - **`B_dw_ex10` (maior lucro e `Ret/DD`):** preço anterior não hiper-esticado (`dir * ext50 < 1,0`). Saída: **`SL 280 / TP 280 / tmax 24`**.
   - **`B_dw_vol11` (mais seletiva, menor giro e maior PF):** volume total da barra `>= 1,1 × mediana_causal(vol)` do dia (`vol_r >= 1,1`). Saída: **`SL 250 / TP 250 / tmax 18`**.

### Auditoria Completa (`1` contrato WIN = `R$ 0,20/pt`)

| Teste | `B_dw_ex10` (`ops / PF / Net / DD / Ret/DD / H1·H2·OOS`) | `B_dw_vol11` (`ops / PF / Net / DD / Ret/DD / H1·H2·OOS`) |
|---|---|---|
| **Base (`10/5`)** | `713 / 1,26 / +4.581 / 511 / `**`8,96`**` (9/11) / +2.212·+772·+1.597` | `345 / 1,34 / +2.473 / 466 / `**`5,31`**` (9/11) / +1.127·+545·+801` |
| `LIVRE` | `790 / 1,16 / +3.268 / 757 / 4,32 (7/11)` | `349 / 1,31 / +2.362 / 519 / 4,55 (9/11)` |
| Pior caminho M1 | `713 / 1,26 / +4.581 / 511 / 8,96` | `345 / 1,34 / +2.473 / 466 / 5,31` |
| Stop 2 ticks (`10/10`) | `713 / 1,24 / +4.284 / 563 / 7,61 (9/11)` | `345 / 1,31 / +2.334 / 492 / 4,74 (9/11)` |
| Custo 2x (`20/5`) | `713 / 1,17 / +3.155 / 713 / 4,42 (8/11)` | `345 / 1,23 / +1.783 / 556 / 3,21 (9/11)` |
| **Pesado (`20/10/+5e`)** | `714 / 1,09 / +1.650 / 880 / `**`1,88`**` (+1.232·+106·+312)` | `344 / 1,12 / +985 / 668 / `**`1,47`**` (+350·+235·+400)` |
| **Invertida (`-dir`)** | `713 / 0,66 / -8.140 / 8.247 / -0,99 (0/11)` | `345 / 0,61 / -4.197 / 4.197 / -1,00 (1/11)` |
| **Placebo SEM `Wall`** | `1.588 / 0,98 / -711 / 2.895 / -0,25` | `553 / 0,98 / -221 / 1.010 / -0,22` |
| **Corr diária vs `E22`** | **`+0,211`** | **`+0,066`** |

- **Platô `B_dw_ex10`:** `SL 250..300 × TP 220..280` fica todo entre `4,59` e `9,47` (`SL 280 / TP 250 -> 9,47`, `SL 250 / TP 250 -> 6,80`); limiar `ag_n`: `>=0,0 -> 6,62`, `>=0,5 -> 6,81`, `>=1,0 -> 8,96` (`>=1,2` cai para `4,92`).
- **Ressalva:** por ter `PF` na faixa `1,26–1,34` (`+32` a `+36 pts` líquidos/trade), é sensível a derrapagem de entrada (`Pesado = 1,88 / 1,47`); exige execução limpa a mercado sem slippage excessivo.

---

## 4. Impacto na Carteira Completa (`E22 WIN 2ct + Rompimento WIN 1ct + V1a WDO 1ct`)

| Carteira | `ops` | `PF` | `Net (R$)` | `DD (R$)` | **`Ret/DD`** | `Meses +` | `H1 / H2 / OOS` |
|---|---:|---:|---:|---:|---:|---:|---|
| `E22 WIN (2ct) + V1a WDO (1ct)` | 450 | `1,88` | `+14.390` | `872` | **`16,50`** | `11/11` | `+4.926 / +3.762 / +5.701` |
| **`E22 (2ct) + B_dw_ex10 (1ct) + V1a WDO (1ct)`** | 1.163 | `1,56` | **`+18.970`** | `801` | **`23,68`** | `11/11` | `+7.138 / +4.534 / +7.298` |
| **`E22 (2ct) + B_dw_vol11 (1ct) + V1a WDO (1ct)`** | 795 | `1,71` | **`+16.862`** | **`748`** | **`22,54`** | `11/11` | `+6.054 / +4.307 / +6.502` |

---

## 5. Rompimento e Continuação com Convergência Estrutural no Fluxo (`F1 -> F2` estilo `v3.2`)

Para testar se a marcação estrutural `F1 -> F2` (usando exatamente os pivôs causais do ZigZag `v3.2` de `modulo.py` e a onda Smart Money `wave` de `compute_flow`) separa rompimentos reais de falsos rompimentos melhor que o filtro de 1 barra (`B_dw_ex10`), construímos três famílias causais (`busca_convergencia_v32.py` e `audit_convergencia_v32.py`):
1. **`BRK_F1F2` (Rompimento de Pivô + `Wall` com Convergência `F1 -> F2`):**
   - `F1` (`k`): pivô confirmado no ZigZag `v3.2` (`side = -1` topo para compra; `side = +1` fundo para venda) próximo a uma `Wall`.
   - `F2` (`t`): primeira barra (`2 <= t - k <= 48`) que fecha rompendo a cabeça do pivô `F1` (`c[t-1] <= px1 + buf` e `c[t] > px1` na compra) e cruzando/ancorada na `Wall`, **exigindo Convergência no Fluxo (`dir * (w2 - w1) > 0,15 * mediana_causal(|wave|)` e `dir * w2 > 0`)**.
2. **`PIV_CONV_CONT` (Continuação em Pullback `F1 -> F2`):** dois fundos ascendentes (`px2 > px1 + buf`, compra) ou dois topos descendentes (`px2 < px1 - buf`, venda) na `Wall` com `dir * (w2 - w1) > thr`.
3. **`PIV_CONV_MOM` / `PIV_MOM_REBRK`:** dois topos ascendentes ou dois fundos descendentes convergentes no ZigZag operando a favor após o respiro (`conf`).

### 5.1 Impacto Puro da Convergência `F1 -> F2` (Sem Filtros Extras, `near_wall=True`, `SL 14 / TP 14 / t24`)
- **WIN `BRK_F1F2` COM Convergência (`w2 - w1 > thr`):** `705 ops`, `WR 53,0%`, `PF 1,05`, **`Net +R$ 878`**, `Ret/DD +0,54` (`7/11` meses).
- **WIN `BRK_F1F2` SEM Convergência (Placebo `w2 - w1 <= thr`):** `470 ops`, `WR 48,9%`, `PF 0,88`, **`Net -R$ 1.626`**, `Ret/DD -0,68` (`4/11` meses).
- **WDO `BRK_F1F2`:** negativo com (`Ret/DD -0,87`) e sem convergência (`-0,54`), confirmando que rompimentos diretos de `Wall` no WDO sofrem absorção passiva/gamma.
- **Validação Cruzada Simétrica (`WIN + WDO` com exatamente a mesma regra):** apenas a família de pullback **`PIV_CONV_CONT`** (`conv | near_w | 09h–12h | smart>0 | SL12_NW_t24`) fecha positiva nos dois ativos simultaneamente (`WIN`: `144 ops`, `PF 1,30`, `Ret/DD 2,35`, `7/11m`; `WDO`: `94 ops`, `PF 1,28`, `Ret/DD 1,92`, `7/11m`, ambos com `H1 > 0` e `H2 > 0`).

### 5.2 Top Setups WIN `BRK_F1F2` (`hh != 11`, `ext50_trend < 0,5`) — Auditoria Completa de 9 Testes
Diferente do rompimento de 1 barra (`B_dw_ex10`), onde o placebo sem fluxo ainda era positivo, no **`BRK_F1F2` o Placebo SEM Convergência `F1 -> F2` dá prejuízo em todos os períodos (`H1 < 0, H2 < 0, OOS < 0`)**, provando que o alfa vem genuinamente da convergência estrutural `F1 -> F2` no fluxo:

| Teste (`1 ct WIN`) | `C1a_BRK_K1_NEAR_CRS` (`conv_k1w2`, `near&crs`, `SL280 TP280 t24`) | `C1b_BRK_K1_NEAR_CRS` (`conv_k1w2`, `near&crs`, `SL280 TP240 t18`) | `C2_BRK_K1_CROSS` (`conv_k1w2`, `cross_w`, `SL280 TP280 t24`) | `C3_BRK_FLOW_NEAR_CRS` (`conv`, `near&crs`, `SL280 TP280 t24`) |
|---|---|---|---|---|
| **1. `UM_POR_VEZ` (`10/5`)** | `122 op / WR 64,8% / PF 1,69 / +1.734 / DD 182 / `**`R/DD 9,53`**` (10/11)` | `122 op / WR 68,0% / PF 1,71 / +1.570 / DD 190 / `**`R/DD 8,26`**` (`**`11/11`**`)` | `139 op / WR 64,0% / PF 1,64 / +1.861 / DD 182 / `**`R/DD 10,23`**` (9/11)` | `207 op / WR 61,8% / PF 1,52 / +2.357 / DD 321 / `**`R/DD 7,34`**` (10/11)` |
| **Subperíodos (`H1/H2/OOS`)** | `+538 / +220 / +976` | `+388 / +310 / +872` | `+356 / +436 / +1.069` | `+746 / +420 / +1.191` |
| **2. `LIVRE`** | `133 op / PF 1,69 / R/DD 8,98 (10/11)` | `133 op / PF 1,67 / R/DD 7,96 (10/11)` | `150 op / PF 1,64 / R/DD 8,94 (9/11)` | `227 op / PF 1,46 / R/DD 6,92 (10/11)` |
| **3. Stop 2 ticks (`10/10`)** | `122 op / PF 1,67 / R/DD 9,10 (10/11)` | `122 op / PF 1,68 / R/DD 7,90 (11/11)` | `139 op / PF 1,61 / R/DD 9,74 (9/11)` | `207 op / PF 1,50 / R/DD 6,81 (10/11)` |
| **4. Custo 2x (`20/5`)** | `122 op / PF 1,58 / R/DD 7,76 (10/11)` | `122 op / PF 1,58 / R/DD 6,41 (10/11)` | `139 op / PF 1,53 / R/DD 8,16 (9/11)` | `207 op / PF 1,42 / R/DD 5,24 (10/11)` |
| **5. Pesado (`20/10/+5e`)** | `122 op / PF 1,44 / +1.218 / `**`R/DD 4,37`**` (9/11)` | `122 op / PF 1,55 / +1.286 / `**`R/DD 6,01`**` (10/11)` | `139 op / PF 1,41 / +1.304 / `**`R/DD 4,39`**` (9/11)` | `207 op / PF 1,31 / +1.521 / `**`R/DD 3,87`**` (9/11)` |
| **6. Pior caminho M1** | `122 op / PF 1,69 / R/DD 9,53` | `122 op / PF 1,71 / R/DD 8,26` | `139 op / PF 1,64 / R/DD 10,23` | `207 op / PF 1,52 / R/DD 7,34` |
| **7. Invertida (`-dir`)** | `122 op / PF 0,49 / -2.342 / R/DD -0,96 (0/11)` | `122 op / PF 0,52 / -2.049 / R/DD -0,94 (0/11)` | `139 op / PF 0,51 / -2.554 / R/DD -0,96 (1/11)` | `207 op / PF 0,55 / -3.387 / R/DD -0,97 (0/11)` |
| **8. PLACEBO SEM Convergência** | `113 op / PF 0,80 / `**`-668 / R/DD -0,76`**` (4/11)` | `113 op / PF 0,81 / `**`-593 / R/DD -0,79`**` (2/11)` | `123 op / PF 0,81 / `**`-693 / R/DD -0,77`**` (5/11)` | `141 op / PF 0,83 / `**`-700 / R/DD -0,81`**` (4/11)` |
| **Corr diária vs `E22_WIN`** | **`+0,088`** | **`+0,088`** | **`+0,217`** | **`+0,133`** |

- **Portfólio `E22_WIN (1 ct)` + `C1a_BRK_K1 (1 ct)`:** `388 ops`, `Net +R$ 6.680`, **`DD R$ 323`** (menor que os `R$ 328` do `E22` sozinho!), **`Ret/DD 20,68`**, **`11/11` meses**, `corr = +0,088`.
- **Portfólio `E22_WIN (2 ct)` + `C1a_BRK_K1 (1 ct)`:** `388 ops`, `Net +R$ 11.626`, `DD R$ 622`, **`Ret/DD 18,69`**, **`11/11` meses**.

---

## 6. Scripts desta pesquisa

- `research/div_master/flow_breakout/explore.py` (`explore_win.pkl`, `explore_wdo.pkl`)
- `research/div_master/flow_breakout/refine_win.py` (`refine_win_hits.pkl`)
- `research/div_master/flow_breakout/audit_win_fb.py`
- `research/div_master/flow_breakout/refine_breakout_sel.py`
- `research/div_master/flow_breakout/check_final_breakout.py`
- `research/div_master/flow_breakout/busca_convergencia_v32.py`
- `research/div_master/flow_breakout/audit_convergencia_v32.py`
