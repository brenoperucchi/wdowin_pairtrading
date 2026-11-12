# Etapa 1 — Módulo unificado + paridade causal (12/11/2026)

SPEC: [`../SPEC_ESPECIALISTAS_5176.md`](../SPEC_ESPECIALISTAS_5176.md), revisão 2. Período usado: só **jan–jul/2026** (143 pregões por ativo, dataset congelado `div_wall_v1` com hash). Ago–nov não foi tocado. **Sem P&L e sem retorno à frente**: só contagens.

Não altera `core/`, o painel 5176 nem `labels.csv`.

| Arquivo | O que faz |
| :-- | :-- |
| `modulo.py` | 3 motores (`v3`, `v2.1`, `v3.1`), 2 especialistas (`WALL`, `EXTREMO`), gatilho Opção C, `run_day` |
| `paridade.py` | portas contra os motores originais + paridade lote × barra a barra → `results/paridade.json` |
| `etapa1.py` | contagens → `results/etapa1.json` |
| `results/gatilho_trivial.json` | quanto da Opção C já valia no fechamento da barra do pivô |

## 1. Testes de causalidade e de porta — todos passaram

| Teste | Resultado |
| :-- | :-- |
| **Porta `v3`**: `engine_v3` × `core.detect_divergences_v3` (raio de Wall infinito, sem NWE) | WIN 985 sinais e WDO 985 sinais em 143 pregões cada, **0 pregões diferentes** (os totais iguais são coincidência: no mesmo dia, 3 × 4 sinais) |
| **Porta `v2.1`**: `engine_v21` com a elegibilidade original × `engine_v2_1/detections.json` | 144 detecções em 16 pregões, **0 diferenças** |
| **Paridade**: pipeline inteiro em `bars[:t+1]` para cada barra `t`, comparado com o lote do dia (candidatos com `conf ≤ t`, gatilhos com `idx ≤ t` e suas etiquetas, descartes) | WIN 143 pregões, 3.359 candidatos, 3.365 gatilhos · WDO 143 pregões, 3.734 candidatos, 3.502 gatilhos · **0 erros** |
| **Mutação** (o teste pega um vazamento?) | Gatilho lendo a barra `t+1`: pego em 19/20 pregões. Âncora lendo `j+2`: pego em 20/20 |

## 2. Escolhas de implementação (pontos que a SPEC não fixava)

1. **Os motores só emitem F2 com âncora** (WALL ou EXTREMO), para que o reset do F1 aconteça só em divergências que algum especialista poderia operar. Pivôs sem âncora continuam disponíveis como F1. As portas usam a elegibilidade original de cada motor.
2. **`v3`**: tolerância de preço do `core` (`50 pts` / `1,5 pt`); a SPEC não dava valor.
3. **`v3.1`**:
   - pareamento do F1 pela regra do `v2.1` (o pivô anterior mais recente que passa);
   - limiar de onda `0,15 ×` mediana e tolerância `60 pts` / `2,0 pts`, como no `v2.1`;
   - semente = barra 0 + o primeiro pivô L1/R1 até 09:20 de cada lado;
   - confirmação reduzida (ZigZag `0,8×ATR` ou L2/R1 com candle a favor) vale até 09:35;
   - cada pivô é avaliado como F2 uma vez, na primeira confirmação.
4. **ATR** com piso de 1 tick (o `v2.1` usava `5,0` fixo, que é 1 tick do WIN e seria 10 pts no WDO).
5. **Nível da Wall**: no C1, a Wall mais próxima que a mínima furou (até `220 pts` / `6,0 pts`); no C2, a mais próxima do lado defendido (até `150 pts` / `3,5 pts`). Compra; a venda é espelhada.
6. **EXTREMO**: `E_prev` exclui a barra `j−1` (como na SPEC). "Testa" = até `30 pts` / `1,0 pt` do extremo. Sem violação, o gatilho é fechar além da máxima/mínima da barra `j`.
7. **Super-confluência** = F2 com as duas âncoras (conhecido na confirmação). Na carteira combinada, o segundo disparo do mesmo candidato é marcado `dup` e descartado; na mesma barra, o WALL tem prioridade. Assim a etiqueta não muda depois de nascer (passa na paridade).
8. **Horário**: o gatilho é contado até a última barra do pregão. Os disparos após 17h aparecem à parte; o corte de horário fica para o backtest.

## 3. Contagens em jan–jul

Gatilhos/dia por especialista; a "carteira" soma os dois sem os duplicados.

