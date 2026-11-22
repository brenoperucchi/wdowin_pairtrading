# Dólar e as Walls: respeito, ímã e operação (12/11/2026)

Os scripts são `teste.py` (respeito, ímã e "rumo à Wall") e `limite.py` (ordem limite na Wall). Os resultados estão em `results/ima.csv` e `results/limite.csv`.

O período é 02/01–11/11. Cada teste é comparado com um **placebo**: os mesmos níveis do dia, deslocados por 25–75% do espaçamento entre níveis, com 10 sorteios.

## 1. O dólar respeita as Walls: confirmado
No primeiro toque do dia, mede-se o que vem primeiro em 12 barras: a volta de k pts para o lado de origem ou o fechamento k pts além do nível.

| k (WDO) | Walls reais | Placebo (faixa) | jan–jul / ago–nov (reais) |
| --: | --: | :-- | :-- |
| 1,5 | 59,9% | 53,0% (50,2–55,8) | 59,9 / 60,0 |
| 2 | 59,0% | 53,3% (51,0–55,6) | 59,2 / 58,6 |
| 3 | 58,9% | 52,8% (49,4–55,7) | 59,3 / 58,1 |
| 6 | 58,1% | 53,2% (50,0–55,4) | 57,3 / 59,8 |

- **WDO:** fica acima de todos os placebos e é estável nos dois períodos.
- **WIN (k = 100):** 54,2% contra 52,2%, quase dentro da faixa do placebo. Ou seja, **o dólar respeita as Walls mais que o índice**.

## 2. Ímã: não existe
A chance de tocar o nível à frente em até 12 barras é igual à do placebo nas duas moedas. Por exemplo, no WDO com d ≤ 8 pts: 46,9% nas Walls contra 47,5% no placebo. A Wall não atrai o preço.

## 3. Operar a favor do movimento até a Wall: perde
Foram 24 variações com gatilho na barra ou na NWE50, stop de 3/5/7 e distância até a Wall entre 3 e 20 pts. O PF ficou entre 0,60 e 0,84, quase igual ao placebo. No WIN ficou entre 0,90 e 1,03, sem vantagem.

## 4. Ordem limite na própria Wall
Regra: no primeiro toque, ordem limite no nível a favor do respeito. Grade com alvo de 3/4/6/8, stop de 3/4/6/8, 12 ou 24 barras e 1 contrato.

| Preenchimento | PF (64 variações) | Melhor | ago–nov |
| :-- | :-- | :-- | :-- |
| **Ao tocar o nível** | 1,17 a 1,28 em todas; placebo ~0,95 | TP 6 / SL 4: 632 tr, PF 1,28, R$ 4.090, Ret/DD 3,3 | 0,82–1,04 (quase todas < 1) |
| **Na fila** (preço precisa passar 1 tick) | 0,87 a 0,99, todas negativas | — | 0,63–0,88 |

Em 56 das 64 variações, as Walls reais ficaram acima do **melhor** placebo. O efeito é real.

## 5. Filtro: o que separa os toques que seguram (`filtros.py`, `so_walls.py`)
Foram analisados 636 primeiros toques no dia. Cada característica é medida na barra anterior ao toque, com os terços definidos em jan–jul. Um filtro só vale se melhorar **os dois** períodos.

| Grupo | jan–jul: respeito · PF no toque · PF na fila | ago–nov: respeito · PF no toque · PF na fila |
| :-- | :-- | :-- |
| Todos | 58,7% · 1,50 · 1,09 | 56,3% · 0,98 · 0,83 |
| **Só Walls principais** | 59,3% · 1,60 · **1,28** | 59,0% · 1,24 · **1,10** |
| MidWall | 58,1% · 1,40 · 0,94 | 53,6% · 0,77 · 0,62 |
| Wall com largura ≥ 2 | 62,1% · 1,69 · 1,45 (66 toques) | 61,5% · 1,76 · 1,32 (26 toques) |
| Wall com NWE50 esticada do lado de onde o preço veio | 64,9% · 1,81 · 1,39 (74) | 60,7% · 1,47 · 1,59 (28) |

- **Características que mudam de sinal entre os períodos:** velocidade, fluxo, hora, lado e extremo do dia. Não servem como filtro.
- **Grade com só as Walls** (16 combinações de alvo e stop, um trade por vez):
  - **No toque:** PF mediano 1,33 (placebo 0,94). 10 de 16 combinações têm PF > 1 nos dois períodos. A melhor, TP 4 / SL 4, faz 318 tr, R$ 2.240 e Ret/DD 4,4.
  - **Na fila:** PF mediano 1,02 (placebo 0,81). **Nenhuma** combinação tem PF > 1 nos dois períodos. A melhor, TP 6 / SL 4, faz PF 1,11, R$ 775 e Ret/DD 0,6.
- **Subgrupos** (largura ≥ 2, NWE esticada): melhoram, mas somam cerca de 100 toques no ano e poucas centenas de reais. É pouco para confiar.

## 6. Execução com os negócios reais do Profit (`ticks.py`)
- **Dados:** só existem 6 pregões completos de `.trd` do WDO em 2026 (30/03, 29/06, 28/10, 29/10, 10/11 e 11/11), com 19 primeiros toques em níveis (Wall e MidWall).
- **Rompem 1 tick:** 17 dos 19 toques (89%) negociaram 1 tick além do nível. Neles, a ordem na fila é executada de qualquer jeito, e o resultado é o mesmo no toque e na fila.
- **Seguram exatamente no nível:** só 2 dos 19 (11%). Os dois foram alvo. No nível foram negociados 32 contratos (11/11, Wall de 5.600, às 09:15) e 381 contratos (10/11, MidWall de 5.575).
- **Bate com a simulação em M1:** lá, a fila deixa de executar 12% dos toques (556 contra 634).
- **De onde vem a diferença:** a diferença entre PF 1,3 (toque) e PF ~1,0 (fila) está toda nesses ~10% de toques que param exatamente na Wall. São os melhores trades: o preço vira ali mesmo.
- **Ser executado ou não depende da posição na fila.** Os `.trd` só têm os negócios, sem o livro de ofertas, então não dá para saber quantas ordens já estavam na frente num preço redondo como 5.600.
- **Faixa de resultado** (só Walls, alvo 6 / stop 4, um trade por vez):
  - nunca executado nesses casos: PF 1,11, R$ 775;
  - sempre executado: PF 1,38, R$ 2.670.

## Conclusão
- **O que existe:** as Walls do dólar seguram o preço de verdade (cerca de 6 pontos percentuais acima do acaso).
- **Por que não dá para operar sozinho:**
  - **Fila:** a vantagem só aparece se a ordem limite for executada exatamente no toque. Com a exigência realista de passar 1 tick, todas as variações perdem.
  - **Período:** mesmo no toque, ago–nov ficou abaixo de PF 1.
- **O filtro encontrado:** **Walls principais seguram, MidWalls não.** Só com as Walls, a ordem no toque fica positiva nos dois períodos.
- **Fila:** com a fila realista, a vantagem cai para o empate (PF ~1,0–1,1). Ainda não é uma estratégia.
- **O que decide:** a execução nos ~10% de toques que param exatamente na Wall. Os negócios reais confirmam o mecanismo, mas não a posição na fila, porque não há histórico do livro de ofertas.
- **Para fechar a dúvida:** só operando, ou gravando o livro de ofertas nas Walls ao vivo. Simulador e conta demo executam no toque e repetiriam o resultado otimista.
