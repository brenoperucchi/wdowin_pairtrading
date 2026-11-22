# Ablação do fluxo: a vantagem das estratégias vem do fluxo ou do preço? (16/11/2026)

**Pergunta do usuário:** se trocarmos a onda "Fluxo Smart Money" por um fluxo que não enxerga o preço, as estratégias que usam fluxo continuam funcionando?

**Resposta curta:** não. No WIN, a vantagem das estratégias atuais vem quase toda da **geometria do candle** que está dentro da parcela Wyckoff: onde a barra fecha dentro do range e o tamanho do pavio. Ela não vem do volume nem da agressão.
- Com o fluxo sem preço (agressão pura, ou porte + institucional sem pavio), o especialista de produção cai de Ret/DD 14,05 para 4–5. É o mesmo nível de uma onda **embaralhada ao acaso**.
- Uma onda feita **só de preço** (a geometria do Wyckoff com volume constante, sem nenhum dado de fluxo) mantém Ret/DD 10,6 no especialista e 13,8 no V21. Isso é maior que o V21 com a onda original.
- No WDO o quadro é menos claro: a mistura sem preço (D) preserva a SYM_DIV_WDO quase inteira (6,24 contra 6,80).

Nada foi alterado em `core/`, nos motores, no painel ou nos EAs. Não houve commit, push nem ordem. Todos os arquivos novos estão em `research/flow_ablation/`.

---

## 1. Método

### 1.1 Estratégias e motores que leem a onda (todos com harness reprodutível no `div_wall_v1`)

| Estratégia / motor | Onde | Harness usado | Reprodução da base |
| :-- | :-- | :-- | :-- |
| `ESP_DIV_V22_WIN` (produção, motor v3.2 `V32_PROD`) | `core/especialista_v22.run` | `setup_v32/motor_addon.exec_bars` + barras MT5 | **252 trades · R$ 9.214 · DD R$ 656 · Ret/DD 14,05 · jan–jul 7,50 / ago–nov 9,99** (exato) |
| `ESP_DIV_V21_WIN` (pesquisa, motor v2.1) | `especialistas/robust.py` | `signals_mode("ab")` + `run_exit` + `evaluate` | 325 trades · R$ 4.642 · Ret/DD 11,63. O documento dizia 319 / R$ 4.703 / 11,8, mas aquilo ia até 06/11. Em 12/11 o `bt.END` passou para 11/11; jan–jul é **idêntico** (R$ 2.335, 5,9) |
| Carteira V3.2: `C1a_BRK_WIN`, `SYM_DIV_WIN`, `V1a_DIV_WDO`, `SYM_DIV_WDO` | `core/carteira_v32_estrategias.run_strategy` | `carteira_v22/paridade_4_estrategias.exec_bars` | Mesmo nº de trades da pesquisa (122 / 358 / 184 / 313). O lucro do core em M5 difere da pesquisa em M1 em C1a (R$ 1.395 × 1.734) e SYM_WIN (R$ 1.158 × 1.683), por causa da execução M5 × M1. V1a e SYM_WDO batem |
| Add-ons `setup_v32` (T1/T2 WIN, T3A/T3B WDO) | `setup_v32/avaliar.py` | `build_days` / `gen_signals` / `execute` | T2 G3 S2b: N 37 · PF 1,33 · R$ 231 em jan–jul (exato) |
| Motor v2.1 (sinal) | `engine_v2_1/detect.py` | `evaluate.py` (rótulos) | Recall 73% · hold-out 60% · precisão 38% (exato) |
| Motor v3.2 (sinal) | `modulo.engine_v32` | igual a `v32/teste.labels` | 59% bruto / 36% consolidado (exato) |
| Div v2 (sinal) | `core/div_wall_signal.detect_divergences_v2` | configuração do rotulador (k 0,5, raio 150, `PIVO`) | **Não tem backtest de estratégia** no projeto. Medi só no nível de sinal: rótulos e estudo de evento |

A troca da onda é feita por monkeypatch de `modulo.compute_flow`. Onde o harness monta as barras, a variante é chamada direto. A regra, os filtros, as saídas e os limiares ficam **congelados**.

### 1.2 Variantes da onda

O pipeline depois da força é sempre o mesmo da produção: impulso de 3 barras, acumulado do dia, EMA 0,5 − EMA 2/11, onda = 0,55·(EMAf − EMAs) + 0,45·imp3, zerando a cada pregão. Só muda a força por barra.

| Variante | Força por barra | Usa OHLC? | Usa fluxo? |
| :-- | :-- | :-: | :-: |
| **A_BASE** | 0,45·Wyckoff + 0,25·Porte + 0,30·Inst (produção) | sim | sim |
| **B_PURO** | `buy_vol − sell_vol` (saldo de agressão do `.min`) | **não** | sim |
| **C_SEM_OHLC** | (0,25·Porte + 0,30·Inst_sem_pavio) / 0,55 | **não** | sim |
| **D_MIX** | 0,45·Puro + 0,25·Porte + 0,30·Inst_sem_pavio (o Puro ocupa a vaga do Wyckoff) | **não** | sim |
| **E1_PLAC_GEOM** (placebo) | A geometria do Wyckoff com **volume constante**: `((c−l)/rng)·(0,8+1,4·lw/rng) − ((h−c)/rng)·(0,8+1,4·uw/rng)` | sim | **não** |
| **E2_PLAC_CORPO** (placebo) | `close − open` | sim | **não** |
| **E3_EMBARALHADO** (nulo) | Força da base embaralhada dentro do pregão. Na tabela, 1 semente; no nulo (§4), 30 sementes | — | sem timing |
| X_WYCKOFF / X_PORTE / X_INST_PAVIO / X_INST_SEM_PAVIO / X_BASE_SEM_WYK | Cada componente sozinho, para atribuição. X_BASE_SEM_WYK é Porte + Inst **com** pavio | | |

**Institucional sem pavio:** recalculei minuto a minuto do `.min` bruto (`_load_profit_min_index`), com as fórmulas de `core/profit_min_decomp.py`. Só troquei as frações passivas `pas_b/pas_s`, que dependem do pavio e do corpo, por uma constante: a média do próprio ativo no ano (0,439 WIN, 0,446 WDO). Os pesos institucional/varejo/HFT dependem só do lote médio e ficam iguais.
- Paridade da versão com pavio contra o `div_wall_v1`: `inst_aggr`, `inst_pass` e `ret` batem **em todas as barras** dos dois ativos (`parity.py`).
- As únicas diferenças estão em `buy_vol`/`sell_vol`: 12–13/02 no WIN, onde o dataset tem agressão em outra escala (1.355 × 164.729 na barra de 09:00), e a barra das 18:25 do WDO. Ficaram como estão no dataset, igual ao que a base usa.

**Escala:** todos os limiares que leem a onda são relativos, k × mediana causal de |onda| (v2.1, v3.2, BRK_F1F2, Div v2), ou comparam sinal e direção (gatilhos G2/G3). A escala da onda não muda nada; só a forma importa. Por isso **não foi preciso normalizar**, e os números "não normalizados" são os próprios números abaixo.

**Divisão temporal:** a mesma da pesquisa, jan–jul (`IS_END = 2026-07-31`) contra ago–11/nov. Atenção: ago–nov **já foi visto** quando as regras foram escolhidas, então não é um teste limpo.

---

## 2. Resultado por estratégia (Ret/DD do período completo; jan–jul / ago–nov)

| Variante | E22 prod. (2c) | V21 | C1a_BRK_WIN | SYM_DIV_WIN | V1a_DIV_WDO | SYM_DIV_WDO | **Carteira de produção** (E22 2c + 4) |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| **A_BASE** | **14,05** (7,50 / 9,99) | **11,63** (5,90 / 10,78) | 5,45 | 1,73 | 7,62 | 6,80 | **15,89** · R$ 20.612 |
| B_PURO | 3,99 (1,57 / 4,15) | 3,67 (1,73 / 2,37) | 0,05 | −0,55 | 1,87 | 0,34 | 2,34 · R$ 5.698 |
| C_SEM_OHLC | 5,28 (2,78 / 3,05) | 4,21 (1,31 / 3,82) | −0,73 | −0,66 | 3,00 | 1,49 | 4,08 · R$ 9.375 |
| D_MIX | 7,08 (2,51 / 9,89) | 6,05 (5,03 / 5,09) | −0,15 | 0,02 | 4,78 | **6,24** | 9,49 · R$ 13.969 |
| **E1_PLAC_GEOM (só preço)** | **10,61** (8,85 / 7,71) | **13,82** (7,28 / 11,31) | 2,76 | 0,76 | 3,11 | 2,36 | 9,49 · R$ 14.837 |
| E2_PLAC_CORPO (só preço) | 1,37 | 0,48 | 1,34 | −0,73 | 1,50 | 0,36 | 1,25 · R$ 3.581 |
| E3_EMBARALHADO (1 semente) | 3,40 | 4,67 | 1,08 | −0,66 | 3,28 | 3,73 | 6,13 · R$ 10.086 |
| X_WYCKOFF | 12,31 (6,06 / 10,66) | 12,21 | 4,38 | 1,73 | 8,04 | 3,37 | 11,84 · R$ 19.047 |
| X_PORTE | 5,05 | 2,69 | −0,65 | −0,71 | 4,69 | 1,70 | 5,21 |
| X_INST_PAVIO | 3,92 | 1,91 | 0,99 | 1,99 | 2,66 | 3,45 | 8,09 |
| X_INST_SEM_PAVIO | 3,42 | 1,58 | −0,63 | −0,41 | 3,21 | 1,06 | 5,02 |
| X_BASE_SEM_WYK | 2,05 | 0,48 | −0,57 | −0,38 | 2,73 | 1,71 | 2,93 |

