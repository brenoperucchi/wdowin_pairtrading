# Motor de divergência v2.1 — resultados da detecção (11/11/2026)

Pesquisa em `research/div_master/engine_v2_1/`. Não altera `core/`, o painel 5176, nem `labels.csv`. Sem backtest de P&L (próxima fase).

Os parâmetros foram escolhidos no **treino** (6 pregões: 11/11, 02/09, 06/02, 01/14, 03/20, 06/23) e reportados no **hold-out** (02/20, 04/07, 07/13) e em **leave-one-session-out**.

## 1. O que ele rotulou

Estado final de `labels.csv` (última LABEL vale; 1 UNDO aplicado). 9 pregões, 112 linhas, 3 adições manuais.

| Pregão | Válidas (pré) | Falsas (pré) | Manuais | Sem rótulo (pré) | Válidas por tipo (inclui manual) |
| --- | ---: | ---: | ---: | ---: | --- |
| 2026-11-11 | 5 | 9 | 0 | 1 (`_12`) | 2 rejeição compra, 2 absorção venda, 1 rejeição venda |
| 2026-02-09 | 6 | 11 | 1 válida rejeição venda 09:35→11:45 | 2 (`_16`, `_17`) | 3 rejeição compra, 3 rejeição venda, 1 absorção compra |
| 2026-02-20 | 8 | 2 | 0 | 1 (`_09`) | 4 rejeição compra, 3 rejeição venda, 1 rompimento compra |
| 2026-03-20 | 3 | 8 | 1 válida absorção compra 11:20→15:20 | 0 | 1 rejeição venda, 1 rompimento venda, 2 absorção compra |
| 2026-04-07 | 4 | 6 | 1 válida absorção venda 11:45→14:35 | 1 (`_10`) | 2 absorção compra, 1 rejeição venda, 1 absorção venda, 1 rompimento venda |
| 2026-06-02 | 6 | 5 | 0 | 0 | 3 rejeição venda, 2 absorção venda, 1 absorção compra |
| 2026-06-23 | 7 | 4 | 0 | 0 | 1 absorção compra, 4 rejeição venda, 1 rompimento compra, 1 rompimento venda |
| 2026-07-13 | 6 | 5 | 0 | 0 | 1 rompimento compra, 1 rompimento venda, 3 absorção compra, 1 rejeição venda |
| 2026-01-14 | 4 | 3 | 0 | 0 | 1 absorção venda, 1 absorção compra, 1 rompimento compra, 1 rejeição venda |
| **Total** | **49** | **53** | **3 válidas** | **4** | **52 válidas no total: 44 divergências (27 rejeição + 17 absorção) e 8 rompimentos** |

O gabarito da avaliação do motor de **divergência** são as 44 válidas com tipo rejeição ou absorção (incluindo as 3 manuais). Os 8 rompimentos válidos ficam de fora desta métrica.

## 2. O que distingue as divergências válidas

### Hipótese A — “às vezes o motor antigo pega topo/fundo pouco evidente”

**Confirmada em parte, com um matiz.**

- 97,7% (43/44) das F2 válidas são pivôs de um zigzag com reversão de 150 pts; 90,9% ainda são pivôs com reversão de 1,2×ATR(14). O gerador antigo (união de detectores + L1/R1) também marcava oscilações menores.
- O discriminante mais claro **não** é a “proeminência bruta” à esquerda (quase todo extremo do dia tem isso), e sim o **tamanho local do swing em ATR e o espaço F1–F2**:
  - válidas: mediana de 4 barras entre F1 e F2 (p75 = 6); swing mediano ≈ 5,0×ATR; 90,9% com swing ≥ 1,5×ATR
  - falsas (candidatos DIV): mediana de 12 barras; 71,8% com swing ≥ 1,5×ATR
- Ou seja: o que ele rejeita com frequência é o **pareamento longo / leque** e o pivô miúdo, não qualquer extremo do dia.
- Matiz: no começo do pregão ele às vezes valida um fundo *pouco* evidente se estiver colado na Wall (exemplo: 11/11, 09:00→09:15 no MidWall, com mínima mais funda logo em seguida). O v2.1, ao exigir pivô evidente, perde esse caso de propósito.

### Hipótese B — “é preciso buscar divergência também em nova máxima/mínima do dia”

**Confirmada como âncora de recall, não como filtro de precisão.**

