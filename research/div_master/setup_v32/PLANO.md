# Plano — Setup aditivo ao especialista, com o motor v3.2 como filtro

**Data:** 13/11/2026 (America/Sao_Paulo)  
**Escopo:** somente planejamento. Nada entra em `core/`, dashboard, EAs ou no painel. Nenhuma ordem, commit ou push.  
**Pasta:** `research/div_master/setup_v32/`  
**Origem:** rascunho do Gemini CLI (`agy.exe --mode plan`, 13/11 ~22:05 BRT), revisado contra o código e o snapshot ao vivo de 13/11. O texto bruto está em `gemini_rascunho.md`. Correções feitas na revisão estão na seção 13.

---

## 1. Premissas

- O especialista em produção (`ESP_DIV_V22_WIN`, rótulo *WIN Especialista V3.2*) **não muda**. Continua com 2 contratos e a regra atual.
- O motor v3.2 entra como **filtro e contexto**, não como ordem em toda marcação. Já está documentado que operar toda divergência isolada não tem edge (`sniper_direct`, `div_v3`; ver `SPEC_ESPECIALISTAS_5176.md`).
- Não reabrir a busca de ~20 mil combinações de 12/11. I3 foi reprovado; I5 e V1a ficam no máximo em sombra; `B_dw_ex10` ainda não teve validação independente.
- Ajuste e escolha **só em jan–jul**. Ago–nov pode ser reportado, mas não escolhe a regra (já contaminado). Validação final = paper live, não o OOS histórico.
- 13/11 é sanidade / exemplo de um pregão ao vivo. **Não se calibra regra olhando este dia.**

## 1.1 Decisões do usuário (13/11/2026, ~22:13, America/Sao_Paulo)

As quatro perguntas da seção 11 foram respondidas e ficam congeladas neste plano:

1. **Ativos:** pesquisar **WIN e WDO** (Teses 1 e 2 no WIN; Tese 3 no WDO, à parte, com `V32_PROD` sem módulo de abertura).
2. **Coexistência:** se o E22 já estiver posicionado, o add-on é bloqueado — **exceto** quando o E22 já está no break-even (`be_time` conhecido e a entrada do add-on é posterior). Nesse caso o add-on pode acrescentar **+1 contrato** na mesma direção. Sinal oposto continua bloqueado enquanto o E22 estiver aberto, mesmo depois do BE. Na mesma barra, o E22 tem prioridade.
3. **Saída do add-on:** alvo na **próxima Wall/MidWall** (S2b) ou na **NWE50** (S2a). O perfil S1 (sem alvo, só BE/tempo) **sai da grade de seleção**. Stop **além do pivô F2 + buffer** (WIN 30 pts, WDO 1,0 pt), abortando se o SL resultante for < 2 ticks ou > 300 / 10,5 pts — é a Saída B já documentada em `especialistas/bt.py`, congelada, sem otimizar o buffer. Tempo máximo 12 barras ou 17:25. Sem BE no add-on (a saída é alvo / stop / tempo).
4. **Fora deste estudo:** I5 e `B_dw_ex10` não entram na tabela nem na grade. A única linha de base obrigatória é o `ESP_DIV_V22_WIN` de produção (252 trades).

A grade efetiva fica: WIN 2 teses × 2 gatilhos × 2 saídas (S2a, S2b) = **8** configurações; WDO 2 âncoras × 2 gatilhos × 2 saídas = **8**; total **16**.

---

## 2. O que é o motor 3.2 e o que é o especialista

### 2.1 Motor oficial v3.2 (`V32_PROD`)

Implementação: `research/div_master/especialistas/modulo.py`, função `engine_v32` com

`V32_PROD = dict(f1="flow", reset=False, rep=True, used=False, open_module=False)`.

É o motor oficial da carteira 5176 desde 12/11/2026 (`SPEC_ESPECIALISTAS_5176.md`). O mesmo código alimenta o desenho no painel (`core/div_engines_view.py`, `POST /api/compass/divergencias_motor`), o filtro do Sniper (`WIN_DIV_WALL` / `WDO_DIV_WALL`, com `elig="all"`, sem exigir âncora) e o especialista.

