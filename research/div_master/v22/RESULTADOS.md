# Motor v2.2 = v2.1 + módulo de abertura (12/11/2026)

**Pedido:** um v2.1 que traga mais divergências às 9h, sem as travas do v3.1 (reset e repetição), que derrubaram a concordância com os rótulos.

Script: `teste.py`. Saídas em `results/`: `variantes.csv`, `trades.json`, `placebo_9h.json`. Log: `run.log`.

Condições: período de 02/01 a 06/11/2026; execução em M1; custo de 10 pts / 0,5 pt e 1 tick de slippage no stop. Foram 9 variantes testadas no período completo, então nada aqui é fora da amostra.

## O que o v2.2 faz

Mantém todas as regras de pareamento do v2.1:
- F1 = pivô anterior mais recente que passa;
- cada F1 usado uma vez;
- onda da própria barra;
- limiar 0,15 × mediana;
- sem reset e sem regra de repetição.

O "módulo de abertura" só acrescenta pivôs:
- **A (semente):** a barra das 09:00 e o primeiro pivô L1/R1 até 09:20 podem ser F1.
- **B8 / B6:** um ZigZag com reversão menor (0,8 ou 0,6 × ATR14), valendo só para pivôs confirmados até 09:35 (ou 10:00).
- **C:** pivô de 3 barras com o candle de confirmação a favor, até 09:35.

**Verificações:**
- sem módulo, o v2.2 é **idêntico** ao v2.1 (10.201 divergências comparadas, zero diferença);
- todas as variantes passam no teste de paridade (lote × barra a barra, causal).

## Resultados

| Variante | Cobertura dos rótulos | Abertura rotulada (3) | WIN: divergências às 9h por dia | Especialista Ret/DD (≥ 10:00 / com 9h) | Sniper Ret/DD (janela 2) | **Carteira Ret/DD (jan–jul)** |
| :-- | --: | --: | --: | :-- | --: | :-- |
| v2.1 (referência) | 72,7% | 1 | 0,14 | 11,8 / 10,6 | 16,1 | 19,1 (11,2) |
| A semente | 72,7% | 1 | 0,40 | 9,7 / 8,3 | 16,9 | — |
| B8 | 72,7% | 1 | 0,33 | 8,3 / 6,5 | 19,9 | — |
| B6 | 72,7% | 1 | 0,46 | 5,4 / 4,1 | 25,1 | 29,1 (19,4) · especialista com PF 1,22 em jan–abr: **reprovado** |
| C | 72,7% | 1 | 0,20 | 10,9 / 9,9 | 16,9 | 19,6 (12,0) |
| A+B8 | 75,0% | 2 | 0,55 | 10,4 / 6,9 | 20,2 | 20,3 (13,0) |
| A+C | 75,0% | 2 | 0,47 | 7,8 / 5,8 | 17,1 | — |
| A+B8+C | 75,0% | 2 | 0,59 | 8,0 / 5,3 | 20,8 | — |
| **A+B8 até 10:00** | **77,3%** | **3** | **0,74** | 9,9 / 6,1 | **23,5** | **23,9 (15,9)** |

Carteira = Sniper com a janela atual (2 barras, na confirmação) + especialista (2 contratos, sem entradas antes das 10:00), os dois com o mesmo motor.

Para comparação, a mesma conta com o v3.1 dá 17,7 (13,8 em jan–jul).

### As 9h como entrada direta: perdem

Retorno em 12 barras, líquido, das entradas do especialista abertas na abertura seguinte a um gatilho às 9h:

| | jan–abr | mai–jul | ago–nov |
| :-- | --: | --: | --: |
| WIN, qualquer barra das 9h (placebo) | −10 | −10 | −10 |
| WIN, divergências às 9h, A+B8 até 10:00 | **−217** | **−237** | **−220** |
| WIN, divergências às 9h, demais variantes | −80 a −310 | | |
| WDO, divergências às 9h | ≈ 0 | | |

Divergência na abertura do WIN como gatilho de entrada **é pior que o acaso** nos três períodos. Por isso o especialista continua **sem entradas antes das 10:00**: liberar as 9h piora o resultado em todas as variantes.

### As 9h como filtro do Sniper: ajudam

Trades do Sniper (janela 2) com entrada antes das 10:00:

| Motor | Trades | PF | R$ | jan–abr / mai–jul / ago–nov |
| :-- | --: | --: | --: | :-- |
| v2.1 | 8 | 1,11 | 47 | −334 / +291 / +90 |
| **v2.2 A+B8 até 10:00** | **61** | **1,67** | **1.236** | +693 / +645 / −102 |

Além disso, os pivôs da abertura viram F1 de divergências mais tarde. O Sniper depois das 10h também melhora: 437 trades e R$ 11.742, contra 393 trades e R$ 9.368 no v2.1.

## Escolha: `V22_ABERTURA` = semente 09:00 + ZigZag 0,8 × ATR até 10:00

Pelo critério da Frente 1:
- PF > 1,3 nas três partes: especialista 1,47 / 1,95 / 2,16; Sniper 1,94 / 1,86 / 1,84;
- maior Ret/DD da carteira em jan–jul: 15,9, contra 13,8 do v3.1 e 11,2 do v2.1.

É também a variante que mais concorda com os seus rótulos (77,3%; 60% no hold-out) e que pega as 3 divergências da abertura que você marcou.

| Carteira unificada | Trades | Lucro | DD | Ret/DD | jan–jul |
| :-- | --: | --: | --: | --: | --: |
| hoje (B no Sniper + v2.1 no especialista) | 606 | R$ 16.842 | R$ 1.106 | 15,2 | — |
| v2.1 nas duas | 720 | R$ 18.821 | R$ 988 | 19,1 | 11,2 |
| v3.1 nas duas | 568 | R$ 16.572 | R$ 937 | 17,7 | 13,8 |
| **v2.2 nas duas** | 795 | **R$ 21.950** | **R$ 918** | **23,9** | **15,9** |

**Ressalvas:**
- as 9 variantes e as 2 configurações do Sniper foram comparadas no período completo;
- o B6, com o melhor número da carteira, foi reprovado pelo especialista;
- só o papel ao vivo valida.

## No painel 5176
O seletor ganhou a opção **V2.2** (`core/div_engines_view.py` usa `modulo.V22_ABERTURA`). Em 11/11:
- **WIN:** compras às 09:25 e 09:35 com F1 às 09:00, que o v2.1 não marca;
- **WDO:** a venda 09:00→09:10 na Wall 5.600, que você tinha marcado.

Precisa reiniciar o `server.py` para valer.
