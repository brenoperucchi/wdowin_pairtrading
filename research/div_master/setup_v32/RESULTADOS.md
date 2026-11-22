# Resultados — Add-on do motor v3.2 (pesquisa)

**Data:** 13/11/2026 (America/Sao_Paulo)  
**Escopo:** só pesquisa em `research/div_master/setup_v32/`. Nada foi alterado em `core/`, dashboard ou EAs. Nenhuma ordem, commit ou push.  
**Decisões congeladas (usuário, 13/11 ~22:13):** WIN e WDO; add-on libera +1 contrato depois do BE do `ESP_DIV_V22_WIN`; saída com alvo na NWE50 (S2a) ou na próxima Wall/MidWall (S2b); stop além do F2 + buffer (30 / 1,0 pt, aborta se SL < 2 ticks ou > 300 / 10,5); I5 e `B_dw_ex10` fora deste estudo.  
**Motor:** `modulo.engine_v32` + `V32_PROD`, `elig="common"`. Execução M1 causal (`bt.sim`: abertura → extremo contra → extremo a favor → fechamento; stop antes do alvo; slip de 1 tick no stop). Custo 10 pts (WIN) / 0,5 pt (WDO), 1 contrato no add-on. Janela 10:00–15:55, no máximo 12 barras ou 17:25. Sem BE no add-on.  
**Escolha só em jan–jul.** Ago–nov é relatório (contaminado). 13/11 é só sanidade mecânica, com M5 do snapshot ao vivo (não há M1 no repositório depois de 11/11).

Scripts: `motor_addon.py`, `avaliar.py`, `diagnostico.py`. Grade bruta: `results/grade.csv`.

---

## 0. Veredito

**Nenhuma das 16 configurações passa no portão pré-registrado.** A recomendação é **não ligar nenhum add-on** e manter só o especialista de produção.

O E22 de produção, reexecutado aqui com `core/especialista_v22.run`, reproduz os números oficiais: **252 trades, R$ 9.214, DD R$ 656, Ret/DD 14,05**, jan–jul 7,50 / ago–nov 9,99 (11/11 meses).

---

## 1. Funil do especialista (contexto da Tese 1)

Em 02/01–11/11 o motor gerou **1.192 gatilhos Opção C** no WIN; o E22 **entrou em 252**. Em jan–jul: **844 gatilhos, 173 entradas**.

Os recuses mais comuns em jan–jul (um gatilho pode ter mais de um motivo):

| Motivo (conjunto) | Gatilhos IS |
| --- | ---: |
| Só `super` | 120 |
| `super` + `seq` (sem NWE/janela) | 168 |
| Só `seq` | 53 |
| Só NWE | 35 |
| Só janela | 21 |
| Só ocupado | 11 |
| Outras combinações (super/seq + NWE/janela/ocupado) | restante até 844 − 173 |

A Tese 1 só aproveita recusa estrutural (`super` ou `seq`) com NWE ainda válido e dentro da janela. Por isso o giro dela é pequeno (41 trades em jan–jul no G1, 24 no G2).

---

## 2. Grade WIN — `ADD_WIN_EXT_REC` (Tese 1) e `ADD_WIN_REJ_NWE` (Tese 2)

Valores em R$ no add-on (1 contrato). IS = jan–jul; H1 = jan–abr; H2 = mai–jul; OOS = ago–nov (só relatório).