Regras:

- Pivôs só do ZigZag causal `1,2 × ATR(14)` (piso 80 pts no WIN / 2,5 pts no WDO). **Sem módulo de abertura** (sem ZigZag `0,8 × ATR`, pivô curto L2/R1 até 09:35 nem semente até 09:20).
- **F1:** pivô da perna com a onda (Fluxo Smart Money) mais extrema da própria barra.
- **F2:** último extremo de preço confirmado, com `d * (w2 − w1) > 0,15 × mediana causal(|onda|)` (`k_v31`).
- Distância F1–F2 entre 2 e 48 barras; tolerância de preço 60 pts (WIN) / 2,0 (WDO).
- Sem reset: o mesmo F1 pode ancorar F2s sucessivos se o preço renovar o extremo (extensão da mesma perna). No painel, das extensões de um F1 aparece só a última.
- Elegibilidade `common` (o que o usuário vê com âncora): F2 a ≤ 150 pts (WIN) / 3,5 pts (WDO) de Wall ou MidWall, furo de até 220 / 6,0, **ou** extremo do dia depois das 09:30 (`day_tol` 30 / 1,0). MidWall conta como Wall.

O trecho de `research/div_master/v32/RESULTADOS.md` que fala em “decisão pendente / só no seletor do painel” está **desatualizado**.

### 2.2 O especialista (`ESP_DIV_V22_WIN`)

Código: `core/especialista_v22.py`. O ID “V22” ficou por compatibilidade; o motor é o v3.2 desde 12/11/2026. **Não existe especialista de WDO em produção.**

Regra atual (imutável neste plano):

- Sinal: `engine_v32` + `V32_PROD`, âncora Wall/MidWall ou extremo do dia (`elig="common"`).
- Gatilho Opção C em `modulo.triggers`: `WALL C1/C2` ou `EXTREMO VIOL/DUPLO`, na janela `max(j+1, conf) … j+3`.
- Descarta **super-confluência** (F2 com Wall/MidWall **e** extremo do dia).
- Conta `seq` por **direção**, incrementando a cada gatilho daquele lado — inclusive os que depois são descartados por `super`. Aceita só `seq <= 1` (1º e 2º gatilho do dia naquela direção).
- Entrada entre **10:00 e 15:55** (abertura da barra seguinte ao gatilho); um trade por vez.
- Contexto NWE50 (bw 8, mult 3): `ext50 > −0,5` e `slope50 > −0,5`.
- Saída: SL 200 pts, sem alvo, BE +180 → +20, no máximo 12 barras (sai na abertura da 13ª) ou 17:25.
- 2 contratos; custo 10 pts por contrato; stop em gap preenche 1 tick pior.

Métricas da **produção** (`especialista_v22.run`, 2 contratos, 02/01–11/11): 252 trades, R$ 9.214, DD R$ 656, Ret/DD **14,05**, jan–jul 7,50 / ago–nov 9,99. A busca às vezes cita um “E22” de 266 trades e Ret/DD 15,08 porque descarta `dup` antes de contar a ordem do dia — **não é a produção**. Toda comparação de carteira neste plano usa os 252 trades.

Carteira 5176 hoje: especialista + sistemáticas Sniper (`EST_*`, `WIN_E2`, `WIN_DIV_WALL`, `WDO_*`). Em 13/11, no `data/processed/portfolio_4_live_days.json`, as Sniper fizeram **0 trades**; só o especialista operou (1 trade).

---

## 3. Diagnóstico de 13/11

Os prints anexados não estavam no caminho informado no box. A reconstrução usou o snapshot ao vivo `GET /api/compass/all?date_str=2026-11-13` (barras M5 com `smart_swing_wave` + Walls do dia) e o próprio `modulo.engine_v32` / `especialista_v22.run`. As marcas batem com o que o usuário descreveu (X▼, W▼/W▲, XW▲) nas máximas e, no WDO, na mínima.