Detalhe do especialista de produção (2 contratos):

| Variante | N | Lucro R$ | PF | WR | DD R$ | Ret/DD | Meses + | Trades da base mantidos |
| :-- | --: | --: | --: | --: | --: | --: | :-: | --: |
| A_BASE | 252 | 9.214 | 1,94 | 54,0% | 656 | 14,05 | 11/11 | 100% |
| B_PURO | 228 | 4.112 | 1,43 | 50,0% | 1.030 | 3,99 | 7/11 | 43% |
| C_SEM_OHLC | 253 | 6.150 | 1,59 | 51,4% | 1.164 | 5,28 | 6/11 | 41% |
| D_MIX | 221 | 6.554 | 1,85 | 58,4% | 926 | 7,08 | 10/11 | 42% |
| E1_PLAC_GEOM | 251 | 8.782 | 1,88 | 53,0% | 828 | 10,61 | 11/11 | **83%** |
| X_WYCKOFF | 251 | 9.032 | 1,92 | 53,8% | 734 | 12,31 | 11/11 | **94%** |

Com o fluxo sem preço, **só cerca de 42% dos trades continuam os mesmos**: é praticamente outra estratégia. Com a onda feita só de preço (E1), 83% dos trades continuam os mesmos.

Tabelas completas, com N, PF, WR, DD, jan–jul, ago–nov, meses e Jaccard de cada estratégia, estão em `results/tabelas.md` e `results/estrategias_por_variante.csv`.

**Add-ons do `setup_v32`:** nenhuma variante os salva. Na base, todas as configurações de WDO perdem em jan–jul e continuam perdendo com qualquer onda. T2 G3 S2b, a "menos ruim", piora em todas as variantes (B: PF 1,08; C: 8 trades). O veredito de 13/11 (não ligar) continua valendo.

---

## 3. Quem carrega a vantagem (atribuição)

1. **A geometria do Wyckoff é a vantagem no WIN.** A parcela Wyckoff sozinha (X_WYCKOFF) mantém de 90% a 100% do resultado em E22, V21, C1a e SYM_WIN. Trocar o volume dela por uma constante (E1) quase não muda nada: o V21 até melhora, e jan–jul do E22 vai de 7,50 para 8,85.
2. **Não é "qualquer preço".** O corpo do candle (E2) falha em tudo: o E22 cai para 1,37 e o V21 para 0,48. O que funciona é a medida específica de **fechamento no range + pavio**, ou seja, a rejeição/absorção desenhada no candle.
3. **Porte e Institucional não carregam vantagem no WIN.** Sozinhos, ou juntos sem o Wyckoff (X_BASE_SEM_WYK: E22 2,05, V21 0,48), ficam no nível do nulo ou abaixo. Tirar o pavio do institucional (X_INST_PAVIO → X_INST_SEM_PAVIO) muda pouco, porque ele já não ajudava.
4. **Agressão pura (B) não reproduz o especialista.** Fica no nível do nulo. Isso não quer dizer que agressão não tenha informação. Quer dizer que **estas regras**, ajustadas sobre a onda base, não a extraem.
5. **WDO é diferente.** Nas duas estratégias de WDO, a geometria pura (E1) fica bem abaixo da base: 3,11 e 2,36. A mistura sem preço D_MIX mantém a SYM_DIV_WDO (6,24 contra 6,80, 11/11 meses), e o Porte sozinho dá 4,69 no V1a. Há algum sinal de fluxo real no WDO, mas com N pequeno e sem teste limpo.

---

## 4. Nulo: o quanto um fluxo aleatório já entrega

Embaralhei a força da base dentro de cada pregão, com 30 sementes. A distribuição de valores é a mesma, mas o timing fica destruído. As âncoras (Wall/extremo), os gatilhos, o contexto NWE e as saídas ficam iguais. Como o pipeline da onda tem memória, o resultado continua "parecendo" fluxo, mas sem informação.

| Estratégia | Nulo: Ret/DD mediano [p95; máx] | Nulo: lucro mediano | Base | Variantes acima do p95 do nulo |
| :-- | :-- | --: | --: | :-- |
| E22 | 2,63 [6,81; 15,22] | R$ 3.988 | 14,05 | A, **D_MIX (7,08)**, E1, X_WYCKOFF |
| V21 | 2,22 [6,32; 14,82] | R$ 1.942 | 11,63 | A, E1, X_WYCKOFF |
| C1a_BRK_WIN | 0,41 [1,42; 2,17] | R$ 200 | 5,45 | A, E1, X_WYCKOFF |
| SYM_DIV_WIN | −0,78 [−0,12; 0,08] | −R$ 1.205 | 1,73 | A, D_MIX, E1, X_WYCKOFF, X_INST_PAVIO |
| V1a_DIV_WDO | 4,10 [6,02; 6,90] | R$ 2.952 | 7,62 | A, X_WYCKOFF |
| SYM_DIV_WDO | 1,79 [4,26; 4,77] | R$ 1.900 | 6,80 | A, **D_MIX** |

Leitura:
- **Uma onda aleatória já dá cerca de R$ 4 mil no E22.** Cerca de 40% do lucro do especialista vem da estrutura da regra (âncora, gatilho, NWE, saída), e não da onda. A onda base acrescenta o resto, e isso é claramente significativo.
- **O fluxo sem preço puro (B, C) não se distingue do aleatório** em nenhuma estratégia de WIN.
- **D_MIX** passa raspando o p95 no E22 (7,08 contra 6,81) e passa com folga na SYM_DIV_WDO. É o único sinal de que fluxo sem preço tem alguma informação aproveitável por estas regras.
- O máximo do nulo no E22 (15,22 em 30 sementes) mostra que um único número de Ret/DD tem **muita variância** com 250 trades.

---

## 5. Reajuste justo (a base joga em casa)

As regras foram escolhidas com a onda base: 77.828 configurações na busca de 12/11, incluindo a memória da onda. Para não punir as variantes por isso, reajustei para cada variante o limiar k do motor (0 a 0,75), a memória da EMA (3 pares) e a mistura (3 pares), num total de 72 configurações no E22 e 8 no V21. A escolha é **só em jan–jul**, com N ≥ 100, e a medida é em ago–nov (`extra.py retune`, `results/reajuste_grade.csv`).

| Estratégia · variante | Melhor de jan–jul: config | jan–jul | ago–nov Ret/DD (R$) | Mediana de ago–nov dos 10 melhores de jan–jul |
| :-- | :-- | --: | --: | --: |
| E22 · A_BASE | k 0,75 · mem (0,4; 2/21) · mix (0,92; 0,08) | 7,55 | **−0,73** (−R$ 1.224) | 9,27 |
| E22 · B_PURO | k 0,35 · mem (0,4; 2/21) · mix (0,3; 0,7) | 4,67 | 2,67 | 2,84 |
| E22 · C_SEM_OHLC | k 0 · mem (0,6; 2/9) · mix (0,3; 0,7) | 4,06 | 2,34 | 3,22 |
| E22 · D_MIX | k 0,35 · original | 5,69 | 7,72 | 6,62 |
| E22 · E1_PLAC_GEOM | k 0,35 · mem (0,6; 2/9) | 10,28 | 6,44 | 6,30 |
| E22 · X_WYCKOFF | k 0 · mem (0,6; 2/9) · mix (0,92; 0,08) | 10,08 | 15,59 | 9,52 |
| V21 · A_BASE | original (k 0,15) | 5,90 | 10,78 | 10,58 |
| V21 · B_PURO | k 0 | 3,87 | 3,32 | 2,29 |
| V21 · C_SEM_OHLC | k 0,10 | 1,86 | 3,95 | 4,33 |
| V21 · D_MIX | k 0,25 | 5,30 | 7,22 | 5,59 |
| V21 · E1_PLAC_GEOM | k 0,10 | 7,94 | 10,91 | 9,38 |

Mesmo com reajuste próprio, **B e C não chegam perto**: ficam em 2–4 fora da amostra, contra 9–10 da base e da geometria. D_MIX melhora (6–7 fora da amostra), mas fica abaixo do que só a geometria do candle entrega. O próprio reajuste da base mostra o perigo do sobreajuste: o "melhor de jan–jul" da base perde em ago–nov.

---

## 6. Nível de sinal

### 6.1 Rótulos do usuário

São 9 pregões de WIN, com 44 divergências válidas de rejeição/absorção. O casamento é pelo F2 com tolerância de ± 2 barras.

| Motor | A_BASE | B_PURO | C_SEM_OHLC | D_MIX | E1_PLAC_GEOM | X_WYCKOFF | E3 (aleatório) |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| v2.1 recall (hold-out) | 73% (60%) | 50% (47%) | 52% (47%) | 55% (47%) | 66% (60%) | 70% (60%) | 48% (33%) |
| v3.2 bruto | 59% (47%) | 50% (40%) | 41% (33%) | 50% (33%) | 57% (47%) | 59% (47%) | 43% (27%) |
| Div v2 | 73% (87%) | 57% (53%) | 57% (67%) | 57% (53%) | 64% (73%) | 73% (87%) | 52% (53%) |

