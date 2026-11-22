# Tarefa: rascunhar um PLANO (somente planejamento) de setup complementar ao especialista, usando o motor de divergência v3.2

Você é um pesquisador quantitativo cauteloso. Trabalhe em modo SOMENTE LEITURA.

## Restrições absolutas
- NÃO edite nenhum arquivo. NÃO crie arquivos. NÃO apague nada. NÃO faça commit, push, nem envie ordens.
- NÃO use flags de auto-aprovação. NÃO altere core/, dashboard, EAs, configs de produção.
- Sua única saída é o texto Markdown do plano, em português do Brasil, no stdout.
- Se precisar consultar o repositório, apenas LEIA. Não rode backtests longos nem instale nada.
- Não invente números. Se citar métricas, use só as que estão nos arquivos abaixo ou neste briefing. Se não tiver o número, escreva "a medir".

## Pedido do usuário (13/11/2026 ~21:56, America/Sao_Paulo)
"o dia de hoje foi lindo, as marcações pegaram as máximas e mínimas dos ativos, mas não temos nenhuma regra para pegar esses trades; por que não tentamos com o Gemini criar um setup para operar isso, deixando o especialista ainda operando mas usando o motor 3.2 para operar ainda mais um pouco usando as divergências como filtro e outras possibilidades para dar o gatilho de entrada. vamos planejar isso"

Ele enviou prints do painel 5176 em 13/11 (WIN M5 e WDO M5 com Fluxo Smart Money) mostrando marcas V3.2 do tipo X▼ (extremo do dia), W▼/W▲ (Wall) e XW▲ (Wall+extremo) nas máximas e mínimas.

Objetivo: um plano de setup ADITIVO (add-on), não um substituto do especialista. O especialista continua operando como está. O motor v3.2 entra como filtro/contexto, e testamos outros gatilhos de entrada para capturar mais desses extremos.

## O que já é fato no código (verifique lendo se quiser)

### Motor 3.2 / V3.2
- Implementação: `research/div_master/especialistas/modulo.py`, função `engine_v32` com `V32_PROD = dict(f1="flow", reset=False, rep=True, used=False, open_module=False)`.
- É o motor oficial da carteira 5176 desde 12/11/2026 (decisão do usuário, `SPEC_ESPECIALISTAS_5176.md`).
- Regras: F1 = pivô da perna com a onda (Fluxo Smart Money) mais extrema; F2 = último extremo de preço; uma divergência por perna (extensão se o preço renovar o extremo com o mesmo F1); pivôs só do ZigZag 1,2×ATR14; SEM módulo de abertura (sem ZigZag 0,8×ATR, L2/R1 nem semente).
- Elegibilidade `common`: F2 a ≤ 150 pts (WIN) / 3,5 pts (WDO) de Wall ou MidWall, com furo de até 220 / 6,0, OU extremo do dia depois das 09:30 (day_tol 30 / 1,0). MidWall conta como Wall.
- Visualização: `core/div_engines_view.py` e `POST /api/compass/divergencias_motor`. No painel, das extensões do mesmo F1 aparece só a última.
- O Sniper (WIN/WDO_DIV_WALL) usa o mesmo motor com `elig="all"` (sem exigir âncora) como FILTRO, não como entrada própria.
- Documentação do motor: `research/div_master/v32/RESULTADOS.md` (trecho "decisão pendente / só no seletor" está DESATUALIZADO; o motor já é o oficial).

### O especialista (já em produção no painel 5176)
- ID: `ESP_DIV_V22_WIN`, rótulo "WIN Especialista V3.2". Código: `core/especialista_v22.py`.
- O ID "V22" ficou por compatibilidade; o motor é o v3.2 desde 12/11/2026.
- Regra atual (NÃO ALTERAR neste plano):
  - sinal: `engine_v32` + `V32_PROD`, âncora Wall/MidWall ou extremo do dia;
  - gatilho Opção C (a)+(b) em `modulo.triggers`: WALL C1/C2 ou EXTREMO VIOL/DUPLO, janela até j+3;
  - descarta super-confluência (F2 com Wall E extremo do dia);
  - no máximo o 2º gatilho do dia em cada direção (`seq <= 1`);
  - entrada 10:00–15:55, a mercado na abertura da barra seguinte ao gatilho, um trade por vez;
  - contexto NWE50 (bw 8, mult 3): ext50 > −0,5 e slope50 > −0,5;
  - saída: SL 200 pts, sem alvo, BE +180 → +20, máximo 12 barras (sai na abertura da 13ª) ou 17:25;
  - 2 contratos; custo 10 pts/contrato; stop sem gap preenche 1 tick pior.
- Não existe especialista de WDO em produção. O V1a de WDO foi pesquisado e a validação independente recomendou só sombra, e ele depende do módulo de abertura (que o motor oficial não tem).
- Pesquisa e validação: `research/div_master/especialistas/`, `win_especialista/RESULTADOS.md`, `win_especialista/VALIDACAO.md`, `wdo_v1a/RESULTADOS.md`.
- Métricas do especialista de PRODUÇÃO (`core/especialista_v22.run`, 2 ct, 02/01–11/11): 252 trades, R$ 9.214, DD R$ 656, Ret/DD 14,05, jan–jul 7,50 / ago–nov 9,99. (A busca às vezes cita um "E22" de 266 trades / Ret/DD 15,08 porque descarta `dup` antes de contar a ordem do dia — não é a produção.)