**Conclusão:** o motor já marca os extremos que ele viu. O buraco é a **regra de entrada / os filtros** do especialista no WIN, e a **ausência de especialista no WDO** — não a detecção.

### 3.1 WIN (WINZ26)

Open 172.900, máxima 174.430 (13:10), mínima 172.495 (barra 09:00), último 174.360. Walls próximas: 172.691, Mid 173.196, Wall 173.701, Mid 174.206, Wall 174.711.

| # | Direção | F1 → F2 (conf) | Preço F2 | Âncora | Gatilho Opção C | O que o especialista fez |
| :-: | --- | --- | ---: | --- | --- | --- |
| 1 | VENDA | 10:45 → 11:05 (11:10) | 173.825 | WALL | WALL/C2, 11:10 → entra 11:15 | **Operado (`seq=0`).** Entrada 173.425, saída 11:30 no BE +20, +10 pts líquidos (2 ct, R$ 2). NWE ext50=−0,12, slope50=−0,31. |
| 2a | VENDA | 10:35 → **11:50** (11:50) | **174.230** | WALL+EXTREMO (XW) | WALL/C1, 12:00 → entra 12:05 | **Recusado por `super=True`.** Mesmo assim consumiu `seq=1`. Houve extensão seguinte em 11:55 (174.390, conf 12:15), que não gerou gatilho próprio. |
| 2b | VENDA | 10:35 → 13:10 (13:20) | **174.430 (máxima do dia)** | EXTREMO DO DIA (X▼) | EXTREMO/DUPLO, 13:20 → entra 13:25 | **Recusado por `seq=2`** (3º gatilho de venda). O NWE50 às 13:25 passaria (ext 0,03, slope −0,22). |
| 3 | COMPRA | 15:45 → 16:00 (16:05) | 173.595 | WALL | WALL/C2, 16:05 → entra 16:10 | **Fora da janela 10:00–15:55.** Não é a mínima do dia. |

A mínima do WIN (172.495) foi a barra das 09:00. O motor oficial, sem módulo de abertura, não marcou compra ali; a onda das 09:15/09:20 ficou bem negativa no recuo — não havia divergência clara de fluxo no fundo da abertura.

A ironia da máxima: o gatilho das 12:05 (quase no topo, Wall + extremo) foi vetado justamente por ter **as duas âncoras**; o das 13:25, na máxima cravada, caiu porque os gatilhos anteriores — inclusive o `super` descartado — já tinham esgotado o `seq`. Um pregão ilustra o mecanismo; **não invalida sozinho** a estatística que levou a descartar `super` no E22.

### 3.2 WDO

Open 5.660, máxima 5.688,5 (18:15), mínima 5.647,5 (13:10), último 5.683,5.

| # | Direção | F1 → F2 (conf) | Preço F2 | Âncora | Gatilho | Diagnóstico |
| :-: | --- | --- | ---: | --- | --- | --- |
| 1 | VENDA | 10:05 → 11:10 (11:15) | 5.683,5 | EXTREMO DO DIA | EXTREMO/DUPLO, 11:15 → 11:20 | Máxima até então. Sem especialista de WDO. |
| 2 | COMPRA | 12:10 → 13:10 (13:10) | **5.647,5 (mínima do dia)** | WALL+EXTREMO | WALL/C2, 13:20 → 13:25, `super=True` | Mínima cravada. Sem especialista de WDO. |
| 3 | VENDA | 14:20 → 18:15 (18:20) | **5.688,5 (máxima da sessão)** | EXTREMO DO DIA | sem barra seguinte | 18:20, fora de qualquer janela. |

---

## 4. Teses / setups candidatos (lista curta)

Três teses, sempre com candidato prévio de `V32_PROD` e `elig="common"` (o que aparece no painel). Não operar toda marca.

### Tese 1 — `ADD_WIN_EXT_REC` (prioridade)