**Ressalva forte:** os rótulos foram feitos **olhando a onda base**, e os candidatos mostrados ao usuário saíram dela. O recall maior da base é em parte circular. Mesmo assim, o padrão é o mesmo do backtest: Wyckoff ≈ base, geometria pura perto, e o fluxo sem preço perto do aleatório.

Em 11/11, o rotulador usou o snapshot ao vivo, cuja onda difere da do `div_wall_v1`. Usei a do dataset, e a base reproduz os 73% / 60% oficiais.

### 6.2 Estudo de evento

Para cada candidato do motor, a entrada é na abertura depois da confirmação e a saída 12 barras depois, já líquido do custo. Isso mede a divergência crua, sem âncora de gatilho nem contexto.
- **WIN v2.1:** a base dá +18 pts por candidato (t = 1,3). Todas as variantes sem preço ficam perto de 0. A geometria pura dá +9,5 e o Wyckoff +13.
- **WIN v3.2:** fica entre +7 e −9 pts, e nenhuma variante é significativa.
- **Div v2 e todo o WDO:** são negativos com qualquer onda (WDO v2.1 da base: −0,38 pt, t = −2,0).

A divergência sozinha quase não tem vantagem. O que as estratégias aproveitam é a interação dela com as âncoras, o gatilho e a saída.

---

## 7. Dias de tape real (.trd)

São 10 pregões de WIN e 9 de WDO (as datas estão em `results/tabelas.md`). Em cada um, a mesma variante foi refeita trocando o institucional do `.min` pelo do tape, que está na sessão JSON (`m5_cvd_series`).
- **B_PURO é idêntico no tape e no `.min`**, com correlação 1,00 e os mesmos candidatos. A agressão do `.min` é o próprio dado da B3, então o fluxo puro é **fluxo real em todos os 213 dias**, não só nos dias de tape.
- **O institucional sintético não bate com o do tape**, quando comparado como onda: a correlação do X_INST com o institucional do tape é −0,07 no WIN e −0,65 no WDO. O `inst_aggr` isolado correlaciona 0,95 (auditoria de 13/11), então quem descola é a parte passiva e de varejo da decomposição. Mesmo assim, C_SEM_OHLC mantém 90% (WIN) e 95% (WDO) dos candidatos v3.2 quando o institucional vem do tape, porque o Porte pesa.
- **Na base, os 9 trades do E22 nesses dias são os mesmos** com o institucional do `.min` ou do tape (R$ 46 → R$ 46). O institucional pesa pouco na onda, e o Wyckoff domina.
- Com N de 6 a 14 trades por variante, **não dá para tirar conclusão de desempenho** nos dias de tape. Serve só para mostrar que a fonte do institucional não muda as estratégias atuais.

---

## 8. Ressalvas

1. **Vantagem de casa:** as regras, as âncoras, os gatilhos, as saídas e a memória da onda foram escolhidos sobre a onda base, com dezenas de milhares de configurações. O reajuste da §5 compensa só em parte (72 configurações contra 77 mil).
2. **Ago–nov não é fora da amostra limpo.** Ele foi visto na escolha das regras de 12/11. O único teste limpo continua sendo o papel ao vivo.
3. **N pequeno:** E22 tem 252 trades (173 em jan–jul), e o nulo mostra que Ret/DD de 15 pode surgir ao acaso (máximo em 30 sementes). As diferenças entre variantes próximas (por exemplo 10,6 × 12,3) não são significativas. As diferenças grandes (14 × 4) são.
4. **"Sem preço" não quer dizer "sem correlação com o preço".** A agressão move o preço, por isso o saldo puro acompanha o candle na mesma barra (correlação 0,84 na auditoria). Isso é causalidade, não vazamento. O vazamento de verdade é a geometria do candle dentro da fórmula, e é ela que carrega a vantagem.
5. **Institucional sem pavio** com fração passiva constante é uma escolha minha (média do ano). Outra constante muda pouco, porque o termo vira um "contra-agressão" proporcional ao volume.
6. **Dados:** 12–13/02 no WIN têm `buy_vol`/`sell_vol` em outra escala no dataset, o que afeta a base e o B igualmente. Os dias de tape são poucos, e o institucional do tape tem definição própria (corretora/passivo).
7. **Div v2** não tem estratégia com backtest no projeto, então só foi medido no nível de sinal.

---

## 9. Conclusão e recomendação

1. **O fluxo sem preço não preserva a vantagem.** Com agressão pura ou porte + institucional sem pavio, o especialista de produção cai para Ret/DD 4–5, e a carteira de produção cai de 15,9 para 2,3–4,1. Isso fica no nível de uma onda aleatória.
2. **A vantagem é real, mas é de preço.** É a geometria de rejeição do candle (fechamento no range + pavio) dentro da parcela Wyckoff, e o volume não acrescenta. No WIN, a "Fluxo Smart Money" funciona como um **oscilador de rejeição de candle acumulado**. Ela bate o nulo com folga e se mantém em jan–jul e em ago–nov, mas **não é medida de fluxo institucional**.
3. **Não trocar a onda do painel e das estratégias pelo `fluxo_puro.ntsl`** esperando os mesmos resultados. São indicadores diferentes. O puro serve para leitura discricionária de agressão real.
4. **Para o Profit/NTSL:** como o Wyckoff sozinho reproduz cerca de 90% do comportamento do E22 e do V21, um indicador NTSL **só com a parcela Wyckoff** (OHLC + `AgressionVolBuy/Sell`, sem porte nem institucional) já reproduz quase tudo o que importa para as estratégias. No WIN, até a versão com volume constante funciona (E22 10,6; V21 13,8), o que dispensaria o plugin de agressão. No WDO, não.
5. **Se a meta for uma estratégia de fluxo de verdade:** desenhar do zero sobre D_MIX ou B, com regras pré-registradas, escolha só em jan–jul e validação em papel. O D_MIX é o único sem preço acima do nulo (E22 7,08; SYM_DIV_WDO 6,24), e o WDO parece o lugar mais promissor. Gravar o tape diariamente daqui para frente ajuda a validar o institucional.

## 10. Por tipo de player, forma de apregoar e tamanho de lote (16/11/2026)

Pergunta: a ablação acima tratou o fluxo como um bloco. Aqui ele é aberto em **quem negocia** (estrangeiro, banco nacional, UBS/BTG, HFT, varejo), **como apregoa** (agressor × passivo, absorção, renovação no mesmo preço) e **tamanho da boleta** (1, 2–5, 6–20, 21–100, >100 contratos e percentis do ativo). Para cada pedaço medimos três coisas. Primeiro, se ele traz informação **além do preço**. Segundo, se melhora as estratégias. Terceiro, se o `.min` (único dado que existe para todos os pregões) consegue reproduzi-lo.

### 10.1 Que dado granular existe (inventário, `results/tape/inventario_trd.csv`)

| Fonte | O que tem | Cobertura útil |
| :-- | :-- | :-- |
| `.trd` do Profit/Scalper (tape negócio a negócio: preço, qtd, corretora compradora e vendedora, agressor/RLP/direto) | Tudo o que este estudo precisa, por corretora e por boleta | **27 pregões completos**: WIN 12 (2025: 25/09, 26/09, 21/11, 24/11, 25/11; 2026: 05/01, 13/04, 14/04, 11/08, 11/11, 12/11, 13/11). WDO 15 (2025: 28–30/07, 28/08, 24–26/09, 27/10, 21/11, 24/11, 25/11; 2026: 30/03, 29/06, 28/10, 29/10). Dentro do período das estratégias (jan–11/nov/26) e com muralhas, ficam só **5 WIN + 4 WDO**. |
| `.trd` parciais | O arquivo para no meio do pregão | WIN 31/07/25, 29/09/25, 06/01, 13/05, 27/07; WDO 31/07/25, 29/09/25, 31/03, 13/04, 30/10. Também 16/11 (sendo gravado ao vivo, excluído). Todos descartados. |
| `.trd` "amostrados" | Cobrem o horário todo, mas trazem só 5–15% dos negócios e quase nenhum RLP | WIN 15/04, 17/06, 12/08; WDO 29/08/25, 30/04, 29/05, 30/06, 31/08, 30/09. Descartados. **Atenção:** a seção 7 usou JSONs de sessão de alguns desses dias (WIN 15/04, 17/06, 12/08; WDO 30/04, 29/05, 30/06, 31/08, 30/09). Se esses JSONs saíram dos mesmos arquivos, o "tape" daqueles dias era parcial. |
| Book / DOM / livro de ofertas | Não há histórico gravado. Os outros binários do Profit (`.agg`, `.rnk`, `.var`, `.sec`, `.prc`) não mostram nada de livro. | Nenhuma. Por isso iceberg e renovação são só **proxy pelo tape** (o mesmo passivo sendo agredido várias vezes no mesmo preço). |
| `.min` do Profit (M1) | Volume comprador/vendedor agredido e **nº de negócios por lado**, ou seja, lote médio por lado. Não tem corretora nem distribuição de lotes dentro do minuto. | 237 pregões WIN, 238 WDO (dez/25–nov/26). A soma da agressão do tape bate **exatamente** com `buy_qty`/`sell_qty` do `.min` (corr 1,00), então o alinhamento está certo. |
| `rastro_irado/data/irai_live.db` (leitura) | `market_bars` do MT5: OHLC, volume, `real_volume`, `delta` agregado (WIN$N e WDO$N, M1 desde mai–jun/26, M5 desde 2022; o delta do WDO só existe desde abr/26) | Não tem corretora, negócio nem livro, então não acrescenta nada ao `.min`. Não foi usado. |
| DOLPRO `.trd` | 14–16/04/26 completos | Contrato cheio, com composição de players diferente. Fora do estudo. |