| Config | N IS (H1/H2) | PF IS | Ret/DD IS | H1 / H2 (R$) | Meses+ IS | N OOS | OOS (R$) | Ret/DD OOS | Portão |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| T1 G1 S2a (NWE) | 41 (18/23) | 0,94 | −0,21 | −248 / +184 | 3/7 | 13 | +215 | 1,91 | **reprova** |
| T1 G1 S2b (Wall) | 41 (18/23) | 0,76 | −0,87 | −238 / −25 | 2/7 | 13 | +61 | 0,54 | **reprova** |
| T1 G2 S2a | 24 (11/13) | 0,73 | −0,51 | +85 / −250 | 1/5 | 2 | +26 | 0,41 | **reprova** |
| T1 G2 S2b | 24 (11/13) | 1,34 | 0,62 | +287 / −104 | 3/5 | 2 | +64 | 1,01 | **reprova** |
| T2 G3 S2a | 39 (19/20) | 1,03 | 0,06 | −32 / +53 | 4/7 | 13 | +111 | 0,56 | **reprova** |
| T2 G3 S2b | 37 (17/20) | 1,33 | 0,96 | +78 / +153 | 5/7 | 13 | −93 | −0,53 | **reprova** (a menos ruim) |
| T2 G4 S2a | 0 | — | — | — | — | 0 | — | — | **reprova** |
| T2 G4 S2b | 0 | — | — | — | — | 0 | — | — | **reprova** |

**T2 G4** praticamente não existe: em jan–jul há 886 candidatos v3.2 e só 6 toques crus no gatilho de retorno da banda (`ext50 ≤ −0,8` + fecha para dentro, na janela de 3 barras). Depois de horário, coexistência e aborto de saída, restam **0 trades**. O gatilho, como estava congelado, é estreito demais para ser um setup.

A configuração **menos ruim** é T2 G3 S2b (rejeição na Wall + alvo na próxima Wall): H1 e H2 positivos, 5/7 meses, correlação com o E22 ≈ 0, estresse PF 1,18, supera os placebos P1 e P3, e na carteira o Ret/DD de jan–jul iria a 7,85 (DD do E22 inalterado). Ainda assim **falha o portão**: N 37 < 40, PF 1,33 < 1,35 e, principalmente, Ret/DD 0,96 << 4. Em ago–nov (só relatório) o lucro vira −R$ 93. O critério **não foi rebaixado** depois de ver o número.

T1 G1 (Opção C destravada no que o E22 recusou) é **negativa em jan–jul**. Liberar `super` e `seq` com o mesmo gatilho do especialista, só que com alvo estrutural, não paga. T1 G2 S2b chega perto em PF (1,34) mas com só 24 trades no IS e H2 negativo.

---

## 3. Placebos e estresse (WIN)

| Config | P1 (sem divergência) PF / Ret/DD IS | P2 invertida (R$ IS) | P3 Walls +250 pts PF / Ret/DD IS | Estresse 2×custo+2 ticks PF IS | Corr. diária vs E22 |
| --- | --- | ---: | --- | ---: | ---: |
| T1 G1 S2a | 1,03 / 0,06 | −260 | 1,05 / 0,22 | 0,86 | +0,07 |
| T1 G1 S2b | **1,66 / 1,64** | −313 | 1,17 / 0,76 | 0,69 | +0,13 |
| T1 G2 S2a | 1,30 / 0,30 | −262 | 0,74 / −0,50 | 0,65 | 0,00 |
| T1 G2 S2b | 1,30 / 0,30 | −43 | 0,83 / −0,33 | 1,22 | −0,02 |
| T2 G3 S2a | 0,58 / −0,57 | −320 | 0,95 / −0,12 | 0,90 | −0,03 |
| T2 G3 S2b | 0,61 / −0,65 | −131 | 0,94 / −0,16 | 1,18 | −0,01 |
| T2 G4 | (sem trades reais) | 0 | — | — | — |

Leitura importante: em T1 G1 S2b o placebo **sem divergência** (PF 1,66, Ret/DD 1,64) **ganha do sinal real** (PF 0,76, Ret/DD −0,87). Nesses descartes do E22, o filtro de divergência v3.2 não é a fonte do resultado — quando muito, atrapalha. A direção invertida é negativa na maior parte das linhas (bom sinal de que não há um viés óbvio de preenchimento), mas isso sozinho não salva a tese.

---