- 61,4% das divergências válidas têm F2 = nova máxima/mínima causal do pregão; 61,4% estão a ≤150 pts de Wall/MidWall; a união cobre **86,4%** (38/44).
- 11/44 (25%) são só extrema do dia, fora da zona de 150 — sem essa âncora o motor perderia a perna 10:25–10:40 de 11/11 (193 pts da Wall, máxima do dia) e várias rejeições que ele marcou válidas (06/02 11:40, 06/23 13:30, 02/20 várias, etc.).
- 6/44 (13,6%) não são nem extrema do dia nem zona 150. Duas são manuais longas e longe da Wall (02/09 09:35→11:45, +471 pts; 04/07 11:45→14:35, −342 pts). As outras são correções no meio do dia (11/11 12:50→13:10, 02/09 13:00 e 15:20, 02/20 16:40).
- O mesmo critério `day_ext OU wall` também cobre 87,2% das **falsas** DIV: serve para não perder evento, não para separar válido de falso. A separação fica por conta do pivô evidente + divergência de onda + um F1 por pivô.

A onda confirma a leitura de divergência (97,7% das válidas com F1 têm `wave(F2)−wave(F1)` no sentido certo; mediana ~17 mil da fórmula do fluxo), mas as falsas também (94,6%). Só a onda não basta.

## 3. A regra do v2.1 (causal)

Parâmetros, todos interpretáveis:

| Parâmetro | Valor | Significado |
| --- | --- | --- |
| Reversão do zigzag | 1,2 × ATR(14) causal (mínimo 80 pts) | “Pivô evidente”: o topo/fundo só existe quando o preço reverte pelo menos isso. Sinal no **fechamento da barra que confirma** a reversão. |
| Elegibilidade do F2 | nova máx./mín. do pregão **ou** ≤150 pts de Wall/MidWall | Âncora que ele pediu; MidWall conta como Wall |
| F1 | pivô zigzag anterior do mesmo lado, até 48 barras (~4 h) | Sem leque: cada pivô é F1 no máximo uma vez |
| Estrutura de preço | tolerância 60 pts | Compra: F2 não muito acima do F1; venda: F2 não muito abaixo |
| Fluxo | divergência de onda > 0,15 × mediana causal \|onda\| | A onda não confirma o movimento de preço |

Implementação: `detect.py`. O sinal nunca lê barra posterior à confirmação.

## 4. Qualidade da detecção

Cem por cento das métricas abaixo são **recall/precision de evento**, não P&L. Um acerto = mesmo lado e F2 a no máximo 2 barras do rótulo válido. Precisão “revisada” considera só os falsos positivos que coincidem com algo que ele já marcou falso; o restante são detecções novas, **não revisadas** (o gabarito não cobre o pregão inteiro).

### 4.1 v2.1 no treino, hold-out e no total

| Recorte | Recall | Precisão | F1 | TP | FP | FN | Manuais | Precisão revisada |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Treino (6 pregões) | 79,3% | 40,4% | 0,54 | 23 | 34 | 6 | 2/2 | 67,6% |
| Hold-out (3 pregões) | 60,0% | 34,6% | 0,44 | 9 | 17 | 6 | 0/1 | 56,2% |
| 9 pregões | 72,7% | 38,6% | 0,50 | 32 | 51 | 12 | 2/3 | 64,0% |
| Média LOSO | 74,9% | 39,8% | — | — | — | — | — | — |

O hold-out cai em relação ao treino (60% vs 79% de recall). Não é um colapso, mas o conjunto é pequeno: um manual longe da Wall e dois pivôs pouco evidentes no hold-out pesam.

### 4.2 Por pregão (v2.1)

| Pregão | GT | Det | TP | FP | FN | Rec | Prec |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-01-14 | 3 | 9 | 3 | 6 | 0 | 1,00 | 0,33 |
| 2026-02-09 | 7 | 6 | 3 | 3 | 4 | 0,43 | 0,50 |
| 2026-02-20 | 7 | 10 | 5 | 5 | 2 | 0,71 | 0,50 |
| 2026-03-20 | 3 | 10 | 3 | 7 | 0 | 1,00 | 0,30 |
| 2026-04-07 | 4 | 6 | 2 | 4 | 2 | 0,50 | 0,33 |
| 2026-06-02 | 6 | 13 | 6 | 7 | 0 | 1,00 | 0,46 |
| 2026-06-23 | 5 | 14 | 5 | 9 | 0 | 1,00 | 0,36 |
| 2026-07-13 | 4 | 10 | 2 | 8 | 2 | 0,50 | 0,20 |
| 2026-11-11 | 5 | 5 | 3 | 2 | 2 | 0,60 | 0,60 |

### 4.3 v2.1 contra os motores antigos

No recorte jan–jul rotulado (8 pregões, sem 11/11, 39 divergências válidas):

