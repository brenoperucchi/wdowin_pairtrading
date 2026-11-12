# Auditoria do Sniper 5176 (`inject_unified_div_opt2.py`) — 11/11/2026

Script de auditoria (somente leitura, não grava o JSON): `audit_sniper.py` → `audit_result.json`.

## Como o número do painel é gerado
1. Candidatos WIN: **todos os trades dos setups registrados do WIN** no JSON (união, sem duplicar horário/direção)
   que passam no "3 motores" (filtro muito permissivo). Candidatos WDO: trades de WDO_01/05/07/10.
2. Filtro Sniper: existe divergência F1→F2 / T1→T2 do detector `detect_visual_swing_divergences` na mesma
   direção entre `entrada − 3` e a **barra da entrada** (inclusive).
3. WIN re-simulado com saída própria de 2 lotes (L1 banda oposta NWE30 260–750 pts, L2 750 pts, BE +180→+20);
   WDO usa a saída original do setup. Janela de horário (sem 12h WIN / sem 11h WDO) e meta diária (R$ 180 / R$ 120).

## O que foi encontrado
| # | Ponto | Efeito |
| :-- | :-- | :-- |
| 1 | **Barra do futuro:** a divergência pode ser detectada no FECHAMENTO da barra em que o trade já entrou (na abertura). O "3 motores" do WIN também cai para a barra da entrada se a anterior não existir. | Tirando isso: trades 400 → 287, lucro R$ 12.407 → 7.436, PF 2,26 → 1,95 |
| 2 | **DD diário:** o painel usa o DD do saldo de fim de dia, não trade a trade. | DD 445 → 569 na reprodução |
| 3 | **Filtros ajustados olhando o ano todo:** horários pulados, meta diária, limiares do detector e saídas foram escolhidos nos 212 pregões, sem separar IS/OOS. | Sem horários/meta (e sem barra do futuro): PF 1,61, R$ 6.582 |
| 4 | **"Na Wall" não é exigido:** o detector calcula `near_wall` mas não filtra. | 355 de 1.238 divergências do WIN (29%) estão fora da Wall |
| 5 | Stop rompido em gap é preenchido no preço do stop (o MT5 preenche na abertura). | Não medido; deixa o resultado um pouco otimista |
| 6 | Barras do Profit vêm de um cache externo (`.gemini/.../cached_214_*.json`), fora do repositório. | Não reproduzível a partir do repo |

## Números (1 contrato WDO + 2 contratos WIN, líquido)
| Versão | Trades | WR | PF | Lucro R$ | DD dia | Ret/DD dia | DD trade | Ret/DD trade | Meses + |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | :-: |
| Painel (doc) | 373 | 70,0 | 2,49 | 12.827 | 380 | 33,76 | — | — | 11/11 |
| A. Reprodução hoje | 400 | 69,2 | 2,26 | 12.407 | 445 | 27,9 | 569 | 21,8 | 11/11 |
| B. Sem barra do futuro | 287 | 67,2 | 1,95 | 7.436 | 465 | 16,0 | 524 | 14,2 | 10/11 |
| C. B sem horários/meta | 343 | 65,0 | 1,61 | 6.582 | 634 | 10,4 | 724 | 9,1 | 10/11 |

B por período: jan–jul PF 1,75, R$ 4.736, Ret/DD 9,0 (trade) · ago–nov PF 2,79, R$ 2.700, Ret/DD 6,3 (4/4 meses).
C por período: jan–jul PF 1,54, Ret/DD 6,2 · ago–nov PF 1,85, Ret/DD 4,0 (4/4 meses).
(Ago–nov não é OOS limpo: as regras foram ajustadas no ano inteiro.)

## Conclusão
O Ret/DD 33,76 está inflado (barra do futuro, DD diário, filtros escolhidos no ano todo), mas **sobra vantagem
real** depois de corrigir: PF 1,6–1,95 e Ret/DD 9–16. A diferença para os testes de `div_gate`/`div_entry` é a
construção: aqui a divergência filtra a **união das entradas de todos os setups** (amostra grande), com detector
de janela curta e saída própria de 2 lotes — combinação que não tinha sido testada.
