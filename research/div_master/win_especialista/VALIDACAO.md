# Validação independente da proposta I3 / I5 e da carteira WIN + WDO (12/11/2026)

O código é próprio, sem importar os scripts da proposta: `validar_i3_i5.py`. As grades de vizinhos estão em `validar_I3_grade.csv` e `validar_I5_grade.csv`.

## Antes dos números
- **Tamanho da busca:** foram testadas cerca de 20 mil combinações (10 motores/modos × âncoras × 7 janelas × 6 contextos × 11 saídas), com 89 aprovadas.
  - O critério de aprovação já exigia ago–nov positivo. Ago–nov não é período de teste aqui.
- **O "E22" da proposta não é o especialista de produção.** Ele descarta os gatilhos repetidos (`dup`) antes de contar a ordem do dia.

| | Trades | Lucro | Ret/DD |
| :-- | --: | --: | --: |
| E22 da proposta | 266 | R$ 9.892 | 15,08 |
| Produção (`core/especialista_v22.run`) | 252 | R$ 9.214 | 14,05 |

  As carteiras da proposta partem da linha de cima.

## Resultados
| Teste | I3 | I5 |
| :-- | :-- | :-- |
| Reprodução | **exata**: 116 tr · R$ 1.528 · DD 217 · 7,04 | **exata**: 119 tr · R$ 1.246 · DD 228 · 5,46 |
| jan–jul / ago–nov | 6,04 / **1,25** | 3,96 / 1,60 |
| Placebo de Walls (mediana / máx) | 2,16 / 3,29: boa parte do resultado não depende da Wall | −0,29 / 0,74: depende da Wall |
| Direção invertida | −0,90 | −0,90 |
| Percentil entre os vizinhos | 99% (mediana dos vizinhos 2,11) | 97% (mediana 1,06) |
| **Walk-forward** (10 melhores de jan–jul medidos em ago–nov) | **mediana −0,34 · 4/10 positivos** | mediana 0,93 · 8/10 positivos |
| Mesma direção a ≤ 30 min de um trade do especialista | 20/116 | 19/119 |
| Correlação diária com o especialista | −0,02 | −0,06 |

## Carteira (especialista de produção 2c + extras 1c)
| Carteira | Trades | Lucro | DD | Ret/DD | jan–jul / ago–nov |
| :-- | --: | --: | --: | --: | :-- |
| Especialista | 252 | R$ 9.214 | R$ 656 | 14,05 | 7,50 / 9,99 |
| + V1a (TP 12) | 442 | R$ 13.199 | R$ 922 | 14,32 | 7,94 / 9,62 |
| + I3 | 368 | R$ 10.742 | R$ 661 | 16,25 | 9,42 / **7,66** |
| + I5 | 371 | R$ 10.460 | R$ 603 | 17,35 | 9,65 / 10,79 |
| + I3 + V1a | 558 | R$ 14.727 | R$ 851 | 17,31 | 10,14 / 9,04 |
| + I5 + V1a | 561 | R$ 14.445 | R$ 834 | 17,32 | 9,86 / 11,45 |

A proposta informava 16,50 / 19,20 / 19,94 a partir do E22 de 266 trades.

## Teste nulo da busca (`nulo_busca.py`)
A mesma grade (14.746 estratégias testadas) com o mesmo critério de aprovação, mas com a **direção de cada sinal sorteada**. Horários, filtros e saídas são idênticos; o que some é a vantagem direcional.

| | Aprovadas | Maior Ret/DD | Aprovadas com Ret/DD ≥ 7 |
| :-- | --: | --: | --: |
| Dados reais | 89 | 15,08 (o próprio E22) | — |
| Nulo, 5 sorteios | 5 / 12 / 7 / 15 / 56 | 6,15 – 10,84 | 0 a 13 |

- **Ruído puro:** a busca aprova de 5 a 56 "estratégias", com Ret/DD de até 10,8.
- **I3 e I5:** com 7,04 e 5,46, ficam **dentro** do que o ruído produz.
- **O excesso de aprovações no real** (89 contra mediana de 12) vem da família do E22: as aprovadas do topo têm correlação de 0,7 a 1,0 com ele.

## Veredito
- **I3: não aprovar.**
  - Falha no walk-forward: os melhores de jan–jul ficam negativos em ago–nov.
  - O ago–nov dele mesmo é fraco (1,25).
  - Metade do efeito aparece com Walls falsas.
  - Na carteira, piora ago–nov (9,99 → 7,66).
  - O número de vitrine é o melhor de uma busca de cerca de 20 mil combinações.
- **I5: efeito real, mas fraco.**
  - Depende das Walls verdadeiras e da direção.
  - Passa razoavelmente no walk-forward (8/10 positivos), mas a expectativa realista fica em torno de **Ret/DD 1**, não 5,46.
  - Depende do módulo de abertura, como o V1a.
  - Candidato a acompanhar em sombra, não a entrar na carteira.
- **V1a:** ver `wdo_v1a/RESULTADOS.md`. Com o especialista real, acrescenta lucro, mas quase não melhora o Ret/DD (14,05 → 14,32).
- **Carteira:** juntar uma estratégia positiva e pouco correlacionada sempre melhora o Ret/DD do período inteiro. O que importa é se cada peça é real e se segura fora da amostra. Só o I5 e o V1a passam nisso, e com expectativa bem menor que a informada.
- **Recomendação:** não ativar nada agora. Se quiser acompanhar, rodar **I5 e V1a em sombra** por ≥ 20 pregões, com o motor V3.2 com módulo de abertura separado do oficial.
