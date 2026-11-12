# Sniper 5176 com o detector v3 (11/11/2026)

O que foi testado: o Sniper corrigido (base B), mudando só o detector de divergência usado para liberar a entrada do setup.

- **Script:** `bt_sniper_v3.py`.
- **Resultados:** `results/comparacao.csv` e `results/trades.csv`.
- **Mantido igual ao Sniper corrigido:**
  - entradas de setup;
  - gate 3 motores no WIN;
  - saída do WIN com 2 lotes, NWE30 + 750 e BE;
  - divergência causal entre `bi−tol−1` e `bi−1`;
  - horários e pausas: WIN 12h, WDO 11h;
  - meta diária: WIN R$ 180, WDO R$ 120.

A base foi reproduzida exatamente: 287 trades, PF 1,95, R$ 7.436, DD R$ 524, Ret/DD 14,2.

## Carteira (WIN + WDO), tolerância 2 barras como no Sniper atual
| Detector | jan–jul trades · PF · Ret/DD | ago–nov trades · PF · Ret/DD | Completo trades · PF · lucro · DD · Ret/DD · meses + |
| :-- | :-- | :-- | :-- |
| Antigo (atual) | 212 · 1,75 · **9,0** | 75 · 2,79 · 6,3 | 287 · 1,95 · 7.436 · 524 · **14,2** · 10/11 |
| v3 | 178 · 1,40 · 2,3 | 73 · 2,49 · 8,6 | 251 · 1,64 · 5.157 · 1.085 · 4,8 · 10/11 |
| v3 só perto da Wall | 101 · 2,10 · 5,3 | 42 · 4,02 · 12,5 | 143 · 2,46 · 5.032 · 586 · 8,6 · 10/11 |
| Antigo OU v3 | 330 · 1,52 · 5,8 | 128 · 2,89 · 9,5 | 458 · 1,80 · 10.533 · 945 · 11,2 · 10/11 |

Melhor de cada variante em jan–jul, testando tolerâncias de 1 a 4 barras:

| Variante | Tolerância | Ret/DD jan–jul | Completo |
| :-- | :-- | --: | :-- |
| Antigo | 2 | 9,0 | — |
| v3 só perto da Wall | 1 | 6,9 | 99 trades, PF 2,96, Ret/DD 10,9 |
| Antigo OU v3 | 4 | 7,9 | 607 trades, R$ 13.875, DD 947, Ret/DD 14,6 |

## Conclusão
- **Em jan–jul**, que é o período usado para escolher, nenhuma variante com o v3 superou o detector atual.
- **Trocar pelo v3** piora a carteira.
- **"Antigo OU v3"** aumenta o volume em 60–110% e o lucro em 40–85%, mas o DD sobe de R$ 524 para cerca de R$ 950.
- **Ressalva:** o período ago–nov já foi visto várias vezes neste projeto, então não serve mais como validação limpa.