### Carteira 5176 hoje
- Especialista + sistemáticas Sniper (EST_*, WIN_E2, WIN_DIV_WALL, WDO_* incluindo WDO_DIV_WALL).
- Auditoria anterior: o painel 5176 inflava números (lookahead, DD diário, filtros no ano inteiro). Sniper corrigido histórico: PF 1,95, Ret/DD 14,2, 287 trades. Protocolo: IS = jan–jul; OOS = ago–nov JÁ FOI USADO várias vezes (contaminado) — validação final = paper live.
- Em 13/11, no `portfolio_4_live_days.json`: TODAS as sistemáticas Sniper fizeram 0 trades. Só o especialista operou (1 trade).

### O que já foi tentado como complemento e NÃO deve ser refeito do zero
Em 12/11 houve busca grande (~20 mil combinações) de complementares WIN (`I3`, `I5`, `I2`, `I1`) e o V1a de WDO, mais rompimento de Wall + fluxo (`flow_breakout`, `B_dw_ex10` / `B_dw_vol11`).
Validação independente (`win_especialista/VALIDACAO.md`):
- I3: NÃO aprovar (walk-forward ruim, OOS fraco, efeito aparece com Walls falsas, piora ago–nov da carteira). Fica dentro do que o teste nulo da busca produz.
- I5: efeito real mas fraco; expectativa ~Ret/DD 1, não 5,46; candidato a sombra, não à carteira.
- V1a WDO: efeito real nas Walls, mas Ret/DD de vitrine 7 está inflado (WF ~3–4); depende do módulo de abertura.
- Recomendação de 12/11: não ativar nada agora; se acompanhar, I5 e V1a em sombra ≥ 20 pregões.
`flow_breakout/RESULTADOS.md`: rompimento de Wall principal + fluxo no WIN teve edge (B_dw_ex10 Ret/DD 8,96 base, mas PF ~1,26 e estresse pesado cai para 1,88). WDO seguidor/rompimento: nenhum hit. Isso NÃO foi validado de forma independente ainda (ao contrário de I3/I5/V1a). Correlação de B_dw_ex10 com E22 = +0,211.

Lição já documentada em `SPEC_ESPECIALISTAS_5176.md` e `PLANO_MESTRE.md`: entrar em toda divergência não deu lucro (`sniper_direct`, `div_v3`). A vantagem do Sniper corrigido veio de setup + divergência como filtro. A âncora "extremo do dia" dá cobertura, não precisão (61% das válidas rotuladas, mas "extremo ou Wall" também cobre ~87% das falsas).

### Respostas antigas do usuário (11/11, ainda valem como default)
- "Na Wall" = até 150 pts; MidWall conta.
- Extremo do dia também vale mesmo fora dos 150 pts.
- Em tese só preço × Smart Money.
- Testar 3 entradas: fechamento da barra de sinal, rompimento da barra de sinal, limite na Wall.
- Alvo inicial: próxima Wall, ou NWE, ou banda da NWE.
- Rompimento: entrada na aceitação após o reteste, não no 1º fechamento.

## Sanidade de 13/11 (reconstruída do snapshot ao vivo `/api/compass/all?date_str=2026-11-13`, barras M5 com `smart_swing_wave`, motor `V32_PROD`, elig=common)
WIN (WINZ26): open 172.900, máxima 174.430 (13:10), mínima 172.495 (barra 09:00), último 174.360. Walls próximas: 172.691, Mid 173.196, Wall 173.701, Mid 174.206, Wall 174.711.

Marcas visuais V3.2 (1 por perna) no WIN:
1. VENDA F1 10:45 → F2 11:05 conf 11:10, px 173.825, âncora WALL. Único trade do especialista: entrada 11:15 a 173.425, saída 11:30 no BE +20, +10 pts (2 ct, R$ 2). NWE ext50=−0,12 slope50=−0,31, gatilho WALL/C2.
2. VENDA F1 10:35 → F2 13:10 conf 13:20, px 174.430, âncora EXTREMO DO DIA — é a MÁXIMA do dia. Extensões intermediárias: 11:50 e 11:55 (WALL+EXTREMO, 174.230 / 174.390). Gatilho 12:00 WALL/C1 SUPER=True (descartado pela regra de super-confluência). Gatilho 13:20 EXTREMO/DUPLO, entrada 13:25, recusado porque seq=2 (3º gatilho na venda). NWE no 13:25 passaria (ext 0,03, slope −0,22). Esta é a operação "bonita" que o usuário viu e o especialista não pegou. Ironia: a super-confluência (Wall + extremo) — teoricamente a melhor âncora — é exatamente o que a regra atual descarta.
3. COMPRA F1 15:45 → F2 16:00 conf 16:05, px 173.595, âncora WALL. Gatilho 16:05, entrada 16:10 — fora da janela (depois de 15:55). Não é a mínima do dia.

