# Resultados — motor único, ordens em níveis e rompimentos (12/11/2026)

Plano: [`PLANO_UNIFICACAO_ROMPIMENTO_LIMITE.md`](PLANO_UNIFICACAO_ROMPIMENTO_LIMITE.md).

Decisões do usuário:
- deslocamentos como propostos;
- motor escolhido depois da tabela;
- sem rotulagem nova;
- critério da Frente 1 aprovado.

Condições de todos os testes:
- período 02/01–06/11/2026;
- execução tick a tick em M1;
- custo de 10 pts / 0,5 pt e 1 tick de slippage no stop;
- DD trade a trade.

Ago–nov já foi muito usado; nada aqui é fora da amostra.

Scripts e saídas:
- `frente1/motores.py` → `frente1/results/`
- `frente3/ordens.py` → `frente3/results/`
- `frente2/rompimento.py` → `frente2/results/`

---

## Frente 1 — Um motor só de divergência

**Base reproduzida exatamente:** o Sniper atual (detector B do cache, janela de 2 barras) dá 287 trades, R$ 7.436, DD R$ 524 e Ret/DD 14,2.

### A. Sniper com cada motor

Pool, gate, saídas, horários e meta iguais aos do Sniper atual.

**Mesma janela do Sniper atual** (2 barras, na confirmação, sem âncora):

| Motor | Trades | PF | Lucro | DD | Ret/DD |
| :-- | --: | --: | --: | --: | --: |
| B (cache, atual) | 287 | 1,95 | R$ 7.436 | R$ 524 | 14,2 |
| B (dataset) | 284 | 2,00 | R$ 7.687 | R$ 480 | 16,0 |
| v3 | 250 | 1,79 | R$ 5.956 | R$ 1.094 | 5,4 |
| **v2.1** | **401** | **1,77** | **R$ 9.415** | **R$ 586** | **16,1** |
| v3.1 | 306 | 1,75 | R$ 7.397 | R$ 752 | 9,8 |

**Em todas as 15 variações de momento × janela × âncora** (Ret/DD):

| Motor | mediana | mín. | máx. |
| :-- | --: | --: | --: |
| **v2.1** | **14,7** | 7,1 | 20,0 |
| B (dataset) | 12,0 | 4,6 | 16,0 |
| v3.1 | 9,7 | 3,6 | 12,0 |
| v3 | 6,4 | 3,1 | 8,5 |

**O Sniper com o `v2.1` não piora; fica igual ou melhor** em quase todas as janelas. O medo de que o `v2.1` derrubasse o Sniper, como o `v3` derrubou, não se confirmou.

### B. Especialista com cada motor

Regra congelada; muda só o motor.

| Motor | Trades | PF | Ret/DD | PF jan–abr / mai–jul / ago–nov |
| :-- | --: | --: | --: | :-- |
| B | 203 | 1,43 | 1,4 | 0,88 / 0,77 / 3,59 |
| v3 | 285 | 1,08 | 0,4 | 0,86 / 0,95 / 1,43 |
| **v2.1** | 319 | 1,77 | **11,8** | 1,43 / 1,70 / 2,38 |
| **v3.1** | 239 | 1,94 | **11,6** | 1,89 / 1,77 / 2,16 |

### C. Carteira com o mesmo motor nas duas estratégias

A configuração do Sniper para cada motor foi escolhida pelo critério (PF > 1,3 nas três partes; maior Ret/DD em jan–jul).

| Motor | Config. do Sniper | Passa no critério? | Trades | Lucro | DD | Ret/DD completo | **Ret/DD jan–jul** | Meses + |
| :-- | :-- | :-- | --: | --: | --: | --: | --: | :-: |
| B | conf · âncora · 2 barras | não (especialista) | 444 | R$ 10.189 | R$ 841 | 12,1 | 4,2 | 10/11 |
| v3 | trig · âncora · 3 barras | não (especialista) | 525 | R$ 5.777 | R$ 1.233 | 4,7 | — | 8/11 |
| **v2.1** | gatilho · âncora · ativo 6 | **sim** | 610 | **R$ 18.856** | R$ 1.103 | 17,1 | 11,2 | 11/11 |
| **v3.1** | conf · âncora · ativo 6 | **sim** | 568 | R$ 16.572 | **R$ 937** | **17,7** | **13,8** | 11/11 |