**Problema:** no v3.2 a perna se estende. As primeiras tentativas na Wall gastam `seq` (ou caem em `super`). Quando o preço crava o extremo da perna, o especialista já está bloqueado — como às 12:05 e 13:25 de 13/11.

**Filtro:** candidato com âncora de extremo do dia (vale `super=True`). O add-on só age nos sinais que o E22 **recusou por regra estrutural**: `super=True` **ou** `seq > 1`. A definição é causal: o mesmo fluxo de gatilhos do `especialista_v22.run`, no fechamento da barra. `seq` conta todo gatilho da direção, inclusive supers descartados e F1s diferentes — não só “extensão do mesmo F1”.

**Limite próprio:** no máximo 1 trade executado por direção por dia neste add-on.

**Gatilhos** (em `t ∈ [max(j+1, conf), j+3]`, entrada na abertura de `t+1`):

- **G1 (Opção C destravada):** o mesmo C1/C2/VIOL/DUPLO + NWE50 `ext50 > −0,5` e `slope50 > −0,5`. Isola se as travas `super` / `seq` estão deixando dinheiro na mesa.
- **G2 (rompimento da barra de sinal + virada de fluxo):** fechamento de `t` rompe a mínima (venda) ou a máxima (compra) da barra do pivô `j`, **e** `d * (wave[t] − wave[t−1]) > 0`.  
  *Nota:* o teste de rompimento da barra `j` já é o subtipo `DUPLO` da Opção C. O que G2 acrescenta é a virada da onda, e a aplicação também em candidatos de Wall (não só extremo). A grade precisa reportar a sobreposição G1∩G2 para não tratar os dois como independentes.

### Tese 2 — `ADD_WIN_REJ_NWE`

**Problema:** o motor confirma a divergência, mas a Opção C não dispara (ou atrasa), e o preço deixa rejeição na zona ou devolve um excesso na banda da NWE50.

**Filtro:** candidato `V32_PROD` / `common` que **não** tenha gerado entrada simultânea no E22.

**Gatilhos:**

- **G3 (rejeição na Wall + virada de fluxo):** a barra `t` (ou a própria `conf`) testa a zona, deixa pavio contra o extremo ≥ 40% do range, fecha a favor da reversão e a onda acelera a favor (`d * (wave[t] − wave[j]) > 0`). O limiar de 40% fica **congelado** (não se otimiza pavio).
- **G4 (retorno da banda NWE50):** o extremo do pivô `j` (ou `t−1`) chegou à banda externa (`ext50 <= −0,8`) e a barra `t` fecha de volta para dentro, com `d * (close[t] − close[j]) > 0`. Isto é o **oposto** do filtro do E22 (`ext50 > −0,5`): o E22 evita entrar contra tendência esticada; o G4 testa justamente o retorno quando a divergência v3.2 ocorre na banda. É hipótese, não fato.

### Tese 3 — `ADD_WDO_V32_CORE` (estudo separado)

O V1a de WDO dependia do módulo de abertura e teve Ret/DD de vitrine ~7 reduzido a ~3–4 no walk-forward; a recomendação de 12/11 foi só sombra (`wdo_v1a/RESULTADOS.md`). O motor oficial **não tem** módulo de abertura, então um add-on de WDO precisa se sustentar no ZigZag `1,2 × ATR` — como os sinais das 11:20 e 13:25 de 13/11.

- Sinal `V32_PROD`, `elig="common"`, janela 10:00–15:55, 1 contrato.
- Duas âncoras, congeladas: (A) só Wall; (B) Wall + extremo, incluindo `super=True`.
- Gatilhos: G1 vs G2 (os mesmos da Tese 1).
- Tem de passar no placebo de Walls deslocadas (o efeito real do V1a estava nas Walls verdadeiras).

---

## 5. Coexistência com o especialista

