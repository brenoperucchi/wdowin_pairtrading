# Marcações do rotulador × detector v3 (WIN, 11/11/2026)

Script: `labels_vs_v3.py`. Saídas: `results/labels_vs_v3.csv`, `results/v3_sem_marcacao.csv` e
`results/diagnostico_labels.csv`.

**Base:** `research/div_master/labels/labels.csv`, estado efetivo depois dos UNDO.
- 105 decisões em 9 pregões: 52 válidas (49 rotuladas + 3 adicionadas à mão) e 53 falsas.
- Uma marcação conta como "pega" quando o v3 tem um sinal no mesmo sentido com o F2 a até 2 barras.

## Concordância
| Você \ v3 | v3 marcou | v3 não marcou |
| :-- | --: | --: |
| Válida (52) | 21 (40%) | 31 |
| Falsa (53) | 13 (25%) | 40 |

Fora disso, o v3 deu mais 23 sinais em pontos que não estavam entre os candidatos rotulados.

Por tipo, entre as válidas:

| Tipo | Pegas pelo v3 |
| :-- | :-- |
| Absorção | 9 de 17 |
| Rejeição | 12 de 27 |
| Rompimento | **0 de 8** |

## Por que o v3 perdeu as válidas (28 dias-caso com barras no dataset)
1. **Rompimento: 8 casos.** O F2 não passa do F1 em preço. Nos 8, o fundo de compra fica acima do F1 (venda: topo abaixo),
   entre 75 e 710 pts. O v3 exige que o F2 faça extremo novo (até 50 pts de folga), e esses F2 também não são pivô.
2. **Distância da Wall: 14 casos.** O F2 fica a mais de 100 pts da Wall/MidWall mais próxima. O v3 aceita até 100 pts, a
   menos que o preço fure e volte. Mas as falsas também ficam longe (mediana de 114–134 pts), então a distância da Wall
   sozinha não separa válida de falsa.
3. **Pivô: 14 F1 e 11 F2 não são pivô pela regra do v3.** A regra é 2 barras à esquerda e 1 à direita. Você aceita
   fundos/topos menos "limpos".
4. **Fluxo: não é o problema.** Em 27 das 28, a melhora do fluxo passa do limiar do v3.

## O que separa as suas válidas das falsas (medianas)
| | Falsa | Válida |
| :-- | --: | --: |
| F2 no extremo do pregão | 34% | 51% |
| Barra seguinte fecha a favor | 50% | 64% |
| Wyckoff na barra do F2 (a favor) | 38,5 mil | 57,2 mil |
| Institucional na barra do F2 (a favor) | 219 | 802 |
| Distância do F2 à Wall | 134 pts | 115 pts |
| Preço 12 barras depois | −133 pts | +155 pts |

A diferença de resultado 12 barras depois é grande. Se a marcação foi feita vendo o resto do dia, parte dela pode refletir
o que aconteceu depois, e não só o desenho da divergência.

# v4 (`detect_divergences_v4` em core/div_wall_signal.py)
O v4 é o v3 com três opções novas:
- tipo **rompimento**: o F2 não passa do F1 (compra com fundo mais alto) e o fluxo melhora, dentro da zona da Wall;
- **zona** da Wall configurável;
- **pivô** mais solto (1 barra à esquerda).

O script `labels_grid_v4.py` testou 37 variantes contra as marcações (`results/labels_grid_v4.csv`).

| Variante | Válidas pegas | Falsas pegas | Sinais/dia |
| :-- | --: | --: | --: |
| v3 | 21/52 | 13/53 | 6,3 |
| **v4: sem rompimento, zona 200, pivô 1** (melhor saldo) | 27/52 | 15/53 | 7,9 |
| v4R: com rompimento, zona 100, pivô 1 | 25/52 | 17/53 | 8,4 |
| Com rompimento, zona 200 (mais válidas) | 30/52 | 22/53 | 12,2 |

O rompimento interpretado assim pega no máximo 4 dos seus 8 e traz muitas falsas junto. Os seus 8 rompimentos também não
têm o F2 como pivô.

## Resultado
**Vantagem bruta em jan–jul, entrando em toda divergência:**

| | jan–abr | mai–jul | v3 (jan–abr / mai–jul) |
| :-- | --: | --: | --: |
| WIN | −25 pts | −31 pts | −17 / −46 |
| WDO | +0,1 pt | −0,4 pt | ≈0 |

**Dentro do Sniper** (carteira, tolerância 2; `research/sniper_v3/bt_sniper_v4.py`, `results/comparacao_v4.csv`):

| Detector | Ret/DD jan–jul | Período completo |
| :-- | --: | :-- |
| Atual | 9,0 | 287 trades · R$ 7.436 · DD 524 · Ret/DD 14,2 |
| v3 | 2,3 | — |
| v4 | 1,9 | 279 trades · R$ 5.644 · DD 1.370 · Ret/DD 4,1 |
| v4R | 1,9 | — |
| Antigo OU v4 | 4,7 | 477 trades · R$ 10.783 · DD 1.166 · Ret/DD 9,3 |
| Antigo OU v3 | 5,8 | — |

**Conclusão:** chegar mais perto das marcações não melhorou o resultado. O v4 concorda um pouco mais com você, mas opera
pior que o v3 e que o detector atual.
