# Entradas próprias (divergência v2 / absorção rápida) — resultados (11/11/2026)

Protocolo: `PLANO.md`. Grade IS: `results/grid_is_WIN.csv`, `results/grid_is_WDO.csv` (13.888 linhas cada).
OOS (uma vez): `results/oos_log.json`, `results/oos_results.csv`, `results/oos_trades.csv`.

## IS (jan–jul): nenhuma família tem vantagem
| | WIN | WDO |
| :-- | --: | --: |
| Combinações com ≥ 150 trades e lucro | 62 de 13.888 | 32 de 13.888 |
| Combinações com ≥ 150 trades e PF ≥ 1,2 | 0 | 0 |
| Melhor PF com ≥ 150 trades | 1,18 (E1, 153 tr, Ret/DD 1,30) | 1,14 (E3, 161 tr, Ret/DD 0,72) |
| PF mediano E1 div + NWE | 0,79 | 0,78 |
| PF mediano E2 absorção + div | 0,62 | 0,75 |
| PF mediano E3 absorção + div + NWE | 0,47 | 0,84 |
| PF mediano E4 absorção sozinha | 0,80 | 0,66 |

No WIN, somar a divergência à absorção piorou o PF (0,80 → 0,62 → 0,47).

## OOS (ago–6/nov) das escolhas do IS
| Ativo | Entrada | Modo | IS PF | IS Ret/DD | OOS trades | OOS PF | OOS lucro | OOS Ret/DD |
| :-- | :-- | :-- | --: | --: | --: | --: | --: | --: |
| WIN | E1 div + NWE | livre | 1,03 | 0,17 | 78 | 0,88 | −256 | −0,41 |
| WIN | E1 div + NWE | um por vez | 1,01 | 0,08 | 70 | 0,81 | −384 | −0,60 |
| WDO | E1 div + NWE | livre | 1,09 | 0,47 | 72 | 0,55 | −1.040 | −0,80 |
| WIN | E4 absorção (controle) | livre | 0,87 | −0,68 | 394 | 0,91 | −765 | −0,62 |
| WDO | E4 absorção (controle) | livre | 0,71 | −0,97 | 882 | 0,63 | −9.695 | −0,97 |

Nenhuma aprovada. "Um por vez" × "livre": mesma conclusão; o modo não muda o sinal do resultado.
O placebo deu p < 0,10 em alguns casos porque as entradas aleatórias em Walls perdem ainda mais — o sinal é
"menos ruim" que o acaso, não lucrativo.

Conclusão: no M5, com estas saídas, divergência v2 e absorção rápida não sustentam entrada própria. O único uso
com evidência é o gate EXIGIR sobre entradas que já têm vantagem (EST_07, `research/div_gate/RESULTADOS.md`).
