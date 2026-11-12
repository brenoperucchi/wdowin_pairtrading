# Plano — Motor único de divergência, rompimentos e ordens limite (12/11/2026)

Status: **somente planejamento**. Nada abaixo foi rodado.

As três frentes pedidas são:
1. unificar o motor de divergência do Sniper 5176 e do especialista novo (`ESP_DIV_V21_WIN`);
2. testar estratégias de rompimento;
3. testar ordens limite no lugar de ordens stop / a mercado.

## 0. Regras comuns às três frentes

- **Dados:** dataset congelado `div_wall_v1` (barras do Profit + Walls, com hash) e MT5 M5/M1 em `data/mt5_rates` (02/01–06/11/2026).
- **Execução:** tick a tick em M1. O WDO antes de 25/02 não tem M1; nesse trecho o stop vem primeiro na barra. Usa o simulador `research/div_master/especialistas/bt.py`.
- **Custos:** WIN 10 pts e WDO 0,5 pt por contrato, mais 1 tick de slippage no stop.
- **DD:** trade a trade.
- **Uma fórmula de fluxo só:** a onda do 5176 (`core.compute_flow`). Mudar a fórmula derruba a regra nova pela metade (`especialistas/RESULTADOS.md` §5b).
- **Registro:** toda configuração vai para um `variations_log.csv`.
- **Relatório:** sempre jan–abr, mai–jul, ago–nov e período completo.
- **Ressalva:** ago–nov já foi usado muitas vezes, então nenhum resultado aqui é fora da amostra. A aprovação final de qualquer mudança é o **papel ao vivo** (≥ 20 pregões / ≥ 40 trades).

---

## Frente 1 — Um motor só para achar divergências

### 1.1 Situação hoje

As duas estratégias leem a **mesma onda**, mas acham a divergência de formas diferentes.

| | Sniper 5176 (WIN_DIV_WALL / WDO_DIV_WALL) | Especialista novo (ESP_DIV_V21_WIN) |
| :-- | :-- | :-- |
| Detector | B "visual": `detect_visual_swing_divergences` (pesquisa) / `_detect_causal_visual_swing_divs` (ao vivo) | `v2.1` (`especialistas/modulo.py`) |
| Pivô | fundo/topo local de 3 barras | ZigZag causal, reversão ≥ 1,2×ATR14 (mínimo 80 pts) |
| F1 | o fundo mais baixo entre 3 e 16 barras atrás | o pivô anterior do mesmo lado (2–48 barras), cada um usado uma vez |
| Fluxo | onda sobe > max(1.500; 18%) no WIN / max(180; 18%) no WDO, ou troca de sinal; exaustão de volume/lote | divergência > 0,15 × mediana causal \|onda\| |
| Wall | calcula `near_wall` mas não filtra (29% fora da Wall) | âncora obrigatória (Wall ≤ 150 / furo ≤ 220, ou extremo do dia); sem super-confluência |
| Como vira trade | **filtro** sobre as entradas dos setups EA: divergência na mesma direção nas 2 barras anteriores à entrada | **entrada própria** na abertura seguinte |
| Cobertura dos seus rótulos (jan–jul, 39 válidas) | 43,6% | 74,4% |

Já foi medido (`research/sniper_v3`):
- trocar o detector do Sniper pelo `v3` derruba o Ret/DD de 14,2 para 4,8;
- `v3` só perto da Wall dá 8,6;
- `v4` dá 4,1.

**Nunca foram testados no Sniper:** o `v2.1` e o `v3.1`.

### 1.2 Teste

**A. Sniper com cada motor.** O resto fica igual à versão B corrigida: o mesmo pool de entradas dos setups, o gate de 3 motores no WIN, as mesmas saídas, horários e meta diária.

| Eixo | Valores |
| :-- | :-- |
| Motor | B (atual), `v3`, `v2.1`, `v3.1` |
| Momento em que a divergência "existe" | barra de confirmação do pivô (`conf`) · barra do gatilho Opção C |
| Janela antes da entrada | 1, 2, 3 barras; e "estado ativo": divergência confirmada há ≤ N barras, N ∈ {6, 12}, ainda não invalidada por novo extremo |
| Âncora | sem âncora (como o Sniper hoje) · âncora da regra nova |

A janela importa porque o `v2.1` confirma mais tarde que o B: o ZigZag espera a reversão. A janela de 2 barras pode não casar com as entradas dos setups, e a opção "estado ativo" testa isso. São 4 × 2 × 5 × 2 = **80 configurações** por ativo.