## 4. Carteira WIN (E22 2 ct + add-on 1 ct), só jan–jul para decisão

E22 isolado em jan–jul: Ret/DD **7,50**, DD R$ 656 (2 contratos).

| Add-on | Ret/DD IS combinado | DD IS combinado (R$) | Ret/DD cheio (relato) | Δ vs E22 |
| --- | ---: | ---: | ---: | --- |
| T1 G1 S2a | 6,43 | 755 | 12,41 | piora Ret/DD e o DD |
| T1 G1 S2b | 6,19 | 752 | 11,98 | piora |
| T1 G2 S2a | 7,24 | 656 | 13,83 | piora leve o Ret/DD |
| T1 G2 S2b | 7,78 | 656 | 14,42 | sobe um pouco, mas o add-on isolado não passa no portão |
| T2 G3 S2a | 7,49 | 659 | 14,18 | praticamente empate |
| T2 G3 S2b | 7,85 | 656 | 14,26 | melhor incremental, insuficiente no standalone |

Sobreposição temporal é baixa (1 a 6 trades do add-on a ≤ 30 min de um E22 na mesma direção). A coexistência “+1 depois do BE” quase não é usada: na prática o add-on entra com o E22 já *flat*.

---

## 5. Grade WDO — `ADD_WDO_V32_CORE`

Todas as 8 linhas são **fortemente negativas** em jan–jul e em ago–nov. PF IS entre 0,52 e 0,80; Ret/DD IS entre −0,65 e −0,96; no máximo 3/7 meses positivos. O prejuízo no IS vai de cerca de R$ 1.175 a R$ 2.925 (1 contrato).

| Config | N IS | PF IS | Ret/DD IS | H1 / H2 (R$) | Meses+ | OOS (R$) | Ret/DD OOS | Portão |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Wall · G1 · S2a | 184 | 0,62 | −0,93 | −2.401 / −524 | 1/7 | −1.530 | −0,77 | **reprova** |
| Wall · G1 · S2b | 179 | 0,70 | −0,87 | −2.020 / −255 | 3/7 | −1.090 | −0,70 | **reprova** |
| Wall · G2 · S2a | 120 | 0,52 | −0,96 | −1.011 / −1.457 | 1/7 | −1.000 | −0,75 | **reprova** |
| Wall · G2 · S2b | 118 | 0,63 | −0,75 | −1.110 / −760 | 2/7 | −1.020 | −0,73 | **reprova** (P2 invertida **positiva**, +375) |
| Wall+Ext · G1 · S2a | 216 | 0,69 | −0,94 | −2.407 / −269 | 1/7 | −2.064 | −0,84 | **reprova** |
| Wall+Ext · G1 · S2b | 211 | 0,76 | −0,87 | −2.145 / +50 | 3/7 | −1.715 | −0,81 | **reprova** |
| Wall+Ext · G2 · S2a | 157 | 0,70 | −0,94 | −843 / −1.018 | 2/7 | −1.478 | −0,92 | **reprova** |
| Wall+Ext · G2 · S2b | 153 | 0,80 | −0,65 | −1.050 / −125 | 3/7 | −1.455 | −0,89 | **reprova** |

Os placebos P1 (sem divergência) e P3 (Walls +5 pts) também são negativos, e em várias linhas o P1 é *menos ruim* que o sinal real. Na variante Wall · G2 · S2b a direção invertida **ganha** no IS — o oposto do que um edge direcional exigiria.

Isso é coerente com a validação do V1a: o efeito no WDO dependia do **módulo de abertura**, que o motor oficial não tem. Operar as marcas `V32_PROD` do dólar, com Opção C ou rompimento da barra, **não transfere** aquele resultado. Juntar qualquer uma dessas linhas ao E22 só aumentaria o DD da carteira.

---

## 6. Walk-forward interno (escolha em jan–abr, medida em mai–jul)

Não usamos ago–nov para escolher.

