# Correlação entre o fluxo calculado e o andamento do preço — 2026

**Data:** 13/11/2026 (America/Sao_Paulo). Somente leitura. Base: `div_wall_v1` (M5, WIN 213 pregões / WDO 211) e `div_wall_m1_v1` (M1). A onda **Fluxo Smart Money** é a mesma do painel 5176 e dos backtests (`compute_flow`): 45% Wyckoff (volume × posição do fechamento e pavios), 25% diferença de lote médio e 30% institucional sintético, depois suavizada (`0,55·(EMA2−EMA10)` do acumulado + `0,45·` impulso de 3 barras). `wave_d` é a variação da onda na barra; `force` é a força da própria barra, antes da suavização.

Períodos: IS = 02/01–31/07; OOS = 01/08–11/11 (até onde o dataset congelado vai). Retorno contemporâneo: corpo (`close−open`) e `close−close`. Horizontes futuros não atravessam o pregão. Números brutos: `research/data_audit/correlacao_fluxo_preco.csv`.

## 1. Correlação contemporânea (mesma barra)

O número que responde “o fluxo anda junto com o preço?” é a correlação de Pearson do fluxo da barra com o corpo do candle.

| Fluxo (WIN M5, ano) | Pearson × corpo | Spearman | Sinal | Pearson × close-close |
|---|---:|---:|---:|---:|
| Variação da onda Smart Money | 0,44 | 0,47 | 66% | 0,42 |
| Força da barra (antes da EMA) | 0,49 | 0,53 | 69% | 0,45 |
| Parcela Wyckoff (45% da força) | 0,49 | 0,56 | 71% | 0,46 |
| Parcela institucional (30%) | 0,40 | 0,22 | 54% | 0,35 |
| Institucional agressor (decomp.) | 0,84 | 0,88 | 85% | 0,81 |
| Inst. agressor + passivo | 0,84 | 0,86 | 83% | 0,80 |
| Varejo (decomp.) | 0,82 | 0,90 | 88% | 0,80 |
| Agressão bruta (compra−venda) | 0,84 | 0,91 | 87% | 0,81 |

A agressão e o institucional sintético andam quase colados no corpo do candle. A onda Smart Money, que é o que aparece no gráfico, é mais fraca (0,44), porque mistura a parcela passiva (correlação **negativa** com o corpo: −0,14 no WIN, −0,46 no WDO) e ainda passa por uma EMA sem deriva.

O mesmo recorte, Pearson × corpo, estável entre IS e OOS:

| Fluxo | WIN IS | WIN OOS | WDO IS | WDO OOS |
|---|---:|---:|---:|---:|
| Variação da onda | 0,44 | 0,45 | 0,35 | 0,34 |
| Força da barra | 0,48 | 0,50 | 0,38 | 0,37 |
| Inst. agressor | 0,86 | 0,80 | 0,62 | 0,54 |
| Agressão bruta | 0,86 | 0,80 | 0,76 | 0,73 |
| Varejo (decomp.) | 0,85 | 0,77 | 0,81 | 0,76 |

No M1 do WIN, a variação da onda × corpo cai para 0,27 (sinal 57%) e a força para 0,28; o institucional agressor continua em 0,82. Minuto a minuto o ruído aumenta, mas o caráter mecânico da decomposição permanece.

### Dentro do pregão: nível da onda × nível de preço

Em cada sessão, correlacionei a série com o close. A onda Smart Money **não** acompanha a tendência do dia — ela foi desenhada para não ter deriva. Quem acompanha o preço é o CVD (agressão acumulada).

| Série × close no pregão (M5, ano) | WIN mediana (p25–p75) | Sessões com corr. > 0,5 | WDO mediana (p25–p75) | Sessões com corr. > 0,5 |
|---|---:|---:|---:|---:|
| Onda Smart Money (nível) | 0,19 (−0,02 a 0,35) | 10% (28% negativas) | 0,08 (−0,12 a 0,24) | 8% (41% negativas) |
| CVD da agressão bruta | 0,87 (0,61 a 0,96) | 82% | 0,75 (0,44 a 0,88) | 73% |
| CVD institucional decomp. | 0,88 (0,70 a 0,95) | 84% | 0,49 (−0,05 a 0,73) | 48% |

## 2. Quanto disso é mecânico (o fluxo “é” o candle)