1. **Prioridade do E22:** se na mesma barra os dois disparam na mesma direção, **só o E22 entra**.
2. **Mesma direção com E22 já posicionado (decisão do usuário):** o add-on **não abre** enquanto o E22 estiver aberto e ainda não tiver atingido o BE. Depois do BE (`entrada do add-on > be_time`), o add-on pode acrescentar +1 contrato. Sem pirâmide além disso. Sinal oposto permanece bloqueado enquanto o E22 estiver aberto.
3. **Sinais opostos:** o add-on é **bloqueado**. Não faz hedge interno nem zera o especialista.
4. **Tamanho:** E22 permanece com 2 ct; add-on WIN 1 ct; add-on WDO (se for à sombra) 1 ct. No add-on: um trade aberto por vez; no máximo 2 trades executados por dia no WIN (e no máximo 1 por direção na Tese 1).
5. **Janela:** entrada 10:00–15:55; encerramento compulsório 17:25. Não reabrir o balde das 09h neste plano (o motor oficial não tem módulo de abertura; a mínima de 13/11 foi justamente às 09:00, sem divergência clara).

Não há conflito de posição com as Sniper neste desenho (o add-on só se amarra ao estado do E22). Sobreposição com `WIN_DIV_WALL` / `WDO_DIV_WALL` será **medida** no relatório, não usada para escolher a regra.

---

## 6. Stops, alvos e grade

Sem otimizar SL/TP numa grade fina. Parâmetros de saída congelados **antes** de ver jan–jul.

### 6.1 Saídas (congeladas pela decisão 3)

- **Stop (WIN e WDO):** além do pivô F2 + buffer (30 pts / 1,0 pt). Aborta se o SL for < 2 ticks ou > 300 / 10,5 pts.
- **S2a (NWE50):** alvo no toque da linha (`nwe50_line`) se a entrada estiver fora de `0,5 × meia-banda` e a linha estiver a favor por ≥ 4 ticks; senão, banda oposta (menos o front-run de 15 / 0,5). Se nenhum alvo válido, o trade não abre.
- **S2b (próxima Wall/MidWall):** alvo na próxima Wall ou MidWall a favor, menos o front-run, desde que a distância na entrada seja ≥ 1× o SL. Se não houver alvo válido, o trade não abre.
- **Tempo:** 12 barras ou 17:25. Sem BE no add-on.
- O perfil S1 (sem alvo) **não entra** na grade de seleção.

### 6.2 Orçamento da grade

- **WIN:** 2 teses × 2 gatilhos × 2 saídas (S2a, S2b) = **8** configurações, já com a regra de coexistência escolhida (liberar +1 depois do BE do E22).
- **WDO:** 2 âncoras × 2 gatilhos × 2 saídas (S2a, S2b) = **8** configurações.
- Total: **16 regras**, no espírito da SPEC (dezenas, não milhares).

Execução 100% causal: sinal no fechamento M5, entrada na abertura de `t+1`. Intrabar conservadora: abertura → extremo contra → extremo a favor → fechamento; na dúvida entre stop e alvo na mesma barra, **o stop ganha**. Custos: WIN 10 pts + 1 tick (5 pts) de slip em stop que não é a abertura; WDO 0,5 pt + 1 tick (0,5); R$ 0,20/pt no WIN e R$ 10,00/pt no WDO; 1 contrato no teste-base. Dados só do repositório, com o mesmo manifesto da pesquisa anterior. Nada de cache `.gemini`.

---

## 7. Protocolo de validação e critérios

### 7.1 Partição

- **IS (escolha):** 02/01/2026–31/07/2026.
- **Walk-forward interno no IS:** treino jan–abr, validação mai–jul. Descarta o que só funciona num trimestre.
- **OOS histórico 01/08–11/11:** apenas relatório. **Não escolhe** a variante.
- **12/11 e 13/11:** só sanidade mecânica (o código tem de reproduzir as marcas e o funil do especialista).

### 7.2 Placebos obrigatórios em jan–jul