- **WIN:** a melhor de jan–abr é T1 G2 S2b (Ret/DD H1 3,87, só 11 trades). Em mai–jul faz Ret/DD **−0,35** (−R$ 104). Mediana das 8 linhas em mai–jul: 0; só 3/8 positivas.
- **WDO:** “melhor” de jan–abr ainda é negativa (T3B G2 S2a, Ret/DD −0,59). Em mai–jul segue negativa (−0,88). Só 1/8 linhas tem H2 > 0.

Nenhum vencedor interno sobrevive a mai–jul com qualidade.

---

## 7. Sanidade de 13/11

Reprodução do funil do E22 no snapshot ao vivo: venda 11:15, BE às 11:25, saída 11:30 — igual ao `portfolio_4_live_days.json`.

A Tese 1 G1 **passaria no filtro e na coexistência** nas duas marcas que o usuário viu e o especialista não operou (o E22 já estava *flat*):

- 12:05, venda, recusa por `super` (Wall+extremo), NWE ok (ext 0,57, slope −0,45).
- 13:25, venda na máxima do dia, recusa por `seq`, NWE ok (ext 0,03, slope −0,22).

Isso **não** significa que o add-on teria pego um bom trade. Com as saídas congeladas, uma simulação só em M5 (sem M1, portanto apenas ilustrativa) mostra:

- **12:05:** entrada 174.115, F2 174.230, stop 174.260 (SL 145, válido). A própria barra das 12:05 foi a 174.335 e **estoparia no mesmo candle** (~−160 pts líquidos, 1 ct). A perna ainda ia fazer a máxima às 13:10 (174.430).
- **13:25:** entrada 174.145, F2 174.430, stop 174.460 → **SL 315 pts, acima do teto de 300**. A regra aborta o trade. O “lance bonito” da máxima do dia **nem abriria**.

No WDO, os gatilhos das 11:20 (extremo) e 13:25 (Wall+extremo, `super`) caem na janela; a máxima das 18:20 não. Dado o resultado do WDO em jan–jul, não há motivo para tratar esses sinais como operáveis.

---

## 8. Problemas e ressalvas

- **O gráfico do dia não é um setup.** As marcas do v3.2 cravaram extremos em 13/11, mas a regra de stop (F2+30, teto 300) ou estopa a extensão ou aborta o trade na máxima.
- **G4 nasceu morto** com o desenho congelado (6 toques crus, 0 trades). Não foi afrouxado depois do fato.
- **WDO oficial ≠ V1a.** Sem módulo de abertura, a Tese 3 só gerou prejuízo grande e estável.
- **Placebo às vezes ganha da Tese 1.** O que o E22 já recusou por `super`/`seq` não é um estoque escondido de edge.
- **OOS contaminado** não foi usado para escolher, e mesmo como relato não reabilita ninguém (a menos ruim no IS, T2 G3 S2b, fica negativa em ago–nov).
- **Dado:** o backtest usa o dataset versionado `div_wall` + MT5 até 11/11. 13/11 não entra na métrica, só na conferência mecânica. O alerta da onda ao vivo × `.min` (item 2.4 do plano-mestre) continua sem conferência formal; G2/G3 dependem da onda.
- I5 e `B_dw_ex10` não foram rerodados, conforme a decisão 4.

---

## 9. Recomendação

1. **Não ativar** `ADD_WIN_EXT_REC`, `ADD_WIN_REJ_NWE` nem `ADD_WDO_V32_CORE`.
2. **Manter o `ESP_DIV_V22_WIN` como está** (2 contratos, regra atual).
3. Não reabrir a grade, não afrouxar o portão (N, PF, Ret/DD) e não calibrar stop/alvo em cima de 13/11.
4. Se no futuro houver outra tese, ela precisa nascer de um mecanismo que sobreviva ao placebo sem divergência e a um stop que ainda permita o trade no extremo do dia — o que esta grade, com as regras combinadas, não entregou.
