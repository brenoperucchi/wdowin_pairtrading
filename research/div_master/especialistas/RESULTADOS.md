# Especialistas 5176 — busca de gatilho no período completo (12/11/2026)

Pedido: aplicar o gatilho (a)+(b), rodar o **período completo** (02/01 a 06/11/2026, MT5 em cache) e, se as hipóteses não fossem boas, continuar até achar um gatilho com **Ret/DD acima de 10**.

**Resultado:** achei uma regra no WIN com Ret/DD 11,8 no período completo. A Opção C não contribui para ela: a vantagem vem da divergência do motor `v2.1` mais quatro filtros de contexto. O WDO não tem vantagem com nenhum dos três motores.

> **Ressalva de seleção.** A regra foi escolhida olhando o período completo, inclusive ago–nov. Foram **77.828 configurações** testadas (22.070 no WIN), todas em `results/variations_log.csv`. Os números abaixo são **dentro da amostra**. O único teste limpo que sobra é o papel ao vivo (Etapa 5).

Scripts: `bt.py` (backtest em M1), `busca.py` (rodada 0), `evento.py`, `r1.py`, `r2.py`, `r3.py`, `robust.py`.
Regras do backtest:
- sinal no fechamento da barra; entrada na abertura da barra seguinte (MT5);
- execução tick a tick em M1;
- custo de 10 pts por contrato e 1 tick de slippage no stop;
- DD trade a trade.

## 1. A SPEC como está (rodada 0): não funciona

São 3 motores × 2 especialistas (e a união dos dois) × Saídas A/B × 2 ativos = 54 linhas. **Todas** dão Ret/DD abaixo de 2. A melhor carteira é `v3`, EXTREMO, Saída B: Ret/DD 0,54. No WDO, a Saída A perde em todos os casos (PF 0,60–0,76).

A Saída B aborta cerca de 70% dos sinais: com o atraso do gatilho, a entrada fica longe do pivô e o stop passa de 300 pts.

## 2. Onde a vantagem aparece (estudo de evento, 12 barras, líquido de custo)

| Ativo | Motor | jan–jul | ago–nov |
| :-- | :-- | --: | --: |
| WIN | v3 | −31 pts | −34 pts |
| WIN | **v2.1** | **+19 pts** | **+14 pts** |
| WIN | v3.1 | −22 pts | −29 pts |
| WDO | os três | ≈ 0 | ≈ 0 |

- No WIN `v2.1`, **sem super-confluência** dá +57 / +100 pts (869 sinais). Quando o F2 está ao mesmo tempo na Wall e no extremo do dia, a reversão falha mais.
- Gatilhos atrasados (2–3 barras depois do pivô) são os piores em todos os motores.

## 3. Rodadas de busca (WIN `v2.1`)

| Rodada | O que variou | Melhor robusto (≥ 150 trades, lucro em jan–abr, mai–jul e ago–nov) | Platô |
| :-- | :-- | :-- | --: |
| r1 | 1 filtro × 74 saídas | Ret/DD 6,9 | — |
| r2 | 1–3 filtros × saídas × gestão (17.908 configurações) | Ret/DD 8,0 | 7,2 |
| r3 | 3 cortes que perdiam nos três períodos (16h; `ext50 ≤ −0,5`; `slope50 ≤ −0,5`) e atraso ≤ 2 barras | **Ret/DD 11,8** (11 configurações acima de 10) | **9,9** |

O WDO passou pelas mesmas rodadas 1 e 2 (55.722 configurações). O melhor robusto deu Ret/DD 1,3 e o platô ficou em 0.

## 4. A regra encontrada (`ESP_DIV_V21_WIN`)

| Item | Regra |
| :-- | :-- |
| Ativo | WIN (M5) |
| Divergência | motor `v2.1`: ZigZag causal de 1,2×ATR14 (piso 80 pts); F1 = pivô anterior do mesmo lado (2–48 barras), sem leque; preço ≤ F1 + 60; onda com divergência > 0,15 × mediana causal de \|onda\| |
| Âncora | F2 a ≤ 150 pts de Wall/MidWall (ou furo de até 220), **ou** extremo do dia depois das 09:30. **Exclui** o F2 com as duas âncoras (super-confluência) |
| Gatilho | Opção C (a)+(b), até `j+3`. Sem ela o resultado é o mesmo (ver §5) |
| Contexto | entrada entre **10:00 e 15:55**; no máximo o **2º gatilho do dia** na direção; `ext50 > −0,5` (não compra acima do centro da NWE50 nem vende abaixo, com folga de meia banda); `slope50 > −0,5` (a NWE50 não inclina forte contra o trade) |
| Saída | **SL 200 pts**, sem alvo, saída no **máximo em 12 barras (60 min)** ou às 17:25, **BE +180 → +20** |
| Gestão | um trade por vez; sem meta diária; sem pausa de almoço |

| Período | Trades | PF | Lucro (1 contrato) | DD | Ret/DD |
| :-- | --: | --: | --: | --: | --: |
| jan–abr | 132 | 1,43 | R$ 1.176 | R$ 381 | 3,1 |
| mai–jul | 95 | 1,70 | R$ 1.159 | R$ 396 | 2,9 |
| jan–jul | 227 | 1,53 | R$ 2.335 | R$ 396 | 5,9 |
| ago–6/nov | 92 | 2,38 | R$ 2.368 | R$ 214 | 11,1 |
| **Completo** | **319** | **1,77** | **R$ 4.703** | **R$ 399** | **11,8** |

