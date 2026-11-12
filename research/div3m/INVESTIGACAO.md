# Investigação — divergência 3 motores (só jan–jul, 11/11/2026)

Script: `investigar.py` · log: `investigacao.log` · sinais com atributos: `results/sinais_is_{WIN,WDO}.csv`.
Jan–jul dividido em H1 (jan–abr) e H2 (mai–jul); cortes dos grupos tirados do H1. Ago–nov não foi lido.
Medida: retorno bruto em pontos 12 barras depois da entrada (abertura da barra seguinte ao sinal), sem custo.

## Todas as divergências
| | Sinais | r12 H1 | r12 H2 | MFE/MAE 12 barras | Custo |
| :-- | --: | --: | --: | :-- | --: |
| WIN | 730 | −46 pts | −15 pts | 428 / 454 pts | 10 pts |
| WDO | 988 | −0,1 pt | +0,6 pt | 7,4 / 7,3 pts | 0,5 pt |

Sem filtro, a divergência não tem vantagem bruta. Todas as 64 saídas testadas ficaram com PF entre 0,8 e 1,04.

## O que se repete nas duas metades
| Grupo | WIN | WDO |
| :-- | :-- | :-- |
| Distância da NWE | ruim colado no centro e muito esticado; bom no meio (NWE80 0,10–0,41: +46/+20) | ruim colado no centro; bom ≥ 0,25 da meia-banda (+1,0/+1,3) |
| Inclinação da NWE50 | contra uma NWE caindo/subindo forte (≤ −1 ATR em 6 barras) é ruim (−143/−71) | sem padrão |
| Price action da barra do sinal | pavio de rejeição grande bom (+63/+27), pavio pequeno ruim (−158/−52); barra > 1,2 ATR ruim; corpo a favor pior | corpo contra melhor (H1 forte) |
| Perseguir | entrada > 1 ATR longe do pivô F2 ruim | idem (−1,1/−0,4) |
| Fluxo na barra | institucional/varejo muito a favor = exaustão (ruim) | varejo contra (vendendo na compra) bom (+0,9/+1,2; acerto 58/62%) |
| Horário | 09h ruim (−166/−121) | 09h ruim |
| Sequência no dia | 1ª divergência do dia ruim (−135/−31) | misto |
| Wall | perto da Wall foi PIOR (−65/−20 vs +11/−2) | sem diferença |
| 3 motores | aprova 99–100% (não filtra) | idem |

## Combinações (ainda é jan–jul: hipótese, não validação)
| | H1 n · r12 · r24 | H2 n · r12 · r24 |
| :-- | :-- | :-- |
| WIN NWE80 0,10–0,41 + sem 9h + não contra NWE50 forte | 152 · +52 · +68 | 130 · +46 · +123 |
| WIN sem 9h + pavio ≥ 0,46 + barra ≤ 1,2 ATR + não contra NWE50 forte | 119 · +40 · +78 | 87 · +24 · +88 |
| WDO sem 9h + NWE80 ≥ 0,25 | 236 · +1,1 · +1,3 | 169 · +1,1 · +0,1 |
| WDO sem 9h + NWE80 ≥ 0,25 + varejo contra | 153 · +1,5 · +1,5 | 109 · +0,5 · −0,8 |

No WIN, r24 > r12: o movimento bom demora; vale testar alvos mais longos ou trailing.