#### Tabela 10.1 — Quem negocia (média dos pregões de tape completos; % do volume do book)
| Classe (corretoras) | WIN % do volume agressor | WIN % do volume passivo | WIN boleta agressora mediana | WDO % agressor | WDO % passivo | WDO boleta mediana |
| :-- | --: | --: | --: | --: | --: | --: |
| Estrangeiro (Merrill, JPM, Goldman, Morgan, Citi, Tullett) | 3,9% | 1,8% | 17 | 13,3% | 7,2% | 263 |
| Banco nacional (Itaú, Bradesco, Santander, Safra) | 6,8% | 9,0% | 24 | 11,2% | 10,2% | 53 |
| UBS / BTG | 22,6% | 19,8% | 38 | 27,0% | 22,5% | 76 |
| HFT (Ideal) | 23,4% | 30,9% | 32 | 13,2% | 14,2% | 35 |
| Varejo (XP, Genial, Toro, Inter, Futura, CM, Modal, Mirae) | 42,9% | 38,4% | 20 | 32,6% | 44,0% | 52 |
| Outras | 0,3% | 0,2% | — | 2,7% | 1,8% | — |
| RLP (% de todo o volume, fora do book) | 25,9% | | | 17,0% | | |

Leitura: no WIN, **varejo (43%) e HFT/UBS-BTG (~46%) fazem quase toda a agressão**. Os estrangeiros são só 4% do volume agressor. No WDO o estrangeiro pesa 13% e agride com boletas muito maiores (mediana 263 contratos). Boletas ≥ p90 (WIN ≥ 30, WDO ≥ 46 contratos) são 10% das boletas, mas **63% (WIN) e 74% (WDO) do volume**. As boletas de 1 contrato são 34–38% das boletas e 2% do volume.

### 10.2 Como cada componente foi montado (`tape_components.py`)

- **Player.** Classe da corretora pelas listas do projeto (`B3_CODE_TO_NAME`/`PLAYER_ROLE_BY_BROKER`). Três medidas por barra M5:
  - `agr` = compra agredida − venda agredida pela classe;
  - `pas` = compra passiva − venda passiva (se a agressão é vendedora, o passivo comprou);
  - `net` = agr + pas.
- **Regra do projeto no tape real.** Mesma lógica de `_build_from_profit_trd`: boleta = mesmo segundo + mesma corretora + mesmo lado, limiares 30/10/25 (WIN) e 15/3/10 (WDO). Daí saem `inst_aggr`, `inst_pass`, `hft`, `ret` e o termo Inst da força (0,55·agr + 1,15·pas − 0,85·varejo).
- **Lote.** Delta agressor por faixa de tamanho de **boleta** (1, 2–5, 6–20, 21–100, >100) e por percentil do ativo (≤ p50, ≥ p90, ≥ p99; WIN p50/p90/p99 = 3/30/150, WDO = 3/46/341).
- **Absorção.** Grupo passivo (minuto, preço, corretora passiva, lado) com volume ≥ p99 dos grupos (WIN 512, WDO 492 contratos). O sinal é o do lado passivo.
- **Renovação/iceberg (proxy).** O mesmo grupo passivo agredido em ≥ 5 segundos distintos no minuto.
- **Componentes do `.min` (todos os dias):**
  - contagem C−V de negócios;
  - porte (lote médio por lado);
  - "minutos de lote grande": delta só dos minutos/lados com lote médio ≥ p90;
  - "excesso de lote": delta agressor − lote médio × delta de contagem;
  - Inst agressor, Inst passivo e varejo sintéticos (fórmula com pavio).

**Métrica (`component_ic.py`).** Para cada componente (dividido pelo volume médio da barra no dia):

- correlação de Spearman com o retorno da **própria** barra;
- IC (Spearman) com o retorno das próximas 1, 3 e 6 barras, e acerto de sinal;
- **IC parcial**: o IC depois de tirar, por regressão nos postos, o retorno da barra, a posição do fechamento no range, o retorno de 3 barras e a geometria Wyckoff só-preço (E1). É o número que responde "informação além do preço".

O erro-padrão vem de **bootstrap por pregão** (400 reamostragens), porque barras do mesmo dia não são independentes. t = IC/EP. Em negrito: |t| ≥ 2.

### 10.3 Informação além do preço — tape real