- Meses positivos: 11/11. Com 2 contratos: R$ 9.406, DD R$ 798.
- Por mês (R$, 1 contrato):
  - jan 289 · fev 425 · mar 197 · abr 265 · mai 657 · jun 441
  - jul 61 · ago 33 · set 360 · out 1.717 · nov 258
- Outubro sozinho é 36% do lucro.

## 5. Robustez (`results/robust.json`)

| Teste | Ret/DD | Leitura |
| :-- | --: | :-- |
| Regra escolhida | 11,8 | — |
| **Placebo de barras**: 300 sorteios de barras com os mesmos filtros de contexto, mesmo nº por mês × direção, mesma saída | mediana −0,55 · p95 0,97 · máx. 2,0 | p = 0,003. A vantagem não vem do contexto sozinho |
| **Sem divergência** (onda com limiar −∞, resto igual) | 5,6 | A divergência dobra o Ret/DD (o DD cai de R$ 766 para R$ 399) |
| **Sem Opção C** (entra na primeira barra da janela) | 11,8 | **A Opção C não acrescenta nada** (jan–jul 6,0 · ago–nov 6,8) |
| Direção invertida | −0,9 | Coerente |
| Custo dobrado + 2 ticks de slippage | 7,2 | Continua positivo (PF 1,57) |
| Só M5 (stop primeiro na barra) | 11,8 | Sem alvo, a ordem dos ticks dentro da barra não muda nada |

## 5b. Sensibilidade à fórmula do fluxo (`fluxo_var.py` → `results/fluxo_var.csv`)

A regra fica congelada (gatilho, filtros e saída); só muda a onda que o motor `v2.1` lê. A fórmula parametrizada reproduz `core.compute_flow` exatamente (conferido em 30 pregões).

| Variante | Trades | PF | Ret/DD | jan–jul | ago–nov | Meses + |
| :-- | --: | --: | --: | --: | --: | :-: |
| 5176 (base) | 319 | 1,77 | 11,8 | 5,9 | 11,1 | 11/11 |
| **5174 V5b inteiro** (12/18/70 · EMA4/20 · 92/8) | 293 | 1,46 | **5,3** | 2,5 | 5,1 | 6/11 |
| Pesos V5b + memória 5176 | 306 | 1,53 | 4,3 | 3,2 | 5,0 | 7/11 |
| Pesos 5176 + memória V5b | 295 | 1,48 | 4,4 | 3,1 | 2,2 | 8/11 |
| Só o institucional V5b (0,90/0,75/−0,25) no 5176 | 317 | 1,74 | 11,4 | 5,3 | 11,4 | 11/11 |

**24 variações pequenas em torno do 5176** (cada motor ±0,05/±0,10, subpesos do institucional ×0,8/×1,2, EMA e mistura):
- todas com PF > 1;
- Ret/DD mediano 11,5, mínimo 6,0, máximo 14,2;
- 17 de 24 com Ret/DD ≥ 10.

O ponto sensível é a **memória da onda**, não o peso dos motores: EMA rápida 0,4, EMA lenta 12 e mistura 0,65/0,35 ficam em 6–6,7. A pior mudança de peso foi Wyckoff −0,10, com 7,5.

O fluxo V5b do 5174 pode ser usado e a regra continua lucrativa, mas o resultado cai pela metade: a regra foi achada sobre a onda do 5176. Variantes melhores que a base, como institucional +0,05 (14,2), **não** foram adotadas, para não sobreajustar mais.

## 6. O que isso significa

1. **A hipótese central da SPEC não se confirmou.** A Opção C não separa o válido do falso. O que funciona é a divergência `v2.1` (pivô evidente) **fora** da super-confluência, com entrada logo depois da confirmação e saída curta por tempo.
2. **O WDO fica de fora** deste especialista. Nenhum motor deu vantagem acima do custo.
3. **Não é a Saída A nem a B da SPEC.** É uma saída nova (stop fixo, sem alvo, 60 min, BE), escolhida na grade.
4. **Riscos de sobreajuste:**
   - os cortes de 16h, `ext50` e `slope50` saíram de olhar o período completo;
   - o platô (9,9) é menor que o ponto (11,8);
   - jan–jul sozinho dá 5,9;
   - outubro concentra o lucro.

   O placebo (p = 0,003, máximo de 2,0 em 300 sorteios) e os três períodos positivos dão algum conforto. Mas eles não substituem um teste fora da amostra.

## 7. Próximos passos sugeridos

1. **Congelar a regra** (hash do `modulo.py`, `bt.py` e dos parâmetros acima) e rodá-la **em sombra ao vivo** no 5176 por ≥ 20 pregões / ≥ 40 trades antes de qualquer dinheiro.
2. Simplificar: como a Opção C não acrescenta, a versão operável pode entrar na confirmação do pivô. É mais simples ao vivo e dá o mesmo resultado no histórico.
3. Opcional: medir a correlação com o Sniper 5176 corrigido (Ret/DD 14,2) para ver se os dois juntos reduzem o DD da carteira.
