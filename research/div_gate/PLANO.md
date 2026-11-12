# Plano — Gate de divergência F1→F2 / T1→T2 na Wall sobre as entradas dos robôs (11/11/2026)

Rascunho de pré-registro. Nada roda antes de aprovado; depois de aprovado, grade e critérios ficam congelados.

## 1. Pergunta
A divergência preço × onda smart money perto de uma Wall **melhora as entradas que já temos** quando usada como
filtro (gate), em vez de ser uma entrada própria? Sozinha ela não sustentou setup (laboratório `research/div_wall`:
M5 sem vantagem, M1 comido pelo custo, fase 2 reprovada no OOS). O teste aqui é outro: ela só decide se uma
entrada que o robô já ia fazer passa ou não.

## 2. Universo de entradas (29 famílias, 32 versões)
Medido pela sobreposição das entradas (data, horário, direção) no BT sem filtro (`bt_32_slots_trades.csv`):
- Os 14 registrados usam a **mesma entrada** do slot do EA (Jaccard 0,92–1,00). O que muda é saída e filtro.
  Exceção: EST_04 registrado (entrada alinhada ao WDO) bate só 0,65 com o slot 4 → família própria.
- Clones (Jaccard ≥ 0,73) entram uma vez só: WIN S08 e S12 ≈ S07 · WDO S12 ≈ S01 · WDO S14 ≈ S13 · WDO S16 ≈ S04.

| Ativo | Famílias de entrada |
| :-- | :-- |
| WIN (16) | S01 Scalper NY · S02 Scalper Dia Todo · S03 Arbitragem WDO · S04 Pullback Reteste · EST_04 alinhado · S05 Cluster NWE · S06 Limit Slope · S07 Breakout Momentum · S09 Stop/Lim Wall NY · S10 Stop/Lim MainWall · S11 Grid Pullback · S13 SmartGrid CrossWDO · S14 SmartGrid Wick25 · S15 SmartGrid Z30 · S16 SmartGrid Spring · E2 Wall Gasta |
| WDO (13) | S01 · S02 · S03 · S04 · S05 · S06 · S07 · S08 · S09 · S10 · S11 · S13 · S15 |

Saída de cada família na fase 2 = **a do EA (Core MQL)**, porque é o que roda no MT5 (8 Elite). Onde a versão
registrada tem saída diferente, ela entra como 2ª versão: EST_01 (BE_WALL 25 + MainWall), EST_07 (BE_WALL 15 +
MidWall), EST_16 (= S03 com BE_WALL 20 + MidWall). Total: 32 versões.

## 3. O gate
Função única `div_gate(asset, date, tmin, dir) -> bool`, calculada do `.min` do Profit com o detector de
`core/div_wall_signal.py` (mesma onda, mesmos pivôs causais, NWE 100/8/3), pré-calculada por barra como as
máscaras de fluxo (`flow_masks.pkl` + manifesto com hash). BT e ao vivo usam a mesma tabela/função.

Estado por barra M5 fechada t: "divergência de compra ativa" = sinal F1→F2 confirmado em alguma barra de
[t−N+1, t] com F2 a até `R` de uma Wall/MidWall (venda: T1→T2, simétrico).

Modos:
- **EXIGIR**: compra só passa com divergência de compra ativa (venda idem).
- **VETAR**: compra é bloqueada se houver divergência de venda ativa (venda idem). Corta menos trades.

### 3b. Definição v2 (revisada com o usuário em 11/11, substitui a v1)
Caso de referência: WIN 10/11. A v1 achava a divergência da manhã (F1 09:25 → F2 10:40, MidWall 174.288) mas
não a da tarde (F1 11:45 → F2 15:20): F1–F2 a 43 barras (limite 20), queda de 575 pts (limite 400), F2 furou a
Wall 172.772 em 322 pts (raio 40–100) e o F1 escolhido era o fundo mais baixo, não o de fluxo mais fraco.
A v1 também tinha um erro no WDO: usava as tolerâncias de preço do WIN (50 / 400 pts).

`core.div_wall_signal.detect_divergences_v2`:
- **F1**: qualquer fundo (topo) anterior do mesmo pregão, a pelo menos 3 barras do F2 — sem limite de distância.
- **Preço**: F2 abaixo do F1 por qualquer distância, ou até `price_tol` acima (WIN 50 / WDO 1,5) — sem limite de extensão.
- **Fluxo**: entre os candidatos, F1 = o de onda mais negativa (venda: mais positiva); exige onda(F2) − onda(F1)
  > k × mediana causal de |onda| do dia.
- **Wall** (Wall ou MidWall): "perto" = F2 a até R do nível; ou "furou e voltou" = F2 além do nível mais próximo
  e um fechamento de volta além dele em até 12 barras.
- **Confirmação** (as duas entram na grade): PIVO = perto vale na confirmação do pivô, furou-e-voltou vale no
  fechamento de retomada; FECHA_WALL = sempre no primeiro fechamento além do nível (até 12 barras após F2).
- Em 10/11 a v2 marca as duas: compra 10:45 (F1 09:25 → F2 10:40) e compra 15:25 (F1 11:45 → F2 15:20, furou a
  Wall 172.772 e voltou).

Fixos: `pivot_left=2`, `pivot_right=1`, NWE "extreme" com o período da grade.