#### Tabela 10.3 — Tape real (12 pregões WIN, 15 WDO; 2025-07 a 2026-11), barras M5
| Componente | WIN corr barra | WIN IC t+1 (t) | WIN IC parcial t+1 (t) | WIN IC parcial t+3 (t) | WIN IC parcial t+6 (t) | WDO corr barra | WDO IC t+1 (t) | WDO IC parcial t+1 (t) | WDO IC parcial t+3 (t) | WDO IC parcial t+6 (t) |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| Agressão total (B) | 0,93 | −0,011 (−0,4) | −0,000 (−0,0) | 0,011 (0,4) | 0,005 (0,2) | 0,77 | −0,022 (−0,8) | −0,007 (−0,4) | 0,001 (0,0) | −0,012 (−0,4) |
| Contagem de boletas (Δ) | 0,83 | 0,008 (0,3) | 0,033 (1,4) | 0,015 (0,4) | −0,005 (−0,1) | 0,51 | −0,023 (−1,0) | −0,014 (−0,7) | 0,019 (0,6) | 0,021 (0,5) |
| Porte (lote médio C×V) | 0,27 | **−0,030 (−2,9)** | **−0,031 (−2,1)** | 0,000 (0,0) | 0,005 (0,2) | 0,33 | 0,016 (1,0) | 0,028 (1,4) | 0,004 (0,2) | −0,018 (−0,6) |
| Estrangeiro agressor | 0,40 | −0,004 (−0,2) | 0,002 (0,1) | 0,015 (0,6) | 0,037 (1,5) | 0,40 | 0,062 (2,0) | **0,084 (2,7)** | **0,067 (3,1)** | **0,048 (2,3)** |
| Estrangeiro passivo | −0,48 | 0,005 (0,2) | −0,001 (−0,0) | 0,002 (0,0) | 0,028 (0,7) | −0,13 | 0,024 (1,2) | 0,021 (1,0) | 0,012 (0,4) | 0,045 (1,6) |
| Estrangeiro líquido | 0,08 | −0,017 (−0,6) | −0,015 (−0,5) | 0,005 (0,2) | 0,049 (1,8) | 0,24 | **0,064 (2,1)** | **0,076 (2,4)** | **0,049 (2,5)** | **0,052 (2,3)** |
| Banco nacional agressor | 0,44 | −0,027 (−1,2) | −0,025 (−1,1) | −0,024 (−1,1) | −0,011 (−0,4) | 0,24 | −0,013 (−0,6) | −0,007 (−0,3) | 0,027 (1,4) | 0,057 (2,0) |
| Banco nacional passivo | −0,67 | −0,041 (−1,7) | **−0,061 (−2,4)** | −0,048 (−1,8) | **−0,063 (−2,2)** | −0,38 | −0,024 (−0,9) | −0,035 (−1,5) | −0,011 (−0,4) | −0,013 (−0,5) |
| Banco nacional líquido | −0,23 | −0,041 (−1,8) | −0,041 (−1,8) | −0,029 (−1,7) | −0,039 (−1,9) | −0,01 | −0,020 (−0,6) | −0,020 (−0,6) | 0,010 (0,5) | 0,035 (1,3) |
| UBS/BTG agressor | 0,77 | −0,031 (−0,9) | −0,034 (−1,1) | −0,037 (−1,3) | −0,038 (−1,1) | 0,43 | −0,014 (−0,4) | −0,007 (−0,2) | 0,010 (0,5) | −0,032 (−1,2) |
| UBS/BTG passivo | −0,90 | 0,005 (0,2) | −0,011 (−0,4) | −0,001 (−0,0) | 0,004 (0,1) | −0,58 | 0,035 (1,2) | 0,027 (1,0) | 0,008 (0,6) | 0,025 (1,1) |
| HFT (Ideal) agressor | 0,40 | 0,041 (1,6) | 0,048 (1,5) | 0,056 (1,3) | 0,029 (0,8) | 0,11 | −0,022 (−0,8) | −0,017 (−0,6) | 0,016 (0,6) | 0,004 (0,2) |
| HFT passivo | −0,53 | 0,036 (1,1) | 0,042 (1,0) | −0,006 (−0,2) | 0,005 (0,2) | −0,40 | 0,013 (0,8) | −0,003 (−0,2) | −0,024 (−1,4) | −0,018 (−0,9) |
| HFT líquido | −0,08 | 0,067 (1,7) | 0,071 (1,8) | 0,045 (1,5) | 0,013 (0,4) | −0,14 | −0,021 (−0,9) | −0,027 (−1,2) | 0,002 (0,1) | −0,011 (−0,4) |
| Varejo agressor | 0,88 | −0,010 (−0,4) | −0,001 (−0,0) | −0,000 (−0,0) | 0,014 (0,5) | 0,60 | −0,032 (−1,3) | −0,024 (−1,4) | −0,009 (−0,5) | −0,023 (−1,1) |
| Varejo passivo | −0,92 | 0,017 (0,7) | 0,014 (0,5) | 0,002 (0,1) | −0,003 (−0,1) | −0,76 | 0,009 (0,3) | −0,010 (−0,5) | −0,005 (−0,2) | −0,014 (−0,6) |
| Varejo líquido | 0,03 | −0,003 (−0,1) | −0,009 (−0,3) | 0,009 (0,3) | 0,015 (0,7) | −0,26 | −0,028 (−1,3) | −0,034 (−1,7) | −0,024 (−1,3) | −0,026 (−1,5) |
| Boleta 1 contrato | 0,65 | 0,005 (0,2) | 0,015 (0,6) | 0,009 (0,2) | −0,003 (−0,1) | 0,43 | −0,030 (−1,0) | −0,022 (−0,9) | 0,016 (0,5) | 0,021 (0,5) |
| Boleta 2–5 | 0,83 | −0,001 (−0,0) | 0,018 (0,9) | −0,006 (−0,2) | −0,016 (−0,5) | 0,49 | −0,029 (−1,3) | −0,021 (−0,9) | 0,029 (0,9) | 0,030 (0,7) |
| Boleta 6–20 | 0,83 | 0,018 (0,9) | **0,052 (2,8)** | 0,046 (1,3) | 0,025 (0,7) | 0,38 | −0,018 (−0,8) | −0,011 (−0,5) | 0,021 (1,0) | 0,007 (0,2) |
| Boleta 21–100 | 0,81 | −0,011 (−0,6) | −0,005 (−0,2) | −0,025 (−0,8) | −0,028 (−0,9) | 0,41 | 0,018 (0,8) | 0,032 (1,3) | 0,021 (1,0) | 0,003 (0,1) |
| Boleta >100 | 0,86 | −0,021 (−0,7) | −0,023 (−0,9) | 0,018 (0,9) | 0,020 (0,8) | 0,73 | −0,032 (−1,1) | −0,023 (−1,0) | 0,000 (0,0) | −0,008 (−0,3) |
| Boleta ≥ p90 do ativo | 0,91 | −0,017 (−0,7) | −0,017 (−0,7) | 0,005 (0,2) | 0,004 (0,2) | 0,75 | −0,025 (−0,9) | −0,012 (−0,5) | −0,002 (−0,1) | −0,019 (−0,7) |
| Boleta ≥ p99 do ativo | 0,84 | −0,018 (−0,6) | −0,015 (−0,6) | 0,019 (0,8) | 0,013 (0,4) | 0,64 | −0,051 (−1,7) | **−0,048 (−2,2)** | −0,006 (−0,3) | −0,031 (−1,0) |
| Absorção (passivo grande) | −0,66 | 0,031 (1,4) | 0,028 (0,9) | −0,006 (−0,2) | 0,006 (0,3) | −0,34 | 0,005 (0,2) | −0,002 (−0,1) | −0,017 (−0,5) | 0,005 (0,1) |
| Renovação/iceberg (proxy) | −0,79 | −0,015 (−0,7) | −0,034 (−1,2) | **−0,068 (−2,9)** | −0,021 (−0,9) | −0,59 | 0,004 (0,1) | −0,013 (−0,7) | −0,018 (−0,7) | −0,017 (−0,6) |
| Inst agressor (regra do projeto) | 0,90 | −0,014 (−0,5) | −0,009 (−0,4) | 0,022 (1,3) | 0,013 (0,6) | 0,76 | −0,019 (−0,7) | −0,002 (−0,1) | −0,001 (−0,0) | −0,013 (−0,5) |
| Inst passivo (regra do projeto) | −0,85 | 0,031 (1,2) | 0,042 (1,4) | 0,032 (1,2) | 0,049 (1,5) | −0,70 | 0,021 (0,8) | 0,006 (0,3) | −0,000 (−0,0) | 0,014 (0,4) |
| Varejo (regra do projeto) | 0,85 | 0,005 (0,2) | 0,029 (1,4) | 0,009 (0,2) | 0,011 (0,2) | 0,60 | −0,040 (−1,7) | −0,037 (−1,5) | 0,013 (0,4) | 0,014 (0,4) |
| Termo Inst da força (tape) | −0,56 | 0,006 (0,2) | 0,001 (0,0) | 0,031 (0,8) | 0,063 (1,7) | −0,61 | 0,023 (1,0) | 0,011 (0,6) | −0,009 (−0,3) | 0,007 (0,2) |
| Referência só preço: geometria × volume | 0,69 | 0,024 (0,9) | **0,043 (2,2)** | 0,011 (0,4) | 0,030 (1,0) | 0,63 | **−0,072 (−3,0)** | −0,047 (−1,6) | **−0,052 (−2,4)** | **−0,087 (−3,5)** |


(Na referência "só preço" o IC parcial é ≈ 0 por construção, porque ela é um dos controles. O que sobra é só o efeito do volume.)

#### Tabela 10.4 — .min, todos os pregões (237 WIN, 237 WDO; dez/25 a 13/nov/26), barras M5
| Componente | WIN corr barra | WIN IC t+1 (t) | WIN IC parcial t+1 (t) | WIN IC parcial t+3 (t) | WIN IC parcial t+6 (t) | WDO corr barra | WDO IC t+1 (t) | WDO IC parcial t+1 (t) | WDO IC parcial t+3 (t) | WDO IC parcial t+6 (t) |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| Agressão total (B) | 0,91 | −0,004 (−0,5) | **−0,015 (−2,2)** | −0,010 (−1,4) | **−0,022 (−2,6)** | 0,73 | **−0,019 (−3,1)** | 0,008 (1,4) | 0,009 (1,3) | 0,011 (1,4) |
| .min contagem C−V | 0,90 | −0,002 (−0,3) | −0,009 (−1,3) | −0,010 (−1,2) | −0,017 (−1,9) | 0,79 | **−0,019 (−3,1)** | 0,012 (1,9) | 0,004 (0,7) | 0,006 (0,8) |
| .min porte | −0,34 | −0,004 (−0,6) | −0,004 (−0,6) | −0,001 (−0,1) | −0,008 (−1,1) | −0,03 | 0,000 (0,1) | 0,001 (0,1) | 0,005 (0,8) | 0,006 (0,9) |
| .min minutos de lote grande | −0,16 | −0,006 (−1,2) | −0,006 (−1,2) | 0,002 (0,4) | −0,005 (−0,8) | −0,04 | 0,002 (0,4) | 0,002 (0,3) | 0,011 (1,8) | **0,014 (2,0)** |
| .min excesso de lote | −0,37 | −0,005 (−0,8) | −0,006 (−0,8) | −0,003 (−0,4) | −0,010 (−1,3) | −0,08 | 0,005 (0,8) | 0,004 (0,6) | 0,008 (1,2) | 0,008 (1,0) |
| .min Inst agressor sintético | 0,88 | −0,007 (−0,9) | **−0,019 (−2,8)** | −0,009 (−1,2) | **−0,021 (−2,8)** | 0,60 | **−0,015 (−2,4)** | 0,008 (1,3) | 0,009 (1,3) | 0,008 (1,1) |
| .min Inst passivo sintético | −0,32 | 0,011 (1,8) | **0,013 (2,0)** | 0,007 (1,0) | 0,008 (1,0) | −0,46 | 0,003 (0,5) | −0,007 (−1,1) | −0,002 (−0,4) | −0,009 (−1,3) |
| .min varejo sintético | 0,90 | −0,002 (−0,3) | −0,010 (−1,5) | −0,010 (−1,3) | **−0,018 (−2,2)** | 0,78 | **−0,019 (−3,1)** | 0,011 (1,7) | 0,006 (0,9) | 0,007 (1,1) |
| .min termo Inst sintético | 0,21 | 0,003 (0,4) | 0,002 (0,3) | 0,000 (0,1) | −0,003 (−0,5) | 0,35 | −0,013 (−1,9) | 0,003 (0,5) | 0,007 (1,0) | 0,004 (0,6) |
| Referência só preço: geometria × volume | 0,65 | 0,006 (0,8) | 0,013 (1,9) | 0,003 (0,5) | 0,002 (0,3) | 0,63 | **−0,050 (−7,2)** | 0,000 (0,1) | −0,001 (−0,1) | −0,001 (−0,2) |


#### Tabela 10.5 — Quantos testes passam de |t| ≥ 2 (IC parcial, 3 horizontes) contra o esperado por acaso
| Universo | Ativo | Testes | |t| ≥ 2 observados | Esperado por acaso (4,6%) |
| :-- | :-- | --: | --: | --: |
| TAPE (todos) | WIN | 129 | 8 | 5,9 |
| TAPE 2026 | WIN | 129 | 13 | 5,9 |
| MIN (todos) | WIN | 30 | 6 | 1,4 |
| MIN nos dias de tape | WIN | 30 | 4 | 1,4 |
| TAPE (todos) | WDO | 129 | 10 | 5,9 |
| TAPE 2026 | WDO | 129 | 14 | 5,9 |
| MIN (todos) | WDO | 30 | 1 | 1,4 |
| MIN nos dias de tape | WDO | 30 | 10 | 1,4 |