**B. Especialista novo com cada motor.** Filtros e saída ficam congelados; muda só o motor (B, `v3`, `v2.1`, `v3.1`). São 4 configurações.

**C. Carteira unificada.** Sniper + especialista, **os dois com o mesmo motor**, para cada um dos 4 motores. O resultado é uma tabela 4 × 3 (Sniper, especialista, carteira) com Ret/DD por período e correlação.

### 1.3 Como decidir (fixado antes de rodar)

1. Só concorrem os motores em que **as duas** estratégias ficam com PF > 1,3 em jan–abr, mai–jul e ago–nov.
2. Entre eles, vence o de maior **Ret/DD da carteira em jan–jul**. Em empate (diferença < 10%), vence o de maior cobertura dos seus rótulos.
3. Resultados possíveis:
   - **O `v2.1` mantém o Sniper perto do atual:** unificar no `v2.1`. O painel passa a desenhar as linhas F1→F2 do `v2.1` para as duas estratégias.
   - **O `v2.1` derruba o Sniper** (como aconteceu com o `v3`): é decisão sua.
     - (a) unificar no B e refazer a validação do especialista com o B;
     - (b) unificar no `v2.1` e aceitar um Sniper menor;
     - (c) manter dois motores por enquanto (o que você quer evitar).

### 1.4 Entrega
- Tabela 4 motores × (Sniper, especialista, carteira) e curvas de capital na mesma página de resultados.
- Só depois do seu ok: trocar o detector no motor ao vivo (`gex_live_dealer_engine._detect_causal_visual_swing_divs`) e no painel, com teste de paridade.

---

## Frente 2 — Estratégias de rompimento

### 2.1 O que já existe
- **Rompimento no 1º fechamento além da Wall com o maior fluxo do dia** (`research/div_v3`, etapas D/E): no WIN com "força", jan–jul deu PF 1,44, mas ago–nov deu PF 0,69. **Reprovado.** No WDO, nada.
- **Seus rótulos:** 8 rompimentos válidos nos 9 pregões. A sua regra para o caso de 11/11 é entrar **na aceitação depois do reteste** (10:10), não no 1º fechamento (09:55).
- **O que nunca foi testado:** o rompimento com reteste.
- No pool de setups há EAs de rompimento (`EST_07 Breakout Momentum NY`, `EST_09/10 Breakout Stop`). Eles não usam a definição de divergência/fluxo.

### 2.2 Hipóteses

Todas usam a **mesma onda** e, onde houver divergência, o **motor escolhido na Frente 1**.

| Código | Hipótese | Regra objetiva | Parâmetros (variações registradas) |
| :-- | :-- | :-- | :-- |
| **R1** | Aceitação depois do reteste (a sua regra) | fecha além da Wall/MidWall W + b → em até N barras volta a tocar W ± r → **fecha de novo além de W** → entrada na abertura seguinte | b ∈ {0, 20}, r ∈ {≤ 100, ≤ 150}, N ∈ {6, 12} |
| **R2** | R1 + divergência **oculta** no reteste | no reteste, o preço faz fundo mais alto (compra) e a onda faz fundo mais baixo: continuação | mesmo motor da Frente 1, com a condição de preço invertida |
| **R3** | R1 + onda a favor | no rompimento, a onda está no maior valor do dia no sentido do rompimento | — |
| **R4** | Falha de rompimento (controle, operado ao contrário) | fecha além e volta para dentro em ≤ N barras, com divergência regular no extremo do furo | N ∈ {3, 6} |
| **R0** | Controle | qualquer travessia de Wall, sem fluxo | — |

**Saídas** (as mesmas para R1–R4):
- stop do outro lado da Wall rompida (W − 150 / W − 4,0 no WDO), com teto de 300 / 10,5;
- alvo na próxima Wall/MidWall, ou sem alvo com saída por tempo (12 / 24 barras);
- BE em +180 / +5.

### 2.3 Passos
1. **Detecção contra os rótulos:** os 8 rompimentos válidos e o caso de 11/11. Como 8 casos é pouco, sugiro **uma sessão de rotulagem só de rompimentos** no rotulador (`127.0.0.1:5180`, que já gera candidatos de rompimento): 10 pregões, uns 20 min no total.
2. **Estudo de evento:** retorno a 6/12/24 barras de R0–R4, contra placebo de travessias sorteadas no mesmo mês e direção.
3. **Backtest** de R1–R4 com as saídas acima: até 48 variações por hipótese e ativo.
4. **Carteira:** correlação com o Sniper e com o especialista. O rompimento tende a ganhar nos dias em que a reversão perde, e esse é o motivo de testá-lo.

---