## 4. Grade (só IS, jan–jul) — 576 combinações por versão (v2, com a confirmação), ~17.900 BTs
**Ajuste do usuário (11/11):** toda divergência tem que ser na Wall (saiu a opção "sem Wall") e a NWE varia.
| Parâmetro | Valores |
| :-- | :-- |
| modo | EXIGIR, VETAR |
| janela N (barras M5) | 3, 6, 12 |
| força `wave_k` | 0,5 · 1,0 · 1,5 |
| raio da Wall `R` (sempre na Wall/MidWall) | WIN 40 / 100 · WDO 1,5 / 4,0 |
| NWE do gate (bw 8, mult 3, filtro "extreme": F2 na metade externa da banda) | período 30, 50, 80, 100 |
| filtro de fluxo junto | nenhum · o filtro atual da versão (E lógico) |
| confirmação (v2) | PIVO · FECHA_WALL |

Filtro atual = o registrado (NR_*) ou, para as demais, o escolhido no IS em `bt_32_slots.py`.
Detector v2 sem cooldown (toda divergência conta), pregão inteiro.
Os dados do BT da grade são cortados em 01/08 00:00 (`mt5_loader`): nenhuma barra do OOS entra.

**Versões efetivas (31):** `research/div_gate/versions.py`. Slots WIN 1–12 fora dos registrados usam a
configuração original do Python (`o16` padrão). Os slots 3 e 5 do Core MQL atual (M15 Fakeout / M15 MidWall)
não têm simulador no runner e ficam fora desta rodada.

Execução: sempre pelos simuladores do runner único (`o16`, `test_win_aligned_wdo_matrix`, `sg_sim`,
`wdo_mt5_sim`, E2), regras MT5 (stop antes do alvo, gap na abertura, BE só se a abertura seguinte passar),
custos WIN 10 pts / WDO 0,5 pt, 1 contrato, Walls reais do histórico B3. Bloquear entrada muda o estado do robô
(posição, trades do dia), então cada combinação é um BT completo — nunca filtro a posteriori na lista de trades.

## 5. Controles contra falso positivo
1. **Placebo aleatório:** para a config escolhida, 200 gates aleatórios (custo: o SmartGrid leva ~10 s por BT)
   que deixam passar a mesma fração de sinais por mês e direção. p = (1 + nº de placebos com Ret/DD ≥ o do
   gate) / 201. Exige p < 0,10 no IS. Só roda para versões que passaram o critério (a).
2. **Gate invertido:** mesma config com a direção trocada. Se o invertido também melhora, o ganho é só cortar
   trade, não informação da divergência → reprova.
3. **Platô:** ranking pela mediana do Ret/DD da config e dos vizinhos de 1 parâmetro (como na fase 2).
4. Mínimo 40 trades no IS por versão com gate.

## 6. Regra de escolha (IS) e OOS (uma vez)
Por versão: o gate só é aceito se no IS (a) Ret/DD do platô ≥ 1,2 × o melhor Ret/DD da versão sem gate
(o maior entre "sem filtro" e "filtro atual"), (b) placebo p < 0,10, (c) o invertido não atinge essa mesma
marca (1,2 × base). Senão a versão segue sem gate.

Carteira: escolhida só com o IS (versões com Ret/DD IS ≥ 3 e PF IS ≥ 1,2, uma por família).

OOS ago–6/nov roda **uma vez**, com `oos_log.json` travando a execução. Aprovação do gate por versão: PF OOS ≥
1,20, lucro > 0, ≥ metade dos meses positivos e Ret/DD OOS ≥ o da mesma versão sem gate. Reprovou → morre.

**Atenção:** o OOS ago–nov das entradas já foi visto hoje (BTs dos 14, 32 e 8 Elite). Ele continua limpo para
a pergunta "o gate ajuda?" (o gate nunca foi escolhido olhando ago–nov), mas não para "qual entrada é boa".
Por isso: **teste em papel ao vivo** a partir de 12/11 com o motor de paridade, mínimo de 20 pregões,
antes de qualquer mudança no MT5.

## 7. Comparações reportadas (mesma tabela de sempre)
Trades, WR, PF, lucro, DD, Ret/DD, meses positivos, IS e OOS, para cada versão em 4 colunas:
sem filtro · filtro atual · gate · gate + filtro atual. Mais a carteira e os 8 Elite atuais como referência.

## 8. Fases
| Fase | Entrega | Critério de pronto |
| :-- | :-- | :-- |
| 0 | `div_gate` + tabela por barra (`.min`, 234 dias), manifesto com hash | teste de causalidade: tabela com corte T = tabela inteira até T, 100% |
| 1 | Integração no runner (`sig_filter` = fluxo E gate) e no `setups_live` — **só para os gates aprovados** (feito depois da fase 3) | paridade ao vivo × BT 100% em cortes barra a barra (como `test_runner_causal.py`) |
| 2 | Grade IS das 32 versões + placebo + invertido | tabela de escolha congelada antes do OOS |
| 3 | OOS uma vez + carteira | relatório com as 4 colunas |
| 4 | (só para sobreviventes) proteção de saída por divergência: BE ou saída quando aparece divergência contrária | mesmo protocolo IS/OOS; exige gancho de saída nos simuladores |
| 5 | Papel ao vivo 20 pregões; depois decidir como levar ao MT5 | ao vivo dentro do intervalo esperado pelo BT |

## 9. Pendências que afetam o plano
- O ao vivo depende do `.min` do Profit atualizar durante o pregão (ainda não confirmado).
- MT5 não tem o `.min`. Para os 8 Elite usarem o gate há dois caminhos: (a) o motor Python publica o gate por
  barra e o EA lê (`InpUseDivGate`), mantendo a mesma fonte; (b) portar o detector para MQL com ticks do MT5,
  que é outra fonte de fluxo e exige nova paridade. Recomendação: (a). Decisão só depois da fase 3.
- O filtro nativo do WIN nos EAs (4_FLUXO_ABSORCAO) não bloqueia nenhum sinal; vale revisar à parte.