Leitura honesta:

- **A agressão de qualquer tipo é quase o próprio candle.** Agressão total × retorno da barra = 0,93 (WIN) e 0,77 (WDO). As faixas de lote ficam entre 0,65 e 0,86. Varejo agressor e UBS/BTG agressor ficam em 0,77–0,88. **Todo fluxo passivo tem sinal contrário ao candle** (varejo passivo −0,92, UBS/BTG passivo −0,90, absorção −0,66, renovação −0,79 no WIN). Ele é o outro lado da mesma agressão.
- **Depois de tirar o preço, quase nada sobra.** No tape há 8–10 testes com |t| ≥ 2 em 129 por ativo, contra ~6 esperados por acaso. No `.min` com 237 pregões, há 6 em 30 no WIN, mas todos com IC parcial **negativo** e pequeno (−0,015 a −0,022). Ou seja, agressão/Inst agressor sintético têm leve **reversão** depois do preço, e não continuação.
- **Candidatos que valem acompanhar (não são conclusão):**
  1. **Estrangeiro no WDO** (agressor e líquido): IC parcial +0,05 a +0,08 em t+1, t+3 e t+6, t 2,3–3,1, em 15 pregões. **Mas vem dos 11 pregões de 2025.** Nos 4 de 2026 fica em +0,03/−0,03 (t ≤ 0,6 em t+1; −2,2 em t+3 para o líquido).
  2. **HFT (Ideal) agressor no WIN**: +0,09 a +0,11 nos 7 pregões de 2026 (t 2,1–2,7), mas só +0,03 a +0,06 (t 0,8–1,5) com os 12.
  3. **Banco nacional passivo no WIN**: −0,05 a −0,06 (t −1,8 a −2,4). Os bancos compram passivamente antes da queda, o que parece "liquidez ferida", e não "smart money".
- **Lote grande não prevê nada.** As boletas > 100 e ≥ p99 têm IC parcial ≈ 0 nos dois ativos. A única faixa com |t| > 2 é **6–20 contratos no WIN em t+1** (+0,05, t 2,8), isolada e sem continuidade em t+3/t+6.
- **Absorção e renovação** também não mostram nada estável. Renovação no WIN tem −0,07 em t+3 (t −2,9), mas o sinal se inverte no WDO.

### 10.4 O `.min` sintético reproduz o tape?

#### Tabela 10.6 — O .min sintético reproduz o tape? (pregões com os dois: 7 WIN, 4 WDO)
| Par (tape × .min) | WIN corr por barra | WIN sinal igual | WIN corr do acumulado no dia | WDO corr por barra | WDO sinal igual | WDO corr do acumulado |
| :-- | --: | --: | --: | --: | --: | --: |
| agressão total (sanidade) | 1,00 | 100% | 1,00 | 1,00 | 100% | 1,00 |
| inst agressor (projeto) | 0,97 | 93% | 0,96 | 0,91 | 90% | 0,84 |
| inst passivo (projeto) | 0,43 | 68% | 0,88 | 0,39 | 64% | 0,38 |
| varejo agressor (projeto) | 0,91 | 89% | 0,90 | 0,67 | 75% | 0,40 |
| termo Inst da força | 0,02 | 50% | 0,41 | −0,83 | 19% | −0,84 |
| gringo líquido vs Inst sintético | 0,11 | 52% | 0,57 | −0,07 | 55% | −0,67 |
| gringo agressor vs inst agr sintético | 0,52 | 66% | 0,38 | 0,35 | 67% | −0,35 |
| gringo passivo vs inst pas sintético | 0,31 | 63% | 0,73 | 0,02 | 51% | −0,01 |
| varejo líquido vs varejo sintético | −0,05 | 57% | −0,26 | −0,32 | 39% | −0,67 |
| varejo agressor vs varejo sintético | 0,95 | 91% | 0,96 | 0,67 | 70% | 0,08 |
| boletas >= p90 vs minutos de lote grande | −0,19 | 42% | 0,30 | 0,13 | 57% | −0,17 |
| boletas >100 vs minutos de lote grande | −0,17 | 45% | 0,31 | 0,13 | 57% | −0,18 |
| porte (lote médio por lado) | 0,40 | 64% | 0,25 | 0,53 | 64% | 0,38 |
| contagem de boletas | 0,92 | 87% | 0,72 | 0,53 | 72% | 0,25 |
| contagem de negócios | 1,00 | 100% | 1,00 | 1,00 | 100% | 1,00 |
| absorção vs inst passivo sintético | 0,32 | 61% | 0,65 | 0,02 | 53% | −0,10 |
| renovação vs inst passivo sintético | 0,35 | 63% | 0,76 | 0,37 | 66% | 0,42 |


- O `.min` reproduz bem **o que é agressão** (Inst agressor 0,97/0,91, varejo agressor 0,91 no WIN, contagem). O motivo: a "decomposição" é só uma divisão da agressão por lote médio.
- O `.min` **não reproduz** o passivo institucional (0,43/0,39), o estrangeiro (0,11/−0,07), o varejo líquido (−0,05/−0,32), o lote grande (−0,19/0,13) nem a absorção (0,32/0,02).
- O **termo Inst da força de produção** (o sintético) tem correlação **0,02 no WIN e −0,83 no WDO** com o mesmo termo calculado no tape real pela própria regra do projeto. **O "institucional" da onda não é o institucional do tape.** No WDO ele chega a ter o sinal oposto, porque no tape o termo é dominado pelo passivo institucional real, que é contra o candle, e no sintético pelo agressor, que é a favor.

### 10.5 Nas estratégias — componentes do `.min` (backtest completo)

#### Backtest completo — componentes do .min (todos os pregões, jan–11/nov/2026)
| Variante | E22 Ret/DD (lucro R$) | V21 Ret/DD (R$) | SYM_WDO Ret/DD (R$) | V1a_WDO Ret/DD (R$) | C1a | SYM_WIN | Carteira Ret/DD (R$) | Carteira jan–jul / ago–nov |
| :-- | --: | --: | --: | --: | --: | --: | --: | :-- |
| A_BASE | **14,05** (9.214) | 11,63 (4.642) | 6,80 (4.350) | 7,62 (4.495) | 5,45 | 1,73 | **15,89** (20.612) | 9,33 / 10,46 |
| X_WYCKOFF | **12,31** (9.032) | 12,21 (5.203) | 3,37 (3.555) | 8,04 (4.020) | 4,38 | 1,73 | **11,84** (19.047) | 6,47 / 10,77 |
| E1_PLAC_GEOM | **10,61** (8.782) | 13,82 (5.113) | 2,36 (2.470) | 3,11 (1.600) | 2,76 | 0,76 | **9,49** (14.837) | 5,60 / 6,27 |
| B_PURO | **3,99** (4.112) | 3,67 (2.035) | 0,34 (365) | 1,87 (1.630) | 0,05 | -0,55 | **2,34** (5.698) | 0,58 / 3,73 |
| D_MIX | **7,08** (6.554) | 6,05 (3.428) | 6,24 (4.275) | 4,78 (3.250) | -0,15 | 0,02 | **9,49** (13.969) | 5,40 / 5,14 |
| M_NTRD | **2,69** (2.744) | 3,68 (1.886) | 0,16 (250) | 2,46 (1.205) | 0,74 | -0,23 | **1,28** (4.678) | 0,27 / 3,88 |
| M_LOTE | **4,96** (4.934) | 2,43 (1.652) | 1,93 (2.285) | 8,64 (4.535) | -0,32 | -0,02 | **6,10** (11.605) | 4,26 / 6,09 |
| M_EXC | **4,75** (5.520) | 3,00 (1.940) | 1,60 (1.685) | 4,44 (3.355) | -0,67 | -0,68 | **5,11** (9.059) | 3,38 / 1,73 |
| W_SEM_INST | **14,83** (9.610) | 10,63 (4.974) | 5,94 (4.250) | 9,58 (4.790) | 5,26 | 1,85 | **14,10** (21.246) | 8,20 / 9,78 |
| W_NTRD | **13,05** (9.240) | 12,50 (4.788) | 3,09 (2.475) | 5,54 (2.770) | 2,02 | 1,06 | **12,33** (16.562) | 6,79 / 9,45 |
| W_LOTE | **12,20** (9.322) | 10,20 (4.782) | 4,09 (3.460) | 8,25 (4.125) | 3,81 | 1,76 | **11,50** (19.073) | 6,84 / 7,65 |
| W_EXC | **10,81** (8.864) | 7,90 (4.605) | 5,06 (3.615) | 6,42 (4.525) | 6,56 | 1,75 | **11,57** (19.584) | 6,48 / 8,82 |
p95 do nulo (força base embaralhada no pregão), Ret/DD: E22 6,81, V21 6,32, C1a_BRK_WIN 1,42, SYM_DIV_WIN -0,12, V1a_DIV_WDO 6,02, SYM_DIV_WDO 4,26