R² da regressão do fluxo da barra nas variáveis do candle. `linear_4` usa corpo, amplitude, volume e posição do fechamento. `volume × forma` acrescenta volume×corpo, volume×(posição−0,5) e volume×pavios — o desenho da parcela Wyckoff.

| Variável (WIN M5, ano) | R² linear_4 | R² volume × forma |
|---|---:|---:|
| Parcela Wyckoff | 0,56 | 0,99 |
| Força da barra | 0,54 | 0,97 |
| Variação da onda | 0,46 | 0,83 |
| Inst. agressor | 0,71 | 0,78 |
| Agressão bruta | 0,72 | 0,82 |
| Parcela institucional (30%) | 0,16 | 0,21 |
| Onda (nível) | 0,14 | 0,25 |

A parcela Wyckoff é, por construção, volume × geometria do candle: R² 0,99 não é descoberta, é a fórmula. Como ela pesa 45% da força, a força da barra fica quase inteiramente explicada (R² 0,97) e a variação da onda herda 0,83. O institucional sintético é menos circular (R² 0,21), mas o `inst_aggr_delta` isolado ainda tem R² 0,78 — a decomposição do `.min` também usa pavios. No WDO o quadro é o mesmo na força (R² 0,90) e um pouco mais baixo no institucional agressor (0,39).

## 3. Correlação preditiva (fluxo em t, retorno depois)

Pearson do fluxo da barra com o retorno futuro (`close` em t+h menos `close` em t), hit-rate de sinal e spread do retorno médio do quintil alto menos o quintil baixo, em pontos. Custo de referência: 10 pts no WIN, 0,5 pt no WDO.

### WIN M5

| Fluxo | Período | t+1 Pearson (sinal) | t+1 Q5−Q1 | t+3 | t+6 | t+12 Pearson (sinal) | t+12 Q5−Q1 |
|---|---|---:|---:|---:|---:|---:|---:|
| Variação da onda | IS | 0,003 (49%) | −1,7 | 0,000 | −0,003 | −0,007 (49%) | −15,7 |
| Variação da onda | OOS | 0,026 (50%) | +14,7 | 0,008 | 0,015 | 0,013 (50%) | +36,9 |
| Força da barra | IS | −0,002 (49%) | +0,5 | −0,007 | −0,005 | −0,007 (50%) | −10,6 |
| Força da barra | OOS | 0,036 (50%) | +18,9 | 0,016 | 0,021 | 0,007 (50%) | +13,5 |
| Força residual (sem a forma do candle) | IS | −0,010 (49%) | −2,7 | −0,002 | −0,001 | 0,002 (50%) | +8,2 |
| Força residual | OOS | −0,010 (49%) | −1,0 | 0,000 | 0,000 | −0,014 (49%) | −40,7 |
| Inst. agressor | IS | 0,007 (49%) | −0,2 | 0,005 | −0,013 | −0,013 (49%) | −24,9 |
| Inst. agressor | OOS | 0,011 (49%) | +0,1 | 0,005 | 0,008 | 0,020 (49%) | +43,6 |
| Agressão bruta | IS | 0,009 (49%) | +2,4 | 0,006 | −0,007 | −0,008 (49%) | −22,2 |
| Agressão bruta | OOS | 0,017 (49%) | +8,8 | 0,009 | 0,013 | 0,026 (49%) | +70,1 |

### WDO M5

| Fluxo | Período | t+1 Pearson (sinal) | t+1 Q5−Q1 | t+3 | t+6 | t+12 Pearson (sinal) | t+12 Q5−Q1 |
|---|---|---:|---:|---:|---:|---:|---:|
| Variação da onda | IS | −0,034 (42%) | — | −0,033 | −0,015 | −0,010 (48%) | — |
| Variação da onda | OOS | −0,032 (43%) | — | −0,008 | 0,000 | −0,005 (49%) | — |
| Força da barra | IS | −0,036 (42%) | −0,29 | −0,037 | −0,020 | −0,023 (48%) | −0,76 |
| Força da barra | OOS | −0,030 (43%) | −0,47 | −0,008 | 0,004 | −0,008 (49%) | −0,45 |
| Força residual | IS | 0,003 (44%) | +0,01 | 0,006 | 0,008 | −0,004 (48%) | −0,05 |
| Força residual | OOS | −0,004 (44%) | −0,01 | 0,009 | 0,006 | 0,007 (49%) | −0,13 |
| Agressão bruta | IS | −0,006 (44%) | +0,02 | −0,009 | −0,017 | −0,016 (47%) | −0,61 |
| Agressão bruta | OOS | 0,009 (44%) | +0,11 | 0,021 | 0,040 | 0,043 (48%) | +0,73 |