## Frente 3 — Ordens limite no lugar de stop / mercado

### 3.1 Como as entradas são hoje
- **Especialista novo:** **a mercado**, na abertura da barra seguinte ao gatilho.
- **Sniper:** usa a entrada de cada setup EA. No `Jumba_GEX_NWE_Core.mqh`, os slots 1, 2, 4, 13, 14 e 15 armam **LIMITE**, os slots 6 e 11 armam **STOP**, e os slots 9 e 10 usam os dois.
- Passo 0 desta frente: tabelar o tipo de ordem de cada um dos 12 setups do pool (EST_01/04/07/13/14/15/16, WIN_E2, WDO_01/05/07/10) e quanto do resultado do Sniper vem de cada tipo.

### 3.2 A grade de entradas: ordens ancoradas em níveis

Pedido de 12/11: armar ordens limite e stop não só na máxima/mínima da barra, mas **antes e depois** das Walls, das MidWalls e da NWE. O nível é usado como suporte para a entrada, ou como filtro/gatilho da operação.

Descrição para a compra; a venda é o espelho. Tudo é causal: o preço da ordem é calculado no fechamento da barra de sinal com os níveis daquele momento. Na NWE, a ordem é **reposicionada a cada barra** com o valor da barra anterior, como os EAs já fazem.

**Eixo 1 — nível de referência L**

| Código | Nível | Comentário |
| :-- | :-- | :-- |
| BAR | máxima/mínima e meio da barra de gatilho | o que já existe |
| PIV | pivô F2 | o fundo que gerou a divergência |
| WALL | Wall mais próxima no lado certo da ordem | nível GEX principal |
| MID | MidWall mais próxima no lado certo da ordem | nível GEX intermediário |
| N50c / N50b | centro / banda inferior da NWE50 | média e extremo do envelope usado nos filtros |
| N30b | banda inferior da NWE30 | o envelope que o Sniper usa no alvo |
| CONF | confluência: Wall/MidWall e uma banda NWE a ≤ 50 pts (WIN) / ≤ 1,5 pt (WDO) uma da outra | o nível vale só onde dois suportes coincidem |

**Eixo 2 — tipo de ordem e lado do nível**

| Tipo | Onde fica | O que significa |
| :-- | :-- | :-- |
| **LIMITE** | nível **abaixo** do preço; compra quando o preço volta ao suporte | entrar no suporte (melhor preço, risco de não executar) |
| **STOP** | nível **acima** do preço; compra quando o preço retoma ou rompe o nível | o nível vira gatilho de confirmação (pior preço, executa só se andar a favor) |

Só arma se o nível estiver do lado certo e a no máximo 1 × ATR14 (ou 250 pts no WIN / 6 pts no WDO) do preço. Se não houver nível elegível, o sinal não opera, e isso é medido como filtro.

**Eixo 3 — deslocamento δ em relação ao nível** ("antes" = sem encostar no nível; "depois" = exige furar um pouco)

| | Antes do nível | No nível | Depois do nível |
| :-- | :-- | :-- | :-- |
| WIN | +30, +15 pts | 0 | −15, −30 pts |
| WDO | +1,0, +0,5 pt | 0 | −0,5, −1,0 pt |

Na LIMITE de compra, "antes" fica acima do suporte (executa mais vezes) e "depois" fica abaixo (exige violinada, preço melhor). Na STOP de compra, "antes" fica abaixo do nível (antecipa) e "depois" fica acima (exige rompimento confirmado).

**Eixo 4 — validade e cancelamento:** a ordem vale 1, 3 ou 6 barras. É cancelada se o preço fizer novo extremo além do F2 antes de executar, ou se chegar às 15:55.

**Eixo 5 — onde fica o stop de proteção**
- (a) −200 pts do preço executado (como hoje);
- (b) **atrás do nível**: L − 60 pts (WIN) / L − 2,0 (WDO), com teto de 300 / 10,5 e mínimo de 80 / 2,5.

A hipótese do (b) é que, entrando no suporte, o stop pode ser bem mais curto.

**Tamanho da grade:** 7 níveis × 2 tipos × 5 deslocamentos × 3 validades × 2 stops = **420 configurações por estratégia e ativo**, mais as 6 entradas simples (MKT, STP na máxima, LMT no meio, LMT no pivô, LMT na abertura −2/−4 ticks). Tudo vai para o `variations_log.csv`. A escolha é por **platô**: a mediana do Ret/DD da configuração e das vizinhas de um passo em δ e na validade. O ponto máximo isolado não é o critério.

### 3.3 O nível como filtro, e não como preço de entrada