A carteira de hoje usa dois motores (Sniper com B + especialista com `v2.1`): R$ 16.842, DD R$ 1.106, Ret/DD 15,2.

**Pela regra fixada, vence o `v3.1`** (13,8 contra 11,2 em jan–jul, diferença maior que 10%). Mas o `v2.1`:
- é mais estável no Sniper (mediana 14,7 contra 9,7 nas 15 variações);
- dá mais lucro (R$ 18,9 mil contra R$ 16,6 mil);
- tem cobertura medida dos seus rótulos (74%). A do `v3.1` não foi medida.

Além disso, o `v3.1` tem mais parâmetros e foi desenhado olhando os mesmos pregões rotulados.

A escolha é sua (decisão 2c). Os dois são defensáveis, e ambos ficam acima da carteira atual.

**Cobertura dos rótulos** (medida em 12/11, 9 pregões, 44 divergências válidas, com a mesma âncora para os dois):

| Motor | Cobertura | Precisão (revisada) | Cobertura no hold-out | Sinais por pregão |
| :-- | --: | :-- | --: | --: |
| v2.1 | **72,7%** | 33,7% (61,5%) | 53,3% | 10,6 |
| v3.1 | 56,8% | 32,5% (62,5%) | 46,7% | 8,6 |

O `v3.1` pega as divergências da abertura que o `v2.1` perde, mas as regras de reset e repetição cortam divergências seguidas que você marcou como válidas. No saldo, ele concorda **menos** com os seus rótulos.

**Visualização no painel 5176:** o seletor "📐 Div.: Atual | V2.1 | V3.1 | Nenhuma" desenha as divergências do motor escolhido, independente dos trades. Arquivos:
- `core/div_engines_view.py`;
- rota `POST /api/compass/divergencias_motor` no `server.py`;
- `IntradayCompassPanel.jsx`.

---

## Frente 3 — Ordens limite / stop ancoradas em níveis

### Especialista (`ESP_DIV_V21_WIN`)

A referência a mercado reproduz exatamente a regra: 319 trades, R$ 9.406, Ret/DD 11,8. Foram testadas 600 configurações:
- 8 níveis: barra, pivô, Wall, MidWall, centro e banda da NWE50, banda da NWE30, confluência;
- limite (com execução "passou 1 tick" e "tocou") e stop;
- 5 deslocamentos, 3 validades e 2 posições de stop.

| Entrada | Execução | Trades | PF | Ret/DD | Platô |
| :-- | --: | --: | --: | --: | --: |
| **Mercado (atual)** | 100% | 319 | 1,77 | **11,8** | — |
| Limite na mínima da barra, "tocou", 6 barras | 58% | 190 | 1,90 | 6,0 | 6,0 |
| Limite na mínima da barra, stop atrás do nível | 33% | 110 | 1,75 | 4,4 | 6,1 |
| Stop na máxima da barra, 6 barras | 85% | 276 | 1,47 | 3,9 | 3,7 |
| Stop na banda NWE30 +30, 6 barras | 42% | 140 | 1,68 | 4,6 | 3,4 |
| Limite no centro da NWE50 | 37% | 126 | 1,63 | 3,2 | 3,0 |

Wall, MidWall, pivô e confluência não tiveram nenhuma configuração válida (≥ 100 trades e PF > 1 nos três períodos).

**Seleção adversa medida.** Na melhor ordem limite, os sinais que executam têm resultado médio, a mercado, de **−R$ 42**. Os que ficam de fora têm **+R$ 58 a +R$ 117**. A limite pega quem volta (os perdedores) e perde quem sai direto (os vencedores). Com a ordem stop acontece o contrário (+R$ 44 executados contra −R$ 79 perdidos), mas o preço pior come a vantagem.

**O nível como filtro, com entrada a mercado, também piora:**
- resistência a ≥ 150 pts: Ret/DD 7,6;
- suporte entre a entrada e o stop: 2,2 a 6,3;
- "testa o suporte e fecha a favor": 2,4 a 3,2.