1. **P1 — sem divergência:** o mesmo gatilho e o mesmo filtro NWE em pivôs ZigZag `1,2 × ATR` na Wall/extremo **sem** divergência v3.2. O candidato precisa superar P1 em PF e Ret/DD.
2. **P2 — direção invertida:** expectativa deve ser negativa.
3. **P3 — Walls deslocadas:** para variantes com âncora de Wall, deslocar +250 pts (WIN) / +5,0 pts (WDO), ou permutar Walls entre dias. (I3 foi reprovado exatamente porque o efeito sobrevivia com Walls falsas.)

### 7.3 Métricas

Standalone e carteira, em IS, WF interno e (só relatório) ago–nov: N, WR, PF, lucro, DD, Ret/DD, meses positivos, H1/H2.

Carteira incremental = `ESP_DIV_V22_WIN` (2 ct, os 252 trades de produção) + add-on (1 ct): correlação do PnL diário, % de barras com os dois posicionados, ganho marginal de Ret/DD e variação do DD em jan–jul.

Estresse: custo dobrado (20 pts no WIN / 1,0 pt no WDO) + 2 ticks de slip no stop.

### 7.4 Portão para sombra / paper live

Tudo abaixo é pré-registrado e avaliado **só em jan–jul**. Nenhuma barra é rebaixada depois de ver o resultado.

1. **Amostra:** N ≥ 40 em jan–jul. Se a Tese 1 (só descartes do E22) ficar abaixo disso, **ela não avança** — o diagnóstico da Etapa 1 apenas reporta o N disponível. O critério não muda no meio do caminho.
2. **Qualidade standalone:** PF ≥ 1,35, Ret/DD ≥ 4,0, jan–abr e mai–jul positivos, pelo menos 5 dos 7 meses de jan–jul no azul.
3. **Placebos:** PF e Ret/DD melhores que P1 e, quando couber âncora de Wall, que P3. P2 negativo.
4. **Valor na carteira:** correlação diária com o E22 de produção ≤ 0,35; e (a) não aumentar o DD do E22 em mais de 15% em R$, **ou** (b) o Ret/DD combinado de jan–jul ficar acima dos 7,50 do especialista isolado.
5. **Estresse:** PF > 1,10 com custo/slip dobrados, ainda em jan–jul.
6. **Estágio final:** ninguém liga ordem real a partir do backtest. Quem passar o portão vai a **sombra / paper live por ≥ 20 pregões**, no mesmo espírito da recomendação de 12/11 para I5 e V1a.

Se ninguém passar, a recomendação é **manter só o especialista atual**.

---

## 8. O que não fazer

1. Não alterar nem reotimizar o `ESP_DIV_V22_WIN`.
2. Não ativar o I3 (`research/div_master/win_especialista/VALIDACAO.md`).
3. Não tratar como prontos para produção os números de vitrine de I5 (Ret/DD 5,46), V1a (~7) ou `B_dw_ex10` (8,96). I5 e V1a já tiveram o desconto de seleção medido; `B_dw_ex10` ainda não passou por auditoria independente.
4. Não religar `open_module=True` por trás dos panos. O add-on tem de usar os candidatos que o usuário vê no painel.
5. Não usar 13/11 nem ago–nov para calibrar parâmetro, pavio, SL ou janela.
6. Não operar toda marca v3.2.

---

## 9. Riscos

- **Super-confluência:** em 13/11, `super=True` às 12:05 no WIN e às 13:25 no WDO teria pego quase o extremo. Na construção do E22, descartar `super` melhorou o histórico — muitas vezes Wall + extremo do dia é *breakout* que atropela. Se G1 degradar em jan–jul, G2 (rompimento da barra + virada de fluxo) é o filtro candidato para separar recaptura de atropelo. Um pregão não prova a regra inversa.
- **Amostra curta na Tese 1:** por construção ela só pega o que o E22 recusou. Pode não chegar a 40 trades.
- **Sobreposição G1/G2:** parte de G2 já está dentro do `DUPLO`.
- **WDO sem módulo de abertura:** menos sinais cedo; o V1a não serve de atalho.
- **Onda ao vivo × histórica:** G2 e G3 leem `wave[t] − wave[t−1]`. O alerta 2.4 do `PLANO_MESTRE.md` (em 11/11, `inst_aggr_delta` / `inst_pass_delta` do WIN perto de zero depois das 10:05 no motor ao vivo) **ainda não tem conferência registrada**. Antes da sombra, comparar barra a barra a onda gravada ao vivo com a reconstruída do `.min` em pelo menos 3 pregões.
- **Overfitting residual:** mesmo com grade curta, 16 regras ainda podem sortear um vencedor. Por isso o portão exige placebos, WF interno e paper live.