No M1 do WIN, variação da onda: t+5 IS −0,006 e OOS 0,011; t+15 IS −0,001 e OOS −0,003. Hit-rate de sinal entre 49% e 50%.

Os spreads de quintil do OOS no WIN às vezes ficam grandes em pontos (14 a 70 pts em 12 barras), mas a correlação linear permanece perto de zero e o acerto de sinal fica em 50%. Isso é típico de caudas, não de uma regra estável. No IS, os spreads da onda e da força são nulos ou negativos. O residual — o que sobra depois de tirar a forma do candle — não antecipa em nenhum dos dois períodos.

## 4. Dias com tape real (`.trd`)

Repeti o teste nos pregões em que a sessão foi montada com Times & Trades, comparando o institucional do tape com o do `.min` nos mesmos dias.

| Ativo / fluxo | Fonte | Pearson × corpo | Sinal | t+1 Pearson | t+12 Pearson |
|---|---|---:|---:|---:|---:|
| WIN inst. agressor | tape `.trd` | 0,75 | 81% | 0,015 | 0,070 |
| WIN inst. agressor | `.min` nos mesmos dias | 0,85 | 84% | 0,006 | −0,002 |
| WIN variação da onda | tape `.trd` | 0,41 | 67% | −0,043 | 0,027 |
| WIN variação da onda | `.min` nos mesmos dias | 0,46 | 66% | −0,065 | 0,009 |
| WDO inst. agressor | tape `.trd` | 0,66 | 55% | 0,001 | 0,003 |
| WDO inst. agressor | `.min` nos mesmos dias | 0,48 | 63% | 0,006 | −0,046 |
| WDO variação da onda | tape `.trd` | 0,25 | 51% | −0,057 | 0,003 |
| WDO variação da onda | `.min` nos mesmos dias | 0,32 | 62% | −0,080 | −0,001 |

No WIN, o institucional do tape ainda anda forte com o corpo (0,75), só um pouco menos que o do `.min` (0,85). No WDO o tape chega a correlacionar mais que o `.min`. Em ambos, a preditiva continua perto de zero (o 0,07 em t+12 no tape do WIN cabe em nove pregões e não se confirma no residual nem no sinal, que fica em 47%). Ou seja: mesmo o fluxo “de verdade” descreve a barra que acabou de fechar; não antecipa as seguintes.

## 5. Veredito

**Contemporânea: sim, e em grande parte mecânica.** No WIN M5, a variação da onda Smart Money correla 0,44 com o corpo da mesma barra (sinal 66%). A agressão bruta e o institucional sintético vão a 0,84 — quase o próprio candle. Isso é esperado: 45% da força é Wyckoff (R² 0,99 com volume × forma), a força inteira tem R² 0,97, e a decomposição do `.min` já usa pavios. A onda do gráfico, por ser sem deriva, **não** acompanha a tendência do dia (mediana 0,19 no pregão; só 10% das sessões acima de 0,50). Quem acompanha o preço ao longo do dia é o CVD da agressão (mediana 0,87).

**Preditiva: não há aresta linear.** No IS, a correlação da variação da onda com o retorno da barra seguinte é 0,003 (sinal 49%). No OOS chega a no máximo 0,03, com sinal ainda em 50%. Tirar a forma do candle da força deixa um residual que também não antecipa (−0,010 em t+1, IS e OOS). O WDO no IS chega a ter correlação **negativa** fraca (mean-reversion de curto prazo, sinal 42–44%), que some no horizonte maior. Em resumo: o fluxo calculado **descreve** o candle que acabou de fechar; **não mostra**, por si só, para onde o preço vai nas barras seguintes.

Isso não contradiz o especialista. Ele não compra a correlação bruta do fluxo com o retorno futuro: usa divergência (preço faz extremo e a onda não confirma), Wall/NWE e regras de entrada. A pergunta da correlação linear é outra, e a resposta é essa.