As mesmas referências servem para responder outra pergunta: **o trade é melhor quando há suporte por perto?** Sem mudar a entrada a mercado:

| Código | Filtro | Variações |
| :-- | :-- | :-- |
| F-dist | só opera se houver Wall / MidWall / banda NWE **entre a entrada e o stop** (suporte protegendo o stop) | por tipo de nível |
| F-espaço | só opera se o próximo nível **contra** (resistência na compra) estiver a ≥ X pts | X ∈ {150, 250, 400} (WIN) / {4, 6, 10} (WDO) |
| F-toque | só opera se, em até N barras depois do gatilho, o preço **testar** o nível de suporte e fechar acima (confirmação no nível) | N ∈ {3, 6}; equivale à LIMITE com execução no fechamento |

### 3.4 Onde aplicar
- **Especialista novo:** a grade inteira (3.2 e 3.3). Sinais, filtros de contexto e saída por tempo/BE ficam congelados.
- **Sniper:** para cada sinal, refazer a entrada com a grade 3.2. A comparação de referência é a ordem que o setup usa hoje. Isto já é uma estratégia nova: os setups foram ajustados com o tipo de entrada que usam hoje.
- **Rompimento R1 (Frente 2):** a aceitação depois do reteste vira naturalmente **STOP acima da Wall/MidWall rompida** (δ "depois" = +15/+30) ou **LIMITE no reteste do nível** (δ "antes"). Os dois são testados com esta mesma grade, para que reversão e rompimento usem o mesmo vocabulário de ordens.

### 3.5 Realismo das ordens pendentes (o ponto que mais distorce backtest)
- **Execução da LIMITE:** só conta quando o preço **passa 1 tick além** do limite, não só quando toca. Como limite superior, o modo "tocou = executou" é reportado à parte.
- **Execução da STOP:** no preço da ordem + 1 tick de slippage. Se a barra abrir além da ordem (gap), executa na abertura.
- **Gap na LIMITE:** se a barra abrir já além do limite, executa na abertura, a favor.
- **Taxa de execução:** relatar quantos sinais executam.
- **Seleção adversa:** comparar o resultado dos sinais **não executados** (com entrada a mercado) com o dos executados. É comum o limite perder justamente os melhores trades, aqueles que saem sem voltar.
- **Ordem dos ticks:** a sequência O→H→L→C dentro de cada minuto é uma aproximação. O limite e o stop na mesma barra M1 são resolvidos de forma conservadora (stop primeiro).

---

## 4. Ordem e esforço

| Ordem | Frente | Por quê | Esforço |
| :-- | :-- | :-- | :-- |
| 1 | Frente 1 | as outras duas dependem do motor escolhido | ~1 dia |
| 2 | Frente 3 | reaproveita `bt.py` e não precisa de rótulos novos; a grade de níveis vale também para o rompimento | ~1 dia (grade de 420 por estratégia e ativo) |
| 3 | Frente 2 | precisa de definições e, idealmente, dos rótulos de rompimento; usa a grade de ordens da Frente 3 | ~1–1,5 dia + ~20 min seus de rotulagem |

## 5. Decisões suas antes de rodar

**Respostas do usuário (12/11/2026):**
1. Sim: os deslocamentos ficam como propostos.
2. (c): a escolha do motor fica para depois da tabela da Frente 1.
3. Não: sem rotulagem nova de rompimentos. A Frente 2 vai direto para o estudo de evento e o backtest.
4. Sim: o critério da Frente 1 fica como está.

Enquanto o motor não é escolhido, a Frente 3 e as hipóteses R2/R4 rodam com o `v2.1` e serão refeitas se o motor mudar.

Perguntas originais:

1. **Ordens:** entendi que as ordens limite/stop ancoradas em níveis valem para a **entrada** (e, na variação 3.2-b, também para posicionar o stop atrás do nível), aplicadas no especialista, no Sniper e no rompimento. Está certo? E os deslocamentos de ±15/±30 pts (WIN) e ±0,5/±1,0 pt (WDO) servem como "antes e depois" do nível?
2. **Unificação:** se o `v2.1` derrubar o Sniper, você prefere (a) unificar no B e refazer o especialista, (b) unificar no `v2.1` e aceitar um Sniper menor, ou decidir depois de ver a tabela?
3. **Rompimento:** os parâmetros de R1 (b, r, N) acima servem como ponto de partida? Você topa uma sessão curta de rotulagem só de rompimentos?
4. **Critério da Frente 1:** PF > 1,3 nas três partes e maior Ret/DD da carteira em jan–jul. Está bom?