A mínima do WIN (172.495) foi a barra das 09:00. O motor oficial sem módulo de abertura não marcou divergência de compra ali. A onda das 09:15/09:20 ficou bem negativa no recuo, então não é óbvio que houvesse divergência de compra no fundo.

WDO: open 5.660, máxima 5.688,5 (18:15), mínima 5.647,5 (13:10), último 5.683,5.
1. VENDA F1 10:05 → F2 11:10 conf 11:15, px 5.683,5, EXTREMO DO DIA (máxima até então). Gatilho EXTREMO/DUPLO 11:15, entrada 11:20. Não há especialista de WDO em produção.
2. COMPRA F1 12:10 → F2 13:10 conf 13:10, px 5.647,5, WALL+EXTREMO — é a MÍNIMA do dia. Gatilho 13:20 WALL/C2, entrada 13:25, mas super=True. Sem especialista de WDO.
3. VENDA F1 14:20 → F2 18:15 conf 18:20, px 5.688,5, EXTREMO DO DIA — máxima da sessão, tarde demais (sem barra seguinte).

Sniper-style (`elig=all`) no WIN acrescenta só uma extensão extra (11:40); no WDO é igual ao `common`.

## O que o plano precisa conter
1. Diagnóstico curto de 13/11: o motor já marca os extremos; o buraco é REGRA DE ENTRADA / FILTROS do especialista (e a ausência de especialista no WDO), não a detecção.
2. Hipóteses objetivas, poucas, testáveis, alinhadas ao que o usuário pediu (divergência como filtro + outros gatilhos), sem reabrir a busca de 20 mil combinações:
   - Tratar como candidato principal o caso "marca no extremo do dia (e/ou Wall+extremo) que o E22 recusou por super-confluência ou seq".
   - Gatilhos alternativos à Opção C (escolher um conjunto CURTO e justificado; o usuário citou: rompimento da barra de sinal, confirmação M1, virada de fluxo, candle de rejeição na Wall, toque da banda NWE, VWAP). Não precisa testar todos de uma vez.
   - Add-on de WDO, se fizer sentido, separado, ciente de que V1a depende do módulo de abertura e o motor oficial não o tem.
   - NÃO propor operar toda marca V3.2.
3. Regras de coexistência com o especialista (imutável): mesma direção (sobreposição), sinais opostos, exposição máxima, tamanho (sugerir 1 contrato no add-on vs 2 do E22), um trade do add-on por vez, o que fazer se o E22 já está posicionado, janelas de horário.
4. Stops e alvos (defaults do usuário + o que já funciona no E22). Evitar otimizar SL/TP numa grade enorme.
5. Grade de teste LIMITADA (orçamento no espírito da SPEC: da ordem de dezenas, não milhares), 100% causal (sinal no fechamento, entrada na abertura seguinte; execução M1; stop antes do alvo; gap de stop = 1 tick pior). Custos: WIN 10 pts, WDO 0,5 pt, 1 tick de slip no stop. 1 contrato no teste-base.
6. Protocolo de validação honesto:
   - Ajuste e escolha só em IS jan–jul.
   - Ago–nov pode ser REPORTADO mas não pode escolher a regra (já contaminado).
   - Placebos: (a) mesmos gatilhos em pivôs da zona SEM divergência; (b) direção invertida; (c) se for o caso, Walls deslocadas.
   - Métricas: trades, WR, PF, lucro, DD, Ret/DD, consistência mensal, H1/H2, correlação diária e sobreposição temporal com o E22 de produção (252 trades, não o E22 da busca).
   - Estresse de custo/slip.
   - Walk-forward interno em jan–jul se a grade tiver mais de um candidato.
   - Critérios de aceitação ANTES de paper live. Não usar OOS contaminado como critério de aprovação.
   - Validação final = paper live (≥ 20 pregões), sem commitar nem ligar no painel neste plano.
7. O que NÃO fazer: reotimizar o E22; ligar I3; tratar números de vitrine de I5/V1a/B_dw_ex10 como prontos para produção; usar lookahead; ajustar a regra olhando 13/11 (13/11 é só sanidade / exemplo, um pregão live, fora de amostra informal).
8. Ordem de trabalho (etapas) e arquivos sugeridos em `research/div_master/setup_v32/` (só pesquisa).
9. Até 4 perguntas objetivas para o usuário (as que realmente travam o plano). Sugira um default para cada uma.

Estrutura sugerida do Markdown:
- Título e premissas
- O que é o motor 3.2 e o especialista
- Diagnóstico 13/11
- Teses / setups candidatos (lista CURTA, nomes estáveis, regra de cada um em linguagem operacional)
- Coexistência
- Protocolo de teste e critérios
- Riscos (overfitting, OOS contaminado, módulo de abertura, dado ao vivo da onda)
- Perguntas ao usuário
- Próximo passo (não implementar ainda)

Seja concreto e cético. Prefira uma tese clara a um cardápio. Apontar a ironia da super-confluência em 13/11 é válido, mas um pregão não prova a regra inversa.