| Motor | Recall | Precisão | F1 | TP | FP | FN | Manuais | Precisão revisada |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A causal (`swing_divergence` sem lookahead) | 53,8% | 32,8% | 0,41 | 21 | 43 | 18 | 0/3 | 63,6% |
| B visual (`detect_visual_swing_divergences`) | 43,6% | 29,8% | 0,35 | 17 | 40 | 22 | 0/3 | 58,6% |
| **v2.1** (mesmo recorte) | **74,4%** | **37,2%** | **0,50** | 29 | 49 | 10 | 2/3 | 63,0% |
| Gerador da rotulagem (união + teto 11, só DIV; 9 pregões) | 93,2% | 51,2% | 0,66 | 41 | 39 | 3 | — | 52,6% |

O gerador da rotulagem não é um motor operacional: foi desenhado para **mostrar muito**, com teto de 11 por dia, para ele julgar. O recall alto (41/44) é o esperado; os 3 que faltam são essencialmente eventos que ele teve de marcar à mão. O v2.1 não tenta repetir essa união. Comparado com A e B (os detectores “de verdade”), o v2.1 **ganha recall com precisão igual ou um pouco melhor**.

### 4.4 Gabarito de 11/11

| Evento | v2.1 |
| --- | --- |
| E1 compra 09:00→09:15, MidWall (−17 pts) | **Perdido** — o fundo das 09:15 não é pivô evidente (09:00 e 09:25–09:35 foram mais fundos; o ATR da abertura é largo) |
| E2 rompimento Wall 173902, aceite 10:10 | Fora do escopo (rompimento, não divergência) |
| E3a venda 10:25→10:40, Wall 174913, 193 pts | **Ok** (F2 confirmado às 10:45, máxima do dia) |
| E3b venda 11:10→11:25, Wall 174913 | **Ok** (máxima do dia e na zona) |
| E4 venda 12:00→12:20, Wall 174913 | **Ok** (F2 12:20, máxima do dia) |
| Extra 12:50→13:10, rejeição compra que ele virou de direção | **Perdido** — fora da zona 150 e não é mínima do dia; a onda quase não diverge (−1,1 mil) |

## 5. Erros notáveis do v2.1 (12 FN)

Fora da âncora (nem máxima/mínima do dia, nem 150 da Wall) — 5 casos:

- 02/09 `_07` 12:30→13:00, 429 pts da Wall
- 02/09 `_13` 14:55→15:20, 217 pts
- 02/20 `_10` 16:30→16:40, pivô pouco evidente (0 barras à esquerda)
- 04/07 **manual** 11:45→14:35, 342 pts da Wall, 34 barras
- 11/11 `_11` 12:50→13:10 (ver acima)

Pivô não passa no zigzag 1,2×ATR — 5 casos:

- 11/11 `_01` 09:00→09:15 (E1, abertura)
- 02/20 `_01` 09:30→09:45 (também cedo)
- 04/07 `_09` 16:20→17:00
- 07/13 `_05` 12:30→12:45, só 2 barras à esquerda (mesmo na Wall)
- 07/13 `_11` 15:55→17:50, mínima do dia no fim do pregão — **não há barra seguinte para confirmar** a reversão (limite causal)

Elegível mas não casou F1/onda — 2 casos no 02/09 (`_10` sem F1 no rótulo; `_12` 14:40→14:55, 2 pts da Wall).

Manuais: 2 de 3 recuperados (02/09 09:35→11:45 não é extrema do dia e está a 471 pts — não entra na regra; 03/20 11:20→15:20 sim, mínima do dia colada na Wall; 04/07 11:45→14:35 não).

## 6. Como ver no rotulador

Servidor em `http://127.0.0.1:5180/?engine=v2.1` (ou o botão **Motor v2.1** no cabeçalho).

- Linhas **tracejadas ciano** (compra) / **laranja** (venda): detecções do v2.1, com `v1`, `v2`, … na barra de confirmação
- Sólido **verde-claro / cinza**: o que ele já marcou válida / falsa
- **Roxo (M)**: marcação manual

A rotulagem normal (`http://127.0.0.1:5180/`) permanece igual. Nada foi escrito em `labels.csv`.

## 7. Limitações e próximo passo

- Gabarito incompleto: ele só julgou os candidatos apresentados (e 3 manuais). Parte dos 51 FP do v2.1 nunca foi vista (33 “não revisados”); a precisão bruta (39%) subestima o motor se alguns desses forem divergências reais, e a precisão revisada (64%) é o teto otimista no que ele já julgou.
- Nove pregões é pouco; o recuo no hold-out pede cautela antes de congelar parâmetros.
- Rompimentos são outro setup e não entram neste motor.
- Próxima fase, se ele quiser: estudo de evento e backtest (IS jan–jul, custos, sem lookahead), com estas regras congeladas — não otimizar de novo no P&L.