| Ativo | Motor | Candidatos/dia | WALL: gatilhos/dia (% da base que dispara) | EXTREMO: gatilhos/dia (% dispara) | Carteira/dia | Item 5 aprova |
| :-- | :-- | --: | :-- | :-- | --: | --: |
| WIN | v3 | 6,4 | 4,4 (85%) | 2,5 (72%) | 5,4 | 98,0% |
| WIN | v2.1 | 10,1 | 6,9 (78%) | 2,4 (67%) | 7,9 | 95,4% |
| WIN | v3.1 | 7,0 | 4,4 (79%) | 2,9 (67%) | 5,5 | 93,4% |
| WDO | v3 | 6,5 | 3,8 (76%) | 3,1 (73%) | 5,2 | 99,2% |
| WDO | v2.1 | 12,0 | 7,1 (69%) | 3,1 (67%) | 8,5 | 97,9% |
| WDO | v3.1 | 7,6 | 4,2 (71%) | 3,2 (65%) | 5,6 | 97,5% |

Outros números (detalhe em `results/etapa1.json`):
- **Atraso do gatilho**: a maioria dispara em `j+1` (WIN `v3` 86%, `v2.1` 68%, `v3.1` 72%).
- **Descartes** (confirmação do pivô depois de `j+3`): 0% no `v3`, 2–5% no `v2.1` e no `v3.1`. Bate com os 4,2% medidos na revisão 2.
- **Super-confluência**: 33–49% dos gatilhos WALL têm também a âncora EXTREMO.
- **Balde das 09h**: o `v3.1` concentra mais (WIN 17% / WDO 25% dos gatilhos WALL), por causa da semente de abertura; o `v2.1` quase não tem (2–4%).
- **Após 17h**: o `v2.1` tem 156 gatilhos WALL no WIN e 159 no WDO; os outros, 27–41.

## 4. O que a Etapa 1 mostra

### 4.1 O item 5 do `v3.1` sai do motor
Ele aprova **93,4% (WIN) e 97,5% (WDO)** dos candidatos, acima do corte de 90% pré-registrado na SPEC (§2.3, item 5). Nos outros motores aprova 95–99%. É o mesmo problema do filtro "3 motores" do Sniper: um "OU" de três condições de força quase sempre tem uma a favor. O `v3.1` segue **sem o item 5**, que fica registrado na SPEC. Com isso o `v3.1` também deixa de depender do dado ao vivo `inst_pass_delta` (alerta do §6.1).

### 4.2 A Opção C, como está escrita, quase não filtra
Ela dispara em **65–85%** dos candidatos com âncora. O motivo está em `results/gatilho_trivial.json`:

| | WIN (v3 / v2.1 / v3.1) | WDO (v3 / v2.1 / v3.1) |
| :-- | :-- | :-- |
| Gatilhos C1 em que a barra do pivô **já fechou** de volta além da Wall + buffer | 76% / 73% / 73% | 62% / 60% / 57% |
| Gatilhos EXTREMO "violou" em que a barra do pivô **já fechou** de volta dentro do range | 65% / 61% / 58% | 61% / 60% / 58% |
| Gatilhos WALL cuja condição já valia no fechamento da barra do pivô | 46% / 44% / 47% | 37% / 35% / 33% |

Na maioria dos C1 o "furo" foi só pavio: a barra do pivô já fechou retomada, e a barra seguinte só precisa não devolver. Nesses casos o gatilho vira "o pivô confirmou e a barra seguinte não caiu", não uma retomada. Como a hipótese da SPEC é que a Opção C é o que separa o válido do falso (§0), isso precisa ser decidido **antes** do backtest, enquanto ninguém olhou resultado.

Alternativas estruturais, sem medir lucro (decisão sua):
- **(a)** O C1 exige que a barra do pivô tenha **fechado além** da Wall (furo real, não pavio); o pavio cai no C2. No EXTREMO, idem: "violou" só com fechamento fora do range.
- **(b)** Manter as âncoras e endurecer o gatilho: a barra `t` tem de fechar além do **fechamento** da barra do pivô (`C_t > C_j`) também no C1 e no EXTREMO, como já é no C2.
- **(c)** Não mudar e deixar o controle "sem Opção C" da Etapa 3 medir. Mas, com 65–85% disparando, as duas versões vão operar quase os mesmos trades, e o teste não terá poder para separar.

Recomendo **(a) + (b)** juntos: (a) faz o C1 significar o que a SPEC descreve, e (b) dá ao gatilho um papel de confirmação em todos os subcasos.

### 4.3 O volume ainda está longe do que você marca
São **5,2 a 8,5 entradas por dia por ativo** na carteira combinada. Você marca cerca de 2–3 por dia por ativo, e só cerca de metade dos candidatos do rotulador saiu válida. Parte disso o gatilho mais duro (4.2) corta. O resto é papel da Etapa 2: escolher o motor pela precisão nos rótulos.

## 5. Próximos passos
1. **Você decide o gatilho** (4.2: a, b, a+b ou c). Eu reaplico no módulo, rodo de novo a paridade e as contagens. Continua sem P&L.
2. **Etapa 2**: cobertura, precisão e atraso dos 3 motores contra `labels.csv` (9 pregões WIN, 44 divergências válidas), com hold-out e leave-one-session-out, mais o gabarito de 11/11. Sai um único motor.
3. O WDO continua só com contagens até ter rótulos (SPEC §6.2).