- **Sem preço** (M_NTRD, M_LOTE, M_EXC): E22 Ret/DD 2,7–5,0 e carteira 1,3–6,1, no nível do nulo, igual ao B puro da seção 2. A exceção é V1a_WDO com M_LOTE (8,64 > base 7,62 > p95 do nulo 6,02). É uma estratégia só, o SYM_WDO do mesmo fluxo cai para 1,93, e é tratada como acaso.
- **Trocar o termo Inst** por contagem, lote grande ou excesso (W_*) piora levemente (E22 10,8–13,1; carteira 11,5–12,3). **Tirar o termo Inst por completo** (W_SEM_INST) deixa o E22 em 14,83 (base 14,05) e a carteira em 14,10 (base 15,89; SYM_WDO 6,80 → 5,94). O termo Inst atual quase não contribui. Nenhum componente do `.min` ocupa esse espaço melhor que ele.

### 10.6 Nas estratégias — componentes só de tape (nível de trade, pregões de tape)

Variantes híbridas: a força é a da base em todos os pregões, menos nos de tape completo. `H_*` troca só o termo Inst pelo componente do tape. `HP_*` usa **só** o componente como força nesses pregões, sem Wyckoff e sem Porte. `HP_AGR` é o controle (agressão total = "B puro").

#### Pregões com tape completo dentro do período das estratégias: WIN ['2026-01-05', '2026-04-13', '2026-04-14', '2026-08-11', '2026-11-11'] · WDO ['2026-03-30', '2026-06-29', '2026-10-28', '2026-10-29']
Fora desses pregões as variantes H_/HP_ são idênticas à base; tudo abaixo é só o efeito NOS pregões de tape.

| Variante | E22 N / R$ | V21 N / R$ | C1a N / R$ | SYM_WIN N / R$ | V1a_WDO N / R$ | SYM_WDO N / R$ | Soma R$ | Trades da base mantidos |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | --: | --: |
| A_BASE | 4 / -38 | 6 / -105 | 1 / 54 | 7 / 112 | 2 / 125 | 5 / 120 | 373 | 25/25 |
| H_PROJ | 4 / -38 | 6 / -105 | 1 / 54 | 7 / 112 | 2 / 125 | 5 / 120 | 373 | 25/25 |
| H_PLAYERS | 5 / 596 | 7 / 212 | 1 / 54 | 7 / 112 | 2 / 125 | 5 / 100 | 987 | 24/25 |
| H_GRINGO | 4 / -38 | 6 / -105 | 1 / 54 | 7 / 112 | 2 / 125 | 6 / 265 | 518 | 25/25 |
| H_HFT | 4 / -38 | 6 / -105 | 1 / 54 | 8 / 158 | 2 / 125 | 5 / 120 | 419 | 25/25 |
| H_LOTE | 4 / -38 | 6 / -105 | 1 / 54 | 8 / 158 | 2 / 125 | 6 / 265 | 564 | 25/25 |
| H_ABS | 4 / -38 | 6 / -105 | 1 / 54 | 7 / 112 | 2 / 125 | 6 / 200 | 453 | 25/25 |
| HP_AGR | 2 / -172 | 3 / -85 | 1 / 54 | 7 / -203 | 2 / 95 | 6 / 15 | -211 | 8/25 |
| HP_PROJ | 6 / 956 | 7 / 338 | 2 / -5 | 10 / 166 | 2 / 125 | 6 / 185 | 1.427 | 12/25 |
| HP_PLAYERS | 6 / 956 | 7 / 338 | 0 / 0 | 10 / 355 | 2 / 195 | 5 / 245 | 1.751 | 10/25 |
| HP_GRINGO | 5 / 508 | 6 / 255 | 3 / 49 | 9 / 204 | 1 / 215 | 5 / -40 | 936 | 9/25 |
| HP_HFT | 5 / -2 | 7 / -87 | 1 / -59 | 7 / 7 | 3 / 340 | 6 / 115 | 401 | 12/25 |
| HP_LOTE | 2 / -172 | 4 / 50 | 0 / 0 | 5 / -85 | 2 / -5 | 9 / 125 | -137 | 7/25 |
| HP_ABS | 5 / 702 | 6 / 211 | 0 / 0 | 8 / 263 | 2 / 125 | 6 / 185 | 1.275 | 12/25 |
| HP_VAREJO | 6 / 956 | 7 / 338 | 0 / 0 | 10 / 355 | 4 / 190 | 5 / 35 | 1.536 | 10/25 |
(Soma sem V21, que é pesquisa e se sobrepõe ao E22.)


#### Sinais dos motores nos pregões de tape (entrada na abertura seguinte, saída 12 barras, líquido de custo, pts)
| Variante | WIN v2.1 N / média | WIN v3.2 N / média | WIN divv2 N / média | WDO v2.1 | WDO v3.2 | WDO divv2 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| A_BASE | 47 / -174,8 | 38 / -214,7 | 85 / -33,1 | 49 / -2,57 | 24 / -0,06 | 67 / 0,83 |
| H_PROJ | 47 / -176,3 | 38 / -214,7 | 83 / -30,5 | 48 / -1,22 | 23 / 1,26 | 68 / 0,78 |
| H_PLAYERS | 47 / -168,4 | 39 / -173,7 | 81 / -33,3 | 47 / -1,20 | 23 / 1,26 | 67 / 0,31 |
| H_GRINGO | 49 / -166,5 | 38 / -214,7 | 85 / -33,1 | 49 / -1,57 | 23 / 0,74 | 65 / 0,63 |
| H_HFT | 47 / -171,3 | 38 / -214,7 | 85 / -33,1 | 49 / -1,76 | 24 / -0,06 | 69 / 0,80 |
| H_LOTE | 49 / -159,6 | 40 / -211,9 | 82 / -28,3 | 45 / -2,69 | 28 / -1,79 | 66 / 1,64 |
| H_ABS | 48 / -169,7 | 39 / -208,6 | 83 / -42,0 | 49 / -1,74 | 25 / 0,94 | 71 / 0,27 |
| HP_AGR | 45 / -217,4 | 37 / -231,1 | 77 / -24,5 | 46 / -0,80 | 22 / 0,32 | 60 / 1,90 |
| HP_PROJ | 55 / -26,5 | 41 / -122,2 | 86 / -13,4 | 58 / -0,37 | 28 / 2,45 | 67 / -1,14 |
| HP_PLAYERS | 58 / -93,5 | 44 / -155,6 | 84 / -58,5 | 53 / -0,59 | 30 / 0,43 | 61 / 0,66 |
| HP_GRINGO | 49 / -133,8 | 34 / -173,5 | 61 / -23,1 | 47 / 0,05 | 21 / 0,83 | 53 / 1,52 |
| HP_HFT | 49 / -160,0 | 35 / -187,7 | 75 / -12,1 | 47 / 0,11 | 30 / 2,62 | 63 / 1,34 |
| HP_LOTE | 48 / -182,1 | 34 / -214,6 | 74 / -15,7 | 40 / -0,97 | 21 / -2,36 | 55 / 1,03 |
| HP_ABS | 59 / -124,8 | 45 / -148,4 | 93 / -63,2 | 61 / -1,16 | 30 / 2,18 | 75 / -0,66 |
| HP_VAREJO | 59 / -110,4 | 45 / -172,4 | 87 / -67,5 | 61 / -0,26 | 27 / 2,81 | 72 / -1,33 |


#### Nulo dos pregões de tape (30 sementes: força HP_PROJ embaralhada dentro de cada pregão de tape)
| Variante | E22 R$ | SYM_WDO R$ | V1a_WDO R$ | Soma (sem V21) R$ | percentil da soma no nulo | sinais WIN média pts | percentil | sinais WDO média pts | percentil |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| A_BASE | -38 | 120 | 125 | 373 | 10% | -112.9 | 37% | -0.51 | 63% |
| HP_ABS | 702 | 185 | 125 | 1275 | 77% | -101.1 | 57% | -0.33 | 70% |
| HP_AGR | -172 | 15 | 95 | -211 | 0% | -127.2 | 13% | 0.66 | 90% |
| HP_GRINGO | 508 | -40 | 215 | 936 | 47% | -96.3 | 63% | 0.83 | 90% |
| HP_HFT | -2 | 115 | 340 | 401 | 10% | -96.3 | 63% | 1.20 | 100% |
| HP_LOTE | -172 | 125 | -5 | -137 | 0% | -110.2 | 40% | -0.28 | 70% |
| HP_PLAYERS | 956 | 245 | 195 | 1751 | 100% | -92.4 | 63% | 0.15 | 77% |
| HP_PROJ | 956 | 185 | 125 | 1427 | 93% | -41.9 | 90% | -0.19 | 73% |
| HP_VAREJO | 956 | 35 | 190 | 1536 | 93% | -105.5 | 53% | -0.22 | 73% |
| H_ABS | -38 | 200 | 125 | 453 | 10% | -116.3 | 33% | -0.30 | 70% |
| H_GRINGO | -38 | 265 | 125 | 518 | 13% | -111.2 | 40% | -0.14 | 73% |
| H_HFT | -38 | 120 | 125 | 419 | 10% | -111.9 | 40% | -0.23 | 73% |
| H_LOTE | -38 | 265 | 125 | 564 | 17% | -108.9 | 47% | -0.45 | 63% |
| H_PLAYERS | 596 | 100 | 125 | 987 | 52% | -104.1 | 57% | -0.05 | 73% |
| H_PROJ | -38 | 120 | 125 | 373 | 10% | -112.9 | 37% | 0.17 | 77% |
| **nulo** mediana [p5–p95] | 527 [-179–1005] | 40 | 190 | 984 [241–1512] | — | -106.6 [-142.2–-33.8] | — | -0.54 [-1.96–0.88] | — |