---

## 10. Ordem de trabalho (só depois de aprovado, só em pesquisa)

Tudo em `research/div_master/setup_v32/`. Zero alteração em `core/`, dashboard ou configs.

1. **Etapa 1 — diagnóstico de descarte** (`diagnostico_descartes.py`): em jan–jul (ago–nov só informativo), listar os candidatos `V32_PROD` que o E22 recusou, com o motivo (`super`, `seq > 1`, NWE, janela, já posicionado). Reproduzir 13/11 exatamente.
2. **Etapa 2 — motor do add-on** (`motor_addon.py`): G1–G4 e saídas S2a/S2b, acoplados ao estado de `especialista_v22.run` (liberar +1 depois do BE; sinal oposto bloqueado).
3. **Etapa 3 — grade IS + placebos** (`avaliar_is.py`): 8 + 8 configurações em jan–jul, WF interno, P1–P3, estresse de custo.
4. **Etapa 4 — relatório cético** (`RESULTADOS.md`): tabela IS / WF / placebos / correlação com o E22 de 252 trades, mais leitura informativa de ago–nov e de 12–13/11. Se ninguém passar o portão 7.4, a recomendação é não ligar nada.

---

## 11. Perguntas ao usuário — respondidas em 13/11/2026

| # | Pergunta | Decisão |
| :-: | --- | --- |
| 1 | Só WIN, ou também WDO? | **WIN e WDO.** |
| 2 | Bloquear o add-on com o E22 posicionado, ou liberar +1 ct depois do BE? | **Liberar +1 depois do BE.** Fora isso, bloqueado enquanto o E22 estiver aberto. Na mesma barra, o E22 ganha. Sinal oposto continua bloqueado. |
| 3 | Saída estilo especialista (S1) ou alvo na NWE/Wall (S2)? | **Alvo na próxima Wall ou na NWE.** Stop além do F2 + buffer. S1 fora da grade. |
| 4 | Incluir I5 e `B_dw_ex10`? | **Não.** Fora deste estudo. |

Detalhes operacionais na seção 1.1.

## 12. Próximo passo

Com as decisões congeladas, a pesquisa (Etapas 1–4) roda em `research/div_master/setup_v32/`. O relatório vai para `RESULTADOS.md`. Nada é commitado nem ligado no painel até o portão da seção 7.4 ser avaliado.

## 13. Notas da revisão (rascunho do Gemini → este plano)

O Gemini (`agy.exe`) acertou o diagnóstico, as teses e o protocolo. Ajustes feitos contra o código e os dados:

- Marca WIN 2a: F2 é **11:50 a 174.230** (gatilho 12:00), não 11:55 a 174.390.
- A janela do E22 é **10:00–15:55** (`tm < 16:00`), não “16:10 ≥ 16:00”.
- `seq` incrementa a cada gatilho da direção, inclusive supers descartados e F1s diferentes — não “WALL e EXTREMO do mesmo pivô”.
- Caminho certo da validação: `research/div_master/win_especialista/VALIDACAO.md` (não `especialistas/win_especialista/`).
- SL 7,0 / BE +6 → +1 no WDO **não existe** na pesquisa; o default documentado do V1a é SL 14, sem BE.
- G2 sobrepõe o subtipo `DUPLO` da Opção C; isso ficou explícito.
- A frase “extremos do dia costumam devolver à NWE50” foi rebaixada a hipótese.
- Incluído o alerta 2.4 (onda ao vivo × `.min`), ainda sem conferência.
- Links `file:///` trocados por caminhos relativos do repositório.