**Conclusão:** para o especialista, **a mercado é a melhor entrada**. As ordens em níveis não melhoram e os filtros por nível também não.

### Sniper — **não concluído**

O teste no Sniper com o meu simulador não é válido, por dois motivos:
1. **WDO:** o Sniper usa a saída nativa de cada setup. Com o preço de entrada do próprio setup, a minha réplica dá R$ 720 (PF 1,22) contra R$ 4.360 (PF 2,11) do original. A diferença está na saída, não na entrada.
2. **WIN:** **22 dos 123 trades** do Sniper WIN têm o preço de entrada **fora da faixa da barra MT5** do horário da entrada, a 10–140 pts (mediana 58). Esses 22 somam R$ 304 dos R$ 3.281 do Sniper WIN. Ou a ordem pendente do setup executou em outra barra, ou o pool de setups usa uma série de preço diferente da MT5 `WIN$N`, em que a saída é simulada. **Isso precisa ser auditado à parte:** o resultado do Sniper WIN depende de o preço de entrada existir naquela barra.

Para testar ordens em níveis no Sniper, a mudança tem de ser feita dentro dos simuladores de cada setup (`core/setups_runner`), que têm a lógica própria de ordem e saída.

---

## Frente 2 — Rompimentos (sem rotulagem nova)

Hipóteses testadas (detalhe em `frente2/rompimento.py`):
- **R0:** cruzamento simples (controle);
- **R1:** aceitação depois do reteste, a sua regra de 11/11;
- **R2:** R1 + divergência oculta no reteste;
- **R3:** rompimento com a onda no maior valor do dia;
- **R4:** falha de rompimento + divergência `v2.1`, operada ao contrário.

**Estudo de evento** (retorno em 12 barras, líquido de custo):

| Hipótese | WIN jan–abr / mai–jul / ago–nov (pts) | WDO jan–abr / mai–jul / ago–nov (pts) |
| :-- | :-- | :-- |
| R0 cruzamento | +2 / +10 / +72 | −0,7 / −1,5 / −0,6 |
| **R1 aceitação após reteste** | **−42 / −43 / −6** | −0,3 / −0,4 / −0,8 |
| R2 R1 + oculta | −38 / −47 / −32 | −1,0 / −0,9 / −1,8 |
| R3 onda no máximo do dia | −100 / −15 / +208 | +0,3 / −1,4 / −3,4 |
| R4 falha + divergência | +49 / −8 / −8 | +0,5 / −1,2 / −2,4 |

**Backtest:** 288 configurações (2 ativos × 5 hipóteses × parâmetros × 6 saídas, um trade por vez). **Só uma passa** (≥ 100 trades, PF > 1 nos três períodos): WIN R4, sem alvo, 12 barras, com 281 trades, PF 1,12 e Ret/DD 0,9. O PF mediano por hipótese fica entre 0,59 e 0,92.

**Conclusão:** nenhuma das formas de rompimento tem vantagem.
- A aceitação depois do reteste é a pior no WIN em jan–jul: o preço que volta e é "aceito" de novo tende a falhar.
- A única que sobra (R4) é, na prática, uma reversão com divergência, a mesma família do especialista, e é fraca.
- Rompimento não entra na carteira.

---

## Resumo

1. **Motor único:** dá para unificar sem perder nada. Com `v2.1` ou `v3.1` nas duas estratégias, a carteira sobe de Ret/DD 15,2 (hoje, dois motores) para 17,1–17,7.
   - Pelo critério fixado vence o `v3.1`.
   - O `v2.1` é mais estável no Sniper e dá mais lucro.
   - Decisão sua.
2. **Ordens em níveis:** no especialista, entrar a mercado é melhor que qualquer ordem limite ou stop em nível, por seleção adversa medida. No Sniper o teste ficou pendente, e apareceu um ponto de auditoria: preço de entrada do WIN fora da barra MT5 em 22 de 123 trades.
3. **Rompimento:** nenhuma hipótese tem vantagem.