(Nos sinais do nulo, a média junta os três motores: v2.1, v3.2 e divv2.)

- Trocar só o termo Inst (H_*) quase não muda a onda (correlação ≥ 0,99 com a base), porque o Inst pesa pouco perto do Wyckoff. Os trades mal mudam.
- Com o componente puro (HP_*), várias variantes parecem melhores que a base (HP_PLAYERS +1.751 e HP_PROJ +1.427, contra +373). **Só que o nulo embaralhado dá mediana +984 (p5–p95: 241–1.512).** Nesses 9 pregões a base ficou no percentil 10 do nulo: foi um conjunto ruim para ela, e qualquer perturbação "melhora". Só o HP_PLAYERS passa do p95 (1 de 14 variantes testadas), o que é compatível com acaso. A agressão pura (HP_AGR) fica no fundo do nulo (percentil 0). Nos sinais dos motores, só o HP_HFT nos sinais do WDO passa do p95 do nulo (média +1,20 pt, contra p95 de +0,88), 1 de 28 comparações, compatível com acaso.
- Os pregões de 2025 (5 WIN + 11 WDO) não têm muralhas nem execução no dataset. Entram só no IC (10.3).

### 10.7 Quantos pregões de tape seriam precisos

#### Quantos pregões de tape seriam precisos
| Ativo | IC parcial alvo | Critério | Pregões necessários | (EP observado com N pregões) |
| :-- | --: | :-- | --: | :-- |
| WIN | 0,02 | t=2 (1 teste) | 78 | 0,026 com 12 |
| WIN | 0,02 | t=3,3 (Bonferroni ~45 componentes) | 213 | 0,026 com 12 |
| WIN | 0,03 | t=2 (1 teste) | 35 | 0,026 com 12 |
| WIN | 0,03 | t=3,3 (Bonferroni ~45 componentes) | 95 | 0,026 com 12 |
| WIN | 0,05 | t=2 (1 teste) | 13 | 0,026 com 12 |
| WIN | 0,05 | t=3,3 (Bonferroni ~45 componentes) | 34 | 0,026 com 12 |
| WDO | 0,02 | t=2 (1 teste) | 79 | 0,023 com 15 |
| WDO | 0,02 | t=3,3 (Bonferroni ~45 componentes) | 214 | 0,023 com 15 |
| WDO | 0,03 | t=2 (1 teste) | 35 | 0,023 com 15 |
| WDO | 0,03 | t=3,3 (Bonferroni ~45 componentes) | 95 | 0,023 com 15 |
| WDO | 0,05 | t=2 (1 teste) | 13 | 0,023 com 15 |
| WDO | 0,05 | t=3,3 (Bonferroni ~45 componentes) | 34 | 0,023 com 15 |
| E22 | — | Δ R$/trade = 25% de 37 (DP 224, 1,18 trades/pregão) | 4.056 | trades necessários 4.798 |
| E22 | — | Δ R$/trade = 50% de 37 (DP 224, 1,18 trades/pregão) | 1.014 | trades necessários 1.200 |
| SYM_DIV_WDO | — | Δ R$/trade = 25% de 14 (DP 99, 1,48 trades/pregão) | 4.412 | trades necessários 6.545 |
| SYM_DIV_WDO | — | Δ R$/trade = 50% de 14 (DP 99, 1,48 trades/pregão) | 1.103 | trades necessários 1.636 |
| V1a_DIV_WDO | — | Δ R$/trade = 25% de 24 (DP 105, 0,87 trades/pregão) | 2.726 | trades necessários 2.377 |
| V1a_DIV_WDO | — | Δ R$/trade = 50% de 24 (DP 105, 0,87 trades/pregão) | 681 | trades necessários 594 |

- Para confirmar um componente com IC parcial de 0,03 (o tamanho dos melhores candidatos), são precisos **~35 pregões de tape completos** se ele for **pré-registrado** (um teste). São **~95** se for escolhido entre ~45 componentes (Bonferroni). Para IC 0,02: ~80 / ~215.
- No nível de estratégia é inviável: detectar +50% de R$/trade no E22 exige ~1.000 pregões (~4 anos). A validação de fluxo de tape tem de ser feita **no nível de IC/sinal** com 1–3 componentes fixados antes, e não por backtest de estratégia.
- Hoje há 27 pregões completos em 16 meses. Gravando WIN + WDO todo dia, 35 pregões novos levam ~7 semanas.

### 10.8 Veredito

1. **Por player:** nenhum player carrega informação além do preço de forma estável. O único sinal com cara de real é o **estrangeiro no WDO** (IC parcial +0,05/+0,08, t até 3,1), mas ele vem de 2025 e não se repete nos 4 pregões de 2026. HFT agressor no WIN (2026) e banco nacional passivo (negativo) ficam como candidatos fracos.
2. **Por forma de apregoar:** agressor = candle e passivo = −candle. Depois do preço, nenhum dos dois prevê nada consistente. Absorção e renovação, com o proxy possível sem livro, também não.
3. **Por lote:** boleta grande não prevê o próximo movimento. Lote grande é a maior parte do volume, então é quase o mesmo que a agressão total. No `.min`, o "lote grande" não reproduz o do tape e não melhora estratégia nenhuma.
4. **O `.min` só reproduz a parte agressora.** O "Inst" da onda de produção não corresponde ao institucional real do tape (0,02 WIN, −0,83 WDO), e tirá-lo quase não muda os resultados. A conclusão da seção 9 continua de pé, agora com o fluxo aberto em pedaços: **a vantagem das estratégias está no preço (geometria do candle), não em quem agride nem no tamanho da boleta.**
5. **Próximo passo sugerido (só proposta, nada alterado):**
   - gravar o `.trd` completo de WIN e WDO todo dia;
   - pré-registrar **3 componentes**: estrangeiro líquido no WDO, HFT agressor no WIN e inst passivo do tape pela regra do projeto;
   - retestar o IC parcial com ~35–40 pregões novos, fora da amostra, antes de qualquer mudança em motor.

**Limites:**

- a classe é a da **corretora**, não a do cliente final (a XP roteia institucional; UBS/BTG são mistos);
- a boleta reconstruída por segundo pode juntar ordens diferentes;
- sem livro, não há como provar iceberg;
- os limiares de percentil usam o pool de todos os dias de tape (um olhar à frente, só no limiar);
- com 4–15 pregões, o próprio erro-padrão bootstrap é instável.

---

## Arquivos (todos novos, em `research/flow_ablation/`)

- `flows.py`: as variantes da onda, a decomposição M1 com pavio configurável e a paridade.
- `parity.py`: paridade do recálculo contra o `div_wall_v1` → `results/paridade.json`.
- `ablation.py <VARIANTE>`: roda todas as estratégias, motores, rótulos e dias de tape de uma variante → `results/var_<VARIANTE>.pkl` e `log_<VARIANTE>.txt`.
- `extra.py ref|null|retune`: referência M1 da carteira, nulo de 30 sementes (`results/nulo_embaralhado.csv`) e reajuste (`results/reajuste_grade.csv`).
- `report.py`: gera `results/tabelas.md`, `estrategias_por_variante.csv`, `carteira_por_variante.csv`, `evento_sinais.csv` e `rotulos.csv`.

- **Seção 10 (player / apregoação / lote):**
  - `tape_components.py`: inventário dos `.trd`, componentes M5 por pregão de tape. Gera `results/tape/inventario_trd.csv`, `comp_<ATIVO>_<data>.pkl` e `percentis_lote.json`.
  - `tape_shares.py`: participação por classe. Gera `results/tape/participacao_classes.csv`.
  - `component_ic.py`: correlação na barra, IC, IC parcial e reprodução pelo `.min`. Gera `results/ic_componentes.csv`, `reproducao_sintetico.csv`, `tape_m5_*.pkl`, `min_m5_*.pkl` e `min_p90_lote.json`.
  - `flows2.py` e `ablation2.py <VARIANTE>`: variantes M_/W_ (`.min`), H_/HP_ (tape) e HPS_<semente> (nulo), no mesmo harness. Geram `results/var_*.pkl`.
  - `report2.py`: gera `results/tabelas_componentes.md`, `componentes_min_backtest.csv`, `componentes_tape_trades.csv`, `componentes_tape_sinais.csv` e `poder_estatistico.csv`.
  - `null_tape.py`: gera `results/nulo_tape.md` e `.csv`.

Para reproduzir:

```
python research/flow_ablation/ablation.py A_BASE   (repetir para cada variante)
python research/flow_ablation/extra.py null
python research/flow_ablation/extra.py retune
python research/flow_ablation/report.py
python research/flow_ablation/tape_components.py
python research/flow_ablation/component_ic.py
python research/flow_ablation/ablation2.py M_LOTE   (idem M_NTRD, M_EXC, W_*, H_*, HP_*, HPS_1..30 com --skip-addon)
python research/flow_ablation/report2.py
python research/flow_ablation/null_tape.py
```
